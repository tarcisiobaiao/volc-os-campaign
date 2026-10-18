"""RED — replay com as_of fixo rejeita parâmetros vindos do futuro (lookahead).

Achado 8 da missão V2. `as_of` = 2026-10-15T12:00Z. Qualquer câmbio, taxa, autorização ou
simulação com `disponivel_em`/`effective_at` posterior ao as_of não existia no momento da
decisão e não pode entrar no replay.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from volc_dil.viability.contrato import ContratoViabilidadeViolado, Evidencia, PontoSimulacao, SimulacaoEntrada

from _entradas import AS_OF, entrada

DEPOIS = AS_OF + timedelta(days=1)


@pytest.mark.parametrize("campo", ["disponivel_em", "effective_at"])
def test_red08a_cambio_do_futuro_e_rejeitado(sobrescrever, campo):
    """Achado 8 (câmbio). Câmbio USD→BRL com `disponivel_em`/`effective_at` = as_of + 1 dia.

    V1 não tem data nenhuma em `Cambio` (falha POR CONSTRUÇÃO): um PTAX publicado depois do
    as_of entra no replay como se estivesse disponível na hora da decisão, e o `input_hash`
    não distingue os dois mundos. V2 deve datar o câmbio e recusar na construção da entrada.
    """
    e = entrada()  # receita USD, câmbio literal
    cambio_futuro = sobrescrever(e.cambio, **{campo: DEPOIS}, hash="")  # hash="" → a V2 recalcula o canon; a V1 não tem o campo
    with pytest.raises(ContratoViabilidadeViolado):
        replace(e, cambio=cambio_futuro)


@pytest.mark.parametrize("campo", ["disponivel_em", "effective_at"])
def test_red08b_taxa_revshare_do_futuro_e_rejeitada(sobrescrever, campo):
    """Achado 8 (taxa). Revshare com `disponivel_em`/`effective_at` posterior ao as_of.
    V1 não tem data em `Taxa` (falha por construção). V2 deve recusar."""
    e = entrada()
    with pytest.raises(ContratoViabilidadeViolado):
        replace(e, revshare=sobrescrever(e.revshare, **{campo: DEPOIS}, hash=""))


@pytest.mark.parametrize("campo", ["disponivel_em", "effective_at"])
def test_red08c_autorizacao_do_futuro_e_rejeitada(sobrescrever, autorizacao_v2, campo):
    """Achado 8 (autorização). `perda_maxima.autorizacao` com vigência/disponibilidade posterior
    ao as_of (hash canônico correto para a vigência informada). V1 não tem `Autorizacao`
    (falha por construção). V2 deve recusar a entrada."""
    e = entrada(perda="300", horizonte=14)
    aut = autorizacao_v2(**{campo: DEPOIS})
    with pytest.raises(ContratoViabilidadeViolado):
        replace(e, perda_maxima=sobrescrever(e.perda_maxima, autorizacao=aut))


def test_red08d_controle_simulacao_do_futuro_ja_e_rejeitada():
    """Controle (passa na V1): `SimulacaoEntrada.disponivel_em` > as_of já é recusado pela V1.
    V2 precisa manter."""
    sim = SimulacaoEntrada("CPC_BID", "BRL", (PontoSimulacao(50_000, 500, 20_000_000), PontoSimulacao(100_000, 1000, 80_000_000)), DEPOIS)
    e = entrada(receita="800", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED)
    with pytest.raises(ContratoViabilidadeViolado):
        replace(e, simulacao=sim)
