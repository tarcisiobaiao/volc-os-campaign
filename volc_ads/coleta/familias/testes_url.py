from __future__ import annotations

from datetime import date

from google.ads.googleads.v25.services.types.google_ads_service import GoogleAdsRow

from volc_ads.coleta.contrato import Contexto
from volc_ads.coleta.familias import todas
from volc_ads.coleta.familias._checagem_v17 import violacoes
from volc_ads.coleta.familias.url import FAMILIA
from volc_ads.gads import catalogo

CTX = Contexto(customer_id="5478096539", login_customer_id="4904074301", origem_janela="D-1",
               data_inicio=date(2026, 10, 7), data_fim=date(2026, 10, 7),
               fuso="America/Sao_Paulo", moeda="BRL")

FINAL = "https://creditoup.com.br/r/guia-cursos-senac/{ignore}?utm_campaign={campaignid}"
EXPANDIDA = "https://creditoup.com.br/r/guia-cursos-senac/?utm_campaign=24278665189"


def _row(view: str, **metricas) -> GoogleAdsRow:
    r = GoogleAdsRow()
    r.campaign.id = 24278665189
    r.segments.date = "2026-10-07"
    if view == "final":
        r.landing_page_view.unexpanded_final_url = FINAL
    else:
        r.expanded_landing_page_view.expanded_final_url = EXPANDIDA
    for campo, valor in metricas.items():
        setattr(r.metrics, campo, valor)
    return r


COMPLETA = dict(impressions=861, clicks=65, interactions=65, cost_micros=58_760_000,
                conversions=29.0, all_conversions=39.0, conversions_value=290.0,
                all_conversions_value=390.0)


def teste_familia_registrada_com_nome_e_rpc():
    assert todas()["url"] is FAMILIA
    assert FAMILIA.rpc == "volc_registrar_gads_fatos"


def teste_cada_view_vira_seu_url_tipo():
    f = FAMILIA.normalizar(_row("final", **COMPLETA), CTX)
    e = FAMILIA.normalizar(_row("expandida", **COMPLETA), CTX)
    assert (f["url"], f["url_tipo"]) == (FINAL, "final")
    assert (e["url"], e["url_tipo"]) == (EXPANDIDA, "expandida")


def teste_tipos_da_linha():
    l = FAMILIA.normalizar(_row("final", **COMPLETA), CTX)
    assert l["campaign_id"] == "24278665189" and l["metric_date"] == "2026-10-07"
    for c in ("impressoes", "cliques", "interacoes", "custo_micros"):
        assert type(l[c]) is int, c
    for c in ("conversoes", "todas_conversoes", "valor_conversoes", "valor_todas_conversoes"):
        assert type(l[c]) is float, c
    assert (l["currency_code"], l["colhida_em"]) == ("BRL", CTX.colhida_iso)


def teste_ausente_vira_none_e_zero_presente_fica_zero():
    l = FAMILIA.normalizar(_row("expandida", impressions=10, clicks=0, cost_micros=0), CTX)
    assert l["cliques"] == 0 and l["custo_micros"] == 0
    assert l["interacoes"] is None and l["conversoes"] is None and l["todas_conversoes"] is None


def teste_extras_so_quando_medidos_e_com_tipo_numerico():
    assert FAMILIA.normalizar(_row("final", **COMPLETA), CTX)["metricas_extras"] == {}
    l = FAMILIA.normalizar(_row("final", speed_score=7, mobile_friendly_clicks_percentage=0.0,
                                **COMPLETA), CTX)
    assert l["metricas_extras"] == {"speed_score": 7, "mobile_friendly_clicks_percentage": 0.0}
    assert type(l["metricas_extras"]["speed_score"]) is int
    assert type(l["metricas_extras"]["mobile_friendly_clicks_percentage"]) is float


def teste_sem_url_descarta():
    r = GoogleAdsRow()
    r.campaign.id = 1
    r.segments.date = "2026-10-07"
    assert FAMILIA.normalizar(r, CTX) is None
    r.landing_page_view.unexpanded_final_url = "  "
    assert FAMILIA.normalizar(r, CTX) is None


def teste_gaqls_passam_no_catalogo_e_cada_uma_le_sua_view():
    gaqls = FAMILIA.gaql(CTX)
    assert len(gaqls) == 2
    for g in gaqls:
        assert catalogo.invalidos(g) == ()
        assert CTX.janela_gaql in g and "metrics.impressions > 0" in g
        assert "metrics.speed_score" in g
    assert "FROM landing_page_view" in gaqls[0] and "expanded_landing_page_view." not in gaqls[0]
    assert "FROM expanded_landing_page_view" in gaqls[1] and " landing_page_view." not in gaqls[1]


def teste_linha_satisfaz_checks_da_v17_01():
    for view in ("final", "expandida"):
        l = FAMILIA.normalizar(_row(view, **COMPLETA), CTX)
        assert violacoes("url", l) == []
        assert violacoes("geo", l) != []
