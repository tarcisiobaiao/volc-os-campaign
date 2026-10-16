"""Simulador de ciclos de alocação SINTÉTICA e métricas por execução.

Fronteira de dinheiro (documentada e testada):
- ``alocacao``/``gasto``, ``receita_final`` e ``receita_reportada`` são ``np.int64`` em
  micros (BRL sintético). Receita é arredondada ao CENTAVO (10.000 micros), como no
  dado real.
- ``contribuicao_esperada`` (float64, BRL) é métrica interna de simulação para regret
  e oráculo; nunca é registro de alocação.

Ruído com números aleatórios comuns (CRN): cada (ciclo, célula) tem uniformes fixos
por seed, transformados por CDF inversa (Poisson de cliques, Poisson de eventos
monetizados, Gamma do valor somado). Políticas diferentes na mesma seed enfrentam o
"mesmo acaso" — as diferenças pareadas por seed ficam menos ruidosas.

Não há I/O, rede nem caminho para mutação real: a "alocação" é um vetor numpy.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
from scipy import special, stats

from volc_dil.swarm.cenario import MICROS, MICROS_POR_CENTAVO, CenarioRealizado

_EPS_U = 1e-12


class ViolacaoOrcamento(RuntimeError):
    """Política devolveu alocação fora do contrato (soma ≠ orçamento, abaixo do mínimo, float...)."""


def inteirizar(pesos: np.ndarray, orcamento: int, minimo: int) -> np.ndarray:
    """Converte pesos não negativos em alocação int64 em micros.

    Contrato: soma == ``orcamento``; cada célula recebe 0 ou >= ``minimo``. Células cujo
    alvo proporcional fica abaixo do mínimo são zeradas uma a uma (a menor primeiro) e o
    orçamento é redistribuído entre as restantes. Arredondamento por maior resto,
    determinístico (empate -> menor índice).
    """
    if not isinstance(orcamento, int) or not isinstance(minimo, int):
        raise TypeError("orçamento e mínimo em micros int")
    w = np.maximum(np.nan_to_num(np.asarray(pesos, dtype=float), nan=0.0), 0.0)
    if w.sum() <= 0:
        w = np.ones_like(w)
    ativo = w > 0
    while True:
        alvo = np.where(ativo, w, 0.0)
        alvo = alvo / alvo.sum() * orcamento
        baixo = ativo & (alvo < minimo)
        if not baixo.any():
            break
        idx = int(np.argmin(np.where(baixo, alvo, np.inf)))
        ativo[idx] = False
        if not ativo.any():  # impossível se orcamento >= minimo; guarda defensiva
            ativo[int(np.argmax(w))] = True
            alvo = np.where(ativo, float(orcamento), 0.0)
            break
    base = np.floor(alvo).astype(np.int64)
    resto = orcamento - int(base.sum())
    if resto:
        frac = np.where(ativo, alvo - base, -1.0)
        ordem = np.lexsort((np.arange(w.size), -frac))
        base[ordem[:resto]] += 1
    return base


@dataclass
class Observacao:
    """O que uma política enxerga no início do ciclo ``t`` (só o passado, só o reportado)."""

    t: int
    gasto: np.ndarray        # (t, K) int64 micros
    cliques: np.ndarray      # (t, K) int64
    receita: np.ndarray      # (t, K) int64 micros — receita REPORTADA até agora (parcial se imatura)
    orcamento: int
    minimo: int
    K: int

    def acumulado(self, idade_minima: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Somas por célula das linhas com idade >= idade_minima (idade da linha t' = t−1−t')."""
        n = max(0, self.t - idade_minima)
        return (self.gasto[:n].sum(axis=0), self.cliques[:n].sum(axis=0), self.receita[:n].sum(axis=0))


class Politica(Protocol):
    nome: str

    def reiniciar(self, K: int, T: int, orcamento: int, minimo: int, rng: np.random.Generator) -> None: ...

    def alocar(self, obs: Observacao) -> np.ndarray: ...

    def promovidas(self) -> np.ndarray: ...


