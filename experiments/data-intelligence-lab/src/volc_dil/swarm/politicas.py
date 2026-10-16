"""Políticas de alocação SINTÉTICA. Todas devolvem ``np.int64`` em micros via ``inteirizar``.

Nenhuma política lê a verdade do cenário, exceto ``Oraculo`` (usado só para regret).

Modos de decisão:
- ``parcial``: usa a receita como reportada agora (linhas recentes ainda imaturas);
- ``madura``: usa só linhas com idade >= ``atraso_assumido`` (receita já completa),
  ao custo de esperar.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from volc_dil.swarm.cenario import MICROS, CenarioRealizado
from volc_dil.swarm.simulador import Observacao, inteirizar

_DECISOES = ("parcial", "madura")
_UNIDADES = ("cliques", "gasto")


def _valor_roi(g: np.ndarray, r: np.ndarray) -> np.ndarray:
    """Contribuição observada por R$ ((receita − gasto)/gasto). Sem gasto -> NaN (não 0)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(g > 0, (r - g) / np.where(g > 0, g, 1), np.nan)


def _ordem_desc(valor: np.ndarray, candidatos: np.ndarray) -> np.ndarray:
    """Índices de ``candidatos`` ordenados por valor desc; NaN por último; empate -> menor índice."""
    v = np.where(np.isnan(valor[candidatos]), -np.inf, valor[candidatos])
    return candidatos[np.lexsort((candidatos, -v))]


class _Base:
    nome = "base"

    def reiniciar(self, K: int, T: int, orcamento: int, minimo: int, rng: np.random.Generator) -> None:
        self.K, self.T, self.B, self.m, self.rng = K, T, orcamento, minimo, rng
        self._ultima = None

    def _dados(self, obs: Observacao, decisao: str, atraso: int):
        return obs.acumulado(0 if decisao == "parcial" else atraso)

    def promovidas(self) -> np.ndarray:
        if self._ultima is None:
            return np.zeros(self.K, bool)
        return self._ultima > self.B / self.K

    def extras(self) -> dict:
        return {}


class EqualBudget(_Base):
    nome = "equal"

    def alocar(self, obs: Observacao) -> np.ndarray:
        self._ultima = inteirizar(np.ones(self.K), self.B, self.m)
        return self._ultima

    def promovidas(self) -> np.ndarray:
        # Não seleciona: "promove" todas (documentado; por isso o critério usa orçamento em perdedoras).
        return np.ones(self.K, bool)


class GreedyConservador(_Base):
    """Janela inicial equal; depois move ``lam`` do caminho rumo a equal nas top-n estimadas."""

    def __init__(self, janela: int = 3, lam: float = 0.3, n_top: int = 4, decisao: str = "parcial",
                 atraso_assumido: int = 0, nome: str | None = None):
        assert decisao in _DECISOES
        self.janela, self.lam, self.n_top, self.decisao, self.atraso = janela, lam, n_top, decisao, atraso_assumido
        self.nome = nome or f"greedy_{decisao}"

    def reiniciar(self, K, T, orcamento, minimo, rng):
        super().reiniciar(K, T, orcamento, minimo, rng)
        self.prev = np.full(K, orcamento / K)

    def alocar(self, obs: Observacao) -> np.ndarray:
        alvo = np.full(self.K, self.B / self.K)
        if obs.t >= self.janela:
            g, _, r = self._dados(obs, self.decisao, self.atraso)
            val = _valor_roi(g, r)
            if np.isfinite(val).any():
                top = _ordem_desc(val, np.arange(self.K))[: self.n_top]
                alvo = np.zeros(self.K)
                alvo[top] = self.B / len(top)
        novo = (1 - self.lam) * self.prev + self.lam * alvo
        a = inteirizar(novo, self.B, self.m)
        self.prev = a.astype(float)
        self._ultima = a
        return a


