"""Idempotência do ledger de previsões."""

from __future__ import annotations

from services.orakul_predictive.adapters_memoria import InMemoryPredictionLedger
from services.orakul_predictive.fixtures_sinteticas import serie_sintetica_a
from services.orakul_predictive.motor import prever

from .helpers import request_naive


def test_gravar_duas_vezes_devolve_o_mesmo_objeto_canonico():
    serie = serie_sintetica_a()
    preds = prever(request_naive("2026-07-05"), serie)
    assert preds
    ledger = InMemoryPredictionLedger()
    a = ledger.gravar(preds[0])
    b = ledger.gravar(preds[0])
    assert a is b
    assert ledger.obter(preds[0].chave_idempotencia) is a
    assert a.chave_idempotencia == preds[0].chave_idempotencia
