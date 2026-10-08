from __future__ import annotations

from datetime import date, datetime, timezone

from google.ads.googleads.v25.services.types.google_ads_service import GoogleAdsRow

from volc_ads.coleta.contrato import Contexto
from volc_ads.coleta.familias import todas
from volc_ads.coleta.familias._checagem_v17 import violacoes
from volc_ads.coleta.familias.asset import FAMILIA
from volc_ads.gads import catalogo

CTX = Contexto(customer_id="5478096539", login_customer_id="4904074301", origem_janela="D-1",
               data_inicio=date(2026, 10, 7), data_fim=date(2026, 10, 7),
               fuso="America/Sao_Paulo", moeda="BRL",
               colhida_em=datetime(2026, 10, 8, 12, tzinfo=timezone.utc))

METRICAS = {"impressions": 759, "clicks": 61, "interactions": 61, "cost_micros": 56200000,
            "conversions": 26.0, "all_conversions": 36.0, "conversions_value": 260.0,
            "all_conversions_value": 360.0}


def _anuncio(rotulo: str = "GOOD", metricas: dict | None = None) -> GoogleAdsRow:
    return GoogleAdsRow(
        campaign={"id": 24278665189}, ad_group={"id": 199085896206}, asset={"id": 425667471127},
        ad_group_ad_asset_view={"field_type": "HEADLINE", "performance_label": rotulo},
        segments={"date": "2026-10-07"}, metrics=METRICAS if metricas is None else metricas)


def _pmax(metricas: dict | None = None) -> GoogleAdsRow:
    return GoogleAdsRow(
        campaign={"id": 777}, asset_group={"id": 6001}, asset={"id": 9002},
        asset_group_asset={"field_type": "MARKETING_IMAGE"},
        segments={"date": "2026-10-07"}, metrics=METRICAS if metricas is None else metricas)


def teste_registrada_com_nome_da_rpc():
    assert todas()["asset"] is FAMILIA
    assert FAMILIA.rpc == "volc_registrar_gads_fatos"


def teste_toda_gaql_passa_no_catalogo_e_usa_a_janela():
    gaqls = FAMILIA.gaql(CTX)
    assert [g.split(" FROM ")[1].split()[0] for g in gaqls] == ["ad_group_ad_asset_view", "asset_group_asset"]
    for g in gaqls:
        assert catalogo.invalidos(g) == ()
        assert CTX.janela_gaql in g and "metrics.impressions > 0" in g


def teste_contexto_ad_group():
    linha = FAMILIA.normalizar(_anuncio(), CTX)
    assert linha["asset_contexto"] == "ad_group" and linha["asset_contexto_id"] == "199085896206"
    assert linha["asset_id"] == "425667471127" and linha["asset_campo"] == "HEADLINE"
    assert linha["asset_rotulo"] == "GOOD"
    assert type(linha["impressoes"]) is int and type(linha["valor_conversoes"]) is float
    assert violacoes("asset", linha) == []


def teste_contexto_asset_group_sem_rotulo():
    linha = FAMILIA.normalizar(_pmax(), CTX)
    assert linha["asset_contexto"] == "asset_group" and linha["asset_contexto_id"] == "6001"
    assert linha["asset_campo"] == "MARKETING_IMAGE" and linha["asset_rotulo"] is None
    assert violacoes("asset", linha) == []


def teste_ausente_none_e_zero_presente_zero():
    linha = FAMILIA.normalizar(_pmax({"impressions": 3, "clicks": 0, "cost_micros": 0}), CTX)
    assert linha["cliques"] == 0 and linha["custo_micros"] == 0
    assert linha["conversoes"] is None and linha["interacoes"] is None


def teste_rotulo_ausente_vira_none_e_not_applicable_passa():
    assert FAMILIA.normalizar(_anuncio(rotulo=0), CTX)["asset_rotulo"] is None
    assert FAMILIA.normalizar(_anuncio(rotulo="NOT_APPLICABLE"), CTX)["asset_rotulo"] == "NOT_APPLICABLE"


def teste_sem_campo_ou_asset_e_descartada():
    row = _anuncio()
    row.ad_group_ad_asset_view.field_type = 0
    assert FAMILIA.normalizar(row, CTX) is None
    row = _pmax()
    row.asset.id = 0
    assert FAMILIA.normalizar(row, CTX) is None


def teste_consolidar_mesmo_titulo_em_dois_anuncios_do_grupo():
    a = FAMILIA.normalizar(_anuncio("GOOD"), CTX)
    b = FAMILIA.normalizar(_anuncio("LOW", {"impressions": 41, "clicks": 4, "conversions": 1.0}), CTX)
    c = FAMILIA.normalizar(_anuncio("GOOD", {"impressions": 10}), CTX)
    [soma] = FAMILIA.consolidar([a, b, c])
    assert soma["impressoes"] == 810 and soma["cliques"] == 65 and soma["conversoes"] == 27.0
    assert soma["asset_rotulo"] is None  # anúncios discordaram
    assert soma["metricas_extras"] == {"linhas_somadas": 3}
    assert violacoes("asset", soma) == []
    [igual] = FAMILIA.consolidar([FAMILIA.normalizar(_anuncio("GOOD"), CTX)] * 2)
    assert igual["asset_rotulo"] == "GOOD"
