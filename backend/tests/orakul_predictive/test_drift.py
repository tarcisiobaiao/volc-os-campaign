"""Drift de feature e de erro. Amostra pequena ≠ sem drift."""

from __future__ import annotations

from services.orakul_predictive.drift import sinal_drift
from services.orakul_predictive.fixtures_sinteticas import CAMPANHA_A, CONTA, procedencia_sintetica
from services.orakul_predictive.semantica import EstadoSemantico

from .helpers import agora


def test_drift_com_amostra_pequena_e_insuficiente():
    sinal = sinal_drift(
        referencia=[1.0, 1.1, 0.9],
        atual=[3.0, 3.1],
        tipo="feature",
        feature="spend_lag0",
        procedencia=procedencia_sintetica(),
        observado_em=agora(),
        janela_inicio="2026-06-01",
        janela_fim="2026-06-10",
        versao_modelo="lagged_linear_ridge/v1",
        campanha_id=CAMPANHA_A,
        conta_id=CONTA,
    )
    assert sinal.evidencia_suficiente is False
    assert sinal.acao == "indisponivel"
    assert sinal.estado_semantico is EstadoSemantico.AUSENTE
    assert "evidencia_insuficiente_nao_e_vitoria" in sinal.notas


def test_drift_de_erro_dispara_fallback_para_baseline():
    ref = [1.0] * 20
    atual = [8.0] * 10
    sinal = sinal_drift(
        referencia=ref,
        atual=atual,
        tipo="residual",
        feature=None,
        procedencia=procedencia_sintetica(),
        observado_em=agora(),
        janela_inicio="2026-06-01",
        janela_fim="2026-07-01",
        versao_modelo="lagged_linear_ridge/v1",
        campanha_id=CAMPANHA_A,
        conta_id=CONTA,
    )
    assert sinal.evidencia_suficiente is True
    assert sinal.acao == "usar_baseline"
    assert sinal.mag is not None and sinal.mag >= 2.0
