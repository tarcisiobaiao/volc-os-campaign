"""Alocação de orçamento sob resposta côncava ESTIMADA com incerteza (sem CVXPY: scipy/numpy).

Modelo por campanha: receita ≈ a · gasto^b, 0 < b < 1 (retorno decrescente), ajustado em log-log nos
dias com gasto e receita conhecidos e > 0. Identificabilidade: sem variação de gasto (desvio de
log gasto < ``min_desvio_log``) a inclinação b não é identificável — o ajuste cai no prior de b e marca
``identificavel=False`` (a curva vira uma extrapolação do prior, não uma medida).

Objetivo: max Σ_i (a_i · exp(-aversao · se_i) · x_i^{b_i} − x_i) sujeito a Σ x_i <= total e
lo_i <= x_i <= hi_i, com lo/hi vindos de mínimo, máximo e passo máximo de mudança relativo ao atual.
Problema côncavo separável: solução exata por KKT (x_i(λ) = clip((a_i b_i/(1+λ))^{1/(1-b_i)}, lo_i, hi_i),
λ por bisseção). ``aversao`` > 0 usa o limite inferior de a (redução por incerteza).

Baselines (mesmas restrições, por projeção): ``alocar_igual``, ``alocar_guloso`` (enche por ROAS
estimado), ``alocar_proporcional`` (pesos = contribuição média recente, piso — regra do
``replay.politicas.Proporcional`` herdado, via ``alocar_com_piso``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from volc_dil.replay.politicas import alocar_com_piso


@dataclass(frozen=True)
class CurvaResposta:
    a: float
    b: float
    se_log_a: float
    identificavel: bool
    n: int
    desvio_log_gasto: float

    def receita(self, x: Any) -> np.ndarray:
        return self.a * np.power(np.asarray(x, dtype=float), self.b)


def ajustar_resposta(gasto: Any, receita: Any, *, b_prior: float, sd_prior_b: float, min_desvio_log: float,
                     extrapolacao_log: float = float(np.log(1.5)), b_min: float = 0.05, b_max: float = 0.95,
                     min_n: int = 4) -> CurvaResposta:
    """Ajuste log-log com prior normal em b (conjugado com variância residual estimada).

    ``se_log_a`` = incerteza do log da receita prevista a ``extrapolacao_log`` do gasto médio observado:
    sqrt(s²/n + var(b)·extrapolacao²), com var(b) posterior (identificável) ou do prior (não identificável).
    Dias com gasto/receita ausentes (NaN) ou <= 0 ficam fora (contados em ``n``)."""
    g = np.asarray(gasto, dtype=float)
    r = np.asarray(receita, dtype=float)
    ok = np.isfinite(g) & np.isfinite(r) & (g > 0) & (r > 0)
    n = int(ok.sum())
    if n < 2:
        return CurvaResposta(float("nan"), b_prior, float("inf"), False, n, 0.0)
    lx, ly = np.log(g[ok]), np.log(r[ok])
    dlx = float(lx.std(ddof=1))
    ident = n >= min_n and dlx >= min_desvio_log
    xc = lx - lx.mean()
    if ident:
        b_ols = float((xc * (ly - ly.mean())).sum() / (xc * xc).sum())
        res = ly - ly.mean() - b_ols * xc
        s2 = float((res ** 2).sum() / max(n - 2, 1))
        var_b_dados = max(s2, 1e-12) / float((xc * xc).sum())
        prec = 1.0 / var_b_dados + 1.0 / sd_prior_b ** 2
        b = (b_ols / var_b_dados + b_prior / sd_prior_b ** 2) / prec
        var_b = 1.0 / prec
    else:
        b, var_b = b_prior, sd_prior_b ** 2
    b = float(np.clip(b, b_min, b_max))
    alfa = float((ly - b * xc).mean())          # log receita no gasto médio observado
    s2a = float(((ly - b * xc - alfa) ** 2).sum() / max(n - 1, 1))
    log_a = alfa - b * float(lx.mean())
    se = float(np.sqrt(s2a / n + var_b * extrapolacao_log ** 2))
    return CurvaResposta(float(np.exp(log_a)), b, se, bool(ident), n, dlx)


def limites(atual: Any, *, minimo: Any, maximo: Any, passo_max: Optional[float]) -> tuple[np.ndarray, np.ndarray]:
    """lo/hi por campanha a partir de mínimo/máximo absolutos e passo relativo máximo ao orçamento atual."""
    at = np.asarray(atual, dtype=float)
    lo = np.broadcast_to(np.asarray(minimo, dtype=float), at.shape).copy()
    hi = np.broadcast_to(np.asarray(maximo, dtype=float), at.shape).copy()
    if passo_max is not None:
        lo = np.maximum(lo, at * (1 - passo_max))
        hi = np.minimum(hi, at * (1 + passo_max))
    if np.any(lo > hi + 1e-9):
        raise ValueError("restrições inviáveis (lo > hi) em alguma campanha")
    return lo, hi


def verificar_restricoes(x: Any, lo: Any, hi: Any, total: float, *, tol: float = 1e-6) -> list[str]:
    x, lo, hi = (np.asarray(v, dtype=float) for v in (x, lo, hi))
    v = []
    if np.any(~np.isfinite(x)):
        v.append("alocacao_nao_finita")
    if np.any(x < lo - tol * np.maximum(1, lo)):
        v.append("abaixo_do_minimo_ou_passo")
    if np.any(x > hi + tol * np.maximum(1, hi)):
        v.append("acima_do_maximo_ou_passo")
    if x.sum() > total * (1 + tol) + tol:
        v.append("total_excedido")
    return v


def _x_de_lambda(lam: float, a: np.ndarray, b: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        x = np.power(a * b / (1.0 + lam), 1.0 / (1.0 - b))
    x = np.where(np.isfinite(x), x, hi)
    return np.clip(x, lo, hi)


def alocar_orcamento(curvas: list[CurvaResposta], *, total: float, lo: Any, hi: Any, aversao: float = 0.0,
                     tol: float = 1e-9) -> np.ndarray:
    """Solução exata do problema côncavo separável (ver docstring do módulo)."""
    lo, hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    if lo.sum() > total * (1 + 1e-12):
        raise ValueError("Σ mínimos > total: inviável")
    a = np.array([c.a * np.exp(-aversao * c.se_log_a) if np.isfinite(c.a) else 0.0 for c in curvas])
    b = np.array([c.b for c in curvas])
    x0 = _x_de_lambda(0.0, a, b, lo, hi)
    if x0.sum() <= total:
        return x0
    lam_lo, lam_hi = 0.0, 1.0
    while _x_de_lambda(lam_hi, a, b, lo, hi).sum() > total:
        lam_hi *= 2.0
        if lam_hi > 1e15:
            break
    for _ in range(200):
        mid = 0.5 * (lam_lo + lam_hi)
        if _x_de_lambda(mid, a, b, lo, hi).sum() > total:
            lam_lo = mid
        else:
            lam_hi = mid
        if lam_hi - lam_lo <= tol * max(1.0, lam_hi):
            break
    return _x_de_lambda(lam_hi, a, b, lo, hi)


def lucro_esperado(curvas: list[CurvaResposta], x: Any) -> float:
    x = np.asarray(x, dtype=float)
    return float(sum((c.receita(xi) - xi) if np.isfinite(c.a) else -xi for c, xi in zip(curvas, x)))


def projetar(x: Any, lo: Any, hi: Any, total: float, *, gastar_tudo: bool = True) -> np.ndarray:
    """Projeta uma alocação nas restrições: recorta em [lo, hi]; se passar do total, reduz o excedente
    sobre lo proporcionalmente; se ``gastar_tudo`` e sobrar, distribui proporcional à folga (hi − x)."""
    x, lo, hi = (np.asarray(v, dtype=float).copy() for v in (x, lo, hi))
    x = np.clip(x, lo, hi)
    s = x.sum()
    if s > total:
        exc = x - lo
        x = lo + exc * (total - lo.sum()) / exc.sum() if exc.sum() > 0 else lo
    elif gastar_tudo and s < total:
        folga = hi - x
        if folga.sum() > 0:
            x = x + folga * min(1.0, (total - s) / folga.sum())
    return np.clip(x, lo, hi)


def alocar_igual(n: int, *, total: float, lo: Any, hi: Any) -> np.ndarray:
    return projetar(np.full(n, total / n), lo, hi, total)


def alocar_guloso(roas_estimado: Any, *, total: float, lo: Any, hi: Any) -> np.ndarray:
    """Começa no mínimo e enche até o máximo na ordem do ROAS estimado (NaN = último); só gasta onde
    o ROAS estimado > 1 (abaixo disso o guloso não acrescenta)."""
    r = np.asarray(roas_estimado, dtype=float)
    lo, hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    x = lo.copy()
    resto = total - x.sum()
    for i in np.argsort(-np.nan_to_num(r, nan=-np.inf), kind="mergesort"):
        if resto <= 0 or not (np.isfinite(r[i]) and r[i] > 1.0):
            break
        add = min(hi[i] - x[i], resto)
        x[i] += add
        resto -= add
    return x


def alocar_proporcional(contribuicao_media: Any, *, total: float, lo: Any, hi: Any, piso: float) -> np.ndarray:
    """Regra herdada (``replay.politicas.Proporcional``): pesos = max(contribuição média, 0) com piso,
    repartição exata por ``alocar_com_piso`` em centavos; depois projeção nas restrições.
    Contribuição ausente (NaN) → mantém o mínimo (não vira 0 de peso silencioso: fica fora)."""
    c = np.asarray(contribuicao_media, dtype=float)
    dentro = [i for i in range(c.size) if np.isfinite(c[i])]
    cent = lambda v: int(round(v * 100))  # noqa: E731
    pesos = [max(cent(c[i]), 0) for i in dentro]
    lo = np.asarray(lo, dtype=float)
    x = lo.copy()
    disponivel = total - sum(lo[i] for i in range(c.size) if i not in dentro)
    rep = alocar_com_piso(cent(disponivel), cent(piso), dentro, pesos)
    for i, v in rep.items():
        x[i] = v / 100.0
    return projetar(x, lo, hi, total)


def para_micros(x_brl: Any) -> np.ndarray:
    """BRL float → micros inteiros arredondados ao centavo (como o simulador espera)."""
    return (np.round(np.asarray(x_brl, dtype=float) * 100).astype(np.int64)) * 10_000


__all__ = ["CurvaResposta", "ajustar_resposta", "alocar_guloso", "alocar_igual", "alocar_orcamento",
           "alocar_proporcional", "limites", "lucro_esperado", "para_micros", "projetar", "verificar_restricoes"]
