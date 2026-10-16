"""Confidence sequences (anytime-valid) para média de outcome LIMITADO em [0, 1].

Forma implementada: CS "PrPl-EB" (predictable plug-in empirical Bernstein) de
Waudby-Smith, I. & Ramdas, A. (2024). *Estimating means of bounded random variables by
betting*. JRSS-B 86(1):1-27, seção 3 (versão empirical-Bernstein com lambda previsível).
Para X_i em [0, 1] com média condicional mu, alpha em (0, 1):

    mu_hat_t   = (1/2 + sum_{i<=t} X_i) / (t + 1)
    sig2_hat_t = (1/4 + sum_{i<=t} (X_i - mu_hat_i)^2) / (t + 1)
    lambda_t   = min( sqrt( 2 log(2/alpha) / (sig2_hat_{t-1} * t * log(1 + t)) ), c )
    v_t        = 4 (X_t - mu_hat_{t-1})^2
    psi_E(l)   = (-log(1 - l) - l) / 4
    C_t        = sum(l_i X_i)/sum(l_i)  +-  (log(2/alpha) + sum v_i psi_E(l_i)) / sum(l_i)

seguido de interseção acumulada (running intersection) e recorte em [0, 1]. Garante
P(existe t: mu fora de C_t) <= alpha sob X_i em [0, 1] (i.i.d. ou martingale com média
condicional constante). ``c`` = 1/2 como sugerido no artigo (constante do método, não
parâmetro de negócio).

Comparação: Wald/t fixo x_bar +- z s/sqrt(t) recalculado a cada passo (peeking).
A garantia NÃO vale para outcome ilimitado (receita) — ver contraprovas no script.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
from scipy import stats


class ForaDoSuporte(ValueError):
    """Entrada fora de [0, 1] (ou ausente) para uma CS que só é válida em [0, 1]."""


def validar_unitario(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        raise ForaDoSuporte("sequência vazia")
    if np.any(~np.isfinite(x)):
        raise ForaDoSuporte("observação ausente/não finita: ausência não vira 0 nem é descartada em silêncio")
    if np.any(x < 0.0) or np.any(x > 1.0):
        raise ForaDoSuporte(
            f"CS PrPl-EB exige X em [0, 1]; recebido min={float(x.min()):.6g} max={float(x.max()):.6g}. "
            "Normalizar por um limite que não é limite real (ex.: receita) invalida a garantia."
        )
    return x


def cs_prpl_eb(x: Any, alpha: float, c: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
    """CS PrPl-EB ao longo do último eixo. Retorna (lo, hi) com a mesma forma de ``x``."""
    if not 0 < alpha < 1:
        raise ValueError("alpha em (0, 1)")
    x = validar_unitario(x)
    T = x.shape[-1]
    t = np.arange(1, T + 1, dtype=float)
    mu_hat = (0.5 + np.cumsum(x, axis=-1)) / (t + 1)
    sig2 = (0.25 + np.cumsum((x - mu_hat) ** 2, axis=-1)) / (t + 1)
    forma_pre = x.shape[:-1] + (1,)
    mu_prev = np.concatenate([np.full(forma_pre, 0.5), mu_hat[..., :-1]], axis=-1)
    sig2_prev = np.concatenate([np.full(forma_pre, 0.25), sig2[..., :-1]], axis=-1)
    log2a = np.log(2.0 / alpha)
    lam = np.minimum(np.sqrt(2 * log2a / (sig2_prev * t * np.log1p(t))), c)
    v = 4 * (x - mu_prev) ** 2
    psi = (-np.log1p(-lam) - lam) / 4
    sl = np.cumsum(lam, axis=-1)
    centro = np.cumsum(lam * x, axis=-1) / sl
    margem = (log2a + np.cumsum(v * psi, axis=-1)) / sl
    lo = np.maximum.accumulate(np.clip(centro - margem, 0.0, 1.0), axis=-1)
    hi = np.minimum.accumulate(np.clip(centro + margem, 0.0, 1.0), axis=-1)
    return lo, hi


def wald_peeking(x: Any, alpha: float) -> tuple[np.ndarray, np.ndarray]:
    """IC de Wald/t de horizonte fixo recalculado a cada t (sem correção). NaN para t < 2."""
    x = np.asarray(x, dtype=float)
    T = x.shape[-1]
    t = np.arange(1, T + 1, dtype=float)
    s1 = np.cumsum(x, axis=-1)
    s2 = np.cumsum(x * x, axis=-1)
    media = s1 / t
    with np.errstate(divide="ignore", invalid="ignore"):
        var = np.maximum(s2 - t * media**2, 0.0) / (t - 1)
        tq = stats.t.ppf(1 - alpha / 2, np.maximum(t - 1, 1))
        meia = tq * np.sqrt(var / t)
    meia[..., 0] = np.nan
    return media - meia, media + meia


def resumir(lo: np.ndarray, hi: np.ndarray, mu: Any, mu0: Any, t_min: int,
            pontos: tuple[int, ...]) -> dict[str, np.ndarray]:
    """Por trajetória: violou em ALGUM t >= t_min; t da 1ª violação; t em que lo > mu0
    (decisão 'mu > mu0'); larguras em ``pontos``; e o uso CORRETO de horizonte fixo (uma olhada
    em T: cobre? decide?). Índices t são 1-based. NaN = nunca. ``mu``/``mu0`` podem ser escalares
    ou um valor por trajetória."""
    T = lo.shape[-1]
    mu = np.asarray(mu, dtype=float).reshape(-1, 1) if np.ndim(mu) else float(mu)
    if mu0 is not None:
        mu0 = np.asarray(mu0, dtype=float).reshape(-1, 1) if np.ndim(mu0) else float(mu0)
    sl = slice(t_min - 1, T)
    fora = (lo[:, sl] > mu) | (hi[:, sl] < mu)
    fora = np.where(np.isnan(lo[:, sl]), False, fora)
    violou = fora.any(axis=1)
    t1 = np.where(violou, np.argmax(fora, axis=1) + t_min, np.nan)
    # erro uniforme contado só a partir de t >= 100 e t >= 1000: separa a degeneração de
    # amostra minúscula (ex.: 0 conversões em 10 cliques -> IC [0, 0]) da inflação por peeking
    extras = {}
    for tm in (100, 1000):
        if tm > t_min and tm <= T:
            idx = tm - t_min
            extras[f"violou_desde_t{tm}"] = fora[:, idx:].any(axis=1)
    mu_col = mu[:, 0] if isinstance(mu, np.ndarray) else mu
    out = {"violou": violou, "t_primeira_violacao": t1,
           "fora_no_horizonte_fixo": (lo[:, -1] > mu_col) | (hi[:, -1] < mu_col), **extras}
    if mu0 is not None:
        mu0_col = mu0[:, 0] if isinstance(mu0, np.ndarray) else mu0
        out["decidiu_horizonte_fixo"] = lo[:, -1] > mu0_col
        dec = np.where(np.isnan(lo[:, sl]), False, lo[:, sl] > mu0)
        out["decidiu"] = dec.any(axis=1)
        out["t_decisao"] = np.where(out["decidiu"], np.argmax(dec, axis=1) + t_min, np.nan)
    for p in pontos:
        if p <= T:
            out[f"largura_t{p}"] = hi[:, p - 1] - lo[:, p - 1]
    return out


Gerador = Callable[[np.random.Generator, tuple[int, int]], np.ndarray]


def bernoulli(p: float) -> Gerador:
    return lambda rng, forma: (rng.random(forma) < p).astype(float)


def beta(media: float, conc: float) -> Gerador:
    return lambda rng, forma: rng.beta(media * conc, (1 - media) * conc, forma)


def rodar_monte_carlo(rng: np.random.Generator, gerador: Gerador, n_traj: int, T: int, mu: float,
                      mu0: float | None, alpha: float, t_min: int, pontos: tuple[int, ...],
                      bloco: int, transform: Callable[[np.ndarray], np.ndarray] | None = None,
                      metodos: tuple[str, ...] = ("cs_prpl_eb", "wald_peeking")) -> dict[str, dict[str, np.ndarray]]:
    """Gera ``n_traj`` trajetórias em blocos (memória limitada) e resume cada método.
    ``transform`` (opcional) mapeia o outcome bruto antes da CS (ex.: normalização por limite)."""
    acum: dict[str, list[dict[str, np.ndarray]]] = {m: [] for m in metodos}
    feitos = 0
    while feitos < n_traj:
        b = min(bloco, n_traj - feitos)
        x = gerador(rng, (b, T))
        xt = transform(x) if transform is not None else x
        for m in metodos:
            if m == "cs_prpl_eb":
                lo, hi = cs_prpl_eb(xt, alpha)
            elif m == "wald_peeking":
                lo, hi = wald_peeking(xt, alpha)
            else:
                raise ValueError(m)
            acum[m].append(resumir(lo, hi, mu, mu0, t_min, pontos))
        feitos += b
    return {m: {k: np.concatenate([d[k] for d in lst]) for k in lst[0]} for m, lst in acum.items()}


def agregar(res: dict[str, np.ndarray], T: int, deslocamento: int = 0) -> dict[str, Any]:
    """Agrega com IC de Monte Carlo. ``deslocamento`` soma atraso de calendário ao tempo de decisão."""
    from volc_dil.statlab.base import ic_media, ic_mediana, ic_proporcao

    n = int(res["violou"].size)
    out: dict[str, Any] = {
        "erro_uniforme_no_tempo": ic_proporcao(int(res["violou"].sum()), n),
        "t_mediano_primeira_violacao_entre_violadas": ic_mediana(res["t_primeira_violacao"]),
    }
    for k, v in res.items():
        if k.startswith("violou_desde_t"):
            out[k.replace("violou", "erro_uniforme")] = ic_proporcao(int(v.sum()), n)
    out["erro_so_no_horizonte_fixo_T"] = ic_proporcao(int(res["fora_no_horizonte_fixo"].sum()), n)
    if "decidiu" in res:
        out["frac_decidiu_horizonte_fixo_T"] = ic_proporcao(int(res["decidiu_horizonte_fixo"].sum()), n)
        out["frac_decidiu_ate_T"] = ic_proporcao(int(res["decidiu"].sum()), n)
        # tempo até decidir: trajetórias que não decidiram contam como > T (mediana com censura à direita)
        td = np.where(res["decidiu"], res["t_decisao"] + deslocamento, np.inf)
        med = float(np.median(td))
        out["t_mediano_decisao_calendario"] = med if np.isfinite(med) else f"> {T + deslocamento}"
    for k, v in res.items():
        if k.startswith("largura_t"):
            out[k] = ic_media(v)
    return out
