"""E1 — Shrinkage em cauda longa. DADOS 100% SINTÉTICOS, verdade conhecida.

Pergunta: Beta-Binomial empírico (EB) vs média agrupada vs regra de mínimo de
cliques vs fórmula fixa "M=20" (B18). E: Gamma-Poisson / lognormal para
RPC/lucro (B17).

Reprodutível: seed fixa. Só numpy + scipy. Rodar:
    python -I e1_shrinkage.py  [saida.json]

NADA aqui é medido em conta real. Nenhum número deste arquivo é parâmetro
operacional do VOLC.
"""
from __future__ import annotations

import json
import sys

import numpy as np
from scipy import optimize, special

SEED = 20261014
R = 40            # réplicas por cenário
N = 3000          # entidades (keywords/grupos) por réplica
MU = 0.05         # taxa média verdadeira (ex.: CVR)
KAPPAS = [2.0, 5.0, 20.0, 100.0, 500.0]   # concentração a+b do prior verdadeiro
M_GRID = np.unique(np.round(np.logspace(0, 3.4, 45), 2))
MIN_CLIQUES = [10, 30, 100]


def cliques_cauda_longa(rng, n):
    """Cliques por entidade ~ Zipf(1.6) truncado: a maioria com 1-3 cliques."""
    return np.minimum(rng.zipf(1.6, size=n), 20000)


def beta_binom_mle(x, n):
    """MLE de (a, b) da Beta-Binomial marginal, só com entidades n>=1."""
    m = n > 0
    x, n = x[m], n[m]

    def nll(theta):
        a, b = np.exp(theta)
        return -np.sum(special.betaln(x + a, n - x + b) - special.betaln(a, b))

    p0 = max(x.sum() / n.sum(), 1e-4)
    res = optimize.minimize(nll, x0=np.log([p0 * 10, (1 - p0) * 10]), method="Nelder-Mead",
                            options={"xatol": 1e-6, "fatol": 1e-6, "maxiter": 4000})
    a, b = np.exp(res.x)
    return float(a), float(b)


def cenario_taxas(kappa, rng):
    a_true, b_true = kappa * MU, kappa * (1 - MU)
    acc = {k: [] for k in ["raw", "pooled", "eb", "oracle", "fixo_M20"] + [f"min{k}" for k in MIN_CLIQUES]}
    acc_grid = np.zeros(len(M_GRID))
    vies_top = {k: [] for k in ["raw", "eb", "fixo_M20", "pooled"]}
    kappa_hat = []
    decisao = {k: [] for k in ["raw", "eb", "fixo_M20", "min30"]}
    for _ in range(R):
        n_tot = cliques_cauda_longa(rng, N)
        n_tr = rng.binomial(n_tot, 0.5)            # 1ª metade do período = treino
        p = rng.beta(a_true, b_true, size=N)
        x = rng.binomial(n_tr, p)
        pooled = x.sum() / n_tr.sum()
        raw = np.where(n_tr > 0, x / np.maximum(n_tr, 1), pooled)
        a_hat, b_hat = beta_binom_mle(x, n_tr)
        kappa_hat.append(a_hat + b_hat)
        est = {
            "raw": raw,
            "pooled": np.full(N, pooled),
            "eb": (x + a_hat) / (n_tr + a_hat + b_hat),
            "oracle": (x + a_true) / (n_tr + a_true + b_true),
            "fixo_M20": (x + 20 * pooled) / (n_tr + 20),
        }
        for k in MIN_CLIQUES:
            est[f"min{k}"] = np.where(n_tr >= k, raw, pooled)
        for k, v in est.items():
            acc[k].append(float(np.mean((v - p) ** 2)))
        for j, M in enumerate(M_GRID):
            acc_grid[j] += np.mean(((x + M * pooled) / (n_tr + M) - p) ** 2) / R
        # maldição do vencedor: viés nos 5% "melhores" segundo o próprio estimador
        for k in vies_top:
            v = est[k]
            top = v >= np.quantile(v, 0.95) if k != "pooled" else np.ones(N, bool)
            vies_top[k].append(float(np.mean(v[top] - p[top])))
        # decisão: "lucrativo" se p*V > CPC; V tal que só ~25% das entidades são de fato lucrativas
        limiar = np.quantile(p, 0.75)
        verdade = p > limiar
        for k in decisao:
            v = est[k]
            sel = v > limiar
            fp = float(np.mean(~verdade[sel])) if sel.any() else None
            decisao[k].append({"selecionadas": int(sel.sum()), "falso_lucrativo": fp,
                               "lucrativas_perdidas": float(np.mean(~sel[verdade]))})
    m_otimo = float(M_GRID[int(np.argmin(acc_grid))])
    resumo_dec = {}
    for k, lst in decisao.items():
        fps = [d["falso_lucrativo"] for d in lst if d["falso_lucrativo"] is not None]
        resumo_dec[k] = {
            "media_selecionadas": float(np.mean([d["selecionadas"] for d in lst])),
            "taxa_falso_lucrativo": float(np.mean(fps)) if fps else None,
            "taxa_lucrativas_perdidas": float(np.mean([d["lucrativas_perdidas"] for d in lst])),
        }
    return {
        "kappa_verdadeiro": kappa,
        "kappa_estimado_mediana": float(np.median(kappa_hat)),
        "M_otimo_grade": m_otimo,
        "mse_x1e4": {k: round(float(np.mean(v)) * 1e4, 4) for k, v in acc.items()},
        "mse_x1e4_M20_vs_Motimo": [round(float(acc_grid[np.argmin(np.abs(M_GRID - 20))]) * 1e4, 4),
                                   round(float(acc_grid.min()) * 1e4, 4)],
        "vies_top5pct": {k: round(float(np.mean(v)), 5) for k, v in vies_top.items()},
        "decisao_lucrativo": resumo_dec,
    }


