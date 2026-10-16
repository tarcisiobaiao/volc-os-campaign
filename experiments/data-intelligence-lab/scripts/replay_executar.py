"""Roda o replay econômico v0 (SINTÉTICO) em todos os cenários × seeds × políticas.

Uso (da raiz do lab): .venv/bin/python -I scripts/replay_executar.py [--seeds 1,2,3,4,5]
Saída: results/replay/replay_resultados.json (parte determinística + tempos separados).
O REPLAY-RESULTS.md é escrito à mão a partir deste JSON.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from volc_dil.contracts import manifesto_execucao, sha256_arquivo, sha256_de  # noqa: E402
from volc_dil.replay import baselines, catalogo, executar, proporcional_ingenua, relatorio_cenario  # noqa: E402
from volc_dil.replay.auditoria import auditar_null_vs_zero  # noqa: E402
from volc_dil.replay.politicas import Estatica  # noqa: E402

SAIDA = RAIZ / "results" / "replay" / "replay_resultados.json"
BASELINES = ["static", "equal", "proportional", "greedy_conservador"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1,2,3,4,5")
    args = ap.parse_args()
    seeds = [int(s) for s in args.seeds.split(",")]

    relatorios, tempos, auditorias = [], {}, {}
    for seed in seeds:
        for espec in catalogo(seed):
            execs = []
            for p in baselines() + [proporcional_ingenua()]:
                t0 = time.perf_counter()
                execs.append(executar(espec, p))
                tempos.setdefault(f"{espec.nome}/{p.nome}", []).append(time.perf_counter() - t0)
            relatorios.append(relatorio_cenario(espec, execs))
            if seed == seeds[0]:
                casos = []
                executar(espec, Estatica(), observador=lambda s, c: casos.append((s, c)))
                auditorias[espec.nome] = [auditar_null_vs_zero(p, casos) for p in baselines() + [proporcional_ingenua()]]

    # resumo: regret por cenário/política na moeda principal (BRL), através das seeds
    resumo: dict = {}
    for rel in relatorios:
        nome = rel["cenario"]["nome"]
        por_pol = {p["politica"]: p for p in rel["politicas"]}
        melhor = min(BASELINES, key=lambda k: (por_pol[k]["por_moeda"]["BRL"]["regret_micros"], k))
        for pol, m in por_pol.items():
            r = resumo.setdefault(nome, {}).setdefault(pol, {"regret_bps": [], "regret_param_bps": [], "lucro_micros": [],
                                                               "drawdown_micros": [], "hhi_bps": [], "turnover_bps": [],
                                                               "decisoes_preliminar": [], "vitorias": 0})
            brl = m["por_moeda"]["BRL"]
            r["regret_bps"].append(brl["regret_bps_do_gasto"])
            r["regret_param_bps"].append(brl["regret_vs_parametros_bps_do_gasto"])
            r["lucro_micros"].append(brl["lucro_realizado_micros"])
            r["drawdown_micros"].append(brl["drawdown_maximo_micros"])
            r["hhi_bps"].append(brl["hhi_medio_bps"])
            r["turnover_bps"].append(brl["turnover_medio_bps_dia"])
            r["decisoes_preliminar"].append(m["decisoes_com_dado_preliminar"])
            r["vitorias"] += pol == melhor
    for nome, pols in resumo.items():
        for pol, r in pols.items():
            r["regret_bps_mediana"] = int(statistics.median(r["regret_bps"]))
            r["regret_param_bps_mediana"] = int(statistics.median(r["regret_param_bps"]))

    deterministico = {
        "natureza": "sintetico",
        "aviso": "Replay por simulador sintético em malha fechada; não é validação com dado real.",
        "seeds": seeds,
        "relatorios_sha256": [r["relatorio_sha256"] for r in relatorios],
        "resumo_brl": resumo,
        "auditoria_null_vs_zero_seed0": auditorias,
        "relatorios": relatorios,
    }
    manifesto = manifesto_execucao(
        nome="replay_economico_v0", seed=seeds[0],
        entradas={"fixture_mini": sha256_arquivo(str(RAIZ / "fixtures" / "replay" / "cenario_mini.json"))},
        parametros={"seeds": seeds, "politicas": BASELINES + ["proportional_naive_null_as_zero"],
                    "janela_consulta_dias": 14, "piso_bps": 1000},
    )
    saida = {
        "manifesto": manifesto,
        "deterministico_sha256": sha256_de(deterministico),
        "deterministico": deterministico,
        "tempos_s_nao_deterministico": {k: {"mediana": round(statistics.median(v), 4), "n": len(v)}
                                        for k, v in sorted(tempos.items())},
    }
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(saida, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print("deterministico_sha256", saida["deterministico_sha256"], "bytes", SAIDA.stat().st_size)
    for nome, pols in resumo.items():
        print(f"\n{nome}")
        for pol, r in pols.items():
            print(f"  {pol:34s} regret_med={r['regret_bps_mediana']:5d}bps regret_param_med={r['regret_param_bps_mediana']:6d}bps "
                  f"vitorias={r['vitorias']} prelim={r['decisoes_preliminar']} turnover={r['turnover_bps']}")
    for nome, a in auditorias.items():
        print(nome, [(x["politica"], x["suspeita_null_como_zero"], x["decisoes_que_distinguem_null_de_zero"], x["snapshots_com_lacuna"]) for x in a])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
