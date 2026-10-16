"""Testes sequenciais com e-values e FDR por e-BH — complemento mínimo da CS/BH herdados.

Reuso: ``statlab.sequencias_confianca`` (CS PrPl-EB, ``validar_unitario``/``ForaDoSuporte``) e
``statlab.fdr`` (BH próprio e statsmodels). Novo aqui, em poucas linhas:

- ``eprocesso_media_limitada``: e-processo de aposta (capital) para H0: E[X] <= mu0 com X em [0, 1]:
  K_t = prod_{i<=t} (1 + lambda_i (X_i - mu0)), lambda_i previsível em [0, c/mu0]. Sob H0, K_t é
  supermartingale não negativo => P(sup_t K_t >= 1/alpha) <= alpha (Ville) e K_tau é e-value para
  qualquer tempo de parada tau (Waudby-Smith & Ramdas 2024; Shafer 2021).
- ``e_bh``: e-BH (Wang & Ramdas 2022): rejeita as k* maiores, k* = max{k : e_(k) >= m / (q k)}.
  Controla FDR <= q sob dependência ARBITRÁRIA entre e-values (em troca de poder).

Garantia só para outcome LIMITADO em [0, 1]. Receita por sessão é ilimitada: normalizar por um
"limite" estimado não é limite — ``validar_unitario`` recusa (``ForaDoSuporte``) quando ele é violado.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from scipy import stats

from volc_dil.statlab.fdr import bh_propria
from volc_dil.statlab.sequencias_confianca import ForaDoSuporte, cs_prpl_eb, validar_unitario


def eprocesso_media_limitada(x: Any, mu0: float, *, c: float = 0.5) -> np.ndarray:
    """Capital K_t ao longo do último eixo (mesma forma de ``x``). ``c`` < 1 limita a aposta a c/mu0."""
    if not 0 < mu0 < 1:
        raise ValueError("mu0 em (0, 1)")
    if not 0 < c < 1:
        raise ValueError("c em (0, 1)")
    x = validar_unitario(x)
    T = x.shape[-1]
    t = np.arange(1, T + 1, dtype=float)
    m = (0.5 + np.cumsum(x, axis=-1)) / (t + 1)
    v = (0.25 + np.cumsum((x - m) ** 2, axis=-1)) / (t + 1)
    pre = x.shape[:-1] + (1,)
    m_prev = np.concatenate([np.full(pre, 0.5), m[..., :-1]], axis=-1)
    v_prev = np.concatenate([np.full(pre, 0.25), v[..., :-1]], axis=-1)
    d = m_prev - mu0
    lam = np.clip(d / (v_prev + d * d), 0.0, c / mu0)
    return np.exp(np.cumsum(np.log1p(lam * (x - mu0)), axis=-1))


def e_bh(e: Any, q: float) -> np.ndarray:
    """e-BH. e-values ausentes (NaN) são RECUSADOS (trate antes; ausência não vira 1 nem 0)."""
    e = np.asarray(e, dtype=float)
    if not 0 < q < 1:
        raise ValueError("q em (0, 1)")
    if np.any(~np.isfinite(e)) or np.any(e < 0):
        raise ValueError("e-values devem ser finitos e >= 0")
    m = e.size
    ordem = np.argsort(-e, kind="mergesort")
    k = np.arange(1, m + 1)
    ok = e[ordem] >= m / (q * k) * (1 - 1e-12)
    kstar = int(np.nonzero(ok)[0].max()) + 1 if ok.any() else 0
    rej = np.zeros(m, dtype=bool)
    rej[ordem[:kstar]] = True
    return rej


def p_binomial_unilateral(x: Any, n: Any, mu0: float) -> np.ndarray:
    """p-valor exato de H0: p <= mu0 contra p > mu0 (P(X >= x | n, mu0)). n == 0 → NaN."""
    x = np.asarray(x, dtype=float)
    n = np.asarray(n, dtype=float)
    with np.errstate(invalid="ignore"):
        p = stats.binom.sf(x - 1, n, mu0)
    return np.where(n > 0, p, np.nan)


def bh(p: Any, q: float) -> np.ndarray:
    """BH herdado (``statlab.fdr.bh_propria``)."""
    return bh_propria(p, q)


def normalizar_por_limite(x: Any, limite: float) -> np.ndarray:
    """Divide por um limite DECLARADO e valida [0, 1]: levanta ``ForaDoSuporte`` se o limite for violado.
    Existe para mostrar que receita por sessão não tem limite: o "limite" estimado numa janela é furado."""
    if not limite > 0:
        raise ValueError("limite > 0")
    return validar_unitario(np.asarray(x, dtype=float) / limite)


__all__ = ["ForaDoSuporte", "bh", "cs_prpl_eb", "e_bh", "eprocesso_media_limitada", "normalizar_por_limite",
           "p_binomial_unilateral"]
