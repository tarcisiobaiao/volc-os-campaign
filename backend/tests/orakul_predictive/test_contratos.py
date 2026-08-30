"""Contratos tipados: identidade, procedência, unidade, fuso, sem mutação."""

from __future__ import annotations

import pytest

from services.orakul_predictive.contratos import PredictionRequest, SourceReceipt, recibo_sintetico
from services.orakul_predictive.excecoes import ContratoInvalido
from services.orakul_predictive.legado_forense import TABELA_FORENSE
from services.orakul_predictive.semantica import EstadoSemantico

from .helpers import agora, request_naive


def test_tabela_forense_tem_fato_hipotese_regra_risco_destino():
    assert len(TABELA_FORENSE) >= 12
    for linha in TABELA_FORENSE:
        assert len(linha) == 5
        assert all(celula.strip() for celula in linha)


def test_source_receipt_sintetico_nao_entra_em_contagem_real():
    with pytest.raises(ContratoInvalido):
        SourceReceipt(
            recibo_id="r",
            origem="fixture_sintetica",
            dataset_kind="sintetico",
            entra_em_contagens_reais=True,
            extraido_em=agora(),
            hash_fonte="h",
        )
    ok = recibo_sintetico("ok", agora())
    assert ok.entra_em_contagens_reais is False
    assert ok.dataset_kind == "sintetico"


def test_prediction_request_recusa_mutacao():
    with pytest.raises(ContratoInvalido):
        PredictionRequest(
            request_id="r",
            campanha_id="c",
            observado_em=agora(),
            janela_inicio="2026-06-01",
            janela_fim="2026-06-10",
            horizonte_dias=1,
            versao_modelo="naive_persistence/v1",
            hash_inputs="h",
            procedencia=recibo_sintetico("p", agora()),
            estado_semantico=EstadoSemantico.MEDIDO,
            chave_idempotencia="k",
            alvos=("spend",),
            mutacao_campanha=True,
        )


def test_campos_obrigatorios_do_request():
    req = request_naive("2026-06-20")
    assert req.campanha_id
    assert req.observado_em
    assert req.janela_inicio <= req.janela_fim
    assert req.horizonte_dias == 1
    assert req.versao_modelo
    assert req.hash_inputs
    assert req.procedencia.origem
    assert req.estado_semantico
    assert req.chave_idempotencia
    assert req.fuso == "America/Sao_Paulo"
    assert req.moeda == "BRL"
    assert req.unidade == "micros"
