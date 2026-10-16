"""Stat Lab — confidence sequence [0,1] e FDR: contraprovas reduzidas (seed fixa)."""

import numpy as np
import pytest

from volc_dil.statlab.base import rngs
from volc_dil.statlab.fdr import agregar, bh_com_ausentes, bh_propria, bh_statsmodels, replica_celulas
from volc_dil.statlab.sequencias_confianca import (
    ForaDoSuporte,
    agregar as agregar_cs,
    bernoulli,
    cs_prpl_eb,
    rodar_monte_carlo,
)


# ----------------------------------------------------------------- CS

def test_cs_rejeita_entrada_fora_de_0_1():
    with pytest.raises(ForaDoSuporte, match=r"\[0, 1\]"):
        cs_prpl_eb(np.array([0.2, 1.5, 0.3]), 0.05)
    with pytest.raises(ForaDoSuporte):
        cs_prpl_eb(np.array([0.2, -0.01]), 0.05)
    with pytest.raises(ForaDoSuporte, match="ausente"):
        cs_prpl_eb(np.array([0.2, np.nan]), 0.05)


def test_cs_monotona_e_dentro_de_0_1():
    x = np.random.default_rng(1).random((3, 500))
    lo, hi = cs_prpl_eb(x, 0.05)
    assert np.all(np.diff(lo, axis=1) >= 0) and np.all(np.diff(hi, axis=1) <= 0)
    assert np.all((0 <= lo) & (lo <= hi) & (hi <= 1))


def test_cs_cobertura_uniforme_vs_wald_peeking():
    rng = np.random.default_rng(20261015)
    r = rodar_monte_carlo(rng, bernoulli(0.5), 300, 2000, 0.5, None, 0.05, 10, (2000,), 150)
    cs = agregar_cs(r["cs_prpl_eb"], 2000)["erro_uniforme_no_tempo"]
    wald = agregar_cs(r["wald_peeking"], 2000)["erro_uniforme_no_tempo"]
    assert cs["ic95"][0] <= 0.05          # compatível com alpha (anytime-valid)
    assert wald["ic95"][0] > 0.15         # peeking infla muito o erro


# ----------------------------------------------------------------- FDR

def test_bh_propria_igual_statsmodels():
    rng = np.random.default_rng(42)
    for _ in range(300):
        m = int(rng.integers(1, 500))
        p = np.concatenate([rng.random(m), rng.beta(0.2, 5, m // 5)])
        for q in (0.01, 0.05, 0.1, 0.3):
            np.testing.assert_array_equal(bh_propria(p, q), bh_statsmodels(p, q))


def test_bh_fronteira_exata_rejeita():
    # p == q k / m na fronteira: a regra BH (<=) rejeita
    assert bh_propria(np.array([0.01, 0.02]), 0.02).tolist() == [True, True]
    assert bh_propria(np.array([0.14] * 7 + [0.9] * 3), 0.2).sum() == 7


def test_bh_ausencia_nao_vira_p1_nem_p0():
    with pytest.raises(ValueError):
        bh_propria(np.array([0.01, np.nan]), 0.05)
    r = bh_com_ausentes(np.array([0.001, np.nan, 0.9]), 0.05)
    assert r["rejeita"] == [True, None, False]
    assert r["n_ausentes"] == 1 and r["m_testado"] == 2


def test_bh_controla_fdr_numa_olhada_e_peeking_infla():
    um = [replica_celulas(r, 500, 0.05, 0.03, 0.3, 5000, 0.05, None) for r in rngs(9, 200)]
    pk = [replica_celulas(r, 500, 0.05, 0.03, 0.3, 5000, 0.05, tuple(range(500, 5001, 500)))
          for r in rngs(9, 200)]
    a1, ap = agregar(um), agregar(pk)
    assert a1["bh"]["fdr_realizado"]["ic95"][0] <= 0.05
    assert a1["nenhuma"]["fdr_realizado"]["estimativa"] > 0.3
    assert ap["bh"]["fdr_realizado"]["estimativa"] > a1["bh"]["fdr_realizado"]["estimativa"] + 0.02
