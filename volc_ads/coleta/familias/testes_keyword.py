from __future__ import annotations

from datetime import date, datetime, timezone

from google.ads.googleads.v25.services.types.google_ads_service import GoogleAdsRow

from volc_ads.coleta.contrato import Contexto
from volc_ads.coleta.familias import todas
from volc_ads.coleta.familias._checagem_v17 import violacoes
from volc_ads.coleta.familias.keyword import FAMILIA
from volc_ads.gads import catalogo

CTX = Contexto(customer_id="5478096539", login_customer_id="4904074301", origem_janela="backfill",
               data_inicio=date(2026, 10, 1), data_fim=date(2026, 10, 7),
               fuso="America/Sao_Paulo", moeda="BRL",
               colhida_em=datetime(2026, 10, 8, 12, tzinfo=timezone.utc))

METRICAS = {"impressions": 375, "clicks": 40, "interactions": 40, "cost_micros": 36900000,
            "conversions": 16.5, "all_conversions": 26.0, "conversions_value": 165.0,
            "all_conversions_value": 260.0}


def _row(quality_info: dict | None = None, metricas: dict | None = None) -> GoogleAdsRow:
    qi = {"quality_score": 8, "creative_quality_score": "ABOVE_AVERAGE",
          "post_click_quality_score": "AVERAGE", "search_predicted_ctr": "BELOW_AVERAGE"}
    return GoogleAdsRow(
        campaign={"id": 24278665189}, ad_group={"id": 199085896206},
        ad_group_criterion={"criterion_id": 300693767730,
                            "keyword": {"text": "cursos gratuitos senac", "match_type": "PHRASE"},
                            "quality_info": qi if quality_info is None else quality_info},
        segments={"date": "2026-10-07"}, metrics=METRICAS if metricas is None else metricas)


def teste_registrada_com_nome_da_rpc():
    assert todas()["keyword"] is FAMILIA
    assert FAMILIA.rpc == "volc_registrar_gads_fatos"


def teste_gaql_passa_no_catalogo_e_usa_a_janela():
    g = FAMILIA.gaql(CTX)
    assert catalogo.invalidos(g) == ()
    assert "FROM keyword_view" in g and CTX.janela_gaql in g and "metrics.impressions > 0" in g


def teste_tipos_e_quality_score():
    linha = FAMILIA.normalizar(_row(), CTX)
    assert linha["ad_group_id"] == "199085896206" and linha["criterion_id"] == "300693767730"
    assert linha["keyword_texto"] == "cursos gratuitos senac" and linha["keyword_match"] == "PHRASE"
    assert linha["quality_score"] == 8 and type(linha["quality_score"]) is int
    assert linha["qs_anuncio"] == "ABOVE_AVERAGE" and linha["qs_pagina"] == "AVERAGE"
    assert linha["qs_ctr_previsto"] == "BELOW_AVERAGE"
    assert type(linha["impressoes"]) is int and type(linha["conversoes"]) is float
    assert violacoes("keyword", linha) == []


def teste_sem_quality_info_tudo_none():
    """Como a 2ª palavra da Crédito Up em 07/10: 486 impressões e nenhum dado de QS."""
    linha = FAMILIA.normalizar(_row(quality_info={}), CTX)
    assert linha["quality_score"] is None
    assert linha["qs_anuncio"] is None and linha["qs_pagina"] is None and linha["qs_ctr_previsto"] is None
    assert linha["metricas_extras"] == {}
    assert violacoes("keyword", linha) == []


def teste_quality_score_zero_presente_nao_e_nota():
    linha = FAMILIA.normalizar(_row(quality_info={"quality_score": 0}), CTX)
    assert linha["quality_score"] is None
    assert violacoes("keyword", linha) == []


def teste_ausente_none_e_zero_presente_zero():
    linha = FAMILIA.normalizar(_row(metricas={"impressions": 9, "clicks": 0, "conversions": 0.0}), CTX)
    assert linha["impressoes"] == 9 and linha["cliques"] == 0 and linha["conversoes"] == 0.0
    assert linha["custo_micros"] is None and linha["valor_todas_conversoes"] is None


def teste_historico_do_dia_vai_em_extras():
    linha = FAMILIA.normalizar(_row(metricas={**METRICAS, "historical_quality_score": 7,
                                              "historical_search_predicted_ctr": "AVERAGE"}), CTX)
    assert linha["metricas_extras"] == {"historical_quality_score": 7,
                                        "historical_search_predicted_ctr": "AVERAGE"}


def teste_sem_ids_e_descartada():
    row = _row()
    row.ad_group_criterion.criterion_id = 0
    assert FAMILIA.normalizar(row, CTX) is None
    row = _row()
    row.ad_group.id = 0
    assert FAMILIA.normalizar(row, CTX) is None
