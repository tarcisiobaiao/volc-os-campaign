"""Simulator Lab — performance: 1 mês × 50 campanhas × horário (× 3 dispositivos) dentro do orçamento de tempo.

Orçamento de tempo X = 15 s (mundo + observador, mediana de 2 rodadas) na máquina da missão
(10 CPUs, OMP_NUM_THREADS=2). Medido ao escrever: ~0,3 s mundo + ~1,2 s observador.
Medição registrada em results/fundacao/simulador/PERFORMANCE.json (inclui escala_10x).
"""
from __future__ import annotations

import time

from volc_dil.fundacao.simulador import cenario, gerar_mundo, observar

ORCAMENTO_S = 15.0


def test_mes_50_campanhas_horario_dentro_do_orcamento():
    e = cenario("estavel")
    assert (e.mundo.n_campanhas, e.mundo.n_dias) == (50, 30)
    tempos = []
    for _ in range(2):
        t0 = time.perf_counter()
        m = gerar_mundo(e.mundo, 20261016)
        leit = observar(m, e.observador, cenario=e.nome)
        tempos.append(time.perf_counter() - t0)
    assert m.horario("impressoes").shape == (50, 30 * 24, 3)
    assert len(leit.registros) > 40_000
    assert sorted(tempos)[0] < ORCAMENTO_S, tempos
