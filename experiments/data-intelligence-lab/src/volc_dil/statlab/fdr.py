"""Controle de multiplicidade: Benjamini-Hochberg (própria + statsmodels), Bonferroni, nenhuma.

Cenário: muitas células (ex.: campanha x página x dia) comparando duas variantes de taxa;
poucas têm diferença verdadeira. Mede FDR realizado, poder, nº de falsos vencedores e FWER,
e o efeito de aplicar BH a cada olhada (peeking).

p-valor ausente NÃO vira 1 nem 0: ``bh_propria`` recusa NaN; ``bh_com_ausentes`` exclui e conta.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy import stats
from statsmodels.stats.multitest import multipletests


def bh_propria(p: Any, q: float) -> np.ndarray:
    """Benjamini-Hochberg step-up em ~10 linhas (para conferir contra statsmodels)."""
    p = np.asarray(p, dtype=float)
    if np.any(~np.isfinite(p)) or np.any((p < 0) | (p > 1)):
        raise ValueError("p-valores devem ser finitos em [0, 1]; ausência deve ser tratada antes")
    m = p.size
    ordem = np.argsort(p, kind="mergesort")
    # tolerância relativa 1e-12: na fronteira exata (p == q k / m) a regra é REJEITAR; sem isso o
    # arredondamento de ponto flutuante decide (statsmodels também diverge nesses empates)
    abaixo = p[ordem] <= q * np.arange(1, m + 1) / m * (1 + 1e-12)
    k = int(np.nonzero(abaixo)[0].max()) + 1 if abaixo.any() else 0
    rejeita = np.zeros(m, dtype=bool)
    rejeita[ordem[:k]] = True
    return rejeita


def na_fronteira(p: Any, q: float, rtol: float = 1e-9) -> np.ndarray:
    """Marca p-valores que coincidem (até rtol) com algum limiar q k / m — onde o resultado do BH
    depende de ponto flutuante e duas implementações corretas podem divergir."""
    p = np.asarray(p, dtype=float)
    lim = q * np.arange(1, p.size + 1) / p.size
    return np.isclose(p[:, None], lim[None, :], rtol=rtol, atol=0).any(axis=1)


def bh_statsmodels(p: Any, q: float) -> np.ndarray:
    return multipletests(np.asarray(p, dtype=float), alpha=q, method="fdr_bh")[0]


def bh_com_ausentes(p: Any, q: float) -> dict[str, Any]:
    """Aplica BH só aos p-valores presentes; ausentes ficam ``None`` (não rejeitados, não testados)."""
    p = np.asarray(p, dtype=float)
    presente = np.isfinite(p)
    rej = np.zeros(p.size, dtype=object)
    rej[:] = None
    if presente.any():
        rej[presente] = bh_propria(p[presente], q)
    return {"rejeita": rej.tolist(), "n_ausentes": int((~presente).sum()), "m_testado": int(presente.sum())}


def p_duas_proporcoes(xa: np.ndarray, na: np.ndarray, xb: np.ndarray, nb: np.ndarray) -> np.ndarray:
    """z-test bicaudal de duas proporções (pooled). NaN quando indefinido (sem dados ou var 0)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        pa, pb = xa / na, xb / nb
        pp = (xa + xb) / (na + nb)
        se = np.sqrt(pp * (1 - pp) * (1 / na + 1 / nb))
        z = (pb - pa) / se
        p = 2 * stats.norm.sf(np.abs(z))
    return np.where(np.isfinite(p), p, np.nan)


def _aplicar(metodo: str, p: np.ndarray, q: float) -> np.ndarray:
    presente = np.isfinite(p)
    rej = np.zeros(p.size, dtype=bool)
    pp = p[presente]
    if metodo == "nenhuma":
        r = pp <= q
    elif metodo == "bonferroni":
        r = pp <= q / max(pp.size, 1)
    elif metodo == "bh":
        r = bh_propria(pp, q)
    else:
        raise ValueError(metodo)
    rej[presente] = r
    return rej


METODOS = ("nenhuma", "bonferroni", "bh")


def replica_celulas(rng: np.random.Generator, m: int, frac_verdadeiras: float, p_base: float,
                    lift: float, n_por_braco: int, q: float, olhadas: tuple[int, ...] | None
                    ) -> dict[str, Any]:
    """Uma réplica. ``olhadas``: tamanhos acumulados por braço em que se olha (peeking).
    Se None, só uma olhada em n_por_braco. Uma célula é 'declarada' na 1ª olhada em que é
    rejeitada (e para); FDR é medido sobre todas as declarações (garantia do BH); 'falso vencedor'
    = célula nula declarada com B > A no momento da declaração."""
    verdadeira = rng.random(m) < frac_verdadeiras
    pb_ = np.where(verdadeira, p_base * (1 + lift), p_base)
    looks = olhadas or (n_por_braco,)
    # incrementos por olhada (dados acumulam)
    xa = np.zeros(m)
    xb = np.zeros(m)
    nprev = 0
    declarado = {k: np.zeros(m, dtype=bool) for k in METODOS}
    positivo_na_declaracao = {k: np.zeros(m, dtype=bool) for k in METODOS}
    for n_ac in looks:
        dn = n_ac - nprev
        xa += rng.binomial(dn, p_base, m)
        xb += rng.binomial(dn, pb_)
        nprev = n_ac
        n_arr = np.full(m, float(n_ac))
        p = p_duas_proporcoes(xa, n_arr, xb, n_arr)
        positivo = xb > xa
        for k in METODOS:
            novo = _aplicar(k, p, q) & ~declarado[k]
            positivo_na_declaracao[k] |= novo & positivo
            declarado[k] |= novo
    out: dict[str, Any] = {"m1": int(verdadeira.sum())}
    for k in METODOS:
        d = declarado[k]
        V = int((d & ~verdadeira).sum())
        S = int((d & verdadeira).sum())
        R = V + S
        out[k] = {"V": V, "S": S, "R": R, "fdp": V / R if R > 0 else 0.0,
                  "poder": S / out["m1"] if out["m1"] > 0 else None,
                  "falsos_vencedores": int((d & ~verdadeira & positivo_na_declaracao[k]).sum())}
    return out


def agregar(reps: list[dict[str, Any]]) -> dict[str, Any]:
    from volc_dil.statlab.base import ic_media, ic_proporcao

    out: dict[str, Any] = {}
    for k in METODOS:
        fdp = np.array([r[k]["fdp"] for r in reps])
        V = np.array([r[k]["V"] for r in reps])
        FV = np.array([r[k]["falsos_vencedores"] for r in reps])
        poder = np.array([np.nan if r[k]["poder"] is None else r[k]["poder"] for r in reps])
        out[k] = {
            "fdr_realizado": ic_media(fdp),
            "poder": ic_media(poder),
            "falsas_descobertas_por_replica": ic_media(V),
            "falsos_vencedores_por_replica": ic_media(FV),
            "fwer": ic_proporcao(int((V > 0).sum()), len(reps)),
            "rejeicoes_por_replica": ic_media([r[k]["R"] for r in reps]),
        }
    return out
