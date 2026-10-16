"""Stat Lab — confidence sequences (PrPl-EB) vs. Wald com peeking, e contraprovas.

Uso (da raiz do repo):
  experiments/data-intelligence-lab/.venv/bin/python experiments/data-intelligence-lab/scripts/statlab_cs.py
Grava results/statlab/confidence_sequences.json.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "src"))

import numpy as np  # noqa: E402

from volc_dil.statlab.base import envelope, gravar_json, ic_media  # noqa: E402
from volc_dil.statlab.sequencias_confianca import (  # noqa: E402
    ForaDoSuporte,
    agregar,
    bernoulli,
    beta,
    cs_prpl_eb,
    resumir,
    rodar_monte_carlo,
    wald_peeking,
)

ALPHA = 0.05
T_MIN = 10
BLOCO = 250


def _concat(lst: list[dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    return {k: np.concatenate([d[k] for d in lst]) for k in lst[0]}


def cobertura(seed: int, n_traj: int, T: int) -> dict:
    out = {}
    for i, (nome, g, mu) in enumerate([
        ("bernoulli_p0.5", bernoulli(0.5), 0.5),
        ("bernoulli_p0.05_cvr_baixa", bernoulli(0.05), 0.05),
        ("beta_media0.3", beta(0.3, 5.0), 0.3),
    ]):
        rng = np.random.default_rng(seed + i)
        r = rodar_monte_carlo(rng, g, n_traj, T, mu, None, ALPHA, T_MIN, (100, 1000, T), BLOCO)
        out[nome] = {"mu": mu, "seed": seed + i, **{m: agregar(v, T) for m, v in r.items()}}
    return out


def decisao(seed: int, n_traj: int, T: int) -> dict:
    out = {}
    mu0 = 0.05
    for i, (nome, p) in enumerate([("nulo_p_igual_mu0", 0.05), ("alternativa_p0.06_vs_mu0_0.05", 0.06),
                                   ("alternativa_p0.075_vs_mu0_0.05", 0.075)]):
        rng = np.random.default_rng(seed + 10 + i)
        r = rodar_monte_carlo(rng, bernoulli(p), n_traj, T, p, mu0, ALPHA, T_MIN, (T,), BLOCO)
        out[nome] = {"p": p, "mu0": mu0, "seed": seed + 10 + i, **{m: agregar(v, T) for m, v in r.items()}}
    return out


def cauda_pesada(seed: int, n_traj: int, T: int, n_piloto: int) -> dict:
    """Receita/visitante ilimitada. 'Limite' B = máximo de um piloto de n_piloto observações
    (palpite realista e ERRADO: a cauda não tem limite). X/B é recortado em [0, 1] porque a CS
    recusa entrada > 1. A CS cobre E[min(X,B)]/B, não E[X]/B."""
    out = {}
    cenarios = {
        "lognormal_sigma1.5": (lambda rng, f: (rng.random(f) < 0.05) * rng.lognormal(np.log(40), 1.5, f),
                               0.05 * 40 * np.exp(1.5**2 / 2)),
        "pareto_alpha1.5_var_infinita": (lambda rng, f: (rng.random(f) < 0.05) * 40 * (1 + rng.pareto(1.5, f)),
                                         0.05 * 40 * 1.5 / 0.5),
    }
    for i, (nome, (g, mu)) in enumerate(cenarios.items()):
        rng = np.random.default_rng(seed + 20 + i)
        cs_l, w_raw, frac_acima = [], [], []
        erro_sem_recorte = None
        feitos = 0
        while feitos < n_traj:
            b = min(BLOCO, n_traj - feitos)
            piloto = g(rng, (b, n_piloto))
            B = piloto.max(axis=1)
            B = np.where(B > 0, B, np.nan)
            x = g(rng, (b, T))
            xn = x / B[:, None]
            if erro_sem_recorte is None:
                try:
                    cs_prpl_eb(xn[:1], ALPHA)
                    erro_sem_recorte = "nenhum (todas as observações <= B nesta trajetória)"
                except ForaDoSuporte as e:
                    erro_sem_recorte = f"ForaDoSuporte: {str(e)[:120]}"
            frac_acima.append(np.nanmean(xn > 1, axis=1))
            ok = np.isfinite(B)
            lo, hi = cs_prpl_eb(np.minimum(xn[ok], 1.0), ALPHA)
            cs_l.append(resumir(lo, hi, mu / B[ok], None, T_MIN, (T,)))
            lo, hi = wald_peeking(x, ALPHA)
            w_raw.append(resumir(lo, hi, mu, None, T_MIN, (T,)))
            feitos += b
        cs_r, w_r = _concat(cs_l), _concat(w_raw)
        out[nome] = {
            "mu_verdadeira": mu, "seed": seed + 20 + i, "n_piloto_para_limite": n_piloto,
            "entrada_sem_recorte": erro_sem_recorte,
            "frac_observacoes_acima_do_limite": ic_media(np.concatenate(frac_acima)),
            "cs_prpl_eb_recortada_em_B": {k: v for k, v in agregar(cs_r, T).items() if not k.startswith("largura")},
            "wald_peeking_bruto": {k: v for k, v in agregar(w_r, T).items() if not k.startswith("largura")},
        }
    return out


def atraso(seed: int, n_traj: int, T: int, media_atraso: float, janela: int, lag_ingenuo: int) -> dict:
    """Conversão com atraso D ~ Geom(1/media). Estimando de negócio: p_W = P(converter com D <= W).
    - oráculo: vê o desfecho final no instante da chegada (impossível; referência);
    - janela_fechada: alimenta a unidade só quando a janela W fecha (válido, atrasa W passos);
    - lag_ingenuo: alimenta após L passos tratando 'ainda não converteu' como 0 (ausência -> 0)."""
    out = {}
    pD_W = 1 - (1 - 1 / media_atraso) ** janela
    pD_L = 1 - (1 - 1 / media_atraso) ** lag_ingenuo
    for i, p in enumerate((0.05, 0.075)):
        mu0 = 0.05 * pD_W
        p_W = p * pD_W
        rng = np.random.default_rng(seed + 30 + i)
        acum = {"oraculo": [], "janela_fechada": [], "lag_ingenuo": []}
        feitos = 0
        while feitos < n_traj:
            b = min(BLOCO, n_traj - feitos)
            conv = rng.random((b, T)) < p
            D = rng.geometric(1 / media_atraso, (b, T))
            final = (conv & (D <= janela)).astype(float)
            ingenuo = (conv & (D <= lag_ingenuo)).astype(float)
            lo, hi = cs_prpl_eb(final, ALPHA)
            r = resumir(lo, hi, p_W, mu0, T_MIN, (T,))
            acum["oraculo"].append(r)
            acum["janela_fechada"].append(r)  # mesma sequência, deslocada W no calendário
            lo, hi = cs_prpl_eb(ingenuo, ALPHA)
            acum["lag_ingenuo"].append(resumir(lo, hi, p_W, mu0, T_MIN, (T,)))
            feitos += b
        desloc = {"oraculo": 0, "janela_fechada": janela, "lag_ingenuo": lag_ingenuo}
        out[f"p{p}"] = {
            "p": p, "p_W_verdadeira": p_W, "mu0": mu0, "estimando_do_lag_ingenuo": p * pD_L,
            "seed": seed + 30 + i,
            **{m: {k: v for k, v in agregar(_concat(l), T, desloc[m]).items() if not k.startswith("largura")}
               for m, l in acum.items()},
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261015)
    ap.add_argument("--n-traj", type=int, default=1000)
    ap.add_argument("--T", type=int, default=10000)
    ap.add_argument("--saida", default=str(LAB / "results" / "statlab" / "confidence_sequences.json"))
    args = ap.parse_args()
    s, n, T = args.seed, args.n_traj, args.T
    resultados = {
        "cobertura_uniforme": cobertura(s, n, T),
        "decisao_mu_maior_que_mu0": decisao(s, n, T),
        "contraprova_cauda_pesada": cauda_pesada(s, n, T, n_piloto=500),
        "contraprova_atraso": atraso(s, n, T, media_atraso=200.0, janela=1000, lag_ingenuo=50),
    }
    parametros = {
        "alpha": ALPHA, "t_min_para_contar_violacao": T_MIN, "T": T, "n_trajetorias": n,
        "metodo_cs": "PrPl-EB, Waudby-Smith & Ramdas (2024) JRSS-B 86(1), seção 3; c = 1/2; running intersection",
        "comparador": "Wald/t de horizonte fixo recalculado a cada passo (peeking)",
        "decisao": "decide 'mu > mu0' no 1º t com limite inferior > mu0 (intervalo bicaudal)",
        "nota": "p, mu0, atrasos, janela e lag são parâmetros de cenário, não defaults operacionais",
    }
    env = envelope("confidence_sequences", s, n, parametros, resultados)
    nbytes = gravar_json(args.saida, env)
    print(f"gravado {args.saida} ({nbytes} bytes)")


if __name__ == "__main__":
    main()
