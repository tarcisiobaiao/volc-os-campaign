from __future__ import annotations

from datetime import date

from google.ads.googleads.v25.enums.types.ad_network_type import AdNetworkTypeEnum
from google.ads.googleads.v25.enums.types.device import DeviceEnum
from google.ads.googleads.v25.services.types.google_ads_service import GoogleAdsRow

from volc_ads.coleta.contrato import Contexto
from volc_ads.coleta.familias import todas
from volc_ads.coleta.familias._checagem_v17 import violacoes
from volc_ads.coleta.familias.hora_dispositivo import FAMILIA
from volc_ads.gads import catalogo

CTX = Contexto(customer_id="5478096539", login_customer_id="4904074301", origem_janela="D-1",
               data_inicio=date(2026, 10, 7), data_fim=date(2026, 10, 7),
               fuso="America/Sao_Paulo", moeda="BRL")


def _row(**metricas) -> GoogleAdsRow:
    r = GoogleAdsRow()
    r.campaign.id = 24278665189
    r.segments.date = "2026-10-07"
    r.segments.hour = 9
    r.segments.device = DeviceEnum.Device.MOBILE
    r.segments.ad_network_type = AdNetworkTypeEnum.AdNetworkType.SEARCH
    for campo, valor in metricas.items():
        setattr(r.metrics, campo, valor)
    return r


COMPLETA = dict(impressions=861, clicks=65, interactions=65, cost_micros=58_760_000,
                conversions=29.0, all_conversions=39.0, conversions_value=290.0,
                all_conversions_value=390.0)


def teste_familia_registrada_com_nome_e_rpc():
    assert todas()["hora_dispositivo"] is FAMILIA
    assert FAMILIA.rpc == "volc_registrar_gads_fatos"


def teste_tipos_da_linha():
    l = FAMILIA.normalizar(_row(**COMPLETA), CTX)
    assert l["campaign_id"] == "24278665189"
    assert l["metric_date"] == "2026-10-07"
    assert l["hora"] == 9 and type(l["hora"]) is int
    assert (l["dispositivo"], l["rede"], l["fuso"]) == ("MOBILE", "SEARCH", "America/Sao_Paulo")
    assert (l["currency_code"], l["colhida_em"]) == ("BRL", CTX.colhida_iso)
    for c in ("impressoes", "cliques", "interacoes", "custo_micros"):
        assert type(l[c]) is int, c
    for c in ("conversoes", "todas_conversoes", "valor_conversoes", "valor_todas_conversoes"):
        assert type(l[c]) is float, c
    assert l["custo_micros"] == 58_760_000


def teste_ausente_vira_none_e_zero_presente_fica_zero():
    l = FAMILIA.normalizar(_row(impressions=3, clicks=0, conversions=0.0), CTX)
    assert l["cliques"] == 0 and l["conversoes"] == 0.0
    assert l["interacoes"] is None and l["custo_micros"] is None
    assert l["valor_conversoes"] is None and l["valor_todas_conversoes"] is None


def teste_hora_zero_e_meia_noite_nao_ausencia():
    r = _row(**COMPLETA)
    r.segments.hour = 0
    assert FAMILIA.normalizar(r, CTX)["hora"] == 0


def teste_sem_hora_ou_sem_campanha_descarta():
    r = _row(**COMPLETA)
    del r.segments.hour
    assert FAMILIA.normalizar(r, CTX) is None
    r = _row(**COMPLETA)
    del r.campaign.id
    assert FAMILIA.normalizar(r, CTX) is None


def teste_gaql_passa_no_catalogo():
    gaql = FAMILIA.gaql(CTX)
    assert catalogo.invalidos(gaql) == ()
    assert "FROM campaign" in gaql and "metrics.impressions > 0" in gaql
    assert CTX.janela_gaql in gaql


def teste_linha_satisfaz_checks_da_v17_01():
    l = FAMILIA.normalizar(_row(**COMPLETA), CTX)
    assert violacoes("hora_dispositivo", l) == []
    assert violacoes("url", l) != []  # dimensões de hora numa linha de url seriam recusadas
