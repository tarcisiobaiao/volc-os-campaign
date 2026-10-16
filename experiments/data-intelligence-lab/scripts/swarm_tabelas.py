"""Imprime tabelas Markdown compactas a partir dos JSON de results/swarm (sem recomputar nada).

Uso: experiments/data-intelligence-lab/.venv/bin/python experiments/data-intelligence-lab/scripts/swarm_tabelas.py [principal|parametros|sensibilidade|diagnostico]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1] / "results" / "swarm"
POL = ("oraculo", "equal", "random_sh", "greedy_parcial", "greedy_madura", "sh_parcial", "sh_madura",
       "asha_parcial", "asha_madura", "thompson_parcial", "thompson_madura")


def ic(d, esc=1.0, casas=0):
    if d is None or d.get("media") is None:
        return "—"
    m = d["media"] / esc
    lo, hi = d["ic95"]
    if lo is None:
        return f"{m:.{casas}f}"
    return f"{m:.{casas}f} [{lo / esc:.{casas}f}; {hi / esc:.{casas}f}]"


def principal():
    j = json.loads((R / "swarm_principal.json").read_text())
    print(f"veredito (regra pré-registrada): {j['veredito_regra_pre_registrada']}")
    print(f"cenários em que supera: {j['cenarios_em_que_supera']}\n")
    for nome, c in j["cenarios"].items():
        print(f"\n#### {nome}\n")
        print("| política | regret R$ [IC95] | orç. em perdedoras (fim) | drawdown R$ | podadas top-k | falso venc./promovida | HHI | turnover |")
        print("|---|---|---|---|---|---|---|---|")
        for p in POL:
            if p not in c["resumo"]:
                continue
            r = c["resumo"][p]
            print(f"| {p} | {ic(r['regret_brl'])} | {ic(r['frac_orcamento_perdedoras_final'], 1, 3)} | "
                  f"{ic(r['drawdown_micros'], 1e6)} | {ic(r['podadas_incorretas'], 1, 2)} | "
                  f"{ic(r['taxa_falso_vencedor'], 1, 2)} | {r['hhi_medio']['media']:.2f} | {r['turnover_medio']['media']:.3f} |")
        print("\ncritério: " + "; ".join(
            f"{k}: {'SUPERA' if v['supera'] else 'não'} (vs {v['melhor_baseline']}; regret {'ok' if v['regret_ok'] else 'x'}, "
            f"perdedoras {'ok' if v['falsos_vencedores_ok'] else 'x'}, drawdown {'ok' if v['drawdown_ok'] else 'x'}; "
            f"Δpareado {ic(v['dif_pareada_regret'])})" for k, v in c["criterio"].items()))
        for k, v in c["pareado_parcial_madura"].items():
            print(f"\n{k}: Δregret {ic(v['regret_brl'])}; Δpodadas {ic(v['podadas_incorretas'], 1, 2)}")


def parametros():
    j = json.loads((R / "swarm_parametros.json").read_text())
    for nome, c in j["cenarios"].items():
        print(f"\n#### {nome}\n")
        print("| política | regret R$ [IC95] | perdedoras | drawdown R$ | podadas | supera? |")
        print("|---|---|---|---|---|---|")
        for p, r in c["resumo"].items():
            crit = c["criterio"].get(p)
            s = "" if crit is None else ("SIM" if crit["supera"] else f"não (vs {crit['melhor_baseline']})")
            print(f"| {p} | {ic(r['regret_brl'])} | {ic(r['frac_orcamento_perdedoras_final'], 1, 3)} | "
                  f"{ic(r['drawdown_micros'], 1e6)} | {ic(r['podadas_incorretas'], 1, 2)} | {s} |")


def sensibilidade():
    for bloco in ("estacionario", "nao_estacionario"):
        f = R / f"swarm_sensibilidade_{bloco}.json"
        if not f.exists():
            continue
        j = json.loads(f.read_text())
        print(f"\n#### bloco {bloco}\n")
        print("| cenário | equal | greedy_p | sh_p | sh_m | asha_p | asha_m | Δpodadas sh p−m | supera? |")
        print("|---|---|---|---|---|---|---|---|---|")
        for nome, c in j["cenarios"].items():
            r = c["resumo"]
            sup = [k for k, v in c["criterio"].items() if v["supera"]]
            dp = c["pareado_parcial_madura"]["sh_parcial_menos_sh_madura"]["podadas_incorretas"]
            curto = nome.replace(f"__{bloco}", "")
            print(f"| {curto} | " + " | ".join(f"{r[p]['regret_brl']['media']:.0f}" for p in
                                             ("equal", "greedy_parcial", "sh_parcial", "sh_madura", "asha_parcial", "asha_madura"))
                  + f" | {ic(dp, 1, 2)} | {','.join(sup) or '—'} |")


def diagnostico():
    j = json.loads((R / "swarm_diagnostico.json").read_text())
    print("| cenário | rung | ρ(parcial,v) | ρ(madura,v) | ρ(parcial,escala) | ρ(madura,escala) | parcial/madura rápidas | lentas | ρ(v,escala) |")
    print("|---|---|---|---|---|---|---|---|---|")
    for nome, c in j["cenarios"].items():
        for rung, d in c.items():
            if not rung.startswith("rung_"):
                continue
            print(f"| {nome} | {rung} | {ic(d['spearman_parcial_v'], 1, 2)} | {ic(d['spearman_madura_v'], 1, 2)} | "
                  f"{ic(d['spearman_parcial_escala'], 1, 2)} | {ic(d['spearman_madura_escala'], 1, 2)} | "
                  f"{ic(d['razao_parcial_madura_rapidas'], 1, 2)} | {ic(d['razao_parcial_madura_lentas'], 1, 2)} | "
                  f"{ic(c['spearman_v_escala'], 1, 2)} |")


if __name__ == "__main__":
    {"principal": principal, "parametros": parametros, "sensibilidade": sensibilidade,
     "diagnostico": diagnostico}[sys.argv[1] if len(sys.argv) > 1 else "principal"]()
