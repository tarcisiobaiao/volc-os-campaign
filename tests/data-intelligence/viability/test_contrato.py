"""Contrato tipado de viabilidade: estados de evidência, dinheiro em micros, as_of obrigatório."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from volc_dil.contracts import Dinheiro
from volc_dil.viability.contrato import (
    Cambio,
    ContratoViabilidadeViolado,
    EntradaViabilidade,
    Evidencia,
    JanelaObservada,
    MedidaContagem,
    MedidaMonetaria,
    PerdaMaxima,
    Taxa,
    hash_entrada,
)

AS_OF = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


def _entrada(**sobrescreve) -> EntradaViabilidade:
    base = dict(
        candidato_id="cand-0001",
        vertical="educacao",
        pais="BR",
        fonte_custo="google_ads",
        fonte_receita="joinads",
        as_of=AS_OF,
        janela=JanelaObservada(inicio="2026-09-26", fim="2026-10-11", dias_maduros=16, dias_imaturos=3),
        cliques=MedidaContagem(valor=634, evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF),
        custo=MedidaMonetaria(valor=Dinheiro.de_decimal("554.75", "BRL"), evidencia=Evidencia.OBSERVED, moeda_evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF),
        receita=MedidaMonetaria(valor=Dinheiro.de_decimal("7.77", "USD"), evidencia=Evidencia.RECONCILED, moeda_evidencia=Evidencia.ATTESTED, disponivel_em=AS_OF),
        cambio=Cambio(taxa=Decimal("5.25"), de="USD", para="BRL", proveniencia="literal_app", evidencia=Evidencia.ESTIMATED),
        revshare=Taxa(valor=Decimal("1"), evidencia=Evidencia.ATTESTED, proveniencia="tela"),
        imposto=Taxa(valor=None, evidencia=Evidencia.UNKNOWN, proveniencia="ausente"),
        perda_maxima=PerdaMaxima(valor=Dinheiro.de_decimal("300", "BRL"), horizonte_dias=14, proveniencia="owner"),
    )
    base.update(sobrescreve)
    return EntradaViabilidade(**base)


def test_estados_de_evidencia_obrigatorios_existem():
    assert {e.value for e in Evidencia} == {
        "observed", "attested", "reconciled", "estimated", "projected", "absent", "unknown", "invalid", "immature",
    }


def test_entrada_valida_constroi():
    e = _entrada()
    assert e.custo.valor.micros == 554_750_000
    assert e.receita.moeda_evidencia is Evidencia.ATTESTED


def test_ausencia_nunca_vira_zero():
    with pytest.raises(ContratoViabilidadeViolado):
        MedidaMonetaria(valor=Dinheiro(0, "BRL"), evidencia=Evidencia.ABSENT, moeda_evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF)
    m = MedidaMonetaria(valor=None, evidencia=Evidencia.ABSENT, moeda_evidencia=Evidencia.UNKNOWN, disponivel_em=AS_OF)
    assert m.valor is None and not m.tem_valor()


def test_valor_presente_exige_evidencia_com_valor():
    with pytest.raises(ContratoViabilidadeViolado):
        MedidaMonetaria(valor=None, evidencia=Evidencia.OBSERVED, moeda_evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF)


def test_dinheiro_nao_entra_como_float():
    with pytest.raises(TypeError):
        Dinheiro.de_decimal(1.5, "BRL")  # type: ignore[arg-type]


def test_as_of_obrigatorio_e_com_timezone():
    with pytest.raises(ContratoViabilidadeViolado):
        _entrada(as_of=None)
    with pytest.raises(ContratoViabilidadeViolado):
        _entrada(as_of=datetime(2026, 10, 15, 12, 0))


def test_observacao_posterior_ao_as_of_e_recusada():
    depois = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ContratoViabilidadeViolado, match="as_of"):
        _entrada(custo=MedidaMonetaria(valor=Dinheiro(1, "BRL"), evidencia=Evidencia.OBSERVED, moeda_evidencia=Evidencia.OBSERVED, disponivel_em=depois))


def test_hash_da_entrada_e_deterministico_e_sensivel():
    a, b = _entrada(), _entrada()
    assert hash_entrada(a) == hash_entrada(b)
    c = _entrada(cliques=MedidaContagem(valor=635, evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF))
    assert hash_entrada(c) != hash_entrada(a)


def test_perda_maxima_ausente_e_representavel_sem_inventar():
    e = _entrada(perda_maxima=PerdaMaxima(valor=None, horizonte_dias=None, proveniencia="ausente"))
    assert e.perda_maxima.valor is None


def test_para_json_e_de_json_sao_inversos():
    e = _entrada()
    j = e.para_json()
    assert EntradaViabilidade.de_json(j) == e
