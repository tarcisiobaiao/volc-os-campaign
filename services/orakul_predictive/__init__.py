"""Orakul Predictive Core V1 — núcleo Python offline, testável, sem mutação."""

from __future__ import annotations

from .adapters_memoria import (
    InMemoryEvaluationRepository,
    InMemoryFeatureRepository,
    InMemoryModelRegistry,
    InMemoryOutcomeRepository,
    InMemoryPredictionLedger,
)
from .avaliacao import avaliar_pares, reconciliar
from .champion_challenger import decidir_champion_challenger, propor_rollback
from .constantes import VERSAO_CONTRATO
from .contratos import (
    BacktestResult,
    ChampionChallengerDecision,
    Confidence,
    DriftSignal,
    EvaluationWindow,
    FeatureSnapshot,
    ModelVersion,
    ObservedOutcome,
    Prediction,
    PredictionInterval,
    PredictionRequest,
    SourceReceipt,
)
from .drift import sinal_drift
from .excecoes import (
    ConflitoDeIdempotencia,
    ContratoInvalido,
    DatasetInsuficiente,
    IsolamentoViolado,
    PopulacaoIncompativel,
    VazamentoDeFuturo,
)
from .features import ObservacaoDiaria, detectar_leakage_de_alvo, montar_snapshot
from .isolamento import auditar_fonte_pacote
from .legado_forense import TABELA_FORENSE
from .motor import prever, recusar_executor
from .replay import walk_forward
from .schema_migracao import SCHEMA_MIGRACAO_UNICA

__all__ = [
    "BacktestResult",
    "ChampionChallengerDecision",
    "Confidence",
    "ConflitoDeIdempotencia",
    "ContratoInvalido",
    "DATASET_KIND_DOC",
    "DatasetInsuficiente",
    "DriftSignal",
    "EvaluationWindow",
    "FeatureSnapshot",
    "InMemoryEvaluationRepository",
    "InMemoryFeatureRepository",
    "InMemoryModelRegistry",
    "InMemoryOutcomeRepository",
    "InMemoryPredictionLedger",
    "IsolamentoViolado",
    "ModelVersion",
    "ObservacaoDiaria",
    "ObservedOutcome",
    "Prediction",
    "PredictionInterval",
    "PredictionRequest",
    "PopulacaoIncompativel",
    "SCHEMA_MIGRACAO_UNICA",
    "SourceReceipt",
    "TABELA_FORENSE",
    "VERSAO_CONTRATO",
    "VazamentoDeFuturo",
    "auditar_fonte_pacote",
    "avaliar_pares",
    "decidir_champion_challenger",
    "detectar_leakage_de_alvo",
    "montar_snapshot",
    "prever",
    "propor_rollback",
    "recusar_executor",
    "reconciliar",
    "sinal_drift",
    "walk_forward",
]

DATASET_KIND_DOC = (
    "As fixtures deste pacote são sintéticas. Nenhuma métrica aqui é performance real."
)

auditar_fonte_pacote()
