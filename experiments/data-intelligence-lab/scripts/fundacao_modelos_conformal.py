"""M8 — predição conformal do lucro diário maduro por campanha: split (calibração fixa) × ACI.

Previsão ingênua as_of: média dos 7 últimos dias MADUROS (rótulo de d conhecido em d + 3); escala =
desvio robusto desses 7 dias (piso declarado). Split: escores dos dias 10–24, testados nos dias 28+.
ACI: sequência achatada (dia, campanha) com atraso de 3 dias × C posições (rótulo maduro), alpha
compartilhado entre campanhas. Pré-registro: PRE-REGISTRO.md (M8). Saída: results/fundacao/modelos/m8_conformal.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fundacao_modelos_comum import manifesto, saida  # noqa: E402

import numpy as np  # noqa: E402

from volc_dil.fundacao import modelos as M  # noqa: E402
from volc_dil.fundacao.simulador import simular  # noqa: E402

ALPHA = 0.1
ATRASO = 3
JAN = 7
CAL = (10, 25)
TESTE0 = 28
PISO_ESCALA = 1.0  # BRL (parâmetro)


def lucro_final(sim):
    kw = dict(entidades=M.ids_campanhas(sim.mundo), dias=M.dias_iso(sim.mundo))
    r = M.TabelaVersoes.de_registros(sim.leituras.registros, fonte="joinads", metrica="revenue", **kw).final()
    c = M.TabelaVersoes.de_registros(sim.leituras.registros, fonte="google_ads", metrica="cost", **kw).final()
    return (r - c) / 1e6


def previsoes(y):
    E, D = y.shape
    p, e = np.full((E, D), np.nan), np.full((E, D), np.nan)
    for d in range(ATRASO + JAN, D):
        h = y[:, d - ATRASO - JAN + 1:d - ATRASO + 1]
        with np.errstate(invalid="ignore"):
            med = np.nanmedian(h, axis=1)
            mad = np.nanmedian(np.abs(h - med[:, None]), axis=1) * 1.4826
        p[:, d] = np.nanmean(h, axis=1)
        e[:, d] = np.maximum(mad, PISO_ESCALA)
    return p, e


def um_mundo(cen, seed, C, D, gamma):
    sim = simular(cen, seed, n_campanhas=C, n_dias=D)
    y = lucro_final(sim)
    p, e = previsoes(y)
    quebrou = sim.mundo.flags["fator_rpm"][:, -1] < 1.0
    dia_q = int(np.floor(0.5 * D + 1e-9))
    cal = M.escores_escalados(y[:, CAL[0]:CAL[1]], p[:, CAL[0]:CAL[1]], e[:, CAL[0]:CAL[1]]).ravel()
    lo, hi = M.intervalo_conformal(p, e, cal, ALPHA)
    # ACI achatado por (dia, campanha)
    pf, yf, ef = p.T.ravel(), y.T.ravel(), e.T.ravel()
    r = M.aci(pf, yf, ef, alpha=ALPHA, gamma=gamma, janela=15 * C, atraso=ATRASO * C, escores_iniciais=cal)
    lo_a, hi_a = r["lo"].reshape(D, C).T, r["hi"].reshape(D, C).T
    dias_t = np.arange(D) >= TESTE0
    pos = np.arange(D) >= dia_q + 1
    out = {}
    for nome, (L, H) in {"split": (lo, hi), "aci": (lo_a, hi_a)}.items():
        def cob(mask):
            ok = mask & np.isfinite(y) & ~np.isnan(L)
            return float(np.mean((L[ok] <= y[ok]) & (y[ok] <= H[ok]))) if ok.any() else np.nan
        m_all = np.broadcast_to(dias_t, y.shape)
        m_qpos = np.outer(quebrou, dias_t & pos)
        m_nq = np.outer(~quebrou, dias_t)
        larg = (H - L)[m_all & np.isfinite(y)]
        out[nome] = {"cobertura_teste": cob(m_all), "cobertura_quebradas_pos": cob(m_qpos),
                     "cobertura_nao_quebradas": cob(m_nq),
                     "largura_mediana": float(np.nanmedian(larg[np.isfinite(larg)])) if np.isfinite(larg).any() else np.nan,
                     "frac_intervalo_infinito": float(np.mean(~np.isfinite(larg))) if larg.size else np.nan}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true")
    a = ap.parse_args()
    seeds = list(range(20261901, 20261901 + (3 if a.rapido else 12)))
    C, D = (20, 50) if a.rapido else (50, 60)
    gamma = 0.005
    res = {}
    for cen in ("estavel", "quebra_regime_rpm"):
        ws = [um_mundo(cen, s, C, D, gamma) for s in seeds]
        res[cen] = {m: {k: M.ic_bootstrap_media([w[m][k] for w in ws]) for k in ws[0][m]} for m in ("split", "aci")}
    est = res["estavel"]["split"]["cobertura_teste"]
    q = res["quebra_regime_rpm"]
    res["H8a_suportada"] = bool(est["estimativa"] >= 1 - ALPHA - 0.02)
    res["H8b_suportada"] = bool(q["split"]["cobertura_quebradas_pos"]["estimativa"] < 1 - ALPHA - 0.05
                                and abs(q["aci"]["cobertura_teste"]["estimativa"] - (1 - ALPHA)) <= 0.03)
    obj = {"manifesto": manifesto(__file__, seeds=seeds, parametros={"C": C, "D": D, "alpha": ALPHA, "gamma": gamma,
                                                                     "atraso": ATRASO, "janela_previsao": JAN,
                                                                     "calibracao_dias": CAL, "teste_desde": TESTE0,
                                                                     "piso_escala_brl": PISO_ESCALA}),
           "resultados": res}
    saida("m8_conformal.json", obj, rapido=a.rapido)


if __name__ == "__main__":
    main()
