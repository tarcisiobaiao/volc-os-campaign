"""Ausência, zero medido, falha, N/A e antigo permanecem distintos. Ausência ≠ 0."""

from __future__ import annotations

from datetime import date, timedelta

from services.orakul_predictive.contratos import recibo_sintetico
from services.orakul_predictive.features import ObservacaoDiaria, montar_snapshot
from services.orakul_predictive.fixtures_sinteticas import CAMPANHA_A, CONTA, INSTANTE_FIXO, serie_sintetica_a
from services.orakul_predictive.motor import codigo_hash_motor, prever
from services.orakul_predictive.relogio import iso_civil, iso_instante
from services.orakul_predictive.semantica import EstadoSemantico, estado_de_valor_monetario, valor_numerico_ou_nulo

from .helpers import agora, request_naive


def test_classificacao_semantica_nao_colapsa():
    assert estado_de_valor_monetario(None, observacao_existe=False) is EstadoSemantico.AUSENTE
    assert estado_de_valor_monetario(0, observacao_existe=True) is EstadoSemantico.ZERO_MEDIDO
    assert estado_de_valor_monetario(1, observacao_existe=True) is EstadoSemantico.MEDIDO
    assert estado_de_valor_monetario(None, fonte_falhou=True) is EstadoSemantico.FALHA
    assert estado_de_valor_monetario(None, aplicavel=False) is EstadoSemantico.NAO_APLICAVEL
    assert estado_de_valor_monetario(10, observacao_existe=True, antigo=True) is EstadoSemantico.ANTIGO
    assert valor_numerico_ou_nulo(EstadoSemantico.AUSENTE, None) is None
    assert valor_numerico_ou_nulo(EstadoSemantico.ZERO_MEDIDO, 0) == 0
    assert valor_numerico_ou_nulo(EstadoSemantico.FALHA, None) is None


def test_fixture_contem_os_cinco_estados():
    serie = serie_sintetica_a()
    estados = {o.spend_estado for o in serie}
    assert EstadoSemantico.ZERO_MEDIDO in estados
    assert EstadoSemantico.FALHA in estados
    assert EstadoSemantico.ANTIGO in estados
    assert EstadoSemantico.MEDIDO in estados
    assert date(2026, 6, 16).isoformat() not in {o.civil_date for o in serie}


def test_snapshot_nao_imputa_zero_na_ausencia():
    origin = "2026-06-16"  # dia ausente na série; origin pode ser o dia 16 se... wait 16 is skipped so origin 16 isn't in series
    # origin 2026-06-17: lag0 é dia 17; precisamos origin cujo lag0 seja o dia ausente 16.
    snap = montar_snapshot(
        serie_sintetica_a(),
        campanha_id=CAMPANHA_A,
        origin="2026-06-16",
        horizonte_dias=1,
        versao_modelo="naive_persistence/v1",
        procedencia=recibo_sintetico("ausencia", agora()),
        codigo_hash=codigo_hash_motor(),
        alvo="spend",
        conta_id=CONTA,
        observado_em=agora(),
    )
    assert snap.features["spend_lag0"] is None
    assert snap.feature_estados["spend_lag0"] is EstadoSemantico.AUSENTE
    preds = prever(request_naive("2026-06-16", alvos=("spend",)), serie_sintetica_a())
    spend = preds[0]
    assert spend.ponto_micros is None
    assert spend.disponivel is False
    assert spend.estado_semantico is EstadoSemantico.AUSENTE


def test_zero_medido_e_zero_nao_ausencia():
    snap = montar_snapshot(
        serie_sintetica_a(),
        campanha_id=CAMPANHA_A,
        origin="2026-06-11",  # i=10 é 2026-06-11, zero medido
        horizonte_dias=1,
        versao_modelo="naive_persistence/v1",
        procedencia=recibo_sintetico("zero", agora()),
        codigo_hash=codigo_hash_motor(),
        alvo="spend",
        observado_em=agora(),
    )
    assert snap.features["spend_lag0"] == 0
    assert snap.feature_estados["spend_lag0"] is EstadoSemantico.ZERO_MEDIDO
    preds = prever(request_naive("2026-06-11", alvos=("spend",)), serie_sintetica_a())
    assert preds[0].ponto_micros == 0
    assert preds[0].estado_semantico is EstadoSemantico.ZERO_MEDIDO
    assert preds[0].disponivel is True
