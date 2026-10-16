"""Painéis as_of vetorizados: equivalência com o consumidor de referência, ausência e determinismo."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from volc_dil.fundacao import modelos as M
from volc_dil.fundacao.modelos.dados import MATURIDADES
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


def _versao(base, *, valor, observed, available, obs_id, maturidade):
    from dataclasses import replace

    return replace(base, valor=valor, status="observed", observed_at=observed, available_at=available,
                   ingested_at=available, obs_id=obs_id, maturidade=maturidade, tipo_leitura="releitura")


def test_preliminar_atrasada_nao_substitui_a_final_r2_g13_f4():
    """Mata o mutante F4 (R2/G13): versão vigente = medição mais recente (observed_at), NÃO a última a
    chegar. Uma preliminar medida antes e entregue depois da final não pode vencer."""
    s = simular("estavel", 7, n_campanhas=2, n_dias=3)
    base = next(r for r in s.leituras.registros if r.fonte == "joinads" and r.metrica == "revenue"
                and r.entidade_tipo == "campaign" and not r.dimensoes)
    final = _versao(base, valor=1_000_000, observed="2026-08-06T10:00:00+00:00",
                    available="2026-08-06T10:05:00+00:00", obs_id="obs-final", maturidade="final")
    prelim = _versao(base, valor=700_000, observed="2026-08-05T10:00:00+00:00",
                     available="2026-08-07T10:00:00+00:00", obs_id="obs-prelim", maturidade="preliminar")
    regs = [final, prelim]
    tab = M.TabelaVersoes.de_registros(regs, fonte="joinads", metrica="revenue")
    depois = M.epoch("2026-08-08T00:00:00+00:00")
    assert tab.painel(depois)[0, 0] == 1_000_000
    assert tab.painel_maturidade(depois)[0, 0] == MATURIDADES.index("final")
    entre = M.epoch("2026-08-06T12:00:00+00:00")  # só a final chegou
    assert tab.painel(entre)[0, 0] == 1_000_000
    antes = M.epoch("2026-08-06T10:01:00+00:00")  # nada disponível ainda
    assert np.isnan(tab.painel(antes)[0, 0])
    # e coincide com o consumidor de referência
    ref = visao_as_of(regs, "2026-08-08T00:00:00+00:00")
    assert [r.valor for r in ref.values()] == [1_000_000]


def test_equivalencia_com_coletas_atrasadas_e_recuperacao_tardia():
    """Cenário com 10% de coletas atrasadas (recuperação tardia): painel = visao_as_of em todos os cortes."""
    s = simular("atraso_receita_longo", 3, n_campanhas=6, n_dias=10)
    m = s.mundo
    tab = M.TabelaVersoes.de_registros(s.leituras.registros, fonte="joinads", metrica="revenue",
                                       entidades=M.ids_campanhas(m), dias=M.dias_iso(m))
    atrasadas = [r for r in s.leituras.registros if r.status == "late" and r.fonte == "joinads"]
    assert atrasadas, "o cenário precisa ter coletas atrasadas para o teste ter poder"
    for k in range(1, 18):
        ao = M.instante_local(m, k, 11.0)
        P = tab.painel(ao)
        Q = _painel_referencia(s.leituras.registros, "joinads", "revenue", tab, ao, "available_at")
        assert np.array_equal(np.isnan(P), np.isnan(Q)) and np.array_equal(np.nan_to_num(P), np.nan_to_num(Q)), k
