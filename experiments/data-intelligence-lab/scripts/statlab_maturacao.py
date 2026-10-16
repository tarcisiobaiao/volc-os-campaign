"""Stat Lab — run completo de maturação/nowcasting (simulação com seed, sem dado real).

Uso (da raiz do repo):
  OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 experiments/data-intelligence-lab/.venv/bin/python \
      experiments/data-intelligence-lab/scripts/statlab_maturacao.py [--seed 20261015] [--n-mundos 300]
Grava results/statlab/maturacao.json.
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
from volc_dil.statlab.maturacao import (  # noqa: E402
    CenarioMaturacao,
    ConfigNowcast,
    agregar,
    avaliar_mundo,
    pmf_atraso_geometrica,
    pmf_atraso_lognormal,
)

A = 60          # idade de maturidade (hipótese de cenário)
N_COORTES = 150
AS_OF = 149


def cenarios() -> list[CenarioMaturacao]:
    receita_base = pmf_atraso_lognormal(mediana=4.0, sigma=1.0, maximo=A)
    return [
        CenarioMaturacao(N_COORTES, A, eventos_por_dia=400, mediana_valor=0.5, sigma_valor=0.4,
                         pmf_atraso=pmf_atraso_geometrica(media=0.3, maximo=A), nome="custo_rapido"),
        CenarioMaturacao(N_COORTES, A, eventos_por_dia=30, mediana_valor=2.0, sigma_valor=1.2,
                         pmf_atraso=receita_base, nome="receita_estavel"),
        CenarioMaturacao(N_COORTES, A, eventos_por_dia=30, mediana_valor=2.0, sigma_valor=1.2,
                         pmf_atraso=pmf_atraso_lognormal(mediana=12.0, sigma=1.2, maximo=A),
                         nome="receita_lenta_fator_perto_de_zero"),
        CenarioMaturacao(N_COORTES, A, eventos_por_dia=30, mediana_valor=2.0, sigma_valor=1.2,
                         pmf_atraso=pmf_atraso_geometrica(media=6.0, maximo=A, minimo=1),
                         nome="receita_d_mais_1_fator_zero_na_idade_0"),
        CenarioMaturacao(N_COORTES, A, eventos_por_dia=30, mediana_valor=2.0, sigma_valor=1.2,
                         pmf_atraso=receita_base, regime_inicio=AS_OF - 29,
                         pmf_atraso_regime=pmf_atraso_lognormal(mediana=10.0, sigma=1.0, maximo=A),
                         nome="receita_mudanca_regime_atraso_x2_5_ultimas_30_coortes"),
        CenarioMaturacao(N_COORTES, A, eventos_por_dia=30, mediana_valor=2.0, sigma_valor=1.2,
                         pmf_atraso=receita_base, regime_inicio=AS_OF - 29,
                         pmf_atraso_regime=pmf_atraso_lognormal(mediana=2.0, sigma=1.0, maximo=A),
                         nome="receita_mudanca_regime_atraso_metade_ultimas_30_coortes"),
    ]


def cenarios_granulares() -> list[CenarioMaturacao]:
    """Forma calibrada (não parâmetro) por fatos reais citados pelo coordenador: receita D-1 que
    muda até ~D+3; receita diária de campanha pequena entre ~US$0,02 e ~1,28, arredondada a 0,01,
    zero-inflada. Idade final 7 (hipótese: nada chega depois de D+7)."""
    A7 = 7
    pmf_d3 = np.array([0.35, 0.35, 0.2, 0.1, 0, 0, 0, 0], dtype=float)
    return [
        CenarioMaturacao(N_COORTES, A7, eventos_por_dia=4, mediana_valor=0.06, sigma_valor=1.0,
                         pmf_atraso=pmf_d3, granularidade=0.01,
                         nome="receita_baixa_magnitude_centavo_ate_d3"),
        CenarioMaturacao(N_COORTES, A7, eventos_por_dia=4, mediana_valor=0.06, sigma_valor=1.0,
                         pmf_atraso=pmf_d3, granularidade=None,
                         nome="receita_baixa_magnitude_sem_arredondar_ate_d3"),
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261015)
    ap.add_argument("--n-mundos", type=int, default=300)
    ap.add_argument("--saida", default=str(LAB / "results" / "statlab" / "maturacao.json"))
    args = ap.parse_args()

    cfgs = {
        "coortes_maduras": ConfigNowcast(janela_coortes=28, maturidade_minima=0.3, min_coortes=14,
                                         metodo="coortes_maduras", nivel_intervalo=0.9, n_bootstrap=200),
        "link_ratio": ConfigNowcast(janela_coortes=28, maturidade_minima=0.3, min_coortes=14,
                                    metodo="link_ratio", nivel_intervalo=0.9, n_bootstrap=0),
    }
    resultados = {}
    for i, cen in enumerate(cenarios() + cenarios_granulares()):
        seed_cen = args.seed + 1000 * i
        por_metodo = {}
        for nome_cfg, cfg in cfgs.items():
            # mesma seed por cenário => mesmos mundos para os dois métodos (pareado)
            mundos = [avaliar_mundo(cen, r, AS_OF, cfg) for r in rngs(seed_cen, args.n_mundos)]
            por_metodo[nome_cfg] = agregar(mundos)
            if nome_cfg == "coortes_maduras":
                v = np.concatenate([w["verdade"] for w in mundos])
                resumo_verdade = {"frac_zero": float(np.mean(v == 0)),
                                  "quantis_p5_p50_p95": [float(x) for x in np.quantile(v, [0.05, 0.5, 0.95])],
                                  "min": float(v.min()), "max": float(v.max())}
        resultados[cen.nome] = {"seed_cenario": seed_cen, "cenario": cen.descrever(),
                                "verdade_final_por_coorte": resumo_verdade, "por_metodo": por_metodo}

    parametros = {
        "as_of": AS_OF, "n_coortes": N_COORTES, "idade_final": A,
        "config": {k: {"janela_coortes": c.janela_coortes, "maturidade_minima": c.maturidade_minima,
                       "min_coortes": c.min_coortes, "metodo": c.metodo, "nivel_intervalo": c.nivel_intervalo,
                       "n_bootstrap": c.n_bootstrap} for k, c in cfgs.items()},
        "nota": "limiares (0.3, 14, 28, 90%) são parâmetros de cenário, não defaults operacionais",
        "avaliacao": "coortes as_of - a, a = 0..A-1; verdade = total final simulado (inclui o que chega até a idade A)",
    }
    env = envelope("maturacao", args.seed, args.n_mundos, parametros, resultados)
    n = gravar_json(args.saida, env)
    print(f"gravado {args.saida} ({n} bytes)")


if __name__ == "__main__":
    main()
