"""Políticas de alocação (baselines). Recebem SÓ o `Snapshot` e um contexto sem dado do mundo.

Contexto = configuração e estado próprio da política (universo de unidades, moeda de
cada uma, orçamento total por moeda, alocação vigente que ela mesma decidiu, piso).
Nenhum campo do contexto vem da verdade do mundo.

Regras comuns:
- pareamento custo×receita só por identidade exata (`ChaveUnidade` inteira, inclusive conta);
- moedas nunca se somam: cada moeda tem seu próprio orçamento e é decidida em separado;
- valor ausente não vira zero: dia sem valor é pulado com motivo; unidade sem nenhum valor
  fica FORA da realocação, mantendo a alocação vigente, com motivo registrado.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from fractions import Fraction
from typing import Mapping, Optional, Protocol

from volc_dil.contracts import (
    ChaveUnidade,
    Cobertura,
    Dinheiro,
    Maturidade,
    Metrica,
    Observacao,
    Snapshot,
    VazamentoDeFuturo,
    contribuicao,
    verificar_sem_futuro,
)
from volc_dil.contracts.vocab import COM_VALOR

from .cenario import dia_de, repartir


@dataclass(frozen=True)
class ContextoDecisao:
    dia: date  # dia ao qual o orçamento se aplica
    as_of: datetime
    unidades: tuple[ChaveUnidade, ...]
    moeda_por_unidade: Mapping[ChaveUnidade, str]
    orcamento_total: Mapping[str, int]  # micros por moeda
    alocacao_atual: Mapping[ChaveUnidade, Dinheiro]
    piso_micros: Mapping[str, int]


@dataclass(frozen=True)
class Decisao:
    alocacao: dict[ChaveUnidade, Dinheiro]
    excluidas: dict[ChaveUnidade, str] = field(default_factory=dict)
    insumos: int = 0  # observações de receita efetivamente usadas
    insumos_preliminares: int = 0  # dessas, quantas eram preliminares (autodeclarado pela política)
    notas: tuple[str, ...] = ()


class Politica(Protocol):
    nome: str

    def decidir(self, snapshot: Snapshot, ctx: ContextoDecisao) -> Decisao: ...


# ── utilitários ────────────────────────────────────────────────────────────

def exigir_snapshot_do_corte(snapshot: Snapshot, ctx: ContextoDecisao) -> None:
    """Guarda no ponto de consumo: nada no snapshot pode ser posterior ao as_of da decisão."""
    if snapshot.as_of != ctx.as_of:
        raise VazamentoDeFuturo(f"snapshot as_of {snapshot.as_of.isoformat()} != decisão {ctx.as_of.isoformat()}")
    verificar_sem_futuro(snapshot.observacoes, ctx.as_of)


def indexar(snapshot: Snapshot) -> dict[tuple[ChaveUnidade, Metrica, date], Observacao]:
    idx: dict[tuple[ChaveUnidade, Metrica, date], Observacao] = {}
    for o in snapshot.observacoes:
        k = (o.unidade, o.metrica, dia_de(o))
        if k in idx:  # duas fontes para o mesmo fato: o v0 recusa em vez de escolher
            raise ValueError(f"mais de uma observação para {o.unidade.entidade_id}/{o.metrica.value}/{k[2]}")
        idx[k] = o
    return idx


def notas_identidade(snapshot: Snapshot, ctx: ContextoDecisao) -> tuple[str, ...]:
    """Observações fora do universo são ignoradas; se colidem por entidade_id, isso é dito."""
    universo = set(ctx.unidades)
    ids = {u.entidade_id: u for u in ctx.unidades}
    notas = set()
    for o in snapshot.observacoes:
        if o.unidade in universo:
            continue
        if o.unidade.entidade_id in ids:
            notas.add(f"identidade_incompativel: {o.unidade.entidade_id} na conta {o.unidade.conta} "
                      f"(universo usa {ids[o.unidade.entidade_id].conta}); ignorada")
        else:
            notas.add(f"fora_do_universo: {o.unidade.conta}/{o.unidade.entidade_id}; ignorada")
    return tuple(sorted(notas))


def _por_moeda(ctx: ContextoDecisao) -> dict[str, list[ChaveUnidade]]:
    g: dict[str, list[ChaveUnidade]] = {}
    for u in ctx.unidades:
        g.setdefault(ctx.moeda_por_unidade[u], []).append(u)
    return {m: sorted(us) for m, us in sorted(g.items())}


def alocar_com_piso(total: int, piso: int, chaves: list[ChaveUnidade], pesos: list[int]) -> dict[ChaveUnidade, int]:
    n = len(chaves)
    if n == 0:
        return {}
    piso_ef = min(piso, total // n)
    resto = total - piso_ef * n
    extra = repartir(resto, pesos)
    return {c: piso_ef + e for c, e in zip(chaves, extra)}


# ── baselines ──────────────────────────────────────────────────────────────

class Estatica:
    """current/static: mantém a alocação vigente."""

    nome = "static"

    def decidir(self, snapshot: Snapshot, ctx: ContextoDecisao) -> Decisao:
        exigir_snapshot_do_corte(snapshot, ctx)
        return Decisao(dict(ctx.alocacao_atual), notas=notas_identidade(snapshot, ctx))


class Igual:
    """equal: orçamento de cada moeda dividido igualmente."""

    nome = "equal"

    def decidir(self, snapshot: Snapshot, ctx: ContextoDecisao) -> Decisao:
        exigir_snapshot_do_corte(snapshot, ctx)
        aloc: dict[ChaveUnidade, Dinheiro] = {}
        for moeda, us in _por_moeda(ctx).items():
            for c, v in zip(us, repartir(ctx.orcamento_total[moeda], [1] * len(us))):
                aloc[c] = Dinheiro(v, moeda)
        return Decisao(aloc, notas=notas_identidade(snapshot, ctx))


@dataclass
class Proporcional:
    """proportional: pesos = contribuição contábil média diária conhecida (receita − custo).

    Usa a versão mais recente conhecida (inclusive PRELIMINAR). Dia sem valor é pulado
    (média só sobre dias com valor); unidade sem nenhum dia com valor fica fora com motivo
    e mantém a alocação vigente. Contribuição <= 0 recebe só o piso.
    """

    janela_dias: int = 7
    nome: str = "proportional"
    ausente_como_zero: bool = False  # True = anti-baseline ingênua (bug deliberado)

    def _medias(self, snapshot: Snapshot, ctx: ContextoDecisao):
        idx = indexar(snapshot)
        medias: dict[ChaveUnidade, int] = {}
        motivos: dict[ChaveUnidade, str] = {}
        insumos = prelim = 0
        dias = [ctx.dia - timedelta(days=k) for k in range(1, self.janela_dias + 1)]
        for u in ctx.unidades:
            soma, n, porque = 0, 0, []
            for d in dias:
                c = idx.get((u, Metrica.CUSTO, d))
                r = idx.get((u, Metrica.RECEITA, d))
                if self.ausente_como_zero:
                    # BUG DELIBERADO: o que não tem valor (ou nem existe) entra como 0.
                    cv = c.valor.micros if c is not None and c.estado in COM_VALOR else 0
                    rv = r.valor.micros if r is not None and r.estado in COM_VALOR else 0
                    soma += rv - cv
                    if r is not None and r.estado in COM_VALOR:
                        insumos += 1
                        prelim += r.maturidade is Maturidade.PRELIMINAR
                    continue
                if c is None or r is None:
                    porque.append(f"{d}:sem_{'custo' if c is None else 'receita'}")
                    continue
                contrib = contribuicao(c, r)  # exige mesma identidade, janela e timezone
                if contrib.valor is None:
                    porque.append(f"{d}:{contrib.motivo}")
                    continue
                soma += contrib.valor.micros
                n += 1
                insumos += 1
                prelim += r.maturidade is Maturidade.PRELIMINAR
            if self.ausente_como_zero:
                medias[u] = soma // self.janela_dias  # lacuna pesa como zero na média
            elif n == 0:
                motivos[u] = "sem contribuição com valor na janela (null != 0): " + ";".join(porque[:3])
            else:
                medias[u] = soma // n
        return medias, motivos, insumos, prelim

    def decidir(self, snapshot: Snapshot, ctx: ContextoDecisao) -> Decisao:
        exigir_snapshot_do_corte(snapshot, ctx)
        medias, motivos, insumos, prelim = self._medias(snapshot, ctx)
        aloc: dict[ChaveUnidade, Dinheiro] = {}
        for moeda, us in _por_moeda(ctx).items():
            fora = [u for u in us if u in motivos]
            dentro = [u for u in us if u not in motivos]
            congelado = sum(ctx.alocacao_atual[u].micros for u in fora)
            for u in fora:
                aloc[u] = ctx.alocacao_atual[u]
            disponivel = ctx.orcamento_total[moeda] - congelado
            pesos = [max(medias[u], 0) for u in dentro]
            for c, v in alocar_com_piso(disponivel, ctx.piso_micros[moeda], dentro, pesos).items():
                aloc[c] = Dinheiro(v, moeda)
        return Decisao(aloc, excluidas=motivos, insumos=insumos, insumos_preliminares=prelim,
                       notas=notas_identidade(snapshot, ctx))


def proporcional_ingenua(janela_dias: int = 7) -> Proporcional:
    """Anti-baseline: trata receita/custo sem valor como 0. Existe para ser detectada."""
    return Proporcional(janela_dias=janela_dias, nome="proportional_naive_null_as_zero", ausente_como_zero=True)


@dataclass
class GulosaConservadora:
    """greedy_conservador: só realoca entre unidades com receita MADURA e cobertura completa.

    Janela madura = os `janela_dias` dias mais recentes cuja revisão já devia ter chegado.
    Elegível = todos os dias da janela com custo e receita revisada/madura, cobertura completa
    e valor. Pares (melhor ROI, pior ROI) trocam até `teto_bps` da alocação vigente por passo,
    só se ROI_melhor > ROI_pior × (1 + margem). Não usa preliminar por construção.
    """

    janela_dias: int = 7
    dias_maturacao: int = 4  # revisão do dia k chega em k+3 06:00; decisão às 23:00 de dia-1
    teto_bps: int = 2000
    margem_bps: int = 500
    nome: str = "greedy_conservador"

    def decidir(self, snapshot: Snapshot, ctx: ContextoDecisao) -> Decisao:
        exigir_snapshot_do_corte(snapshot, ctx)
        idx = indexar(snapshot)
        dias = [ctx.dia - timedelta(days=self.dias_maturacao + k) for k in range(self.janela_dias)]
        roi: dict[ChaveUnidade, Fraction] = {}
        motivos: dict[ChaveUnidade, str] = {}
        insumos = 0
        for u in ctx.unidades:
            rec = cus = 0
            falta: Optional[str] = None
            for d in dias:
                c = idx.get((u, Metrica.CUSTO, d))
                r = idx.get((u, Metrica.RECEITA, d))
                if c is None or c.estado not in COM_VALOR:
                    falta = f"{d}:custo_sem_valor"
                    break
                if r is None or r.estado not in COM_VALOR:
                    falta = f"{d}:receita_sem_valor"
                    break
                if r.maturidade is Maturidade.PRELIMINAR or r.cobertura is not Cobertura.COMPLETA:
                    falta = f"{d}:receita_nao_madura"
                    break
                contrib = contribuicao(c, r)  # exige mesma identidade/janela/tz
                if contrib.valor is None:
                    falta = f"{d}:{contrib.motivo}"
                    break
                rec += r.valor.micros
                cus += c.valor.micros
            if falta is not None:
                motivos[u] = "cobertura madura incompleta: " + falta
            elif cus == 0:
                motivos[u] = "custo zero confirmado na janela: ROI indefinido"
            else:
                roi[u] = Fraction(rec, cus)
                insumos += len(dias)
        aloc = {u: ctx.alocacao_atual[u] for u in ctx.unidades}
        for moeda, us in _por_moeda(ctx).items():
            elegiveis = sorted((u for u in us if u in roi), key=lambda u: (-roi[u], u))
            piso = ctx.piso_micros[moeda]
            i, j = 0, len(elegiveis) - 1
            while i < j:
                melhor, pior = elegiveis[i], elegiveis[j]
                if roi[melhor] <= roi[pior] * Fraction(10_000 + self.margem_bps, 10_000):
                    break
                cm, cp = aloc[melhor].micros, aloc[pior].micros
                delta = min(cp * self.teto_bps // 10_000, cm * self.teto_bps // 10_000, max(cp - piso, 0))
                if delta > 0:
                    aloc[melhor] = Dinheiro(cm + delta, moeda)
                    aloc[pior] = Dinheiro(cp - delta, moeda)
                i += 1
                j -= 1
        return Decisao(aloc, excluidas=motivos, insumos=insumos, insumos_preliminares=0,
                       notas=notas_identidade(snapshot, ctx))


def baselines() -> list:
    return [Estatica(), Igual(), Proporcional(), GulosaConservadora()]
