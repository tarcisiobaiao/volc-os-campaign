"""Maturação: casos analíticos (CL, BF, fixo), guarda herdada, anti-futuro, monitor de regime, intradiário."""
from __future__ import annotations

import numpy as np
import pytest

from volc_dil.fundacao import modelos as M
from volc_dil.statlab.base import ResultadoInsuficiente
from volc_dil.statlab.maturacao import CenarioMaturacao, pmf_atraso_geometrica, simular_incrementos


def _tri(fatores, finais):
    """Triângulo determinístico: C[c, a] = final_c * f(a) (cumulativo)."""
    return np.outer(np.asarray(finais, float), np.asarray(fatores, float))


CFG = M.ConfigNowcast(janela_coortes=10, maturidade_minima=0.1, min_coortes=3)


def test_chain_ladder_exato_em_triangulo_deterministico():
    f = [0.2, 0.6, 0.9, 1.0]
    finais = np.linspace(100, 200, 20)
    tri = _tri(f, finais)
    for a in range(3):
        r = M.nowcast(tri, 19, 19 - a, CFG)
        assert r["status"] == "estimado"
        assert r["estimativa"] == pytest.approx(finais[19 - a], rel=1e-12)
        assert r["fator"] == pytest.approx(f[a], rel=1e-12)


def test_bornhuetter_ferguson_formula_e_prior():
    f = [0.25, 0.5, 1.0]
    tri = _tri(f, np.full(15, 100.0))
    tri[14, 0] = 40.0  # coorte recente com observação baixa
    r = M.nowcast(tri, 14, 14, CFG, metodo="bornhuetter_ferguson")
    # obs + (1 - m) * prior, prior = média dos finais maduros = 100
    assert r["estimativa"] == pytest.approx(40.0 + 0.75 * 100.0)
    cl = M.nowcast(tri, 14, 14, CFG)
    assert cl["estimativa"] == pytest.approx(160.0)


def test_fator_fixo_congelado_nao_se_atualiza():
    tri = _tri([0.5, 1.0], np.full(30, 100.0))
    fixo = M.fator_congelado(tri, 10, janela_coortes=5)
    tri2 = tri.copy()
    tri2[20:, 0] = 25.0  # regime novo: só 25% na idade 0
    r = M.nowcast(tri2, 29, 29, CFG, metodo="fator_fixo", fator_fixo=fixo)
    assert r["estimativa"] == pytest.approx(50.0)  # viés de -50%: o fixo não vê a mudança


def test_guarda_herdada_devolve_insuficiente():
    tri = _tri([0.01, 1.0], np.full(10, 100.0))
    r = M.nowcast(tri, 9, 9, M.ConfigNowcast(janela_coortes=5, maturidade_minima=0.05, min_coortes=3))
    assert isinstance(r, ResultadoInsuficiente) and r.motivo == "maturidade_abaixo_do_minimo"
    tri[9, 0] = np.nan
    r2 = M.nowcast(tri, 9, 9, CFG)
    assert isinstance(r2, ResultadoInsuficiente) and r2.motivo == "observacao_ausente"


def test_anti_futuro_celulas_alem_do_as_of_nao_entram():
    f = [0.5, 1.0]
    tri = _tri(f, np.full(12, 100.0))
    poluido = tri.copy()
    poluido[11, 1] = 1e9  # célula futura (11 + 1 > as_of = 11)
    poluido[10, 1] = 1e9  # célula futura para as_of = 10
    a = M.nowcast(tri, 10, 10, CFG)
    b = M.nowcast(poluido, 10, 10, CFG)
    assert a["estimativa"] == pytest.approx(b["estimativa"])


def test_monitor_detecta_mudanca_e_nowcast_recusa_ate_ter_base():
    rng = np.random.default_rng(0)
    C, A = 60, 4
    finais = 100 * rng.lognormal(0, 0.1, C)
    f_antigo = np.array([0.6, 0.85, 0.95, 0.99, 1.0])
    f_novo = np.array([0.3, 0.55, 0.8, 0.95, 1.0])
    fat = np.where(np.arange(C)[:, None] >= 40, f_novo[None, :], f_antigo[None, :])
    tri = finais[:, None] * fat * rng.lognormal(0, 0.01, (C, A + 1))
    mon = M.ConfigMonitor(idade=0, janela_ref=15, k=1.0, h=8.0)
    ach = M.monitor_maturacao(tri, 44, mon)
    assert ach.detectado and ach.tipo == "mudanca_maturacao"
    assert 40 <= ach.ponto_estimado <= 43 and ach.detalhes["direcao"] == "mais_lenta"
    # sem mudança: não dispara
    tri_estavel = finais[:, None] * f_antigo[None, :] * rng.lognormal(0, 0.01, (C, A + 1))
    assert not M.monitor_maturacao(tri_estavel, 59, mon).detectado
    # com monitor: recusa com motivo explícito até haver coortes pós-mudança maduras
    cfg = M.ConfigNowcast(janela_coortes=20, maturidade_minima=0.1, min_coortes=3)
    r = M.nowcast(tri, 44, 44, cfg, monitor=mon)
    assert isinstance(r, ResultadoInsuficiente) and r.motivo == "regime_de_maturacao_mudou"
    sem = M.nowcast(tri, 44, 44, cfg)
    assert sem["estimativa"] < 0.6 * finais[44]  # o herdado publica número enviesado
    assert M.regime_vigente(tri, 50, mon).ponto_estimado == ach.ponto_estimado  # persistente, sem estado
    depois = M.nowcast(tri, 50, 50, cfg, monitor=mon)
    assert depois["status"] == "estimado"
    assert depois["estimativa"] == pytest.approx(finais[50], rel=0.08)


