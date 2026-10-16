"""Anomalia (lacuna ≠ anomalia, robusto × z-score, zero implausível) e alocação (KKT × SLSQP, restrições)."""
from __future__ import annotations

import numpy as np
import pytest
from scipy import optimize

from volc_dil.fundacao import modelos as M


# ── anomalia ──────────────────────────────────────────────────────────────

def test_lacuna_nao_e_anomalia_e_nulo_como_zero_dispara():
    rng = np.random.default_rng(0)
    x = list(100 + rng.normal(0, 3, 40))
    for t in (20, 21, 22):
        x[t] = None
    st = ["observed"] * 40
    st[20] = st[21] = st[22] = "unavailable"
    achados = M.detectar_anomalias(x, metodo="robusto_mad", limiar=3.5, janela=14, status=st)
    lac = [a.indice for a in achados if a.tipo == "lacuna"]
    val = [a.indice for a in achados if a.tipo == "anomalia_valor"]
    assert lac == [20, 21, 22] and not set(val) & {20, 21, 22}
    assert {20, 21, 22} & set(M.nulo_como_zero(x, limiar=3.0, janela=14))


def test_status_sem_valor_vira_lacuna_mesmo_com_numero():
    achados = M.detectar_anomalias([1.0] * 10 + [5.0], metodo="zscore", limiar=3.0, janela=5,
                                   status=["observed"] * 10 + ["invalid"])
    assert achados[-1].tipo == "lacuna"


def test_robusto_nao_e_mascarado_por_outlier_anterior():
    rng = np.random.default_rng(1)
    x = 50 + rng.normal(0, 1, 30)
    x[10] = 500.0   # outlier antigo infla média/desvio do z-score
    x[20] = 60.0    # anomalia moderada
    z = {a.indice for a in M.detectar_anomalias(list(x), metodo="zscore", limiar=3.0, janela=14)}
    r = {a.indice for a in M.detectar_anomalias(list(x), metodo="robusto_mad", limiar=3.5, janela=14)}
    assert 20 in r and 20 not in z


def test_sazonal_robusto_ignora_ciclo_semanal():
    t = np.arange(70)
    x = 100 + 30 * (t % 7 >= 5) + np.random.default_rng(2).normal(0, 1, 70)
    x[60] += 15  # anomalia num dia útil
    saz = {a.indice for a in M.detectar_anomalias(list(x), metodo="sazonal_robusto", limiar=3.5, janela=28)}
    mad = {a.indice for a in M.detectar_anomalias(list(x), metodo="robusto_mad", limiar=3.5, janela=28)}
    assert 60 in saz
    assert len(saz - {60}) < len(mad - {60})  # fins de semana viram falso alarme sem sazonalidade


def test_zero_implausivel():
    x = [30, 28, 35, 31, 0, 29, 2, 1, 0, 1, 0]
    a = [z.indice for z in M.zero_implausivel(x, janela=4, p_max=1e-3)]
    assert a == [4]  # zero depois de ~30 cliques/dia é implausível; zeros em série baixa não
    assert M.zero_implausivel([30, 30, 30, None, 0], janela=4, p_max=1e-3)[0].indice == 4
    pr = M.precisao_recall([4, 7], [4])
    assert pr["precisao"] == 0.5 and pr["recall"] == 1.0


# ── alocação ──────────────────────────────────────────────────────────────

def _curvas(seed=0, n=8):
    rng = np.random.default_rng(seed)
    return [M.CurvaResposta(a=float(rng.uniform(1.5, 4)), b=float(rng.uniform(0.3, 0.8)), se_log_a=0.1,
                            identificavel=True, n=20, desvio_log_gasto=0.5) for _ in range(n)]


def test_kkt_igual_a_slsqp():
    cs = _curvas()
    lo, hi = np.full(8, 1.0), np.full(8, 40.0)
    total = 60.0
    x = M.alocar_orcamento(cs, total=total, lo=lo, hi=hi)
    f = lambda v: -M.lucro_esperado(cs, v)  # noqa: E731
    ref = optimize.minimize(f, np.full(8, total / 8), method="SLSQP", bounds=list(zip(lo, hi)),
                            constraints=[{"type": "ineq", "fun": lambda v: total - v.sum()}], options={"ftol": 1e-12})
    assert M.lucro_esperado(cs, x) >= -ref.fun - 1e-6
    assert not M.verificar_restricoes(x, lo, hi, total)


@pytest.mark.parametrize("seed", range(6))
def test_restricoes_respeitadas_por_todas_as_politicas(seed):
    rng = np.random.default_rng(seed)
    n = 10
    cs = _curvas(seed, n)
    atual = rng.uniform(5, 20, n)
    lo, hi = M.limites(atual, minimo=1.0, maximo=30.0, passo_max=0.5)
    total = float(atual.sum())
    roas = np.array([c.a * a ** (c.b - 1) for c, a in zip(cs, atual)])
    contrib = rng.normal(0, 5, n)
    contrib[0] = np.nan
    pols = {
        "concava": M.alocar_orcamento(cs, total=total, lo=lo, hi=hi, aversao=1.0),
        "igual": M.alocar_igual(n, total=total, lo=lo, hi=hi),
        "guloso": M.alocar_guloso(roas, total=total, lo=lo, hi=hi),
        "proporcional": M.alocar_proporcional(contrib, total=total, lo=lo, hi=hi, piso=1.0),
    }
    for nome, x in pols.items():
        assert not M.verificar_restricoes(x, lo, hi, total), nome
        assert np.all(np.abs(x - atual) <= 0.5 * atual + 1e-6), nome  # passo máximo


def test_limites_inviaveis_e_total_inviavel():
    with pytest.raises(ValueError):
        M.limites([10.0], minimo=20.0, maximo=30.0, passo_max=0.1)
    with pytest.raises(ValueError):
        M.alocar_orcamento(_curvas(n=2), total=1.0, lo=[1.0, 1.0], hi=[5.0, 5.0])


def test_ajuste_identifica_com_variacao_e_cai_no_prior_sem():
    rng = np.random.default_rng(3)
    g = np.exp(rng.uniform(np.log(10), np.log(40), 30))
    r = 3.0 * g ** 0.6 * rng.lognormal(0, 0.05, 30)
    c = M.ajustar_resposta(g, r, b_prior=0.8, sd_prior_b=0.3, min_desvio_log=0.1)
    assert c.identificavel and c.b == pytest.approx(0.6, abs=0.08)
    g2 = np.full(30, 20.0) * rng.lognormal(0, 0.01, 30)
    c2 = M.ajustar_resposta(g2, 3.0 * g2 ** 0.6, b_prior=0.8, sd_prior_b=0.3, min_desvio_log=0.1)
    assert not c2.identificavel and c2.b == 0.8 and c2.se_log_a > c.se_log_a
    c3 = M.ajustar_resposta([np.nan, 1.0], [1.0, 1.0], b_prior=0.8, sd_prior_b=0.3, min_desvio_log=0.1)
    assert not c3.identificavel and c3.n == 1


def test_aversao_reduz_gasto_em_curva_incerta():
    certa = M.CurvaResposta(3.0, 0.6, 0.01, True, 30, 0.5)
    incerta = M.CurvaResposta(3.0, 0.6, 1.0, False, 30, 0.0)
    x = M.alocar_orcamento([certa, incerta], total=100.0, lo=[0.0, 0.0], hi=[100.0, 100.0], aversao=1.0)
    assert x[1] < x[0]


def test_para_micros_centavos():
    assert M.para_micros([1.234, 2.0]).tolist() == [1_230_000, 2_000_000]
