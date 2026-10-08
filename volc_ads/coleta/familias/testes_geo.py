from __future__ import annotations

from datetime import date

from google.ads.googleads.v25.enums.types.geo_targeting_type import GeoTargetingTypeEnum
from google.ads.googleads.v25.services.types.google_ads_service import GoogleAdsRow

from volc_ads.coleta.contrato import Contexto
from volc_ads.coleta.familias import todas
from volc_ads.coleta.familias._checagem_v17 import violacoes
from volc_ads.coleta.familias.geo import FAMILIA
from volc_ads.gads import catalogo

CTX = Contexto(customer_id="5478096539", login_customer_id="4904074301", origem_janela="D-1",
               data_inicio=date(2026, 10, 7), data_fim=date(2026, 10, 7),
               fuso="America/Sao_Paulo", moeda="BRL")
TIPO = GeoTargetingTypeEnum.GeoTargetingType


def _row(nivel: str, tipo=TIPO.LOCATION_OF_PRESENCE, **metricas) -> GoogleAdsRow:
    r = GoogleAdsRow()
    r.campaign.id = 24278665189
    r.segments.date = "2026-10-07"
    r.geographic_view.location_type = tipo
    if nivel == "pais":
        r.geographic_view.country_criterion_id = 2076
    else:
        r.segments.geo_target_city = "geoTargetConstants/1001773"
    for campo, valor in metricas.items():
        setattr(r.metrics, campo, valor)
    return r


COMPLETA = dict(impressions=861, clicks=66, interactions=66, cost_micros=59_660_000,
                conversions=30.0, all_conversions=42.0, conversions_value=300.0,
                all_conversions_value=420.0)


def teste_familia_registrada_com_nome_e_rpc():
    assert todas()["geo"] is FAMILIA
    assert FAMILIA.rpc == "volc_registrar_gads_fatos"


def teste_pais_e_cidade():
    p = FAMILIA.normalizar(_row("pais", **COMPLETA), CTX)
    c = FAMILIA.normalizar(_row("cidade", **COMPLETA), CTX)
    assert (p["geo_constant"], p["geo_nivel"]) == ("geoTargetConstants/2076", "pais")
    assert (c["geo_constant"], c["geo_nivel"]) == ("geoTargetConstants/1001773", "cidade")


def teste_local_tipo_traduzido_e_outros_descartados():
    assert FAMILIA.normalizar(_row("pais", TIPO.AREA_OF_INTEREST), CTX)["local_tipo"] == "area_de_interesse"
    assert FAMILIA.normalizar(_row("pais", TIPO.LOCATION_OF_PRESENCE), CTX)["local_tipo"] == "localizacao_fisica"
    for outro in (TIPO.UNKNOWN, TIPO.UNSPECIFIED):
        assert FAMILIA.normalizar(_row("cidade", outro), CTX) is None


def teste_tipos_da_linha():
    l = FAMILIA.normalizar(_row("cidade", **COMPLETA), CTX)
    assert l["campaign_id"] == "24278665189" and l["metric_date"] == "2026-10-07"
    for c in ("impressoes", "cliques", "interacoes", "custo_micros"):
        assert type(l[c]) is int, c
    for c in ("conversoes", "todas_conversoes", "valor_conversoes", "valor_todas_conversoes"):
        assert type(l[c]) is float, c
    assert (l["currency_code"], l["colhida_em"]) == ("BRL", CTX.colhida_iso)


def teste_ausente_vira_none_e_zero_presente_fica_zero():
    l = FAMILIA.normalizar(_row("pais", impressions=4, clicks=0, all_conversions=0.0), CTX)
    assert l["cliques"] == 0 and l["todas_conversoes"] == 0.0
    assert l["custo_micros"] is None and l["conversoes"] is None and l["valor_conversoes"] is None


def teste_linha_da_consulta_de_cidade_sem_cidade_descarta():
    # A consulta de cidade não pede country_criterion_id: sem cidade, nada identifica o local.
    r = _row("cidade", **COMPLETA)
    del r.segments.geo_target_city
    assert FAMILIA.normalizar(r, CTX) is None
    r.segments.geo_target_city = ""
    assert FAMILIA.normalizar(r, CTX) is None


def teste_gaqls_passam_no_catalogo():
    pais, cidade = FAMILIA.gaql(CTX)
    for g in (pais, cidade):
        assert catalogo.invalidos(g) == ()
        assert "FROM geographic_view" in g and CTX.janela_gaql in g and "metrics.impressions > 0" in g
    assert "country_criterion_id" in pais and "geo_target_city" not in pais
    assert "geo_target_city" in cidade and "country_criterion_id" not in cidade


def teste_linha_satisfaz_checks_da_v17_01():
    for nivel in ("pais", "cidade"):
        l = FAMILIA.normalizar(_row(nivel, **COMPLETA), CTX)
        assert violacoes("geo", l) == []
        assert violacoes("hora_dispositivo", l) != []
