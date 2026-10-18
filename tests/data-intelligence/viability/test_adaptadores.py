"""Adapters de entrada (futura integração): puros, sem rede; a Bia nunca define parâmetros financeiros nem autoriza.

Regras do adapter de ledger (campanha × dia):
- custo e cliques somam TODOS os dias maduros com custo (nunca filtrados pela receita);
- receita soma só dias maduros com receita_status em {observed, zero_confirmed};
- evidência agregada = a mais fraca entre as linhas; flags = união; observado_em = o mais antigo;
- moedas heterogêneas numa mesma medida são erro de contrato (nunca "a primeira");
- datas duplicadas são deduplicadas pela maior disponivel_em e viram flag; dias_* contam datas distintas;
- `cliques` ausente num dia com custo ⇒ cliques agregado UNKNOWN (o custo é real, a contagem não é somável);
- moeda nunca é assumida: sem `custo_moeda`/`receita_moeda` em nenhuma linha a medida vira UNKNOWN com flag
  `moeda_ausente` (fail-closed); linha com valor sem moeda enquanto outras declaram é `moeda_ausente_em_linha`;
  o câmbio nunca inventa o par (de/para) e `de_pautador_card` exige `moeda`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
from volc_dil.viability.contrato import Autorizacao, ContratoViabilidadeViolado, Evidencia

AS_OF = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
EFETIVO = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
AUT = Autorizacao.emitir(authorization_id="AUTH-T-0001", version="1", issuer="owner:teste", effective_at=EFETIVO, expires_at=None, disponivel_em=EFETIVO)
CAMBIO = {"taxa": "5.25", "de": "USD", "para": "BRL", "proveniencia": "ptax", "evidencia": "observed", "effective_at": EFETIVO.isoformat(), "disponivel_em": EFETIVO.isoformat(), "versao": "ptax-2026-10-01"}
REVSHARE = {"valor": "0.8", "evidencia": "attested", "proveniencia": "contrato", "effective_at": EFETIVO.isoformat(), "disponivel_em": EFETIVO.isoformat(), "versao": "contrato-v3"}
PERDA = {"valor": {"micros": 300_000_000, "moeda": "BRL"}, "horizonte_dias": 14, "autorizacao": AUT.para_json()}


def linha(dia, custo, cliques=10, receita=None, receita_status=None, maduro=True, **extra):
    """Linha campanha×dia do ledger. `receita_status` default: observed com valor, missing sem valor.
    `status` (em extra) é o status da LINHA (lado do custo): observed/projected/estimated…"""
    d = {"dia": dia, "custo_micros": custo, "custo_moeda": "BRL", "custo_moeda_evidencia": "observed", "cliques": cliques,
         "receita_micros": receita, "receita_moeda": "USD", "receita_moeda_evidencia": "attested",
         "receita_status": receita_status or ("observed" if receita is not None else "missing"), "maduro": maduro, "disponivel_em": AS_OF.isoformat()}
    d.update(extra)
    return d


# --------------------------------------------------------------------------- fix 1: custo nunca filtrado pela receita
def test_ledger_custo_inclui_dia_maduro_sem_receita_e_cobertura_e_parcial():
    linhas = [linha("2026-10-01", 10_000_000, 10, 2_000_000), linha("2026-10-02", 10_000_000, 10, 2_000_000), linha("2026-10-03", 10_000_000, 10, 2_000_000),
              linha("2026-10-04", 90_000_000, 100, None)]  # dia caro, maduro, receita missing
    e = de_ledger_campanha_dia("cand-1", linhas, as_of=AS_OF, cambio=CAMBIO, revshare=REVSHARE, perda_maxima=PERDA)
    assert e.custo.valor == Dinheiro(120_000_000, "BRL") and e.cliques.valor == 130
    assert e.receita.valor == Dinheiro(6_000_000, "USD") and e.receita.evidencia is Evidencia.RECONCILED
    j = e.janela
    assert j.dias_maduros == 4 and j.dias_custo_maduro == 4 and j.dias_receita_madura == 3 and j.dias_custo_sem_receita == 1
    assert j.cobertura_receita_ppm == 750_000
    assert "dias_com_custo_sem_receita=1" in e.flags_qualidade


def test_ledger_imaturos_nao_entram_e_contam_na_janela():
    linhas = [linha("2026-10-01", 30_000_000, 40, 2_000_000), linha("2026-10-03", 10_000_000, 10, 500_000, receita_status="partial", maduro=False)]
    e = de_ledger_campanha_dia("cand-1", linhas, as_of=AS_OF, vertical="v", pais="BR", cambio=CAMBIO, revshare=REVSHARE, perda_maxima=PERDA)
    assert e.custo.valor == Dinheiro(30_000_000, "BRL") and e.cliques.valor == 40
    assert e.receita.valor == Dinheiro(2_000_000, "USD") and e.receita.moeda_evidencia is Evidencia.ATTESTED
    assert e.janela.dias_maduros == 1 and e.janela.dias_imaturos == 1 and e.janela.cobertura_receita_ppm == 1_000_000
    assert e.perda_maxima.informada() and e.perda_maxima.autorizacao == AUT and e.cambio.versao == "ptax-2026-10-01" and len(e.cambio.hash) == 64


def test_ledger_sem_dias_maduros_da_receita_ausente_nao_zero():
    linhas = [linha("2026-10-01", 30_000_000, 40, None)]
    e = de_ledger_campanha_dia("cand-1", linhas, as_of=AS_OF)
    assert e.receita.valor is None and e.receita.evidencia is Evidencia.ABSENT
    assert e.custo.valor == Dinheiro(30_000_000, "BRL")
    assert e.janela.dias_receita_madura == 0 and e.janela.cobertura_receita_ppm == 0


def test_ledger_sem_linha_madura_com_custo_da_custo_ausente_e_cobertura_desconhecida():
    e = de_ledger_campanha_dia("cand-1", [linha("2026-10-03", 10_000_000, 10, 500_000, receita_status="partial", maduro=False)], as_of=AS_OF)
    assert e.custo.valor is None and e.custo.evidencia is Evidencia.ABSENT and e.cliques.valor is None
    assert e.janela.dias_custo_maduro == 0 and e.janela.cobertura_receita_ppm is None


# --------------------------------------------------------------------------- fix 2: sem `or 0`
def test_ledger_cliques_ausente_num_dia_com_custo_vira_unknown_nao_zero():
    linhas = [linha("2026-10-01", 10_000_000, 10, 1_000_000), linha("2026-10-02", 10_000_000, None, 1_000_000)]
    e = de_ledger_campanha_dia("cand-1", linhas, as_of=AS_OF)
    assert e.custo.valor == Dinheiro(20_000_000, "BRL")
    assert e.cliques.valor is None and e.cliques.evidencia is Evidencia.UNKNOWN
    assert "cliques_ausentes_em_dias_com_custo=1" in e.cliques.flags_qualidade


# --------------------------------------------------------------------------- fix 3: moedas heterogêneas
def test_ledger_moedas_heterogeneas_no_custo_ou_na_receita_sao_recusadas():
    with pytest.raises(ContratoViabilidadeViolado, match="moedas_heterogeneas"):
        de_ledger_campanha_dia("c", [linha("2026-10-01", 1, 1, 1), linha("2026-10-02", 1, 1, 1, custo_moeda="USD")], as_of=AS_OF)
    with pytest.raises(ContratoViabilidadeViolado, match="moedas_heterogeneas"):
        de_ledger_campanha_dia("c", [linha("2026-10-01", 1, 1, 1), linha("2026-10-02", 1, 1, 1, receita_moeda="BRL")], as_of=AS_OF)


# --------------------------------------------------------------------------- R7: moeda nunca é assumida
def test_ledger_sem_moeda_em_nenhuma_linha_nao_assume_brl_nem_usd():
    linhas = [linha("2026-10-01", 10_000_000, 10, 1_000_000, custo_moeda=None, receita_moeda=None),
              linha("2026-10-02", 10_000_000, 10, 1_000_000, custo_moeda=None, receita_moeda=None)]
    e = de_ledger_campanha_dia("c", linhas, as_of=AS_OF)
    # custo sem moeda não é somável: nada de BRL por padrão
    assert e.custo.valor is None and e.custo.evidencia is Evidencia.UNKNOWN and e.custo.moeda_evidencia is Evidencia.UNKNOWN
    assert "moeda_ausente" in e.custo.flags_qualidade
    # receita idem: nada de USD por padrão
    assert e.receita.valor is None and e.receita.evidencia is Evidencia.UNKNOWN and e.receita.moeda_evidencia is Evidencia.UNKNOWN
    assert "moeda_ausente" in e.receita.flags_qualidade and "moeda_ausente" in e.flags_qualidade
    # a contagem de cliques e os dias continuam reais (não dependem de moeda)
    assert e.cliques.valor == 20 and e.janela.dias_maduros == 2 and e.janela.dias_receita_madura == 2
    # o par do câmbio nunca é inventado
    assert e.cambio.evidencia is Evidencia.ABSENT and e.cambio.proveniencia == "moeda_desconhecida" and e.cambio.de == "" and e.cambio.para == ""


def test_ledger_so_custo_sem_moeda_rebaixa_so_o_custo():
    linhas = [linha("2026-10-01", 10_000_000, 10, 1_000_000, custo_moeda=None), linha("2026-10-02", 10_000_000, 10, 1_000_000, custo_moeda=None)]
    e = de_ledger_campanha_dia("c", linhas, as_of=AS_OF)
    assert e.custo.valor is None and e.custo.evidencia is Evidencia.UNKNOWN and "moeda_ausente" in e.custo.flags_qualidade
    assert e.receita.valor == Dinheiro(2_000_000, "USD") and "moeda_ausente" not in e.receita.flags_qualidade
    assert e.cambio.evidencia is Evidencia.ABSENT and e.cambio.proveniencia == "moeda_desconhecida"


def test_ledger_linha_com_valor_sem_moeda_enquanto_outras_declaram_e_recusada():
    with pytest.raises(ContratoViabilidadeViolado, match="moeda_ausente_em_linha em custo"):
        de_ledger_campanha_dia("c", [linha("2026-10-01", 1, 1, 1), linha("2026-10-02", 1, 1, 1, custo_moeda=None)], as_of=AS_OF)
    with pytest.raises(ContratoViabilidadeViolado, match="moeda_ausente_em_linha em receita"):
        de_ledger_campanha_dia("c", [linha("2026-10-01", 1, 1, 1), linha("2026-10-02", 1, 1, 1, receita_moeda=None)], as_of=AS_OF)
    # moeda declarada só em linha SEM valor, e ausente na linha COM valor: também é ausência em linha (a moeda existe no ledger)
    with pytest.raises(ContratoViabilidadeViolado, match="moeda_ausente_em_linha em receita"):
        de_ledger_campanha_dia("c", [linha("2026-10-01", 1, 1, None, receita_moeda="USD"), linha("2026-10-02", 1, 1, 1, receita_moeda=None)], as_of=AS_OF)


def test_ledger_receita_sem_valor_nao_precisa_de_moeda():
    linhas = [linha("2026-10-01", 1, 1, 1), linha("2026-10-02", 1, 1, None, receita_moeda=None)]
    e = de_ledger_campanha_dia("c", linhas, as_of=AS_OF)
    assert e.receita.valor == Dinheiro(1, "USD") and e.janela.dias_custo_sem_receita == 1


def test_cambio_nunca_inventa_o_par():
    sem_par = {k: v for k, v in CAMBIO.items() if k not in ("de", "para")}
    sem_moeda = [linha("2026-10-01", 1, 1, 1, custo_moeda=None, receita_moeda=None)]
    # taxa sem par e sem moedas nas linhas: não se sabe o que converte → câmbio ausente, nunca "USD→BRL"
    c = de_ledger_campanha_dia("c", sem_moeda, as_of=AS_OF, cambio=sem_par).cambio
    assert c.taxa is None and c.evidencia is Evidencia.ABSENT and c.proveniencia == "moeda_desconhecida" and (c.de, c.para) == ("", "")
    # sem dict de câmbio e sem moedas: idem
    c = de_ledger_campanha_dia("c", sem_moeda, as_of=AS_OF, cambio=None).cambio
    assert c.taxa is None and c.proveniencia == "moeda_desconhecida" and (c.de, c.para) == ("", "")
    # Mesmo com moedas conhecidas nas linhas, uma taxa sem par continua ambígua:
    # o ledger não pode completar silenciosamente o contrato da cotação.
    c = de_ledger_campanha_dia("c", [linha("2026-10-01", 1, 1, 1)], as_of=AS_OF, cambio=sem_par).cambio
    assert c.taxa is None and c.evidencia is Evidencia.ABSENT and (c.de, c.para) == ("", "")
    # dict com par explícito: vale mesmo sem moedas nas linhas
    c = de_ledger_campanha_dia("c", sem_moeda, as_of=AS_OF, cambio=CAMBIO).cambio
    assert c.taxa == Decimal("5.25") and (c.de, c.para) == ("USD", "BRL")
    # só UMA moeda conhecida: ainda não há par
    c = de_ledger_campanha_dia("c", [linha("2026-10-01", 1, 1, 1, receita_moeda=None)], as_of=AS_OF, cambio=sem_par).cambio
    assert c.taxa is None and c.proveniencia == "moeda_desconhecida"


def test_pautador_card_exige_moeda_sem_padrao():
    with pytest.raises(TypeError, match="moeda"):
        de_pautador_card({"id": "card-65"}, as_of=AS_OF)  # type: ignore[call-arg]
    e = de_pautador_card({"id": "card-65"}, as_of=AS_OF, moeda="USD")
    assert (e.cambio.de, e.cambio.para) == ("USD", "USD")


# --------------------------------------------------------------------------- fix 4: evidência por linha preservada
def test_ledger_evidencia_agregada_e_a_mais_fraca_flags_uniao_observado_mais_antigo_fonte_propagada():
    antigo, recente = AS_OF - timedelta(days=5), AS_OF - timedelta(days=1)
    linhas = [linha("2026-10-01", 10_000_000, 10, 1_000_000, observado_em=recente.isoformat(), flags=["a"]),
              linha("2026-10-02", 10_000_000, 10, 1_000_000, status="projected", receita_status="projected", observado_em=antigo.isoformat(), flags=["b"], receita_moeda_evidencia="unknown"),
              linha("2026-10-03", 10_000_000, 10, 1_000_000, custo_evidencia="estimated")]
    e = de_ledger_campanha_dia("c", linhas, as_of=AS_OF, fonte_custo="google_ads_api", fonte_receita="joinads_csv")
    # linha 2 é projetada (status da linha) e a 3 estimada: o agregado fica com a MAIS FRACA (projected)
    assert e.custo.evidencia is Evidencia.PROJECTED and e.custo.observado_em == antigo and e.custo.fonte == "google_ads_api"
    assert e.cliques.evidencia is Evidencia.PROJECTED and e.cliques.valor == 30
    # a receita projetada não compõe a receita realizada (status fora de {observed, zero_confirmed}) e vira dia sem receita
    assert e.receita.valor == Dinheiro(2_000_000, "USD") and e.receita.fonte == "joinads_csv"
    assert e.receita.moeda_evidencia is Evidencia.ATTESTED and e.janela.dias_receita_madura == 2 and e.janela.dias_custo_sem_receita == 1
    assert {"a", "b"} <= set(e.custo.flags_qualidade) and set(e.flags_qualidade) >= {"a", "b", "dias_com_custo_sem_receita=1"}


def test_ledger_receita_com_evidencia_de_moeda_mais_fraca_rebaixa_o_agregado():
    linhas = [linha("2026-10-01", 1, 1, 1, receita_moeda_evidencia="observed"), linha("2026-10-02", 1, 1, 1, receita_moeda_evidencia="attested")]
    assert de_ledger_campanha_dia("c", linhas, as_of=AS_OF).receita.moeda_evidencia is Evidencia.ATTESTED


# --------------------------------------------------------------------------- fix 5: datas duplicadas
def test_ledger_datas_duplicadas_nao_inflam_dias_e_ficam_com_a_versao_mais_recente():
    cedo, tarde = (AS_OF - timedelta(days=2)).isoformat(), (AS_OF - timedelta(days=1)).isoformat()
    linhas = [linha("2026-10-01", 10_000_000, 10, 1_000_000, disponivel_em=tarde), linha("2026-10-01", 99_000_000, 99, 9_000_000, disponivel_em=cedo),
              linha("2026-10-02", 10_000_000, 10, 1_000_000, disponivel_em=cedo)]
    e = de_ledger_campanha_dia("c", linhas, as_of=AS_OF)
    assert e.janela.dias_maduros == 2 and e.custo.valor == Dinheiro(20_000_000, "BRL") and e.cliques.valor == 20
    assert "datas_duplicadas=1" in e.flags_qualidade
    assert e.custo.disponivel_em.isoformat() == tarde


# --------------------------------------------------------------------------- fix 6: parâmetros versionados
def test_ledger_parametros_versionados_hash_verificado_e_lookahead_recusado():
    e = de_ledger_campanha_dia("c", [linha("2026-10-01", 1, 1, 1)], as_of=AS_OF, cambio=CAMBIO, revshare=REVSHARE, imposto={**REVSHARE, "valor": "0.1"})
    assert e.cambio.effective_at == EFETIVO and e.revshare.versao == "contrato-v3" and e.imposto.valor == Decimal("0.1")
    assert de_ledger_campanha_dia("c", [linha("2026-10-01", 1, 1, 1)], as_of=AS_OF, cambio={**CAMBIO, "hash": e.cambio.hash}).cambio == e.cambio
    with pytest.raises(ContratoViabilidadeViolado, match="hash"):
        de_ledger_campanha_dia("c", [linha("2026-10-01", 1, 1, 1)], as_of=AS_OF, cambio={**CAMBIO, "hash": "0" * 64})
    depois = (AS_OF + timedelta(hours=1)).isoformat()
    with pytest.raises(ContratoViabilidadeViolado, match="cambio.disponivel_em"):
        de_ledger_campanha_dia("c", [linha("2026-10-01", 1, 1, 1)], as_of=AS_OF, cambio={**CAMBIO, "disponivel_em": depois})
    with pytest.raises(ContratoViabilidadeViolado, match="revshare.disponivel_em"):
        de_ledger_campanha_dia("c", [linha("2026-10-01", 1, 1, 1)], as_of=AS_OF, revshare={**REVSHARE, "disponivel_em": depois})
    with pytest.raises(ContratoViabilidadeViolado, match="effective_at"):
        de_ledger_campanha_dia("c", [linha("2026-10-01", 1, 1, 1)], as_of=AS_OF, cambio={k: v for k, v in CAMBIO.items() if k != "effective_at"})


def test_ledger_perda_maxima_so_com_autorizacao():
    e = de_ledger_campanha_dia("c", [linha("2026-10-01", 1, 1, 1)], as_of=AS_OF, perda_maxima=PERDA)
    assert e.perda_maxima.informada() and e.perda_maxima.autorizacao.hash == AUT.hash
    with pytest.raises(ContratoViabilidadeViolado, match="autoriza"):
        de_ledger_campanha_dia("c", [linha("2026-10-01", 1, 1, 1)], as_of=AS_OF,
                               perda_maxima={"valor": {"micros": 300_000_000, "moeda": "BRL"}, "horizonte_dias": 14, "proveniencia": "owner"})
    with pytest.raises(ContratoViabilidadeViolado, match="autoriza"):
        de_ledger_campanha_dia("c", [linha("2026-10-01", 1, 1, 1)], as_of=AS_OF, perda_maxima={"valor": {"micros": 300_000_000, "moeda": "BRL"}, "horizonte_dias": 14})
    with pytest.raises(ContratoViabilidadeViolado, match="hash"):
        de_ledger_campanha_dia("c", [linha("2026-10-01", 1, 1, 1)], as_of=AS_OF, perda_maxima={**PERDA, "autorizacao": {**AUT.para_json(), "hash": "0" * 64}})
    assert not de_ledger_campanha_dia("c", [linha("2026-10-01", 1, 1, 1)], as_of=AS_OF, perda_maxima=None).perda_maxima.informada()


# --------------------------------------------------------------------------- outros adapters (V1 mantidos)
def test_campaign_simulation_gaql_mapeia_cpc_bid_points():
    linha_ = {"campaign_simulation": {"type": "CPC_BID", "cpc_bid_point_list": {"points": [
        {"cpcBidMicros": "100000", "clicks": 1000, "costMicros": "80000000", "impressions": 50000, "biddableConversions": 10.0},
        {"cpcBidMicros": "150000", "clicks": 1200, "costMicros": "120000000"},
    ]}}}
    s = de_campaign_simulation_gaql(linha_, moeda="BRL", disponivel_em=AS_OF, estrategia_lance="MANUAL_CPC")
    assert s.tipo == "CPC_BID" and [p.modificacao_micros for p in s.pontos] == [100_000, 150_000]
    assert s.pontos[0].conversoes == Decimal("10.0") and s.pontos[1].conversoes is None and s.cambio is None


def test_campaign_simulation_tipo_sem_pontos_vira_simulacao_vazia_nao_erro():
    s = de_campaign_simulation_gaql({"campaign_simulation": {"type": "TARGET_ROAS"}}, moeda="BRL", disponivel_em=AS_OF)
    assert s.tipo == "TARGET_ROAS" and s.pontos == ()


def test_keyword_planner_vira_intervalo_de_cpc_de_pesquisa():
    cpc = de_pesquisa_keyword_planner({"low_top_of_page_bid_micros": 300_000, "high_top_of_page_bid_micros": 900_000}, moeda="BRL")
    assert cpc == (Dinheiro(300_000, "BRL"), Dinheiro(900_000, "BRL"))


def test_joinads_campanha_dia_marca_moeda_atestada_por_padrao():
    m = de_joinads_campanha_dia([{"dia": "2026-10-01", "earnings_micros": 1_000_000, "status": "observed"}], moeda="USD", moeda_evidencia="attested", disponivel_em=AS_OF)
    assert m.valor == Dinheiro(1_000_000, "USD") and m.moeda_evidencia is Evidencia.ATTESTED


# --------------------------------------------------------------------------- fix 7: fronteira Pautador/Bia
def test_pautador_card_sem_historico_so_pesquisa_e_tolerancia_com_autorizacao_ref():
    e = de_pautador_card({"id": "card-65", "vertical": "financas", "pais": "BR"}, as_of=AS_OF, moeda="BRL",
                         cpc_intervalo=(Dinheiro(300_000, "BRL"), Dinheiro(600_000, "BRL")), rpc_intervalo=None,
                         autorizacao_ref=AUT, perda_maxima_valor=Dinheiro(300_000_000, "BRL"), perda_maxima_horizonte_dias=14)
    assert e.custo.valor is None and e.receita.valor is None and e.cliques.valor is None
    assert e.cpc_intervalo is not None and e.rpc_intervalo is None
    assert e.perda_maxima.informada() and e.perda_maxima.autorizacao == AUT and e.janela.dias_custo_maduro == 0


def test_pautador_card_sem_autorizacao_nao_tem_tolerancia_e_com_valor_sem_ref_e_recusado():
    e = de_pautador_card({"id": "card-65"}, as_of=AS_OF, moeda="BRL", autorizacao_ref=None)
    assert not e.perda_maxima.informada()
    with pytest.raises(ContratoViabilidadeViolado, match="autoriza"):
        de_pautador_card({"id": "card-65"}, as_of=AS_OF, moeda="BRL", autorizacao_ref=None, perda_maxima_valor=Dinheiro(1, "BRL"), perda_maxima_horizonte_dias=1)


@pytest.mark.parametrize("campo", ["perda_maxima", "cambio", "revshare", "imposto", "tolerancia", "orcamento", "lance", "autorizacao"])
def test_bia_nao_pode_definir_nada_financeiro_nem_passar_autorizacao(campo):
    base = de_pautador_card({"id": "card-65"}, as_of=AS_OF, moeda="BRL", autorizacao_ref=AUT, perda_maxima_valor=Dinheiro(300_000_000, "BRL"), perda_maxima_horizonte_dias=14)
    with pytest.raises(BiaNaoPodeDefinirFinanceiro):
        requisicao_bia(base, {campo: AUT.para_json() if campo == "autorizacao" else {"x": 1}})
    r = requisicao_bia(base, {"motivo": "pergunta do operador"})
    assert r.entrada == base and r.somente_leitura is True and r.pode_executar is False
