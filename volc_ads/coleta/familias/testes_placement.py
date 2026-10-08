from __future__ import annotations

from datetime import date, datetime, timezone

from google.ads.googleads.v25.services.types.google_ads_service import GoogleAdsRow

from volc_ads.coleta.contrato import Contexto
from volc_ads.coleta.familias import todas
from volc_ads.coleta.familias._checagem_v17 import violacoes
from volc_ads.coleta.familias.placement import FAMILIA
from volc_ads.gads import catalogo

CTX = Contexto(customer_id="5478096539", login_customer_id="4904074301", origem_janela="D-1",
               data_inicio=date(2026, 10, 7), data_fim=date(2026, 10, 7),
               fuso="America/Sao_Paulo", moeda="BRL",
               colhida_em=datetime(2026, 10, 8, 12, tzinfo=timezone.utc))

METRICAS = {"impressions": 120, "clicks": 0, "interactions": 3, "cost_micros": 4500000,
            "conversions": 0.0, "all_conversions": 1.5, "conversions_value": 0.0,
            "all_conversions_value": 30.0}


def _row(view: str, metricas: dict | None = None, **dados) -> GoogleAdsRow:
    base = {"placement": "exemplo.com.br/noticia", "target_url": "https://exemplo.com.br/noticia",
            "placement_type": "WEBSITE", "display_name": "Exemplo"}
    base.update(dados)
    return GoogleAdsRow(campaign={"id": 24278665189}, segments={"date": "2026-10-07"},
                        metrics=METRICAS if metricas is None else metricas, **{view: base})


def teste_registrada_com_nome_da_rpc():
    assert todas()["placement"] is FAMILIA
    assert FAMILIA.rpc == "volc_registrar_gads_fatos"


def teste_toda_gaql_passa_no_catalogo_e_usa_a_janela():
    gaqls = FAMILIA.gaql(CTX)
    assert len(gaqls) == 3
    for g in gaqls:
        assert catalogo.invalidos(g) == ()
        assert CTX.janela_gaql in g and "metrics.impressions > 0" in g


def teste_pmax_so_pede_impressoes():
    pmax = FAMILIA.gaql(CTX)[2]
    assert "FROM performance_max_placement_view" in pmax
    assert "metrics.clicks" not in pmax and "metrics.cost_micros" not in pmax


def teste_detail_tipos_e_zero_presente():
    linha = FAMILIA.normalizar(_row("detail_placement_view"), CTX)
    assert linha["placement_view"] == "detail"
    assert linha["placement"] == "exemplo.com.br/noticia"
    assert linha["placement_tipo"] == "WEBSITE" and linha["placement_nome"] == "Exemplo"
    assert linha["campaign_id"] == "24278665189" and linha["metric_date"] == "2026-10-07"
    assert linha["currency_code"] == "BRL" and linha["colhida_em"] == CTX.colhida_iso
    assert linha["impressoes"] == 120 and type(linha["impressoes"]) is int
    assert linha["cliques"] == 0 and type(linha["cliques"]) is int
    assert linha["conversoes"] == 0.0 and type(linha["conversoes"]) is float
    assert violacoes("placement", linha) == []


def teste_group_vem_marcado():
    linha = FAMILIA.normalizar(_row("group_placement_view", placement="youtube.com::UCabc"), CTX)
    assert linha["placement_view"] == "group" and linha["placement"] == "youtube.com::UCabc"
    assert violacoes("placement", linha) == []


def teste_pmax_metricas_ausentes_sao_none():
    linha = FAMILIA.normalizar(_row("performance_max_placement_view", {"impressions": 7}), CTX)
    assert linha["placement_view"] == "pmax" and linha["impressoes"] == 7
    for c in ("cliques", "interacoes", "custo_micros", "conversoes", "todas_conversoes",
              "valor_conversoes", "valor_todas_conversoes"):
        assert linha[c] is None, c
    assert violacoes("placement", linha) == []


def teste_target_url_so_quando_placement_vazio():
    linha = FAMILIA.normalizar(_row("detail_placement_view", placement=""), CTX)
    assert linha["placement"] == "https://exemplo.com.br/noticia"
    assert FAMILIA.normalizar(_row("detail_placement_view", placement="", target_url=" "), CTX) is None


def teste_atributo_ausente_vira_none():
    linha = FAMILIA.normalizar(_row("detail_placement_view", placement_type=0, display_name=""), CTX)
    assert linha["placement_tipo"] is None and linha["placement_nome"] is None


def teste_linha_sem_view_ou_campanha_e_descartada():
    assert FAMILIA.normalizar(GoogleAdsRow(campaign={"id": 1}, segments={"date": "2026-10-07"}), CTX) is None
    sem_campanha = _row("detail_placement_view")
    sem_campanha.campaign.id = 0
    assert FAMILIA.normalizar(sem_campanha, CTX) is None


def teste_consolidar_soma_o_mesmo_placement_de_dois_grupos():
    a = FAMILIA.normalizar(_row("detail_placement_view"), CTX)
    b = FAMILIA.normalizar(_row("detail_placement_view", {"impressions": 10, "clicks": 2,
                                                          "conversions": 0.5}), CTX)
    outro = FAMILIA.normalizar(_row("group_placement_view"), CTX)
    saida = FAMILIA.consolidar([a, outro, b])
    assert len(saida) == 2 and saida[1] is outro
    soma = saida[0]
    assert soma["impressoes"] == 130 and soma["cliques"] == 2 and soma["conversoes"] == 0.5
    # o segundo grupo não mediu custo: ausente + medido = medido
    assert soma["custo_micros"] == 4500000
    assert soma["metricas_extras"] == {"linhas_somadas": 2}
    assert violacoes("placement", soma) == []
