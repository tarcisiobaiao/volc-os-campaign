"""M2 — Empirical Bayes (herdado) para CTR e RPM de campanhas novas em `campanha_nova_aprendendo`.

Pergunta: no dia k após o lançamento (k = 1, 3, 7 dias de dado maduro), a taxa encolhida prevê melhor a
taxa dos 14 dias seguintes que a taxa crua? E escolhe menos "vencedores por sorte" no top 20%?
Pré-registro: PRE-REGISTRO.md (M2). Saída: results/fundacao/modelos/m2_eb.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fundacao_modelos_comum import manifesto, pareado, razao_pareada, saida, supera  # noqa: E402

import numpy as np  # noqa: E402

from volc_dil.fundacao import modelos as M  # noqa: E402
from volc_dil.fundacao.simulador import simular  # noqa: E402

KS = (1, 3, 7)
FUTURO = 14
FRAC_TOP = 0.2


def _painel_final(sim, fonte, metrica):
    tab = M.TabelaVersoes.de_registros(sim.leituras.registros, fonte=fonte, metrica=metrica,
                                       entidades=M.ids_campanhas(sim.mundo), dias=M.dias_iso(sim.mundo))
    return tab.final()


def um_mundo(seed, C, D):
    sim = simular("campanha_nova_aprendendo", seed, n_campanhas=C, n_dias=D)
    cliques = _painel_final(sim, "google_ads", "clicks")
    imp = _painel_final(sim, "google_ads", "impressions")
    rec = _painel_final(sim, "joinads", "revenue")
    pv = _painel_final(sim, "joinads", "pageviews")
    # lançamento OBSERVÁVEL: 1º dia com registro de impressões; campanha "nova" = lança depois do dia 0
    tem = np.isfinite(imp)
    lanc = np.where(tem.any(axis=1), tem.argmax(axis=1), D)
    novas = np.nonzero((lanc > 0) & (lanc + max(KS) + FUTURO <= D))[0]
    out = {}
    for k in KS:
        sel = novas
        x = np.array([np.nansum(cliques[c, lanc[c]:lanc[c] + k]) for c in sel])
        n = np.array([np.nansum(imp[c, lanc[c]:lanc[c] + k]) for c in sel])
        vx = np.array([np.nansum(cliques[c, lanc[c] + k:lanc[c] + k + FUTURO]) for c in sel])
        vn = np.array([np.nansum(imp[c, lanc[c] + k:lanc[c] + k + FUTURO]) for c in sel])
        ok = (n > 0) & (vn > 0)
        x, n, vx, vn = x[ok], n[ok], vx[ok], vn[ok]
        verdade = vx / vn
        cru = x / n
        eb = M.encolher_taxa(x, n, nivel=0.9)
        r = {"n_campanhas": int(ok.sum()),
             "ctr": {"mse_cru": float(np.mean((cru - verdade) ** 2)), "mse_eb": float(np.mean((eb["media"] - verdade) ** 2)),
                     "sorte_cru": M.vencedores_por_sorte(cru, verdade, frac_top=FRAC_TOP)["por_sorte"],
                     "sorte_eb": M.vencedores_por_sorte(eb["media"], verdade, frac_top=FRAC_TOP)["por_sorte"],
                     "vies_cru_rel": float(np.mean(cru / verdade - 1)), "prior_status": eb["prior"]["status"]}}
        # RPM diário por campanha (R$ por mil pageviews); EB normal exige >= 2 dias por unidade
        if k >= 2:
            s1, s2, kn, vr = [], [], [], []
            for c in sel[ok]:
                rr = rec[c, lanc[c]:lanc[c] + k]
                pp = pv[c, lanc[c]:lanc[c] + k]
                okd = np.isfinite(rr) & np.isfinite(pp) & (pp > 0)
                rpm = 1000 * rr[okd] / pp[okd] / 1e6
                s1.append(rpm.sum()); s2.append((rpm ** 2).sum()); kn.append(okd.sum())
                fr, fp = rec[c, lanc[c] + k:lanc[c] + k + FUTURO], pv[c, lanc[c] + k:lanc[c] + k + FUTURO]
                okf = np.isfinite(fr) & np.isfinite(fp)
                vr.append(1000 * np.nansum(fr[okf]) / max(np.nansum(fp[okf]), 1) / 1e6)
            s1, s2, kn, vr = map(np.asarray, (s1, s2, kn, vr))
            e = M.encolher_media(s1, s2, kn, nivel=0.9)
            cru_r = np.where(kn > 0, s1 / np.maximum(kn, 1), np.nan)
            okr = np.isfinite(cru_r)
            r["rpm"] = {"mse_cru": float(np.mean((cru_r[okr] - vr[okr]) ** 2)),
                        "mse_eb": float(np.mean((e["media"][okr] - vr[okr]) ** 2)),
                        "sorte_cru": M.vencedores_por_sorte(cru_r, vr, frac_top=FRAC_TOP)["por_sorte"],
                        "sorte_eb": M.vencedores_por_sorte(e["media"], vr, frac_top=FRAC_TOP)["por_sorte"],
                        "status_prior": e["status"]}
        else:
            r["rpm"] = {"status": "insuficiente", "motivo": "variância intra-campanha não identificável com 1 dia"}
        out[k] = r
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true")
    a = ap.parse_args()
    seeds = list(range(20261201, 20261201 + (3 if a.rapido else 16)))
    C, D = (30, 50) if a.rapido else (60, 60)
    mundos = [um_mundo(s, C, D) for s in seeds]
    res = {}
    for k in KS:
        bloco = {"n_campanhas_novas_media": float(np.mean([w[k]["n_campanhas"] for w in mundos]))}
        for alvo in ("ctr", "rpm"):
            if "mse_cru" not in mundos[0][k][alvo]:
                bloco[alvo] = mundos[0][k][alvo]
                continue
            cru = [w[k][alvo]["mse_cru"] for w in mundos]
            eb = [w[k][alvo]["mse_eb"] for w in mundos]
            sc = [w[k][alvo]["sorte_cru"] for w in mundos]
            se = [w[k][alvo]["sorte_eb"] for w in mundos]
            bloco[alvo] = {"razao_mse_eb_sobre_cru": razao_pareada(eb, cru),
                           "sorte_cru": M.ic_bootstrap_media(sc), "sorte_eb": M.ic_bootstrap_media(se),
                           "dif_sorte_eb_menos_cru": pareado(se, sc)}
            if alvo == "ctr":
                bloco[alvo]["vies_relativo_ctr_cru_vs_futuro"] = M.ic_bootstrap_media(
                    [w[k]["ctr"]["vies_cru_rel"] for w in mundos])
        res[str(k)] = bloco
    h2 = {
        "mse_ctr_k1": res["1"]["ctr"]["razao_mse_eb_sobre_cru"]["ic95"][1] < 1,
        "mse_ctr_k3": res["3"]["ctr"]["razao_mse_eb_sobre_cru"]["ic95"][1] < 1,
        "mse_rpm_k3": res["3"]["rpm"]["razao_mse_eb_sobre_cru"]["ic95"][1] < 1,
        "sorte_ctr_k1": supera(res["1"]["ctr"]["dif_sorte_eb_menos_cru"], direcao="menor"),
    }
    res["H2_criterios"] = h2
    res["H2_suportada"] = bool(all(v for v in h2.values()))
    obj = {"manifesto": manifesto(__file__, seeds=seeds, parametros={"C": C, "D": D, "ks": KS, "futuro": FUTURO,
                                                                     "frac_top": FRAC_TOP}), "resultados": res}
    saida("m2_eb.json", obj, rapido=a.rapido)


if __name__ == "__main__":
    main()
