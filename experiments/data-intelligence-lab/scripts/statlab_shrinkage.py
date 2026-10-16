"""Stat Lab — run completo de shrinkage Empirical Bayes (simulação com seed, sem dado real).

Uso (da raiz do repo):
  experiments/data-intelligence-lab/.venv/bin/python experiments/data-intelligence-lab/scripts/statlab_shrinkage.py
Grava results/statlab/shrinkage.json.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "src"))

import numpy as np  # noqa: E402

from volc_dil.statlab.base import envelope, gravar_json, rngs  # noqa: E402
from volc_dil.statlab.shrinkage import (  # noqa: E402
    agregar_replicas,
    gerar_taxas_beta,
    gerar_taxas_bimodal,
    gerar_taxas_informativas,
    replica_contagens,
    replica_receita,
    replica_taxas,
)

K = 300
TOP_K = 10
NIVEL = 0.9
EST_TAXA = ["cru", "media_grupo", "eb_momentos", "eb_mle"]
EST_RECEITA = ["cru", "media_grupo", "gamma_poisson_reais", "gamma_poisson_centavos",
               "eb_normal_var_empirica", "hurdle_beta_lognormal"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261015)
    ap.add_argument("--n-replicas", type=int, default=300)
    ap.add_argument("--saida", default=str(LAB / "results" / "statlab" / "shrinkage.json"))
    args = ap.parse_args()
    R = args.n_replicas

    cen_taxas = {
        "cvr_beta_unimodal": dict(mediana_n=50, sigma_n=1.0, gerador=gerar_taxas_beta(0.03, 60)),
        "cvr_bimodal_vencedores_raros": dict(mediana_n=50, sigma_n=1.0,
                                             gerador=gerar_taxas_bimodal(0.02, 0.08, 0.05, 200)),
        "cvr_n_informativo": dict(mediana_n=50, sigma_n=1.0,
                                  gerador=gerar_taxas_informativas(0.03, 60, 0.4)),
        "cvr_n_grande_pouco_ganho": dict(mediana_n=5000, sigma_n=0.3, gerador=gerar_taxas_beta(0.03, 60)),
        "cvr_sem_heterogeneidade": dict(mediana_n=50, sigma_n=1.0, gerador=gerar_taxas_beta(0.03, 1e6)),
    }
    resultados: dict = {"taxas_beta_binomial": {}, "contagens_gamma_poisson": {}, "receita_monetaria": {}}
    for i, (nome, c) in enumerate(cen_taxas.items()):
        seed_c = args.seed + 100 * i
        reps = [replica_taxas(r, K, c["mediana_n"], c["sigma_n"], c["gerador"], TOP_K, NIVEL)
                for r in rngs(seed_c, R)]
        status = {}
        for r in reps:
            for k, v in r["status_prior"].items():
                status.setdefault(k, {}).setdefault(v, 0)
                status[k][v] += 1
        resultados["taxas_beta_binomial"][nome] = {
            "seed_cenario": seed_c, "mediana_n": c["mediana_n"], "sigma_n": c["sigma_n"],
            "estimadores": agregar_replicas(reps, EST_TAXA), "status_prior_contagem": status,
            "unidades_sem_dados_media": float(np.mean([r["n_unidades_sem_dados"] for r in reps])),
        }

    cen_cont = {
        "contagem_gamma_heterogenea": dict(mediana_e=20, sigma_e=1.0, media_taxa=0.5, forma=2.0),
        "contagem_gamma_quase_homogenea": dict(mediana_e=20, sigma_e=1.0, media_taxa=0.5, forma=200.0),
    }
    for i, (nome, c) in enumerate(cen_cont.items()):
        seed_c = args.seed + 10_000 + 100 * i
        reps = [replica_contagens(r, K, c["mediana_e"], c["sigma_e"], c["media_taxa"], c["forma"], TOP_K, NIVEL)
                for r in rngs(seed_c, R)]
        resultados["contagens_gamma_poisson"][nome] = {
            "seed_cenario": seed_c, **c, "estimadores": agregar_replicas(reps, EST_TAXA)}

    cen_rec = {
        "receita_lognormal_zero_inflada": dict(K=K, mediana_n=80, sigma_n=1.0, media_cvr=0.03, conc_cvr=60,
                                               mediana_valor=40.0, tau_log_valor=0.4, sigma_log_valor=1.0),
        "receita_cauda_pesada_sigma2": dict(K=K, mediana_n=80, sigma_n=1.0, media_cvr=0.03, conc_cvr=60,
                                            mediana_valor=40.0, tau_log_valor=0.4, sigma_log_valor=2.0),
        "receita_valor_pareto_hurdle_mal_especificado": dict(
            K=K, mediana_n=80, sigma_n=1.0, media_cvr=0.03, conc_cvr=60, mediana_valor=40.0,
            tau_log_valor=0.4, sigma_log_valor=1.0, alpha_pareto=1.8),
    }
    for i, (nome, c) in enumerate(cen_rec.items()):
        seed_c = args.seed + 20_000 + 100 * i
        reps = [replica_receita(r, TOP_K, NIVEL, 2000, **c) for r in rngs(seed_c, R)]
        fs = np.array([[r["gp_fator_shrink_mediano"]["reais"], r["gp_fator_shrink_mediano"]["centavos"]]
                       for r in reps])
        resultados["receita_monetaria"][nome] = {
            "seed_cenario": seed_c, **c, "estimadores": agregar_replicas(reps, EST_RECEITA),
            "gamma_poisson_peso_do_prior_mediano": {"reais": float(np.median(fs[:, 0])),
                                                    "centavos": float(np.median(fs[:, 1]))},
        }

    parametros = {"K_unidades": K, "top_k": TOP_K, "nivel_intervalo": NIVEL,
                  "nota": "n, CVR, valores e top-k são parâmetros de cenário, não defaults operacionais",
                  "metricas": {
                      "mse_relativo_ao_cru": "MSE / MSE do estimador cru na mesma réplica (unidades com n > 0)",
                      "vencedores_por_sorte_topk": "unidades no top-k estimado que não estão no top-k verdadeiro",
                      "regret_topk": "1 - média verdadeira do top-k escolhido / média do top-k verdadeiro",
                      "inclinacao_calibracao": "cov(est, verdade)/var(est); 1 = calibrado, <1 = estimativas dispersas demais",
                      "cobertura": f"fração das unidades cuja verdade cai no intervalo {NIVEL:.0%}",
                  }}
    env = envelope("shrinkage", args.seed, R, parametros, resultados)
    n = gravar_json(args.saida, env)
    print(f"gravado {args.saida} ({n} bytes)")


if __name__ == "__main__":
    main()
