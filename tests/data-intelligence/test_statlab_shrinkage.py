"""Stat Lab — shrinkage EB: contraprovas (sem dados != 0, dinheiro não é contagem, invariância)."""

import numpy as np
import pytest

from volc_dil.statlab.shrinkage import (
    eb_hurdle,
    metricas_estimador,
    pesos_topk,
    eb_normal_media,
    gamma_poisson_em_dinheiro,
    posterior_beta,
    prior_beta_mle,
    prior_beta_momentos,
    prior_gamma_momentos,
    simular_receita,
)


def test_unidade_sem_dados_nao_vira_zero():
    x = np.array([1.0, 0.0, 5.0, 2.0, 0.0])
    n = np.array([10.0, 0.0, 50.0, 40.0, 30.0])
    pr = prior_beta_momentos(np.array([1, 5, 2, 0, 3, 4.0]), np.array([10, 50, 40, 30, 20, 60.0]))
    post = posterior_beta(x, n, pr, 0.9)
    assert np.isnan(post["cru"][1])           # cru indefinido, não 0
    assert post["sem_dados"][1]
    assert post["media"][1] == pytest.approx(pr.media)  # cai no prior, marcado
    assert post["cru"][4] == 0.0              # zero observado É zero


def test_ausencia_explicita_recusada():
    with pytest.raises(ValueError):
        prior_beta_momentos(np.array([1.0, np.nan]), np.array([10.0, 10.0]))
    with pytest.raises(ValueError):
        prior_gamma_momentos(np.array([1.0, np.nan]), np.array([10.0, 10.0]))


def test_gamma_poisson_recusa_valor_monetario_continuo():
    with pytest.raises(ValueError, match="CONTAGENS"):
        prior_gamma_momentos(np.array([12.37, 0.0, 3.5]), np.array([10.0, 5.0, 8.0]))


def test_sem_heterogeneidade_detectada_vira_pooling_total():
    rng = np.random.default_rng(3)
    n = np.full(300, 50.0)
    x = rng.binomial(50, 0.03, 300).astype(float)  # todas iguais
    pr = prior_beta_momentos(x, n)
    if pr.status == "sem_heterogeneidade_detectada":
        assert pr.a + pr.b > 1e6
    else:  # MoM ruidoso pode achar pouca heterogeneidade; nesse caso concentração deve ser alta
        assert pr.a + pr.b > 100


def test_mle_recupera_concentracao_aproximada():
    rng = np.random.default_rng(11)
    K = 3000
    n = np.floor(rng.lognormal(np.log(80), 0.8, K)).astype(float)
    p = rng.beta(0.03 * 50, 0.97 * 50, K)
    x = rng.binomial(n.astype(int), p).astype(float)
    pr = prior_beta_mle(x, n)
    assert 25 < pr.a + pr.b < 100
    assert pr.media == pytest.approx(0.03, rel=0.1)


def test_gamma_poisson_em_dinheiro_depende_da_unidade_e_alternativas_nao():
    rng = np.random.default_rng(5)
    d = simular_receita(rng, K=300, mediana_n=80, sigma_n=1.0, media_cvr=0.03, conc_cvr=60,
                        mediana_valor=40.0, tau_log_valor=0.4, sigma_log_valor=1.0)
    gp_r = gamma_poisson_em_dinheiro(d["soma"], d["n"], 1.0, 0.9)
    gp_c = gamma_poisson_em_dinheiro(d["soma"], d["n"], 100.0, 0.9)
    # peso do prior muda >10x só por trocar R$ por centavos: o modelo não é invariante a escala
    assert gp_r["fator_shrink_mediano"] > 10 * gp_c["fator_shrink_mediano"]
    # normal-normal EB com variância empírica: invariante
    nn1 = eb_normal_media(d["soma"], d["soma2"], d["n"], 0.9)
    nn100 = eb_normal_media(d["soma"] * 100, d["soma2"] * 1e4, d["n"], 0.9)
    np.testing.assert_allclose(nn100["media"], 100 * nn1["media"], rtol=1e-9)
    # hurdle: invariante (média posterior determinística)
    h1 = eb_hurdle(d["x"], d["n"], d["soma_log"], d["soma_log2"], 0.9, np.random.default_rng(0), 200)
    lg = np.log(100.0)
    h100 = eb_hurdle(d["x"], d["n"], d["soma_log"] + d["x"] * lg,
                     d["soma_log2"] + 2 * lg * d["soma_log"] + d["x"] * lg**2, 0.9,
                     np.random.default_rng(0), 200)
    np.testing.assert_allclose(h100["media"], 100 * h1["media"], rtol=1e-8)


def test_estimador_constante_sem_calibracao_e_topk_por_desempate_aleatorio():
    rng = np.random.default_rng(1)
    verdade = rng.random(100)
    n = np.full(100, 50.0)
    const = np.full(100, 0.37)
    m = metricas_estimador(verdade, const, 10, n)
    assert m["inclinacao_calibracao"] is None and m["calibracao_nao_aplicavel_estimador_constante"]
    # top-k de um estimador constante = sorteio: 10 * (1 - 10/100) = 9 vencedores por sorte esperados
    assert m["vencedores_por_sorte_topk"] == pytest.approx(9.0)
    assert m["regret_topk"] == pytest.approx(1 - verdade.mean() / np.sort(verdade)[-10:].mean())
    # o resultado não depende da ordem dos índices
    perm = rng.permutation(100)
    m2 = metricas_estimador(verdade[perm], const, 10, n)
    assert m2["vencedores_por_sorte_topk"] == pytest.approx(m["vencedores_por_sorte_topk"])
    # estimador que varia tem calibração definida
    assert metricas_estimador(verdade, verdade + rng.normal(0, 0.1, 100), 10, n)["inclinacao_calibracao"] is not None


def test_pesos_topk_empates_somam_k():
    w = pesos_topk(np.array([0.9, 0.5, 0.5, 0.5, 0.1, np.nan]), 2)
    np.testing.assert_allclose(w, [1, 1 / 3, 1 / 3, 1 / 3, 0, 0])
    assert w.sum() == pytest.approx(2)