class SuccessiveHalving(_Base):
    """SH síncrono: todas as vivas recebem orçamento igual; no degrau i (métrica acumulada por
    célula >= degraus[i]) mantém ceil(n/eta) (o último degrau corta para ``n_final``).

    ``promocao='aleatoria'`` é o baseline random com o MESMO cronograma (isola o valor da informação).
    """

    def __init__(self, eta: float = 2, degraus: tuple[float, ...] = (60, 180), unidade: str = "cliques",
                 n_final: int = 4, decisao: str = "parcial", atraso_assumido: int = 0,
                 promocao: str = "melhor", nome: str | None = None):
        assert decisao in _DECISOES and unidade in _UNIDADES and promocao in ("melhor", "aleatoria")
        assert eta > 1 and len(degraus) >= 1 and all(b > a for a, b in zip(degraus, degraus[1:]))
        self.eta, self.degraus, self.unidade, self.n_final = eta, tuple(degraus), unidade, n_final
        self.decisao, self.atraso, self.promocao = decisao, atraso_assumido, promocao
        self.nome = nome or ("random_sh" if promocao == "aleatoria" else f"sh_{decisao}")

    def reiniciar(self, K, T, orcamento, minimo, rng):
        super().reiniciar(K, T, orcamento, minimo, rng)
        self.vivos = np.ones(K, bool)
        self.rung = 0
        self.historico: list[dict] = []

    def _metrica(self, g, c):
        return c.astype(float) if self.unidade == "cliques" else g / MICROS

    def alocar(self, obs: Observacao) -> np.ndarray:
        while self.rung < len(self.degraus):
            g, c, r = self._dados(obs, self.decisao, self.atraso)
            idx = np.flatnonzero(self.vivos)
            if not (self._metrica(g, c)[idx] >= self.degraus[self.rung]).all():
                break
            ultimo = self.rung == len(self.degraus) - 1
            n_keep = self.n_final if ultimo else max(self.n_final, math.ceil(idx.size / self.eta))
            n_keep = min(n_keep, idx.size)
            if n_keep < idx.size:
                if self.promocao == "melhor":
                    manter = _ordem_desc(_valor_roi(g, r), idx)[:n_keep]
                else:
                    manter = self.rng.choice(idx, size=n_keep, replace=False)
                self.vivos = np.zeros(self.K, bool)
                self.vivos[manter] = True
            self.historico.append({"rung": self.rung, "t": obs.t, "n_antes": int(idx.size), "n_depois": int(n_keep)})
            self.rung += 1
        a = inteirizar(self.vivos.astype(float), self.B, self.m)
        self._ultima = a
        return a

    def promovidas(self) -> np.ndarray:
        return self.vivos.copy()

    def extras(self) -> dict:
        return {"concluiu": self.rung == len(self.degraus),
                "t_fim_exploracao": self.historico[-1]["t"] if self.rung == len(self.degraus) else None}


