"""Adapters de entrada (futura integração): puros, sem rede; a Bia nunca define parâmetros financeiros."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from volc_dil.contracts import Dinheiro
from volc_dil.viability.adaptadores import (
    BiaNaoPodeDefinirFinanceiro,
    de_campaign_simulation_gaql,
    de_joinads_campanha_dia,
    de_ledger_campanha_dia,
    de_pautador_card,
    de_pesquisa_keyword_planner,
    requisicao_bia,
)
from volc_dil.viability.contrato import Evidencia, PerdaMaxima

AS_OF = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


def test_ledger_campanha_dia_agrega_so_dias_maduros_e_marca_moeda():
    linhas = [
        {"dia": "2026-10-01", "custo_micros": 30_000_000, "custo_moeda": "BRL", "custo_moeda_evidencia": "observed", "cliques": 40,
         "receita_micros": 2_000_000, "receita_moeda": "USD", "receita_moeda_evidencia": "attested", "receita_status": "observed", "maduro": True, "disponivel_em": AS_OF.isoformat()},
        {"dia": "2026-10-02", "custo_micros": 20_000_000, "custo_moeda": "BRL", "custo_moeda_evidencia": "observed", "cliques": 30,
         "receita_micros": None, "receita_moeda": "USD", "receita_moeda_evidencia": "attested", "receita_status": "missing", "maduro": True, "disponivel_em": AS_OF.isoformat()},
        {"dia": "2026-10-03", "custo_micros": 10_000_000, "custo_moeda": "BRL", "custo_moeda_evidencia": "observed", "cliques": 10,
         "receita_micros": 500_000, "receita_moeda": "USD", "receita_moeda_evidencia": "attested", "receita_status": "partial", "maduro": False, "disponivel_em": AS_OF.isoformat()},
    ]
    e = de_ledger_campanha_dia("cand-1", linhas, as_of=AS_OF, vertical="v", pais="BR",
                               cambio={"taxa": "5.25", "de": "USD", "para": "BRL", "proveniencia": "ptax", "evidencia": "observed"},
                               revshare={"valor": "0.8", "evidencia": "attested", "proveniencia": "contrato"},
                               perda_maxima={"valor": {"micros": 300_000_000, "moeda": "BRL"}, "horizonte_dias": 14, "proveniencia": "owner"})
    # só o dia 1 tem custo E receita maduros; o dia 2 (receita missing) não entra na receita nem no custo comparável
    assert e.custo.valor == Dinheiro(30_000_000, "BRL") and e.cliques.valor == 40
    assert e.receita.valor == Dinheiro(2_000_000, "USD") and e.receita.moeda_evidencia is Evidencia.ATTESTED
    assert e.janela.dias_maduros == 1 and e.janela.dias_imaturos == 1
    assert "dias_com_custo_sem_receita=1" in e.flags_qualidade


def test_ledger_sem_dias_maduros_da_receita_ausente_nao_zero():
    linhas = [{"dia": "2026-10-01", "custo_micros": 30_000_000, "custo_moeda": "BRL", "custo_moeda_evidencia": "observed", "cliques": 40,
               "receita_micros": None, "receita_moeda": "USD", "receita_moeda_evidencia": "attested", "receita_status": "missing", "maduro": True, "disponivel_em": AS_OF.isoformat()}]
    e = de_ledger_campanha_dia("cand-1", linhas, as_of=AS_OF)
    assert e.receita.valor is None and e.receita.evidencia is Evidencia.ABSENT


def test_campaign_simulation_gaql_mapeia_cpc_bid_points():
    linha = {"campaign_simulation": {"type": "CPC_BID", "cpc_bid_point_list": {"points": [
        {"cpcBidMicros": "100000", "clicks": 1000, "costMicros": "80000000", "impressions": 50000, "biddableConversions": 10.0},
        {"cpcBidMicros": "150000", "clicks": 1200, "costMicros": "120000000"},
    ]}}}
    s = de_campaign_simulation_gaql(linha, moeda="BRL", disponivel_em=AS_OF, estrategia_lance="MANUAL_CPC")
    assert s.tipo == "CPC_BID" and [p.modificacao_micros for p in s.pontos] == [100_000, 150_000]
    assert s.pontos[0].conversoes == Decimal("10.0") and s.pontos[1].conversoes is None


def test_campaign_simulation_tipo_sem_pontos_vira_simulacao_vazia_nao_erro():
    s = de_campaign_simulation_gaql({"campaign_simulation": {"type": "TARGET_ROAS"}}, moeda="BRL", disponivel_em=AS_OF)
    assert s.tipo == "TARGET_ROAS" and s.pontos == ()


def test_keyword_planner_vira_intervalo_de_cpc_de_pesquisa():
    cpc = de_pesquisa_keyword_planner({"low_top_of_page_bid_micros": 300_000, "high_top_of_page_bid_micros": 900_000}, moeda="BRL")
    assert cpc == (Dinheiro(300_000, "BRL"), Dinheiro(900_000, "BRL"))


def test_joinads_campanha_dia_marca_moeda_atestada_por_padrao():
    m = de_joinads_campanha_dia([{"dia": "2026-10-01", "earnings_micros": 1_000_000, "status": "observed"}], moeda="USD", moeda_evidencia="attested", disponivel_em=AS_OF)
    assert m.valor == Dinheiro(1_000_000, "USD") and m.moeda_evidencia is Evidencia.ATTESTED


def test_pautador_card_sem_historico_so_pesquisa():
    e = de_pautador_card({"id": "card-65", "vertical": "financas", "pais": "BR"}, as_of=AS_OF,
                         cpc_intervalo=(Dinheiro(300_000, "BRL"), Dinheiro(600_000, "BRL")), rpc_intervalo=None,
                         perda_maxima=PerdaMaxima(Dinheiro(300_000_000, "BRL"), 14, "owner"))
    assert e.custo.valor is None and e.receita.valor is None and e.cliques.valor is None
    assert e.cpc_intervalo is not None and e.rpc_intervalo is None


def test_bia_nao_pode_definir_perda_maxima_nem_cambio():
    base = de_pautador_card({"id": "card-65"}, as_of=AS_OF, perda_maxima=PerdaMaxima(Dinheiro(300_000_000, "BRL"), 14, "owner"))
    with pytest.raises(BiaNaoPodeDefinirFinanceiro):
        requisicao_bia(base, {"perda_maxima": {"valor": {"micros": 1, "moeda": "BRL"}, "horizonte_dias": 1}})
    with pytest.raises(BiaNaoPodeDefinirFinanceiro):
        requisicao_bia(base, {"cambio": {"taxa": "9"}})
    r = requisicao_bia(base, {"motivo": "pergunta do operador"})
    assert r.entrada == base and r.somente_leitura is True and r.pode_executar is False
