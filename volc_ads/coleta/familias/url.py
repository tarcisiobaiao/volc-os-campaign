"""Família `url`: campanha × dia × página de destino.

Duas consultas, uma por view:
- `landing_page_view` → URL final como configurada (`url_tipo = 'final'`);
- `expanded_landing_page_view` → URL depois do ValueTrack/sufixo (`'expandida'`).

As duas cobrem o mesmo tráfego por recortes diferentes: quem lê agrega dentro
de UM `url_tipo`, nunca dos dois juntos. E nem dentro de um a soma bate com a
campanha: a impressão de um anúncio com sitelinks conta para cada página
exibida (Crédito Up, 07/10/2026: 3084 impressões somando URLs × 861 na campanha).
"""
from __future__ import annotations

from typing import Any

from ..contrato import Contexto, medida
from ._metricas_nucleo import SELECT_NUCLEO, id_texto, metricas_nucleo

# Experiência de página. Conferido no GoogleAdsFieldService em 08/10/2026: as
# três são selecionáveis nas duas views (e em geographic_view, não).
EXTRAS: dict[str, type] = {
    "speed_score": int,
    "mobile_friendly_clicks_percentage": float,
    "valid_accelerated_mobile_pages_clicks_percentage": float,
}
_SELECT_EXTRAS = ", ".join(f"metrics.{m}" for m in EXTRAS)


class _Url:
    nome = "url"
    rpc = "volc_registrar_gads_fatos"

    def gaql(self, ctx: Contexto) -> list[str]:
        filtro = f"WHERE {ctx.janela_gaql} AND metrics.impressions > 0"
        return [
            "SELECT landing_page_view.unexpanded_final_url, campaign.id, segments.date, "
            f"{SELECT_NUCLEO}, {_SELECT_EXTRAS} FROM landing_page_view {filtro}",
            "SELECT expanded_landing_page_view.expanded_final_url, campaign.id, segments.date, "
            f"{SELECT_NUCLEO}, {_SELECT_EXTRAS} FROM expanded_landing_page_view {filtro}",
        ]

    def normalizar(self, row: Any, ctx: Contexto) -> dict | None:
        # A linha não diz de qual GAQL veio; o campo de URL presente diz. Cada
        # consulta seleciona só o da sua view, então nunca vêm os dois.
        if "unexpanded_final_url" in row.landing_page_view:
            url, url_tipo = row.landing_page_view.unexpanded_final_url, "final"
        elif "expanded_final_url" in row.expanded_landing_page_view:
            url, url_tipo = row.expanded_landing_page_view.expanded_final_url, "expandida"
        else:
            return None
        campaign_id = id_texto(row.campaign, "id")
        if campaign_id is None or not url.strip() or not row.segments.date:
            return None
        extras = {m: medida(row.metrics, m, tipo) for m, tipo in EXTRAS.items()}
        return {
            "campaign_id": campaign_id,
            "metric_date": row.segments.date,
            "url": url,
            "url_tipo": url_tipo,
            "currency_code": ctx.moeda,
            "colhida_em": ctx.colhida_iso,
            **metricas_nucleo(row),
            # Extra não medido fica fora do jsonb; a API costuma não mandá-los.
            "metricas_extras": {m: v for m, v in extras.items() if v is not None},
        }


FAMILIA = _Url()
