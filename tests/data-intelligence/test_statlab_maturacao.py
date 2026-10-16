"""Stat Lab — maturação/nowcasting: contraprovas (ausência != 0, guarda, sem olhar o futuro)."""

import math

import numpy as np
import pytest

from volc_dil.statlab.base import ResultadoInsuficiente, rngs
from volc_dil.statlab.maturacao import (
    CenarioMaturacao,
    ConfigNowcast,
    agregar,
    avaliar_mundo,
    fatores_maturacao,
    nowcast_coorte,
    nowcast_sem_guarda,
    pmf_atraso_geometrica,
    pmf_atraso_lognormal,
    simular_incrementos,
    triangulo_observado,
)

A = 20
AS_OF = 69


def _cenario(**kw):
    base = dict(n_coortes=70, idade_final=A, eventos_por_dia=40, mediana_valor=2.0, sigma_valor=1.0,
                pmf_atraso=pmf_atraso_lognormal(3.0, 1.0, A), nome="teste")
    base.update(kw)
    return CenarioMaturacao(**base)


def _cfg(**kw):
    base = dict(janela_coortes=20, maturidade_minima=0.3, min_coortes=10)
    base.update(kw)
    return ConfigNowcast(**base)


def _triangulo(seed=1, **kw):
    cen = _cenario(**kw)
    inc = simular_incrementos(cen, np.random.default_rng(seed))
    return inc, triangulo_observado(inc, AS_OF)


def test_null_nao_vira_zero_no_fator():
    _, tri = _triangulo()
    idade = 2
    ref = fatores_maturacao(tri, AS_OF, janela_coortes=20)
    maduras = np.arange(AS_OF - A - 19, AS_OF - A + 1)
    alvo = maduras[5]
    com_ausente = tri.copy()
    com_ausente[alvo, idade] = np.nan
    f_aus = fatores_maturacao(com_ausente, AS_OF, janela_coortes=20)
    # esperado: coorte com célula ausente é EXCLUÍDA (complete case), não somada como 0
    resto = np.setdiff1d(maduras, [alvo])
    esperado = tri[resto, idade].sum() / tri[resto, A].sum()
    assert f_aus["fator"][idade] == pytest.approx(esperado, rel=1e-12)
    assert f_aus["n_excluidas_ausentes"][idade] == 1
    assert f_aus["n_coortes"][idade] == ref["n_coortes"][idade] - 1
    # contraprova: tratar NaN como 0 daria outro (menor) fator
    como_zero = tri.copy()
    como_zero[alvo, idade] = 0.0
    f_zero = fatores_maturacao(como_zero, AS_OF, janela_coortes=20)["fator"][idade]
    assert f_zero < f_aus["fator"][idade]


def test_fator_indefinido_e_nan_nao_zero():
    _, tri = _triangulo()
    vazio = tri.copy()
    vazio[:, :] = np.nan
    f = fatores_maturacao(vazio, AS_OF, janela_coortes=20)
    assert np.all(np.isnan(f["fator"]))
    assert np.all(f["n_coortes"] == 0)


def test_observacao_ausente_devolve_insuficiente():
    _, tri = _triangulo()
    tri = tri.copy()
    tri[AS_OF - 3, 3] = np.nan
    r = nowcast_coorte(tri, AS_OF, AS_OF - 3, _cfg())
    assert isinstance(r, ResultadoInsuficiente)
    assert r.motivo == "observacao_ausente"


def test_guarda_maturacao_devolve_insuficiente_e_sem_guarda_explode():
    # reporte D+1: m(0) == 0 exatamente
    pmf = pmf_atraso_geometrica(media=4.0, maximo=A, minimo=1)
    _, tri = _triangulo(pmf_atraso=pmf)
    f = fatores_maturacao(tri, AS_OF, janela_coortes=20)
    assert f["fator"][0] == 0.0
    r = nowcast_coorte(tri, AS_OF, AS_OF, _cfg())
    assert isinstance(r, ResultadoInsuficiente)
    assert r.motivo == "maturidade_abaixo_do_minimo"
    assert r.como_dict()["status"] == "insuficiente"
    # sem guarda: divisão por fator 0 vira inf/NaN (o número que NÃO pode ser publicado)
    assert math.isinf(nowcast_sem_guarda(1.0, 0.0))
    assert math.isnan(nowcast_sem_guarda(0.0, 0.0))
    # fator pequeno mas positivo: amplificação 1/m
    assert nowcast_sem_guarda(1.0, 0.01) == pytest.approx(100.0)


def test_guarda_min_coortes():
    _, tri = _triangulo()
    r = nowcast_coorte(tri, AS_OF, AS_OF - 5, _cfg(min_coortes=999))
    assert isinstance(r, ResultadoInsuficiente)
    assert r.motivo == "coortes_maduras_insuficientes"


def test_estimativa_traz_baseline_n_e_metodo():
    _, tri = _triangulo()
    r = nowcast_coorte(tri, AS_OF, AS_OF - 6, _cfg(nivel_intervalo=0.9))
    assert isinstance(r, dict) and r["status"] == "estimado"
    for k in ("estimativa", "observado", "fator", "n_coortes", "metodo", "intervalo", "idade"):
        assert k in r
    assert r["estimativa"] == pytest.approx(r["observado"] / r["fator"])


def test_nao_olha_o_futuro():
    inc, tri = _triangulo()
    acum = np.cumsum(inc, axis=1)  # triângulo COMPLETO (inclui o futuro)
    lixo = acum.copy()
    c = np.arange(acum.shape[0])[:, None]
    a = np.arange(acum.shape[1])[None, :]
    lixo = np.where(c + a > AS_OF, 1e9, acum)  # futuro adulterado
    for metodo in ("coortes_maduras", "link_ratio"):
        f1 = fatores_maturacao(tri, AS_OF, janela_coortes=20, metodo=metodo)["fator"]
        f2 = fatores_maturacao(lixo, AS_OF, janela_coortes=20, metodo=metodo)["fator"]
        np.testing.assert_array_equal(np.nan_to_num(f1, nan=-1), np.nan_to_num(f2, nan=-1))
    r1 = nowcast_coorte(tri, AS_OF, AS_OF - 4, _cfg())
    r2 = nowcast_coorte(lixo, AS_OF, AS_OF - 4, _cfg())
    assert r1["estimativa"] == r2["estimativa"]


def test_mudanca_de_regime_degrada_e_estavel_nao():
    cfg = _cfg(nivel_intervalo=0.9, n_bootstrap=50)
    estavel = _cenario()
    regime = _cenario(regime_inicio=AS_OF - 14, pmf_atraso_regime=pmf_atraso_lognormal(8.0, 1.0, A))
    faixas = ((3, 6),)
    ag_e = agregar([avaliar_mundo(estavel, r, AS_OF, cfg) for r in rngs(7, 25)], faixas)[0]
    ag_r = agregar([avaliar_mundo(regime, r, AS_OF, cfg) for r in rngs(7, 25)], faixas)[0]
    assert abs(ag_e["com_guarda"]["vies_relativo"]) < 0.08
    assert ag_r["com_guarda"]["vies_relativo"] < -0.25  # subestima quando o atraso fica mais lento
    assert ag_r["cobertura_razao"]["estimativa"] < ag_e["cobertura_razao"]["estimativa"] - 0.2
    # resultado negativo preservado: bootstrap só do fator ignora ruído de processo e sub-cobre
    assert ag_e["cobertura_boot"]["estimativa"] < 0.6 < ag_e["cobertura_razao"]["estimativa"]
