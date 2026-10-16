"""Bandits/OPE (IPS não-viesado com propensão correta, recusa sem propensão) e conformal (cobertura)."""
from __future__ import annotations

import numpy as np
import pytest

from volc_dil.fundacao import modelos as M


def _ambiente(T=600, K=4, n_ctx=3, seed=0):
    rng = np.random.default_rng(seed)
    mu = rng.normal(0, 1, (n_ctx, K))
    ctx = rng.integers(0, n_ctx, T)
    r = mu[ctx].T + rng.normal(0, 1.0, (K, T))
    return r, ctx, n_ctx


def _alvo_deterministico(ctx, K, melhor):
    pi = np.zeros((ctx.size, K))
    pi[np.arange(ctx.size), melhor[ctx]] = 1.0
    return pi


def test_ips_nao_viesado_com_propensao_correta_e_viesado_com_inventada():
    r, ctx, n_ctx = _ambiente()
    K = r.shape[0]
    mu = M.medias_por_contexto(r, ctx, n_ctx)
    pi = _alvo_deterministico(ctx, K, np.argmax(mu, axis=1))
    V = M.valor_verdadeiro(pi, r)
    est, inv = [], []
    for s in range(300):
        out = M.rodar(M.Gulosa(K, n_ctx, epsilon=0.3), r, ctx, seed=s)
        log = out["log"]
        est.append(M.ips(log, pi))
        falso = M.Log(log.contexto, log.acao, log.recompensa, np.full(log.acao.size, 1.0 / K))
        inv.append(M.ips(falso, pi))
    est, inv = np.array(est), np.array(inv)
    ep = est.std(ddof=1) / np.sqrt(est.size)
    assert abs(est.mean() - V) <= 3 * ep
    ep_inv = inv.std(ddof=1) / np.sqrt(inv.size)
    assert abs(inv.mean() - V) > 3 * ep_inv  # propensão inventada depois do fato enviesa


def test_snips_e_dr_tem_variancia_menor_que_ips():
    r, ctx, n_ctx = _ambiente(seed=1)
    K = r.shape[0]
    mu = M.medias_por_contexto(r, ctx, n_ctx)
    pi = _alvo_deterministico(ctx, K, np.argmax(mu, axis=1))
    a, b, c = [], [], []
    for s in range(150):
        log = M.rodar(M.Uniforme(K, n_ctx), r, ctx, seed=s)["log"]
        a.append(M.ips(log, pi))
        b.append(M.snips(log, pi))
        c.append(M.dr(log, pi, M.q_tabular_cruzado(log, n_ctx, K)))
    assert np.var(b) < np.var(a) and np.var(c) < np.var(a)


def test_sem_propensao_nao_ha_ope():
    r, ctx, n_ctx = _ambiente(T=50)
    out = M.rodar(M.Uniforme(4, n_ctx), r, ctx, seed=0, logar_propensao=False)
    pi = np.full((50, 4), 0.25)
    for f in (M.ips, M.snips):
        with pytest.raises(M.PropensaoAusente):
            f(out["log"], pi)
    log = out["log"]
    zero = M.Log(log.contexto, log.acao, log.recompensa, np.zeros(50))
    with pytest.raises(M.PropensaoAusente):
        M.ips(zero, pi)


def test_dr_exato_com_q_perfeito():
    r, ctx, n_ctx = _ambiente(T=200, seed=2)
    K = r.shape[0]
    log = M.rodar(M.Uniforme(K, n_ctx), r, ctx, seed=3)["log"]
    pi = np.full((200, K), 1.0 / K)
    q = r.T.copy()  # q̂ = recompensa realizada de cada braço (oráculo)
    assert M.dr(log, pi, q) == pytest.approx(M.valor_verdadeiro(pi, r))


def test_linucb_e_thompson_batem_uniforme_em_problema_facil_e_sao_deterministicos():
    r, ctx, n_ctx = _ambiente(T=1500, seed=4)
    K = r.shape[0]
    mu = M.medias_por_contexto(r, ctx, n_ctx)
    reg = {}
    for nome, pol in (("u", M.Uniforme(K, n_ctx)), ("l", M.LinUCB(K, n_ctx, alpha=1.0)),
                      ("t", M.ThompsonLinear(K, n_ctx, n_mc=100))):
        reg[nome] = M.pseudo_regret(M.rodar(pol, r, ctx, seed=0)["distribuicoes"], ctx, mu)
    assert reg["l"] < 0.5 * reg["u"] and reg["t"] < 0.5 * reg["u"]
    a = M.rodar(M.ThompsonLinear(K, n_ctx, n_mc=50), r, ctx, seed=9)["log"]
    b = M.rodar(M.ThompsonLinear(K, n_ctx, n_mc=50), r, ctx, seed=9)["log"]
    assert np.array_equal(a.acao, b.acao) and np.array_equal(a.propensao, b.propensao)


# ── conformal ─────────────────────────────────────────────────────────────

def test_quantil_conformal_amostra_finita():
    s = np.arange(1, 10, dtype=float)  # n = 9
    assert M.quantil_conformal(s, 0.1) == 9.0  # posto ceil(10 * 0.9) = 9
    assert M.quantil_conformal(s, 0.2) == 8.0
    assert M.quantil_conformal(s[:3], 0.1) == float("inf")


def test_split_conformal_cobre_nominal_em_dado_trocavel():
    rng = np.random.default_rng(0)
    cob = []
    for _ in range(200):
        y = rng.standard_t(4, 400)
        cal, teste = y[:200], y[200:]
        lo, hi = M.intervalo_conformal(np.zeros(200), np.ones(200), np.abs(cal), 0.1)
        cob.append(np.mean((lo <= teste) & (teste <= hi)))
    assert np.mean(cob) >= 0.9 - 0.01


def test_aci_recupera_cobertura_de_longo_prazo_sob_quebra():
    rng = np.random.default_rng(1)
    T = 1200
    y = rng.normal(0, 1, T)
    y[400:] *= 3.0  # variância triplica: o split fixo sub-cobre
    p, e = np.zeros(T), np.ones(T)
    cal = np.abs(rng.normal(0, 1, 300))
    lo_s, hi_s = M.intervalo_conformal(p, e, cal, 0.1)
    pos = slice(400, T)
    split_pos = np.mean((lo_s[pos] <= y[pos]) & (y[pos] <= hi_s[pos]))
    gamma = 0.02
    r = M.aci(p, y, e, alpha=0.1, gamma=gamma, janela=200, atraso=3, escores_iniciais=cal)
    assert split_pos < 0.75
    # garantia de longo prazo (Gibbs & Candès 2021, Prop. 4.1), folgada pelo atraso de rótulo
    limite = (max(0.1, 0.9) + gamma) / (gamma * T) + 3 / T
    assert abs(np.nanmean(r["cobre"]) - 0.9) <= limite + 0.01
    assert np.nanmean(r["cobre"][pos]) > split_pos + 0.1
