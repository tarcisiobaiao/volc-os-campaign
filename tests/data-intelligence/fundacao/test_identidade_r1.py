"""Respostas à revisão adversarial R1 (F5, F6, F18, F19, F23, F20/M13) — cada teste falhava antes.

Valores sintéticos (F25): conta 1000000001, campanha 20000000011, domínios `site-a.exemplo`/`site-b.exemplo`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from fractions import Fraction

import pytest

from volc_dil.contracts.money import Dinheiro
from volc_dil.contracts.vocab import EstadoMedida
from volc_dil.fundacao.identidade import (
    CampanhaRegistrada,
    ContratoDeEntrada,
    CustoCampanhaDia,
    EventoSensorReady,
    FuturoNaJuncao,
    GraoMistoNaReceita,
    LinhaDuplicada,
    MotivoRecusa,
    OrigemValor,
    ReceitaChaveDia,
    ReceitaDominioDia,
    RegistroCampanhas,
    TemplateCampanha,
    UtmSessao,
    detectar_custom_key_substituida,
    interpretar_campanha_da_sessao,
    interpretar_chave_campanha,
    juntar_campanha_dia,
)

CONTA, CAMP = "1000000001", "20000000011"
D = date(2026, 10, 14)
AS_OF = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
LIDO = datetime(2026, 10, 15, 9, tzinfo=timezone.utc)
SITE_A, SITE_B = "site-a.exemplo", "site-b.exemplo"
REG = RegistroCampanhas([CampanhaRegistrada(CONTA, CAMP, "CAMPANHA-SINTETICA", date(2026, 1, 1), hosts=(SITE_A,))])


def usd(m):
    return Dinheiro(m, "USD")


def kv(micros, *, value=CAMP, key="utm_campaign", endpoint="key_value_campaign_adunit",
       grao="campaign_adunit_day", dimensao=("unidade-1",), dominio=SITE_A, dia=D, disponivel_em=LIDO,
       estado=EstadoMedida.MEDIDO):
    return ReceitaChaveDia(dia, dominio, endpoint, grao, key, value,
                           usd(micros) if micros is not None else None, estado, dimensao, disponivel_em)


def custo(cliques=5, estado=EstadoMedida.MEDIDO, camp=CAMP, valor=3_000_000):
    return CustoCampanhaDia(CONTA, camp, D, Dinheiro(valor, "BRL"), cliques, estado)


# ---------------------------------------------------------------- F5: identidade de linha da receita

def test_f5_mesmo_dinheiro_em_dois_cortes_e_grao_misto_recusado():
    a = kv(1_000_000)
    b = kv(1_000_000, endpoint="key_value_country_adunit", grao="campaign_country_adunit_day",
           dimensao=("BR", "unidade-1"))
    with pytest.raises(GraoMistoNaReceita):
        juntar_campanha_dia([custo()], [], [a, b], REG, as_of=AS_OF)


def test_f5_linha_duplicada_recusada():
    with pytest.raises(LinhaDuplicada):
        juntar_campanha_dia([custo()], [], [kv(1_000_000), kv(1_000_000)], REG, as_of=AS_OF)


def test_f5_duplicata_com_espaco_na_chave_tambem_e_duplicata():
    with pytest.raises(LinhaDuplicada):
        juntar_campanha_dia([], [], [kv(1), kv(1, key=" utm_campaign ", value=f" {CAMP} ")], REG, as_of=AS_OF)


def test_f5_soma_legitima_dentro_de_um_grao():
    r = juntar_campanha_dia([custo()], [], [kv(400_000), kv(600_000, dimensao=("unidade-2",))], REG, as_of=AS_OF)
    assert r.linhas[0].receita.valor == usd(1_000_000)


def test_f5_custo_duplicado_recusado():
    with pytest.raises(LinhaDuplicada):
        juntar_campanha_dia([custo(), custo()], [], [], REG, as_of=AS_OF)


def test_f5_earnings_duplicado_recusado():
    rd = [ReceitaDominioDia(D, SITE_A, usd(1)), ReceitaDominioDia(D, "www." + SITE_A, usd(1))]
    with pytest.raises(LinhaDuplicada):
        juntar_campanha_dia([], [], [kv(1)], REG, as_of=AS_OF, receitas_dominio=rd)


def test_f5_dimensao_incoerente_com_grao_recusada():
    with pytest.raises(ContratoDeEntrada):
        juntar_campanha_dia([], [], [kv(1, dimensao=())], REG, as_of=AS_OF)
    with pytest.raises(ContratoDeEntrada):
        juntar_campanha_dia([], [], [kv(1, grao="url_day", dimensao=())], REG, as_of=AS_OF)


def test_f5_contrato_as_of_estado_nao_fluxo():
    with pytest.raises(TypeError):
        juntar_campanha_dia([], [], [kv(1)], REG)  # as_of é obrigatório
    with pytest.raises(ContratoDeEntrada):
        juntar_campanha_dia([], [], [kv(1, disponivel_em=None)], REG, as_of=AS_OF)
    with pytest.raises(FuturoNaJuncao):
        juntar_campanha_dia([], [], [kv(1, disponivel_em=AS_OF + timedelta(seconds=1))], REG, as_of=AS_OF)
    ev = EventoSensorReady("s", "p", AS_OF + timedelta(minutes=1), UtmSessao(), host=SITE_A)
    with pytest.raises(FuturoNaJuncao):
        juntar_campanha_dia([], [ev], [], REG, as_of=AS_OF)
    with pytest.raises(ContratoDeEntrada):
        juntar_campanha_dia([], [], [], REG, as_of=datetime(2026, 10, 16))  # as_of sem fuso


# ---------------------------------------------------------------- F6: null≠zero e matriz

def test_f6_cliques_none_nunca_vira_zero():
    r = juntar_campanha_dia([custo(cliques=None)], [], [], REG, as_of=AS_OF)
    assert r.linhas[0].cliques.estado is EstadoMedida.NAO_COLETADO and r.linhas[0].cliques.valor is None


def test_f6_matriz_manda_sessoes_campanha_dia_nao_atribuivel_hoje():
    ev = EventoSensorReady("s", "p", datetime(2026, 10, 14, 15, tzinfo=timezone.utc),
                           UtmSessao(source="google", medium="cpc", paid=1), host=SITE_A)
    r = juntar_campanha_dia([custo()], [ev], [], REG, as_of=AS_OF)
    s = r.linhas[0].sessoes
    assert s.estado is EstadoMedida.NAO_ATRIBUIVEL and s.valor is None and "matriz" in s.motivo


def test_f6_zero_de_sessao_so_com_sensor_no_host_da_campanha():
    reg = RegistroCampanhas([
        CampanhaRegistrada(CONTA, "31", "alfa", date(2026, 1, 1), template=TemplateCampanha.NOME, hosts=(SITE_B,))])
    organico_em_a = EventoSensorReady("s", "p", datetime(2026, 10, 14, 15, tzinfo=timezone.utc), UtmSessao(), host=SITE_A)
    r = juntar_campanha_dia([custo(camp="31")], [organico_em_a], [], reg, as_of=AS_OF, trafego_campanha_comprovado=True)
    assert r.linhas[0].sessoes.estado is EstadoMedida.AUSENTE
    organico_em_b = EventoSensorReady("s2", "p2", datetime(2026, 10, 14, 15, tzinfo=timezone.utc), UtmSessao(),
                                      host="www." + SITE_B)
    r2 = juntar_campanha_dia([custo(camp="31")], [organico_em_b], [], reg, as_of=AS_OF, trafego_campanha_comprovado=True)
    assert r2.linhas[0].sessoes.estado is EstadoMedida.ZERO_CONFIRMADO


def test_f6_campanha_sem_host_declarado_nao_tem_zero():
    reg = RegistroCampanhas([CampanhaRegistrada(CONTA, "31", "alfa", date(2026, 1, 1), template=TemplateCampanha.NOME)])
    ev = EventoSensorReady("s", "p", datetime(2026, 10, 14, 15, tzinfo=timezone.utc), UtmSessao(), host=SITE_A)
    r = juntar_campanha_dia([custo(camp="31")], [ev], [], reg, as_of=AS_OF, trafego_campanha_comprovado=True)
    assert r.linhas[0].sessoes.estado is EstadoMedida.AUSENTE


# ---------------------------------------------------------------- F18: surrogate no limite

def test_f18_surrogate_cortado_no_limite_nao_derruba():
    partido = "x" * 39 + "\ud83c"  # o que o sensor grava para 'x'*39 + emoji
    ch = interpretar_chave_campanha(partido, OrigemValor.SENSOR_V3)
    assert ch.recusa is MotivoRecusa.POSSIVELMENTE_TRUNCADO
    reg = RegistroCampanhas([CampanhaRegistrada(CONTA, "31", "x" * 39 + "🎓", date(2026, 1, 1),
                                                template=TemplateCampanha.NOME, hosts=(SITE_A,))])
    ev = EventoSensorReady("s", "p", datetime(2026, 10, 14, 15, tzinfo=timezone.utc),
                           UtmSessao(campaign=partido), host=SITE_A)
    r = juntar_campanha_dia([custo(camp="31")], [ev], [], reg, as_of=AS_OF, trafego_campanha_comprovado=True)
    assert r.cobertura.sessoes_resolvidas == 0
    assert interpretar_campanha_da_sessao(partido, paid=0, source=None, medium=None).recusa \
        is MotivoRecusa.POSSIVELMENTE_TRUNCADO


# ---------------------------------------------------------------- F19: universos do denominador

def test_f19_dominio_sem_kv_coletado_nao_conta_como_sem_chave():
    rd = [ReceitaDominioDia(D, SITE_A, usd(10_000_000)), ReceitaDominioDia(D, SITE_B, usd(90_000_000))]
    r = juntar_campanha_dia([], [], [kv(10_000_000)], REG, as_of=AS_OF, receitas_dominio=rd)
    c = r.cobertura
    assert c.fracao_receita_com_chave == Fraction(1)
    assert c.receita_sem_chave == usd(0)
    assert c.receita_earnings_sem_kv == usd(90_000_000)
    assert any("sem /key-value coletado" in a for a in c.avisos)


def test_f19_kv_sem_earnings_fica_fora_e_avisa():
    rd = [ReceitaDominioDia(D, SITE_A, usd(10_000_000))]
    r = juntar_campanha_dia([], [], [kv(8_000_000), kv(5_000_000, dominio=SITE_B)], REG, as_of=AS_OF,
                            receitas_dominio=rd)
    c = r.cobertura
    assert c.fracao_receita_com_chave == Fraction(8, 10)
    assert c.receita_kv_sem_earnings == usd(5_000_000)
    assert any("sem /earnings" in a for a in c.avisos)


def test_f19_universo_kv_explicito_inclui_dominio_coletado_e_vazio():
    # site-b teve /key-value coletado e voltou vazio: aí sim a receita dele é "sem chave"
    rd = [ReceitaDominioDia(D, SITE_A, usd(10_000_000)), ReceitaDominioDia(D, SITE_B, usd(90_000_000))]
    r = juntar_campanha_dia([], [], [kv(10_000_000)], REG, as_of=AS_OF, receitas_dominio=rd,
                            dominios_dia_kv_coletados={(D, SITE_A), (D, SITE_B)})
    assert r.cobertura.fracao_receita_com_chave == Fraction(1, 10)
    assert r.cobertura.receita_earnings_sem_kv is None


# ---------------------------------------------------------------- F23 e M13: custon_key / strip

def test_f23_custon_key_quando_custom_key_e_null():
    cols = detectar_custom_key_substituida([{"custom_key": None, "custon_key": "land_uri"}])
    assert [c.envolvidos for c in cols] == [("land_uri",)]


def test_m13_custom_key_com_espacos_nao_e_substituicao():
    assert detectar_custom_key_substituida([{"custom_key": " utm_campaign ", "custom_value": CAMP}]) == []
    assert detectar_custom_key_substituida([{"custom_key": "utm_campaign\t"}]) == []
    assert interpretar_chave_campanha(CAMP, OrigemValor.JOINADS, custom_key=" utm_campaign ").campaign_id == CAMP
