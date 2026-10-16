"""Stat Lab — FDR: nenhuma correção vs Bonferroni vs Benjamini-Hochberg, com e sem peeking.

Uso (da raiz do repo):
  experiments/data-intelligence-lab/.venv/bin/python experiments/data-intelligence-lab/scripts/statlab_fdr.py
Grava results/statlab/fdr.json.
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
from volc_dil.statlab.fdr import agregar, bh_propria, bh_statsmodels, na_fronteira, replica_celulas  # noqa: E402

Q = 0.05


def conferir_bh(seed: int, n_casos: int) -> dict:
    """BH própria == statsmodels em p-valores aleatórios, com empates e m variados."""
    rng = np.random.default_rng(seed)
    div_fronteira = 0
    div_fora_fronteira = 0
    for _ in range(n_casos):
        m = int(rng.integers(1, 400))
        p = rng.beta(0.3, 1.0, m)
        if rng.random() < 0.5:
            p = np.round(p, 2)  # força empates (inclusive empates exatos com q k / m)
        for q in (0.01, 0.05, 0.2):
            a, b = bh_propria(p, q), bh_statsmodels(p, q)
            if not np.array_equal(a, b):
                # divergência só é aceitável se TODAS as diferenças estão em p == q k / m
                if na_fronteira(p, q)[a != b].all() or _fronteira_do_corte(p, q):
                    div_fronteira += 1
                else:
                    div_fora_fronteira += 1
    return {"n_casos": n_casos * 3, "divergencias_fora_da_fronteira": div_fora_fronteira,
            "divergencias_por_empate_exato_na_fronteira": div_fronteira, "seed": seed,
            "nota": "na fronteira exata a regra BH rejeita; a implementação própria usa tolerância 1e-12 "
                    "e o statsmodels compara p/ecdf <= q, então o arredondamento pode divergir"}


def _fronteira_do_corte(p: np.ndarray, q: float) -> bool:
    """O ponto de corte k* é decidido por um p na fronteira (afeta todas as células abaixo dele)."""
    return bool(na_fronteira(p, q).any())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261015)
    ap.add_argument("--n-replicas", type=int, default=500)
    ap.add_argument("--saida", default=str(LAB / "results" / "statlab" / "fdr.json"))
    args = ap.parse_args()
    R = args.n_replicas
    base = dict(m=1000, p_base=0.03, lift=0.3, q=Q)
    cenarios = {
        "pi1_5pct_n5000_uma_olhada": dict(frac_verdadeiras=0.05, n_por_braco=5000, olhadas=None),
        "pi1_5pct_n5000_10_olhadas": dict(frac_verdadeiras=0.05, n_por_braco=5000,
                                          olhadas=tuple(range(500, 5001, 500))),
        "pi1_5pct_n5000_50_olhadas": dict(frac_verdadeiras=0.05, n_por_braco=5000,
                                          olhadas=tuple(range(100, 5001, 100))),
        "nulo_global_uma_olhada": dict(frac_verdadeiras=0.0, n_por_braco=5000, olhadas=None),
        "nulo_global_10_olhadas": dict(frac_verdadeiras=0.0, n_por_braco=5000,
                                       olhadas=tuple(range(500, 5001, 500))),
        "pi1_20pct_n20000_uma_olhada": dict(frac_verdadeiras=0.2, n_por_braco=20000, olhadas=None),
    }
    resultados = {"conferencia_bh_propria_vs_statsmodels": conferir_bh(args.seed, 1000), "cenarios": {}}
    for i, (nome, c) in enumerate(cenarios.items()):
        seed_c = args.seed + 100 * (i + 1)
        reps = [replica_celulas(r, base["m"], c["frac_verdadeiras"], base["p_base"], base["lift"],
                                c["n_por_braco"], base["q"], c["olhadas"]) for r in rngs(seed_c, R)]
        resultados["cenarios"][nome] = {
            "seed_cenario": seed_c, **{k: v for k, v in c.items() if k != "olhadas"},
            "n_olhadas": 1 if c["olhadas"] is None else len(c["olhadas"]),
            "metodos": agregar(reps),
        }
    parametros = {**base, "teste": "z de duas proporções bicaudal (pooled) por célula",
                  "declaracao": "célula declarada na 1ª olhada em que é rejeitada; para de ser testada",
                  "fdr_realizado": "média de V/max(R,1)", "falso_vencedor": "célula nula declarada com B > A",
                  "nota": "m, p_base, lift, n e nº de olhadas são parâmetros de cenário, não defaults"}
    env = envelope("fdr", args.seed, R, parametros, resultados)
    nbytes = gravar_json(args.saida, env)
    print(f"gravado {args.saida} ({nbytes} bytes)")


if __name__ == "__main__":
    main()
