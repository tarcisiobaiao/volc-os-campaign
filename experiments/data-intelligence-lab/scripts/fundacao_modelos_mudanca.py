"""M3 — detecção de mudança (CUSUM, BOCPD mínimo) × média móvel na série de log RPM diário maduro.

Limiares calibrados em seeds do `estavel` para a MESMA taxa-alvo de alarme falso; avaliação em seeds
disjuntas de `quebra_regime_rpm`. O rótulo maduro chega com ATRASO (3 dias): o alarme no índice t é
acionável em t + 3. Pré-registro: PRE-REGISTRO.md (M3). Saída: results/fundacao/modelos/m3_mudanca.json
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

ATRASO = 3
N_REF = 14
JANELA_PODER = 14
ALVO_FA = 0.02  # alarmes por campanha-semana (parâmetro)
METODOS = {
    "media_movel": (dict(n_ref=N_REF, janela=5), np.round(np.linspace(0.5, 5.0, 19), 3)),
    "cusum": (dict(n_ref=N_REF, k=0.5), np.array([2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 25, 30], float)),
    "bocpd": (dict(n_ref=N_REF, hazard=1 / 60, w=5), np.array([0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99,
                                                               0.995, 0.999])),
}


def series_log_rpm(sim):
    m = sim.mundo
    kw = dict(entidades=M.ids_campanhas(m), dias=M.dias_iso(m))
    rec = M.TabelaVersoes.de_registros(sim.leituras.registros, fonte="joinads", metrica="revenue", **kw).final()
    pv = M.TabelaVersoes.de_registros(sim.leituras.registros, fonte="joinads", metrica="pageviews", **kw).final()
    out = []
    for c in range(m.C):
        ok = np.isfinite(rec[c]) & np.isfinite(pv[c]) & (pv[c] > 0) & (rec[c] > 0)
        dias = np.nonzero(ok)[0]
        out.append((dias, np.log(rec[c, ok] / pv[c, ok])))
    return out


def _usavel(dias, D):
    return dias.size >= D - 5 and dias[0] == 0  # campanha madura do início, quase sem lacuna


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true")
    a = ap.parse_args()
    nc, nt = (3, 3) if a.rapido else (10, 16)
    seeds_cal = list(range(20261301, 20261301 + nc))
    seeds_teste = list(range(20261401, 20261401 + nt))
    C, D = (20, 60) if a.rapido else (50, 60)
    # calibração no estável
    cal = []
    for s in seeds_cal:
        for dias, x in series_log_rpm(simular("estavel", s, n_campanhas=C, n_dias=D)):
            if _usavel(dias, D):
                cal.append(x)
    calib = {nome: M.calibrar_limiar(cal, metodo=nome, alvo_fa_por_unidade_tempo=ALVO_FA, unidade_tempo=7.0,
                                     grade=grade, **par) for nome, (par, grade) in METODOS.items()}
    lim = {n: calib[n]["limiar"] if calib[n]["limiar"] is not None else float(METODOS[n][1].max()) for n in METODOS}
    nome_lim = {"media_movel": "limiar", "cusum": "h", "bocpd": "limiar"}
    # teste em quebra_regime_rpm
    dia_quebra = int(np.floor(0.5 * D + 1e-9))  # QuebraRegime em 50% do período (hora 14)
    por_seed = {n: {"poder": [], "fa_semana": [], "atraso": []} for n in METODOS}
    for s in seeds_teste:
        sim = simular("quebra_regime_rpm", s, n_campanhas=C, n_dias=D)
        quebrou = sim.mundo.flags["fator_rpm"][:, -1] < 1.0  # verdade (só avaliação)
        series = series_log_rpm(sim)
        for n, (par, _) in METODOS.items():
            det, alvo, fa, semanas, atrasos = 0, 0, 0, 0.0, []
            for c, (dias, x) in enumerate(series):
                if not _usavel(dias, D):
                    continue
                ach = M.detectar_quebra(x, metodo=n, **par, **{nome_lim[n]: lim[n]})
                dia_acao = dias[ach.indice] + ATRASO if ach.detectado else None
                fim_limpo = dia_quebra if quebrou[c] else D + ATRASO
                if ach.detectado and dia_acao < fim_limpo:
                    fa += 1
                    semanas += (dias[ach.indice] - dias[N_REF] + 1) / 7
                else:
                    semanas += (min(fim_limpo - ATRASO, D) - dias[N_REF]) / 7
                if quebrou[c]:
                    alvo += 1
                    if ach.detectado and dia_quebra <= dia_acao <= dia_quebra + JANELA_PODER:
                        det += 1
                        atrasos.append(dia_acao - dia_quebra)
            por_seed[n]["poder"].append(det / alvo if alvo else np.nan)
            por_seed[n]["fa_semana"].append(fa / semanas if semanas else np.nan)
            por_seed[n]["atraso"].append(float(np.median(atrasos)) if atrasos else np.nan)
    res = {"limiares_calibrados": lim, "dia_quebra": dia_quebra,
           "calibracao": {n: {"limiar": calib[n]["limiar"], "curva": calib[n]["curva"]} for n in METODOS},
           "por_metodo": {n: {k: M.ic_bootstrap_media(v) for k, v in d.items()} for n, d in por_seed.items()}}
    for n in ("cusum", "bocpd"):
        dif = pareado(por_seed[n]["poder"], por_seed["media_movel"]["poder"])
        res[f"H3_poder_{n}_menos_media_movel"] = dif
        res[f"H3_{n}_supera"] = supera(dif, direcao="maior")
    res["H3_suportada"] = bool(res["H3_cusum_supera"] and res["H3_bocpd_supera"])
    obj = {"manifesto": manifesto(__file__, seeds=seeds_cal + seeds_teste,
                                  parametros={"C": C, "D": D, "atraso": ATRASO, "n_ref": N_REF, "alvo_fa": ALVO_FA,
                                              "janela_poder": JANELA_PODER,
                                              "metodos": {k: v[0] for k, v in METODOS.items()}}),
           "resultados": res}
    saida("m3_mudanca.json", obj, rapido=a.rapido)


if __name__ == "__main__":
    main()