def test_monitor_no_cenario_herdado_de_regime():
    """Cenário de regime do Stat Lab herdado (atraso 2,5× mais lento a partir da coorte 70)."""
    A = 20
    cen = CenarioMaturacao(n_coortes=100, idade_final=A, eventos_por_dia=200, mediana_valor=1.0, sigma_valor=0.8,
                           pmf_atraso=pmf_atraso_geometrica(2.0, A), regime_inicio=70,
                           pmf_atraso_regime=pmf_atraso_geometrica(5.0, A))
    inc = simular_incrementos(cen, np.random.default_rng(1))
    tri = np.cumsum(inc, axis=1)
    mons = [M.ConfigMonitor(idade=i, janela_ref=30, k=0.5, h=10.0) for i in (0, 1)]
    vig = M.regime_vigente(tri, 85, mons)
    assert vig.detectado and 68 <= vig.ponto_estimado <= 73
    assert not M.regime_vigente(tri, 69, mons).detectado  # antes da mudança: nada


def test_maturar_varias_coortes_e_metodo_invalido():
    tri = _tri([0.5, 0.8, 1.0], np.full(10, 10.0))
    out = M.maturar(tri, 9, CFG)
    assert len(out) == 2 and all(o["estimativa"] == pytest.approx(10.0) for o in out)
    with pytest.raises(ValueError):
        M.nowcast(tri, 9, 9, CFG, metodo="prophet")


def test_curva_intradiaria_analitica():
    final = np.full((3, 5), 100.0)
    vh = np.stack([final * 0.2, final * 0.7, final * 0.95])
    vh[1, 0, 0] = np.nan
    c = M.curva_intradiaria(vh, final, dias_ref=range(5))
    assert c["fator"] == pytest.approx([0.2, 0.7, 0.95])
    assert c["n_celulas"].tolist() == [15, 14, 15]
    est = M.nowcast_intradiario(np.array([20.0, np.nan]), 0.2, 15, CFG)
    assert est[0] == pytest.approx(100.0) and np.isnan(est[1])


def test_triangulo_de_registros_converge_para_final():
    from volc_dil.fundacao.simulador import simular

    s = simular("estavel", 4, n_campanhas=5, n_dias=8)
    tab = M.TabelaVersoes.de_registros(s.leituras.registros, fonte="joinads", metrica="revenue",
                                       entidades=M.ids_campanhas(s.mundo), dias=M.dias_iso(s.mundo))
    tri = M.triangulo_de_tabela(tab, s.mundo, hora_corte=12, idade_max=6)
    fim = tab.final()
    np.testing.assert_allclose(tri["por_campanha"][:, :, 6], fim)
    assert np.all(np.isnan(tri["por_campanha"][:, :, 0]) | (tri["por_campanha"][:, :, 0] <= fim * 1.5))


def test_coorte_do_regime_antigo_usa_fator_antigo():
    C, A = 50, 3
    f_antigo, f_novo = np.array([0.5, 0.8, 0.95, 1.0]), np.array([0.2, 0.5, 0.8, 1.0])
    fat = np.where(np.arange(C)[:, None] >= 40, f_novo[None, :], f_antigo[None, :])
    tri = 100.0 * fat
    reg = M.Achado("mudanca_maturacao", True, "cusum_link_ratio", indice=45, ponto_estimado=40,
                   detalhes={"pontos": [40]})
    cfg = M.ConfigNowcast(janela_coortes=10, maturidade_minima=0.1, min_coortes=3)
    velho = M.nowcast(tri, 41, 39, cfg, regime=reg)  # coorte 39 (regime antigo), idade 2
    assert velho["fator"] == pytest.approx(0.95) and velho["estimativa"] == pytest.approx(100.0)
    novo = M.nowcast(tri, 41, 41, cfg, regime=reg)
    assert isinstance(novo, ResultadoInsuficiente) and novo.motivo == "regime_de_maturacao_mudou"
