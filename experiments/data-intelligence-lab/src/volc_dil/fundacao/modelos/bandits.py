"""Bandits contextuais mínimos (Thompson linear, LinUCB) e avaliação off-policy (IPS, SNIPS, DR).

Ambiente semi-sintético: uma matriz de recompensas ``r[a, t]`` (ex.: lucro horário de cada campanha,
tirado da VERDADE do simulador) e um contexto categórico ``x_t`` (ex.: bloco horário × fim de semana).
Escolher o braço ``a`` em ``t`` revela só ``r[a, t]``. Simplificação declarada: a escolha não altera o
mundo (conversão supervisionado→bandit); no VOLC real a alocação mudaria leilão e saturação.

OPE só é possível com a probabilidade com que a ação logada foi escolhida (propensão). O VOLC hoje
não loga propensão (decisões humanas): ``ips``/``snips``/``dr`` RECUSAM (``PropensaoAusente``) quando
ela falta, é zero ou não finita. Propensão "inventada" depois do fato (ex.: supor uniforme) enviesa.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np


class PropensaoAusente(ValueError):
    """Log sem propensão válida: não há estimador off-policy honesto."""


# ---------------------------------------------------------------------------
# políticas online (devolvem a distribuição sobre braços = propensão)
# ---------------------------------------------------------------------------

@dataclass
class _Estado:
    K: int
    n_ctx: int
    soma: np.ndarray = field(init=False)
    soma2: np.ndarray = field(init=False)
    n: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.soma = np.zeros((self.n_ctx, self.K))
        self.soma2 = np.zeros((self.n_ctx, self.K))
        self.n = np.zeros((self.n_ctx, self.K))

    def atualizar(self, x: int, a: int, r: float) -> None:
        self.soma[x, a] += r
        self.soma2[x, a] += r * r
        self.n[x, a] += 1


class Uniforme:
    nome = "equal"

    def __init__(self, K: int, n_ctx: int, **_: Any) -> None:
        self.K = K

    def distribuicao(self, x: int, rng: np.random.Generator) -> np.ndarray:
        return np.full(self.K, 1.0 / self.K)

    def atualizar(self, x: int, a: int, r: float) -> None:
        pass


class Gulosa:
    """ε-guloso por contexto (ε = 0: guloso puro). Braço nunca tentado no contexto tem prioridade."""

    def __init__(self, K: int, n_ctx: int, *, epsilon: float = 0.0, **_: Any) -> None:
        self.s = _Estado(K, n_ctx)
        self.K = K
        self.eps = epsilon
        self.nome = "greedy" if epsilon == 0 else f"eps_greedy_{epsilon:g}"

    def distribuicao(self, x: int, rng: np.random.Generator) -> np.ndarray:
        n = self.s.n[x]
        if (n == 0).any():
            alvo = (n == 0).astype(float)
        else:
            med = self.s.soma[x] / n
            alvo = (med == med.max()).astype(float)
        p = (1 - self.eps) * alvo / alvo.sum() + self.eps / self.K
        return p

    def atualizar(self, x: int, a: int, r: float) -> None:
        self.s.atualizar(x, a, r)


class LinUCB:
    """LinUCB disjunto com contexto one-hot (equivale a UCB por contexto com prior ridge λ).
    ``alpha`` em unidades do desvio do ruído; ``epsilon`` mistura exploração uniforme para o log ter
    propensão > 0 em todos os braços (necessário para OPE posterior)."""

    def __init__(self, K: int, n_ctx: int, *, alpha: float, lam: float = 1.0, epsilon: float = 0.0, **_: Any) -> None:
        self.s = _Estado(K, n_ctx)
        self.K, self.alpha, self.lam, self.eps = K, alpha, lam, epsilon
        self.nome = "linucb"

    def distribuicao(self, x: int, rng: np.random.Generator) -> np.ndarray:
        n = self.s.n[x]
        media = self.s.soma[x] / (n + self.lam)
        tot_n = self.s.n.sum()
        var = (self.s.soma2.sum() - (self.s.soma.sum() ** 2) / tot_n) / max(tot_n - 1, 1) if tot_n > 1 else 1.0
        sd = float(np.sqrt(max(var, 1e-12)))
        ucb = media + self.alpha * sd / np.sqrt(n + self.lam)
        alvo = (ucb == ucb.max()).astype(float)
        return (1 - self.eps) * alvo / alvo.sum() + self.eps / self.K

    def atualizar(self, x: int, a: int, r: float) -> None:
        self.s.atualizar(x, a, r)


class ThompsonLinear:
    """Thompson gaussiano por contexto×braço (prior N(0, v²/λ), ruído com variância estimada).
    A propensão de Thompson não tem forma fechada: estimada por ``n_mc`` sorteios da posterior
    (aproximação declarada; o log grava a estimativa)."""

    def __init__(self, K: int, n_ctx: int, *, v: float = 1.0, lam: float = 1.0, n_mc: int = 200, **_: Any) -> None:
        self.s = _Estado(K, n_ctx)
        self.K, self.v, self.lam, self.n_mc = K, v, lam, n_mc
        self.nome = "thompson"

    def distribuicao(self, x: int, rng: np.random.Generator) -> np.ndarray:
        n = self.s.n[x]
        media = self.s.soma[x] / (n + self.lam)
        tot_n = self.s.n.sum()
        var = (self.s.soma2.sum() - (self.s.soma.sum() ** 2) / tot_n) / max(tot_n - 1, 1) if tot_n > 1 else 1.0
        sd = self.v * np.sqrt(max(var, 1e-12)) / np.sqrt(n + self.lam)
        amostras = media[None, :] + sd[None, :] * rng.standard_normal((self.n_mc, self.K))
        vencedor = np.argmax(amostras, axis=1)
        p = np.bincount(vencedor, minlength=self.K) / self.n_mc
        return np.maximum(p, 0.5 / self.n_mc) / np.maximum(p, 0.5 / self.n_mc).sum()

    def atualizar(self, x: int, a: int, r: float) -> None:
        self.s.atualizar(x, a, r)


POLITICAS = {"equal": Uniforme, "greedy": Gulosa, "linucb": LinUCB, "thompson": ThompsonLinear}


@dataclass(frozen=True)
class Log:
    contexto: np.ndarray       # (T,)
    acao: np.ndarray           # (T,)
    recompensa: np.ndarray     # (T,)
    propensao: Optional[np.ndarray]  # (T,) prob. da ação logada; None = não logada


def rodar(politica, r: np.ndarray, ctx: np.ndarray, *, seed: int, logar_propensao: bool = True) -> dict[str, Any]:
    """Executa a política online sobre ``r`` (K, T). Devolve o log e as distribuições por rodada."""
    K, T = r.shape
    rng = np.random.default_rng(seed)
    acoes = np.empty(T, dtype=int)
    props = np.empty(T)
    dist = np.empty((T, K))
    for t in range(T):
        p = politica.distribuicao(int(ctx[t]), rng)
        a = int(rng.choice(K, p=p))
        acoes[t], props[t], dist[t] = a, p[a], p
        politica.atualizar(int(ctx[t]), a, float(r[a, t]))
    log = Log(ctx.astype(int), acoes, r[acoes, np.arange(T)], props if logar_propensao else None)
    return {"log": log, "distribuicoes": dist}


def medias_por_contexto(r: np.ndarray, ctx: np.ndarray, n_ctx: int) -> np.ndarray:
    """μ[x, a] = média de r[a, t] nas rodadas com contexto x (verdade em retrospecto; avaliação apenas)."""
    K = r.shape[0]
    mu = np.full((n_ctx, K), np.nan)
    for x in range(n_ctx):
        sel = ctx == x
        if sel.any():
            mu[x] = r[:, sel].mean(axis=1)
    return mu


def pseudo_regret(dist: np.ndarray, ctx: np.ndarray, mu: np.ndarray) -> float:
    """Σ_t (max_a μ[x_t, a] − Σ_a π_t(a) μ[x_t, a]) — regret contra a melhor política contextual fixa."""
    m = mu[ctx]
    return float((m.max(axis=1) - (dist * m).sum(axis=1)).sum())


def valor_verdadeiro(pi_alvo: np.ndarray, r: np.ndarray) -> float:
    """V(π) = média_t Σ_a π(a|x_t) r[a, t] — exato no ambiente semi-sintético. ``pi_alvo`` (T, K)."""
    return float((pi_alvo * r.T).sum(axis=1).mean())


# ---------------------------------------------------------------------------
# OPE
# ---------------------------------------------------------------------------

def _pesos(log: Log, pi_alvo: np.ndarray) -> np.ndarray:
    if log.propensao is None:
        raise PropensaoAusente("log sem propensão: decisões sem probabilidade registrada não admitem OPE honesto")
    p = np.asarray(log.propensao, dtype=float)
    if np.any(~np.isfinite(p)) or np.any(p <= 0) or np.any(p > 1):
        raise PropensaoAusente("propensão ausente, zero ou fora de (0, 1]")
    T = log.acao.size
    return pi_alvo[np.arange(T), log.acao] / p


def ips(log: Log, pi_alvo: np.ndarray) -> float:
    return float((_pesos(log, pi_alvo) * log.recompensa).mean())


def snips(log: Log, pi_alvo: np.ndarray) -> float:
    w = _pesos(log, pi_alvo)
    return float((w * log.recompensa).sum() / w.sum()) if w.sum() > 0 else float("nan")


def q_tabular_cruzado(log: Log, n_ctx: int, K: int, *, lam: float = 1.0) -> np.ndarray:
    """q̂(x_t, a) por média encolhida (ridge λ para a média global) por contexto×braço, com
    cross-fitting em duas dobras (rodadas pares/ímpares) para não usar a própria rodada. (T, K)."""
    T = log.acao.size
    q = np.empty((T, K))
    dobra = np.arange(T) % 2
    for f in (0, 1):
        tr = dobra != f
        g = log.recompensa[tr].mean() if tr.any() else 0.0
        s = np.zeros((n_ctx, K)); n = np.zeros((n_ctx, K))
        np.add.at(s, (log.contexto[tr], log.acao[tr]), log.recompensa[tr])
        np.add.at(n, (log.contexto[tr], log.acao[tr]), 1)
        tab = (s + lam * g) / (n + lam)
        q[dobra == f] = tab[log.contexto[dobra == f]]
    return q


def dr(log: Log, pi_alvo: np.ndarray, q: np.ndarray) -> float:
    w = _pesos(log, pi_alvo)
    T = log.acao.size
    direto = (pi_alvo * q).sum(axis=1)
    return float((direto + w * (log.recompensa - q[np.arange(T), log.acao])).mean())


__all__ = ["Gulosa", "LinUCB", "Log", "POLITICAS", "PropensaoAusente", "ThompsonLinear", "Uniforme", "dr", "ips",
           "medias_por_contexto", "pseudo_regret", "q_tabular_cruzado", "rodar", "snips", "valor_verdadeiro"]