def cenario_rpc_lucro(rng):
    """Por que Gamma-Poisson é para CONTAGEM e lognormal não representa lucro.

    Mundo sintético de arbitragem: cada clique gera pageviews ~ Poisson(lambda_i),
    lambda_i ~ Gamma(k, theta) (heterogeneidade entre entidades); receita por
    pageview = RPM/1000 fixo; custo por clique = CPC_i. Lucro por clique pode
    ser NEGATIVO.
    """
    n_ent = 5000
    k_shape, theta = 2.0, 0.9            # média 1,8 pageview monetizada/clique
    rpm = 9.0                             # R$ por mil pageviews (sintético)
    n = cliques_cauda_longa(rng, n_ent)
    lam = rng.gamma(k_shape, theta, size=n_ent)
    cpc = rng.uniform(0.008, 0.025, size=n_ent)
    pv = rng.poisson(lam * n)
    lucro_true = lam * rpm / 1000 - cpc
    lucro_obs = pv / n * rpm / 1000 - cpc
    # Gamma-Poisson EB (método dos momentos sobre taxas pv/n, ponderado)
    taxa = pv / n
    m1 = pv.sum() / n.sum()
    var_between = max(np.average((taxa - m1) ** 2, weights=n) - m1 / np.mean(n), 1e-9)
    shape_hat = m1 ** 2 / var_between
    rate_hat = m1 / var_between
    lam_eb = (pv + shape_hat) / (n + rate_hat)
    lucro_eb = lam_eb * rpm / 1000 - cpc
    # "lognormal" sobre lucro observado: log de lucro <= 0 é indefinido
    frac_lucro_nao_pos = float(np.mean(lucro_obs <= 0))
    frac_receita_zero = float(np.mean(pv == 0))
    # Tentativa "lognormal só nos positivos": descarta entidades -> viés de seleção
    pos = lucro_obs > 0
    mu_ln = np.mean(np.log(lucro_obs[pos]))
    sd_ln = np.std(np.log(lucro_obs[pos]))
    media_lognormal_pos = float(np.exp(mu_ln + sd_ln ** 2 / 2))
    return {
        "entidades": n_ent,
        "fracao_entidades_lucro_observado_nao_positivo": round(frac_lucro_nao_pos, 4),
        "fracao_entidades_receita_zero": round(frac_receita_zero, 4),
        "lucro_medio_por_clique_verdadeiro_ponderado": round(float(np.average(lucro_true, weights=n)), 6),
        "lucro_medio_lognormal_so_positivos": round(media_lognormal_pos, 6),
        "mse_lucro_por_clique_x1e6": {
            "raw": round(float(np.mean((lucro_obs - lucro_true) ** 2)) * 1e6, 4),
            "gamma_poisson_eb_em_pageviews": round(float(np.mean((lucro_eb - lucro_true) ** 2)) * 1e6, 4),
        },
        "gamma_estimado": {"shape": round(float(shape_hat), 3), "rate": round(float(rate_hat), 3),
                           "shape_verdadeiro": k_shape, "rate_verdadeiro": round(1 / theta, 3)},
        "leitura": ("Gamma-Poisson encolhe a CONTAGEM (pageviews/clique) e o lucro é derivado "
                    "depois (lambda*RPM - CPC), preservando lucro negativo. Lognormal exige valor > 0: "
                    "descarta as entidades com lucro <= 0 e superestima o lucro médio."),
    }


def main():
    rng = np.random.default_rng(SEED)
    saida = {
        "rotulo": "SINTETICO — verdade conhecida; nenhum dado real; nao e parametro operacional",
        "seed": SEED, "replicas": R, "entidades": N, "mu": MU,
        "distribuicao_cliques": "Zipf(1.6) truncado em 20000; treino = Binomial(n, 0.5)",
        "cenarios_taxa": [cenario_taxas(k, rng) for k in KAPPAS],
        "rpc_lucro": cenario_rpc_lucro(rng),
    }
    n_demo = cliques_cauda_longa(np.random.default_rng(SEED), N)
    saida["cauda"] = {"frac_ate_2_cliques": float(np.mean(n_demo <= 2)),
                      "frac_cliques_nas_entidades_ate_2": float(n_demo[n_demo <= 2].sum() / n_demo.sum())}
    destino = sys.argv[1] if len(sys.argv) > 1 else "e1_resultado.json"
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump(saida, fh, indent=1, ensure_ascii=False)
    for c in saida["cenarios_taxa"]:
        print(f"kappa={c['kappa_verdadeiro']:>6} kappa_hat={c['kappa_estimado_mediana']:>8.2f} "
              f"M_otimo={c['M_otimo_grade']:>8.2f} mse(x1e4)={c['mse_x1e4']} M20_vs_Mot={c['mse_x1e4_M20_vs_Motimo']}")
        print("   vies_top5:", c["vies_top5pct"])
        print("   decisao:", json.dumps(c["decisao_lucrativo"]))
    print(json.dumps(saida["rpc_lucro"], ensure_ascii=False, indent=1))
    print(saida["cauda"])


if __name__ == "__main__":
    main()
