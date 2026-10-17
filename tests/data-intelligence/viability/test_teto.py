"""Teto de experimento: só a partir da tolerância do owner; nunca derivado."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction

from volc_dil.contracts import Dinheiro
from volc_dil.viability.contrato import PerdaMaxima
from volc_dil.viability.economia import Indisponivel
from volc_dil.viability.teto import TetoExperimento, calcular_teto

from _entradas import entrada


def test_sem_tolerancia_do_owner_nao_ha_teto():
    r = calcular_teto(entrada(perda=None, horizonte=None))
    assert isinstance(r, Indisponivel) and r.motivo == "perda_maxima_ausente"


def test_teto_senac_like_limita_spend_e_cliques_pela_perda_esperada_por_clique():
    t = calcular_teto(entrada(perda="300", horizonte=14))
    assert isinstance(t, TetoExperimento)
    # perda conservadora por clique = cpc_cons − rpc_cons > 0 → click_cap = perda / perda_por_clique
    assert t.perda_por_clique_conservadora > 0
    assert t.click_cap == int(Fraction(300_000_000) / t.perda_por_clique_conservadora)
    assert t.click_cap * t.perda_por_clique_conservadora <= 300_000_000  # perda esperada nunca excede a tolerância
    assert t.spend_cap.micros > 0
    assert 1 <= t.day_cap <= 14


def test_teto_menor_nunca_aumenta_spend_cap():
    a = calcular_teto(entrada(perda="300", horizonte=14))
    b = calcular_teto(entrada(perda="150", horizonte=14))
    assert b.spend_cap.micros <= a.spend_cap.micros and b.click_cap <= a.click_cap


def test_teto_favoravel_limita_pelo_spend_do_horizonte_e_volume():
    e = entrada(receita="800", moeda_receita="BRL", taxa=None, perda="300", horizonte=14)
    e2 = e.__class__(**{**e.__dict__, "volume_diario_possivel": 50})
    t = calcular_teto(e2)
    assert t.perda_por_clique_conservadora == 0
    assert t.click_cap == 50 * 14
    assert t.spend_cap.micros == int(t.click_cap * t.cpc_conservador)
    assert t.day_cap == 14


def test_teto_sem_economia_usa_so_a_perda_e_o_cpc_de_pesquisa():
    e = entrada(receita_none=True, custo_none=True, cliques=None, perda="300", horizonte=14)
    e2 = e.__class__(**{**e.__dict__, "cpc_intervalo": (Dinheiro.de_decimal("0.50", "BRL"), Dinheiro.de_decimal("1.20", "BRL"))})
    t = calcular_teto(e2)
    assert t.spend_cap == Dinheiro.de_decimal("300", "BRL")
    assert t.cpc_conservador == Fraction(1_200_000)
    assert t.click_cap == 250
    assert "rpc_desconhecido_perda_total" in t.premissas


def test_condicoes_de_parada_continuidade_e_inconclusao_sao_tipadas():
    t = calcular_teto(entrada(perda="300", horizonte=14))
    assert t.parada.gatilhos and t.continuidade.gatilhos and t.inconclusao.gatilhos
    assert t.maturity_wait_dias >= 3
