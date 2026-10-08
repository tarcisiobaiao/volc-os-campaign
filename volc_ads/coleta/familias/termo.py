"""Família `termo`: campanha × dia × [grupo] × termo de pesquisa × correspondência.

Duas consultas:
- `search_term_view` → Search e demais campanhas com grupo (`ad_group_id` presente);
- `campaign_search_term_view` → só PERFORMANCE_MAX (sem grupo).

O filtro de canal na segunda não é opcional. Medido na Crédito Up em
08/10/2026 (janela 07/10): a view de campanha devolve as MESMAS 320 linhas de
Search que `search_term_view` devolve. Como o hash da RPC inclui
`ad_group_id`, a cópia sem grupo entraria como fato novo e dobraria o tráfego.

`ai_max_search_term_ad_combination_view` fica de fora: o grão dela é termo ×
título × página de destino, sem tipo de correspondência, e o mesmo tráfego já
está em `search_term_view`. Levar a combinação para `metricas_extras` da linha
do termo exigiria juntar linhas de duas consultas, e `normalizar` é linha a linha.
"""
from __future__ import annotations

from typing import Any

from ..contrato import Contexto, enum_nome
from ._metricas_nucleo import SELECT_NUCLEO, id_texto, metricas_nucleo


def _enum(mensagem: Any, campo: str) -> str | None:
    # Enum sem presença lê UNSPECIFIED quando a API não mandou.
    return enum_nome(getattr(mensagem, campo)) if campo in mensagem else None


class _Termo:
    nome = "termo"
    rpc = "volc_registrar_gads_fatos"

    def gaql(self, ctx: Contexto) -> list[str]:
        filtro = f"{ctx.janela_gaql} AND metrics.impressions > 0"
        return [
            "SELECT campaign.id, ad_group.id, search_term_view.search_term, search_term_view.status, "
            f"segments.search_term_match_type, segments.date, {SELECT_NUCLEO} "
            f"FROM search_term_view WHERE {filtro}",
            "SELECT campaign.id, campaign_search_term_view.search_term, "
            f"segments.search_term_match_type, segments.date, {SELECT_NUCLEO} "
            f"FROM campaign_search_term_view WHERE {filtro} "
            "AND campaign.advertising_channel_type = 'PERFORMANCE_MAX'",
        ]

    def normalizar(self, row: Any, ctx: Contexto) -> dict | None:
        if "search_term_view" in row:
            termo = row.search_term_view.search_term
            ad_group_id = id_texto(row.ad_group, "id")
            status = _enum(row.search_term_view, "status")
            if ad_group_id is None:
                return None
        elif "campaign_search_term_view" in row:
            termo = row.campaign_search_term_view.search_term
            ad_group_id, status = None, None
        else:
            return None
        campaign_id = id_texto(row.campaign, "id")
        if not termo.strip() or campaign_id is None or not row.segments.date:
            return None
        return {
            "campaign_id": campaign_id,
            "metric_date": row.segments.date,
            "ad_group_id": ad_group_id,
            "termo": termo,
            "termo_match": _enum(row.segments, "search_term_match_type"),
            "termo_status": status,
            "currency_code": ctx.moeda,
            "colhida_em": ctx.colhida_iso,
            **metricas_nucleo(row),
        }


FAMILIA = _Termo()
