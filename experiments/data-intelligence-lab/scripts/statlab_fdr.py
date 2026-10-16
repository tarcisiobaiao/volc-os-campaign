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
from volc_dil.statlab.fdr import agregar, bh_propria, bh_statsmodels, replica_celulas  # noqa: E402

Q = 0.05


def bh_mutante_pontual(p: np.ndarray, q: float) -> np.ndarray:
    """Contraprova da conferência: BH ERRADA sem o passo step-up (rejeita só p_(i) <= q i/m pontual)."""
    p = np.asarray(p, dtype=float)
    o = np.argsort(p, kind="mergesort")
    r = np.zeros(p.size, dtype=bool)
    r[o] = p[o] <= q * np.arange(1, p.size + 1) / p.size
    return r


def conferir_bh(seed: int, n_casos: int, bh=bh_propria) -> dict:
    """BH própria == statsmodels em p-valores aleatórios, com empates e m variados.
    Uma divergência só é atribuída à fronteira se o PONTO DE CORTE que as separa é um empate exato:
    com k_max = maior nº de rejeições entre as duas, o k_max-ésimo menor p deve ser == q*k_max/m
    (até rtol 1e-9). Qualquer outra divergência conta como defeito."""
    rng = np.random.default_rng(seed)
    div_fronteira = 0
    div_fora_fronteira = 0
    exemplos = []
    for _ in range(n_casos):
        m = int(rng.integers(1, 400))
        p = rng.beta(0.3, 1.0, m)
        if rng.random() < 0.5:
            p = np.round(p, 2)  # força empates (inclusive empates exatos com q k / m)
        for q in (0.01, 0.05, 0.2):
            a, b = bh(p, q), bh_statsmodels(p, q)
            if np.array_equal(a, b):
                continue
            if _divergencia_no_corte_exato(p, q, a, b):
                div_fronteira += 1
                if len(exemplos) < 3:
                    k = int(max(a.sum(), b.sum()))
                    exemplos.append({"m": m, "q": q, "k_corte": k, "p_no_corte": float(np.sort(p)[k - 1]),
                                     "rejeicoes_propria": int(a.sum()), "rejeicoes_statsmodels": int(b.sum())})
            else:
                div_fora_fronteira += 1
    return {"n_casos": n_casos * 3, "divergencias_fora_da_fronteira": div_fora_fronteira,
            "divergencias_por_empate_exato_na_fronteira": div_fronteira, "exemplos_fronteira": exemplos,
            "seed": seed,
            "nota": "na fronteira exata a regra BH rejeita; a implementação própria usa tolerância 1e-12 "
                    "e o statsmodels compara p/ecdf <= q, então o arredondamento pode divergir"}


def _divergencia_no_corte_exato(p: np.ndarray, q: float, a: np.ndarray, b: np.ndarray) -> bool:
    """Step-up: as duas regras só podem diferir no nº de rejeições k. A divergência é de ponto
    flutuante se, e só se, ambos os conjuntos são prefixos por valor, o menor está contido no maior e
    o p do corte maior está na fronteira q k / m."""
    ka, kb = int(a.sum()), int(b.sum())
    if ka == kb:
        return False
    # step-up rejeita sempre um PREFIXO por valor: {p <= max p rejeitado} (empates entram juntos)
    for r in (a, b):
        if r.any() and not np.array_equal(r, p <= p[r].max()):
            return False
    menor, maior = (a, b) if ka < kb else (b, a)
    if np.any(menor & ~maior):
        return False
    k = max(ka, kb)
    p_corte = np.sort(p)[k - 1]
    return bool(np.isclose(p_corte, q * k / p.size, rtol=1e-9, atol=0))


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
    conf = conferir_bh(args.seed, 1000)
    conf["contraprova_mutante_sem_step_up_divergencias_fora_da_fronteira"] = \
        conferir_bh(args.seed, 1000, bh_mutante_pontual)["divergencias_fora_da_fronteira"]
    resultados = {"conferencia_bh_propria_vs_statsmodels": conf, "cenarios": {}}
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
