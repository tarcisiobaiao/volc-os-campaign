"""M9 — anomalias: z-score × mediana/MAD × sazonal robusto (outlier_bot); lacuna ≠ anomalia
(fonte_fora_do_ar); zero implausível (zero_falso). Detectores NÃO leem gabarito/mundo; a verdade só rotula.

Pré-registro: PRE-REGISTRO.md (M9). Saída: results/fundacao/modelos/m9_anomalia.json
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

LIMIARES = {"zscore": 3.0, "robusto_mad": 3.5, "sazonal_robusto": 3.5}
JANELA = 14


def parte_bot(seed, C, D):
    sim = simular("outlier_bot", seed, n_campanhas=C, n_dias=D)
    kw = dict(entidades=M.ids_campanhas(sim.mundo), dias=M.dias_iso(sim.mundo))
    cl = M.TabelaVersoes.de_registros(sim.leituras.registros, fonte="google_ads", metrica="clicks", **kw).final()
    se = M.TabelaVersoes.de_registros(sim.leituras.registros, fonte="site_analytics", metrica="sessions", **kw).final()
    bot_dia = sim.mundo.flags["bot_hora"].reshape(C, D, 24).any(axis=2)  # verdade (rótulo)
    out = {}
    for met, lim in LIMIARES.items():
        alarmes, verdade = [], []
        for c in range(C):
            x = np.log((cl[c] + 1) / (se[c] + 1))
            serie = [None if not np.isfinite(v) else float(v) for v in x]
            ach = M.detectar_anomalias(serie, metodo=met, limiar=lim, janela=JANELA, bilateral=False, min_hist=7)
            alarmes += [c * D + a.indice for a in ach if a.tipo == "anomalia_valor"]
            verdade += [c * D + d for d in np.nonzero(bot_dia[c])[0] if d >= 7]
        out[met] = M.precisao_recall(alarmes, verdade)
    out["n_dias_bot"] = int(bot_dia[:, 7:].sum())
    return out


def _serie_d1(registros, fonte, metrica, ids, dias):
    """Série da leitura D-1 por campanha: (valores, status, obs_id), None onde não houve registro."""
    ie, idd = {e: i for i, e in enumerate(ids)}, {d: i for i, d in enumerate(dias)}
    V = [[None] * len(dias) for _ in ids]
    S = [["missing"] * len(dias) for _ in ids]
    O = [[None] * len(dias) for _ in ids]
    for r in registros:
        if (r.fonte == fonte and r.metrica == metrica and r.tipo_leitura == "d1" and r.entidade_tipo == "campaign"
                and not r.dimensoes and r.entidade in ie and r.janela_inicio in idd):
            e, d = ie[r.entidade], idd[r.janela_inicio]
            if O[e][d] is None or r.available_at < O[e][d][1]:  # 1ª leitura D-1 (sem duplicata)
                V[e][d], S[e][d], O[e][d] = r.valor, r.status, (r.obs_id, r.available_at)
    return V, S, O


def parte_fora_do_ar(seed, C, D):
    sim = simular("fonte_fora_do_ar", seed, n_campanhas=C, n_dias=D)
    ids, dias = M.ids_campanhas(sim.mundo), M.dias_iso(sim.mundo)
    V, S, _ = _serie_d1(sim.leituras.registros, "joinads", "revenue", ids, dias)
    lacunas = anom_em_lacuna = naive_em_lacuna = 0
    for c in range(C):
        sem = {d for d in range(D) if V[c][d] is None}
        ach = M.detectar_anomalias(V[c], metodo="robusto_mad", limiar=3.5, janela=JANELA, status=S[c], min_hist=7)
        lacunas += sum(a.tipo == "lacuna" for a in ach)
        anom_em_lacuna += sum(a.tipo == "anomalia_valor" and a.indice in sem for a in ach)
        naive_em_lacuna += len(set(M.nulo_como_zero(V[c], limiar=3.0, janela=JANELA, min_hist=7)) & sem)
    n_indisp = sum(s == "unavailable" for row in S for s in row)
    return {"lacunas_classificadas": lacunas, "registros_unavailable_d1": n_indisp,
            "anomalias_de_valor_em_lacuna": anom_em_lacuna, "alarmes_nulo_como_zero_em_lacuna": naive_em_lacuna}


def parte_zero_falso(seed, C, D):
    sim = simular("zero_falso", seed, n_campanhas=C, n_dias=D)
    ids, dias = M.ids_campanhas(sim.mundo), M.dias_iso(sim.mundo)
    V, S, O = _serie_d1(sim.leituras.registros, "google_ads", "clicks", ids, dias)
    alarmes, verdade = [], []
    for c in range(C):
        alarmes += [c * D + a.indice for a in M.zero_implausivel(V[c], janela=7, p_max=1e-3, status=S[c])]
        verdade += [c * D + d for d in range(D)
                    if O[c][d] is not None and "zero_falso" in sim.leituras.gabarito[O[c][d][0]].armadilhas]
    return M.precisao_recall(alarmes, verdade)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true")
    a = ap.parse_args()
    seeds = list(range(20262001, 20262001 + (3 if a.rapido else 12)))
    C, D = (20, 40) if a.rapido else (50, 60)
    bots = [parte_bot(s, C, D) for s in seeds]
    fora = [parte_fora_do_ar(s, C, 30) for s in seeds]
    zf = [parte_zero_falso(s, C, 30) for s in seeds]
    res = {"outlier_bot": {m: {k: M.ic_bootstrap_media([b[m][k] if b[m][k] is not None else np.nan for b in bots])
                               for k in ("precisao", "recall", "f1")} for m in LIMIARES},
           "n_dias_bot_medio": float(np.mean([b["n_dias_bot"] for b in bots])),
           "fonte_fora_do_ar": {k: int(sum(f[k] for f in fora)) for k in fora[0]},
           "zero_falso": {k: M.ic_bootstrap_media([z[k] if z[k] is not None else np.nan for z in zf])
                          for k in ("precisao", "recall", "f1")}}
    f1 = {m: [b[m]["f1"] or 0.0 for b in bots] for m in LIMIARES}
    for m in ("robusto_mad", "sazonal_robusto"):
        d = pareado(f1[m], f1["zscore"])
        res[f"f1_{m}_menos_zscore"] = d
        res[f"{m}_supera_zscore"] = supera(d, direcao="maior")
    res["H9a_suportada"] = bool(res["robusto_mad_supera_zscore"] and res["sazonal_robusto_supera_zscore"])
    fo = res["fonte_fora_do_ar"]
    n_janelas = len(seeds)  # 1 janela de indisponibilidade JoinAds por mundo (cenário fonte_fora_do_ar)
    fo["alarmes_nulo_como_zero_por_janela"] = fo["alarmes_nulo_como_zero_em_lacuna"] / n_janelas
    res["H9b_suportada"] = bool(fo["anomalias_de_valor_em_lacuna"] == 0 and fo["alarmes_nulo_como_zero_por_janela"] >= 1)
    z = res["zero_falso"]
    res["H9c_suportada"] = bool(z["recall"]["estimativa"] >= 0.8 and z["precisao"]["estimativa"] >= 0.9)
    obj = {"manifesto": manifesto(__file__, seeds=seeds, parametros={"C": C, "D": D, "limiares": LIMIARES, "janela": JANELA,
                                                                     "zero_p_max": 1e-3, "zero_janela": 7}),
           "resultados": res}
    saida("m9_anomalia.json", obj, rapido=a.rapido)


if __name__ == "__main__":
    main()
