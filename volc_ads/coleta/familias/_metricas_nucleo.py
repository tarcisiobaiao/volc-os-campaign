"""Núcleo de métricas que toda família granular manda à `volc_registrar_gads_fatos`.

As oito colunas de métrica de `google_ads_fato_granular` (v17_01), com o tipo
que a API usa: contagem e micros em int, conversão e valor em float.
"""
from __future__ import annotations

from typing import Any

from ..contrato import medida

# coluna da v17_01 → (campo de `metrics`, tipo)
NUCLEO: dict[str, tuple[str, type]] = {
    "impressoes": ("impressions", int),
    "cliques": ("clicks", int),
    "interacoes": ("interactions", int),
    "custo_micros": ("cost_micros", int),
    "conversoes": ("conversions", float),
    "todas_conversoes": ("all_conversions", float),
    "valor_conversoes": ("conversions_value", float),
    "valor_todas_conversoes": ("all_conversions_value", float),
}

SELECT_NUCLEO = ", ".join(f"metrics.{campo}" for campo, _ in NUCLEO.values())


def metricas_nucleo(row: Any) -> dict:
    return {coluna: medida(row.metrics, campo, tipo) for coluna, (campo, tipo) in NUCLEO.items()}


def id_texto(mensagem: Any, campo: str) -> str | None:
    """ID int64 da API como texto (a v17_01 guarda IDs em `text`); None se ausente ou 0."""
    valor = medida(mensagem, campo)
    return str(valor) if valor else None
