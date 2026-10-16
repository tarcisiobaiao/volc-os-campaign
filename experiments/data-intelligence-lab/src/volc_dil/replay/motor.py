"""Motor de replay econômico v0 (malha fechada sobre mundo sintético).

Para cada dia de decisão `d` (a partir do 2º dia):
1. corte: o log de observações emitidas é cortado em `as_of = véspera 23:00` (dados com
   `disponivel_em <= as_of`) e limitado à janela de consulta;
2. ponto de consumo: `Snapshot.construir(..., politica_futuro="falhar")` — se o corte
   deixou passar qualquer observação posterior, levanta `VazamentoDeFuturo`;
3. a política recebe SÓ o snapshot + contexto; a decisão (alocação em micros com moeda
   explícita) é validada e registrada SEM resultado;
4. o mundo executa a alocação e emite as observações futuras (custo, receita preliminar,
   revisão) no log, cada uma com seu `disponivel_em`.

O resultado econômico (lucro com verdade madura) é calculado DEPOIS, em `avaliacao.py`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional, Sequence

from volc_dil.contracts import (
    ChaveUnidade,
    ContratoViolado,
    Dinheiro,
    Maturidade,
    MoedasDiferentes,
    Observacao,
    Snapshot,
)

from .cenario import EspecCenario, Mundo, as_of_decisao
from .politicas import ContextoDecisao, Decisao, Politica, declaracao

Cortador = Callable[[Sequence[Observacao], datetime, int], list[Observacao]]


def cortar_as_of(log: Sequence[Observacao], as_of: datetime, janela_dias: int) -> list[Observacao]:
    """Camada de dados: só o que era conhecido no as_of, dentro da janela de consulta."""
    desde = as_of - timedelta(days=janela_dias)
    return [o for o in log if o.disponivel_em <= as_of and o.janela_inicio >= desde]


@dataclass(frozen=True)
class RegistroDecisao:
    dia: str
    as_of: str
    politica: str
    snapshot_fingerprint: str
    n_obs_snapshot: int
    alocacao: dict[str, dict]  # entidade -> {micros, moeda}
    excluidas: dict[str, str]
    insumos: int
    insumos_preliminares: int  # autodeclarado pela política
    dependeu_de_preliminar: Optional[bool]  # MEDIDO pelo motor: decisão muda sem números preliminares?
    notas: tuple[str, ...]

    def para_json(self) -> dict:
        return {
            "dia": self.dia, "as_of": self.as_of, "politica": self.politica,
            "snapshot_fingerprint": self.snapshot_fingerprint, "n_obs_snapshot": self.n_obs_snapshot,
            "alocacao": self.alocacao, "excluidas": self.excluidas, "insumos": self.insumos,
            "insumos_preliminares": self.insumos_preliminares,
            "dependeu_de_preliminar": self.dependeu_de_preliminar, "notas": list(self.notas),
        }


@dataclass(frozen=True)
class ExecucaoReplay:
    espec: EspecCenario
    politica: str
    decisoes: tuple[RegistroDecisao, ...]
    alocacoes: tuple[dict[ChaveUnidade, Dinheiro], ...]  # uma por dia do horizonte
    n_observacoes_log: int
    declaracao: dict


def _assinatura(aloc: dict[ChaveUnidade, Dinheiro]) -> tuple:
    return tuple(sorted((u.entidade_id, u.conta, v.micros, v.moeda) for u, v in aloc.items()))


def validar_decisao(dec: Decisao, ctx: ContextoDecisao) -> None:
    universo = set(ctx.unidades)
    if set(dec.alocacao) != universo:
        raise ContratoViolado("decisão precisa alocar exatamente o universo de unidades")
    somas: dict[str, Dinheiro] = {}
    for u, v in dec.alocacao.items():
        if not isinstance(v, Dinheiro):
            raise ContratoViolado("alocação precisa ser Dinheiro")
        if v.moeda != ctx.moeda_por_unidade[u]:
            raise MoedasDiferentes(f"{u.entidade_id}: alocado em {v.moeda}, unidade opera em {ctx.moeda_por_unidade[u]}")
        if v.micros < 0:
            raise ContratoViolado("orçamento negativo")
        if v.micros < ctx.piso_micros[v.moeda]:
            raise ContratoViolado(f"{u.entidade_id}: {v.micros} abaixo do piso {ctx.piso_micros[v.moeda]} ({v.moeda})")
        somas[v.moeda] = somas[v.moeda] + v if v.moeda in somas else v
    for moeda, total in ctx.orcamento_total.items():
        if somas.get(moeda, Dinheiro(0, moeda)).micros != total:
            raise ContratoViolado(f"orçamento {moeda} não fecha: {somas.get(moeda)} != {total}")


def executar(
    espec: EspecCenario,
    politica: Politica,
    *,
    cortar: Cortador = cortar_as_of,
    janela_consulta_dias: int = 14,
    piso_bps: int = 1000,
    observador: Optional[Callable[[Snapshot, ContextoDecisao], None]] = None,
    medir_preliminar: bool = True,
) -> ExecucaoReplay:
    mundo = Mundo(espec)
    log: list[Observacao] = []
    alocacao = mundo.alocacao_inicial()
    unidades = tuple(u.chave for u in mundo.unidades)
    moedas = {u.chave: u.moeda for u in mundo.unidades}
    orc = mundo.orcamento_total()
    n_por_moeda = {m: sum(1 for u in mundo.unidades if u.moeda == m) for m in orc}
    piso = {m: orc[m] // n_por_moeda[m] * piso_bps // 10_000 for m in orc}
    decisoes: list[RegistroDecisao] = []
    alocacoes: list[dict[ChaveUnidade, Dinheiro]] = []
    for i in range(espec.n_dias):
        dia = mundo.dia(i)
        if i >= 1:
            as_of = as_of_decisao(dia)
            visiveis = cortar(log, as_of, janela_consulta_dias)
            snap = Snapshot.construir(visiveis, as_of, politica_futuro="falhar",
                                      rotulo=f"decisao/{dia.isoformat()}")  # opaco: sem cenário/seed (F1-01)
            ctx = ContextoDecisao(dia=dia, as_of=as_of, unidades=unidades, moeda_por_unidade=moedas,
                                  orcamento_total=orc, alocacao_atual=dict(alocacao), piso_micros=piso)
            if observador is not None:  # só para auditoria/testes; não altera a decisão
                observador(snap, ctx)
            dec = politica.decidir(snap, ctx)
            validar_decisao(dec, ctx)
            dependeu = None
            if medir_preliminar:
                # Medição por EFEITO (F1-06): mesma política, mesmo contexto, snapshot sem nenhum
                # número preliminar. Se a decisão muda, ela dependeu de preliminar — declare ou não.
                sem_prelim = [o for o in visiveis if not (o.maturidade is Maturidade.PRELIMINAR and o.valor is not None)]
                snap2 = Snapshot.construir(sem_prelim, as_of, politica_futuro="falhar", rotulo=f"decisao/{dia.isoformat()}")
                dec2 = politica.decidir(snap2, ctx)
                dependeu = _assinatura(dec.alocacao) != _assinatura(dec2.alocacao)
            alocacao = dict(dec.alocacao)
            decisoes.append(RegistroDecisao(
                dia=dia.isoformat(), as_of=as_of.isoformat(), politica=politica.nome,
                snapshot_fingerprint=snap.fingerprint, n_obs_snapshot=len(snap.observacoes),
                alocacao={u.entidade_id: v.para_json() for u, v in sorted(alocacao.items())},
                excluidas={u.entidade_id: m for u, m in sorted(dec.excluidas.items())},
                insumos=dec.insumos, insumos_preliminares=dec.insumos_preliminares,
                dependeu_de_preliminar=dependeu, notas=dec.notas))
        alocacoes.append(dict(alocacao))
        log.extend(mundo.emitir(i, alocacao))
    return ExecucaoReplay(espec, politica.nome, tuple(decisoes), tuple(alocacoes), len(log), declaracao(politica))


def log_completo(espec: EspecCenario, alocacoes: Sequence[dict[ChaveUnidade, Dinheiro]]) -> list[Observacao]:
    """Reemite o log inteiro de uma execução (para fixture/auditoria)."""
    mundo = Mundo(espec)
    saida: list[Observacao] = []
    for i, a in enumerate(alocacoes):
        saida.extend(mundo.emitir(i, a))
    return saida
