"""e-processos/e-BH (validade sob H0, FDR <= q) e diagnósticos causais em painéis com efeito conhecido."""
from __future__ import annotations

import numpy as np
import pytest

from volc_dil.fundacao import modelos as M


# ── sequencial ────────────────────────────────────────────────────────────

def test_e_bh_caso_analitico():
    e = np.array([100.0, 30.0, 1.0, 0.5])
    # m = 4, q = 0.1: limiares m/(q k) = 40, 20, 13.3, 10 → k* = 2 (30 >= 20)
    assert M.e_bh(e, 0.1).tolist() == [True, True, False, False]
    assert not M.e_bh(np.ones(5), 0.1).any()
    with pytest.raises(ValueError):
        M.e_bh([1.0, np.nan], 0.1)


def test_eprocesso_valido_sob_h0_ville_e_esperanca():
    rng = np.random.default_rng(0)
    x = rng.binomial(1, 0.2, size=(3000, 300)).astype(float)  # H0 no limite: mu = mu0
    K = M.eprocesso_media_limitada(x, 0.2)
    assert K[:, -1].mean() <= 1.0 + 3 * K[:, -1].std() / np.sqrt(K.shape[0])
    alpha = 0.05
    assert (K.max(axis=1) >= 1 / alpha).mean() <= alpha + 0.01


def test_eprocesso_cresce_sob_alternativa():
    rng = np.random.default_rng(1)
    x = rng.binomial(1, 0.3, size=(200, 2000)).astype(float)
    K = M.eprocesso_media_limitada(x, 0.2)
    assert (K[:, -1] >= 20).mean() > 0.9


def test_e_bh_controla_fdr_em_monte_carlo():
    rng = np.random.default_rng(2)
    m, n, q = 40, 400, 0.1
    fdps = []
    for _ in range(150):
        alt = np.zeros(m, bool)
        alt[:8] = True
        mu = np.where(alt, 0.3, 0.2)
        x = rng.binomial(1, mu[:, None], size=(m, n)).astype(float)
        e = M.eprocesso_media_limitada(x, 0.2)[:, -1]
        rej = M.e_bh(e, q)
        fdps.append((rej & ~alt).sum() / max(rej.sum(), 1))
    assert np.mean(fdps) <= q


def test_limite_falso_para_receita_e_recusado():
    receita = np.array([0.1, 0.5, 0.2, 3.0])
    with pytest.raises(M.ForaDoSuporte):
        M.normalizar_por_limite(receita, limite=1.0)
    with pytest.raises(M.ForaDoSuporte):
        M.eprocesso_media_limitada(receita, 0.2)


def test_p_binomial_unilateral():
    p = M.p_binomial_unilateral([5, 0], [10, 0], 0.5)
    assert p[0] == pytest.approx(0.623046875) and np.isnan(p[1])


# ── causal ────────────────────────────────────────────────────────────────

def _painel(efeito=2.0, tendencia_extra=0.0, n=40, T=20, t0=12, seed=0):
    rng = np.random.default_rng(seed)
    nivel = rng.normal(10, 3, n)
    tempo = np.linspace(0, 2, T)
    tr = np.zeros(n, bool)
    tr[: n // 2] = True
    Y = nivel[:, None] + tempo[None, :] + rng.normal(0, 0.3, (n, T))
    Y[tr] += tendencia_extra * np.arange(T)[None, :]
    Y[np.ix_(tr, np.arange(t0, T))] += efeito
    return Y, tr, t0


def test_did_recupera_efeito_conhecido_e_diagnosticos_passam():
    Y, tr, t0 = _painel()
    d = M.did_painel(Y, tr, t0, n_boot=400)
    assert d["efeito"] == pytest.approx(2.0, abs=0.15)
    assert d["ic95"][0] < 2.0 < d["ic95"][1]
    assert M.tendencias_paralelas(Y, tr, t0, n_boot=400)["passou"]
    assert M.placebo_temporal(Y, tr, t0, 6, n_boot=400)["passou"]
    assert M.placebo_unidades(Y, tr, t0, n_perm=300)["p_valor"] < 0.01


def test_tendencia_nao_paralela_e_acusada():
    Y, tr, t0 = _painel(efeito=0.0, tendencia_extra=0.2)
    assert not M.tendencias_paralelas(Y, tr, t0, n_boot=400)["passou"]
    assert not M.placebo_temporal(Y, tr, t0, 6, n_boot=400)["passou"]


def test_did_recusa_painel_com_ausencia():
    Y, tr, t0 = _painel()
    Y[0, 3] = np.nan
    with pytest.raises(ValueError):
        M.did_painel(Y, tr, t0)


def test_controle_sintetico_recupera_pesos_e_efeito():
    rng = np.random.default_rng(4)
    T, t0 = 30, 20
    X = rng.normal(0, 1, (6, T)).cumsum(axis=1)
    w = np.array([0.5, 0.3, 0.2, 0, 0, 0])
    y = w @ X
    y[t0:] += 1.5
    Y = np.vstack([y, X])
    r = M.controle_sintetico(Y, 0, np.arange(1, 7), t0, com_intercepto=False)
    np.testing.assert_allclose(r["pesos"], w, atol=0.02)
    assert r["efeito"] == pytest.approx(1.5, abs=0.05) and r["rmspe_pre"] < 0.05
    assert r["pesos"].min() >= 0 and r["pesos"].sum() == pytest.approx(1.0)
    pl = M.controle_sintetico_placebo(Y, 0, np.arange(1, 7), t0, com_intercepto=False)
    assert pl["p_valor"] == pytest.approx(1 / 7)
