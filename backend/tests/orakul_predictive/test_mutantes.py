"""Mutantes e contraprovas: timezone/moeda, alvo, sintético como real, proveniência."""

from __future__ import annotations

import pytest

from services.orakul_predictive.constantes import CENARIO_OBSERVADO, DEFINICOES_ALVO
from services.orakul_predictive.contratos import ObservedOutcome, Prediction, SourceReceipt, recibo_sintetico
from services.orakul_predictive.excecoes import (
    ContratoInvalido,
    MoedaOuFusoIncompativel,
)
from services.orakul_predictive.features import ObservacaoDiaria
from services.orakul_predictive.fixtures_sinteticas import CAMPANHA_A, CONTA, serie_sintetica_a
from services.orakul_predictive.motor import prever
from services.orakul_predictive.replay import walk_forward
from services.orakul_predictive.schema_migracao import SCHEMA_MIGRACAO_UNICA
from services.orakul_predictive.semantica import EstadoSemantico
from services.orakul_predictive.hashes import pair_id_d1

from .helpers import agora, request_naive


def _pred_spend():
    return prever(request_naive("2026-07-08", alvos=("spend",)), serie_sintetica_a())[0]


def test_reconcilicao_recusa_target_date_desalinhado():
    pred = _pred_spend()
    # D+2 rotulado horizonte 1 morre no contrato, antes de alcançar a métrica.
    with pytest.raises(ContratoInvalido):
        ObservedOutcome(
            outcome_id="o",
            campanha_id=pred.campanha_id,
            conta_id=pred.conta_id,
            observado_em=agora(),
            janela_inicio="2026-07-10",
            janela_fim="2026-07-10",
            horizonte_dias=1,
            versao_modelo=pred.versao_modelo,
            hash_inputs="h",
            procedencia=recibo_sintetico("o", agora()),
            estado_semantico=EstadoSemantico.MEDIDO,
            chave_idempotencia="k",
            alvo=pred.alvo,
            target_date="2026-07-10",
            valor_micros=1,
            pair_id=pred.pair_id,
            origin_date=pred.origin_date,
            target_definition=pred.target_definition,
            cenario=CENARIO_OBSERVADO,
        )


def test_outcome_recusa_fuso_errado():
    origin = "2026-07-08"
    target = "2026-07-09"
    with pytest.raises(MoedaOuFusoIncompativel):
        ObservedOutcome(
            outcome_id="o",
            campanha_id=CAMPANHA_A,
            conta_id=CONTA,
            observado_em=agora(),
            janela_inicio="2026-07-09",
            janela_fim="2026-07-09",
            horizonte_dias=1,
            versao_modelo="naive_persistence/v1",
            hash_inputs="h",
            procedencia=recibo_sintetico("o", agora()),
            estado_semantico=EstadoSemantico.MEDIDO,
            chave_idempotencia="k",
            alvo="spend",
            target_date="2026-07-09",
            valor_micros=1,
            pair_id=pair_id_d1(
                conta_id=CONTA,
                campanha_id=CAMPANHA_A,
                origin_date=origin,
                target_date=target,
                alvo="spend",
                cenario=CENARIO_OBSERVADO,
                target_definition=DEFINICOES_ALVO["spend"],
            ),
            origin_date=origin,
            target_definition=DEFINICOES_ALVO["spend"],
            cenario=CENARIO_OBSERVADO,
            fuso="UTC",
        )


def test_observacao_recusa_moeda_float_implícita():
    with pytest.raises(MoedaOuFusoIncompativel):
        ObservacaoDiaria(
            campanha_id=CAMPANHA_A,
            civil_date="2026-06-01",
            spend_micros=40,
            revenue_micros=50,
            spend_estado=EstadoSemantico.MEDIDO,
            revenue_estado=EstadoSemantico.MEDIDO,
            lido_em=agora(),
            unidade="reais",
        )


def test_sintetico_marcado_como_real_falha_no_replay():
    # A mentira morre na fronteira, antes de qualquer replay ou métrica.
    with pytest.raises(ContratoInvalido):
        SourceReceipt(
            recibo_id="mentira",
            origem="fixture_sintetica",
            dataset_kind="real",
            entra_em_contagens_reais=True,
            extraido_em=agora(),
            hash_fonte="h",
            notas=("mentira",),
        )
    with pytest.raises(ContratoInvalido):
        SourceReceipt(
            recibo_id="x",
            origem="fixture_sintetica",
            dataset_kind="sintetico",
            entra_em_contagens_reais=True,
            extraido_em=agora(),
            hash_fonte="h",
        )


def test_serie_da_fixture_nao_pode_ser_reetiquetada_por_recibo_com_nome_real():
    proc_falso = SourceReceipt(
        recibo_id="recibo-que-finge-ser-real",
        origem="coletor_offline",
        dataset_kind="real",
        entra_em_contagens_reais=True,
        extraido_em=agora(),
        hash_fonte="h",
    )
    with pytest.raises(ContratoInvalido, match="não pode se declarar real"):
        walk_forward(
            serie_sintetica_a(),
            campanha_id=CAMPANHA_A,
            conta_id=CONTA,
            procedencia=proc_falso,
            observado_em=agora(),
        )


def test_previsao_exige_procedencia():
    with pytest.raises(TypeError):
        Prediction(  # type: ignore[misc]
            previsao_id="p",
            campanha_id=CAMPANHA_A,
            observado_em=agora(),
            janela_inicio="2026-06-01",
            janela_fim="2026-07-08",
            horizonte_dias=1,
            versao_modelo="naive_persistence/v1",
            hash_inputs="h",
            estado_semantico=EstadoSemantico.MEDIDO,
            chave_idempotencia="k",
            alvo="spend",
            target_date="2026-07-09",
            ponto_micros=1,
            ponto_bruto_micros=1,
            intervalo=None,
            confianca=None,
            snapshot_id="s",
            cenario="observado",
        )


def test_schema_de_migration_nao_esta_aplicado():
    assert SCHEMA_MIGRACAO_UNICA["aplicada"] is False
    assert "forecast_predictions" in SCHEMA_MIGRACAO_UNICA["tabelas"]
    assert "não criar nesta branch" in SCHEMA_MIGRACAO_UNICA["nao_fazer"]


def test_naive_nao_afirma_performance_real():
    from services.orakul_predictive.constantes import MODELO_LAGGED_LINEAR
    from services.orakul_predictive.fixtures_sinteticas import procedencia_sintetica

    r = walk_forward(
        serie_sintetica_a(),
        campanha_id=CAMPANHA_A,
        procedencia=procedencia_sintetica(),
        observado_em=agora(),
        versao_modelo=MODELO_LAGGED_LINEAR,
        n_minimo_treino=14,
    )
    assert r.entra_em_contagens_reais is False
    for m in r.metricas_por_alvo.values():
        assert m.dataset_kind == "sintetico"
        assert m.entra_em_contagens_reais is False
