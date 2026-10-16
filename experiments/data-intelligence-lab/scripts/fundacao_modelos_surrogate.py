"""M6 — surrogate: reabre o portão herdado (`volc_dil.surrogate.feasibility`) com linhas geradas pelo
simulador novo, só para dizer se alguma PREMISSA muda (não reabre o surrogate como ganho).

Verifica: (i) veredito por volume (50×30 ≈ horizonte atual × 50×90 = mínimo calibrado herdado);
(ii) força do sinal sessões→receita no mundo sintético (skill fora do tempo de Ridge com efeito fixo de
campanha vs média da campanha); (iii) efeito do R2 (sensor descarta campanha): cobertura das features
de sessão no grão campanha. Pré-registro: PRE-REGISTRO.md (M6). Saída: results/fundacao/modelos/m6_surrogate.json
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fundacao_modelos_comum import manifesto, saida  # noqa: E402

import numpy as np  # noqa: E402

from volc_dil.fundacao import modelos as M  # noqa: E402
from volc_dil.fundacao.simulador import simular  # noqa: E402
from volc_dil.surrogate.feasibility import Feature, LinhaRotulada, avaliar_viabilidade  # noqa: E402


def _tabelas(sim):
    kw = dict(entidades=M.ids_campanhas(sim.mundo), dias=M.dias_iso(sim.mundo))
    t = lambda f, m: M.TabelaVersoes.de_registros(sim.leituras.registros, fonte=f, metrica=m, **kw)  # noqa: E731
    return {"receita": t("joinads", "revenue"), "pv_joinads": t("joinads", "pageviews"),
            "sessoes": t("site_analytics", "sessions"), "destino": t("site_analytics", "destino"),
            "cliques": t("google_ads", "clicks")}


def linhas(sim):
    tb = _tabelas(sim)
    fin = {k: v.final() for k, v in tb.items()}
    # disponibilidade: instante do 1º registro com valor de cada fato (por fonte)
    disp = {}
    for k, t in tb.items():
        P = np.full(t.forma, np.inf)
        np.minimum.at(P, (t.ent, t.dia), t.available.astype(float))
        disp[k] = P
    out = []
    for e, eid in enumerate(tb["receita"].entidades):
        for d, dia in enumerate(tb["receita"].dias):
            rot = fin["receita"][e, d]
            per = date.fromisoformat(dia[:10])
            feats = {}
            for k, origem in (("sessoes", "browser"), ("destino", "browser"), ("cliques", "google_ads"),
                              ("pv_joinads", "joinads")):
                v = fin[k][e, d]
                feats[k] = Feature(None if not np.isfinite(v) else float(v), origem,
                                   None if not np.isfinite(disp[k][e, d]) else
                                   datetime.fromtimestamp(disp[k][e, d], timezone.utc))
            out.append(LinhaRotulada(eid, per, "campaign_day", None if not np.isfinite(rot) else float(rot) / 1e6,
                                     bool(np.isfinite(rot)), "joinads", feats))
    return out


def skill_oot(sim, frac_teste=0.3):
    """Ridge com efeito fixo de campanha sobre sessões e cliques (D+1) × baseline média da campanha."""
    from sklearn.linear_model import RidgeCV

    tb = _tabelas(sim)
    y = tb["receita"].final() / 1e6
    s, c = tb["sessoes"].final(), tb["cliques"].final()
    E, D = y.shape
    corte = int(D * (1 - frac_teste))
    ok = np.isfinite(y) & np.isfinite(s) & np.isfinite(c)
    ee, dd = np.nonzero(ok)
    X = np.column_stack([s[ee, dd], c[ee, dd], np.eye(E)[ee]])
    tr, te = dd < corte, dd >= corte
    if tr.sum() < 10 or te.sum() < 10:
        return {"status": "insuficiente", "motivo": "linhas com feature de sessão no grão campanha < 10",
                "cobertura_feature_sessao": float(np.isfinite(s).mean())}
    m = RidgeCV(alphas=np.logspace(-2, 4, 13)).fit(X[tr], y[ee, dd][tr])
    base = np.array([np.nanmean(np.where(ok[e, :corte], y[e, :corte], np.nan)) for e in ee[te]])
    mae_m = float(np.mean(np.abs(m.predict(X[te]) - y[ee, dd][te])))
    mae_b = float(np.mean(np.abs(base - y[ee, dd][te])))
    return {"mae_modelo": mae_m, "mae_media_campanha": mae_b, "skill": 1 - mae_m / mae_b, "n_teste": int(te.sum()),
            "cobertura_feature_sessao": float(np.isfinite(s).mean())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true")
    a = ap.parse_args()
    seeds = list(range(20261701, 20261701 + (2 if a.rapido else 6)))
    res = {"portao": {}, "skill": {}}
    for nome, cen, C, D in (("estavel_50x30", "estavel", 50, 30), ("estavel_50x90", "estavel", 50, 90),
                            ("sensor_sem_campanha_50x90", "sensor_sem_campanha", 50, 90)):
        if a.rapido:
            C, D = 10, min(D, 30)
        sim = simular(cen, seeds[0], n_campanhas=C, n_dias=D)
        r = avaliar_viabilidade(linhas(sim), grao_alvo="campaign_day")
        cob = np.mean([l.features["sessoes"].valor is not None for l in linhas(sim)])
        res["portao"][nome] = {**r.para_json(), "cobertura_feature_sessoes_no_grao_campanha": float(cob)}
    for cen in ("estavel", "sensor_sem_campanha"):
        sk = [skill_oot(simular(cen, s, n_campanhas=10 if a.rapido else 50, n_dias=30 if a.rapido else 90))
              for s in seeds]
        res["skill"][cen] = {"skill": M.ic_bootstrap_media([x.get("skill", np.nan) for x in sk]),
                             "cobertura_feature_sessao": M.ic_bootstrap_media([x.get("cobertura_feature_sessao", np.nan)
                                                                               for x in sk])}
    res["leitura"] = {
        "vereditos": {k: v["veredito"] for k, v in res["portao"].items()},
        "r2_muda_veredito": res["portao"]["sensor_sem_campanha_50x90"]["veredito"] != res["portao"]["estavel_50x90"]["veredito"],
        "cobertura_sessao_r2": res["portao"]["sensor_sem_campanha_50x90"]["cobertura_feature_sessoes_no_grao_campanha"],
    }
    obj = {"manifesto": manifesto(__file__, seeds=seeds, parametros={"grao": "campaign_day", "rotulo": "joinads final"}),
           "resultados": res}
    saida("m6_surrogate.json", obj, rapido=a.rapido)


if __name__ == "__main__":
    main()