@dataclass
class ResultadoExecucao:
    nome: str
    alocacao: np.ndarray            # (T, K) int64 micros
    cliques: np.ndarray             # (T, K) int64
    receita_final: np.ndarray       # (T, K) int64 micros (madura)
    contribuicao_esperada: np.ndarray  # (T,) float BRL — métrica de simulação
    promovidas: np.ndarray          # (K,) bool
    tempo_s: float
    extras: dict = field(default_factory=dict)


def validar_alocacao(a: object, K: int, orcamento: int, minimo: int) -> np.ndarray:
    if not isinstance(a, np.ndarray) or a.dtype != np.int64:
        raise ViolacaoOrcamento("alocação precisa ser np.ndarray int64 em micros (sem float)")
    if a.shape != (K,):
        raise ViolacaoOrcamento(f"shape {a.shape} != ({K},)")
    if (a < 0).any():
        raise ViolacaoOrcamento("alocação negativa")
    if int(a.sum()) != orcamento:
        raise ViolacaoOrcamento(f"soma {int(a.sum())} != orçamento {orcamento}")
    if ((a > 0) & (a < minimo)).any():
        raise ViolacaoOrcamento("célula ativa abaixo do mínimo")
    return a


def receita_reportada(cen: CenarioRealizado, receita_final: np.ndarray, t: int) -> np.ndarray:
    """Receita reportada no início do ciclo t para as linhas 0..t−1 (piso ao centavo)."""
    if t == 0:
        return receita_final[:0]
    idade = (t - 1 - np.arange(t))[:, None]
    f = cen.fracao_maturada(idade)
    cent = receita_final[:t] // MICROS_POR_CENTAVO
    return (np.floor(cent * f + 1e-9).astype(np.int64)) * MICROS_POR_CENTAVO


def simular(cen: CenarioRealizado, politica: Politica, rng_politica: np.random.Generator) -> ResultadoExecucao:
    p = cen.params
    K, T, B, m = p.K, p.T, p.orcamento_ciclo_micros, p.minimo_celula_micros
    aloc = np.zeros((T, K), dtype=np.int64)
    cliq = np.zeros((T, K), dtype=np.int64)
    rec = np.zeros((T, K), dtype=np.int64)
    contrib = np.zeros(T, dtype=float)
    U = np.clip(cen.uniformes, _EPS_U, 1 - _EPS_U)
    cv2 = p.cv_evento ** 2
    t0 = time.perf_counter()
    politica.reiniciar(K, T, B, m, rng_politica)
    for t in range(T):
        obs = Observacao(t=t, gasto=aloc[:t], cliques=cliq[:t], receita=receita_reportada(cen, rec, t),
                         orcamento=B, minimo=m, K=K)
        a = validar_alocacao(politica.alocar(obs), K, B, m)
        aloc[t] = a
        esperada = cen.receita_esperada_brl(t, a)
        contrib[t] = float(esperada.sum() - a.sum() / MICROS)
        gasto_brl = a / MICROS
        cliq[t] = stats.poisson.ppf(U[t, :, 0], gasto_brl / p.cpc_brl).astype(np.int64)
        eventos = stats.poisson.ppf(U[t, :, 1], esperada / p.valor_evento_brl)
        valor = np.zeros(K)
        pos = eventos > 0
        if pos.any():
            valor[pos] = p.valor_evento_brl * cv2 * special.gammaincinv(eventos[pos] / cv2, U[t, pos, 2])
        rec[t] = np.rint(valor * 100).astype(np.int64) * MICROS_POR_CENTAVO
    tempo = time.perf_counter() - t0
    return ResultadoExecucao(nome=politica.nome, alocacao=aloc, cliques=cliq, receita_final=rec,
                             contribuicao_esperada=contrib, promovidas=np.asarray(politica.promovidas(), bool),
                             tempo_s=tempo, extras=getattr(politica, "extras", lambda: {})())


