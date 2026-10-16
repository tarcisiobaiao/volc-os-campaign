"""Regras puras de corte por rung (só numpy), conferidas contra o Optuna em sonda isolada.

``asha_parada_na_chegada`` reproduz o ``SuccessiveHalvingPruner`` do Optuna 5.0 (ASHA na
variante de PARADA: o trial é avaliado ao chegar ao rung contra todos que já chegaram;
se não estiver no top ``len//eta`` é parado para sempre; os primeiros ``eta−1`` passam se
forem o melhor até então). A política ``ASHA`` deste módulo usa a variante de PROMOÇÃO do
artigo (Li et al. 2018): trials param no rung e podem ser promovidos depois, quando houver
``>= eta`` concluídos e ele estiver no top ``len//eta``.
"""
from __future__ import annotations

import numpy as np


def asha_parada_na_chegada(valores: np.ndarray, eta: int) -> np.ndarray:
    """valores (N, R): valor do trial i ao chegar ao rung r, trials em sequência.
    Retorna o número de rungs alcançados por trial (R = completou)."""
    N, R = valores.shape
    competidores: list[list[float]] = [[] for _ in range(R)]
    alcancado = np.zeros(N, dtype=np.int64)
    for i in range(N):
        for r in range(R):
            competidores[r].append(float(valores[i, r]))
            if r == R - 1:
                alcancado[i] = R
                break
            ordenados = sorted(competidores[r])
            idx = len(ordenados) // eta - 1
            if idx == -1:
                idx = 0
            if valores[i, r] >= ordenados[-(idx + 1)]:
                continue
            alcancado[i] = r + 1
            break
    return alcancado
