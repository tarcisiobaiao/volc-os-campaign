"""Modelos tabulares com features ``as_of`` e validação rolling-origin, com checagem de vazamento.

Problema: no corte do dia ``o`` (origem), prever o lucro FINAL (receita − custo, maduro) da campanha
no dia ``o + horizonte``. Features só de painéis ``as_of`` do próprio corte ``o`` (valores preliminares
entram como estão, com o indicador de maturidade); rótulos de TREINO só entram se já estavam
MADUROS no corte em que o modelo é treinado (rótulo imaturo é vazamento de outra espécie).

Duas defesas contra vazamento (as duas testadas com feature do futuro injetada):
1. ``checar_vazamento``: toda feature carrega ``disponivel_em``; se for posterior à origem → achado.
2. ``vazamento_empirico``: ganho relativo de MAE fora do tempo ao acrescentar uma feature acima de um
   limiar implausível → achado "suspeita" (heurística; não substitui a 1).

Modelos: ``Ridge`` (escalonado, alpha por CV em grade) e ``HistGradientBoostingRegressor``, contra
baselines ``ultimo_maduro`` e ``media_maduros``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

import numpy as np

from .base import Achado

FINAL = 2  # índice de "final" em dados.MATURIDADES


@dataclass(frozen=True)
class FeatureMeta:
    nome: str
    disponivel_em: int  # epoch s (ou índice de corte) em que o valor passou a ser conhecido


def checar_vazamento(metas: Sequence[FeatureMeta], origem: int) -> list[Achado]:
    """Achado ``vazamento`` para cada feature com ``disponivel_em > origem`` (mesma unidade de tempo)."""
    return [Achado("vazamento", True, "disponibilidade", indice=i, estatistica=float(m.disponivel_em - origem),
                   limiar=0.0, detalhes={"feature": m.nome, "disponivel_em": m.disponivel_em, "origem": origem})
            for i, m in enumerate(metas) if m.disponivel_em > origem]


def _lags(P: np.ndarray, o: int, n_lags: int) -> np.ndarray:
    """(E, n_lags) valores dos dias o-1..o-n_lags no painel P (do corte o). NaN fora do intervalo."""
    E, D = P.shape
    out = np.full((E, n_lags), np.nan)
    for j in range(1, n_lags + 1):
        if 0 <= o - j < D:
            out[:, j - 1] = P[:, o - j]
    return out


def features_no_corte(custo: np.ndarray, receita: np.ndarray, mat_custo: np.ndarray, mat_receita: np.ndarray,
                      o: int, *, n_lags: int, n_media: int, dia_semana_alvo: int) -> tuple[np.ndarray, list[str]]:
    """Features por campanha no corte ``o`` a partir dos painéis DAQUELE corte (E, D).
    NaN viram ``nan`` mesmo (HGB lida; Ridge recebe imputação + indicador no chamador)."""
    lucro = receita - custo
    L = _lags(lucro, o, n_lags)
    madura = (mat_custo == FINAL) & (mat_receita == FINAL)
    Lm = np.where(_lags(madura.astype(float), o, n_lags) > 0, L, np.nan)
    with np.errstate(invalid="ignore"):
        ult_maduro = np.array([row[np.isfinite(row)][0] if np.isfinite(row).any() else np.nan for row in Lm])
        media = np.array([np.nanmean(row[np.isfinite(row)][:n_media]) if np.isfinite(row).any() else np.nan
                          for row in Lm])
    frac_maduro = np.isfinite(Lm).mean(axis=1)
    custo1 = _lags(custo, o, 1)[:, 0]
    rec1 = _lags(receita, o, 1)[:, 0]
    dow = np.zeros((custo.shape[0], 7))
    dow[:, dia_semana_alvo] = 1.0
    X = np.column_stack([L, ult_maduro, media, frac_maduro, custo1, rec1, dow])
    nomes = ([f"lucro_lag{j}" for j in range(1, n_lags + 1)] + ["ultimo_maduro", "media_maduros", "frac_maduro",
             "custo_lag1", "receita_lag1"] + [f"dow_{k}" for k in range(7)])
    return X, nomes


def imputar(X: np.ndarray, medias: Optional[np.ndarray] = None) -> tuple[np.ndarray, np.ndarray]:
    """Imputação por média de TREINO + indicadores de ausência (para Ridge). Devolve (X', medias)."""
    falta = ~np.isfinite(X)
    if medias is None:
        with np.errstate(invalid="ignore"):
            medias = np.nanmean(np.where(falta, np.nan, X), axis=0)
        medias = np.where(np.isfinite(medias), medias, 0.0)
    Xi = np.where(falta, medias[None, :], X)
    return np.column_stack([Xi, falta.astype(float)]), medias


class ModeloAjustado:
    """Modelo já treinado (para reusar entre origens até o próximo retreino)."""

    def __init__(self, nome: str, modelo: Any, medias: Optional[np.ndarray]) -> None:
        self.nome, self._m, self._medias = nome, modelo, medias

    def prever(self, X: np.ndarray) -> np.ndarray:
        if self._medias is not None:
            X, _ = imputar(X, self._medias)
        return self._m.predict(X)


def ajustar(modelo: str, Xtr: np.ndarray, ytr: np.ndarray, *, seed: int = 0) -> ModeloAjustado:
    if modelo == "ridge":
        from sklearn.linear_model import RidgeCV
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        A, med = imputar(Xtr)
        m = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 4, 13)))
        m.fit(A, ytr)
        return ModeloAjustado(modelo, m, med)
    if modelo == "hgb":
        from sklearn.ensemble import HistGradientBoostingRegressor

        m = HistGradientBoostingRegressor(max_iter=150, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=20,
                                          l2_regularization=1.0, random_state=seed)
        m.fit(Xtr, ytr)
        return ModeloAjustado(modelo, m, None)
    raise ValueError(f"modelo desconhecido: {modelo}")


def ajustar_e_prever(modelo: str, Xtr: np.ndarray, ytr: np.ndarray, Xte: np.ndarray, *, seed: int = 0) -> np.ndarray:
    return ajustar(modelo, Xtr, ytr, seed=seed).prever(Xte)


def vazamento_empirico(mae_sem: float, mae_com: float, *, ganho_implausivel: float, nome: str) -> Achado:
    """Suspeita de vazamento quando a feature reduz o MAE fora do tempo em mais que ``ganho_implausivel``
    (fração). Heurística calibrada pelo chamador; um ganho grande e legítimo também dispara."""
    ganho = (mae_sem - mae_com) / mae_sem if mae_sem > 0 else 0.0
    det = ganho > ganho_implausivel
    return Achado("vazamento" if det else "sem_achado", det, "ganho_implausivel", indice=0 if det else None,
                  estatistica=float(ganho), limiar=ganho_implausivel, detalhes={"feature": nome})


__all__ = ["FINAL", "FeatureMeta", "ModeloAjustado", "ajustar", "ajustar_e_prever", "checar_vazamento", "features_no_corte", "imputar",
           "vazamento_empirico"]
