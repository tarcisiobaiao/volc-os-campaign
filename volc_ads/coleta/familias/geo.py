"""Família `geo`: campanha × dia × local × tipo de local (`geographic_view`).

Duas consultas: país (`geographic_view.country_criterion_id`) e cidade
(`segments.geo_target_city`). As duas cobrem o mesmo tráfego em níveis
diferentes: quem lê agrega dentro de UM `geo_nivel`. A soma das cidades fica
abaixo do país porque o tráfego sem cidade identificada não tem linha de cidade.
"""
from __future__ import annotations

from typing import Any

from ..contrato import Contexto, enum_nome, medida
from ._metricas_nucleo import SELECT_NUCLEO, id_texto, metricas_nucleo

LOCAL_TIPO = {
    "AREA_OF_INTEREST": "area_de_interesse",
    "LOCATION_OF_PRESENCE": "localizacao_fisica",
}


class _Geo:
    nome = "geo"
    rpc = "volc_registrar_gads_fatos"

    def gaql(self, ctx: Contexto) -> list[str]:
        filtro = f"WHERE {ctx.janela_gaql} AND metrics.impressions > 0"
        return [
            "SELECT geographic_view.country_criterion_id, geographic_view.location_type, "
            f"campaign.id, segments.date, {SELECT_NUCLEO} FROM geographic_view {filtro}",
            # Sem country_criterion_id de propósito: é a ausência dele que marca
            # a linha como de cidade no `normalizar`.
            "SELECT segments.geo_target_city, geographic_view.location_type, "
            f"campaign.id, segments.date, {SELECT_NUCLEO} FROM geographic_view {filtro}",
        ]

    def normalizar(self, row: Any, ctx: Contexto) -> dict | None:
        if "geo_target_city" in row.segments:
            geo_constant, geo_nivel = row.segments.geo_target_city, "cidade"
        elif medida(row.geographic_view, "country_criterion_id"):
            geo_constant = f"geoTargetConstants/{row.geographic_view.country_criterion_id}"
            geo_nivel = "pais"
        else:
            return None
        local_tipo = LOCAL_TIPO.get(enum_nome(row.geographic_view.location_type))
        campaign_id = id_texto(row.campaign, "id")
        if (local_tipo is None or campaign_id is None or not row.segments.date
                or not geo_constant.startswith("geoTargetConstants/")):
            return None
        return {
            "campaign_id": campaign_id,
            "metric_date": row.segments.date,
            "geo_constant": geo_constant,
            "geo_nivel": geo_nivel,
            "local_tipo": local_tipo,
            "currency_code": ctx.moeda,
            "colhida_em": ctx.colhida_iso,
            **metricas_nucleo(row),
        }


FAMILIA = _Geo()
