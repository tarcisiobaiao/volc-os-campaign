"""Detecção online de mudança de regime numa série (ex.: log RPM diário maduro de uma campanha).

Três detectores, todos ONLINE (a decisão em t usa só x[0..t]) e padronizados pela MESMA janela de
referência (os ``n_ref`` primeiros pontos, mediana e MAD — robusto a outlier):

- ``media_movel`` (baseline): alarme quando |média dos últimos ``janela`` − média_ref| / escala_ref > limiar;
- ``cusum``: CUSUM bilateral (Page 1954) com folga ``k`` e limiar ``h`` em desvios robustos;
- ``bocpd``: Bayesian online changepoint detection mínima (Adams & MacKay 2007) com prior
  Normal-Gama (média e variância desconhecidas), hazard constante e preditiva t de Student;
  alarme quando P(run length < ``w``) > limiar.

Os limiares NÃO têm default operacional: calibre-os para uma taxa de alarme falso alvo em dados
sem mudança (``calibrar_limiar``) — comparar detectores com limiares diferentes de FA é inválido.
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np
from scipy import special

from .base import Achado, serie_finita

METODOS_QUEBRA = ("media_movel", "cusum", "bocpd")


def _referencia(x: np.ndarray, n_ref: int) -> tuple[float, float]:
    if n_ref < 3 or x.size <= n_ref:
        raise ValueError("n_ref >= 3 e série maior que a referência")
    r = x[:n_ref]
    med = float(np.median(r))
    mad = float(np.median(np.abs(r - med))) * 1.4826
    sd = float(np.std(r, ddof=1))
    escala = mad if mad > 0 else sd
    if not escala > 0:
        escala = max(abs(med), 1.0) * 1e-6
    return med, escala


def media_movel(serie: Any, *, n_ref: int, janela: int, limiar: float) -> Achado:
    x = serie_finita(serie)
    med, esc = _referencia(x, n_ref)
    for t in range(n_ref + janela - 1, x.size):
        if t - janela + 1 < n_ref:
            continue
        est = abs(float(x[t - janela + 1:t + 1].mean()) - med) / esc
        if est > limiar:
            return Achado("quebra", True, "media_movel", indice=t, ponto_estimado=t - janela + 1, estatistica=est,
                          limiar=limiar, detalhes={"n_ref": n_ref, "janela": janela})
    return Achado("sem_achado", False, "media_movel", limiar=limiar, detalhes={"n_ref": n_ref, "janela": janela})


def cusum(serie: Any, *, n_ref: int, k: float, h: float) -> Achado:
    x = serie_finita(serie)
    med, esc = _referencia(x, n_ref)
    sp = sn = 0.0
    ip = ineg = None
    for t in range(n_ref, x.size):
        z = (x[t] - med) / esc
        np_, nn_ = max(0.0, sp + z - k), max(0.0, sn - z - k)
        ip = (t if sp == 0.0 else ip) if np_ > 0 else None
        ineg = (t if sn == 0.0 else ineg) if nn_ > 0 else None
        sp, sn = np_, nn_
        if sp > h or sn > h:
            subida = sp > h
            return Achado("quebra", True, "cusum", indice=t, ponto_estimado=ip if subida else ineg,
                          estatistica=float(max(sp, sn)), limiar=h,
                          detalhes={"direcao": "subida" if subida else "queda", "k": k, "n_ref": n_ref})
    return Achado("sem_achado", False, "cusum", estatistica=float(max(sp, sn)), limiar=h, detalhes={"k": k, "n_ref": n_ref})


def bocpd_posterior(z: np.ndarray, *, hazard: float, mu0: float = 0.0, kappa0: float = 1.0, alpha0: float = 1.0,
                    beta0: float = 1.0, r_max: int = 500) -> np.ndarray:
    """Matriz R[t, r] = P(run length = r | z[0..t]) (Adams & MacKay 2007), prior Normal-Gama.
    ``z`` já padronizado. Trunca run length em ``r_max`` (massa acumulada no último estado)."""
    if not 0 < hazard < 1:
        raise ValueError("hazard em (0, 1)")
    T = z.size
    R = np.zeros((T, min(T + 1, r_max + 1)))
    mu = np.array([mu0]); ka = np.array([kappa0]); al = np.array([alpha0]); be = np.array([beta0])
    p_r = np.array([1.0])
    for t in range(T):
        x = z[t]
        # preditiva t de Student para cada run length
        nu = 2 * al
        escala2 = be * (ka + 1) / (al * ka)
        logp = (special.gammaln((nu + 1) / 2) - special.gammaln(nu / 2) - 0.5 * np.log(np.pi * nu * escala2)
                - (nu + 1) / 2 * np.log1p((x - mu) ** 2 / (nu * escala2)))
        pred = np.exp(logp)
        cresce = p_r * pred * (1 - hazard)
        muda = float((p_r * pred * hazard).sum())
        novo = np.concatenate([[muda], cresce])
        tot = novo.sum()
        novo = novo / tot if tot > 0 else np.r_[1.0, np.zeros(novo.size - 1)]
        # atualização dos parâmetros (run length r+1 herda de r; r = 0 volta ao prior)
        mu_n = (ka * mu + x) / (ka + 1)
        ka_n = ka + 1
        al_n = al + 0.5
        be_n = be + ka * (x - mu) ** 2 / (2 * (ka + 1))
        mu = np.r_[mu0, mu_n]; ka = np.r_[kappa0, ka_n]; al = np.r_[alpha0, al_n]; be = np.r_[beta0, be_n]
        if novo.size > r_max + 1:
            novo[r_max] += novo[r_max + 1:].sum()
            novo = novo[:r_max + 1]
            mu, ka, al, be = mu[:r_max + 1], ka[:r_max + 1], al[:r_max + 1], be[:r_max + 1]
        p_r = novo
        R[t, :p_r.size] = p_r
    return R


def bocpd(serie: Any, *, n_ref: int, hazard: float, w: int, limiar: float, r_max: int = 500) -> Achado:
    x = serie_finita(serie)
    med, esc = _referencia(x, n_ref)
    if not 1 <= w < n_ref:
        raise ValueError("1 <= w < n_ref (a janela de mudança recente precisa caber depois da referência)")
    z = (x - med) / esc
    R = bocpd_posterior(z, hazard=hazard, r_max=r_max)
    for t in range(n_ref, x.size):
        p = float(R[t, :w].sum())
        if p > limiar:
            r_map = int(np.argmax(R[t]))
            return Achado("quebra", True, "bocpd", indice=t, ponto_estimado=t - r_map, estatistica=p, limiar=limiar,
                          detalhes={"hazard": hazard, "w": w, "n_ref": n_ref})
    return Achado("sem_achado", False, "bocpd", limiar=limiar, detalhes={"hazard": hazard, "w": w, "n_ref": n_ref})


_DETECTORES: dict[str, Callable[..., Achado]] = {"media_movel": media_movel, "cusum": cusum, "bocpd": bocpd}
_PARAM_LIMIAR = {"media_movel": "limiar", "cusum": "h", "bocpd": "limiar"}


def detectar_quebra(serie: Any, *, metodo: str, **params: Any) -> Achado:
    """API única para o shadow: ``detectar_quebra(serie, metodo="cusum", n_ref=10, k=0.5, h=5.0)``."""
    if metodo not in _DETECTORES:
        raise ValueError(f"método desconhecido: {metodo}; conhecidos: {METODOS_QUEBRA}")
    return _DETECTORES[metodo](serie, **params)


def calibrar_limiar(series_sem_mudanca: list[np.ndarray], *, metodo: str, alvo_fa_por_unidade_tempo: float,
                    unidade_tempo: float, grade: np.ndarray, **params: Any) -> dict[str, Any]:
    """Menor limiar da ``grade`` cuja taxa de alarme falso (alarmes / unidades de tempo monitoradas,
    parando no 1º alarme) fica ≤ alvo nas séries SEM mudança. Devolve também a curva medida."""
    nome = _PARAM_LIMIAR[metodo]
    n_ref = params["n_ref"]
    curva = []
    escolhido = None
    for lim in sorted(np.asarray(grade, dtype=float)):
        alarmes, tempo = 0, 0.0
        for s in series_sem_mudanca:
            a = detectar_quebra(s, metodo=metodo, **{**params, nome: float(lim)})
            fim = a.indice if a.detectado else len(s) - 1
            tempo += (fim - n_ref + 1) / unidade_tempo
            alarmes += int(a.detectado)
        taxa = alarmes / tempo if tempo > 0 else float("nan")
        curva.append({"limiar": float(lim), "taxa_fa": taxa, "alarmes": alarmes, "tempo": tempo})
        if escolhido is None and taxa <= alvo_fa_por_unidade_tempo:
            escolhido = float(lim)
    return {"metodo": metodo, "parametro": nome, "limiar": escolhido, "curva": curva,
            "alvo": alvo_fa_por_unidade_tempo}


__all__ = ["METODOS_QUEBRA", "bocpd", "bocpd_posterior", "calibrar_limiar", "cusum", "detectar_quebra", "media_movel"]
