"""Execução de Monte Carlo (mesmas seeds e cenários para todas as políticas), agregação com IC
e avaliação do critério pré-registrado."""
from __future__ import annotations

import math
from typing import Callable

import numpy as np

from volc_dil.swarm.cenario import CenarioRealizado, ParametrosCenario, gerar_cenario
from volc_dil.swarm.politicas import Oraculo
from volc_dil.swarm.simulador import metricas_execucao, simular

Z95 = 1.959963984540054
Fabrica = Callable[[CenarioRealizado], object]


def rng_politica(seed: int) -> np.random.Generator:
    # Mesmo gerador para todas as políticas na mesma seed (sorteios de política comparáveis).
    return np.random.default_rng(np.random.SeedSequence([int(seed), 0xB0A7]))


def rodar_seed(params: ParametrosCenario, seed: int, fabricas: dict[str, Fabrica]) -> dict[str, dict]:
    cen = gerar_cenario(params, seed)
    oraculo = simular(cen, Oraculo(cen), rng_politica(seed))
    saida = {}
    for nome, fab in fabricas.items():
        pol = fab(cen)
        pol.nome = nome
        res = oraculo if nome == "oraculo" else simular(cen, pol, rng_politica(seed))
        saida[nome] = metricas_execucao(res, cen, oraculo.contribuicao_esperada)
    return saida


def rodar_cenario(params: ParametrosCenario, seeds: list[int], fabricas: dict[str, Fabrica]) -> dict[str, dict[str, list]]:
    """-> {politica: {metrica: [valor por seed]}} (ordem das seeds preservada)."""
    acum: dict[str, dict[str, list]] = {n: {} for n in fabricas}
    for s in seeds:
        for nome, met in rodar_seed(params, s, fabricas).items():
            for k, v in met.items():
                acum[nome].setdefault(k, []).append(v)
    return acum


def ic_media(valores) -> dict:
    v = np.asarray([np.nan if x is None else x for x in valores], dtype=float)
    f = v[np.isfinite(v)]
    n = int(f.size)
    if n == 0:
        return {"media": None, "ic95": [None, None], "n": 0}
    m = float(f.mean())
    if n == 1:
        return {"media": m, "ic95": [None, None], "n": 1}
    ep = float(f.std(ddof=1) / math.sqrt(n))
    return {"media": m, "ic95": [m - Z95 * ep, m + Z95 * ep], "n": n, "n_excluidos": int(v.size - n)}


METRICAS_RESUMO = ("regret_brl", "lucro_esperado_brl", "lucro_realizado_micros", "drawdown_micros",
                   "frac_orcamento_perdedoras_final", "taxa_falso_vencedor", "falsos_vencedores",
                   "promovidas_negativas", "podadas_incorretas", "acertou_melhor", "hhi_medio", "turnover_medio")


def resumir(acum: dict[str, dict[str, list]]) -> dict[str, dict]:
    out = {}
    for nome, mets in acum.items():
        r = {k: ic_media(mets[k]) for k in METRICAS_RESUMO if k in mets}
        r["tempo_medio_ms"] = float(np.mean(mets["tempo_s"]) * 1000)
        if "extra_concluiu" in mets:
            r["frac_concluiu_exploracao"] = float(np.mean(mets["extra_concluiu"]))
            fins = [x for x in mets["extra_t_fim_exploracao"] if x is not None]
            r["t_fim_exploracao_medio"] = float(np.mean(fins)) if fins else None
        out[nome] = r
    return out


BASELINES_SIMPLES = ("equal", "random_sh", "greedy_parcial", "greedy_madura")


def avaliar_criterio(acum: dict[str, dict[str, list]], candidato: str,
                     baselines: tuple[str, ...] = BASELINES_SIMPLES) -> dict:
    """Critério PRÉ-REGISTRADO (ver results/swarm/PRE-REGISTRO.md):
    supera <=> IC95(regret cand) inteiro abaixo do IC95(regret do melhor baseline)
           E média(frac_orcamento_perdedoras_final cand) <= limite superior IC95 do baseline
           E média(drawdown cand) <= limite superior IC95 do baseline.
    Melhor baseline = menor regret médio entre os baselines simples presentes."""
    presentes = [b for b in baselines if b in acum]
    melhor = min(presentes, key=lambda b: float(np.mean(acum[b]["regret_brl"])))
    rc, rb = ic_media(acum[candidato]["regret_brl"]), ic_media(acum[melhor]["regret_brl"])
    fc, fb = ic_media(acum[candidato]["frac_orcamento_perdedoras_final"]), ic_media(acum[melhor]["frac_orcamento_perdedoras_final"])
    dc, db = ic_media(acum[candidato]["drawdown_micros"]), ic_media(acum[melhor]["drawdown_micros"])
    dif = np.asarray(acum[candidato]["regret_brl"]) - np.asarray(acum[melhor]["regret_brl"])
    regret_ok = rc["ic95"][1] < rb["ic95"][0]
    falsos_ok = fc["media"] <= fb["ic95"][1] + 1e-12
    dd_ok = dc["media"] <= db["ic95"][1] + 1e-9
    return {
        "candidato": candidato, "melhor_baseline": melhor,
        "regret_candidato": rc, "regret_baseline": rb,
        "dif_pareada_regret": ic_media(dif),
        "regret_ok": bool(regret_ok), "falsos_vencedores_ok": bool(falsos_ok), "drawdown_ok": bool(dd_ok),
        "supera": bool(regret_ok and falsos_ok and dd_ok),
    }
