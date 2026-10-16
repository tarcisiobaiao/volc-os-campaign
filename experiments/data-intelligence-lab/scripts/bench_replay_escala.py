"""Onde o replay econômico v0 gasta tempo quando o número de unidades cresce (SINTÉTICO).

Uso (da raiz do lab): .venv/bin/python -I scripts/bench_replay_escala.py
Mede uma execução da política `proportional` para N unidades × 20 dias e separa o tempo de
`Snapshot.construir` (contrato), da política e da emissão do mundo. Saída:
results/bench/replay_escala.json. Uma repetição por ponto (ordem de grandeza, não mediana).
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from volc_dil.contracts import Snapshot, manifesto_execucao  # noqa: E402
from volc_dil.replay import Proporcional, cenario_mini  # noqa: E402
from volc_dil.replay import motor  # noqa: E402
from volc_dil.replay.cenario import Mundo  # noqa: E402

SAIDA = RAIZ / "results" / "bench" / "replay_escala.json"


def medir(n_unidades: int, n_dias: int = 20) -> dict:
    espec = replace(cenario_mini(), nome="escala", n_unidades=n_unidades, n_unidades_outra_moeda=1, n_dias=n_dias)
    acum = {"snapshot_s": 0.0, "politica_s": 0.0, "emissao_s": 0.0, "obs_por_snapshot": []}
    orig_construir = Snapshot.construir
    orig_emitir = Mundo.emitir
    pol = Proporcional()
    orig_decidir = pol.decidir

    def construir(*a, **k):
        t = time.perf_counter()
        s = orig_construir(*a, **k)
        acum["snapshot_s"] += time.perf_counter() - t
        acum["obs_por_snapshot"].append(len(s.observacoes))
        return s

    def emitir(self, *a, **k):
        t = time.perf_counter()
        r = orig_emitir(self, *a, **k)
        acum["emissao_s"] += time.perf_counter() - t
        return r

    def decidir(s, c):
        t = time.perf_counter()
        r = orig_decidir(s, c)
        acum["politica_s"] += time.perf_counter() - t
        return r

    pol.decidir = decidir
    motor.Snapshot = type("S", (), {"construir": staticmethod(construir)})
    Mundo.emitir = emitir
    try:
        t0 = time.perf_counter()
        motor.executar(espec, pol)
        total = time.perf_counter() - t0
    finally:
        motor.Snapshot = Snapshot
        Mundo.emitir = orig_emitir
    obs = acum.pop("obs_por_snapshot")
    return {"n_unidades": n_unidades + 1, "n_dias": n_dias, "decisoes": n_dias - 1, "total_s": round(total, 3),
            **{k: round(v, 3) for k, v in acum.items()},
            "obs_por_snapshot_max": max(obs), "snapshot_ms_por_decisao": round(acum["snapshot_s"] / (n_dias - 1) * 1000, 2)}


def main() -> int:
    pontos = [medir(n) for n in (8, 50, 200, 500)]
    for p in pontos:
        print(p)
    saida = {"natureza": "sintetico",
             "manifesto": manifesto_execucao(nome="replay_escala_v0", seed=cenario_mini().seed, entradas={},
                                             parametros={"unidades": [8, 50, 200, 500], "dias": 20,
                                                         "politica": "proportional", "janela_consulta_dias": 14}),
             "nota": "1 repetição por ponto; tempos de parede; ordem de grandeza.",
             "pontos": pontos}
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(saida, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
