"""Família `placement`: campanha × dia × placement × view.

Três consultas, uma por view; `placement_view` diz qual:
- `detail` → `detail_placement_view` (URL, vídeo, app: o grão mais fino);
- `group`  → `group_placement_view` (domínio, canal, app inteiro);
- `pmax`   → `performance_max_placement_view` (só impressões: medido com
  validate_only em 08/10/2026, clicks/custo/conversões dão
  PROHIBITED_METRIC_IN_SELECT_OR_WHERE_CLAUSE nessa view).

As views cobrem o mesmo tráfego em recortes diferentes: quem lê agrega dentro
de UM `placement_view`.

`placement` vem de `<view>.placement`, não de `target_url`. É a identidade da
linha (vai em base64 no resource_name) e vem sempre; `target_url` é a URL de
navegação (para vídeo, o link do YouTube; para app, o da loja), pode faltar e
muda de forma sem mudar o placement. Para site os dois dão o mesmo domínio em
`volc_dominio()`. `target_url` só entra quando `placement` vem vazio, porque a
CHECK exige placement não vazio.
"""
from __future__ import annotations

from typing import Any

from ..contrato import Contexto, enum_nome
from ._consolidacao import consolidar
from ._metricas_nucleo import SELECT_NUCLEO, id_texto, metricas_nucleo

VIEWS = {
    "detail_placement_view": "detail",
    "group_placement_view": "group",
    "performance_max_placement_view": "pmax",
}


def _select(view: str, metricas: str, ctx: Contexto) -> str:
    return (
        f"SELECT campaign.id, segments.date, {view}.placement, {view}.target_url, "
        f"{view}.placement_type, {view}.display_name, {metricas} "
        f"FROM {view} WHERE {ctx.janela_gaql} AND metrics.impressions > 0"
    )


class _Placement:
    nome = "placement"
    rpc = "volc_registrar_gads_fatos"

    def gaql(self, ctx: Contexto) -> list[str]:
        return [
            _select("detail_placement_view", SELECT_NUCLEO, ctx),
            _select("group_placement_view", SELECT_NUCLEO, ctx),
            _select("performance_max_placement_view", "metrics.impressions", ctx),
        ]

    def normalizar(self, row: Any, ctx: Contexto) -> dict | None:
        view = next((v for v in VIEWS if v in row), None)
        if view is None:
            return None
        dados = getattr(row, view)
        placement = (dados.placement or dados.target_url).strip()
        campaign_id = id_texto(row.campaign, "id")
        if not placement or campaign_id is None or not row.segments.date:
            return None
        return {
            "campaign_id": campaign_id,
            "metric_date": row.segments.date,
            "placement": placement,
            "placement_view": VIEWS[view],
            "placement_tipo": enum_nome(dados.placement_type) if "placement_type" in dados else None,
            "placement_nome": dados.display_name or None,
            "currency_code": ctx.moeda,
            "colhida_em": ctx.colhida_iso,
            **metricas_nucleo(row),
        }

    # detail e group vêm uma linha por grupo de anúncios; a família não tem grupo.
    consolidar = staticmethod(consolidar)


FAMILIA = _Placement()
