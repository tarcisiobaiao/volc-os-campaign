"""Painéis as_of vetorizados: equivalência com o consumidor de referência, ausência e determinismo."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from volc_dil.fundacao import modelos as M
from volc_dil.fundacao.simulador import iso, simular, visao_as_of


def _painel_referencia(registros, fonte, metrica, tab, as_of_epoch, relogio):
    v = visao_as_of(registros, iso(datetime.fromtimestamp(as_of_epoch, timezone.utc)), relogio=relogio)
    Q = np.full(tab.forma, np.nan)
    ie = {e: i for i, e in enumerate(tab.entidades)}
    idd = {d: i for i, d in enumerate(tab.dias)}
    for r in v.values():
        if (r.fonte == fonte and r.metrica == metrica and r.entidade_tipo == "campaign" and not r.dimensoes
                and r.entidade in ie and tuple(r.grao) == ("campaign", "day")):
            Q[ie[r.entidade], idd[r.janela_inicio]] = r.valor
    return Q


@pytest.mark.parametrize("cenario,fonte,metrica", [
    ("estavel", "joinads", "revenue"),
    ("vazamento_tentado", "google_ads", "cost"),
    ("identidade_trocada", "joinads", "revenue"),
    ("fonte_fora_do_ar", "google_ads", "clicks"),
])
@pytest.mark.parametrize("relogio", ["available_at", "observed_at"])
def test_painel_equivale_a_visao_as_of(cenario, fonte, metrica, relogio):
    s = simular(cenario, 7, n_campanhas=6, n_dias=8)
    m = s.mundo
    tab = M.TabelaVersoes.de_registros(s.leituras.registros, fonte=fonte, metrica=metrica,
                                       entidades=M.ids_campanhas(m), dias=M.dias_iso(m))
    for k in range(0, 12, 2):
        for h in (6.5, 12.0, 23.5):
            ao = M.instante_local(m, k, h)
            P = tab.painel(ao, relogio=relogio)
            Q = _painel_referencia(s.leituras.registros, fonte, metrica, tab, ao, relogio)
            assert np.array_equal(np.isnan(P), np.isnan(Q)), (k, h)
            assert np.array_equal(np.nan_to_num(P), np.nan_to_num(Q)), (k, h)


def test_ausencia_fica_nan_e_nao_zero():
    s = simular("fonte_fora_do_ar", 3, n_campanhas=6, n_dias=10)
    tab = M.TabelaVersoes.de_registros(s.leituras.registros, fonte="joinads", metrica="revenue",
                                       entidades=M.ids_campanhas(s.mundo), dias=M.dias_iso(s.mundo))
    assert tab.n_sem_valor > 0
    P = tab.painel(M.instante_local(s.mundo, 5, 12))
    assert np.isnan(P).any()
    assert not np.any(P[np.isfinite(P)] < 0)


def test_relogio_observed_vaza_futuro_em_vazamento_tentado():
    """Cortar por observed_at mostra o valor final antes de ele existir (o vazamento que o contrato proíbe)."""
    s = simular("vazamento_tentado", 5, n_campanhas=6, n_dias=8)
    m = s.mundo
    tab = M.TabelaVersoes.de_registros(s.leituras.registros, fonte="google_ads", metrica="cost",
                                       entidades=M.ids_campanhas(m), dias=M.dias_iso(m))
    ao = M.instante_local(m, 3, 0) + 60  # meia-noite do dia 3: o dia 2 acabou de fechar
    disp = tab.painel(ao, relogio="available_at")[:, 2]
    obs = tab.painel(ao, relogio="observed_at")[:, 2]
    final = tab.final()[:, 2]
    assert np.mean(obs == final) > np.mean(disp == final)


def test_determinismo_e_multiversao_d0():
    a = simular("custo_d0_multiversao", 11, n_campanhas=5, n_dias=6)
    b = simular("custo_d0_multiversao", 11, n_campanhas=5, n_dias=6)
    ta = M.TabelaVersoes.de_registros(a.leituras.registros, fonte="google_ads", metrica="cost")
    tb = M.TabelaVersoes.de_registros(b.leituras.registros, fonte="google_ads", metrica="cost")
    assert np.array_equal(ta.final(), tb.final(), equal_nan=True)
    nv = ta.n_versoes_distintas()
    assert nv.max() >= 10  # 16 runs D0/dia => muitas versões distintas por campanha-dia
