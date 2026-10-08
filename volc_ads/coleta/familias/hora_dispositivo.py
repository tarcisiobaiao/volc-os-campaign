"""Família `hora_dispositivo`: campanha × dia × hora × dispositivo × rede."""
from __future__ import annotations

from typing import Any

from ..contrato import Contexto, enum_nome, medida
from ._metricas_nucleo import SELECT_NUCLEO, id_texto, metricas_nucleo


class _HoraDispositivo:
    nome = "hora_dispositivo"
    rpc = "volc_registrar_gads_fatos"

    def gaql(self, ctx: Contexto) -> str:
        return (
            "SELECT campaign.id, segments.date, segments.hour, segments.device, "
            f"segments.ad_network_type, {SELECT_NUCLEO} "
            f"FROM campaign WHERE {ctx.janela_gaql} AND metrics.impressions > 0"
        )

    def normalizar(self, row: Any, ctx: Contexto) -> dict | None:
        campaign_id = id_texto(row.campaign, "id")
        # Hora 0 é meia-noite medida, não ausência: só a presença decide.
        hora = medida(row.segments, "hour")
        if campaign_id is None or hora is None or not row.segments.date:
            return None
        return {
            "campaign_id": campaign_id,
            "metric_date": row.segments.date,
            "hora": hora,
            "dispositivo": enum_nome(row.segments.device),
            "rede": enum_nome(row.segments.ad_network_type),
            "fuso": ctx.fuso,
            "currency_code": ctx.moeda,
            "colhida_em": ctx.colhida_iso,
            **metricas_nucleo(row),
        }


FAMILIA = _HoraDispositivo()
