"""M12 — Ridge × HistGradientBoosting com features `as_of` e validação rolling-origin, contra baselines
"último maduro" e "média dos maduros"; teste de vazamento com feature do futuro injetada.

Tarefa: no corte do dia o (12:00 local), prever o lucro FINAL do dia o + 1 por campanha. Treino só com
rótulos já maduros no corte de treino. Retreino a cada 5 origens. Pré-registro: PRE-REGISTRO.md (M12).
Saída: results/fundacao/modelos/m12_tabular.json
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fundacao_modelos_comum import manifesto, razao_pareada, saida  # noqa: E402

import numpy as np  # noqa: E402

from volc_dil.fundacao import modelos as M  # noqa: E402
from volc_dil.fundacao.modelos.tabular import FINAL  # noqa: E402
from volc_dil.fundacao.simulador import simular  # noqa: E402

N_LAGS, N_MEDIA, HORIZ, RETREINO, O_TESTE0 = 7, 7, 1, 5, 30


def um_mundo(cen, seed, C, D):
    sim = simular(cen, seed, n_campanhas=C, n_dias=D)
    m = sim.mundo
    kw = dict(entidades=M.ids_campanhas(m), dias=M.dias_iso(m))
    tc = M.TabelaVersoes.de_registros(sim.leituras.registros, fonte="google_ads", metrica="cost", **kw)
    tr = M.TabelaVersoes.de_registros(sim.leituras.registros, fonte="joinads", metrica="revenue", **kw)
    cortes = [M.instante_local(m, k, 12) for k in range(D)]
    P = {k: (tc.painel(cortes[k]) / 1e6, tr.painel(cortes[k]) / 1e6, tc.painel_maturidade(cortes[k]),
             tr.painel_maturidade(cortes[k])) for k in range(D)}
    final = (tr.final() - tc.final()) / 1e6
    dows = [datetime.fromisoformat(d).weekday() for d in M.dias_iso(m)]

    def X_de(o):
        c, r, mc, mr = P[o]
        return M.features_no_corte(c, r, mc, mr, o, n_lags=N_LAGS, n_media=N_MEDIA,
                                   dia_semana_alvo=dows[min(o + HORIZ, D - 1)])

    feats = {o: X_de(o)[0] for o in range(14, D - HORIZ)}
    nomes = X_de(14)[1]
    i_ult, i_med = nomes.index("ultimo_maduro"), nomes.index("media_maduros")
    pred = {k: [] for k in ("ultimo_maduro", "media_maduros", "ridge", "hgb", "ridge_com_vazamento")}
    alvo_teste = []
    achados_meta = 0
    n_origens = 0
    modelos = {}
    rng = np.random.default_rng(seed)
    sd_alvo = float(np.nanstd(final))
    for o in range(O_TESTE0, D - HORIZ):
        if (o - O_TESTE0) % RETREINO == 0:
            # rótulos maduros no corte o: custo e receita do dia-alvo com maturidade final
            _, _, mc, mr = P[o]
            Xs, ys = [], []
            for oo in range(14, o):
                t = oo + HORIZ
                if t >= D:
                    continue
                c_, r_, _, _ = P[o]
                lab = r_[:, t] - c_[:, t]
                ok = (mc[:, t] == FINAL) & (mr[:, t] == FINAL) & np.isfinite(lab)
                Xs.append(feats[oo][ok]); ys.append(lab[ok])
            Xtr, ytr = np.vstack(Xs), np.concatenate(ys)
            vaz_tr = ytr + rng.normal(0, 0.1 * sd_alvo, ytr.size)  # feature do futuro injetada (o próprio alvo)
            modelos = {"Xtr": Xtr, "ytr": ytr, "vaz": vaz_tr}
        X = feats[o]
        y = final[:, o + HORIZ]
        ok = np.isfinite(y)
        Xo, yo = X[ok], y[ok]
        alvo_teste.append(yo)
        pred["ultimo_maduro"].append(np.where(np.isfinite(Xo[:, i_ult]), Xo[:, i_ult], np.nanmean(modelos["ytr"])))
        pred["media_maduros"].append(np.where(np.isfinite(Xo[:, i_med]), Xo[:, i_med], np.nanmean(modelos["ytr"])))
        pred["ridge"].append(M.ajustar_e_prever("ridge", modelos["Xtr"], modelos["ytr"], Xo))
        pred["hgb"].append(M.ajustar_e_prever("hgb", modelos["Xtr"], modelos["ytr"], Xo, seed=seed))
        vz_te = yo + rng.normal(0, 0.1 * sd_alvo, yo.size)
        pred["ridge_com_vazamento"].append(M.ajustar_e_prever("ridge", np.column_stack([modelos["Xtr"], modelos["vaz"]]),
                                                              modelos["ytr"], np.column_stack([Xo, vz_te])))
        # checagem por metadado: a feature injetada só existe quando o alvo amadurece (≥ corte o + HORIZ + 3)
        metas = [M.FeatureMeta(n, cortes[o]) for n in nomes] + [M.FeatureMeta("lucro_alvo_final",
                                                                               cortes[min(o + HORIZ + 3, D - 1)] + 1)]
        achados_meta += int(any(a.detalhes["feature"] == "lucro_alvo_final" for a in M.checar_vazamento(metas, cortes[o])))
        n_origens += 1
    y = np.concatenate(alvo_teste)
    mae = {k: float(np.mean(np.abs(np.concatenate(v) - y))) for k, v in pred.items()}
    emp = M.vazamento_empirico(mae["ridge"], mae["ridge_com_vazamento"], ganho_implausivel=0.3, nome="lucro_alvo_final")
    emp_honesto = M.vazamento_empirico(mae["media_maduros"], mae["ridge"], ganho_implausivel=0.3, nome="modelo_honesto")
    return {"mae": mae, "deteccao_meta": achados_meta / n_origens, "deteccao_empirica": emp.detectado,
            "ganho_vazamento": emp.estatistica, "alarme_falso_empirico_modelo_honesto": emp_honesto.detectado,
            "n_teste": int(y.size)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true")
    a = ap.parse_args()
    seeds = list(range(20262301, 20262301 + (2 if a.rapido else 10)))
    C, D = (15, 45) if a.rapido else (50, 60)
    res = {}
    for cen in ("estavel", "quebra_regime_rpm"):
        ws = [um_mundo(cen, s, C, D) for s in seeds]
        mae = {k: [w["mae"][k] for w in ws] for k in ws[0]["mae"]}
        bloco = {"mae": {k: M.ic_bootstrap_media(v) for k, v in mae.items()}}
        for k in ("ridge", "hgb", "ultimo_maduro"):
            r = razao_pareada(mae[k], mae["media_maduros"])
            bloco[f"mae_rel_{k}_sobre_media_maduros"] = r
            bloco[f"{k}_supera_2pct"] = bool(r["ic95"][1] is not None and r["ic95"][1] < 0.98)
        bloco["deteccao_vazamento_metadado"] = float(np.mean([w["deteccao_meta"] for w in ws]))
        bloco["deteccao_vazamento_empirica"] = float(np.mean([w["deteccao_empirica"] for w in ws]))
        bloco["ganho_mae_com_vazamento"] = M.ic_bootstrap_media([w["ganho_vazamento"] for w in ws])
        bloco["alarme_falso_empirico_modelo_honesto"] = float(np.mean([w["alarme_falso_empirico_modelo_honesto"] for w in ws]))
        res[cen] = bloco
    e = res["estavel"]
    res["H12_suportada"] = bool(not e["ridge_supera_2pct"] and not e["hgb_supera_2pct"]
                                and e["deteccao_vazamento_metadado"] == 1.0 and e["deteccao_vazamento_empirica"] == 1.0)
    obj = {"manifesto": manifesto(__file__, seeds=seeds, parametros={"C": C, "D": D, "n_lags": N_LAGS, "horizonte": HORIZ,
                                                                     "retreino": RETREINO, "origem_teste0": O_TESTE0}),
           "resultados": res}
    saida("m12_tabular.json", obj, rapido=a.rapido)


if __name__ == "__main__":
    main()
