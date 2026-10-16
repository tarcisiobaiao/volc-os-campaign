"""M4 — testes sequenciais e FDR: e-BH × BH (uma olhada e peeking) e CS herdada em outcome limitado
(taxa de sessões que chegam ao destino) × receita por sessão (ilimitada).

Pré-registro: PRE-REGISTRO.md (M4). Saída: results/fundacao/modelos/m4_sequencial.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fundacao_modelos_comum import manifesto, saida  # noqa: E402

import numpy as np  # noqa: E402

from volc_dil.fundacao import modelos as M  # noqa: E402
from volc_dil.fundacao.simulador import simular  # noqa: E402
from volc_dil.statlab.base import ic_proporcao  # noqa: E402

Q = 0.1
ALPHA = 0.05


def taxa_destino_simulador(seed):
    m = simular("estavel", seed, n_campanhas=30, n_dias=14).mundo
    s, d = m.diario("sessoes") - m.diario("sessoes_bot"), m.diario("destino")
    tot_s, tot_d = s.sum(axis=1), d.sum(axis=1)
    ok = tot_s > 0
    return float(np.median(tot_d[ok] / tot_s[ok]))


def parte_fdr(mu0, n_rep, m, n_alt, n, lift, seed):
    rng = np.random.default_rng(seed)
    regimes = {"uma_olhada": [n], "olhadas_10": list(np.linspace(n / 10, n, 10).astype(int)),
               "olhadas_50": list(np.linspace(n / 50, n, 50).astype(int))}
    acc = {r: {"bh": {"fdp": [], "poder": []}, "ebh": {"fdp": [], "poder": []}} for r in regimes}
    for _ in range(n_rep):
        alt = np.zeros(m, bool)
        alt[:n_alt] = True
        mu = np.where(alt, mu0 * lift, mu0)
        x = (rng.random((m, n)) < mu[:, None]).astype(float)
        K = M.eprocesso_media_limitada(x, mu0)
        cs = np.cumsum(x, axis=1)
        for r, olhadas in regimes.items():
            rej_bh = np.zeros(m, bool)
            rej_e = np.zeros(m, bool)
            for t in olhadas:
                rej_bh |= M.bh(M.p_binomial_unilateral(cs[:, t - 1], np.full(m, t), mu0), Q)
                rej_e |= M.e_bh(K[:, t - 1], Q)
            for nome, rej in (("bh", rej_bh), ("ebh", rej_e)):
                acc[r][nome]["fdp"].append((rej & ~alt).sum() / max(rej.sum(), 1))
                acc[r][nome]["poder"].append((rej & alt).sum() / n_alt)
    out = {}
    for r in regimes:
        out[r] = {}
        for nome in ("bh", "ebh"):
            f = np.asarray(acc[r][nome]["fdp"])
            out[r][nome] = {"fdr": float(f.mean()), "ep_mc": float(f.std(ddof=1) / np.sqrt(f.size)),
                            "poder": float(np.mean(acc[r][nome]["poder"]))}
    out["H4a_ebh_controla"] = bool(all(out[r]["ebh"]["fdr"] <= Q + 2 * out[r]["ebh"]["ep_mc"] for r in regimes))
    out["bh_infla_com_peeking"] = bool(out["olhadas_50"]["bh"]["fdr"] > Q)
    return out


def _sessoes(mundo, c, rng):
    """Fluxo de sessões humanas de uma campanha (0/1 chegou ao destino; receita da hora rateada por
    sessão) em ordem aleatória (permutação = amostragem de população finita, média verdadeira conhecida)."""
    s = (mundo.horario("sessoes") - mundo.horario("sessoes_bot"))[c].sum(axis=1)
    d = mundo.horario("destino")[c].sum(axis=1)
    rec = mundo.horario("receita_micros")[c].sum(axis=1) / 1e6
    dest, val = [], []
    for t in np.nonzero(s > 0)[0]:
        dest += [1.0] * int(min(d[t], s[t])) + [0.0] * int(s[t] - min(d[t], s[t]))
        val += [rec[t] / s[t]] * int(s[t])
    dest, val = np.asarray(dest), np.asarray(val)
    p = rng.permutation(dest.size)
    return dest[p], val[p]


def parte_cs(seed, n_camp, n_traj, T, janela_limite):
    sim = simular("outlier_bot", seed, n_campanhas=n_camp, n_dias=14)
    rng = np.random.default_rng(seed)
    erro_dest, recusa, erro_clip, n_traj_tot = 0, 0, 0, 0
    for c in range(n_camp):
        for _ in range(n_traj):
            dest, val = _sessoes(sim.mundo, c, rng)
            if dest.size < T:
                break
            n_traj_tot += 1
            mu = dest.mean()
            lo, hi = M.cs_prpl_eb(dest[:T], ALPHA)
            erro_dest += bool(np.any((lo > mu) | (hi < mu)))
            limite = float(val[:janela_limite].max())  # "limite" estimado numa janela inicial
            try:
                M.normalizar_por_limite(val[:T], limite)
            except M.ForaDoSuporte:
                recusa += 1
            clip = np.minimum(val[:T], limite) / limite
            mu_v = val.mean() / limite  # média verdadeira da receita normalizada (sem recorte)
            lo2, hi2 = M.cs_prpl_eb(clip, ALPHA)
            erro_clip += bool(np.any((lo2[janela_limite:] > mu_v) | (hi2[janela_limite:] < mu_v)))
    return {"n_trajetorias": n_traj_tot, "T": T, "alpha": ALPHA,
            "taxa_destino_erro_uniforme": ic_proporcao(erro_dest, n_traj_tot),
            "receita_limite_violado_recusa": ic_proporcao(recusa, n_traj_tot),
            "receita_recortada_erro_uniforme": ic_proporcao(erro_clip, n_traj_tot)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true")
    a = ap.parse_args()
    seed = 20261501
    mu0 = taxa_destino_simulador(seed)
    fdr = parte_fdr(mu0, 40 if a.rapido else 400, m=50, n_alt=10, n=2000, lift=1.25, seed=seed + 1)
    cs = parte_cs(seed + 2, 4 if a.rapido else 12, 5 if a.rapido else 25, T=1500, janela_limite=200)
    res = {"mu0_taxa_destino_derivada_do_simulador": mu0, "fdr": fdr, "cs": cs,
           "H4b_suportada": bool(cs["taxa_destino_erro_uniforme"]["ic95"][0] <= ALPHA
                                  and (cs["receita_limite_violado_recusa"]["estimativa"] > 0.5
                                       or cs["receita_recortada_erro_uniforme"]["estimativa"] > ALPHA))}
    obj = {"manifesto": manifesto(__file__, seeds=[seed, seed + 1, seed + 2],
                                  parametros={"q": Q, "alpha": ALPHA, "m": 50, "n_alt": 10, "n": 2000, "lift": 1.25,
                                              "T_cs": 1500, "janela_limite": 200}), "resultados": res}
    saida("m4_sequencial.json", obj, rapido=a.rapido)


if __name__ == "__main__":
    main()
