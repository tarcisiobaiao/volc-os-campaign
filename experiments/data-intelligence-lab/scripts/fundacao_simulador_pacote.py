"""Gera o pacote de datasets SINTÉTICOS do Simulator Lab (fundação 2026-10-16) + medição de performance.

Uso (da raiz do repositório):
    OMP_NUM_THREADS=2 experiments/data-intelligence-lab/.venv/bin/python -I \
        experiments/data-intelligence-lab/scripts/fundacao_simulador_pacote.py [--seed N] [--verificar] [--sem-performance]

--verificar  regenera em memória e exige igualdade byte a byte com o pacote em disco (sem escrever).
Saída: experiments/data-intelligence-lab/results/fundacao/simulador/{MANIFEST.json,PERFORMANCE.json,<cenario>/...}
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

RAIZ_LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ_LAB / "src"))

from volc_dil.contracts.fingerprint import json_canonico, versoes  # noqa: E402
from volc_dil.fundacao.simulador import NOMES, VERSAO_SIMULADOR, gerar_mundo, observar, cenario  # noqa: E402
from volc_dil.fundacao.simulador.pacote import conteudo_cenario, gerar_pacote, sha256_de_bytes  # noqa: E402

DESTINO = RAIZ_LAB / "results" / "fundacao" / "simulador"
SEED_PADRAO = 20261016


def medir_performance(seed: int, repeticoes: int = 3) -> dict:
    """Tempo de parede do gerador e do observador no tamanho do catálogo (50×30×24; escala 500×30×24)."""
    saida = {}
    for nome, rep in (("estavel", repeticoes), ("escala_10x", 1)):
        e = cenario(nome)
        tm, to, nreg = [], [], 0
        for _ in range(rep):
            t0 = time.perf_counter()
            m = gerar_mundo(e.mundo, seed)
            t1 = time.perf_counter()
            leit = observar(m, e.observador, cenario=nome)
            t2 = time.perf_counter()
            tm.append(t1 - t0)
            to.append(t2 - t1)
            nreg = len(leit.registros)
        saida[nome] = {"n_campanhas": e.mundo.n_campanhas, "n_dias": e.mundo.n_dias, "horas": e.mundo.n_dias * 24,
                       "celulas_campanha_hora_dispositivo": e.mundo.n_campanhas * e.mundo.n_dias * 24 * 3,
                       "n_registros": nreg, "repeticoes": rep,
                       "mundo_s_mediana": round(sorted(tm)[len(tm) // 2], 3),
                       "observador_s_mediana": round(sorted(to)[len(to) // 2], 3),
                       "total_s_mediana": round(sorted(a + b for a, b in zip(tm, to))[len(tm) // 2], 3)}
    return {"natureza": "medicao_nao_deterministica", "seed": seed, "versao_simulador": VERSAO_SIMULADOR,
            "omp_num_threads": __import__("os").environ.get("OMP_NUM_THREADS"), "versoes": versoes(),
            "medidas": saida}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED_PADRAO)
    ap.add_argument("--verificar", action="store_true")
    ap.add_argument("--sem-performance", action="store_true")
    a = ap.parse_args()
    if a.verificar:
        manif = json.loads((DESTINO / "MANIFEST.json").read_text(encoding="utf-8"))
        falhas = []
        for nome in manif["cenarios"]:
            for arq, dados in conteudo_cenario(nome, manif["seed"]).items():
                if sha256_de_bytes(dados) != manif["arquivos"][f"{nome}/{arq}"]["sha256"]:
                    falhas.append(f"{nome}/{arq}")
        print(json.dumps({"verificado": not falhas, "divergentes": falhas}, ensure_ascii=False))
        return 1 if falhas else 0
    t0 = time.perf_counter()
    manif = gerar_pacote(DESTINO, a.seed, NOMES)
    print(json.dumps({"bytes_total": manif["bytes_total"], "fingerprint": manif["fingerprint"],
                      "tempo_s": round(time.perf_counter() - t0, 2)}, ensure_ascii=False))
    if not a.sem_performance:
        perf = medir_performance(a.seed)
        (DESTINO / "PERFORMANCE.json").write_text(json_canonico(perf) + "\n", encoding="utf-8")
        print(json.dumps(perf["medidas"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
