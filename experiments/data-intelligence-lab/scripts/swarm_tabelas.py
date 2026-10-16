"""Imprime tabelas Markdown compactas a partir dos JSON de results/swarm (sem recomputar nada).

Uso: experiments/data-intelligence-lab/.venv/bin/python experiments/data-intelligence-lab/scripts/swarm_tabelas.py \
     [principal|parametros|sensibilidade|diagnostico|pos_registro|fatos|tudo]
`tudo` grava results/swarm/SWARM-TABELAS.md (arquivo GERADO; não editar à mão).
"""
from __future__ import annotations

import builtins
import json
import sys
from pathlib import Path

_LINHAS: list[str] = []


def print(*a, **k):  # noqa: A001 — coleta para gravar SWARM-TABELAS.md além de imprimir
    texto = " ".join(str(x) for x in a)
    _LINHAS.append(texto)
    builtins.print(texto, **k)

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
        print("| política | regret R$ [IC95] | orç. em perdedoras (fim) | excesso vs oráculo (fim, pós-reg.) | drawdown R$ | podadas top-k | falso venc./promovida | HHI | turnover |")
        print("|---|---|---|---|---|---|---|---|---|")
        for p in POL:
            if p not in c["resumo"]:
                continue
            r = c["resumo"][p]
            print(f"| {p} | {ic(r['regret_brl'])} | {ic(r['frac_orcamento_perdedoras_final'], 1, 3)} | "
                  f"{ic(r.get('excesso_perdedoras_vs_oraculo_final'), 1, 3)} | "
                  f"{ic(r['drawdown_micros'], 1e6)} | {ic(r['podadas_incorretas'], 1, 2)} | "
                  f"{ic(r['taxa_falso_vencedor'], 1, 2)} | {r['hhi_medio']['media']:.2f} | {r['turnover_medio']['media']:.3f} |")
        print("\ncritério: " + "; ".join(
            f"{k}: {'SUPERA' if v['supera'] else 'não'} (vs {v['melhor_baseline']}; regret {'ok' if v['regret_ok'] else 'x'}, "
            f"perdedoras {'ok' if v['falsos_vencedores_ok'] else 'x'}, drawdown {'ok' if v['drawdown_ok'] else 'x'}; "
            f"Δpareado {ic(v['dif_pareada_regret'])})" for k, v in c["criterio"].items()))
        for k, v in c["pareado_parcial_madura"].items():
            print(f"\n{k}: Δregret {ic(v['regret_brl'])}; Δpodadas {ic(v['podadas_incorretas'], 1, 2)}")
        pos = c.get("pos_registro")
        if pos:
            o = pos["criterio_pre_registrado_aplicado_ao_oraculo"]
            print(f"\nPÓS-REGISTRO — critério pré-registrado aplicado ao ORÁCULO: {'supera' if o['supera'] else 'NÃO supera'} "
                  f"(vs {o['melhor_baseline']}; perdedoras {'ok' if o['falsos_vencedores_ok'] else 'x'}, drawdown {'ok' if o['drawdown_ok'] else 'x'})")
            print("PÓS-REGISTRO — critério com excesso vs oráculo: " + "; ".join(
                f"{k}: {'SUPERA' if v['supera'] else 'não'} (regret {'ok' if v['regret_ok'] else 'x'}, excesso {'ok' if v['falsos_vencedores_ok'] else 'x'}, "
                f"drawdown {'ok' if v['drawdown_ok'] else 'x'})" for k, v in pos["criterio_exploratorio_excesso_vs_oraculo"].items()))


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
        vistos: dict[str, str] = {}
        dup = {}
        for nome, c in j["cenarios"].items():
            chave = json.dumps(c["resumo"], sort_keys=True)
            if chave in vistos:
                dup[nome] = vistos[chave]
            else:
                vistos[chave] = nome
        print(f"\n#### bloco {bloco}: {len(j['cenarios'])} combinações, {len(vistos)} cenários distintos "
              f"(com D=0 a maturação não tem efeito; duplicatas marcadas com =)\n")
        print("| cenário | equal | greedy_p | sh_p | sh_m | asha_p | asha_m | Δpodadas sh p−m | supera? |")
        print("|---|---|---|---|---|---|---|---|---|")
        for nome, c in j["cenarios"].items():
            if nome in dup:
                print(f"| {nome.replace(f'__{bloco}', '')} | = {dup[nome].replace(f'__{bloco}', '')} | | | | | | | |")
                continue
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


