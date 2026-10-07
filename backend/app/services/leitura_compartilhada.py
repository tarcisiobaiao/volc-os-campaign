"""Leitura compartilhada: cache TTL curto + singleflight, só na memória do processo.

## O defeito que isto conserta

Duas engines repetiam a MESMA leitura externa cara, e cada repetição saía para
a rede como se fosse a primeira:

  * o Pautador relê Keyword Planner e DataForSEO para o mesmo termo, geo e
    idioma a cada mineração, embora essas fontes mudem no ritmo do dia;
  * `/provar` relê o plano de mensuração (até cinco GAQL) a cada clique, e o
    teto HTTP para de ESPERAR sem cancelar a thread — dez cliques numa conta em
    `RATE_EXCEEDED` deixavam dez threads iguais gastando a mesma quota.

## O que esta primitiva garante, e o que ela recusa

  * uma execução subjacente por chave enquanto houver leitura em voo — quem
    chega depois espera a mesma tarefa em vez de abrir outra;
  * o tempo de espera de um consumidor (timeout ou cancelamento) NÃO cancela o
    trabalho compartilhado: `asyncio.shield` separa os dois;
  * só entra no cache o valor que o chamador declara aceitável. Exceção,
    timeout, `None` e resposta parcial nunca entram — e "vazio medido" não é
    confundido com falha, porque quem decide é o predicado do dono da leitura,
    não um `if valor`;
  * memória do processo, TTL explícito por chamada, teto de entradas (LRU) e
    relógio monotônico injetável. Nada vai para banco, disco ou rede.

⚠️ A chave é um SHA-256 de partes JSON canônicas. Nenhum payload, token ou
credencial entra nela nem na telemetria; quem monta a chave escolhe as partes
que mudam a resposta, e só elas.

⚠️ Este módulo não sabe nada de Google Ads, DataForSEO ou plano de mensuração.
O que é "aceitável" e o que entra na chave pertencem a quem chama.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
import weakref
from collections import OrderedDict
from dataclasses import dataclass
from functools import partial
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

log = logging.getLogger("volc.leitura_compartilhada")

#: O valor veio do cache, dentro do TTL.
HIT = "hit"
#: Ninguém tinha o valor nem estava lendo: esta chamada abriu a leitura.
MISS = "miss"
#: Já havia uma leitura em voo para a mesma chave, e esta chamada a aguardou.
COMPARTILHADA = "compartilhada"
#: O chamador exigiu leitura própria: sem cache e sem pegar carona.
FRESCA = "fresca"

#: Toda instância viva, para `limpar_todas()` — o gancho dos testes. Fraca para
#: não prolongar a vida de um cache que alguém trocou por monkeypatch.
_INSTANCIAS: "weakref.WeakSet[LeituraCompartilhada]" = weakref.WeakSet()


def limpar_todas() -> None:
    """Esquece o conteúdo de todo cache de leitura do processo.

    ⚠️ Existe para os testes: o cache é de módulo, e sem isto o valor dublado
    num teste seria servido como hit no teste seguinte.
    """
    for instancia in list(_INSTANCIAS):
        instancia.limpar()


def chave_canonica(*partes: Any) -> str:
    """SHA-256 das partes em JSON canônico. Determinística entre processos.

    ⚠️ Sem `default=`: um objeto que não serializa em JSON levanta `TypeError`
    em vez de virar `repr()` — e `repr()` de objeto carrega endereço de memória,
    o que daria uma chave diferente a cada processo sem ninguém perceber.
    """
    bruto = json.dumps(list(partes), ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"))
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Recibo:
    """Como o valor chegou. Não carrega chave nem valor — só a procedência."""

    origem: str
    #: Idade do valor servido do cache, em segundos. `None` quando foi lido
    #: agora (ou aguardado de uma leitura em voo).
    idade_s: Optional[float] = None


class LeituraCompartilhada:
    """Cache TTL + singleflight para UMA família de leituras read-only."""

    def __init__(self, nome: str, *, max_entradas: int,
                 relogio: Callable[[], float] = time.monotonic) -> None:
        self.nome = nome
        self._max = max(1, int(max_entradas))
        self._relogio = relogio
        # ⚠️ Um lock de thread, e não de asyncio: o `TestClient` e o
        # `asyncio.run` de cada teste rodam laços diferentes, às vezes em
        # threads diferentes, sobre o MESMO objeto de módulo.
        self._lock = threading.Lock()
        self._valores: "OrderedDict[str, Tuple[float, float, Any]]" = OrderedDict()
        self._em_voo: Dict[str, "asyncio.Task[Any]"] = {}
        self._contagem: Dict[str, int] = {
            HIT: 0, MISS: 0, COMPARTILHADA: 0, FRESCA: 0,
            "guardada": 0, "descartada": 0, "erro": 0,
        }
        _INSTANCIAS.add(self)

    # ── ganchos de teste e telemetria ────────────────────────────────────────

    def limpar(self) -> None:
        """Esquece valores e contadores. Leituras em voo seguem até o fim, mas
        deixam de ser encontradas por chamadas novas."""
        with self._lock:
            self._valores.clear()
            self._em_voo.clear()
            for k in self._contagem:
                self._contagem[k] = 0

    def telemetria(self) -> Dict[str, int]:
        with self._lock:
            return {**self._contagem, "entradas": len(self._valores),
                    "em_voo": len(self._em_voo)}

    # ── a leitura ────────────────────────────────────────────────────────────

    async def obter(
        self,
        chave: str,
        leitor: Callable[[], Awaitable[Any]],
        *,
        ttl_s: float,
        aceitavel: Callable[[Any], bool],
        fresco: bool = False,
        timeout_s: Optional[float] = None,
    ) -> Tuple[Any, Recibo]:
        """O valor da chave e a procedência dele.

        `aceitavel(valor)` decide o que pode ser guardado. Exceção do leitor
        sobe para quem chamou e não é guardada. `ttl_s <= 0` desliga o cache e
        mantém só o singleflight.

        `fresco=True` ignora o cache E as leituras em voo: o chamador quer uma
        leitura que começou depois do pedido dele. O resultado, se aceitável,
        ainda é guardado — ele é a leitura mais nova que existe.

        `timeout_s` limita a ESPERA deste consumidor (`asyncio.TimeoutError`),
        nunca a leitura compartilhada.
        """
        loop = asyncio.get_running_loop()
        with self._lock:
            tarefa: Optional["asyncio.Task[Any]"] = None
            if not fresco:
                agora = self._relogio()
                entrada = self._valores.get(chave)
                if entrada is not None:
                    gravado_em, expira_em, valor = entrada
                    if agora < expira_em:
                        self._valores.move_to_end(chave)
                        self._contagem[HIT] += 1
                        return valor, Recibo(HIT, max(0.0, agora - gravado_em))
                    del self._valores[chave]
                tarefa = self._em_voo.get(chave)
                # Uma tarefa de OUTRO laço (já encerrado, num teste, ou vivo em
                # outra thread) não pode ser aguardada daqui.
                if tarefa is not None and (tarefa.done()
                                           or tarefa.get_loop() is not loop):
                    tarefa = None
            if tarefa is not None:
                self._contagem[COMPARTILHADA] += 1
                origem = COMPARTILHADA
            else:
                tarefa = loop.create_task(
                    self._ler(chave, leitor, ttl_s=ttl_s, aceitavel=aceitavel))
                if fresco:
                    self._contagem[FRESCA] += 1
                    origem = FRESCA
                else:
                    self._em_voo[chave] = tarefa
                    self._contagem[MISS] += 1
                    origem = MISS
                tarefa.add_done_callback(partial(self._largar, chave))

        espera = asyncio.shield(tarefa)
        if timeout_s is None:
            valor = await espera
        else:
            valor = await asyncio.wait_for(espera, timeout=timeout_s)
        return valor, Recibo(origem)

    async def _ler(self, chave: str, leitor: Callable[[], Awaitable[Any]], *,
                   ttl_s: float, aceitavel: Callable[[Any], bool]) -> Any:
        try:
            valor = await leitor()
        except BaseException:
            with self._lock:
                self._contagem["erro"] += 1
            raise
        guardar = ttl_s > 0 and bool(aceitavel(valor))
        with self._lock:
            if not guardar:
                self._contagem["descartada"] += 1
                return valor
            agora = self._relogio()
            self._valores[chave] = (agora, agora + float(ttl_s), valor)
            self._valores.move_to_end(chave)
            while len(self._valores) > self._max:
                self._valores.popitem(last=False)
            self._contagem["guardada"] += 1
        return valor

    def _largar(self, chave: str, tarefa: "asyncio.Task[Any]") -> None:
        with self._lock:
            if self._em_voo.get(chave) is tarefa:
                del self._em_voo[chave]
        # ⚠️ Recolhe a exceção: quando todo consumidor desistiu por timeout,
        # ninguém mais a lê, e o asyncio registraria "Task exception was never
        # retrieved" — ruído que esconde a falha verdadeira no log.
        if not tarefa.cancelled():
            exc = tarefa.exception()
            if exc is not None:
                log.debug("leitura compartilhada %s falhou: %s", self.nome,
                          type(exc).__name__)