def drawdown_maximo(fluxo: np.ndarray) -> int:
    """Maior queda do lucro acumulado a partir de um pico (pico inicial = 0). int micros."""
    acum = np.concatenate([[0], np.cumsum(fluxo)])
    pico = np.maximum.accumulate(acum)
    return int((pico - acum).max())


def excesso_perdedoras_vs_oraculo(aloc: np.ndarray, aloc_oraculo: np.ndarray, perdedora: np.ndarray,
                                  orcamento: int) -> float:
    """PÓS-REGISTRO (exploratório, achado F2-01). Fração do orçamento gasta em células de
    contribuição <= 0 ALÉM do que o oráculo gastaria nelas: Σ max(0, a − a_oráculo)·perdedora / Σ B.

    Motivo: com orçamento forçado (Σ = B) e saturação, o ótimo também põe dinheiro em
    perdedoras; a métrica pré-registrada (fração absoluta) pune o ótimo. Esta mede só o excesso.
    O oráculo tem 0 por construção. Com interferência o oráculo é aproximado (documentado)."""
    excesso = np.maximum(aloc.astype(np.int64) - aloc_oraculo.astype(np.int64), 0) * perdedora
    return float(excesso.sum() / (orcamento * aloc.shape[0]))


def metricas_execucao(res: ResultadoExecucao, cen: CenarioRealizado, contrib_oraculo: np.ndarray,
                      janela_final: int = 5, aloc_oraculo: np.ndarray | None = None) -> dict:
    p = cen.params
    B, K, T = p.orcamento_ciclo_micros, p.K, p.T
    a = res.alocacao
    fluxo = res.receita_final.sum(axis=1) - a.sum(axis=1)
    reg_final = cen.regime(T - 1)
    v_final = cen.v[reg_final]
    topk_final = cen.top_k_verdadeiro(reg_final)
    topk_ini = cen.top_k_verdadeiro(0)
    prom = res.promovidas
    podadas = a[-1] == 0
    perdedora_t = np.vstack([cen.v_em(t) <= 1.0 for t in range(T)])
    jan = slice(T - janela_final, T)
    frac = a[jan].astype(float) / B
    falsos = prom & ((v_final <= 1.0) | ~topk_final)
    n_prom = int(prom.sum())
    pos_registro = {}
    if aloc_oraculo is not None:
        pos_registro = {
            "excesso_perdedoras_vs_oraculo_final": excesso_perdedoras_vs_oraculo(a[jan], aloc_oraculo[jan], perdedora_t[jan], B),
            "excesso_perdedoras_vs_oraculo_total": excesso_perdedoras_vs_oraculo(a, aloc_oraculo, perdedora_t, B),
        }
    return {
        **pos_registro,
        "lucro_realizado_micros": int(fluxo.sum()),
        "lucro_esperado_brl": float(res.contribuicao_esperada.sum()),
        "regret_brl": float(contrib_oraculo.sum() - res.contribuicao_esperada.sum()),
        "drawdown_micros": drawdown_maximo(fluxo),
        "hhi_medio": float((((a.astype(float) / B) ** 2).sum(axis=1)).mean()),
        "turnover_medio": float((0.5 * np.abs(np.diff(a, axis=0)).sum(axis=1) / B).mean()) if T > 1 else 0.0,
        "frac_orcamento_perdedoras_final": float((frac * perdedora_t[jan]).sum() / frac.sum()),
        "n_promovidas": n_prom,
        "falsos_vencedores": int(falsos.sum()),
        "taxa_falso_vencedor": float(falsos.sum() / n_prom) if n_prom else float("nan"),
        "promovidas_negativas": int((prom & (v_final <= 1.0)).sum()),
        "podadas_incorretas": int((topk_final & podadas).sum()),
        "podadas_incorretas_regime0": int((topk_ini & podadas).sum()) if cen.t_troca < T else int((topk_final & podadas).sum()),
        "acertou_melhor": bool(prom[int(np.argmax(v_final))]),
        "tempo_s": res.tempo_s,
        **{f"extra_{k}": v for k, v in res.extras.items()},
    }
