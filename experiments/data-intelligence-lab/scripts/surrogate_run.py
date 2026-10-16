"""Fase 6: roda o portão sobre os dados reais versionados e o experimento sintético.

Uso (da raiz do repo):
    OMP_NUM_THREADS=2 experiments/data-intelligence-lab/.venv/bin/python \
        experiments/data-intelligence-lab/scripts/surrogate_run.py
Grava results/surrogate/surrogate_results.json. Determinístico por seed.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

LAB = Path(__file__).resolve().parents[1]
RAIZ = LAB.parents[1]
sys.path.insert(0, str(LAB / "src"))

from sklearn.linear_model import RidgeCV  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from volc_dil.contracts import manifesto_execucao, sha256_arquivo, sha256_codigo  # noqa: E402
from volc_dil.surrogate import ParametrosPortao, avaliar_viabilidade  # noqa: E402
from volc_dil.surrogate.experiment import ALPHAS, Mundo, grade  # noqa: E402
from volc_dil.surrogate.real_probe import GOLDEN_META, SENAC, carregar_golden_meta, carregar_senac  # noqa: E402

SEED0 = 20261015


def descritivo_real(linhas, nomes, fracao_teste=0.3, n_boot=2000, seed=SEED0):
    """Tentativa DESCRITIVA (o portão já disse 'insuficiente'): Ridge vs média por unidade, fora do tempo."""
    ok = [l for l in linhas if l.rotulo is not None and l.rotulo_maduro and all(l.features[n].valor is not None for n in nomes)]
    periodos = sorted({l.periodo for l in ok})
    n_te = max(1, round(len(periodos) * fracao_teste))
    corte = periodos[-n_te]
    tr = [l for l in ok if l.periodo < corte]
    unidades_tr = {x.unidade_id for x in tr}
    te = [l for l in ok if l.periodo >= corte and l.unidade_id in unidades_tr]
    if len(tr) < 5 or len(te) < 3:
        return {"n_treino": len(tr), "n_teste": len(te), "status": "amostra pequena demais até para descritivo"}
    unidades = sorted(unidades_tr)

    def matriz(ls):
        f = np.array([[l.features[n].valor for n in nomes] for l in ls], dtype=float)
        oh = np.array([[1.0 if l.unidade_id == u else 0.0 for u in unidades] for l in ls])
        return f, oh

    ftr, ohtr = matriz(tr)
    fte, ohte = matriz(te)
    sc = StandardScaler().fit(ftr)
    m = RidgeCV(alphas=ALPHAS).fit(np.hstack([sc.transform(ftr), ohtr]), [l.rotulo for l in tr])
    pred = m.predict(np.hstack([sc.transform(fte), ohte]))
    y = np.array([l.rotulo for l in te])
    medias = {u: np.mean([l.rotulo for l in tr if l.unidade_id == u]) for u in unidades}
    base = np.array([medias[l.unidade_id] for l in te])
    rng = np.random.default_rng(seed)
    sk = []
    for _ in range(n_boot):
        i = rng.integers(0, len(y), len(y))
        mb = np.mean(np.abs(y[i] - base[i]))
        if mb > 0:
            sk.append(1 - np.mean(np.abs(y[i] - pred[i])) / mb)
    sk = np.array(sk)
    return {"n_treino": len(tr), "n_teste": len(te), "periodos_teste": n_te, "features": nomes,
            "skill_vs_media_unidade": float(1 - np.mean(np.abs(y - pred)) / np.mean(np.abs(y - base))),
            "skill_ic95_bootstrap": [float(np.quantile(sk, 0.025)), float(np.quantile(sk, 0.975))],
            "alpha": float(m.alpha_),
            "interpretavel": len(te) >= 30,
            "nota": "descritivo; com menos de 30 pontos de teste o bootstrap não sustenta conclusão"}


def main():
    t0 = time.perf_counter()
    out: dict = {}
    senac, meta = carregar_senac(RAIZ), carregar_golden_meta(RAIZ)
    p = ParametrosPortao()
    out["real"] = {
        "entradas_sha256": {str(SENAC): sha256_arquivo(str(RAIZ / SENAC)),
                            str(GOLDEN_META): sha256_arquivo(str(RAIZ / GOLDEN_META))},
        "senac_campaign_day": avaliar_viabilidade(senac, grao_alvo="campaign_day", parametros=p).para_json(),
        "meta_campaign_day": avaliar_viabilidade(meta, grao_alvo="campaign_day", parametros=p).para_json(),
        "meta_session": avaliar_viabilidade(meta, grao_alvo="session", parametros=p).para_json(),
        "meta_descritivo_valido": descritivo_real(meta, ["meta_spend", "meta_impressions", "meta_clicks"]),
        "meta_descritivo_com_circular": descritivo_real(
            meta, ["meta_spend", "meta_impressions", "meta_clicks", "gam_impressions", "gam_clicks"]),
    }
    tamanhos = [(1, 16), (7, 17), (10, 30), (20, 60), (50, 90), (100, 120)]
    validas = ["s1", "s2", "s3"]
    out["grade"] = []
    for forca in (0.0, 0.25, 0.5):
        out["grade"] += grade([Mundo(u, t, forca_sinal=forca) for u, t in tamanhos], validas,
                              range(SEED0, SEED0 + 200))
    out["contraprovas"] = []
    for u, t in [(7, 17), (50, 90)]:
        for nome, feats in [("validas", validas), ("com_circular", validas + ["circ"]),
                            ("com_vazamento", validas + ["vaz"])]:
            linha = grade([Mundo(u, t, forca_sinal=0.25)], feats, range(SEED0, SEED0 + 100), hgb_min_treino=None)[0]
            linha["caso"] = nome
            out["contraprovas"].append(linha)
    cal = [g for g in out["grade"] if g["forca_sinal"] == 0.25 and g["ridge_p_skill_pos"] is not None
           and g["ridge_p_skill_pos"] >= 0.8 and g["ridge_skill_media_ic95"][1] > 0]
    out["calibracao_portao"] = {
        "criterio": "P(skill_ridge>0) >= 0.8 e IC95 inferior da skill média > 0, sinal fraco (0.25)",
        "menor_volume": min(cal, key=lambda g: g["linhas"]) if cal else None,
        "parametros_portao_usados": p.__dict__,
    }
    out["manifesto"] = manifesto_execucao(
        nome="surrogate_fase6", seed=SEED0, entradas=out["real"]["entradas_sha256"],
        parametros={"tamanhos": tamanhos, "forcas": [0.0, 0.25, 0.5], "seeds_grade": 200,
                    "seeds_contraprova": 100, "fracao_teste": 0.3},
        codigo_sha256=sha256_codigo([str(x) for x in (LAB / "src" / "volc_dil" / "surrogate").glob("*.py")] + [__file__]),
        resultado={k: v for k, v in out.items() if k not in ("manifesto", "segundos")})
    out["segundos"] = round(time.perf_counter() - t0, 1)
    destino = LAB / "results" / "surrogate"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "surrogate_results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    print(json.dumps({"segundos": out["segundos"], "fingerprint": out["manifesto"]["fingerprint"]}))


if __name__ == "__main__":
    main()