class ASHA(_Base):
    """ASHA (Li et al.) mapeado para células: ``n_slots`` trials rodando em paralelo dividem o
    orçamento com as células em produção; um trial que atinge o degrau do seu rung para e
    reporta (``parcial``: na hora; ``madura``: fica pendente, sem orçamento, até a métrica
    madura atingir o degrau). Slot livre -> promove o melhor do top 1/eta de algum rung
    (de cima para baixo) ou inicia uma célula nova (ordem aleatória). Completar o último rung
    = célula "treinada até o fim" (candidata à produção, recebe orçamento). A exploração termina
    quando ``n_topo`` (padrão n_final·eta) células completam o último rung, ou não há mais
    trabalho; aí a produção são as ``n_final`` melhores do último rung (seleção final do HPO).
    """

    def __init__(self, eta: float = 2, degraus: tuple[float, ...] = (60, 180), unidade: str = "cliques",
                 n_slots: int = 8, n_final: int = 4, decisao: str = "parcial", atraso_assumido: int = 0,
                 n_topo: int | None = None, nome: str | None = None):
        assert decisao in _DECISOES and unidade in _UNIDADES and eta > 1
        self.n_topo = n_topo if n_topo is not None else int(math.ceil(n_final * eta))
        self.eta, self.degraus, self.unidade, self.n_slots, self.n_final = eta, tuple(degraus), unidade, n_slots, n_final
        self.decisao, self.atraso = decisao, atraso_assumido
        self.nome = nome or f"asha_{decisao}"

    # estados
    NAO, RODANDO, PENDENTE, PARADA = 0, 1, 2, 3

    def reiniciar(self, K, T, orcamento, minimo, rng):
        super().reiniciar(K, T, orcamento, minimo, rng)
        self.status = np.zeros(K, np.int8)
        self.alvo = np.zeros(K, np.int64)
        self.completou: list[dict[int, float]] = [dict() for _ in self.degraus]
        self.promovida_de: list[set[int]] = [set() for _ in self.degraus]
        self.producao: list[int] = []
        self.ordem = rng.permutation(K)
        self.prox = 0
        self.explorando = True
        self.t_fim = None
        self.promocoes = 0

    def _metrica(self, g, c):
        return c.astype(float) if self.unidade == "cliques" else g / MICROS

    def _reportar(self, k: int, valor: float) -> None:
        r = int(self.alvo[k])
        self.completou[r][k] = valor
        self.status[k] = self.PARADA
        if r == len(self.degraus) - 1:
            self.producao.append(k)

    def _proximo_job(self):
        R = len(self.degraus)
        for r in range(R - 2, -1, -1):
            comp = self.completou[r]
            n_prom = int(len(comp) // self.eta)
            if n_prom < 1:
                continue
            ks = np.fromiter(comp.keys(), dtype=np.int64)
            vals = np.full(self.K, np.nan)
            vals[ks] = [comp[int(k)] for k in ks]
            top = _ordem_desc(vals, ks)[:n_prom]
            for k in top:
                if int(k) not in self.promovida_de[r]:
                    self.promovida_de[r].add(int(k))
                    self.promocoes += 1
                    return int(k), r + 1
        if self.prox < self.K:
            k = int(self.ordem[self.prox])
            self.prox += 1
            return k, 0
        return None

    def _melhores_conhecidas(self) -> np.ndarray:
        m = np.zeros(self.K, bool)
        for r in range(len(self.degraus) - 1, -1, -1):
            comp = self.completou[r]
            if comp:
                ks = np.fromiter(comp.keys(), dtype=np.int64)
                vals = np.full(self.K, np.nan)
                vals[ks] = [comp[int(k)] for k in ks]
                m[_ordem_desc(vals, ks)[: self.n_final]] = True
                return m
        return m

    def alocar(self, obs: Observacao) -> np.ndarray:
        g, c, r = obs.acumulado(0)
        met = self._metrica(g, c)
        if self.decisao == "madura":
            gm, cm, rm = obs.acumulado(self.atraso)
            metm = self._metrica(gm, cm)
        if self.explorando:
            for k in np.flatnonzero(self.status == self.RODANDO):
                if met[k] >= self.degraus[self.alvo[k]]:
                    if self.decisao == "parcial":
                        self._reportar(int(k), float(_valor_roi(g[k:k + 1], r[k:k + 1])[0]))
                    else:
                        self.status[k] = self.PENDENTE
            if self.decisao == "madura":
                for k in np.flatnonzero(self.status == self.PENDENTE):
                    if metm[k] >= self.degraus[self.alvo[k]]:
                        self._reportar(int(k), float(_valor_roi(gm[k:k + 1], rm[k:k + 1])[0]))
            while len(self.producao) < self.n_topo and (self.status == self.RODANDO).sum() < self.n_slots:
                job = self._proximo_job()
                if job is None:
                    break
                k, rung = job
                self.status[k] = self.RODANDO
                self.alvo[k] = rung
            sem_trabalho = not (self.status == self.RODANDO).any() and not (self.status == self.PENDENTE).any()
            if len(self.producao) >= self.n_topo or sem_trabalho:
                self.explorando = False
                self.t_fim = obs.t
                if self.producao:  # seleção final: n_final melhores do último rung
                    topo = self.completou[len(self.degraus) - 1]
                    ks = np.asarray(self.producao, dtype=np.int64)
                    vals = np.full(self.K, np.nan)
                    vals[ks] = [topo[int(k)] for k in ks]
                    self.producao = [int(k) for k in _ordem_desc(vals, ks)[: self.n_final]]
        prod = np.zeros(self.K, bool)
        prod[self.producao] = True
        if self.explorando:
            ativos = (self.status == self.RODANDO) | prod
            if not ativos.any():
                ativos = self._melhores_conhecidas()
            if not ativos.any():
                ativos = self.status == self.PENDENTE
        else:
            ativos = prod if prod.any() else self._melhores_conhecidas()
        if not ativos.any():
            ativos = np.ones(self.K, bool)
        a = inteirizar(ativos.astype(float), self.B, self.m)
        self._ultima = a
        return a

    def promovidas(self) -> np.ndarray:
        if self.producao:
            m = np.zeros(self.K, bool)
            m[self.producao] = True
            return m
        return self._melhores_conhecidas()

    def extras(self) -> dict:
        return {"concluiu": not self.explorando, "t_fim_exploracao": self.t_fim,
                "n_producao": len(self.producao), "promocoes": self.promocoes}


class ThompsonTopN(_Base):
    """EXTENSÃO. Thompson top-n gaussiano sobre v (receita por R$): aloca ∝ P(célula no top-n)."""

    def __init__(self, n_top: int = 4, decisao: str = "parcial", atraso_assumido: int = 0,
                 m0: float = 1.0, tau0: float = 1.0, n_amostras: int = 128, nome: str | None = None):
        assert decisao in _DECISOES
        self.n_top, self.decisao, self.atraso = n_top, decisao, atraso_assumido
        self.m0, self.tau0, self.M = m0, tau0, n_amostras
        self.nome = nome or f"thompson_{decisao}"

    def alocar(self, obs: Observacao) -> np.ndarray:
        n = obs.t if self.decisao == "parcial" else max(0, obs.t - self.atraso)
        if n == 0:
            a = inteirizar(np.ones(self.K), self.B, self.m)
            self._ultima = a
            return a
        unidade = self.B / self.K
        G = obs.gasto[:n].astype(float)
        Rr = obs.receita[:n].astype(float)
        u = G.sum(0) / unidade
        vhat = np.where(u > 0, Rr.sum(0) / np.where(G.sum(0) > 0, G.sum(0), 1), 0.0)
        with np.errstate(divide="ignore", invalid="ignore"):
            y = np.where(G > 0, Rr / np.where(G > 0, G, 1), np.nan)
        w = G / unidade
        res = np.where(G > 0, w * (y - vhat) ** 2, 0.0)
        gl = max(1.0, (G > 0).sum() - (u > 0).sum())
        s2 = max(0.01, float(res.sum() / gl))
        prec = 1 / self.tau0 ** 2 + u / s2
        media = (self.m0 / self.tau0 ** 2 + vhat * u / s2) / prec
        amostras = media + self.rng.standard_normal((self.M, self.K)) / np.sqrt(prec)
        top = np.argpartition(-amostras, self.n_top - 1, axis=1)[:, : self.n_top]
        prob = np.bincount(top.ravel(), minlength=self.K) / self.M
        a = inteirizar(prob, self.B, self.m)
        self._ultima = a
        return a


class Oraculo(_Base):
    """Sabe v(t) e cap verdadeiros. Resolve, por regime, o MILP exato do problema sem
    interferência: max Σ (v−1)·p1 + (v·beta−1)·p2, Σ = B, célula ativa >= mínimo.
    Com interferência > 0 vira ORÁCULO APROXIMADO (ignora canibalização; regret pode ser < 0)."""

    nome = "oraculo"

    def __init__(self, cen: CenarioRealizado):
        self.cen = cen
        self._cache: dict[int, np.ndarray] = {}

    def _resolver(self, regime: int) -> np.ndarray:
        p = self.cen.params
        K = p.K
        B = p.orcamento_ciclo_micros / MICROS
        mn = p.minimo_celula_micros / MICROS
        v = self.cen.v[regime]
        c = -np.concatenate([v - 1, v * p.beta_saturacao - 1, np.zeros(K)])
        I, Z = np.eye(K), np.zeros((K, K))
        A = np.vstack([
            np.concatenate([np.ones(K), np.ones(K), np.zeros(K)])[None, :],
            np.hstack([I, I, -mn * I]),
            np.hstack([I, I, -B * I]),
        ])
        lo = np.concatenate([[B], np.zeros(K), np.full(K, -np.inf)])
        hi = np.concatenate([[B], np.full(K, np.inf), np.zeros(K)])
        res = milp(c, constraints=LinearConstraint(A, lo, hi),
                   bounds=Bounds(np.zeros(3 * K), np.concatenate([self.cen.cap_brl, np.full(K, B), np.ones(K)])),
                   integrality=np.concatenate([np.zeros(2 * K), np.ones(K)]))
        if not res.success:
            raise RuntimeError(f"oráculo MILP falhou: {res.message}")
        s = res.x[:K] + res.x[K:2 * K]
        ativo = res.x[2 * K:] > 0.5
        micros = np.where(ativo, np.maximum(np.rint(s * MICROS), p.minimo_celula_micros), 0).astype(np.int64)
        dif = p.orcamento_ciclo_micros - int(micros.sum())
        micros[int(np.argmax(micros))] += dif
        return micros

    def alocar(self, obs: Observacao) -> np.ndarray:
        reg = self.cen.regime(obs.t)
        if reg not in self._cache:
            self._cache[reg] = self._resolver(reg)
        a = self._cache[reg].copy()
        self._ultima = a
        return a

    def promovidas(self) -> np.ndarray:
        return self._ultima > self.B / self.K if self._ultima is not None else np.zeros(self.K, bool)
