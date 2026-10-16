"""Gerador de cenários SINTÉTICOS de swarm (seed -> cenário determinístico).

Cada célula é um rótulo sintético canal × ângulo × objetivo × device. Os dados
reais do VOLC só deram FORMA ao gerador (receita zero-inflada e arredondada ao
centavo, receita que matura com atraso de alguns ciclos, ligação só por
célula-ciclo, gasto sem variação exógena); nenhum número real é parâmetro.

Modelo econômico por célula k e ciclo t (valores ESPERADOS, float, só simulação):

    receita_esperada_k(s) = v_k(t) · [min(s, cap_k) + beta · max(s − cap_k, 0)]
                            · (1 − rho · gasto_outras_mesmo_canal / B)
    contribuicao_k(s)     = receita_esperada_k(s) − s

- ``v_k`` = receita por R$ gasto (margem de contribuição = v_k − 1). Distribuição
  log-t com cauda: maioria abaixo de 1 (contribuição negativa/perto de zero), poucas
  vencedoras.
- ``cap_k`` = capacidade de escala (saturação): acima dela cada R$ rende só ``beta``.
- ``rho`` = interferência/canibalização entre células do mesmo canal.
- não estacionariedade: em ``troca_vencedora_em·T`` a melhor célula cai e uma
  perdedora assume o valor antigo da melhor.
- maturação: do ciclo t, na idade a (ciclos depois), é reportada a fração
  ``f_k(a) = phi0_k + (1 − phi0_k)·min(1, a/D)`` da receita final; D=0 -> tudo no ato.
"""
from __future__ import annotations

import itertools
from dataclasses import asdict, dataclass, field

import numpy as np

MICROS = 1_000_000
MICROS_POR_CENTAVO = 10_000

CANAIS = ("canal_a", "canal_b", "canal_c", "canal_d", "canal_e", "canal_f", "canal_g", "canal_h")
ANGULOS = ("angulo_1", "angulo_2", "angulo_3")
OBJETIVOS = ("obj_x", "obj_y", "obj_z")
DEVICES = ("mobile", "desktop")

MODOS_MATURACAO = ("uniforme", "por_canal", "vencedoras_lentas")


@dataclass(frozen=True)
class ParametrosCenario:
    """Parâmetros de um cenário. Todos são PARÂMETROS a variar, não defaults operacionais."""

    nome: str = "base"
    K: int = 16
    T: int = 30
    # Dinheiro de configuração em micros inteiros (BRL sintético).
    orcamento_ciclo_micros: int = 960 * MICROS
    minimo_celula_micros: int = 10 * MICROS
    # Parâmetros de simulação (float por natureza: taxas, médias, desvios).
    cpc_brl: float = 2.0
    valor_evento_brl: float = 8.0
    cv_evento: float = 1.0
    mu_log_v: float = -0.35
    sigma_log_v: float = 0.45
    df_cauda: float = 3.0
    cap_mult_mediana: float = 2.5
    cap_sigma: float = 0.5
    beta_saturacao: float = 0.25
    atraso_ciclos: int = 3
    fracao_inicial: float = 0.5
    fracao_inicial_lenta: float = 0.1
    modo_maturacao: str = "uniforme"
    troca_vencedora_em: float | None = None
    fator_queda_vencedora: float = 0.6
    interferencia: float = 0.0
    top_k: int = 4

    def __post_init__(self) -> None:
        for nome in ("orcamento_ciclo_micros", "minimo_celula_micros"):
            v = getattr(self, nome)
            if not isinstance(v, int) or isinstance(v, bool):
                raise TypeError(f"{nome} precisa ser int em micros (dinheiro não entra como float)")
        if self.minimo_celula_micros * self.K > self.orcamento_ciclo_micros:
            raise ValueError("orçamento total não cobre o mínimo de todas as células")
        if self.modo_maturacao not in MODOS_MATURACAO:
            raise ValueError(f"modo_maturacao inválido: {self.modo_maturacao}")
        if self.atraso_ciclos < 0:
            raise ValueError("atraso_ciclos < 0")
        if not (0 < self.top_k <= self.K):
            raise ValueError("top_k fora de (0, K]")
        if self.K > len(CANAIS) * len(ANGULOS) * len(OBJETIVOS) * len(DEVICES):
            raise ValueError("K maior que o produto de rótulos disponíveis")

    def como_dict(self) -> dict:
        return asdict(self)


