"""O operario como PROCESSO, fora do processo web.

## O defeito que este modulo fecha

Ate aqui, produzir uma peca acontecia dentro do request. Duas medicoes desta
rodada:

  1. `POST /api/criativos/jobs` e `async def`, logo roda NA THREAD DO EVENT LOOP.
     Dali, `execucao.disparar` chamava `anyio.from_thread.run(...)`, que so
     funciona dentro de uma worker thread do anyio. Resultado reproduzido:
     `NoEventLoopError` sem tratamento, rota 500, e o job ja gravado como
     `queued` que ninguem nunca executa.
  2. O proprio fail-closed explodia: o fallback `anyio.run(marcar)` era chamado
     de dentro de um loop ja rodando e levantava
     `RuntimeError: Already running asyncio in this thread`. O job nao virava
     `failed`, nao recebia motivo e nao recebia carimbo terminal.

  E, mesmo quando funcionava, `POST /api/criativos/bancada/trabalhos` chamava
  `DespachanteLocal.despachar` — inteiramente sincrono — na thread do loop:
  durante todo o render, NENHUMA outra requisicao do processo era atendida.
  Nao e lentidao da rota; e parada do servidor.

A resposta nao e "chamar de outro jeito". E o trabalho sair do processo web.

## O que este worker e

Um processo. Sobe sozinho, reivindica trabalho pelo deposito, renova o lease,
produz, valida, assina o recibo e volta para a fila. Ele NAO importa
`app.main`, nao abre porta HTTP e nao depende de request nenhum.

    python -m app.criativo.bancada.worker
    python -m app.criativo.bancada.worker --uma-vez        # um trabalho e sai
    python -m app.criativo.bancada.worker --ate-esvaziar   # ate a fila zerar
    CRIATIVO_DEPOSITO=postgres CRIATIVO_DEPOSITO_DSN=... python -m app.criativo.bancada.worker

## Interrompivel sem perder nem duplicar

O aceite do P17-T05 diz "pode ser interrompido sem perder ou duplicar trabalho".
Sao duas garantias diferentes e cada uma tem um mecanismo:

  · **nao perder** — SIGTERM/SIGINT nao matam o trabalho em voo. O laco marca
    que deve parar e deixa o trabalho ATUAL terminar; so entao sai. Um segundo
    sinal e a saida dura, e ai o lease vence e o trabalho volta para a fila
    pelo recolhedor. Em nenhum dos dois casos o pedido some.
  · **nao duplicar** — quem reivindica e o deposito, com exclusao mutua real
    (`BEGIN IMMEDIATE` no SQLite, `for update skip locked` no Postgres), e a
    idempotencia e por conteudo. Dois workers na mesma fila nunca pegam o mesmo
    trabalho; um worker que morre e volta nao refaz o que ja concluiu, porque
    `rendered` e terminal.

⚠️ Saida dura NAO marca o trabalho como falho. Um operario que morreu nao torna
o pedido invalido — essa decisao ja e do deposito, pelo vencimento do lease.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("bancada.worker")


class Parada:
    """Um pedido de parada que chega por sinal e e lido pelo laco.

    ⚠️ Nao usa `sys.exit` dentro do handler de proposito. Sair de dentro do
    handler mata o processo no meio do render — que e exatamente o "perder
    trabalho" que o aceite proibe. O handler so levanta a bandeira; quem decide
    quando parar e o laco, entre um trabalho e outro.
    """

    def __init__(self) -> None:
        self._evento = threading.Event()
        self.sinais: list[str] = []

    @property
    def pedida(self) -> bool:
        return self._evento.is_set()

    def esperar(self, segundos: float) -> bool:
        """Dorme, mas acorda na hora se a parada chegar."""
        return self._evento.wait(segundos)

    def instalar(self) -> Parada:
        def receber(numero: int, _quadro: Any) -> None:
            nome = signal.Signals(numero).name
            self.sinais.append(nome)
            if self._evento.is_set():
                # ⚠️ Segundo sinal e saida dura, e ela e DECLARADA. Sem isto, um
                # operador que pede parada duas vezes fica preso a um render
                # longo e recorre ao SIGKILL, que nao deixa nem log.
                log.warning("%s pela segunda vez: saindo sem esperar o trabalho atual",
                            nome)
                os._exit(130)
            log.info("%s recebido: termino o trabalho atual e saio", nome)
            self._evento.set()

        for s in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(s, receber)
            except ValueError:
                # Fora da thread principal (teste embutido). A bandeira continua
                # funcionando; so nao ha sinal para levanta-la.
                log.debug("sem handler para %s nesta thread", s)
        return self


def carregar_motor(referencia: str) -> Any:
    """Instancia um motor a partir de `modulo:Classe`.

    ⚠️ Ponto de extensao declarado, e nao gancho de teste disfarçado. Um motor
    que mora fora do nucleo — um adaptador de video, um provider novo — precisa
    entrar no worker sem que o nucleo o importe. A referencia e resolvida pelo
    `sys.path` do PROCESSO DO WORKER, que e outro processo: nada disto alcanca
    o processo web.
    """
    import importlib  # noqa: PLC0415

    try:
        modulo, _, classe = referencia.partition(":")
        if not modulo or not classe:
            raise ValueError("use `modulo:Classe`")
        return getattr(importlib.import_module(modulo), classe)()
    except Exception as e:  # noqa: BLE001
        # Falha ao carregar motor e falha do worker, nao motor silenciosamente
        # ausente: um trabalho que pedisse esse motor falharia com
        # `motor_desconhecido` e ninguem saberia por que.
        raise RuntimeError(f"nao consegui carregar o motor `{referencia}`: {e}") from e


def montar_operario(
    *, nome: str | None = None, lease_s: int = 60, raiz: str | Path | None = None,
    motores_extra: list[str] | None = None,
) -> tuple[Any, Any]:
    """O deposito da porta unica e um operario com os motores desta maquina.

    ⚠️ Nao reimplementa registro de motor. `servico.montar()` ja decide quais
    motores esta maquina consegue rodar, e ter duas listas de motores seria a
    mesma dupla verdade que a porta de deposito acabou de eliminar.
    """
    from .operario import Operario  # noqa: PLC0415
    from .porta import escolher_deposito  # noqa: PLC0415
    from .servico import montar as montar_bancada, raiz_da_bancada  # noqa: PLC0415

    _dep_local, operario_local, _desp = montar_bancada()
    base = Path(raiz) if raiz else raiz_da_bancada()
    deposito = escolher_deposito(caminho_sqlite=base / "fila.db")
    motores = dict(operario_local.motores)
    for referencia in motores_extra or []:
        motor = carregar_motor(referencia)
        motores[motor.slug] = motor
    operario = Operario(
        deposito,
        motores,
        base / "trabalhos",
        nome=nome or f"worker-{os.getpid()}",
        lease_s=lease_s,
        # ⚠️ A loja vem do operario que `servico.montar()` ja construiu, pelo
        # MESMO motivo que os motores vem: duas listas de motores seriam duas
        # verdades, e duas decisoes de armazenamento tambem. Sem esta linha o
        # worker — que e justamente quem PRODUZ — seria o unico operario da casa
        # sem loja, e a peca ficaria no disco de um processo que ja saiu.
        loja=operario_local.loja,
    )
    return deposito, operario


def rodar(
    *,
    nome: str | None = None,
    lease_s: int = 60,
    intervalo_s: float = 2.0,
    uma_vez: bool = False,
    ate_esvaziar: bool = False,
    limite: int | None = None,
    raiz: str | Path | None = None,
    motores_extra: list[str] | None = None,
    parada: Parada | None = None,
) -> dict[str, Any]:
    """O laco. Devolve o que aconteceu, para o teste poder afirmar sobre isso."""
    from .operario import Reaper  # noqa: PLC0415

    parada = parada or Parada()
    deposito, operario = montar_operario(
        nome=nome, lease_s=lease_s, raiz=raiz, motores_extra=motores_extra
    )

    # ⚠️ O recolhedor roda AQUI e nao no processo web. Medicao desta rodada:
    # `iniciar_reaper` tinha ZERO chamadores em todo o repositorio — a unica
    # ocorrencia era a propria definicao. Ou seja, a promessa "o trabalho volta
    # para a fila" era verdadeira no deposito e falsa na operacao: um trabalho
    # abandonado so voltava se, por acaso, outro pedido chegasse.
    reaper = Reaper(deposito, intervalo_s=max(1.0, lease_s / 3)).iniciar()

    feitos: list[str] = []
    ocioso = 0
    try:
        while not parada.pedida:
            if limite is not None and len(feitos) >= limite:
                break
            trabalho = deposito.reivindicar(operario.nome, lease_s=lease_s)
            if trabalho is None:
                ocioso += 1
                if uma_vez or ate_esvaziar:
                    break
                if parada.esperar(intervalo_s):
                    break
                continue
            ocioso = 0
            log.info("reivindiquei %s (tentativa %d)", trabalho.id, trabalho.tentativa)
            final = operario.executar(trabalho)
            feitos.append(trabalho.id)
            log.info("trabalho %s terminou em %s", trabalho.id, final.estado.value)
            if uma_vez:
                break
    finally:
        reaper.parar()
    return {
        "operario": operario.nome,
        "feitos": feitos,
        "rodadas_ociosas": ocioso,
        "parada_pedida": parada.pedida,
        "sinais": list(parada.sinais),
        "reaper_devolveu": reaper.devolvidos,
    }


def principal(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m app.criativo.bancada.worker",
        description="O operario da bancada criativa, como processo proprio.",
    )
    p.add_argument("--nome", default=None, help="nome do operario (aparece na trilha)")
    p.add_argument("--lease", type=int, default=60, help="segundos de lease por claim")
    p.add_argument("--intervalo", type=float, default=2.0,
                   help="segundos de espera quando a fila esta vazia")
    p.add_argument("--uma-vez", action="store_true", help="pega um trabalho e sai")
    p.add_argument("--ate-esvaziar", action="store_true",
                   help="trabalha ate a fila zerar e sai")
    p.add_argument("--limite", type=int, default=None,
                   help="para depois de N trabalhos (para prova)")
    p.add_argument("--raiz", default=None, help="raiz da bancada (padrao: CRIATIVO_BANCADA_DIR)")
    p.add_argument("--motor", action="append", default=[], metavar="modulo:Classe",
                   help="registra um motor extra neste worker (repetivel)")
    a = p.parse_args(argv)

    logging.basicConfig(
        level=os.environ.get("CRIATIVO_WORKER_LOG", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    inicio = time.monotonic()
    saida = rodar(
        nome=a.nome, lease_s=a.lease, intervalo_s=a.intervalo,
        uma_vez=a.uma_vez, ate_esvaziar=a.ate_esvaziar, limite=a.limite,
        raiz=a.raiz, motores_extra=a.motor, parada=Parada().instalar(),
    )
    log.info("worker %s encerrou: %d trabalho(s) em %.1fs (sinais: %s)",
             saida["operario"], len(saida["feitos"]), time.monotonic() - inicio,
             ",".join(saida["sinais"]) or "nenhum")
    return 0


if __name__ == "__main__":  # pragma: no cover — ponto de entrada do processo
    sys.exit(principal())
