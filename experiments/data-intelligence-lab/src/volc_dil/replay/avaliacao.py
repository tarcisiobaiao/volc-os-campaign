"""Avaliação posterior: resultado com verdade madura, separado das decisões.

Tudo em inteiros (micros, bps) para que o relatório seja byte a byte reprodutível.
Moedas nunca se somam: cada métrica monetária é reportada por moeda.
"""
from __future__ import annotations

from typing import Sequence

from volc_dil.contracts import ChaveUnidade, Dinheiro, json_canonico, sha256_de

from .cenario import EspecCenario, Mundo, repartir
from .motor import ExecucaoReplay

ESCALA_PESO = 10**9


def alocacao_oraculo(mundo: Mundo, i: int, *, com_ruido: bool = True) -> dict[ChaveUnidade, Dinheiro]:
    """Oráculo sob orçamento total fixo por moeda.

    `com_ruido=True`: informação perfeita do dia (eficiência latente × ruído realizado) — é o
    teto do regret pedido. `com_ruido=False`: conhece só os parâmetros latentes do dia
    (inclusive a quebra de regime), não o ruído — separa regret aprendível de irredutível.
    Com receita = e_i · s_i^b, o ótimo sob soma fixa é s_i ∝ e_i^(1/(1-b)).
    """
    b = mundo.espec.elasticidade
    saida: dict[ChaveUnidade, Dinheiro] = {}
    for moeda, total in mundo.orcamento_total().items():
        membros = sorted(u.chave for u in mundo.unidades if u.moeda == moeda)
        ef = mundo.eficiencia if com_ruido else mundo.alpha_efetivo
        brutos = [ef(c, i) ** (1 / (1 - b)) for c in membros]
        m = max(brutos)
        pesos = [int(round(x / m * ESCALA_PESO)) for x in brutos]
        for c, v in zip(membros, repartir(total, pesos)):
            saida[c] = Dinheiro(v, moeda)
    return saida


def _lucros_diarios(mundo: Mundo, alocacoes: Sequence[dict[ChaveUnidade, Dinheiro]]) -> dict[str, list[int]]:
    por_moeda: dict[str, list[int]] = {}
    for i, aloc in enumerate(alocacoes):
        dia: dict[str, int] = {}
        for c, v in aloc.items():
            rec = mundo.receita_verdadeira(c, i, v.micros)
            dia[v.moeda] = dia.get(v.moeda, 0) + rec - v.micros
        for m, x in dia.items():
            por_moeda.setdefault(m, []).append(x)
    return dict(sorted(por_moeda.items()))


def drawdown_maximo(diarios: Sequence[int]) -> int:
    pico = acum = 0
    pior = 0
    for x in diarios:
        acum += x
        pico = max(pico, acum)
        pior = max(pior, pico - acum)
    return pior


def _hhi_bps(valores: list[int]) -> int:
    tot = sum(valores)
    if tot == 0:
        return 0
    return sum(v * v for v in valores) * 10_000 // (tot * tot)


def metricas(execucao: ExecucaoReplay) -> dict:
    espec = execucao.espec
    mundo = Mundo(espec)
    lucro = _lucros_diarios(mundo, execucao.alocacoes)
    oraculo = _lucros_diarios(mundo, [alocacao_oraculo(mundo, i) for i in range(espec.n_dias)])
    oraculo_par = _lucros_diarios(mundo, [alocacao_oraculo(mundo, i, com_ruido=False) for i in range(espec.n_dias)])
    orc = mundo.orcamento_total()
    por_moeda = {}
    for moeda in orc:
        membros = sorted(c for c in execucao.alocacoes[0] if mundo.moeda_de(c) == moeda)
        hhis = [_hhi_bps([a[c].micros for c in membros]) for a in execucao.alocacoes]
        turn = []
        for ant, atu in zip(execucao.alocacoes, execucao.alocacoes[1:]):
            mov = sum(abs(atu[c].micros - ant[c].micros) for c in membros) // 2
            turn.append(mov * 10_000 // orc[moeda])
        total = sum(lucro[moeda])
        total_or = sum(oraculo[moeda])
        total_par = sum(oraculo_par[moeda])
        regret = total_or - total
        por_moeda[moeda] = {
            "n_unidades": len(membros),
            "lucro_realizado_micros": total,
            "lucro_oraculo_micros": total_or,
            "regret_micros": regret,
            "regret_bps_do_gasto": regret * 10_000 // (orc[moeda] * espec.n_dias),
            "lucro_oraculo_parametros_micros": total_par,
            "regret_vs_parametros_micros": total_par - total,
            "regret_vs_parametros_bps_do_gasto": (total_par - total) * 10_000 // (orc[moeda] * espec.n_dias),
            "drawdown_maximo_micros": drawdown_maximo(lucro[moeda]),
            "hhi_medio_bps": sum(hhis) // len(hhis),
            "turnover_medio_bps_dia": (sum(turn) // len(turn)) if turn else 0,
        }
    decs = execucao.decisoes
    return {
        "politica": execucao.politica,
        "declaracao": execucao.declaracao,
        "por_moeda": por_moeda,
        "n_decisoes": len(decs),
        "decisoes_com_dado_preliminar_declarado": sum(1 for d in decs if d.insumos_preliminares > 0),
        "decisoes_que_dependeram_de_preliminar_medido": (
            sum(1 for d in decs if d.dependeu_de_preliminar) if all(d.dependeu_de_preliminar is not None for d in decs)
            else None),
        "decisoes_sem_insumo": sum(1 for d in decs if d.insumos == 0),
        "exclusoes_unidade_dia": sum(len(d.excluidas) for d in decs),
        "notas_identidade": sum(len(d.notas) for d in decs),
        "n_observacoes_log": execucao.n_observacoes_log,
        "decisoes_sha256": sha256_de([d.para_json() for d in decs]),
    }


def relatorio_cenario(espec: EspecCenario, execucoes: Sequence[ExecucaoReplay]) -> dict:
    corpo = {"cenario": espec.para_json(), "politicas": [metricas(e) for e in execucoes]}
    corpo["relatorio_sha256"] = sha256_de(corpo)
    return corpo


def bytes_relatorio(rel: dict) -> bytes:
    return json_canonico(rel).encode("utf-8")
