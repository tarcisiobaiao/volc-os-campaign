"""Detecção de anomalia de VALOR, separada de LACUNA (ausência) e de ZERO IMPLAUSÍVEL.

Regra central (contrato da missão): ausência não é valor. Um ponto sem valor (``None``/NaN ou status
``missing``/``unavailable``/``unsupported``/``invalid``) vira ``Achado(tipo="lacuna")`` e fica FORA do
histórico dos detectores de valor — nunca entra como 0 (o anti-baseline ``nulo_como_zero`` existe só
para medir o estrago de fazer isso).

Detectores de valor (escore no ponto t usa só o histórico ANTERIOR, janela móvel, sem o próprio t):
- ``zscore``: (x - média) / desvio — baseline clássico, sensível ao próprio outlier no histórico;
- ``robusto_mad``: (x - mediana) / (1,4826·MAD);
- ``sazonal_robusto``: resíduo contra a mediana da MESMA fase nos ciclos anteriores (ex.: dia da
  semana, período 7), escalado pelo MAD dos resíduos recentes.

``zero_implausivel``: zero com valor (status com valor) onde a contagem típica recente torna o zero
improvável sob Poisson (P(0 | λ) = e^{-λ} < ``p_max``). Pega o "zero falso" de fonte que devolve 0
para ausência (Google Ads MCP 0.0.4, coletor R3) — sem ler gabarito.
"""
from __future__ import annotations

import math
from typing import Any, Optional, Sequence

import numpy as np

from .base import Achado

STATUS_SEM_VALOR = frozenset({"missing", "unavailable", "unsupported", "invalid"})
METODOS_ANOMALIA = ("zscore", "robusto_mad", "sazonal_robusto")


def _valores(serie: Sequence[Any], status: Optional[Sequence[str]] = None) -> tuple[np.ndarray, np.ndarray]:
    x = np.array([np.nan if v is None else float(v) for v in serie], dtype=float)
    lac = ~np.isfinite(x)
    if status is not None:
        if len(status) != len(serie):
            raise ValueError("status e série com tamanhos diferentes")
        lac |= np.array([s in STATUS_SEM_VALOR for s in status], dtype=bool)
    return np.where(lac, np.nan, x), lac


def escores(x: np.ndarray, *, metodo: str, janela: int, periodo: int = 7, min_hist: int = 5) -> np.ndarray:
    """Escore por ponto (NaN onde não há histórico suficiente ou o ponto é lacuna)."""
    if metodo not in METODOS_ANOMALIA:
        raise ValueError(f"método desconhecido: {metodo}")
    T = x.size
    s = np.full(T, np.nan)
    if metodo == "sazonal_robusto":
        res = np.full(T, np.nan)
        for t in range(T):
            fase = x[t - periodo::-periodo][: max(1, janela // periodo)] if t >= periodo else np.array([])
            fase = fase[np.isfinite(fase)]
            if fase.size and np.isfinite(x[t]):
                res[t] = x[t] - np.median(fase)
        for t in range(T):
            h = res[max(0, t - janela):t]
            h = h[np.isfinite(h)]
            if h.size < min_hist or not np.isfinite(res[t]):
                continue
            mad = np.median(np.abs(h - np.median(h))) * 1.4826
            s[t] = (res[t] - np.median(h)) / mad if mad > 0 else np.nan
        return s
    for t in range(T):
        if not np.isfinite(x[t]):
            continue
        h = x[max(0, t - janela):t]
        h = h[np.isfinite(h)]
        if h.size < min_hist:
            continue
        if metodo == "zscore":
            sd = h.std(ddof=1)
            s[t] = (x[t] - h.mean()) / sd if sd > 0 else np.nan
        else:
            med = np.median(h)
            mad = np.median(np.abs(h - med)) * 1.4826
            s[t] = (x[t] - med) / mad if mad > 0 else np.nan
    return s


def detectar_anomalias(serie: Sequence[Any], *, metodo: str, limiar: float, janela: int,
                       status: Optional[Sequence[str]] = None, periodo: int = 7, bilateral: bool = True,
                       min_hist: int = 5) -> list[Achado]:
    """Achados por ponto: ``lacuna`` (sem valor) e ``anomalia_valor`` (|escore| > limiar)."""
    x, lac = _valores(serie, status)
    sc = escores(x, metodo=metodo, janela=janela, periodo=periodo, min_hist=min_hist)
    out: list[Achado] = []
    for t in range(x.size):
        if lac[t]:
            out.append(Achado("lacuna", True, "ausencia_explicita", indice=t,
                              detalhes={"status": None if status is None else status[t]}))
            continue
        v = sc[t]
        if np.isfinite(v) and ((abs(v) if bilateral else v) > limiar):
            out.append(Achado("anomalia_valor", True, metodo, indice=t, estatistica=float(v), limiar=limiar))
    return out


def nulo_como_zero(serie: Sequence[Any], *, limiar: float, janela: int, min_hist: int = 5) -> list[int]:
    """ANTI-BASELINE: troca ausência por 0 e roda z-score. Devolve índices alarmados (para medir o estrago)."""
    x = np.array([0.0 if v is None or not np.isfinite(float(v)) else float(v) for v in serie])
    sc = escores(x, metodo="zscore", janela=janela, min_hist=min_hist)
    return [int(t) for t in np.nonzero(np.isfinite(sc) & (np.abs(sc) > limiar))[0]]


def zero_implausivel(serie: Sequence[Any], *, janela: int, p_max: float, status: Optional[Sequence[str]] = None,
                     min_hist: int = 3) -> list[Achado]:
    """Zeros com valor cuja contagem típica (mediana dos ``janela`` valores anteriores com valor) torna
    P(0) = e^{-λ} < ``p_max``. Série deve ser CONTAGEM (ex.: cliques, impressões)."""
    if not 0 < p_max < 1:
        raise ValueError("p_max em (0, 1)")
    x, lac = _valores(serie, status)
    lam_min = -math.log(p_max)
    out: list[Achado] = []
    for t in range(x.size):
        if lac[t] or x[t] != 0:
            continue
        h = x[max(0, t - janela):t]
        h = h[np.isfinite(h)]
        if h.size < min_hist:
            continue
        lam = float(np.median(h))
        if lam > lam_min:
            out.append(Achado("zero_implausivel", True, "poisson_mediana", indice=t, estatistica=math.exp(-lam),
                              limiar=p_max, detalhes={"lambda": lam}))
    return out


def precisao_recall(alarmes: Sequence[int], verdade: Sequence[int]) -> dict[str, Any]:
    a, v = set(int(i) for i in alarmes), set(int(i) for i in verdade)
    tp = len(a & v)
    prec = tp / len(a) if a else None
    rec = tp / len(v) if v else None
    f1 = (2 * prec * rec / (prec + rec)) if prec and rec else (0.0 if (a and v) else None)
    return {"tp": tp, "fp": len(a - v), "fn": len(v - a), "precisao": prec, "recall": rec, "f1": f1}


__all__ = ["METODOS_ANOMALIA", "STATUS_SEM_VALOR", "detectar_anomalias", "escores", "nulo_como_zero",
           "precisao_recall", "zero_implausivel"]
