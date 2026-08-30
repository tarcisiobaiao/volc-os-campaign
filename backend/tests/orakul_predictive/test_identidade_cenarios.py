"""Identidade conta/cenário/payload e planned_spend sem alegação causal."""

from __future__ import annotations

from dataclasses import replace

import pytest

from services.orakul_predictive.adapters_memoria import InMemoryPredictionLedger
from services.orakul_predictive.constantes import (
    CENARIO_PLANNED_SPEND,
    IDENTIFICACAO_PLANNED_SPEND,
)
from services.orakul_predictive.excecoes import ConflitoDeIdempotencia, ContratoInvalido
from services.orakul_predictive.fixtures_sinteticas import serie_sintetica_a
from services.orakul_predictive.hashes import chave_idempotencia, hash_canonico, id_canonico
from services.orakul_predictive.modelos import FEATURES_OLS_REVENUE
from services.orakul_predictive.motor import prever
from services.orakul_predictive.semantica import EstadoSemantico

from .helpers import request_naive


def _request_planned(janela_fim: str, planned_spend_micros: int):
    base = request_naive(janela_fim, alvos=("spend", "revenue", "roas"))
    payload = {
        "base": base.hash_inputs,
        "cenario": CENARIO_PLANNED_SPEND,
        "planned_spend_micros": planned_spend_micros,
        "identificacao": IDENTIFICACAO_PLANNED_SPEND,
    }
    return replace(
        base,
        request_id=id_canonico("request", **payload),
        hash_inputs=hash_canonico(payload),
        chave_idempotencia=chave_idempotencia(
            kind="request",
            conta_id=base.conta_id,
            campanha_id=base.campanha_id,
            janela_fim=janela_fim,
            versao_modelo=base.versao_modelo,
            cenario=CENARIO_PLANNED_SPEND,
        ),
        cenario=CENARIO_PLANNED_SPEND,
        planned_spend_micros=planned_spend_micros,
        identificacao_cenario=IDENTIFICACAO_PLANNED_SPEND,
    )


def test_conta_e_cenario_participam_de_ids_pair_id_e_idempotencia():
    origin = "2026-07-08"
    serie_a = serie_sintetica_a()
    serie_b = tuple(replace(o, conta_id="conta-sintetica-2") for o in serie_a)
    pred_a = prever(request_naive(origin, alvos=("spend",)), serie_a)[0]
    pred_b = prever(
        request_naive(origin, alvos=("spend",), conta_id="conta-sintetica-2"),
        serie_b,
    )[0]
    assert pred_a.previsao_id != pred_b.previsao_id
    assert pred_a.chave_idempotencia != pred_b.chave_idempotencia
    assert pred_a.pair_id != pred_b.pair_id

    pred_planned = prever(_request_planned(origin, 50_000_000), serie_a)[0]
    assert pred_planned.previsao_id != pred_a.previsao_id
    assert pred_planned.chave_idempotencia != pred_a.chave_idempotencia
    assert pred_planned.pair_id != pred_a.pair_id


def test_mesma_chave_com_payload_diferente_e_conflito_nao_replay_silencioso():
    serie = serie_sintetica_a()
    req_a = request_naive("2026-07-08", alvos=("spend",))
    req_b = replace(req_a, hash_inputs=hash_canonico({"mutante": req_a.hash_inputs}))
    pred_a = prever(req_a, serie)[0]
    pred_b = prever(req_b, serie)[0]
    assert pred_a.previsao_id == pred_b.previsao_id
    assert pred_a.chave_idempotencia == pred_b.chave_idempotencia
    assert pred_a.hash_inputs != pred_b.hash_inputs

    ledger = InMemoryPredictionLedger()
    ledger.gravar(pred_a)
    with pytest.raises(ConflitoDeIdempotencia, match="payload diferente"):
        ledger.gravar(pred_b)


def test_planned_spend_e_hipotese_nao_causal_e_nao_duplica_lag0_no_ridge():
    assert "planned_spend_scenario" not in FEATURES_OLS_REVENUE
    req = _request_planned("2026-07-08", 50_000_000)
    por_alvo = {p.alvo: p for p in prever(req, serie_sintetica_a())}

    spend = por_alvo["spend"]
    assert spend.ponto_micros == 50_000_000
    assert spend.estado_semantico is EstadoSemantico.HIPOTESE
    assert spend.intervalo is None

    revenue = por_alvo["revenue"]
    assert revenue.ponto_micros is None
    assert revenue.estado_semantico is EstadoSemantico.NAO_APLICAVEL
    assert revenue.motivo_indisponivel == "efeito_causal_de_planned_spend_nao_identificado"

    roas = por_alvo["roas"]
    assert roas.ponto_micros is None
    assert roas.estado_semantico is EstadoSemantico.NAO_APLICAVEL


def test_planned_spend_sem_declarar_ausencia_de_identificacao_causal_falha():
    base = request_naive("2026-07-08", alvos=("spend",))
    with pytest.raises(ContratoInvalido, match="identificação causal"):
        replace(
            base,
            cenario=CENARIO_PLANNED_SPEND,
            planned_spend_micros=50_000_000,
            identificacao_cenario=None,
        )
