"""M7 — bandits contextuais mínimos e OPE contra a verdade do simulador.

Ambiente semi-sintético: braços = 5 campanhas maduras; rodada = hora; recompensa = lucro horário verdadeiro
(receita − custo final) escalado pelo desvio do 1º dia; contexto = bloco de 6 h × fim de semana (8).
Escolher não altera o mundo (simplificação declarada). Pré-registro: PRE-REGISTRO.md (M7).
Saída: results/fundacao/modelos/m7_bandits.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fundacao_modelos_comum import manifesto, pareado, saida, supera  # noqa: E402

import numpy as np  # noqa: E402

from volc_dil.fundacao import modelos as M  # noqa: E402
from volc_dil.fundacao.simulador import simular  # noqa: E402

K = 5
N_CTX = 8


def ambiente(cen, seed, C, D):
    m = simular(cen, seed, n_campanhas=C, n_dias=D).mundo
    maduras = [c.idx for c in m.campanhas if not c.nova]
    arms = np.random.default_rng(seed).choice(maduras, K, replace=False)
    lucro = (m.por_hora("receita_micros") - m.por_hora("custo_final_micros"))[arms] / 1e6
    T = lucro.shape[1]
    h = np.arange(T) % 24
    fds = np.array([m.dias[t // 24].weekday() >= 5 for t in range(T)])
    ctx = (h // 6) + 4 * fds.astype(int)
    escala = float(lucro[:, :24].std()) or 1.0
    return lucro / escala, ctx


def politicas():
    return {"equal": lambda: M.Uniforme(K, N_CTX), "greedy": lambda: M.Gulosa(K, N_CTX),
            "eps_greedy_0.1": lambda: M.Gulosa(K, N_CTX, epsilon=0.1),
            "linucb": lambda: M.LinUCB(K, N_CTX, alpha=1.0), "thompson": lambda: M.ThompsonLinear(K, N_CTX, n_mc=100)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true")
    a = ap.parse_args()
    seeds = list(range(20261801, 20261801 + (3 if a.rapido else 16)))
    C, D = (20, 20) if a.rapido else (50, 60)
    n_log = 30 if a.rapido else 200
    res = {}
    for cen in ("estavel", "quebra_regime_rpm"):
        reg = {n: [] for n in politicas()}
        ope = {alvo: {e: [] for e in ("ips", "snips", "dr", "ips_propensao_inventada")} for alvo in ("oraculo", "uniforme")}
        for i, s in enumerate(seeds):
            r, ctx = ambiente(cen, s, C, D)
            mu = M.medias_por_contexto(r, ctx, N_CTX)
            for n, fab in politicas().items():
                reg[n].append(M.pseudo_regret(M.rodar(fab(), r, ctx, seed=s)["distribuicoes"], ctx, mu))
            T = ctx.size
            alvos = {"oraculo": np.eye(K)[np.argmax(mu, axis=1)[ctx]], "uniforme": np.full((T, K), 1.0 / K)}
            reps = n_log if i == 0 else max(5, n_log // 20)  # 1º mundo: muitas seeds de logging (viés)
            for alvo, pi in alvos.items():
                V = M.valor_verdadeiro(pi, r)
                est = {e: [] for e in ope[alvo]}
                for j in range(reps):
                    log = M.rodar(M.Gulosa(K, N_CTX, epsilon=0.2), r, ctx, seed=10_000 + j)["log"]
                    est["ips"].append(M.ips(log, pi) - V)
                    est["snips"].append(M.snips(log, pi) - V)
                    est["dr"].append(M.dr(log, pi, M.q_tabular_cruzado(log, N_CTX, K)) - V)
                    inv = M.Log(log.contexto, log.acao, log.recompensa, np.full(T, 1.0 / K))
                    est["ips_propensao_inventada"].append(M.ips(inv, pi) - V)
                for e, v in est.items():
                    ope[alvo][e].append({"vies": float(np.mean(v)), "ep_mc": float(np.std(v, ddof=1) / np.sqrt(len(v))),
                                         "dp": float(np.std(v, ddof=1)), "n_logs": len(v)})
        bloco = {"regret": {n: M.ic_bootstrap_media(v) for n, v in reg.items()}}
        for n in ("linucb", "thompson"):
            for b in ("equal", "greedy"):
                d = pareado(reg[n], reg[b])
                bloco[f"{n}_menos_{b}"] = d
                bloco[f"{n}_supera_{b}"] = supera(d, direcao="menor")
        bloco["H7a_suportada"] = bool(all(bloco[f"{n}_supera_{b}"] for n in ("linucb", "thompson")
                                          for b in ("equal", "greedy")))
        bloco["ope"] = {}
        for alvo in ope:
            p1 = ope[alvo]["ips"][0]
            inv1 = ope[alvo]["ips_propensao_inventada"][0]
            bloco["ope"][alvo] = {
                "mundo1_muitos_logs": {e: ope[alvo][e][0] for e in ope[alvo]},
                "entre_mundos_vies_medio": {e: M.ic_bootstrap_media([x["vies"] for x in ope[alvo][e]]) for e in ope[alvo]},
                "entre_mundos_dp_medio": {e: float(np.mean([x["dp"] for x in ope[alvo][e]])) for e in ope[alvo]},
                "ips_nao_viesado_mundo1": bool(abs(p1["vies"]) <= 3 * p1["ep_mc"]),
                "inventada_viesada_mundo1": bool(abs(inv1["vies"]) > 3 * inv1["ep_mc"]),
                "snips_dr_variancia_menor": bool(ope[alvo]["snips"][0]["dp"] < p1["dp"] and ope[alvo]["dr"][0]["dp"] < p1["dp"]),
            }
        res[cen] = bloco
    try:
        r, ctx = ambiente("estavel", seeds[0], 10, 3)
        sem = M.rodar(M.Uniforme(K, N_CTX), r, ctx, seed=0, logar_propensao=False)["log"]
        M.ips(sem, np.full((ctx.size, K), 1.0 / K))
        res["sem_propensao"] = "ERRO: estimou sem propensão"
    except M.PropensaoAusente as exc:
        res["sem_propensao"] = f"recusado: {exc}"
    o = res["estavel"]["ope"]
    # pré-registro: vale para as políticas-alvo avaliadas (as duas), sem escolher a favorável depois
    res["H7b_por_alvo"] = {x: {k: o[x][k] for k in ("ips_nao_viesado_mundo1", "inventada_viesada_mundo1",
                                                     "snips_dr_variancia_menor")} for x in o}
    res["H7b_suportada"] = bool(all(all(v.values()) for v in res["H7b_por_alvo"].values())
                                and res["sem_propensao"].startswith("recusado"))
    obj = {"manifesto": manifesto(__file__, seeds=seeds, parametros={"C": C, "D": D, "K": K, "contextos": N_CTX,
                                                                     "logger": "eps_greedy 0.2", "n_logs_mundo1": n_log}),
           "resultados": res}
    saida("m7_bandits.json", obj, rapido=a.rapido)


if __name__ == "__main__":
    main()
