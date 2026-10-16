"""M5 — diagnóstico causal com verdade conhecida em `mudanca_orcamento`.

Verdade: contrafactual pareado (CRN) re-simulando o mesmo mundo com o orçamento base sem mudanças.
H5a: tratados = campanhas cujo orçamento dobrou (log de decisão observável), seleção aleatória do cenário.
H5b: tratados = top 30% por ROAS observado recente (seleção pelo resultado), orçamento dobrado no dia 10.
Rótulo = verdade diária do mundo (o valor maduro observado coincide com ela: conservação testada no simulador).
Pré-registro: PRE-REGISTRO.md (M5). Saída: results/fundacao/modelos/m5_causal.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fundacao_modelos_comum import manifesto, pareado, saida  # noqa: E402

import numpy as np  # noqa: E402

from volc_dil.fundacao import modelos as M  # noqa: E402
from volc_dil.fundacao.simulador import cenario, gerar_mundo  # noqa: E402

DESFECHOS = ("custo", "receita", "lucro")


def _diario(mundo):
    custo = mundo.diario("custo_final_micros") / 1e6
    rec = mundo.diario("receita_micros") / 1e6
    return {"custo": custo, "receita": rec, "lucro": rec - custo}


def _base(mundo, D):
    return np.repeat(np.array([c.orcamento_base_micros for c in mundo.campanhas], dtype=np.int64)[:, None], D, axis=1)


def _estimar(Y, tr, t0, verdade_att, n_boot, seed):
    pre, pos = Y[:, :t0], Y[:, t0:]
    d = M.did_painel(Y, tr, t0, n_boot=n_boot, seed=seed)
    sc = [M.controle_sintetico(Y, int(i), np.nonzero(~tr)[0], t0, com_intercepto=True)["efeito"]
          for i in np.nonzero(tr)[0]]
    est = {"antes_depois": float(pos[tr].mean() - pre[tr].mean()),
           "corte_transversal": float(pos[tr].mean() - pos[~tr].mean()),
           "did": d["efeito"], "controle_sintetico": float(np.mean(sc))}
    diag = {"did_ic95": d["ic95"], "did_ic_cobre_verdade": bool(d["ic95"][0] <= verdade_att <= d["ic95"][1]),
            "tendencias_paralelas_passou": M.tendencias_paralelas(Y, tr, t0, n_boot=n_boot, seed=seed)["passou"],
            "placebo_temporal_passou": M.placebo_temporal(Y, tr, t0, t0 // 2, n_boot=n_boot, seed=seed)["passou"]}
    return est, diag


def um_mundo(seed, C, D, n_boot):
    esp = cenario("mudanca_orcamento").reduzir(n_campanhas=C, n_dias=D)
    obs = gerar_mundo(esp.mundo, seed)
    base = _base(obs, D)
    cf = gerar_mundo(esp.mundo, seed, orcamento_diario_micros=base)
    orc = obs.flags["orcamento_hora_micros"].reshape(C, D, 24)
    d_dobra = int(np.floor(D / 3 + 1e-9))
    d_corta = int(np.floor(2 * D / 3 + 1e-9))
    tr_a = orc[:, d_dobra + 1, 0] > 1.5 * orc[:, d_dobra - 1, 0]  # log de decisão: orçamento dobrou
    dias = [d for d in range(d_corta) if d != d_dobra]              # dia da troca (14h) fica fora
    t0 = d_dobra
    out = {"a": {}, "b": {}}
    yo, yc = _diario(obs), _diario(cf)
    for k in DESFECHOS:
        Y = yo[k][:, dias]
        att = float((yo[k] - yc[k])[np.ix_(tr_a, [d for d in dias if d > d_dobra])].mean())
        est, diag = _estimar(Y, tr_a, t0, att, n_boot, seed)
        out["a"][k] = {"verdade": att, "vies": {m: v - att for m, v in est.items()}, **diag}
    # H5b: seleção pelo resultado (ROAS observado dos 7 dias antes da decisão)
    roas = yo["receita"][:, d_dobra - 7:d_dobra].sum(1) / np.maximum(yo["custo"][:, d_dobra - 7:d_dobra].sum(1), 1e-9)
    tr_b = roas >= np.quantile(roas, 0.7)
    orc_b = base.copy()
    orc_b[tr_b, d_dobra:] *= 2
    wb = gerar_mundo(esp.mundo, seed, orcamento_diario_micros=orc_b)
    cfb = gerar_mundo(esp.mundo, seed, orcamento_diario_micros=base)
    yb, ycb = _diario(wb), _diario(cfb)
    dias_b = list(range(d_corta))
    for k in DESFECHOS:
        Y = yb[k][:, dias_b]
        att = float((yb[k] - ycb[k])[np.ix_(tr_b, list(range(d_dobra, d_corta)))].mean())
        est, diag = _estimar(Y, tr_b, d_dobra, att, n_boot, seed)
        out["b"][k] = {"verdade": att, "vies": {m: v - att for m, v in est.items()}, **diag}
    out["n_tratados_a"], out["n_tratados_b"] = int(tr_a.sum()), int(tr_b.sum())
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true")
    a = ap.parse_args()
    seeds = list(range(20261601, 20261601 + (3 if a.rapido else 20)))
    C, D = 50, 30
    mundos = [um_mundo(s, C, D, 100 if a.rapido else 400) for s in seeds]
    metodos = ("antes_depois", "corte_transversal", "did", "controle_sintetico")
    res = {}
    for parte in ("a", "b"):
        res[parte] = {}
        for k in DESFECHOS:
            bloco = {"verdade_att": M.ic_bootstrap_media([w[parte][k]["verdade"] for w in mundos]),
                     "vies": {m: M.ic_bootstrap_media([w[parte][k]["vies"][m] for w in mundos]) for m in metodos},
                     "abs_vies_antes_depois_menos_did": pareado([abs(w[parte][k]["vies"]["antes_depois"]) for w in mundos],
                                                                [abs(w[parte][k]["vies"]["did"]) for w in mundos]),
                     "frac_did_ic_cobre_verdade": float(np.mean([w[parte][k]["did_ic_cobre_verdade"] for w in mundos])),
                     "frac_tendencias_paralelas_passou": float(np.mean([bool(w[parte][k]["tendencias_paralelas_passou"])
                                                                        for w in mundos])),
                     "frac_placebo_temporal_passou": float(np.mean([w[parte][k]["placebo_temporal_passou"]
                                                                    for w in mundos]))}
            res[parte][k] = bloco
    va = res["a"]
    res["H5a_suportada"] = bool(all(va[k]["vies"]["did"]["ic95"][0] <= 0 <= va[k]["vies"]["did"]["ic95"][1]
                                    for k in ("custo", "lucro"))
                                and all(va[k]["abs_vies_antes_depois_menos_did"]["ic95"][0] > 0 for k in ("custo", "lucro")))
    vb = res["b"]["lucro"]["vies"]
    res["H5b_suportada"] = bool(not (vb["did"]["ic95"][0] <= 0 <= vb["did"]["ic95"][1]))
    res["n_tratados"] = {"a": float(np.mean([w["n_tratados_a"] for w in mundos])),
                         "b": float(np.mean([w["n_tratados_b"] for w in mundos]))}
    obj = {"manifesto": manifesto(__file__, seeds=seeds, parametros={"C": C, "D": D, "selecao_b": "top 30% ROAS 7d",
                                                                     "unidade": "BRL por campanha-dia"}),
           "resultados": res}
    saida("m5_causal.json", obj, rapido=a.rapido)


if __name__ == "__main__":
    main()
