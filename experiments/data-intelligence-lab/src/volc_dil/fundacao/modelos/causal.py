"""Diagnóstico causal mínimo para mudanças observadas (ex.: orçamento dobrado em parte das campanhas).

- ``did_painel``: diferenças em diferenças 2×2 sobre painel balanceado unidade × período, IC por
  bootstrap de unidades (cluster), separado por grupo;
- ``tendencias_paralelas``: inclinação do gap tratado − controle no pré-período (IC por bootstrap);
- ``placebo_temporal``: DiD com data falsa dentro do pré-período (deve ser ~0);
- ``placebo_unidades``: permutação do rótulo de tratamento (p-valor de aleatorização);
- ``controle_sintetico``: Abadie-Diamond-Hainmueller mínimo (pesos >= 0 somando 1, SLSQP do scipy),
  opcionalmente com intercepto (unidades centradas na média pré — Ferman & Pinto), e placebo em espaço.

Nada disso prova causalidade em dado observacional: os diagnósticos só REJEITAM premissas
(tendência não paralela, placebo diferente de zero, ajuste pré ruim). Seleção pelo resultado
(dobrar onde o ROAS recente foi alto) viola a premissa sem que o pré-período necessariamente acuse.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
from scipy import optimize


def _validar(Y: Any, tratado: Any, t0: int) -> tuple[np.ndarray, np.ndarray]:
    Y = np.asarray(Y, dtype=float)
    tr = np.asarray(tratado, dtype=bool)
    if Y.ndim != 2 or tr.shape != (Y.shape[0],):
        raise ValueError("Y (N, T) e tratado (N,)")
    if not np.all(np.isfinite(Y)):
        raise ValueError("painel com ausência: DiD exige painel balanceado (não preencha com 0)")
    if not 1 <= t0 < Y.shape[1]:
        raise ValueError("t0 precisa deixar pré e pós não vazios")
    if tr.sum() < 1 or (~tr).sum() < 1:
        raise ValueError("precisa de tratados e controles")
    return Y, tr


def _did(Y: np.ndarray, tr: np.ndarray, t0: int) -> float:
    pre, pos = Y[:, :t0].mean(axis=1), Y[:, t0:].mean(axis=1)
    d = pos - pre
    return float(d[tr].mean() - d[~tr].mean())


def _boot_unidades(stat, Y: np.ndarray, tr: np.ndarray, n_boot: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    it, ic = np.nonzero(tr)[0], np.nonzero(~tr)[0]
    out = np.empty(n_boot)
    for b in range(n_boot):
        sel = np.r_[rng.choice(it, it.size), rng.choice(ic, ic.size)]
        out[b] = stat(Y[sel], np.r_[np.ones(it.size, bool), np.zeros(ic.size, bool)])
    return out


def did_painel(Y: Any, tratado: Any, t0: int, *, n_boot: int = 1000, seed: int = 0) -> dict[str, Any]:
    Y, tr = _validar(Y, tratado, t0)
    est = _did(Y, tr, t0)
    b = _boot_unidades(lambda y, t: _did(y, t, t0), Y, tr, n_boot, seed)
    return {"efeito": est, "ic95": [float(np.quantile(b, 0.025)), float(np.quantile(b, 0.975))],
            "n_tratados": int(tr.sum()), "n_controles": int((~tr).sum()), "t0": t0, "metodo": "did_2x2"}


def _inclinacao_gap(Y: np.ndarray, tr: np.ndarray, t0: int) -> float:
    gap = Y[tr, :t0].mean(axis=0) - Y[~tr, :t0].mean(axis=0)
    t = np.arange(t0, dtype=float)
    return float(np.polyfit(t, gap, 1)[0]) if t0 >= 2 else float("nan")


def tendencias_paralelas(Y: Any, tratado: Any, t0: int, *, n_boot: int = 1000, seed: int = 0) -> dict[str, Any]:
    """Teste (fraco) de tendências paralelas: IC95 da inclinação do gap no pré contém 0 → ``passou``.
    Passar não prova paralelismo no pós; reprovar é motivo para não confiar no DiD."""
    Y, tr = _validar(Y, tratado, t0)
    if t0 < 3:
        return {"inclinacao": None, "ic95": [None, None], "passou": None, "motivo": "pre_periodo_curto"}
    est = _inclinacao_gap(Y, tr, t0)
    b = _boot_unidades(lambda y, t: _inclinacao_gap(y, t, t0), Y, tr, n_boot, seed)
    lo, hi = float(np.quantile(b, 0.025)), float(np.quantile(b, 0.975))
    return {"inclinacao": est, "ic95": [lo, hi], "passou": bool(lo <= 0 <= hi)}


def placebo_temporal(Y: Any, tratado: Any, t0: int, t0_falso: int, *, n_boot: int = 1000, seed: int = 0
                     ) -> dict[str, Any]:
    """DiD só no pré-período com uma data falsa ``t0_falso < t0``; IC95 contendo 0 → ``passou``."""
    Y, tr = _validar(Y, tratado, t0)
    if not 1 <= t0_falso < t0:
        raise ValueError("t0_falso dentro do pré-período")
    r = did_painel(Y[:, :t0], tr, t0_falso, n_boot=n_boot, seed=seed)
    r["passou"] = bool(r["ic95"][0] <= 0 <= r["ic95"][1])
    r["metodo"] = "placebo_temporal"
    return r


def placebo_unidades(Y: Any, tratado: Any, t0: int, *, n_perm: int = 1000, seed: int = 0) -> dict[str, Any]:
    """p-valor de aleatorização: fração de permutações do rótulo com |DiD| >= |DiD real|."""
    Y, tr = _validar(Y, tratado, t0)
    real = _did(Y, tr, t0)
    rng = np.random.default_rng(seed)
    ext = 0
    for _ in range(n_perm):
        ext += abs(_did(Y, rng.permutation(tr), t0)) >= abs(real) - 1e-12
    return {"efeito": real, "p_valor": (ext + 1) / (n_perm + 1), "n_perm": n_perm}


def controle_sintetico(Y: Any, i_tratado: int, controles: Any, t0: int, *, com_intercepto: bool = True
                       ) -> dict[str, Any]:
    """Pesos w >= 0, sum w = 1 que minimizam o erro quadrático pré entre o tratado e a combinação dos
    controles. ``com_intercepto``: centra cada unidade na própria média pré (ajusta forma, não nível)."""
    Y = np.asarray(Y, dtype=float)
    ctl = np.asarray(controles, dtype=int)
    if not np.all(np.isfinite(Y[np.r_[i_tratado, ctl]])):
        raise ValueError("painel com ausência")
    if ctl.size < 2 or i_tratado in set(ctl.tolist()):
        raise ValueError("controles: >= 2 e sem o tratado")
    y = Y[i_tratado].copy()
    X = Y[ctl].copy()
    if com_intercepto:
        y = y - y[:t0].mean()
        X = X - X[:, :t0].mean(axis=1, keepdims=True)
    yp, Xp = y[:t0], X[:, :t0]
    k = ctl.size

    def perda(w: np.ndarray) -> float:
        r = yp - w @ Xp
        return float(r @ r)

    def grad(w: np.ndarray) -> np.ndarray:
        return -2.0 * Xp @ (yp - w @ Xp)

    res = optimize.minimize(perda, np.full(k, 1.0 / k), jac=grad, method="SLSQP", bounds=[(0.0, 1.0)] * k,
                            constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1.0, "jac": lambda w: np.ones(k)}],
                            options={"maxiter": 500, "ftol": 1e-12})
    w = np.clip(res.x, 0.0, None)
    w = w / w.sum()
    gap = y - w @ X
    pre, pos = gap[:t0], gap[t0:]
    return {"pesos": w, "gap": gap, "efeito": float(pos.mean()), "rmspe_pre": float(np.sqrt((pre ** 2).mean())),
            "rmspe_pos": float(np.sqrt((pos ** 2).mean())), "convergiu": bool(res.success),
            "com_intercepto": com_intercepto}


def controle_sintetico_placebo(Y: Any, i_tratado: int, controles: Any, t0: int, *, com_intercepto: bool = True,
                               max_placebos: Optional[int] = None) -> dict[str, Any]:
    """Placebo em espaço: cada controle vira 'tratado' contra os demais; p = posto da razão RMSPE pós/pré."""
    ctl = list(np.asarray(controles, dtype=int))
    real = controle_sintetico(Y, i_tratado, ctl, t0, com_intercepto=com_intercepto)
    razao_real = real["rmspe_pos"] / max(real["rmspe_pre"], 1e-12)
    razoes = []
    for j in ctl[:max_placebos] if max_placebos else ctl:
        outros = [c for c in ctl if c != j]
        r = controle_sintetico(Y, j, outros, t0, com_intercepto=com_intercepto)
        razoes.append(r["rmspe_pos"] / max(r["rmspe_pre"], 1e-12))
    razoes = np.asarray(razoes)
    return {"efeito": real["efeito"], "razao": razao_real,
            "p_valor": float((1 + (razoes >= razao_real).sum()) / (1 + razoes.size)), "n_placebos": int(razoes.size)}


__all__ = ["controle_sintetico", "controle_sintetico_placebo", "did_painel", "placebo_temporal", "placebo_unidades",
           "tendencias_paralelas"]
