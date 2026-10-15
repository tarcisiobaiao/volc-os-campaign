"""E2 — Nowcasting de receita por idade da coorte. DADOS 100% SINTÉTICOS.

Mecânica que o blueprint (B19/B20) descreve como "Projected = Observed /
Maturation_Factor(dt)", implementada SEM vazamento temporal e com backtest
que só usa o que estava disponível em cada instante.

O mundo sintético TEM as-of snapshots (a cada 6 h, até 168 h). O VOLC real NÃO
tem: joinads_metrics/gam_metrics fazem upsert por (date, utm_campaign_value,
dominio) e guardam só o último valor + updated_at (ver AUDITORIA-DADOS.md §1).
Logo, nenhum número daqui é parâmetro operacional; 65%/90%/95% do blueprint
são exemplos — aqui a curva é escolhida por nós e muda no meio do período.

Rodar: python -I e2_nowcasting.py [saida.json]
"""
from __future__ import annotations

import json
import sys

import numpy as np

SEED = 20261014
DIAS = 240
PASSO_H = 6
IDADE_FINAL_H = 168                       # "final" = valor reportado em 168 h
K_MAX = IDADE_FINAL_H // PASSO_H          # 28 snapshots por coorte
JANELA_DIAS = 28                          # coortes maduras usadas para estimar f
F_MIN = 0.15                              # abaixo disso, Chain-Ladder é "não apurado"
DIA_DRIFT = 150                           # a partir daqui a fonte reporta mais devagar
CAMPANHAS = {"grande": 2000, "media": 200, "pequena": 15}   # cliques/dia médios
RPC_MEDIO = 0.012                          # R$/clique (sintético)


def curva(idade_h, tau, beta=0.9):
    """Fração reportada até a idade (Weibull), normalizada para 1 em 168 h."""
    g = lambda h: 1 - np.exp(-(h / tau) ** beta)
    return np.minimum(g(idade_h) / g(IDADE_FINAL_H), 1.0)


def simular(rng, tau_pos=40.0):
    idades = np.arange(1, K_MAX + 1) * PASSO_H
    mundo = {}
    for nome, media in CAMPANHAS.items():
        cliques = np.maximum(rng.poisson(media * np.exp(rng.normal(0, 0.3, DIAS))), 1)
        dow = 1 + 0.15 * np.sin(2 * np.pi * np.arange(DIAS) / 7)
        rpc_dia = RPC_MEDIO * dow * np.exp(rng.normal(0, 0.10, DIAS))
        shape = 0.8 * cliques                                # CV por clique ~ 1,1
        final = rng.gamma(shape, rpc_dia * cliques / shape)
        obs = np.zeros((DIAS, K_MAX))
        for d in range(DIAS):
            tau = (20.0 if d < DIA_DRIFT else tau_pos) * np.exp(rng.normal(0, 0.25))
            frac = curva(idades, tau)
            frac = frac * np.exp(rng.normal(0, 0.05, K_MAX))   # ruído de reporte
            frac[-1] = 1.0
            if rng.random() < 0.2:                             # revisão para baixo em 48 h
                frac[idades >= 48] *= 0.97
                frac[-1] = 1.0
            obs[d] = final[d] * np.minimum(frac, 1.2)
        mundo[nome] = {"cliques": cliques, "final": final, "obs": obs}
    return mundo


def disponivel(d, k, T):
    """Snapshot k (idade (k+1)*6 h) da coorte d existe no instante T (horas)?"""
    return 24 * d + (k + 1) * PASSO_H <= T


