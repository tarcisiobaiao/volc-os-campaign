"""Empirical Bayes / shrinkage para taxas e médias por campanha — fachada fina sobre o Stat Lab.

Reuso integral de ``volc_dil.statlab.shrinkage`` (Beta-Binomial por momentos/MLE, normal-normal
com variância intra agrupada). Aqui só ficam: a API que o shadow chama, a métrica de "vencedores por
sorte" e a montagem das taxas a partir de painéis ``as_of`` (NaN = sem dado; nunca 0).
"""
from __future__ import annotations

from typing import Any

import numpy as np

from volc_dil.statlab.shrinkage import eb_normal_media, posterior_beta, prior_beta_mle, prior_beta_momentos


def encolher_taxa(x: Any, n: Any, *, nivel: float, metodo: str = "momentos") -> dict[str, Any]:
    """Taxa x/n encolhida por Beta-Binomial EB. ``n == 0`` → posterior = prior, marcado ``sem_dados``.
    Ausência (NaN) em x ou n é RECUSADA pelo herdado (trate antes)."""
    if metodo not in ("momentos", "mle"):
        raise ValueError("metodo: momentos | mle")
    prior = prior_beta_momentos(x, n) if metodo == "momentos" else prior_beta_mle(x, n)
    post = posterior_beta(x, n, prior, nivel)
    return {**post, "prior": {"a": prior.a, "b": prior.b, "status": prior.status, "metodo": prior.metodo}}


def encolher_media(soma: Any, soma_quad: Any, n: Any, *, nivel: float) -> dict[str, Any]:
    """Média por unidade (ex.: RPM diário de cada campanha, n = dias) encolhida por normal-normal EB
    com variância intra agrupada (herdado). Unidade com n == 0 recebe a média global."""
    s = np.asarray(soma, dtype=float)
    q = np.asarray(soma_quad, dtype=float)
    k = np.asarray(n, dtype=float)
    if not (np.all(np.isfinite(s)) and np.all(np.isfinite(q)) and np.all(np.isfinite(k))):
        raise ValueError("ausência em soma/soma_quad/n: trate antes (não vira 0)")
    return eb_normal_media(s, q, k, nivel)


def vencedores_por_sorte(estimativa: Any, verdade: Any, *, frac_top: float) -> dict[str, Any]:
    """Quantos dos selecionados no top ``frac_top`` pela estimativa NÃO estão no top verdadeiro.
    Unidades com estimativa ou verdade NaN ficam fora (contadas)."""
    e = np.asarray(estimativa, dtype=float)
    v = np.asarray(verdade, dtype=float)
    ok = np.isfinite(e) & np.isfinite(v)
    n = int(ok.sum())
    k = max(1, int(round(frac_top * n)))
    if n < 2:
        return {"selecionados": 0, "por_sorte": None, "n": n, "n_excluidos": int((~ok).sum())}
    ie = np.nonzero(ok)[0]
    top_e = set(ie[np.argsort(-e[ok], kind="mergesort")[:k]].tolist())
    top_v = set(ie[np.argsort(-v[ok], kind="mergesort")[:k]].tolist())
    return {"selecionados": k, "por_sorte": len(top_e - top_v), "n": n, "n_excluidos": int((~ok).sum())}


__all__ = ["encolher_media", "encolher_taxa", "vencedores_por_sorte"]
