"""Experimento sintético do surrogate: quando um modelo de micro-sinais supera o ingênuo?

Mundo sintético (seed) com a FORMA observada no VOLC — receita diária de campanha
pequena, zero-inflada e quantizada em 0,01 — e três tipos de feature:

- sinais de custo/navegação não circulares (força configurável);
- feature CIRCULAR: impressões da mesma fonte da receita (receita ≈ impressões × eCPM);
- feature com VAZAMENTO: receita do período seguinte.

Avaliação sempre fora do tempo (treino nos primeiros períodos, teste nos últimos):
baseline ingênuo = média de treino por unidade; RidgeCV; HistGradientBoosting só com volume.
Fronteira numérica: modelos usam float; isto é estimação, não contabilidade.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler

ALPHAS = np.logspace(-3, 3, 13)


@dataclass(frozen=True)
class Mundo:
    n_unidades: int
    n_periodos: int
    forca_sinal: float = 0.5  # 0 = sinais sem relação com a receita
    prob_zero: float = 0.25
    sd_unidade: float = 0.5
    sd_ruido: float = 0.6
    escala: float = 0.35  # receita mediana ~ US$0,35/dia
    rho: float = 0.6  # autocorrelação diária do choque de demanda (torna o futuro informativo)


def gerar(m: Mundo, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    U, T = m.n_unidades, m.n_periodos
    a = rng.normal(0, m.sd_unidade, U)
    s1 = rng.normal(0, 1, (U, T))  # ex.: engajamento pós-clique
    s2 = rng.normal(0, 1, (U, T))  # ex.: CTR/qualidade de tráfego
    s3 = rng.normal(0, 1, (U, T))  # irrelevante
    choque = np.empty((U, T))
    choque[:, 0] = rng.normal(0, 1, U)
    for t in range(1, T):
        choque[:, t] = m.rho * choque[:, t - 1] + np.sqrt(1 - m.rho**2) * rng.normal(0, 1, U)
    log_r = np.log(m.escala) + a[:, None] + m.forca_sinal * (0.8 * s1 + 0.4 * s2) + m.sd_ruido * choque
    receita = np.exp(log_r) * (rng.random((U, T)) > m.prob_zero)
    y = np.round(receita, 2)  # quantização de US$ 0,01
    ecpm = rng.lognormal(np.log(1.2), 0.15, (U, T))
    impressoes_mesma_fonte = rng.poisson(np.maximum(y, 0) / ecpm * 1000)  # circular
    vazamento = np.concatenate([y[:, 1:], np.full((U, 1), np.nan)], axis=1)  # receita de t+1
    return {"y": y, "s1": s1, "s2": s2, "s3": s3, "circ": impressoes_mesma_fonte.astype(float), "vaz": vazamento,
            "unidade": np.repeat(np.arange(U)[:, None], T, axis=1), "t": np.repeat(np.arange(T)[None, :], U, axis=0)}


def _matriz(d: dict, nomes: list[str], mascara: np.ndarray) -> np.ndarray:
    return np.column_stack([d[n][mascara] for n in nomes])


def avaliar_oot(d: dict, nomes: list[str], *, fracao_teste: float = 0.3, usar_hgb: bool = False) -> dict:
    T = d["y"].shape[1]
    n_teste = max(1, round(T * fracao_teste))
    corte = T - n_teste
    tr = d["t"] < corte
    te = d["t"] >= corte
    if "vaz" in nomes:  # a última coluna não tem futuro
        te = te & ~np.isnan(d["vaz"])
    y_tr, y_te = d["y"][tr], d["y"][te]
    u_tr, u_te = d["unidade"][tr], d["unidade"][te]
    # baseline ingênuo: média de treino por unidade (fallback: média global)
    medias = {u: y_tr[u_tr == u].mean() for u in np.unique(u_tr)}
    base = np.array([medias.get(u, y_tr.mean()) for u in u_te])
    mae_base = float(np.mean(np.abs(y_te - base)))
    out = {"n_treino": int(tr.sum()), "n_teste": int(te.sum()), "mae_base": mae_base}
    X_tr, X_te = _matriz(d, nomes, tr), _matriz(d, nomes, te)
    sc = StandardScaler().fit(X_tr)
    X_tr_s, X_te_s = sc.transform(X_tr), sc.transform(X_te)
    # one-hot da unidade dá ao modelo a mesma informação do baseline
    U = d["y"].shape[0]
    oh_tr, oh_te = np.eye(U)[u_tr], np.eye(U)[u_te]
    Xr_tr, Xr_te = np.hstack([X_tr_s, oh_tr]), np.hstack([X_te_s, oh_te])
    t0 = time.perf_counter()
    ridge = RidgeCV(alphas=ALPHAS).fit(Xr_tr, y_tr)
    pred = ridge.predict(Xr_te)
    res_tr = y_tr - ridge.predict(Xr_tr)
    lo, hi = np.quantile(res_tr, [0.1, 0.9])
    out["ridge"] = {
        "mae": float(np.mean(np.abs(y_te - pred))),
        "skill_vs_base": float(1 - np.mean(np.abs(y_te - pred)) / mae_base) if mae_base > 0 else None,
        "r2_oot": float(1 - np.sum((y_te - pred) ** 2) / np.sum((y_te - y_te.mean()) ** 2)) if np.var(y_te) > 0 else None,
        "cobertura_80": float(np.mean((y_te >= pred + lo) & (y_te <= pred + hi))),
        "alpha": float(ridge.alpha_),
        "segundos": time.perf_counter() - t0,
    }
    if usar_hgb:
        t0 = time.perf_counter()
        hgb = HistGradientBoostingRegressor(max_iter=150, learning_rate=0.05, random_state=0).fit(
            np.hstack([X_tr, u_tr[:, None]]), y_tr)
        ph = hgb.predict(np.hstack([X_te, u_te[:, None]]))
        out["hgb"] = {"mae": float(np.mean(np.abs(y_te - ph))),
                      "skill_vs_base": float(1 - np.mean(np.abs(y_te - ph)) / mae_base) if mae_base > 0 else None,
                      "segundos": time.perf_counter() - t0}
    return out


def ic_media(x: np.ndarray, z: float = 1.96) -> tuple[float, float, float]:
    x = np.asarray([v for v in x if v is not None and np.isfinite(v)], dtype=float)
    if len(x) == 0:
        return (float("nan"),) * 3
    m = float(x.mean())
    h = float(z * x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else float("nan")
    return m, m - h, m + h


def grade(mundos: list[Mundo], nomes: list[str], seeds: range, *, hgb_min_treino: Optional[int] = 500) -> list[dict]:
    linhas = []
    for m in mundos:
        skills, hskills, cobs, r2s = [], [], [], []
        for s in seeds:
            d = gerar(m, s)
            usar = hgb_min_treino is not None and m.n_unidades * m.n_periodos * 0.7 >= hgb_min_treino and s < seeds.start + 50
            r = avaliar_oot(d, nomes, usar_hgb=usar)
            skills.append(r["ridge"]["skill_vs_base"])
            cobs.append(r["ridge"]["cobertura_80"])
            r2s.append(r["ridge"]["r2_oot"])
            if "hgb" in r:
                hskills.append(r["hgb"]["skill_vs_base"])
        sk = np.array([x for x in skills if x is not None])
        linhas.append({
            "unidades": m.n_unidades, "periodos": m.n_periodos, "linhas": m.n_unidades * m.n_periodos,
            "forca_sinal": m.forca_sinal, "features": nomes, "seeds": len(seeds),
            "ridge_skill_media_ic95": ic_media(sk),
            "ridge_p_skill_pos": float(np.mean(sk > 0)) if len(sk) else None,
            "ridge_r2_oot_media_ic95": ic_media(np.array([x for x in r2s if x is not None])),
            "ridge_cobertura80_media_ic95": ic_media(np.array(cobs)),
            "hgb_skill_media_ic95": ic_media(np.array(hskills)) if hskills else None,
            "hgb_seeds": len(hskills),
        })
    return linhas
