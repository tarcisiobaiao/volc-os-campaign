"""Contraprovas exatas de cutoff intraday e estados semânticos ponta a ponta."""

from __future__ import annotations

from dataclasses import replace

import pytest

from services.orakul_predictive.avaliacao import outcome_de_observacao
from services.orakul_predictive.contratos import recibo_sintetico
from services.orakul_predictive.excecoes import ContratoInvalido
from services.orakul_predictive.features import montar_snapshot
from services.orakul_predictive.fixtures_sinteticas import (
    CAMPANHA_A,
    CONTA,
    serie_sintetica_a,
)
from services.orakul_predictive.hashes import hash_canonico
from services.orakul_predictive.motor import codigo_hash_motor, prever
from services.orakul_predictive.semantica import EstadoSemantico, valor_numerico_ou_nulo

from .helpers import agora, request_naive


def _snapshot(serie, origin: str, *, tag: str = "cutoff", cutoff_em: str | None = None):
    return montar_snapshot(
        serie,
        campanha_id=CAMPANHA_A,
        conta_id=CONTA,
        origin=origin,
        horizonte_dias=1,
        versao_modelo="naive_persistence/v1",
        procedencia=recibo_sintetico(tag, agora()),
        codigo_hash=codigo_hash_motor(),
        alvo="spend",
        observado_em=agora(),
        cutoff_em=cutoff_em,
    )


def test_revisao_intraday_posterior_ao_cutoff_nao_altera_snapshot_previsao_ou_hash():
    origin = "2026-07-08"
    base = serie_sintetica_a()
    atual = next(o for o in base if o.civil_date == origin)
    revisao_futura = replace(
        atual,
        spend_micros=atual.spend_micros + 900_000_000,
        revenue_micros=atual.revenue_micros + 900_000_000,
        # A revisão existe quando o replay roda, mas ainda não existia na
        # origem histórica. Sem vintage por origem, ela vazaria para o passado.
        lido_em="2026-07-20T12:00:00Z",
    )
    contaminada = base + (revisao_futura,)

    cutoff_origem = "2026-07-09T02:59:59Z"
    snap_base = _snapshot(base, origin, cutoff_em=cutoff_origem)
    snap_contaminada = _snapshot(contaminada, origin, cutoff_em=cutoff_origem)
    assert snap_contaminada.serializar() == snap_base.serializar()
    assert snap_contaminada.hash_inputs == snap_base.hash_inputs

    req = replace(request_naive(origin, alvos=("spend",)), cutoff_em=cutoff_origem)
    pred_base = prever(req, base)[0]
    pred_contaminada = prever(req, contaminada)[0]
    assert pred_contaminada.serializar() == pred_base.serializar()
    assert hash_canonico(pred_contaminada.serializar()) == hash_canonico(pred_base.serializar())


def test_actual_do_proprio_dia_nao_fecha_por_declaracao_do_caller():
    with pytest.raises(ContratoInvalido, match="não está fechada"):
        outcome_de_observacao(
            campanha_id=CAMPANHA_A,
            conta_id=CONTA,
            target_date="2026-08-01",
            origin_date="2026-07-31",
            alvo="spend",
            micros=1,
            estado=EstadoSemantico.MEDIDO,
            procedencia=recibo_sintetico("actual-mesmo-dia", agora()),
            observado_em="2026-08-01T12:00:00Z",
        )


def test_watermark_explicito_pode_fechar_actual_do_proprio_dia():
    outcome = outcome_de_observacao(
        campanha_id=CAMPANHA_A,
        conta_id=CONTA,
        target_date="2026-08-01",
        origin_date="2026-07-31",
        alvo="spend",
        micros=1,
        estado=EstadoSemantico.MEDIDO,
        procedencia=recibo_sintetico("actual-watermark", agora()),
        observado_em="2026-08-01T23:59:59Z",
        watermark_fechado_ate="2026-08-01",
    )
    assert outcome.fechado is True
    assert outcome.watermark_fechado_ate == "2026-08-01"


@pytest.mark.parametrize(
    ("origin", "esperado"),
    [
        ("2026-06-21", EstadoSemantico.FALHA),
        ("2026-06-26", EstadoSemantico.ANTIGO),
    ],
)
def test_falha_e_antigo_nao_viram_ausente_na_previsao(origin, esperado):
    serie = serie_sintetica_a()
    if esperado is EstadoSemantico.ANTIGO:
        # Isola o estado antigo da falha global deliberada cinco dias antes.
        serie = tuple(o for o in serie if o.civil_date != "2026-06-21")
    pred = prever(request_naive(origin, alvos=("spend",)), serie)[0]
    assert pred.ponto_micros is None
    assert pred.disponivel is False
    assert pred.estado_semantico is esperado
    assert pred.motivo_indisponivel == f"feature_origem_{esperado.value}"


def test_frescor_maior_que_36h_se_preserva_como_antigo():
    origin = "2026-07-08"
    serie = serie_sintetica_a()
    antiga = tuple(
        replace(o, lido_em="2026-07-06T12:00:00Z") if o.civil_date == origin else o
        for o in serie
    )
    snap = _snapshot(
        antiga,
        origin,
        tag="frescor",
        cutoff_em="2026-07-09T02:59:59Z",
    )
    assert snap.features["spend_lag0"] is None
    assert snap.feature_estados["spend_lag0"] is EstadoSemantico.ANTIGO
    assert snap.estado_semantico is EstadoSemantico.ANTIGO


def test_zero_medido_contraditorio_e_fonte_falhou_contraditoria_sao_recusados():
    obs = next(o for o in serie_sintetica_a() if o.civil_date == "2026-07-08")
    with pytest.raises(ContratoInvalido, match="ZERO_MEDIDO"):
        replace(obs, spend_estado=EstadoSemantico.ZERO_MEDIDO, spend_micros=123)
    with pytest.raises(ContratoInvalido, match="fonte_falhou"):
        replace(obs, fonte_falhou=True)
    with pytest.raises(ContratoInvalido, match="ZERO_MEDIDO"):
        valor_numerico_ou_nulo(EstadoSemantico.ZERO_MEDIDO, 123)
