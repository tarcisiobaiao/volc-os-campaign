"""Shrinkage Empirical Bayes simples e as suas contraprovas.

- Beta-Binomial (taxas, ex. CVR = conversões/cliques): prior Beta(a, b) estimado por
  método dos momentos (ponderado por n, à la Kleinman 1973) ou MLE da marginal
  beta-binomial; posterior Beta(a + x, b + n - x).
- Gamma-Poisson (contagens com exposição): prior Gamma(alpha, beta) (taxa beta) por
  momentos ou MLE da marginal binomial-negativa; posterior Gamma(alpha + y, beta + e).
- Receita monetária zero-inflada: Gamma-Poisson aplicado a dinheiro depende da UNIDADE
  monetária (R$ vs centavos) porque assume Var = média; alternativas testadas:
  normal-normal EB com variância intra-unidade empírica agrupada e hurdle
  (P(conversão) Beta-Binomial x valor por conversão lognormal-normal EB).

Ausência: unidade com n == 0 tem estimativa crua ``NaN`` (não 0); a posterior cai no prior
e a unidade é marcada ``sem_dados``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
from scipy import optimize, special, stats

_Z = stats.norm.ppf


# ---------------------------------------------------------------------------
# Beta-Binomial
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PriorBeta:
    a: float
    b: float
    metodo: str
    status: str  # "estimado" | "sem_heterogeneidade_detectada" | "fronteira_mle"

    @property
    def media(self) -> float:
        return self.a / (self.a + self.b)


def _validar_xn(x: Any, n: Any) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=float)
    n = np.asarray(n, dtype=float)
    if x.shape != n.shape:
        raise ValueError("x e n com formas diferentes")
    if np.any(~np.isfinite(x)) or np.any(~np.isfinite(n)):
        raise ValueError("x/n com ausência: trate explicitamente antes (não vire 0)")
    if np.any(x < 0) or np.any(x > n):
        raise ValueError("exige 0 <= x <= n")
    return x, n


_AB_MAX = 1e7  # cap numérico para "sem heterogeneidade" (pooling total)


def prior_beta_momentos(x: Any, n: Any) -> PriorBeta:
    x, n = _validar_xn(x, n)
    ok = n > 0
    x, n = x[ok], n[ok]
    K, N = x.size, n.sum()
    if K < 2 or N <= 0:
        raise ValueError("precisa de >= 2 unidades com n > 0")
    mu = x.sum() / N
    if mu <= 0 or mu >= 1:
        return PriorBeta(mu * _AB_MAX + 1e-12, (1 - mu) * _AB_MAX + 1e-12, "momentos", "taxa_degenerada")
    p = x / n
    s = np.sum(n * (p - mu) ** 2)
    denom = N - np.sum(n**2) / N - (K - 1)
    rho = (s / (mu * (1 - mu)) - (K - 1)) / denom if denom > 0 else -1.0
    if rho <= 0:
        return PriorBeta(mu * _AB_MAX, (1 - mu) * _AB_MAX, "momentos", "sem_heterogeneidade_detectada")
    ab = min(1.0 / rho - 1.0, _AB_MAX)
    return PriorBeta(mu * ab, (1 - mu) * ab, "momentos", "estimado")


def prior_beta_mle(x: Any, n: Any) -> PriorBeta:
    x, n = _validar_xn(x, n)
    ok = n > 0
    x, n = x[ok], n[ok]
    inicial = prior_beta_momentos(x, n)
    a0, b0 = min(inicial.a, 1e5), min(inicial.b, 1e5)

    def nll(th: np.ndarray) -> float:
        a, b = np.exp(th)
        return -float(np.sum(special.betaln(x + a, n - x + b) - special.betaln(a, b)))

    r = optimize.minimize(nll, np.log([a0, b0]), method="L-BFGS-B",
                          bounds=[(np.log(1e-3), np.log(_AB_MAX))] * 2)
    a, b = np.exp(r.x)
    status = "fronteira_mle" if (a + b) > 0.5 * _AB_MAX else "estimado"
    return PriorBeta(float(a), float(b), "mle", status)


def posterior_beta(x: Any, n: Any, prior: PriorBeta, nivel: float) -> dict[str, np.ndarray]:
    x, n = _validar_xn(x, n)
    a, b = prior.a + x, prior.b + n - x
    q = (1 - nivel) / 2
    with np.errstate(divide="ignore", invalid="ignore"):
        cru = np.where(n > 0, x / n, np.nan)
    return {"media": a / (a + b), "lo": stats.beta.ppf(q, a, b), "hi": stats.beta.ppf(1 - q, a, b),
            "cru": cru, "sem_dados": n == 0}


def ic_wilson(x: np.ndarray, n: np.ndarray, nivel: float) -> tuple[np.ndarray, np.ndarray]:
    z = _Z(1 - (1 - nivel) / 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        p = x / n
        den = 1 + z**2 / n
        c = (p + z**2 / (2 * n)) / den
        h = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / den
    lo = np.where(n > 0, c - h, np.nan)
    hi = np.where(n > 0, c + h, np.nan)
    return lo, hi


# ---------------------------------------------------------------------------
# Gamma-Poisson
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PriorGamma:
    alpha: float
    beta: float  # taxa
    metodo: str
    status: str

    @property
    def media(self) -> float:
        return self.alpha / self.beta


def _validar_ye(y: Any, e: Any) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(y, dtype=float)
    e = np.asarray(e, dtype=float)
    if np.any(~np.isfinite(y)) or np.any(~np.isfinite(e)):
        raise ValueError("y/e com ausência: trate explicitamente antes (não vire 0)")
    if np.any(y < 0) or np.any(e < 0):
        raise ValueError("exige y >= 0 e e >= 0")
    if np.any(np.abs(y - np.round(y)) > 1e-9):
        raise ValueError("Gamma-Poisson exige CONTAGENS inteiras; valor monetário contínuo não é contagem")
    return y, e


def prior_gamma_momentos(y: Any, e: Any) -> PriorGamma:
    y, e = _validar_ye(y, e)
    ok = e > 0
    y, e = y[ok], e[ok]
    K, E = y.size, e.sum()
    if K < 2 or E <= 0:
        raise ValueError("precisa de >= 2 unidades com exposição > 0")
    mu = y.sum() / E
    if mu <= 0:
        return PriorGamma(1e-12, 1.0, "momentos", "taxa_degenerada")
    r = y / e
    s = np.sum(e * (r - mu) ** 2)
    denom = E - np.sum(e**2) / E
    v = (s - (K - 1) * mu) / denom if denom > 0 else -1.0
    if v <= 0:
        return PriorGamma(mu * _AB_MAX, _AB_MAX, "momentos", "sem_heterogeneidade_detectada")
    return PriorGamma(mu**2 / v, mu / v, "momentos", "estimado")


def prior_gamma_mle(y: Any, e: Any) -> PriorGamma:
    y, e = _validar_ye(y, e)
    ok = e > 0
    y, e = y[ok], e[ok]
    ini = prior_gamma_momentos(y, e)
    mu = y.sum() / e.sum()
    a0 = min(max(ini.alpha, 1e-2), 1e5)

    def nll(th: np.ndarray) -> float:
        a, b = np.exp(th)
        ll = (special.gammaln(y + a) - special.gammaln(a) + a * np.log(b / (b + e))
              + y * np.log(e / (b + e)))
        return -float(np.sum(ll))

    r = optimize.minimize(nll, np.log([a0, a0 / max(mu, 1e-12)]), method="L-BFGS-B",
                          bounds=[(np.log(1e-4), np.log(_AB_MAX)), (np.log(1e-9), np.log(1e12))])
    a, b = np.exp(r.x)
    status = "fronteira_mle" if a > 0.5 * _AB_MAX else "estimado"
    return PriorGamma(float(a), float(b), "mle", status)


def posterior_gamma(y: Any, e: Any, prior: PriorGamma, nivel: float) -> dict[str, np.ndarray]:
    y, e = _validar_ye(y, e)
    a, b = prior.alpha + y, prior.beta + e
    q = (1 - nivel) / 2
    with np.errstate(divide="ignore", invalid="ignore"):
        cru = np.where(e > 0, y / e, np.nan)
    return {"media": a / b, "lo": stats.gamma.ppf(q, a, scale=1 / b),
            "hi": stats.gamma.ppf(1 - q, a, scale=1 / b), "cru": cru, "sem_dados": e == 0}


# ---------------------------------------------------------------------------
# Receita monetária: alternativas
# ---------------------------------------------------------------------------

def eb_normal_media(soma: np.ndarray, soma_quad: np.ndarray, n: np.ndarray, nivel: float
                    ) -> dict[str, Any]:
    """Normal-normal EB para a média por clique (ȳ_k), com variância intra-unidade AGRUPADA
    (a variância por unidade de quem tem 0 ou 1 conversão é 0 e não serve). Tau² por momentos.
    Invariante a escala por construção."""
    ok = n > 0
    K = int(ok.sum())
    N = n[ok].sum()
    ybar = np.where(ok, soma / np.where(ok, n, 1), np.nan)
    ss_dentro = np.sum(soma_quad[ok] - n[ok] * ybar[ok] ** 2)
    s2w = ss_dentro / (N - K)
    mu = soma[ok].sum() / N
    se2 = np.where(ok, s2w / np.where(ok, n, 1), np.inf)
    w = n[ok] / N
    tau2 = (np.sum(w * (ybar[ok] - mu) ** 2) - np.sum(w * se2[ok])) / (1 - np.sum(w**2))
    status = "estimado"
    if tau2 <= 0:
        tau2, status = 0.0, "sem_heterogeneidade_detectada"
    B = np.where(ok, tau2 / (tau2 + se2), 0.0)
    media = np.where(ok, mu + B * (np.nan_to_num(ybar) - mu), mu)
    var_post = np.where(ok, B * np.where(ok, se2, 0.0), tau2)
    z = _Z(1 - (1 - nivel) / 2)
    sd = np.sqrt(var_post)
    return {"media": media, "lo": media - z * sd, "hi": media + z * sd, "cru": ybar,
            "status": status, "tau2": float(tau2), "s2_dentro": float(s2w)}


def eb_hurdle(x: np.ndarray, n: np.ndarray, soma_log: np.ndarray, soma_log2: np.ndarray, nivel: float,
              rng: np.random.Generator, n_amostras: int) -> dict[str, Any]:
    """Hurdle: receita/clique = P(conv) x E[valor | conv].
    P(conv): Beta-Binomial EB (momentos). Valor: log-valor ~ Normal(mu_k, s2) com mu_k ~ N(m0, tau2)
    (EB por momentos, s2 agrupado); E[valor] = exp(mu_k + s2/2). Unidade sem conversão usa o prior do
    valor (marcado). Intervalo por amostragem da posterior (independência entre as partes assumida)."""
    pb = prior_beta_momentos(x, n)
    a_p, b_p = pb.a + x, pb.b + n - x
    conv = x > 0
    Kc = int(conv.sum())
    if Kc < 2:
        raise ValueError("hurdle precisa de >= 2 unidades com conversão")
    lbar = np.where(conv, soma_log / np.where(conv, x, 1), np.nan)
    gl = x[conv].sum() - Kc
    s2 = np.sum(soma_log2[conv] - x[conv] * lbar[conv] ** 2) / gl if gl > 0 else np.nan
    if not np.isfinite(s2):
        raise ValueError("variância intra do log-valor indefinida (poucas conversões repetidas)")
    m0 = soma_log[conv].sum() / x[conv].sum()
    se2 = np.where(conv, s2 / np.where(conv, x, 1), np.inf)
    w = x[conv] / x[conv].sum()
    tau2 = (np.sum(w * (lbar[conv] - m0) ** 2) - np.sum(w * se2[conv])) / (1 - np.sum(w**2))
    tau2 = max(tau2, 0.0)
    B = np.where(conv, tau2 / (tau2 + se2), 0.0)
    mu_post = np.where(conv, m0 + B * (np.nan_to_num(lbar) - m0), m0)
    v_post = np.where(conv, B * np.where(conv, se2, 0.0), tau2)
    p_media = a_p / (a_p + b_p)
    val_media = np.exp(mu_post + v_post / 2 + s2 / 2)
    media = p_media * val_media
    # intervalo por Monte Carlo da posterior
    ps = rng.beta(a_p, b_p, size=(n_amostras, x.size))
    mus = rng.normal(mu_post, np.sqrt(v_post), size=(n_amostras, x.size))
    amostras = ps * np.exp(mus + s2 / 2)
    q = (1 - nivel) / 2
    return {"media": media, "lo": np.quantile(amostras, q, axis=0), "hi": np.quantile(amostras, 1 - q, axis=0),
            "sem_conversao": ~conv, "tau2_log": float(tau2), "s2_log": float(s2), "prior_p": pb}


# ---------------------------------------------------------------------------
# simulação e métricas
# ---------------------------------------------------------------------------

def gerar_n(rng: np.random.Generator, K: int, mediana_n: float, sigma_n: float) -> np.ndarray:
    """Exposições heterogêneas (lognormal arredondada; pode gerar 0 -> unidade sem dados)."""
    return np.floor(rng.lognormal(np.log(mediana_n), sigma_n, K)).astype(float)


def metricas_estimador(verdade: np.ndarray, est: np.ndarray, top_k: int, n: np.ndarray,
                       lo: np.ndarray | None = None, hi: np.ndarray | None = None) -> dict[str, Any]:
    """MSE (excluindo NaN, contados), vencedores por sorte no top-k, regret do top-k,
    fração do top-k com n abaixo do quartil 25%, inclinação de calibração e cobertura."""
    ok = np.isfinite(est)
    # MSE sempre no MESMO conjunto (unidades com n > 0) para comparar estimadores
    comum = ok & (n > 0)
    erro2 = (est[comum] - verdade[comum]) ** 2
    ordem_est = np.argsort(-np.where(ok, est, -np.inf), kind="mergesort")[:top_k]
    ordem_ver = np.argsort(-verdade, kind="mergesort")[:top_k]
    sorte = int(np.setdiff1d(ordem_est, ordem_ver).size)
    q25 = np.quantile(n, 0.25)
    xs, ys = est[ok], verdade[ok]
    inclin = float(np.cov(xs, ys)[0, 1] / np.var(xs, ddof=1)) if xs.size > 2 and np.var(xs) > 0 else None
    m: dict[str, Any] = {
        "mse": float(erro2.mean()) if erro2.size else None,
        "n_excluidos_sem_estimativa": int((~ok).sum()),
        "vencedores_por_sorte_topk": sorte,
        "regret_topk": float(1 - verdade[ordem_est].mean() / verdade[ordem_ver].mean()),
        "frac_topk_n_baixo": float(np.mean(n[ordem_est] <= q25)),
        "inclinacao_calibracao": inclin,
    }
    if lo is not None and hi is not None:
        oki = np.isfinite(lo) & np.isfinite(hi)
        m["cobertura"] = float(np.mean((lo[oki] <= verdade[oki]) & (verdade[oki] <= hi[oki]))) if oki.any() else None
        m["n_sem_intervalo"] = int((~oki).sum())
    return m


GeradorTaxa = Callable[[np.random.Generator, int, np.ndarray], np.ndarray]


def gerar_taxas_beta(media: float, concentracao: float) -> GeradorTaxa:
    def g(rng: np.random.Generator, K: int, n: np.ndarray) -> np.ndarray:
        return rng.beta(media * concentracao, (1 - media) * concentracao, K)
    return g


def gerar_taxas_bimodal(media_base: float, media_vencedor: float, frac_vencedor: float,
                        concentracao: float) -> GeradorTaxa:
    """Contraprova: poucos vencedores REAIS fora da massa (prior Beta unimodal mal especificado)."""
    def g(rng: np.random.Generator, K: int, n: np.ndarray) -> np.ndarray:
        venc = rng.random(K) < frac_vencedor
        base = rng.beta(media_base * concentracao, (1 - media_base) * concentracao, K)
        alto = rng.beta(media_vencedor * concentracao, (1 - media_vencedor) * concentracao, K)
        return np.where(venc, alto, base)
    return g


def gerar_taxas_informativas(media: float, concentracao: float, elasticidade: float) -> GeradorTaxa:
    """Contraprova: n informativo (orçamento já foi para quem converte melhor): taxa cresce com n."""
    def g(rng: np.random.Generator, K: int, n: np.ndarray) -> np.ndarray:
        rel = np.log1p(n) - np.log1p(n).mean()
        mu_k = np.clip(media * np.exp(elasticidade * rel), 1e-4, 0.5)
        return rng.beta(mu_k * concentracao, (1 - mu_k) * concentracao)
    return g


def replica_taxas(rng: np.random.Generator, K: int, mediana_n: float, sigma_n: float,
                  gerador: GeradorTaxa, top_k: int, nivel: float) -> dict[str, Any]:
    n = gerar_n(rng, K, mediana_n, sigma_n)
    p = gerador(rng, K, n)
    x = rng.binomial(n.astype(int), p).astype(float)
    com = n > 0
    pm = prior_beta_momentos(x, n)
    pl = prior_beta_mle(x, n)
    post_m = posterior_beta(x, n, pm, nivel)
    post_l = posterior_beta(x, n, pl, nivel)
    grupo = np.full(K, x.sum() / n.sum())
    lo_w, hi_w = ic_wilson(x, n, nivel)
    out = {
        "cru": metricas_estimador(p, post_m["cru"], top_k, n, lo_w, hi_w),
        "media_grupo": metricas_estimador(p, grupo, top_k, n),
        "eb_momentos": metricas_estimador(p, post_m["media"], top_k, n, post_m["lo"], post_m["hi"]),
        "eb_mle": metricas_estimador(p, post_l["media"], top_k, n, post_l["lo"], post_l["hi"]),
        "status_prior": {"momentos": pm.status, "mle": pl.status},
        "n_unidades_sem_dados": int((~com).sum()),
    }
    # cobertura no subgrupo dos top-10% verdadeiros (onde shrinkage puxa vencedores reais para baixo)
    top = p >= np.quantile(p, 0.9)
    for nome, lo, hi in (("cru", lo_w, hi_w), ("eb_mle", post_l["lo"], post_l["hi"])):
        oki = top & np.isfinite(lo)
        out[nome]["cobertura_top10pct_verdadeiro"] = float(np.mean((lo[oki] <= p[oki]) & (p[oki] <= hi[oki])))
    return out


def replica_contagens(rng: np.random.Generator, K: int, mediana_e: float, sigma_e: float,
                      media_taxa: float, forma: float, top_k: int, nivel: float) -> dict[str, Any]:
    e = gerar_n(rng, K, mediana_e, sigma_e)
    lam = rng.gamma(forma, media_taxa / forma, K)
    y = rng.poisson(lam * e).astype(float)
    pm = prior_gamma_momentos(y, e)
    pl = prior_gamma_mle(y, e)
    post_m = posterior_gamma(y, e, pm, nivel)
    post_l = posterior_gamma(y, e, pl, nivel)
    grupo = np.full(K, y.sum() / e.sum())
    # IC cru: exato de Garwood
    q = (1 - nivel) / 2
    with np.errstate(divide="ignore", invalid="ignore"):
        lo = np.where(e > 0, np.where(y > 0, stats.chi2.ppf(q, 2 * y) / 2, 0.0) / e, np.nan)
        hi = np.where(e > 0, stats.chi2.ppf(1 - q, 2 * y + 2) / 2 / e, np.nan)
    return {
        "cru": metricas_estimador(lam, post_m["cru"], top_k, e, lo, hi),
        "media_grupo": metricas_estimador(lam, grupo, top_k, e),
        "eb_momentos": metricas_estimador(lam, post_m["media"], top_k, e, post_m["lo"], post_m["hi"]),
        "eb_mle": metricas_estimador(lam, post_l["media"], top_k, e, post_l["lo"], post_l["hi"]),
        "status_prior": {"momentos": pm.status, "mle": pl.status},
        "n_unidades_sem_dados": int((e == 0).sum()),
    }


def simular_receita(rng: np.random.Generator, K: int, mediana_n: float, sigma_n: float,
                    media_cvr: float, conc_cvr: float, mediana_valor: float, tau_log_valor: float,
                    sigma_log_valor: float, alpha_pareto: float | None = None) -> dict[str, np.ndarray]:
    """Receita por clique zero-inflada: clique converte com p_k, valor lognormal(mu_k, sigma).
    Devolve suficientes por unidade (n, x, soma, soma², soma_log, soma_log²) e a verdade."""
    n = gerar_n(rng, K, mediana_n, sigma_n)
    p = rng.beta(media_cvr * conc_cvr, (1 - media_cvr) * conc_cvr, K)
    mu = rng.normal(np.log(mediana_valor), tau_log_valor, K)
    x = rng.binomial(n.astype(int), p).astype(float)
    unidade = np.repeat(np.arange(K), x.astype(int))
    if alpha_pareto is None:
        lv = rng.normal(mu[unidade], sigma_log_valor)
        verdade = p * np.exp(mu + sigma_log_valor**2 / 2)
    else:
        # contraprova: valor = exp(mu_k) * (1 + Lomax(alpha)) — NÃO lognormal (hurdle mal especificado)
        if alpha_pareto <= 1:
            raise ValueError("alpha_pareto <= 1 => média infinita; verdade indefinida")
        lv = mu[unidade] + np.log1p(rng.pareto(alpha_pareto, unidade.size))
        verdade = p * np.exp(mu) * alpha_pareto / (alpha_pareto - 1)
    v = np.exp(lv)
    def soma(w: np.ndarray) -> np.ndarray:
        return np.bincount(unidade, weights=w, minlength=K)
    return {"n": n, "x": x, "soma": soma(v), "soma2": soma(v * v), "soma_log": soma(lv),
            "soma_log2": soma(lv * lv), "verdade": verdade}


def gamma_poisson_em_dinheiro(soma: np.ndarray, n: np.ndarray, fator_unidade: float, nivel: float
                              ) -> dict[str, Any]:
    """USO INDEVIDO deliberado: arredonda receita para 'contagem' na unidade dada (1 = R$,
    100 = centavos) e aplica Gamma-Poisson com exposição = cliques. Resultado volta para R$."""
    y = np.round(soma * fator_unidade)
    pr = prior_gamma_mle(y, n)
    post = posterior_gamma(y, n, pr, nivel)
    return {"media": post["media"] / fator_unidade, "lo": post["lo"] / fator_unidade,
            "hi": post["hi"] / fator_unidade, "prior": pr,
            "fator_shrink_mediano": float(np.median(pr.beta / (pr.beta + n[n > 0])))}


def replica_receita(rng: np.random.Generator, top_k: int, nivel: float, n_amostras_hurdle: int,
                    **cen: Any) -> dict[str, Any]:
    d = simular_receita(rng, **cen)
    n, verdade = d["n"], d["verdade"]
    with np.errstate(divide="ignore", invalid="ignore"):
        cru = np.where(n > 0, d["soma"] / n, np.nan)
    grupo = np.full(n.size, d["soma"].sum() / n.sum())
    gp_r = gamma_poisson_em_dinheiro(d["soma"], n, 1.0, nivel)
    gp_c = gamma_poisson_em_dinheiro(d["soma"], n, 100.0, nivel)
    nn = eb_normal_media(d["soma"], d["soma2"], n, nivel)
    hu = eb_hurdle(d["x"], n, d["soma_log"], d["soma_log2"], nivel, rng, n_amostras_hurdle)
    return {
        "cru": metricas_estimador(verdade, cru, top_k, n),
        "media_grupo": metricas_estimador(verdade, grupo, top_k, n),
        "gamma_poisson_reais": metricas_estimador(verdade, gp_r["media"], top_k, n, gp_r["lo"], gp_r["hi"]),
        "gamma_poisson_centavos": metricas_estimador(verdade, gp_c["media"], top_k, n, gp_c["lo"], gp_c["hi"]),
        "eb_normal_var_empirica": metricas_estimador(verdade, nn["media"], top_k, n, nn["lo"], nn["hi"]),
        "hurdle_beta_lognormal": metricas_estimador(verdade, hu["media"], top_k, n, hu["lo"], hu["hi"]),
        "gp_fator_shrink_mediano": {"reais": gp_r["fator_shrink_mediano"], "centavos": gp_c["fator_shrink_mediano"]},
    }


def agregar_replicas(reps: list[dict[str, Any]], estimadores: list[str]) -> dict[str, Any]:
    from volc_dil.statlab.base import ic_media

    saida: dict[str, Any] = {}
    chaves = ("mse", "vencedores_por_sorte_topk", "regret_topk", "frac_topk_n_baixo",
              "inclinacao_calibracao", "cobertura", "cobertura_top10pct_verdadeiro")
    mse_cru = np.array([r["cru"]["mse"] for r in reps], dtype=float)
    for est in estimadores:
        linha: dict[str, Any] = {}
        for k in chaves:
            vals = [r[est].get(k) for r in reps]
            if all(v is None for v in vals):
                continue
            linha[k] = ic_media(np.array([np.nan if v is None else v for v in vals], dtype=float))
        mse = np.array([r[est]["mse"] for r in reps], dtype=float)
        linha["mse_relativo_ao_cru"] = ic_media(mse / mse_cru)
        saida[est] = linha
    return saida
