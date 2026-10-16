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
    cs_prpl_eb_componentes,
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
    # n grande o bastante para que o LIMITE SUPERIOR do IC de Wilson fique abaixo de alpha:
    # uma CS que erra 8% (ex.: psi/8) é reprovada; ver também os valores de referência abaixo
    rng = np.random.default_rng(20261015)
    r = rodar_monte_carlo(rng, bernoulli(0.5), 2000, 2000, 0.5, None, 0.05, 10, (2000,), 250)
    cs = agregar_cs(r["cs_prpl_eb"], 2000)["erro_uniforme_no_tempo"]
    wald = agregar_cs(r["wald_peeking"], 2000)["erro_uniforme_no_tempo"]
    assert cs["ic95"][1] <= 0.05          # anytime-valid: até o limite superior do IC MC fica <= alpha
    assert wald["ic95"][0] > 0.15         # peeking infla muito o erro


def test_cs_valores_de_referencia_a_mao():
    """x = [1, 0], alpha = 0.05, c = 1/2 — calculado à mão a partir da forma PrPl-EB:
    t=1: mu_prev=1/2, sig2_prev=1/4, lambda=min(sqrt(2 ln 40/(1/4 * 1 * ln 2)), 1/2)=1/2,
         v=4(1-1/2)^2=1, psi=(ln 2 - 1/2)/4, centro=1, margem=(ln 40 + psi)/(1/2)
    t=2: mu_hat_1=3/4, sig2_1=(1/4 + 1/16)/2=5/32, lambda=1/2 (teto), v=4(0-3/4)^2=9/4,
         centro=1/2, margem=(ln 40 + psi + 9/4 psi)/1"""
    k = cs_prpl_eb_componentes(np.array([1.0, 0.0]), 0.05)
    psi = (np.log(2) - 0.5) / 4
    np.testing.assert_allclose(k["lam"], [0.5, 0.5])
    np.testing.assert_allclose(k["v"], [1.0, 2.25])
    np.testing.assert_allclose(k["centro"], [1.0, 0.5])
    np.testing.assert_allclose(k["margem"], [(np.log(40) + psi) / 0.5, np.log(40) + psi * (1 + 2.25)], rtol=1e-12)


def _cs_referencia_escalar(x, alpha, c=0.5):
    """Implementação escalar independente (laço), lambda e v PREVISÍVEIS (usam só i-1)."""
    soma = 0.0
    soma_q = 0.0
    mu_ant, sig2_ant = 0.5, 0.25
    sl = slx = svpsi = 0.0
    lo_acc, hi_acc = 0.0, 1.0
    los, his = [], []
    for i, xi in enumerate(x, start=1):
        lam = min(np.sqrt(2 * np.log(2 / alpha) / (sig2_ant * i * np.log(1 + i))), c)
        v = 4 * (xi - mu_ant) ** 2
        psi = (-np.log(1 - lam) - lam) / 4
        sl += lam
        slx += lam * xi
        svpsi += v * psi
        centro = slx / sl
        margem = (np.log(2 / alpha) + svpsi) / sl
        lo_acc = max(lo_acc, min(max(centro - margem, 0.0), 1.0))
        hi_acc = min(hi_acc, max(min(centro + margem, 1.0), 0.0))
        los.append(lo_acc)
        his.append(hi_acc)
        soma += xi
        mu_atual = (0.5 + soma) / (i + 1)
        soma_q += (xi - mu_atual) ** 2
        mu_ant, sig2_ant = mu_atual, (0.25 + soma_q) / (i + 1)
    return np.array(los), np.array(his)


def test_cs_igual_referencia_escalar_lambda_previsivel():
    rng = np.random.default_rng(3)
    for x in (rng.random(3000), (rng.random(3000) < 0.05).astype(float), rng.beta(0.5, 3, 3000)):
        lo, hi = cs_prpl_eb(x, 0.05)
        lo_r, hi_r = _cs_referencia_escalar(x, 0.05)
        np.testing.assert_allclose(lo, lo_r, rtol=1e-10, atol=1e-12)
        np.testing.assert_allclose(hi, hi_r, rtol=1e-10, atol=1e-12)


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
