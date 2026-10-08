"""Família `asset`: campanha × dia × contexto × asset × campo (+ rótulo).

Duas consultas, uma por contexto:
- `ad_group` → `ad_group_ad_asset_view` (RSA e afins). A view é por ANÚNCIO e
  o contexto guarda o grupo: o mesmo título em dois anúncios do grupo é uma
  identidade só, somada em `consolidar`. O rótulo de desempenho é por anúncio;
  quando os anúncios discordam, a soma fica sem rótulo.
- `asset_group` → `asset_group_asset` (PMax). Validado com as oito métricas e
  `segments.date` em 08/10/2026. É o grão do PMax; `campaign_aggregate_asset_view`
  é por campanha e soma TODOS os canais, então repetiria o Search que a primeira
  consulta já traz. `channel_aggregate_asset_view` recusa métricas com `asset.id`.
  `asset_group_asset` não tem rótulo de desempenho no catálogo da v25.
"""
from __future__ import annotations

from typing import Any

from ..contrato import Contexto, enum_nome
from ._consolidacao import consolidar
from ._metricas_nucleo import SELECT_NUCLEO, id_texto, metricas_nucleo


def _enum(mensagem: Any, campo: str) -> str | None:
    return enum_nome(getattr(mensagem, campo)) if campo in mensagem else None


class _Asset:
    nome = "asset"
    rpc = "volc_registrar_gads_fatos"

    def gaql(self, ctx: Contexto) -> list[str]:
        filtro = f"WHERE {ctx.janela_gaql} AND metrics.impressions > 0"
        return [
            "SELECT campaign.id, ad_group.id, asset.id, ad_group_ad_asset_view.field_type, "
            f"ad_group_ad_asset_view.performance_label, segments.date, {SELECT_NUCLEO} "
            f"FROM ad_group_ad_asset_view {filtro}",
            "SELECT campaign.id, asset_group.id, asset.id, asset_group_asset.field_type, "
            f"segments.date, {SELECT_NUCLEO} FROM asset_group_asset {filtro}",
        ]

    def normalizar(self, row: Any, ctx: Contexto) -> dict | None:
        if "ad_group_ad_asset_view" in row:
            contexto, contexto_id = "ad_group", id_texto(row.ad_group, "id")
            campo = _enum(row.ad_group_ad_asset_view, "field_type")
            rotulo = _enum(row.ad_group_ad_asset_view, "performance_label")
        elif "asset_group_asset" in row:
            contexto, contexto_id = "asset_group", id_texto(row.asset_group, "id")
            campo, rotulo = _enum(row.asset_group_asset, "field_type"), None
        else:
            return None
        campaign_id = id_texto(row.campaign, "id")
        asset_id = id_texto(row.asset, "id")
        if None in (campaign_id, asset_id, contexto_id, campo) or not row.segments.date:
            return None
        return {
            "campaign_id": campaign_id,
            "metric_date": row.segments.date,
            "asset_id": asset_id,
            "asset_campo": campo,
            "asset_contexto": contexto,
            "asset_contexto_id": contexto_id,
            "asset_rotulo": rotulo,
            "currency_code": ctx.moeda,
            "colhida_em": ctx.colhida_iso,
            **metricas_nucleo(row),
        }

    consolidar = staticmethod(consolidar)


FAMILIA = _Asset()
