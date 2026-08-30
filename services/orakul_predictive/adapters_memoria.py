"""Adapters in-memory/local para testes. Não conectam ao Supabase oficial."""

from __future__ import annotations

from typing import Optional, Sequence

from .constantes import DATASET_SINTETICO
from .contratos import (
    BacktestResult,
    ChampionChallengerDecision,
    DriftSignal,
    ModelVersion,
    ObservedOutcome,
    Prediction,
)
from .excecoes import ConflitoDeIdempotencia, ContratoInvalido, IsolamentoViolado
from .features import ObservacaoDiaria, serie_sem_futuro
from .isolamento import recusar_mutacao_externa
from .hashes import hash_canonico
from .relogio import civil_de_instante, iso_civil


def _mesmo_payload(a, b) -> bool:
    return hash_canonico(a.serializar()) == hash_canonico(b.serializar())


def _repeticao_ou_conflito(existente, novo, *, kind: str):
    if _mesmo_payload(existente, novo):
        return existente
    raise ConflitoDeIdempotencia(
        f"{kind}: mesma identidade idempotente recebeu payload diferente"
    )


class InMemoryFeatureRepository:
    def __init__(self, serie: Sequence[ObservacaoDiaria]) -> None:
        self._serie = tuple(serie)

    def obter_serie(
        self,
        conta_id: str,
        campanha_id: str,
        as_of: str,
    ) -> Sequence[ObservacaoDiaria]:
        as_of_civil = iso_civil(civil_de_instante(as_of)) if "T" in as_of else as_of
        recortada = [
            o
            for o in serie_sem_futuro(self._serie, as_of_civil, as_of)
            if o.conta_id == conta_id and o.campanha_id == campanha_id
        ]
        return tuple(recortada)


class InMemoryPredictionLedger:
    def __init__(self) -> None:
        self._por_chave: dict[str, Prediction] = {}
        self._por_id: dict[str, Prediction] = {}
        self._por_logica: dict[tuple[str, str], Prediction] = {}

    def gravar(self, previsao: Prediction) -> Prediction:
        recusar_mutacao_externa(previsao.mutacao_campanha)
        existente = self._por_chave.get(previsao.chave_idempotencia)
        if existente is not None:
            return _repeticao_ou_conflito(existente, previsao, kind="prediction.chave")
        por_id = self._por_id.get(previsao.previsao_id)
        if por_id is not None:
            return _repeticao_ou_conflito(por_id, previsao, kind="prediction.id")
        logica = (previsao.pair_id, previsao.versao_modelo)
        por_logica = self._por_logica.get(logica)
        if por_logica is not None:
            return _repeticao_ou_conflito(
                por_logica, previsao, kind="prediction.pair_id/modelo"
            )
        self._por_chave[previsao.chave_idempotencia] = previsao
        self._por_id[previsao.previsao_id] = previsao
        self._por_logica[logica] = previsao
        return previsao

    def obter(self, chave_idempotencia: str) -> Optional[Prediction]:
        return self._por_chave.get(chave_idempotencia)

    def por_campanha(
        self,
        campanha_id: str,
        target_date: str,
        alvo: str,
        *,
        conta_id: str,
        cenario: str,
    ) -> Sequence[Prediction]:
        return tuple(
            p
            for p in self._por_chave.values()
            if p.conta_id == conta_id
            and p.campanha_id == campanha_id
            and p.target_date == target_date
            and p.alvo == alvo
            and p.cenario == cenario
        )


class InMemoryOutcomeRepository:
    def __init__(self) -> None:
        self._por_previsao: dict[str, ObservedOutcome] = {}
        self._por_pair: dict[str, ObservedOutcome] = {}
        self._por_chave: dict[str, ObservedOutcome] = {}
        self._por_id: dict[str, ObservedOutcome] = {}

    def gravar(self, outcome: ObservedOutcome) -> ObservedOutcome:
        if not outcome.fechado:
            raise ContratoInvalido("actual antes do fechamento")
        existente = self._por_chave.get(outcome.chave_idempotencia)
        if existente is not None:
            return _repeticao_ou_conflito(existente, outcome, kind="outcome.chave")
        por_id = self._por_id.get(outcome.outcome_id)
        if por_id is not None:
            return _repeticao_ou_conflito(por_id, outcome, kind="outcome.id")
        por_pair = self._por_pair.get(outcome.pair_id)
        if por_pair is not None:
            return _repeticao_ou_conflito(por_pair, outcome, kind="outcome.pair_id")
        self._por_chave[outcome.chave_idempotencia] = outcome
        self._por_id[outcome.outcome_id] = outcome
        self._por_pair[outcome.pair_id] = outcome
        if outcome.previsao_id:
            self._por_previsao[outcome.previsao_id] = outcome
        return outcome

    def obter_para_previsao(self, previsao_id: str) -> Optional[ObservedOutcome]:
        return self._por_previsao.get(previsao_id)

    def obter_por_pair(self, pair_id: str) -> Optional[ObservedOutcome]:
        return self._por_pair.get(pair_id)


