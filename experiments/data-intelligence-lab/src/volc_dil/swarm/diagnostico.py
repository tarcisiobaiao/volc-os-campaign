"""Diagnóstico das premissas do ASHA/SH no mapeamento "célula = trial, gasto = fidelidade".

ASHA assume (i) avaliação intermediária informativa sobre o valor final (rank em baixa
fidelidade correlaciona com rank em alta fidelidade) e (ii) trials independentes e
estacionários. Aqui medimos, com alocação equal (sem seleção), quanto o ROI observado num
degrau baixo ordena as células como (a) v verdadeiro e (b) o valor por R$ na escala de
produção (B/n_final), com receita parcial e madura.
"""
from __future__ import annotations

import numpy as np
from scipy import stats

from volc_dil.swarm.cenario import MICROS, ParametrosCenario, gerar_cenario
from volc_dil.swarm.politicas import EqualBudget
from volc_dil.swarm.simulador import receita_reportada, simular


def valor_por_real_em_escala(cen, gasto_brl: float, regime: int = 0) -> np.ndarray:
    p = cen.params
    v = cen.v[regime]
    dentro = np.minimum(gasto_brl, cen.cap_brl)
    fora = np.maximum(gasto_brl - cen.cap_brl, 0.0)
    return v * (dentro + p.beta_saturacao * fora) / gasto_brl - 1.0


def _spearman(a, b) -> float:
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3 or np.ptp(a[ok]) == 0 or np.ptp(b[ok]) == 0:
        return float("nan")
    return float(stats.spearmanr(a[ok], b[ok]).statistic)


def diagnosticar_seed(params: ParametrosCenario, seed: int, ciclos_rung: tuple[int, ...] = (2, 6),
                      n_final: int = 4) -> dict:
    cen = gerar_cenario(params, seed)
    res = simular(cen, EqualBudget(), np.random.default_rng(0))
    D = params.atraso_ciclos
    escala = valor_por_real_em_escala(cen, params.orcamento_ciclo_micros / MICROS / n_final)
    v_margem = cen.v[0] - 1.0
    out = {}
    for n in ciclos_rung:
        g = res.alocacao[:n].sum(0)
        rep_parcial = receita_reportada(cen, res.receita_final, n)[:n].sum(0)
        t_mad = min(params.T, n + D)
        rep_madura = receita_reportada(cen, res.receita_final, t_mad)[:n].sum(0)
        roi_p = (rep_parcial - g) / g
        roi_m = (rep_madura - g) / g
        lento = cen.phi0 < params.fracao_inicial if params.modo_maturacao != "uniforme" else np.zeros(cen.K, bool)
        with np.errstate(invalid="ignore", divide="ignore"):
            razao = rep_parcial.astype(float) / np.where(rep_madura > 0, rep_madura, np.nan)
        out[f"rung_{n}ciclos"] = {
            "spearman_parcial_v": _spearman(roi_p, v_margem),
            "spearman_madura_v": _spearman(roi_m, v_margem),
            "spearman_parcial_escala": _spearman(roi_p, escala),
            "spearman_madura_escala": _spearman(roi_m, escala),
            "razao_parcial_madura_rapidas": float(np.nanmean(razao[~lento])) if (~lento).any() else float("nan"),
            "razao_parcial_madura_lentas": float(np.nanmean(razao[lento])) if lento.any() else float("nan"),
        }
    out["spearman_v_escala"] = _spearman(v_margem, escala)
    return out
