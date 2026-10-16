"""M10 — alocação de orçamento sob resposta côncava estimada × equal × greedy × proporcional herdado.

Avaliação por re-simulação do MESMO mundo (CRN) com o orçamento de cada política nos 15 dias pós-decisão
(dias 30–44); oráculo = melhor escolha numa grade de multiplicadores por campanha (MILP, mesmas restrições;
campanhas são independentes no simulador, então o lucro da grade é aditivo). Histórico de decisão = registros
observados dos dias 0–29 lidos como painel as_of no instante da decisão, só dias com custo e receita em
maturidade final (errata R2/G10, 2026-10-16; antes usava a verdade diária, inclusive dias imaturos).
Pré-registro: PRE-REGISTRO.md (M10). Saída: m10_alocacao.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fundacao_modelos_comum import manifesto, pareado, saida, supera  # noqa: E402

import numpy as np  # noqa: E402
from scipy.optimize import Bounds, LinearConstraint, milp  # noqa: E402

from volc_dil.fundacao import modelos as M  # noqa: E402
from volc_dil.fundacao.modelos.tabular import FINAL  # noqa: E402
from volc_dil.fundacao.simulador import cenario, gerar_mundo, observar  # noqa: E402

D_HIST, D_TOT = 30, 45
HORA_DECISAO = 12.0  # decisão no dia D_HIST às 12h locais
GRADE = np.linspace(0.5, 1.5, 9)
PARAM = dict(minimo_frac=0.2, maximo_frac=3.0, passo_max=0.5, b_prior=0.7, sd_prior_b=0.25, min_desvio_log=0.1,
             aversao=1.0, janela_recente=7)


def _lucro_pos(mundo):
    r = mundo.diario("receita_micros")[:, D_HIST:] / 1e6
    c = mundo.diario("custo_final_micros")[:, D_HIST:] / 1e6
    return (r - c).sum(axis=1)


def um_mundo(nome, seed, C):
    esp = cenario(nome).reduzir(n_campanhas=C, n_dias=D_TOT)
    w0 = gerar_mundo(esp.mundo, seed)
    b_hist = w0.flags["orcamento_hora_micros"].reshape(C, D_TOT, 24)[:, :D_HIST, 23].astype(np.int64)
    atual_m = b_hist[:, -1]
    B = np.concatenate([b_hist, np.repeat(atual_m[:, None], D_TOT - D_HIST, axis=1)], axis=1)
    sq = gerar_mundo(esp.mundo, seed, orcamento_diario_micros=B)
    # Histórico de decisão = painel AS_OF MADURO observado (errata R2/G10, 2026-10-16): as políticas veem só
    # registros com available_at <= decisão (dia 30, 12h local) e só dias com custo E receita em maturidade
    # "final"; o resto fica NaN (atraso de maturação declarado ~3 dias; lacunas de coleta também ficam NaN).
    leit = observar(sq, esp.observador, cenario=f"m10_{nome}")
    kw = dict(entidades=M.ids_campanhas(sq), dias=M.dias_iso(sq))
    tc = M.TabelaVersoes.de_registros(leit.registros, fonte="google_ads", metrica="cost", **kw)
    tr = M.TabelaVersoes.de_registros(leit.registros, fonte="joinads", metrica="revenue", **kw)
    t_dec = M.instante_local(sq, D_HIST, HORA_DECISAO)
    maduro = (tc.painel_maturidade(t_dec) == FINAL) & (tr.painel_maturidade(t_dec) == FINAL)
    gasto = np.where(maduro, tc.painel(t_dec), np.nan)[:, :D_HIST] / 1e6
    rec = np.where(maduro, tr.painel(t_dec), np.nan)[:, :D_HIST] / 1e6
    dias_maduros = np.nonzero(maduro[:, :D_HIST].any(axis=0))[0]
    ultimo_maduro = int(dias_maduros.max())
    atual = atual_m / 1e6
    total = float(atual.sum())
    lo, hi = M.limites(atual, minimo=PARAM["minimo_frac"] * atual, maximo=PARAM["maximo_frac"] * atual,
                       passo_max=PARAM["passo_max"])
    j = PARAM["janela_recente"]
    jan = slice(ultimo_maduro - j + 1, ultimo_maduro + 1)  # últimos j dias MADUROS
    with np.errstate(invalid="ignore", divide="ignore"):
        contrib = np.nanmean(rec[:, jan] - gasto[:, jan], axis=1)
        g_j, r_j = np.nansum(gasto[:, jan], 1), np.nansum(rec[:, jan], 1)
        roas = np.where(np.isfinite(rec[:, jan] - gasto[:, jan]).any(axis=1), r_j / np.maximum(g_j, 1e-9), np.nan)
    curvas = [M.ajustar_resposta(gasto[c], rec[c], b_prior=PARAM["b_prior"], sd_prior_b=PARAM["sd_prior_b"],
                                 min_desvio_log=PARAM["min_desvio_log"]) for c in range(C)]
    pols = {
        "status_quo": atual.copy(),
        "equal": M.alocar_igual(C, total=total, lo=lo, hi=hi),
        "greedy": M.alocar_guloso(roas, total=total, lo=lo, hi=hi),
        "proporcional_herdado": M.alocar_proporcional(contrib, total=total, lo=lo, hi=hi, piso=0.0),
        "concava": M.alocar_orcamento(curvas, total=total, lo=lo, hi=hi, aversao=PARAM["aversao"]),
        "concava_sem_aversao": M.alocar_orcamento(curvas, total=total, lo=lo, hi=hi, aversao=0.0),
    }
    violacoes = {n: M.verificar_restricoes(x, lo, hi, total, tol=1e-4) for n, x in pols.items()}
    lucro = {}
    for n, x in pols.items():
        Bp = B.copy()
        Bp[:, D_HIST:] = M.para_micros(x)[:, None]
        lucro[n] = float(_lucro_pos(gerar_mundo(esp.mundo, seed, orcamento_diario_micros=Bp)).sum())
    # oráculo na grade (MILP): lucro por campanha em cada multiplicador
    L = np.zeros((C, GRADE.size))
    for k, g in enumerate(GRADE):
        Bg = B.copy()
        Bg[:, D_HIST:] = M.para_micros(g * atual)[:, None]
        L[:, k] = _lucro_pos(gerar_mundo(esp.mundo, seed, orcamento_diario_micros=Bg))
    custo = (GRADE[None, :] * atual[:, None]).ravel()
    A_um = np.kron(np.eye(C), np.ones(GRADE.size))
    sol = milp(-L.ravel(), integrality=np.ones(C * GRADE.size),
               constraints=[LinearConstraint(A_um, 1, 1), LinearConstraint(custo[None, :], -np.inf, total * (1 + 1e-9))],
               bounds=Bounds(0, 1))
    oraculo = float(-sol.fun) if sol.success else float("nan")
    return {"lucro": lucro, "oraculo_grade": oraculo, "regret": {n: oraculo - v for n, v in lucro.items()},
            "violacoes": violacoes, "frac_curvas_identificaveis": float(np.mean([c.identificavel for c in curvas])),
            "frac_b_no_teto": float(np.mean([c.b >= 0.95 - 1e-9 for c in curvas])),
            "ultimo_dia_maduro": ultimo_maduro, "frac_celulas_maduras_hist": float(maduro[:, :D_HIST].mean()),
            "b_mediano": float(np.median([c.b for c in curvas])),
            "desvio_log_gasto_mediano": float(np.median([c.desvio_log_gasto for c in curvas]))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true")
    a = ap.parse_args()
    seeds = list(range(20262201, 20262201 + (3 if a.rapido else 16)))
    C = 15 if a.rapido else 40
    res = {}
    for nome in ("mudanca_orcamento", "estavel"):
        ws = [um_mundo(nome, s, C) for s in seeds]
        pols = list(ws[0]["regret"])
        reg = {n: [w["regret"][n] for w in ws] for n in pols}
        bloco = {"regret": {n: M.ic_bootstrap_media(v) for n, v in reg.items()},
                 "oraculo_grade": M.ic_bootstrap_media([w["oraculo_grade"] for w in ws]),
                 "frac_curvas_identificaveis": M.ic_bootstrap_media([w["frac_curvas_identificaveis"] for w in ws]),
                 "desvio_log_gasto_mediano": M.ic_bootstrap_media([w["desvio_log_gasto_mediano"] for w in ws]),
                 "frac_b_no_teto": M.ic_bootstrap_media([w["frac_b_no_teto"] for w in ws]),
                 "b_mediano": M.ic_bootstrap_media([w["b_mediano"] for w in ws]),
                 "ultimo_dia_maduro_mediano": float(np.median([w["ultimo_dia_maduro"] for w in ws])),
                 "frac_celulas_maduras_hist": M.ic_bootstrap_media([w["frac_celulas_maduras_hist"] for w in ws]),
                 "violacoes_de_restricao": sum(len(v) for w in ws for v in w["violacoes"].values())}
        for b in ("equal", "proporcional_herdado", "greedy", "status_quo"):
            d = pareado(reg["concava"], reg[b])
            bloco[f"concava_menos_{b}"] = d
            bloco[f"concava_supera_{b}"] = supera(d, direcao="menor")
        res[nome] = bloco
    mo, es = res["mudanca_orcamento"], res["estavel"]
    res["H10a_suportada"] = bool(mo["concava_supera_equal"] and mo["concava_supera_proporcional_herdado"])
    res["H10b_suportada_nao_supera_equal_sem_variacao"] = bool(not es["concava_supera_equal"])
    obj = {"manifesto": manifesto(__file__, seeds=seeds, parametros={"C": C, "dias_hist": D_HIST, "dias_total": D_TOT,
                                                                     "grade": GRADE.tolist(), **PARAM}),
           "resultados": res}
    saida("m10_alocacao.json", obj, rapido=a.rapido)


if __name__ == "__main__":
    main()