def fatores(mundo, T, vazar=False):
    """f(k) = soma(obs_k) / soma(final), só coortes MADURAS em T (ratio of sums).

    vazar=True usa as coortes dos últimos JANELA_DIAS dias ATÉ o dia de T,
    inclusive as imaturas, com o valor FINAL delas (que em T ainda não existe):
    é o que um backtest feito sobre a tabela sobrescrita (sem as-of) faz sem
    perceber — o "final" de hoje entra no passado.
    """
    num = np.zeros(K_MAX)
    den = 0.0
    rpc_num = rpc_den = 0.0
    por_coorte = []
    for nome, m in mundo.items():
        if vazar:
            dia_T = int(T // 24)
            ds = range(max(0, dia_T - JANELA_DIAS + 1), dia_T + 1)
        else:
            ultimo = int((T - IDADE_FINAL_H) // 24)            # maduro: 24d+168 <= T
            ds = range(max(0, ultimo - JANELA_DIAS + 1), ultimo + 1) if ultimo >= 0 else []
        for d in ds:
            num += m["obs"][d]
            den += m["final"][d]
            rpc_num += m["final"][d]
            rpc_den += m["cliques"][d]
            por_coorte.append((nome, d))
    if den <= 0:
        return None, None, []
    return num / den, rpc_num / rpc_den, por_coorte


def residuos_loo(mundo, f_soma_num, f_soma_den, coortes, k):
    """Razão final/projeção CL em coortes maduras, com f leave-one-out."""
    out = []
    for nome, d in coortes:
        m = mundo[nome]
        num = f_soma_num[k] - m["obs"][d][k]
        den = f_soma_den - m["final"][d]
        if den <= 0 or num <= 0 or m["obs"][d][k] <= 0:
            continue
        f_loo = num / den
        out.append(m["final"][d] / (m["obs"][d][k] / f_loo))
    return np.array(out)


def backtest(mundo, vazar=False):
    reg = []
    for t in range(40, DIAS - 8):
        for hora in (6, 18):
            T = 24 * t + hora
            f, rpc_prior, coortes = fatores(mundo, T, vazar)
            if f is None:
                continue
            # somas para leave-one-out
            sn = np.zeros(K_MAX); sd = 0.0
            for nome, d in coortes:
                sn += mundo[nome]["obs"][d]; sd += mundo[nome]["final"][d]
            q_cache = {}
            for nome, m in mundo.items():
                for d in range(max(0, t - 7), t + 1):
                    idade = T - 24 * d
                    k = idade // PASSO_H - 1
                    if idade <= 0 or k >= K_MAX - 1 or not disponivel(d, k, T):
                        continue
                    obs = m["obs"][d][k]
                    verdade = m["final"][d]
                    prior = m["cliques"][d] * rpc_prior          # cliques do dia são conhecidos (custo D0)
                    fk = float(f[k])
                    cl = obs / fk if fk >= F_MIN else None       # guarda de fator ~ 0
                    cl_sem_guarda = obs / fk if fk > 0 else None
                    bf = obs + (1 - min(fk, 1.0)) * prior        # Bornhuetter-Ferguson
                    if k not in q_cache:
                        r = residuos_loo(mundo, sn, sd, coortes, k)
                        q_cache[k] = (np.quantile(r, [0.05, 0.95]) if len(r) >= 20 else None)
                    q = q_cache[k]
                    ic = None
                    if cl is not None and q is not None:
                        ic = (cl * q[0], cl * q[1])
                    reg.append({"t": t, "campanha": nome, "idade_h": int(idade), "f": fk,
                                "verdade": verdade, "ingenuo": obs, "cl": cl, "cl_sem_guarda": cl_sem_guarda, "bf": bf,
                                "so_prior": prior, "ic": ic, "pos_drift": d >= DIA_DRIFT})
    return reg


def metricas(reg, filtro=lambda r: True):
    sel = [r for r in reg if filtro(r)]
    if not sel:
        return None
    soma_v = sum(r["verdade"] for r in sel)
    out = {"n": len(sel)}
    for est in ("ingenuo", "cl", "cl_sem_guarda", "bf", "so_prior"):
        val = [r for r in sel if r[est] is not None]
        if not val:
            out[est] = None
            continue
        sv = sum(r["verdade"] for r in val)
        out[est] = {
            "erro_abs_rel": round(sum(abs(r[est] - r["verdade"]) for r in val) / sv, 4),
            "vies_rel": round(sum(r[est] - r["verdade"] for r in val) / sv, 4),
            "cobertura_n": round(len(val) / len(sel), 4),
        }
    com_ic = [r for r in sel if r["ic"] is not None]
    out["cobertura_ic90_cl"] = (round(sum(r["ic"][0] <= r["verdade"] <= r["ic"][1] for r in com_ic)
                                      / len(com_ic), 4) if com_ic else None)
    out["nao_apurado_cl"] = round(sum(r["cl"] is None for r in sel) / len(sel), 4)
    return out


def main():
    rng = np.random.default_rng(SEED)
    mundo = simular(rng)
    reg = backtest(mundo, vazar=False)
    reg_vaz = backtest(mundo, vazar=True)
    idades = sorted({r["idade_h"] for r in reg})
    faixas = [(6, 12), (18, 24), (30, 48), (54, 96), (102, 162)]
    res = {
        "rotulo": "SINTETICO — curva de maturacao escolhida por nos; nao e parametro operacional do VOLC",
        "seed": SEED,
        "curva_verdadeira_antes_drift": {h: round(float(curva(np.array([h]), 20.0)[0]), 3) for h in (6, 12, 24, 48, 72)},
        "curva_verdadeira_pos_drift": {h: round(float(curva(np.array([h]), 40.0)[0]), 3) for h in (6, 12, 24, 48, 72)},
        "config": {"f_min": F_MIN, "janela_dias": JANELA_DIAS, "dia_drift": DIA_DRIFT,
                   "campanhas_cliques_dia": CAMPANHAS},
        "por_faixa_de_idade": {},
        "por_campanha": {},
        "drift": {},
        "vazamento": {},
    }
    for a, b in faixas:
        chave = f"{a}-{b}h"
        res["por_faixa_de_idade"][chave] = metricas(reg, lambda r, a=a, b=b: a <= r["idade_h"] <= b)
        res["vazamento"][chave] = {
            "sem_vazamento_cl": (metricas(reg, lambda r, a=a, b=b: a <= r["idade_h"] <= b and r["pos_drift"]) or {}).get("cl"),
            "com_vazamento_cl": (metricas(reg_vaz, lambda r, a=a, b=b: a <= r["idade_h"] <= b and r["pos_drift"]) or {}).get("cl"),
        }
    for nome in CAMPANHAS:
        res["por_campanha"][nome] = metricas(reg, lambda r, n=nome: r["campanha"] == n and 18 <= r["idade_h"] <= 48)
    res["drift"]["antes"] = metricas(reg, lambda r: not r["pos_drift"] and 18 <= r["idade_h"] <= 48)
    res["drift"]["primeiros_35_dias_pos"] = metricas(
        reg, lambda r: r["pos_drift"] and r["t"] < DIA_DRIFT + 35 and 18 <= r["idade_h"] <= 48)
    res["drift"]["depois_de_35_dias"] = metricas(
        reg, lambda r: r["pos_drift"] and r["t"] >= DIA_DRIFT + 35 and 18 <= r["idade_h"] <= 48)
    # Estresse: fonte que reporta MUITO devagar após o drift (f(6 h) ~ 0,04).
    mundo_s = simular(np.random.default_rng(SEED + 1), tau_pos=160.0)
    reg_s = backtest(mundo_s, vazar=False)
    res["estresse_fator_quase_zero"] = {
        "curva_pos_drift": {h: round(float(curva(np.array([h]), 160.0)[0]), 3) for h in (6, 12, 24, 48)},
        "6-12h_pos_drift": metricas(reg_s, lambda r: 6 <= r["idade_h"] <= 12 and r["pos_drift"]),
        "6-12h_pos_drift_campanha_pequena": metricas(
            reg_s, lambda r: 6 <= r["idade_h"] <= 12 and r["pos_drift"] and r["campanha"] == "pequena"),
    }
    destino = sys.argv[1] if len(sys.argv) > 1 else "e2_resultado.json"
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, ensure_ascii=False)
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
