"""Portas de integração. Sem implementação de produção, sem Supabase, sem migration."""

from __future__ import annotations

from typing import Optional, Protocol, Sequence

from .contratos import (
    BacktestResult,
    ChampionChallengerDecision,
    DriftSignal,
    ModelVersion,
    ObservedOutcome,
    Prediction,
)
from .features import ObservacaoDiaria


class FeatureRepository(Protocol):
    def obter_serie(
        self,
        conta_id: str,
        campanha_id: str,
        as_of: str,
    ) -> Sequence[ObservacaoDiaria]:
        """Última revisão da conta/campanha conhecida no instante as_of."""


class PredictionLedger(Protocol):
    def gravar(self, previsao: Prediction) -> Prediction:
        """Append-only e idempotente pela chave_idempotencia."""

    def obter(self, chave_idempotencia: str) -> Optional[Prediction]:
        ...

    def por_campanha(
        self,
        campanha_id: str,
        target_date: str,
        alvo: str,
        *,
        conta_id: str,
        cenario: str,
    ) -> Sequence[Prediction]:
        ...


class OutcomeRepository(Protocol):
    def gravar(self, outcome: ObservedOutcome) -> ObservedOutcome:
        """Actual só depois do fechamento da data."""

    def obter_para_previsao(self, previsao_id: str) -> Optional[ObservedOutcome]:
        ...

    def obter_por_pair(self, pair_id: str) -> Optional[ObservedOutcome]:
        """Actual comum a todos os modelos avaliados no mesmo pair_id."""

        ...


class ModelRegistry(Protocol):
    def registrar(self, versao: ModelVersion) -> ModelVersion:
        ...

    def obter(self, version_id: str) -> Optional[ModelVersion]:
        ...

    def champion(self, alvo: str) -> Optional[ModelVersion]:
        ...

    def aplicar_proposta(self, decisao: ChampionChallengerDecision, *, humano_confirmou: bool) -> ModelVersion:
        """Só troca papel in-memory se humano_confirmou. Nunca muta campanha."""


class EvaluationRepository(Protocol):
    def gravar_backtest(self, resultado: BacktestResult) -> BacktestResult:
        ...

    def gravar_drift(self, sinal: DriftSignal) -> DriftSignal:
        ...

    def gravar_decisao_cc(self, decisao: ChampionChallengerDecision) -> ChampionChallengerDecision:
        ...
