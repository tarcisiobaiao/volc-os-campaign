from __future__ import annotations

from datetime import date, datetime, timezone

from google.ads.googleads.v25.services.types.google_ads_service import GoogleAdsRow

from volc_ads.coleta.contrato import Contexto
from volc_ads.coleta.familias import todas
from volc_ads.coleta.familias._checagem_v17 import violacoes
from volc_ads.coleta.familias.termo import FAMILIA
from volc_ads.gads import catalogo

CTX = Contexto(customer_id="5478096539", login_customer_id="4904074301", origem_janela="D0",
               data_inicio=date(2026, 10, 7), data_fim=date(2026, 10, 7),
               fuso="America/Sao_Paulo", moeda="BRL",
               colhida_em=datetime(2026, 10, 7, 15, tzinfo=timezone.utc))

METRICAS = {"impressions": 19, "clicks": 3, "interactions": 3, "cost_micros": 2760000,
            "conversions": 1.0, "all_conversions": 1.0, "conversions_value": 10.0,
            "all_conversions_value": 10.0}


def _stv(**metricas) -> GoogleAdsRow:
    return GoogleAdsRow(
        campaign={"id": 24278665189}, ad_group={"id": 199085896206},
        search_term_view={"search_term": "cursos gratuitos senac", "status": "ADDED"},
        segments={"date": "2026-10-07", "search_term_match_type": "EXACT"},
        metrics=metricas or METRICAS)


def _cstv(**metricas) -> GoogleAdsRow:
    return GoogleAdsRow(
        campaign={"id": 555}, campaign_search_term_view={"search_term": "curso tecnico"},
        segments={"date": "2026-10-07", "search_term_match_type": "BROAD"},
        metrics=metricas or METRICAS)


def teste_registrada_com_nome_da_rpc():
    assert todas()["termo"] is FAMILIA
    assert FAMILIA.rpc == "volc_registrar_gads_fatos"


def teste_toda_gaql_passa_no_catalogo_e_usa_a_janela():
    gaqls = FAMILIA.gaql(CTX)
    assert len(gaqls) == 2
    for g in gaqls:
        assert catalogo.invalidos(g) == ()
        assert CTX.janela_gaql in g and "metrics.impressions > 0" in g


def teste_view_de_campanha_so_traz_pmax():
    """Sem o filtro, a view de campanha repete o Search e o hash sem grupo dobra o tráfego."""
    g = FAMILIA.gaql(CTX)[1]
    assert "FROM campaign_search_term_view" in g
    assert "campaign.advertising_channel_type = 'PERFORMANCE_MAX'" in g


def teste_search_term_view_tipos_e_dimensoes():
    linha = FAMILIA.normalizar(_stv(), CTX)
    assert linha["campaign_id"] == "24278665189" and linha["ad_group_id"] == "199085896206"
    assert linha["termo"] == "cursos gratuitos senac"
    assert linha["termo_match"] == "EXACT" and linha["termo_status"] == "ADDED"
    assert type(linha["impressoes"]) is int and type(linha["custo_micros"]) is int
    assert type(linha["conversoes"]) is float
    assert violacoes("termo", linha) == []


def teste_pmax_sem_grupo_e_sem_status():
    linha = FAMILIA.normalizar(_cstv(), CTX)
    assert linha["ad_group_id"] is None and linha["termo_status"] is None
    assert linha["termo"] == "curso tecnico" and linha["termo_match"] == "BROAD"
    assert violacoes("termo", linha) == []


def teste_ausente_none_e_zero_presente_zero():
    linha = FAMILIA.normalizar(_stv(impressions=4, clicks=0, cost_micros=0), CTX)
    assert linha["impressoes"] == 4 and linha["cliques"] == 0 and linha["custo_micros"] == 0
    for c in ("interacoes", "conversoes", "todas_conversoes", "valor_conversoes", "valor_todas_conversoes"):
        assert linha[c] is None, c
    assert violacoes("termo", linha) == []


def teste_enum_ausente_vira_none():
    row = _stv()
    row.segments.search_term_match_type = 0
    row.search_term_view.status = 0
    linha = FAMILIA.normalizar(row, CTX)
    assert linha["termo_match"] is None and linha["termo_status"] is None


def teste_termo_vazio_ou_sem_grupo_e_descartado():
    vazio = _stv()
    vazio.search_term_view.search_term = "  "
    assert FAMILIA.normalizar(vazio, CTX) is None
    sem_grupo = _stv()
    sem_grupo.ad_group.id = 0
    assert FAMILIA.normalizar(sem_grupo, CTX) is None
    assert FAMILIA.normalizar(GoogleAdsRow(campaign={"id": 1}), CTX) is None
