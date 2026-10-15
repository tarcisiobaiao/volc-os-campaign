"""E3 — Avaliação off-policy (IPS / SNIPS / DM / DR). DADOS 100% SINTÉTICOS.

Prova a MECÂNICA com propensões conhecidas e mostra onde ela quebra:
  A) boa sobreposição, n grande;
  B) n pequeno (a ordem de grandeza de decisões de orçamento que o VOLC
     registraria em meses);
  C) sem suporte: a política de log nunca toma a ação que a política alvo quer
     em parte dos contextos;
  D) propensão inventada: o log não guardou a probabilidade (como o ledger
     v10_02 hoje) e o analista "assume" uniforme.

NÃO alega ganho real. Reward = lucro diário sintético normalizado.
Rodar: python -I e3_ope.py [saida.json] [arrays.npz]
"""
from __future__ import annotations

import json
import sys

import numpy as np

SEED = 20261014
K = 3                        # 0 reduzir 20%, 1 manter, 2 aumentar 20%
R = 300                      # réplicas por cenário
ACOES = ["reduzir_20pct", "manter", "aumentar_20pct"]


def q(x, a):
    """Recompensa esperada (não linear de propósito: o DM linear fica mal especificado)."""
    base = 0.5 * x[:, 1] + 0.3 * np.sin(2 * x[:, 2])
    efeito = np.stack([-0.6 * x[:, 0], np.zeros(len(x)), 0.9 * x[:, 0] - 0.4 * x[:, 0] ** 2], axis=1)
    return base[:, None] + efeito if a is None else (base + efeito[np.arange(len(x)), a])


def politica_log(x, cenario):
    s = np.stack([-x[:, 0], np.zeros(len(x)), x[:, 0]], axis=1)
    p = np.exp(1.2 * s)
    if cenario == "C_sem_suporte":
        p[:, 2] = np.where(x[:, 0] < 0.3, 0.0, p[:, 2])    # nunca aumenta abaixo de 0,3
    return p / p.sum(1, keepdims=True)


def politica_alvo(x):
    """Determinística: aumenta se x0 > 0, senão reduz."""
    pi = np.zeros((len(x), K))
    pi[np.arange(len(x)), np.where(x[:, 0] > 0, 2, 0)] = 1.0
    return pi


def contexto(rng, n):
    return rng.normal(size=(n, 3))


def valor_verdadeiro(rng):
    x = contexto(rng, 400_000)
    return float(np.mean(np.sum(politica_alvo(x) * q(x, None), axis=1)))


def dm_modelo(x, a, r):
    """Ridge linear por ação (mal especificado de propósito)."""
    X = np.column_stack([np.ones(len(x)), x])
    coefs = []
    for k in range(K):
        m = a == k
        if m.sum() < 5:
            coefs.append(np.zeros(X.shape[1]))
            continue
        A = X[m].T @ X[m] + 1.0 * np.eye(X.shape[1])
        coefs.append(np.linalg.solve(A, X[m].T @ r[m]))
    return lambda xx: np.column_stack([np.column_stack([np.ones(len(xx)), xx]) @ c for c in coefs])


def estimar(x, a, r, pscore_usado, pi_e, qhat):
    n = len(x)
    w = pi_e[np.arange(n), a] / pscore_usado
    ips_i = w * r
    dm_i = np.sum(pi_e * qhat, axis=1)
    dr_i = dm_i + w * (r - qhat[np.arange(n), a])
    out = {}
    for nome, v in (("IPS", ips_i), ("DM", dm_i), ("DR", dr_i)):
        out[nome] = (float(v.mean()), float(v.std(ddof=1) / np.sqrt(n)))
    out["SNIPS"] = (float(ips_i.sum() / w.sum()), None)
    out["_peso_max"] = float(w.max())
    out["_n_efetivo"] = float(w.sum() ** 2 / np.sum(w ** 2))
    return out


def rodar(cenario, n, rng, v_true, guardar=None):
    acum = {k: [] for k in ("IPS", "SNIPS", "DM", "DR")}
    cob = {k: [] for k in ("IPS", "DR")}
    pesos, neff, sem_suporte = [], [], []
    for i in range(R):
        x = contexto(rng, n)
        p0 = politica_log(x, cenario)
        a = np.array([rng.choice(K, p=pp) for pp in p0])
        r = q(x, a) + rng.normal(0, 1.0, n)
        pi_e = politica_alvo(x)
        # fração do log em que o alvo quer uma ação de propensão 0 no log
        alvo = pi_e.argmax(1)
        sem_suporte.append(float(np.mean(p0[np.arange(n), alvo] == 0)))
        pscore_verdadeiro = p0[np.arange(n), a]
        pscore = np.full(n, 1 / K) if cenario == "D_propensao_inventada" else pscore_verdadeiro
        qhat = dm_modelo(x, a, r)(x)
        est = estimar(x, a, r, pscore, pi_e, qhat)
        for k in acum:
            acum[k].append(est[k][0])
        for k in cob:
            m, se = est[k]
            cob[k].append(abs(m - v_true) <= 1.96 * se)
        pesos.append(est["_peso_max"]); neff.append(est["_n_efetivo"])
        if guardar is not None and i == 0:
            np.savez(guardar, x=x, a=a, r=r, pscore=pscore_verdadeiro, pi_e=pi_e, qhat=qhat)
    res = {"cenario": cenario, "n_log": n, "replicas": R, "valor_verdadeiro": round(v_true, 4),
           "fracao_log_sem_suporte_para_o_alvo": round(float(np.mean(sem_suporte)), 4),
           "peso_max_mediano": round(float(np.median(pesos)), 2),
           "n_efetivo_mediano": round(float(np.median(neff)), 1)}
    for k, v in acum.items():
        v = np.array(v)
        res[k] = {"vies": round(float(v.mean() - v_true), 4), "rmse": round(float(np.sqrt(np.mean((v - v_true) ** 2))), 4)}
    for k, v in cob.items():
        res[k]["cobertura_ic95"] = round(float(np.mean(v)), 3)
    return res


def main():
    rng = np.random.default_rng(SEED)
    v_true = valor_verdadeiro(rng)
    x = contexto(rng, 400_000)
    v_log = float(np.mean(np.sum(politica_log(x, "A") * q(x, None), axis=1)))
    npz = sys.argv[2] if len(sys.argv) > 2 else "e3_replica0_A.npz"
    cenarios = [
        rodar("A_boa_sobreposicao", 5000, rng, v_true, guardar=npz),
        rodar("B_n_pequeno", 200, rng, v_true),
        rodar("C_sem_suporte", 5000, rng, v_true),
        rodar("D_propensao_inventada", 5000, rng, v_true),
    ]
    saida = {"rotulo": "SINTETICO — propensoes conhecidas; mecanica, nao ganho real",
             "seed": SEED, "acoes": ACOES, "valor_politica_de_log": round(v_log, 4),
             "valor_politica_alvo": round(v_true, 4), "cenarios": cenarios}
    destino = sys.argv[1] if len(sys.argv) > 1 else "e3_resultado.json"
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump(saida, fh, indent=1, ensure_ascii=False)
    print(json.dumps(saida, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