class InMemoryModelRegistry:
    def __init__(self, *, permitir_sintetico: bool = False) -> None:
        self._versoes: dict[str, ModelVersion] = {}
        self._historico_champion: list[str] = []
        self._permitir_sintetico = permitir_sintetico

    def _exigir_universo_do_champion(self, versao: ModelVersion, papel: str) -> None:
        if (
            papel == "champion"
            and versao.procedencia.dataset_kind == DATASET_SINTETICO
            and not self._permitir_sintetico
        ):
            raise IsolamentoViolado(
                "champion sintético só existe em registry de laboratório explicitamente isolado"
            )

    def registrar(self, versao: ModelVersion) -> ModelVersion:
        recusar_mutacao_externa(versao.mutacao_campanha)
        self._exigir_universo_do_champion(versao, versao.papel)
        if versao.version_id in self._versoes:
            return _repeticao_ou_conflito(
                self._versoes[versao.version_id], versao, kind="model_version.id"
            )
        self._versoes[versao.version_id] = versao
        if versao.papel == "champion":
            self._historico_champion.append(versao.version_id)
        return versao

    def obter(self, version_id: str) -> Optional[ModelVersion]:
        return self._versoes.get(version_id)

    def champion(self, alvo: str) -> Optional[ModelVersion]:
        champs = [v for v in self._versoes.values() if v.papel == "champion" and v.alvo == alvo]
        return champs[-1] if champs else None

    def aplicar_proposta(self, decisao: ChampionChallengerDecision, *, humano_confirmou: bool) -> ModelVersion:
        recusar_mutacao_externa(decisao.mutacao_campanha)
        if not humano_confirmou:
            raise IsolamentoViolado("proposta CC não se aplica sozinha")
        if decisao.veredito == "propor_rollback":
            alvo_id = decisao.previous_champion_id or decisao.challenger_id
            return self._trocar_papel(alvo_id, "champion", aposentar=decisao.champion_id)
        if decisao.veredito in ("propor_promocao", "champion_inicial_proposto"):
            return self._trocar_papel(decisao.challenger_id, "champion", aposentar=decisao.champion_id)
        raise ContratoInvalido(f"veredito {decisao.veredito} não se aplica")

    def _trocar_papel(self, version_id: str, papel: str, *, aposentar: Optional[str]) -> ModelVersion:
        atual = self._versoes.get(version_id)
        if atual is None:
            raise ContratoInvalido(f"versão {version_id} ausente do registry")
        self._exigir_universo_do_champion(atual, papel)
        if aposentar and aposentar in self._versoes:
            velho = self._versoes[aposentar]
            self._versoes[aposentar] = ModelVersion(
                version_id=velho.version_id,
                papel="retired",
                alvo=velho.alvo,
                feature_set_id=velho.feature_set_id,
                code_hash=velho.code_hash,
                artifact_hash=velho.artifact_hash,
                criado_em=velho.criado_em,
                procedencia=velho.procedencia,
                estado_semantico=velho.estado_semantico,
                chave_idempotencia=velho.chave_idempotencia,
                parent_version_id=velho.parent_version_id,
                notas=velho.notas + ("retired_by_cc",),
                mutacao_campanha=False,
            )
        novo = ModelVersion(
            version_id=atual.version_id,
            papel=papel,
            alvo=atual.alvo,
            feature_set_id=atual.feature_set_id,
            code_hash=atual.code_hash,
            artifact_hash=atual.artifact_hash,
            criado_em=atual.criado_em,
            procedencia=atual.procedencia,
            estado_semantico=atual.estado_semantico,
            chave_idempotencia=atual.chave_idempotencia,
            parent_version_id=atual.parent_version_id,
            notas=atual.notas + (f"papel={papel}",),
            mutacao_campanha=False,
        )
        self._versoes[version_id] = novo
        if papel == "champion":
            self._historico_champion.append(version_id)
        return novo

    def historico_champion(self) -> tuple[str, ...]:
        return tuple(self._historico_champion)


class InMemoryEvaluationRepository:
    def __init__(self) -> None:
        self.backtests: list[BacktestResult] = []
        self.drifts: list[DriftSignal] = []
        self.decisoes: list[ChampionChallengerDecision] = []
        self._backtests: dict[str, BacktestResult] = {}
        self._drifts: dict[str, DriftSignal] = {}
        self._decisoes: dict[str, ChampionChallengerDecision] = {}

    def gravar_backtest(self, resultado: BacktestResult) -> BacktestResult:
        existente = self._backtests.get(resultado.chave_idempotencia)
        if existente is not None:
            return _repeticao_ou_conflito(existente, resultado, kind="backtest.chave")
        self._backtests[resultado.chave_idempotencia] = resultado
        self.backtests.append(resultado)
        return resultado

    def gravar_drift(self, sinal: DriftSignal) -> DriftSignal:
        existente = self._drifts.get(sinal.chave_idempotencia)
        if existente is not None:
            return _repeticao_ou_conflito(existente, sinal, kind="drift.chave")
        self._drifts[sinal.chave_idempotencia] = sinal
        self.drifts.append(sinal)
        return sinal

    def gravar_decisao_cc(self, decisao: ChampionChallengerDecision) -> ChampionChallengerDecision:
        existente = self._decisoes.get(decisao.chave_idempotencia)
        if existente is not None:
            return _repeticao_ou_conflito(existente, decisao, kind="cc.chave")
        self._decisoes[decisao.chave_idempotencia] = decisao
        self.decisoes.append(decisao)
        return decisao