def pos_registro():
    print("\n### PÓS-REGISTRO / EXPLORATÓRIO — diferença-em-diferenças pareada (Δ = candidato − greedy_parcial)\n")
    j = json.loads((R / "swarm_pos_registro_did.json").read_text())
    print("| cenário | sh_parcial | sh_madura | asha_parcial | asha_madura |")
    print("|---|---|---|---|---|")
    for nome, d in j["delta_candidato_menos_greedy"].items():
        print(f"| {nome} | " + " | ".join(ic(d[c]) for c in ("sh_parcial", "sh_madura", "asha_parcial", "asha_madura")) + " |")
    print("\n| DiD (alvo − ref) | fator | sh_parcial | sh_madura | asha_parcial | asha_madura |")
    print("|---|---|---|---|---|---|")
    for nome, d in j["did"].items():
        print(f"| {nome} | {d['fator']} | " + " | ".join(ic(d[c]) for c in ("sh_parcial", "sh_madura", "asha_parcial", "asha_madura")) + " |")
    print("\nDiD > 0: o fator piora o candidato MAIS que o greedy; < 0: favorece o candidato.")
    print("\n### PÓS-REGISTRO / EXPLORATÓRIO — saturação (cap × beta × maturação, D=3, 200 seeds)\n")
    j = json.loads((R / "swarm_pos_registro_saturacao.json").read_text())
    print("| cenário | melhor baseline | greedy_p | sh_p | asha_p | Δpareado sh_p − baseline | supera (pré-reg.) | supera (excesso vs oráculo) |")
    print("|---|---|---|---|---|---|---|---|")
    for nome, c in j["cenarios"].items():
        r = c["resumo"]
        cr = c["criterio"]["sh_parcial"]
        sup = [k for k, v in c["criterio"].items() if v["supera"]]
        supx = [k for k, v in c["pos_registro"]["criterio_exploratorio_excesso_vs_oraculo"].items() if v["supera"]]
        print(f"| {nome} | {cr['melhor_baseline']} | {r['greedy_parcial']['regret_brl']['media']:.0f} | "
              f"{r['sh_parcial']['regret_brl']['media']:.0f} | {r['asha_parcial']['regret_brl']['media']:.0f} | "
              f"{ic(cr['dif_pareada_regret'])} | {','.join(sup) or '—'} | {','.join(supx) or '—'} |")


def fatos():
    print("\n### Fatos extraídos dos JSON (gerados, não digitados)\n")
    j = json.loads((R / "swarm_principal.json").read_text())
    print(f"- veredito pré-registrado: **{j['veredito_regra_pre_registrada']}**; cenários em que supera: {j['cenarios_em_que_supera']}")
    pr = j.get("pos_registro", {})
    if pr:
        print(f"- PÓS-REGISTRO: o oráculo NÃO supera pelo critério pré-registrado em "
              f"{len(pr['cenarios_em_que_o_oraculo_nao_supera_pelo_criterio_pre_registrado'])}/{len(j['cenarios'])} cenários: "
              f"{pr['cenarios_em_que_o_oraculo_nao_supera_pelo_criterio_pre_registrado']}")
        print(f"- PÓS-REGISTRO: com a métrica excesso vs oráculo, cenários em que supera: "
              f"{pr['cenarios_em_que_supera_com_metrica_excesso_vs_oraculo']}")
    melhores_np = {n: min((p for p in c["resumo"] if p != "oraculo"), key=lambda p: c["resumo"][p]["regret_brl"]["media"])
                   for n, c in j["cenarios"].items()}
    print(f"- política não-oráculo de menor regret médio por cenário: {melhores_np}")
    jp = json.loads((R / "swarm_parametros.json").read_text())
    for nome, c in jp["cenarios"].items():
        if not nome.startswith("degraus__"):
            continue
        r = c["resumo"]
        for fam in ("sh_", "asha_"):
            cand = [p for p in r if p.startswith(fam + "e")]
            b = min(cand, key=lambda p: r[p]["regret_brl"]["media"])
            print(f"- {nome}: melhor {fam.rstrip('_')} = {b} {ic(r[b]['regret_brl'])}; greedy_parcial {ic(r['greedy_parcial']['regret_brl'])}")
        neg = [p for p, v in c["criterio"].items() if v["dif_pareada_regret"]["ic95"][1] < 0]
        print(f"  - variantes com Δ pareado < 0 vs melhor baseline: {len(neg)} de {len(c['criterio'])}")
        sup = [p for p, v in c["criterio"].items() if v["supera"]]
        print(f"  - variantes que superam (pré-reg.): {sup or 'nenhuma'}")


def tudo():
    print("# Swarm Lab — tabelas GERADAS de results/swarm/*.json (não editar à mão)\n")
    print("Gerado por `scripts/swarm_tabelas.py tudo`. Regret em R$ (soma de 30 ciclos), média [IC95 de Monte Carlo], n=200 seeds.")
    for f in (fatos, principal, parametros, sensibilidade, diagnostico, pos_registro):
        print(f"\n## {f.__name__}\n")
        f()
    (R / "SWARM-TABELAS.md").write_text("\n".join(_LINHAS) + "\n")


if __name__ == "__main__":
    {"principal": principal, "parametros": parametros, "sensibilidade": sensibilidade,
     "diagnostico": diagnostico, "pos_registro": pos_registro, "fatos": fatos,
     "tudo": tudo}[sys.argv[1] if len(sys.argv) > 1 else "principal"]()
