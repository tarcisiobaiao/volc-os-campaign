"""Simulator Lab — determinismo, mundos pareados (CRN) e contrafactual de orçamento."""
from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

import numpy as np
import pytest

from volc_dil.contracts.fingerprint import json_canonico, sha256_de
from volc_dil.fundacao.simulador import cenario, catalogo_sha256, gerar_mundo, simular
from volc_dil.fundacao.simulador.pacote import conteudo_cenario

SEED = 20261016


def _bytes(sim) -> str:
    L = sim.leituras
    corpo = {
        "registros": [r.como_dict() for r in L.registros],
        "gabarito": [L.gabarito[r.obs_id].como_dict() for r in L.registros],
        "execucoes": L.execucoes,
        "diaria": sim.mundo.tabela_diaria(),
        "campanhas": sim.mundo.tabela_campanhas(),
    }
    return sha256_de(corpo)


@lru_cache(maxsize=None)
def _sim(nome: str, seed: int = SEED):
    return simular(nome, seed, n_campanhas=8, n_dias=14)


@pytest.mark.parametrize("nome", ["estavel", "identidade_trocada", "gatilho_legado_joinads", "fonte_fora_do_ar"])
def test_mesma_seed_mesmos_bytes(nome):
    a = _bytes(_sim(nome))
    b = _bytes(simular(nome, SEED, n_campanhas=8, n_dias=14))
    assert a == b


def test_seeds_diferentes_mundos_diferentes():
    a, b = _sim("estavel", SEED), _sim("estavel", SEED + 1)
    assert _bytes(a) != _bytes(b)
    assert not np.array_equal(a.mundo.diario("custo_final_micros"), b.mundo.diario("custo_final_micros"))


def test_pacote_bytes_identicos_em_duas_geracoes():
    a = conteudo_cenario("zero_falso", SEED, (4, 7))
    b = conteudo_cenario("zero_falso", SEED, (4, 7))
    assert a == b
    assert json_canonico(sorted(a)) == json_canonico(sorted(b))


def test_mundos_pareados_so_diferem_no_que_o_cenario_injeta():
    base, bot = _sim("estavel"), _sim("outlier_bot")
    # mesmo acaso para tudo que não é bot: impressões e cliques humanos idênticos
    assert np.array_equal(base.mundo.horario("impressoes"), bot.mundo.horario("impressoes"))
    humano_base = base.mundo.horario("cliques") - base.mundo.horario("cliques_bot")
    humano_bot = bot.mundo.horario("cliques") - bot.mundo.horario("cliques_bot")
    assert np.array_equal(humano_base, humano_bot)
    assert bot.mundo.horario("cliques_bot").sum() > 0 and base.mundo.horario("cliques_bot").sum() == 0


def test_contrafactual_orcamento_reproduz_e_responde():
    e = cenario("estavel").reduzir(n_campanhas=8, n_dias=14)
    m = gerar_mundo(e.mundo, SEED)
    orc = np.array([[c.orcamento_base_micros] * e.mundo.n_dias for c in m.campanhas], dtype=np.int64)
    igual = gerar_mundo(e.mundo, SEED, orcamento_diario_micros=orc)
    assert np.array_equal(m.horario("custo_final_micros"), igual.horario("custo_final_micros"))
    dobro = gerar_mundo(e.mundo, SEED, orcamento_diario_micros=orc * 2)
    limitadas = (m.flags["theta"] < 0.999).reshape(8, 14, 24).any(axis=2)
    assert limitadas.any()
    c_base = m.diario("custo_bruto_micros")[limitadas].sum()
    c_dobro = dobro.diario("custo_bruto_micros")[limitadas].sum()
    assert c_dobro > c_base * 1.1  # mais orçamento ⇒ mais gasto onde o orçamento limitava


def test_orcamento_override_exige_inteiro():
    e = cenario("estavel").reduzir(n_campanhas=2, n_dias=2)
    with pytest.raises(TypeError):
        gerar_mundo(e.mundo, SEED, orcamento_diario_micros=np.ones((2, 2)) * 1.5)


def test_fingerprint_do_catalogo_muda_com_parametro():
    from volc_dil.fundacao.simulador import cenarios as cen

    original = catalogo_sha256()
    assert original == catalogo_sha256()
    salvo = cen.CATALOGO["estavel"]
    try:
        cen.CATALOGO["estavel"] = replace(salvo, mundo=replace(salvo.mundo, ctr_media=0.05))
        assert catalogo_sha256() != original
    finally:
        cen.CATALOGO["estavel"] = salvo
    assert catalogo_sha256() == original
