"""Tipos comuns do Model Lab: ``Achado`` (resultado de detector) e reexportações do Stat Lab.

Convenções (iguais às do Stat Lab herdado):
- ausência é ``None``/NaN tratada explicitamente — nunca vira 0;
- quando não há base para um número, devolve ``ResultadoInsuficiente`` (herdado), não um número;
- todo limiar é PARÂMETRO de quem chama; nenhum default aqui é política operacional.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

import numpy as np

from volc_dil.statlab.base import ResultadoInsuficiente, envelope, gravar_json, para_json, versoes

VERSAO_MODELOS = "0.1.0"

TIPOS_ACHADO = ("quebra", "anomalia_valor", "lacuna", "zero_implausivel", "mudanca_maturacao",
                "vazamento", "sem_achado")


@dataclass(frozen=True)
class Achado:
    """Resultado de um detector. ``detectado=False`` é resposta válida (não é ausência de resposta).

    ``indice``: posição na série (0-based) do alarme; ``ponto_estimado``: posição estimada da mudança
    (quando o método estima, ex.: CUSUM/BOCPD), que pode ser anterior ao alarme.
    """

    tipo: str
    detectado: bool
    metodo: str
    indice: Optional[int] = None
    ponto_estimado: Optional[int] = None
    estatistica: Optional[float] = None
    limiar: Optional[float] = None
    detalhes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.tipo not in TIPOS_ACHADO:
            raise ValueError(f"tipo de achado desconhecido: {self.tipo!r}")
        if self.detectado and self.indice is None:
            raise ValueError("achado detectado precisa de índice")

    def como_dict(self) -> dict[str, Any]:
        return {"tipo": self.tipo, "detectado": self.detectado, "metodo": self.metodo, "indice": self.indice,
                "ponto_estimado": self.ponto_estimado, "estatistica": self.estatistica, "limiar": self.limiar,
                "detalhes": dict(self.detalhes)}


def serie_finita(x: Any, *, nome: str = "serie") -> np.ndarray:
    """Converte para float e RECUSA ausência (NaN/inf). Quem tem lacuna trata antes (ver ``anomalia``)."""
    a = np.asarray(x, dtype=float).ravel()
    if a.size == 0:
        raise ValueError(f"{nome} vazia")
    if not np.all(np.isfinite(a)):
        raise ValueError(f"{nome} com ausência/não finito: trate a lacuna antes (ausência não vira 0)")
    return a


def ic_bootstrap_media(x: Any, *, b: int = 2000, seed: int = 0, nivel: float = 0.95) -> dict[str, Any]:
    """Média com IC por bootstrap percentil (unidade = elemento de ``x``, tipicamente seed). NaN excluídos e contados."""
    v = np.asarray(x, dtype=float).ravel()
    ok = v[np.isfinite(v)]
    out: dict[str, Any] = {"estimativa": None, "ic95": [None, None], "n": int(ok.size),
                           "n_excluidos": int(v.size - ok.size)}
    if ok.size == 0:
        return out
    out["estimativa"] = float(ok.mean())
    if ok.size >= 2:
        idx = np.random.default_rng(seed).integers(0, ok.size, size=(b, ok.size))
        m = ok[idx].mean(axis=1)
        q = (1 - nivel) / 2
        out["ic95"] = [float(np.quantile(m, q)), float(np.quantile(m, 1 - q))]
    return out


__all__ = ["Achado", "ResultadoInsuficiente", "TIPOS_ACHADO", "VERSAO_MODELOS", "envelope", "gravar_json",
           "ic_bootstrap_media", "para_json", "serie_finita", "versoes"]
