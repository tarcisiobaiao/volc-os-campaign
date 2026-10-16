"""M1 — maturação: chain-ladder herdado × Bornhuetter-Ferguson × fator fixo × observado; D0 intradiário;
mudança de regime (Stat Lab herdado e simulador com troca de observador) e monitor de link ratio.

Pré-registro: results/fundacao/modelos/PRE-REGISTRO.md (M1). Saída: results/fundacao/modelos/m1_maturacao.json
Uso: OMP_NUM_THREADS=2 python -I scripts/fundacao_modelos_maturacao.py [--rapido]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fundacao_modelos_comum import manifesto, pareado, razao_pareada, saida, supera  # noqa: E402

import numpy as np  # noqa: E402

from volc_dil.fundacao import modelos as M  # noqa: E402
from volc_dil.fundacao.simulador import cenario, gerar_mundo, observar, simular  # noqa: E402
from volc_dil.statlab.base import ResultadoInsuficiente, rngs  # noqa: E402
from volc_dil.statlab.maturacao import CenarioMaturacao, pmf_atraso_lognormal, simular_incrementos  # noqa: E402

FAIXAS = ((0, 0), (1, 2), (3, 6), (7, 13), (14, 29), (30, 59))


def _num(r):
    return None if isinstance(r, ResultadoInsuficiente) else r


def _agg_final(tab):
    f = tab.final()
    return np.where(np.isfinite(f).any(axis=0), np.nansum(f, axis=0), np.nan)


# ── parte A: receita JoinAds no estável ────────────────────────────────────

def parte_a(seeds, C, D):
    cfg = M.ConfigNowcast(janela_coortes=14, maturidade_minima=0.05, min_coortes=5, nivel_intervalo=0.8)
    metodos = ("chain_ladder", "bornhuetter_ferguson", "fator_fixo", "observado")
    por_seed = {m: {a: [] for a in range(3)} for m in metodos}
    cobertura = {a: [] for a in range(3)}
    for s in seeds:
        sim = simular("estavel", s, n_campanhas=C, n_dias=D)
        tab = M.TabelaVersoes.de_registros(sim.leituras.registros, fonte="joinads", metrica="revenue",
                                           entidades=M.ids_campanhas(sim.mundo), dias=M.dias_iso(sim.mundo))
        agg = M.triangulo_de_tabela(tab, sim.mundo, hora_corte=12, idade_max=6)["agregado"]
        verdade = _agg_final(tab)
        fixo = M.fator_congelado(agg, 20, janela_coortes=14)
        ape = {m: {a: [] for a in range(3)} for m in metodos}
        cob = {a: [] for a in range(3)}
        for T in range(25, D):
            for a in range(3):
                c = T - a
                for m in metodos:
                    r = _num(M.nowcast(agg, T, c, cfg, metodo=m, fator_fixo=fixo))
                    if r is not None and verdade[c] > 0:
                        ape[m][a].append(abs(r["estimativa"] - verdade[c]) / verdade[c])
                        if m == "chain_ladder" and r["intervalo"] and r["intervalo"][0] is not None:
                            cob[a].append(float(r["intervalo"][0] <= verdade[c] <= r["intervalo"][1]))
        for m in metodos:
            for a in range(3):
                por_seed[m][a].append(float(np.mean(ape[m][a])) if ape[m][a] else np.nan)
        for a in range(3):
            cobertura[a].append(float(np.mean(cob[a])) if cob[a] else np.nan)
    res = {"mape_por_idade": {m: {str(a): M.ic_bootstrap_media(por_seed[m][a]) for a in range(3)} for m in metodos},
           "cobertura_ic80_cl": {str(a): M.ic_bootstrap_media(cobertura[a]) for a in range(3)}}
    dif = pareado(por_seed["bornhuetter_ferguson"][0], por_seed["chain_ladder"][0])
    res["H1a_bf_menos_cl_mape_idade0"] = dif
    res["H1a_suportada"] = supera(dif, direcao="menor")
    res["dif_bf_menos_cl_por_idade"] = {str(a): pareado(por_seed["bornhuetter_ferguson"][a], por_seed["chain_ladder"][a])
                                        for a in range(3)}
    return res


# ── parte B: custo D0 intradiário multiversão ──────────────────────────────

def parte_b(seeds, C, D):
    horas = (8, 10, 12, 14, 16, 18, 20, 22)
    cfg = M.ConfigNowcast(janela_coortes=10, maturidade_minima=0.05, min_coortes=20)
    wmape = {"cl_intradiario": {h: [] for h in horas}, "d0_como_final": {h: [] for h in horas}}
    curvas = {h: [] for h in horas}
    versoes = []
    for s in seeds:
        sim = simular("custo_d0_multiversao", s, n_campanhas=C, n_dias=D)
        m = sim.mundo
        tab = M.TabelaVersoes.de_registros(sim.leituras.registros, fonte="google_ads", metrica="cost",
                                           entidades=M.ids_campanhas(m), dias=M.dias_iso(m))
        nv = tab.n_versoes_distintas()
        versoes.append(float(np.median(nv[nv > 0])))
        vh = M.paineis_intradiarios(tab, m, horas=horas, folga_s=900)
        final = tab.final()
        err = {k: {h: [0.0, 0.0] for h in horas} for k in wmape}
        for d in range(14, D):
            ref = range(d - 13, d - 3)  # backfill (D+3 05:00) já conhecido na manhã de d
            cur = M.curva_intradiaria(vh, final, ref)
            for j, h in enumerate(horas):
                v, f = vh[j][:, d], final[:, d]
                est = M.nowcast_intradiario(v, cur["fator"][j], int(cur["n_celulas"][j]), cfg)
                ok = np.isfinite(f) & (f > 0) & np.isfinite(est) & np.isfinite(v)
                err["cl_intradiario"][h][0] += float(np.abs(est[ok] - f[ok]).sum())
                err["d0_como_final"][h][0] += float(np.abs(v[ok] - f[ok]).sum())
                for k in err:
                    err[k][h][1] += float(f[ok].sum())
                curvas[h].append(float(cur["fator"][j]))
        for k in wmape:
            for h in horas:
                wmape[k][h].append(err[k][h][0] / err[k][h][1] if err[k][h][1] > 0 else np.nan)
    cl_ate18 = [np.mean([wmape["cl_intradiario"][h][i] for h in horas if h <= 18]) for i in range(len(seeds))]
    nv_ate18 = [np.mean([wmape["d0_como_final"][h][i] for h in horas if h <= 18]) for i in range(len(seeds))]
    raz = razao_pareada(cl_ate18, nv_ate18)
    return {"wmape_por_hora": {k: {str(h): M.ic_bootstrap_media(wmape[k][h]) for h in horas} for k in wmape},
            "fator_medio_por_hora": {str(h): float(np.mean(curvas[h])) for h in horas},
            "versoes_distintas_mediana_por_campanha_dia": M.ic_bootstrap_media(versoes),
            "H1b_razao_wmape_cl_sobre_naive_ate_18h": raz,
            "H1b_suportada": bool(raz["ic95"][1] is not None and raz["ic95"][1] < 0.5)}


# ── parte C1: regime no cenário herdado do Stat Lab ───────────────────────

def _deslocar(achado, k):
    if not achado.detectado:
        return achado
    d = dict(achado.detalhes)
    d["pontos"] = [p + k for p in d.get("pontos", [achado.ponto_estimado])]
    return M.Achado("mudanca_maturacao", True, achado.metodo, indice=achado.indice + k,
                    ponto_estimado=achado.ponto_estimado + k, estatistica=achado.estatistica, limiar=achado.limiar,
                    detalhes=d)


def _cenarios_herdados(A, N, R):
    base = pmf_atraso_lognormal(mediana=4.0, sigma=1.0, maximo=A)
    kw = dict(eventos_por_dia=30, mediana_valor=2.0, sigma_valor=1.2)
    return {
        "receita_estavel": CenarioMaturacao(N, A, pmf_atraso=base, nome="receita_estavel", **kw),
        "atraso_x2_5": CenarioMaturacao(N, A, pmf_atraso=base, regime_inicio=R,
                                        pmf_atraso_regime=pmf_atraso_lognormal(mediana=10.0, sigma=1.0, maximo=A),
                                        nome="atraso_x2_5", **kw),
        "atraso_metade": CenarioMaturacao(N, A, pmf_atraso=base, regime_inicio=R,
                                          pmf_atraso_regime=pmf_atraso_lognormal(mediana=2.0, sigma=1.0, maximo=A),
                                          nome="atraso_metade", **kw),
    }


def parte_c1(n_mundos, n_calib, seed, k=0.5, escala="mad", grade=(6.0, 8.0, 10.0, 12.0, 15.0, 20.0)):
    A, N, AS_OF, R, CORTE = 60, 150, 149, 120, 60
    cfg = M.ConfigNowcast(janela_coortes=28, maturidade_minima=0.3, min_coortes=14, nivel_intervalo=0.9)
    cens = _cenarios_herdados(A, N, R)

    def mons(h):
        return [M.ConfigMonitor(idade=i, janela_ref=30, k=k, h=h, escala=escala) for i in (0, 1, 2)]

    # calibração do h em mundos SEM mudança (seeds disjuntas)
    calib = []
    tris_c = [np.cumsum(simular_incrementos(cens["receita_estavel"], r), axis=1) for r in rngs(seed + 999, n_calib)]
    h_escolhido = None
    for h in grade:
        fa = float(np.mean([M.regime_vigente(t[CORTE:], AS_OF - CORTE, mons(h)).detectado for t in tris_c]))
        calib.append({"h": h, "fa_por_mundo": fa})
        if h_escolhido is None and fa <= 0.05:
            h_escolhido = h
    h_escolhido = h_escolhido or grade[-1]
    out = {"calibracao": calib, "h": h_escolhido, "calibrou": any(c["fa_por_mundo"] <= 0.05 for c in calib),
           "monitor": {"idades": [0, 1, 2], "janela_ref": 30, "k": k, "escala": escala},
           "cenarios": {}}
    for i_cen, (nome, cen) in enumerate(cens.items()):
        linhas = {f"{lo}-{hi}": {"cl": {"vies": [], "cob": [], "insuf": []}, "mon": {"vies": [], "cob": [], "insuf": []}}
                  for lo, hi in FAIXAS}
        detect, pontos = [], []
        for r in rngs(seed + 1000 * (i_cen + 1), n_mundos):
            inc = simular_incrementos(cen, r)
            tri = np.cumsum(inc, axis=1)
            tri_obs = np.where(np.arange(N)[:, None] + np.arange(A + 1)[None, :] <= AS_OF, tri, np.nan)
            verdade = tri[:, A]
            reg = _deslocar(M.regime_vigente(tri_obs[CORTE:], AS_OF - CORTE, mons(h_escolhido)), CORTE)
            detect.append(reg.detectado)
            if reg.detectado:
                pontos.append(reg.ponto_estimado)
            for lo, hi in FAIXAS:
                acc = {mm: {"num": 0.0, "den": 0.0, "cob": [], "n": 0, "ins": 0} for mm in ("cl", "mon")}
                for a in range(lo, hi + 1):
                    c = AS_OF - a
                    for mm, rr in (("cl", M.nowcast(tri_obs, AS_OF, c, cfg)),
                                   ("mon", M.nowcast(tri_obs, AS_OF, c, cfg, regime=reg))):
                        acc[mm]["n"] += 1
                        if isinstance(rr, ResultadoInsuficiente):
                            acc[mm]["ins"] += 1
                            continue
                        acc[mm]["num"] += rr["estimativa"] - verdade[c]
                        acc[mm]["den"] += verdade[c]
                        if rr["intervalo"] and rr["intervalo"][0] is not None:
                            acc[mm]["cob"].append(float(rr["intervalo"][0] <= verdade[c] <= rr["intervalo"][1]))
                for mm in ("cl", "mon"):
                    L = linhas[f"{lo}-{hi}"][mm]
                    L["vies"].append(acc[mm]["num"] / acc[mm]["den"] if acc[mm]["den"] > 0 else np.nan)
                    L["cob"].append(float(np.mean(acc[mm]["cob"])) if acc[mm]["cob"] else np.nan)
                    L["insuf"].append(acc[mm]["ins"] / acc[mm]["n"] if acc[mm]["n"] else np.nan)
        out["cenarios"][nome] = {
            "taxa_deteccao": float(np.mean(detect)),
            "ponto_estimado_mediana": float(np.median(pontos)) if pontos else None,
            "regime_inicio": cen.regime_inicio,
            "faixas": {f: {k: {m: M.ic_bootstrap_media(v) for m, v in d.items()} for k, d in L.items()}
                       for f, L in linhas.items()},
        }
    return out


# ── parte C2: regime no simulador (observador JoinAds troca no dia 30) ─────

def _splice(seed, C, D, dia_troca):
    e_a = cenario("estavel").reduzir(n_campanhas=C, n_dias=D)
    e_b = cenario("atraso_receita_longo").reduzir(n_campanhas=C, n_dias=D)
    mundo = gerar_mundo(e_a.mundo, seed)
    la = observar(mundo, e_a.observador, cenario="splice_a")
    lb = observar(mundo, e_b.observador, cenario="splice_b")
    dias = M.dias_iso(mundo)
    corte = dias[dia_troca]
    regs = [r for r in la.registros if r.janela_inicio < corte] + [r for r in lb.registros if r.janela_inicio >= corte]
    return mundo, regs


def parte_c2(seeds, seeds_calib, C, D, dia_troca, k=0.5, escala="mad", grade=(4.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0)):
    A = 7
    cfg = M.ConfigNowcast(janela_coortes=14, maturidade_minima=0.05, min_coortes=5, nivel_intervalo=0.8)

    def mons(h):
        return [M.ConfigMonitor(idade=i, janela_ref=14, k=k, h=h, escala=escala) for i in (0, 1)]

    tris_cal = []
    for s in seeds_calib:
        sim = simular("estavel", s, n_campanhas=C, n_dias=D)
        tab = M.TabelaVersoes.de_registros(sim.leituras.registros, fonte="joinads", metrica="revenue",
                                           entidades=M.ids_campanhas(sim.mundo), dias=M.dias_iso(sim.mundo))
        tris_cal.append(M.triangulo_de_tabela(tab, sim.mundo, hora_corte=12, idade_max=A)["agregado"])
    calib, h_esc = [], None
    for h in grade:
        fa = float(np.mean([M.regime_vigente(t, D - 1, mons(h)).detectado for t in tris_cal]))
        calib.append({"h": h, "fa_por_mundo": fa})
        if h_esc is None and fa <= 0.05:
            h_esc = h
    h_esc = h_esc or grade[-1]
    metodos = ("chain_ladder", "fator_fixo", "chain_ladder_monitor")
    vies = {m: {a: [] for a in range(A)} for m in metodos}
    insuf = {m: {a: [] for a in range(A)} for m in metodos}
    atraso_det = []
    for s in seeds:
        mundo, regs = _splice(s, C, D, dia_troca)
        tab = M.TabelaVersoes.de_registros(regs, fonte="joinads", metrica="revenue", entidades=M.ids_campanhas(mundo),
                                           dias=M.dias_iso(mundo))
        agg = M.triangulo_de_tabela(tab, mundo, hora_corte=12, idade_max=A)["agregado"]
        verdade = _agg_final(tab)
        fixo = M.fator_congelado(agg, 20, janela_coortes=14)
        acc = {m: {a: [0.0, 0.0, 0, 0] for a in range(A)} for m in metodos}
        primeiro = None
        for T in range(dia_troca, min(dia_troca + 16, D)):
            reg = M.regime_vigente(agg, T, mons(h_esc))
            if primeiro is None and reg.detectado and reg.ponto_estimado >= dia_troca - 3:
                primeiro = T
            for a in range(A):
                c = T - a
                if c < dia_troca:
                    continue
                for m in metodos:
                    if m == "chain_ladder_monitor":
                        r = M.nowcast(agg, T, c, cfg, regime=reg)
                    else:
                        r = M.nowcast(agg, T, c, cfg, metodo=m, fator_fixo=fixo)
                    acc[m][a][3] += 1
                    if isinstance(r, ResultadoInsuficiente):
                        acc[m][a][2] += 1
                        continue
                    acc[m][a][0] += r["estimativa"] - verdade[c]
                    acc[m][a][1] += verdade[c]
        atraso_det.append(np.nan if primeiro is None else primeiro - dia_troca)
        for m in metodos:
            for a in range(A):
                n, d_, ins, tot = acc[m][a][0], acc[m][a][1], acc[m][a][2], acc[m][a][3]
                vies[m][a].append(n / d_ if d_ > 0 else np.nan)
                insuf[m][a].append(ins / tot if tot else np.nan)
    ad = np.asarray(atraso_det, float)
    return {"calibracao": calib, "h": h_esc, "calibrou": any(c["fa_por_mundo"] <= 0.05 for c in calib),
            "monitor": {"idades": [0, 1], "janela_ref": 14, "k": k, "escala": escala}, "dia_troca": dia_troca,
            "taxa_deteccao_em_15_dias": float(np.mean(np.isfinite(ad))),
            "atraso_deteccao_dias": M.ic_bootstrap_media(ad),
            "vies_relativo_coortes_pos_troca": {m: {str(a): M.ic_bootstrap_media(vies[m][a]) for a in range(A)}
                                                for m in metodos},
            "frac_insuficiente": {m: {str(a): M.ic_bootstrap_media(insuf[m][a]) for a in range(A)} for m in metodos}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true")
    ap.add_argument("--pos-registro", action="store_true",
                    help="EXPLORATÓRIO: só C1/C2 com monitor conservador (k=1, escala max(MAD, dp), h até 60)")
    args = ap.parse_args()
    r = args.rapido
    seeds = list(range(20261101, 20261101 + (3 if r else 12)))
    seeds_cal = list(range(20262101, 20262101 + (3 if r else 12)))
    C, D = (12, 40) if r else (40, 60)
    if args.pos_registro:
        g = (8.0, 12.0, 16.0, 20.0, 25.0, 30.0, 40.0, 60.0)
        res = {"natureza": "POS-REGISTRO exploratório: o monitor pré-registrado (k=0,5, escala MAD) não calibrou",
               "C1_regime_stat_lab_herdado": parte_c1(20 if r else 100, 20 if r else 60, 20261150, k=1.0,
                                                      escala="max_mad_dp", grade=g),
               "C2_regime_simulador": parte_c2(seeds, seeds_cal, C, D, 30, k=1.0, escala="max_mad_dp", grade=g)}
        obj = {"manifesto": manifesto(__file__, seeds=seeds + seeds_cal, parametros={"C": C, "D": D, "pos_registro": True}),
               "resultados": res}
        saida("m1_maturacao_pos_registro.json", obj, rapido=r)
        return
    res = {
        "A_receita_estavel": parte_a(seeds, C, D),
        "B_custo_d0_intradiario": parte_b(seeds, C, 30),
        "C1_regime_stat_lab_herdado": parte_c1(20 if r else 100, 20 if r else 60, 20261150),
        "C2_regime_simulador": parte_c2(seeds, seeds_cal, C, D, 30),
    }
    obj = {"manifesto": manifesto(__file__, seeds=seeds + seeds_cal, parametros={"C": C, "D": D, "rapido": r}),
           "resultados": res}
    saida("m1_maturacao.json", obj, rapido=r)


if __name__ == "__main__":
    main()
