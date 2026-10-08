"""Família `keyword`: campanha × dia × grupo × critério de palavra-chave (+ Quality Score).

As colunas de QS vêm de `quality_info`, que é o estado do INSTANTE da coleta:
numa linha de backfill descrevem hoje, não `metric_date`. A nota do dia medido
vem das métricas `historical_*` (segmentáveis por data; conferidas com leitura
real em 08/10/2026), que vão em `metricas_extras` quando a API manda.
"""
from __future__ import annotations

from typing import Any

from ..contrato import Contexto, enum_nome, medida
from ._metricas_nucleo import SELECT_NUCLEO, id_texto, metricas_nucleo

_QI = "ad_group_criterion.quality_info"

HISTORICO = {
    "historical_quality_score": int,
    "historical_creative_quality_score": None,
    "historical_landing_page_quality_score": None,
    "historical_search_predicted_ctr": None,
}
_SELECT_HISTORICO = ", ".join(f"metrics.{m}" for m in HISTORICO)


def _enum(mensagem: Any, campo: str) -> str | None:
    # Enum sem presença lê UNSPECIFIED quando a API não mandou (palavra sem QS).
    return enum_nome(getattr(mensagem, campo)) if campo in mensagem else None


class _Keyword:
    nome = "keyword"
    rpc = "volc_registrar_gads_fatos"

    def gaql(self, ctx: Contexto) -> str:
        return (
            "SELECT campaign.id, ad_group.id, ad_group_criterion.criterion_id, "
            "ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type, "
            f"{_QI}.quality_score, {_QI}.creative_quality_score, "
            f"{_QI}.post_click_quality_score, {_QI}.search_predicted_ctr, "
            f"segments.date, {SELECT_NUCLEO}, {_SELECT_HISTORICO} "
            f"FROM keyword_view WHERE {ctx.janela_gaql} AND metrics.impressions > 0"
        )

    def normalizar(self, row: Any, ctx: Contexto) -> dict | None:
        criterio = row.ad_group_criterion
        campaign_id = id_texto(row.campaign, "id")
        ad_group_id = id_texto(row.ad_group, "id")
        criterion_id = id_texto(criterio, "criterion_id")
        if campaign_id is None or ad_group_id is None or criterion_id is None or not row.segments.date:
            return None
        qi = criterio.quality_info
        # Medido na Crédito Up em 08/10/2026: palavra sem dado suficiente vem sem
        # o campo (lido como 0 sem `medida`). 0 não é nota; fora de 1..10, idem.
        qs = medida(qi, "quality_score")
        historico = {m: (medida(row.metrics, m) if tipo else _enum(row.metrics, m))
                     for m, tipo in HISTORICO.items()}
        return {
            "campaign_id": campaign_id,
            "metric_date": row.segments.date,
            "ad_group_id": ad_group_id,
            "criterion_id": criterion_id,
            "keyword_texto": criterio.keyword.text,
            "keyword_match": _enum(criterio.keyword, "match_type"),
            "quality_score": qs if qs is not None and 1 <= qs <= 10 else None,
            "qs_anuncio": _enum(qi, "creative_quality_score"),
            "qs_pagina": _enum(qi, "post_click_quality_score"),
            "qs_ctr_previsto": _enum(qi, "search_predicted_ctr"),
            "currency_code": ctx.moeda,
            "colhida_em": ctx.colhida_iso,
            **metricas_nucleo(row),
            "metricas_extras": {m: v for m, v in historico.items() if v is not None},
        }


FAMILIA = _Keyword()
