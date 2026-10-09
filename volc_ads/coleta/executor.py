"""Executor: GAQL → normalização → documento → RPC, em lotes, com recibo.

Não decide nada de negócio. A precedência, a idempotência e o NULL ≠ 0 moram
no banco (v12_04 / v17_01); aqui só se monta o documento certo e se conta.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from ..gads import catalogo
from .contrato import Contexto, Familia

CONTRATO_VERSAO = "coleta-v1"
LOTE_MAXIMO = 2000


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def contrato_sha256() -> str:
    """Impressão do contrato: muda quando o executor ou o contrato mudam."""
    from pathlib import Path

    aqui = Path(__file__).resolve().parent
    corpo = "".join((aqui / n).read_text(encoding="utf-8") for n in ("contrato.py", "executor.py"))
    return _sha(corpo)


@dataclass
class Recibo:
    familia: str
    lidas: int = 0
    descartadas: int = 0
    lotes: list[dict] = field(default_factory=list)
    fechamento: dict | None = None
    truncado: bool = False

    # A v17_01 devolve `aceitas`; a v12_04 devolve `linhas_aceitas`.
    @staticmethod
    def _conta(r: dict, chave: str) -> int:
        return int(r.get(chave, r.get(f"linhas_{chave}", 0)) or 0)

    @property
    def aceitas(self) -> int:
        return sum(self._conta(r, "aceitas") for r in self.lotes)

    @property
    def preteridas(self) -> int:
        return sum(self._conta(r, "preteridas") for r in self.lotes)

    @property
    def rejeitadas(self) -> int:
        return sum(self._conta(r, "rejeitadas") for r in self.lotes)

    def resumo(self) -> str:
        extra = " · ⚠️ TRUNCADA no LIMIT" if self.truncado else ""
        fecho = "" if self.fechamento is None else " · fechamento ok"
        return (f"{self.familia}: lidas {self.lidas} · descartadas {self.descartadas} · "
                f"aceitas {self.aceitas} · preteridas {self.preteridas} · "
                f"rejeitadas {self.rejeitadas} · lotes {len(self.lotes)}{fecho}{extra}")


def documento_padrao(familia: Familia, ctx: Contexto, linhas: list[dict], *,
                     lote: int, execucao_chave: str, iniciada: datetime) -> dict:
    agora = datetime.now(timezone.utc)
    return {
        "familia": familia.nome,
        "chave_idempotencia": f"{execucao_chave}:lote{lote}",
        "execucao_chave": execucao_chave,
        "job": f"gads_{familia.nome}",
        "fonte": "python_oneshot",
        "disparo": ctx.disparo,
        "customer_id": ctx.customer_id,
        "origem_janela": ctx.origem_janela,
        "janela_inicio": ctx.data_inicio.isoformat(),
        "janela_fim": ctx.data_fim.isoformat(),
        "api_versao": ctx.api_versao,
        "contrato_versao": CONTRATO_VERSAO,
        "contrato_sha256": contrato_sha256(),
        "lote_ordinal": lote,
        "iniciada_em": iniciada.isoformat(),
        "encerrada_em": agora.isoformat(),
        "batimento_em": agora.isoformat(),
        "linhas": linhas,
    }


def prefixo_do_passo(familia_nome: str, ctx: Contexto) -> str:
    """A `execucao_chave` sem o instante: identifica o PASSO (família, conta,
    janela e, na agenda, o passo). Cada tentativa ganha o instante no fim e,
    com ele, recibo próprio — retry guarda a falha E registra a recuperação."""
    base = (f"gads_{familia_nome}:{ctx.customer_id}:{ctx.origem_janela}:"
            f"{ctx.data_inicio.isoformat()}:{ctx.data_fim.isoformat()}")
    return f"{base}:passo{ctx.passo}" if ctx.passo else base


def passo_concluido(linhas_do_ledger: Iterable[dict], *, exige_fechamento: bool) -> bool:
    """Alguma tentativa deste passo terminou sem lote `falhou`?

    `linhas_do_ledger`: `execucao_chave`, `tipo_lote` e `resultado` das linhas do
    ledger cujo prefixo é o do passo. A família com fechamento só conta como
    concluída quando o fechamento existe (é ele que a RPC reconcilia).
    """
    por_tentativa: dict[str, list[dict]] = {}
    for l in linhas_do_ledger:
        por_tentativa.setdefault(str(l.get("execucao_chave")), []).append(l)
    for linhas in por_tentativa.values():
        if any(l.get("resultado") == "falhou" for l in linhas):
            continue
        if exige_fechamento and not any(l.get("tipo_lote") == "fechamento" for l in linhas):
            continue
        return True
    return False


def coletar(familia: Familia, ctx: Contexto, *,
            buscar: Callable[[str, str], Iterable[Any]],
            registrar: Callable[[str, dict], dict]) -> Recibo:
    """Roda uma família para um contexto.

    `buscar(customer_id, gaql)` devolve GoogleAdsRows (é `gads.client.buscar`
    com o login já resolvido); `registrar(rpc, documento)` chama a RPC.
    Os dois são injetados: o teste não fala com Google nem com banco.
    """
    iniciada = datetime.now(timezone.utc)
    recibo = Recibo(familia=familia.nome)
    consultas = familia.gaql(ctx)
    if isinstance(consultas, str):
        consultas = [consultas]
    linhas: list[dict] = []
    for gaql in consultas:
        catalogo.exigir_valida(gaql)
        for row in buscar(ctx.customer_id, gaql):
            recibo.lidas += 1
            linha = familia.normalizar(row, ctx)
            if linha is None:
                recibo.descartadas += 1
                continue
            linhas.append(linha)

    # Views por grupo de anúncios ou por anúncio (placement detail/group, asset)
    # repetem a identidade do fato. Sem somar aqui, a segunda linha empataria em
    # precedência e colhida_em e a RPC a contaria como "preterida": perda muda.
    consolidar = getattr(familia, "consolidar", None)
    if consolidar is not None:
        linhas = list(consolidar(linhas))

    # Uma execução por (família, conta, janela, instante de coleta): D0 roda
    # várias vezes ao dia e cada passada é uma leitura nova, com recibo próprio.
    execucao_chave = f"{prefixo_do_passo(familia.nome, ctx)}:{ctx.colhida_iso}"
    montar = getattr(familia, "documento", None)
    rpc = getattr(familia, "rpc", "volc_registrar_gads_fatos")
    # Sem linha nenhuma ainda se registra um lote vazio: "li e veio zero" é um
    # fato diferente de "não li".
    blocos = [linhas[i:i + LOTE_MAXIMO] for i in range(0, len(linhas), LOTE_MAXIMO)] or [[]]
    for n, bloco in enumerate(blocos, start=1):
        if montar is not None:
            doc = montar(ctx, bloco, lote=n, execucao_chave=execucao_chave, iniciada=iniciada)
        else:
            doc = documento_padrao(familia, ctx, bloco, lote=n,
                                   execucao_chave=execucao_chave, iniciada=iniciada)
        resposta = registrar(rpc, doc)
        recibo.lotes.append(resposta if isinstance(resposta, dict) else {"bruto": resposta})

    fechar = getattr(familia, "fechamento", None)
    if fechar is not None:
        doc = fechar(ctx, execucao_chave=execucao_chave, lotes=recibo.lotes, iniciada=iniciada)
        resposta = registrar(rpc, doc)
        recibo.fechamento = resposta if isinstance(resposta, dict) else {"bruto": resposta}

    limite = getattr(familia, "limite", None)
    if limite and recibo.lidas >= int(limite):
        recibo.truncado = True
    return recibo


def payload_sha(linhas: list[dict]) -> str:
    return _sha(json.dumps(linhas, sort_keys=True, ensure_ascii=False))
