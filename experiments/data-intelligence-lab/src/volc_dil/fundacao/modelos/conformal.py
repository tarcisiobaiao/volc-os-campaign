"""Predição conformal: split conformal e ACI (adaptive conformal inference) para séries.

- ``quantil_conformal``: quantil de calibração com correção de amostra finita
  (posto ceil((n+1)(1-alpha)); infinito se n pequeno demais). Sob troca (exchangeability) dos
  escores, P(y em [ŷ ± q·escala]) >= 1 - alpha (Vovk; Lei et al. 2018).
- ``intervalo_conformal``: intervalo com escore de resíduo ESCALADO (|y-ŷ|/escala), útil quando as
  campanhas têm níveis muito diferentes (escala = desvio robusto recente da própria campanha).
- ``aci``: Gibbs & Candès (2021): alpha_{t+1} = alpha_t + gamma (alpha - erro_t), com o rótulo
  chegando com ``atraso`` (maturação: o lucro de d só é conhecido em d + atraso). Sem garantia de
  cobertura condicional; garante cobertura de LONGO PRAZO média ~ 1 - alpha mesmo sem troca.

Série com regime quebrado viola a troca: o split com calibração fixa sub-cobre depois da quebra.
"""
from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np


def quantil_conformal(escores: Any, alpha: float) -> float:
    s = np.asarray(escores, dtype=float)
    s = s[np.isfinite(s)]
    if not 0 < alpha < 1:
        raise ValueError("alpha em (0, 1)")
    n = s.size
    posto = math.ceil((n + 1) * (1 - alpha))
    if n == 0 or posto > n:
        return float("inf")
    return float(np.sort(s)[posto - 1])


def escores_escalados(y: Any, yhat: Any, escala: Any) -> np.ndarray:
    y, yhat, esc = (np.asarray(v, dtype=float) for v in (y, yhat, escala))
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.abs(y - yhat) / esc
    return np.where(np.isfinite(s) & (esc > 0), s, np.nan)


def intervalo_conformal(previsao: Any, escala: Any, escores_calibracao: Any, alpha: float
                        ) -> tuple[np.ndarray, np.ndarray]:
    """(lo, hi) = previsão ∓ q·escala, q = ``quantil_conformal(escores_calibracao, alpha)``."""
    q = quantil_conformal(escores_calibracao, alpha)
    p = np.asarray(previsao, dtype=float)
    e = np.asarray(escala, dtype=float)
    return p - q * e, p + q * e


def aci(previsoes: Any, observados: Any, escalas: Any, *, alpha: float, gamma: float, janela: int,
        atraso: int = 0, escores_iniciais: Optional[Any] = None) -> dict[str, np.ndarray]:
    """ACI online numa série. Em t: intervalo com quantil (1 - alpha_t) dos últimos ``janela`` escores
    já MADUROS (rótulos de t' <= t - atraso); depois, quando o rótulo de t - atraso chega, atualiza
    alpha. ``escores_iniciais`` semeiam o histórico (ex.: calibração de outras campanhas)."""
    p, y, e = (np.asarray(v, dtype=float) for v in (previsoes, observados, escalas))
    T = p.size
    if not (y.size == T == e.size):
        raise ValueError("tamanhos diferentes")
    if not 0 < gamma < 1:
        raise ValueError("gamma em (0, 1)")
    hist = [] if escores_iniciais is None else [float(v) for v in np.asarray(escores_iniciais, float) if np.isfinite(v)]
    a_t = alpha
    lo, hi, alphas, cobre = (np.full(T, np.nan) for _ in range(4))
    for t in range(T):
        # rótulo de t - atraso amadurece agora: entra no histórico e atualiza alpha
        s = t - atraso
        if s >= 0 and np.isfinite(y[s]) and not np.isnan(lo[s]):  # intervalo infinito também conta (cobre)
            err = 0.0 if lo[s] <= y[s] <= hi[s] else 1.0
            a_t = a_t + gamma * (alpha - err)
            sc = escores_escalados(y[s], p[s], e[s])
            if np.isfinite(sc):
                hist.append(float(sc))
        alphas[t] = a_t
        if not (np.isfinite(p[t]) and np.isfinite(e[t]) and e[t] > 0):
            continue
        rec = np.asarray(hist[-janela:])
        if a_t <= 0:
            q = float("inf")
        elif a_t >= 1:
            q = 0.0
        else:
            q = quantil_conformal(rec, a_t)
        lo[t], hi[t] = p[t] - q * e[t], p[t] + q * e[t]
        if np.isfinite(y[t]):
            cobre[t] = float(lo[t] <= y[t] <= hi[t])
    return {"lo": lo, "hi": hi, "alpha_t": alphas, "cobre": cobre}


def cobertura(lo: Any, hi: Any, y: Any) -> dict[str, Any]:
    lo, hi, y = (np.asarray(v, dtype=float) for v in (lo, hi, y))
    ok = np.isfinite(y) & ~np.isnan(lo) & ~np.isnan(hi)
    c = (lo[ok] <= y[ok]) & (y[ok] <= hi[ok])
    larg = (hi[ok] - lo[ok])
    return {"cobertura": float(c.mean()) if ok.any() else None, "n": int(ok.sum()),
            "largura_mediana": float(np.median(larg)) if ok.any() and np.isfinite(larg).any() else None,
            "frac_infinito": float(np.mean(~np.isfinite(larg))) if ok.any() else None}


__all__ = ["aci", "cobertura", "escores_escalados", "intervalo_conformal", "quantil_conformal"]
