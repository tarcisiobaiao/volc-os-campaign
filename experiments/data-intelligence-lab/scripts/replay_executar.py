"""Roda o replay econômico v0 (SINTÉTICO) em todos os cenários × seeds × políticas.

Uso (da raiz do lab): .venv/bin/python -I scripts/replay_executar.py [--seeds 1-30] [--processos 4]
Saída: results/replay/replay_resultados.json (parte determinística + tempos separados).
O REPLAY-RESULTS.md é GERADO a partir deste JSON por scripts/replay_relatorio.py.

Paralelismo: `--processos` processos Python independentes (um par seed×cenário por tarefa);
cada processo é single-thread. O resultado não depende do número de processos.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from multiprocessing import get_context
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from volc_dil.contracts import manifesto_execucao, sha256_arquivo, sha256_codigo, sha256_de  # noqa: E402
from volc_dil.replay import baselines, catalogo, executar, proporcional_ingenua, relatorio_cenario  # noqa: E402
from volc_dil.replay.auditoria import auditar_null_vs_zero  # noqa: E402
from volc_dil.replay.politicas import Estatica  # noqa: E402

SAIDA = RAIZ / "results" / "replay" / "replay_resultados.json"
BASELINES = ["static", "equal", "proportional", "greedy_conservador"]
REFERENCIA_PAREADA = "equal"
T_975 = {5: 2.776, 10: 2.262, 20: 2.093, 30: 2.045}  # t de Student bicaudal 95% para n-1 gl (n = nº de seeds)


def _tarefa(args: tuple[int, int, bool]) -> dict:
    seed, idx, auditar = args
    espec = catalogo(seed)[idx]
    execs, tempos = [], {}
    for p in baselines() + [proporcional_ingenua()]:
        t0 = time.perf_counter()
        execs.append(executar(espec, p))
        tempos[p.nome] = time.perf_counter() - t0
    saida = {"seed": seed, "cenario": espec.nome, "relatorio": relatorio_cenario(espec, execs), "tempos": tempos}
    if auditar:
        casos = []
        executar(espec, Estatica(), observador=lambda s, c: casos.append((s, c)), medir_preliminar=False)
        saida["auditoria"] = [auditar_null_vs_zero(p, casos) for p in baselines() + [proporcional_ingenua()]]
    return saida


def _seeds(txt: str) -> list[int]:
    if "-" in txt:
        a, b = txt.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(s) for s in txt.split(",")]


def _t(n: int) -> float:
    return T_975.get(n) or (1.96 if n > 30 else T_975[min(T_975, key=lambda k: abs(k - n))])


def _estat(xs: list[int]) -> dict:
    n = len(xs)
    media = sum(xs) / n
    dp = statistics.stdev(xs) if n > 1 else 0.0
    ordenado = sorted(xs)
    return {"n": n, "media": round(media, 1), "dp": round(dp, 1), "mediana": statistics.median(xs),
            "p10": ordenado[max(0, math.ceil(0.1 * n) - 1)], "p90": ordenado[min(n - 1, math.ceil(0.9 * n) - 1)],
            "min": ordenado[0], "pior": ordenado[-1]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1-30")
    ap.add_argument("--processos", type=int, default=4)
    args = ap.parse_args()
    seeds = _seeds(args.seeds)
    n_cen = len(catalogo(seeds[0]))
    tarefas = [(s, i, s == seeds[0]) for s in seeds for i in range(n_cen)]
    t0 = time.perf_counter()
    with get_context("spawn").Pool(args.processos) as pool:
        saidas = pool.map(_tarefa, tarefas, chunksize=1)
    parede = time.perf_counter() - t0

    relatorios = [s["relatorio"] for s in saidas]
    auditorias = {s["cenario"]: s["auditoria"] for s in saidas if "auditoria" in s}
    tempos: dict[str, list[float]] = {}
    for s in saidas:
        for pol, t in s["tempos"].items():
            tempos.setdefault(f"{s['cenario']}/{pol}", []).append(t)

    # por cenário × política: distribuição por seed na moeda principal (BRL)
    por_seed: dict = {}
    for s in saidas:
        for p in s["relatorio"]["politicas"]:
            brl = p["por_moeda"]["BRL"]
            por_seed.setdefault(s["cenario"], {}).setdefault(p["politica"], {})[s["seed"]] = {
                "regret_bps": brl["regret_bps_do_gasto"], "regret_param_bps": brl["regret_vs_parametros_bps_do_gasto"],
                "drawdown_micros": brl["drawdown_maximo_micros"], "hhi_bps": brl["hhi_medio_bps"],
                "turnover_bps": brl["turnover_medio_bps_dia"],
                "prelim_declarado": p["decisoes_com_dado_preliminar_declarado"],
                "prelim_medido": p["decisoes_que_dependeram_de_preliminar_medido"],
                "n_decisoes": p["n_decisoes"], "declaracao": p["declaracao"],
            }
    resumo: dict = {}
    for cen, pols in por_seed.items():
        vitorias = {k: 0 for k in BASELINES}
        for seed in seeds:
            melhor = min(BASELINES, key=lambda k: (pols[k][seed]["regret_param_bps"], k))
            vitorias[melhor] += 1
        ref = pols[REFERENCIA_PAREADA]
        for pol, ss in pols.items():
            serie = [ss[s]["regret_param_bps"] for s in seeds]
            dif = [ss[s]["regret_param_bps"] - ref[s]["regret_param_bps"] for s in seeds]
            md = sum(dif) / len(dif)
            dpd = statistics.stdev(dif) if len(dif) > 1 else 0.0
            meia = _t(len(dif)) * dpd / math.sqrt(len(dif))
            resumo.setdefault(cen, {})[pol] = {
                "declaracao": ss[seeds[0]]["declaracao"],
                "regret_param_bps": _estat(serie),
                "regret_perfeito_bps": _estat([ss[s]["regret_bps"] for s in seeds]),
                "turnover_bps": _estat([ss[s]["turnover_bps"] for s in seeds]),
                "hhi_bps": _estat([ss[s]["hhi_bps"] for s in seeds]),
                "drawdown_micros": _estat([ss[s]["drawdown_micros"] for s in seeds]),
                "prelim_declarado": _estat([ss[s]["prelim_declarado"] for s in seeds]),
                "prelim_medido": _estat([ss[s]["prelim_medido"] for s in seeds]),
                "n_decisoes": ss[seeds[0]]["n_decisoes"],
                "vitorias": vitorias.get(pol),
                f"pareado_vs_{REFERENCIA_PAREADA}": {
                    "media_bps": round(md, 1), "ic95_bps": [round(md - meia, 1), round(md + meia, 1)],
                    "seeds_melhor": sum(1 for d in dif if d < 0), "seeds_pior": sum(1 for d in dif if d > 0),
                },
                "por_seed_regret_param_bps": serie,
            }

    deterministico = {
        "natureza": "sintetico",
        "aviso": "Replay por simulador sintético em malha fechada; não é validação com dado real.",
        "seeds": seeds,
        "metrica_principal": "regret vs oráculo de parâmetros, bps do gasto do horizonte, moeda BRL",
        "referencia_pareada": REFERENCIA_PAREADA,
        "relatorios_sha256": [r["relatorio_sha256"] for r in relatorios],
        "resumo_brl": resumo,
        "auditoria_null_vs_zero": {"seed": seeds[0], "por_cenario": auditorias},
        # relatórios completos só da primeira seed (tamanho < 300 KB); das demais, o sha256
        "relatorios_primeira_seed": [s["relatorio"] for s in saidas if s["seed"] == seeds[0]],
    }
    codigo = sha256_codigo([str(p) for p in sorted((RAIZ / "src" / "volc_dil" / "replay").glob("*.py"))]
                           + [str(Path(__file__).resolve())])
    manifesto = manifesto_execucao(
        nome="replay_economico_v0", seed=seeds[0],
        entradas={"fixture_mini": sha256_arquivo(str(RAIZ / "fixtures" / "replay" / "cenario_mini.json"))},
        parametros={"seeds": seeds, "politicas": BASELINES + ["proportional_naive_null_as_zero"],
                    "janela_consulta_dias": 14, "piso_bps": 1000, "medir_preliminar": True},
        codigo_sha256=codigo, resultado=deterministico,
    )
    saida = {
        "manifesto": manifesto,
        "deterministico_sha256": sha256_de(deterministico),
        "deterministico": deterministico,
        "tempos_s_nao_deterministico": {
            "parede_total_s": round(parede, 1), "processos": args.processos,
            "por_execucao": {k: {"mediana": round(statistics.median(v), 4), "n": len(v)} for k, v in sorted(tempos.items())},
        },
    }
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(saida, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print("deterministico_sha256", saida["deterministico_sha256"], "bytes", SAIDA.stat().st_size, "parede", round(parede, 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