@dataclass
class CenarioRealizado:
    """Cenário sorteado (verdade do simulador; políticas NUNCA leem isto, só o oráculo)."""

    params: ParametrosCenario
    seed: int
    rotulos: list[dict]
    grupo: np.ndarray            # (K,) int — canal (para interferência e maturação por canal)
    v: np.ndarray                # (2, K) float — v por regime (0 antes da troca, 1 depois)
    cap_brl: np.ndarray          # (K,) float
    phi0: np.ndarray             # (K,) float
    t_troca: int                 # ciclo em que o regime 1 começa (T se não houver troca)
    uniformes: np.ndarray = field(repr=False)  # (T, K, 3) números comuns aleatórios (CRN)

    @property
    def K(self) -> int:
        return self.params.K

    @property
    def T(self) -> int:
        return self.params.T

    def regime(self, t: int) -> int:
        return 0 if t < self.t_troca else 1

    def v_em(self, t: int) -> np.ndarray:
        return self.v[self.regime(t)]

    def fracao_maturada(self, idade: np.ndarray) -> np.ndarray:
        """f_k(a) para matriz de idades (n, 1) ou (n, K) -> (n, K)."""
        D = self.params.atraso_ciclos
        if D == 0:
            return np.ones(np.broadcast_shapes(np.shape(idade), (self.K,)))
        prog = np.minimum(1.0, np.asarray(idade, dtype=float) / D)
        return self.phi0 + (1.0 - self.phi0) * prog

    def receita_esperada_brl(self, t: int, gasto_micros: np.ndarray) -> np.ndarray:
        p = self.params
        s = np.asarray(gasto_micros, dtype=float) / MICROS
        v = self.v_em(t)
        dentro = np.minimum(s, self.cap_brl)
        fora = np.maximum(s - self.cap_brl, 0.0)
        bruto = v * (dentro + p.beta_saturacao * fora)
        if p.interferencia > 0:
            B = p.orcamento_ciclo_micros / MICROS
            por_grupo = np.bincount(self.grupo, weights=s, minlength=int(self.grupo.max()) + 1)
            outras = por_grupo[self.grupo] - s
            bruto = bruto * np.clip(1.0 - p.interferencia * outras / B, 0.0, 1.0)
        return bruto

    def contribuicao_esperada_brl(self, t: int, gasto_micros: np.ndarray) -> float:
        s = np.asarray(gasto_micros, dtype=float) / MICROS
        return float(self.receita_esperada_brl(t, gasto_micros).sum() - s.sum())

    def top_k_verdadeiro(self, regime: int) -> np.ndarray:
        """Máscara das top-k células por v no regime, SÓ entre as de contribuição positiva (v > 1).

        Podar uma perdedora nunca é "poda incorreta"; se houver menos de k vencedoras, o
        conjunto tem menos de k células (empate: menor índice)."""
        v = self.v[regime]
        ordem = np.lexsort((np.arange(self.K), -v))
        ordem = ordem[v[ordem] > 1.0][: self.params.top_k]
        m = np.zeros(self.K, dtype=bool)
        m[ordem] = True
        return m

    def resumo(self) -> dict:
        return {
            "seed": self.seed,
            "n_vencedoras_regime0": int((self.v[0] > 1).sum()),
            "n_vencedoras_regime1": int((self.v[1] > 1).sum()),
            "t_troca": self.t_troca,
        }


def _rotulos(K: int) -> tuple[list[dict], np.ndarray]:
    n_canais = max(1, min(len(CANAIS), int(np.ceil(K / (len(ANGULOS) * len(OBJETIVOS) * len(DEVICES))))))
    n_canais = max(n_canais, 2) if K >= 2 else 1
    produto = list(itertools.product(range(n_canais), range(len(ANGULOS)), range(len(OBJETIVOS)),
                                     range(len(DEVICES))))
    # Intercala canais para que K pequeno ainda tenha mais de um canal.
    produto.sort(key=lambda x: (x[1], x[2], x[3], x[0]))
    escolhidos = produto[:K]
    rot = [{"canal": CANAIS[c], "angulo": ANGULOS[a], "objetivo": OBJETIVOS[o], "device": DEVICES[d]}
           for c, a, o, d in escolhidos]
    grupo = np.array([c for c, _, _, _ in escolhidos], dtype=np.int64)
    return rot, grupo


def gerar_cenario(params: ParametrosCenario, seed: int) -> CenarioRealizado:
    """Sorteia um cenário. Mesma (params, seed) -> mesmo cenário, bit a bit."""
    ss = np.random.SeedSequence([int(seed), 0x5A4B])
    r_val, r_ruido = (np.random.default_rng(s) for s in ss.spawn(2))
    K, T = params.K, params.T
    rot, grupo = _rotulos(K)

    t_cauda = r_val.standard_t(params.df_cauda, size=K)
    v0 = np.exp(params.mu_log_v + params.sigma_log_v * t_cauda)
    v0 = np.clip(v0, 0.02, 6.0)
    B_brl = params.orcamento_ciclo_micros / MICROS
    cap = (B_brl / K) * params.cap_mult_mediana * np.exp(params.cap_sigma * r_val.standard_normal(K))
    cap = np.maximum(cap, 2 * params.minimo_celula_micros / MICROS)

    v1 = v0.copy()
    if params.troca_vencedora_em is not None:
        t_troca = int(round(params.troca_vencedora_em * T))
        melhor = int(np.argmax(v0))
        perdedoras = np.flatnonzero((v0 <= 1.0) & (np.arange(K) != melhor))
        if perdedoras.size == 0:
            perdedoras = np.flatnonzero(np.arange(K) != melhor)
        nova = int(r_val.choice(perdedoras))
        v1[melhor] = v0[melhor] * params.fator_queda_vencedora
        v1[nova] = v0[melhor]
    else:
        t_troca = T
        # consome o mesmo número de sorteios para manter a estrutura de seeds estável
        r_val.integers(0, 2)

    if params.modo_maturacao == "uniforme":
        phi0 = np.full(K, params.fracao_inicial)
    elif params.modo_maturacao == "por_canal":
        phi0 = np.where(grupo % 2 == 0, params.fracao_inicial, params.fracao_inicial_lenta)
    else:  # vencedoras_lentas
        phi0 = np.where(v0 > 1.0, params.fracao_inicial_lenta, params.fracao_inicial)

    uniformes = r_ruido.random((T, K, 3))
    return CenarioRealizado(params=params, seed=int(seed), rotulos=rot, grupo=grupo,
                            v=np.vstack([v0, v1]), cap_brl=cap, phi0=phi0.astype(float),
                            t_troca=t_troca, uniformes=uniformes)
