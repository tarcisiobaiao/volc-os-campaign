"""Helpers herméticos dos testes do Core V1."""

from __future__ import annotations

from datetime import date, timedelta

from services.orakul_predictive.constantes import (
    ALVO_REVENUE,
    ALVO_SPEND,
    CENARIO_OBSERVADO,
    DEFINICOES_ALVO,
    MODELO_NAIVE_PERSISTENCE,
)
from services.orakul_predictive.contratos import (
    BacktestResult,
    EvaluationWindow,
    MetricasAvaliacao,
    ModelVersion,
    PredictionRequest,
)
from services.orakul_predictive.fixtures_sinteticas import CAMPANHA_A, CONTA, INSTANTE_FIXO, procedencia_sintetica
from services.orakul_predictive.relogio import iso_instante
from services.orakul_predictive.hashes import chave_idempotencia, hash_canonico, id_canonico, pair_id_d1
from services.orakul_predictive.semantica import EstadoSemantico


def agora() -> str:
    return iso_instante(INSTANTE_FIXO)


def request_naive(
    janela_fim: str,
    *,
    alvos=None,
    conta_id: str = CONTA,
    campanha_id: str = CAMPANHA_A,
) -> PredictionRequest:
    proc = procedencia_sintetica()
    alvos_finais = alvos or (ALVO_SPEND, ALVO_REVENUE)
    payload = {
        "conta_id": conta_id,
        "campanha_id": campanha_id,
        "janela_inicio": "2026-06-01",
        "janela_fim": janela_fim,
        "horizonte_dias": 1,
        "versao_modelo": MODELO_NAIVE_PERSISTENCE,
        "alvos": alvos_finais,
        "cenario": CENARIO_OBSERVADO,
        "procedencia_hash": proc.hash_fonte,
    }
    return PredictionRequest(
        request_id=id_canonico("request", **payload),
        campanha_id=campanha_id,
        conta_id=conta_id,
        observado_em=agora(),
        janela_inicio="2026-06-01",
        janela_fim=janela_fim,
        horizonte_dias=1,
        versao_modelo=MODELO_NAIVE_PERSISTENCE,
        hash_inputs=hash_canonico(payload),
        procedencia=proc,
        estado_semantico=EstadoSemantico.MEDIDO,
        chave_idempotencia=chave_idempotencia(
            kind="request",
            conta_id=conta_id,
            campanha_id=campanha_id,
            janela_fim=janela_fim,
            versao_modelo=MODELO_NAIVE_PERSISTENCE,
            cenario=CENARIO_OBSERVADO,
        ),
        alvos=alvos_finais,
        cenario=CENARIO_OBSERVADO,
        mutacao_campanha=False,
    )


def metricas(
    n: int,
    mae: float,
    wape: float,
    *,
    pair_ids: tuple[str, ...],
    suficiente: bool = True,
) -> MetricasAvaliacao:
    return MetricasAvaliacao(
        n=n,
        mae=mae,
        wape=wape,
        rmse=mae * 1.2,
        bias=0.0,
        cobertura=0.64,
        largura_media=10.0,
        winkler=12.0,
        evidencia_suficiente=suficiente,
        dataset_kind="sintetico",
        entra_em_contagens_reais=False,
        pair_ids=pair_ids,
        n_intervalos=n,
    )


def backtest_fake(
    versao: str,
    *,
    n: int = 30,
    wape_rev: float = 0.20,
    mae_spend: float = 5.0,
    inicio: str = "2026-06-01",
    fim: str = "2026-07-01",
    completa: bool = True,
    conta_id: str = CONTA,
    campanha_id: str = CAMPANHA_A,
    pair_origin_offset: int = 0,
) -> BacktestResult:
    proc = procedencia_sintetica()
    primeiro = date.fromisoformat(inicio)
    pair_ids_por_alvo = {
        alvo: tuple(
            pair_id_d1(
                conta_id=conta_id,
                campanha_id=campanha_id,
                origin_date=(primeiro + timedelta(days=i + pair_origin_offset)).isoformat(),
                target_date=(primeiro + timedelta(days=i + pair_origin_offset + 1)).isoformat(),
                alvo=alvo,
                cenario=CENARIO_OBSERVADO,
                target_definition=DEFINICOES_ALVO[alvo],
            )
            for i in range(n)
        )
        for alvo in (ALVO_REVENUE, ALVO_SPEND)
    }
    population_hash = hash_canonico({
        "conta_id": conta_id,
        "campanha_id": campanha_id,
        "inicio": inicio,
        "fim": fim,
        "horizonte_dias": 1,
        "cenario": CENARIO_OBSERVADO,
        "pair_ids_por_alvo": pair_ids_por_alvo,
        "dataset_kind": proc.dataset_kind,
        "source_hash": proc.hash_fonte,
    })
    janela = EvaluationWindow(
        window_id=id_canonico("ew", modelo=versao, population_hash=population_hash),
        campanha_id=campanha_id,
        conta_id=conta_id,
        observado_em=agora(),
        janela_inicio=inicio,
        janela_fim=fim,
        horizonte_dias=1,
        versao_modelo=versao,
        hash_inputs=versao,
        procedencia=proc,
        estado_semantico=EstadoSemantico.MEDIDO,
        chave_idempotencia=f"ew:{versao}",
        n_pares=n,
        completa=completa,
        split="walk_forward_temporal",
        cenario=CENARIO_OBSERVADO,
        population_hash=population_hash,
    )
    return BacktestResult(
        result_id=f"bt:{versao}",
        campanha_id=campanha_id,
        conta_id=conta_id,
        observado_em=agora(),
        janela_inicio=inicio,
        janela_fim=fim,
        horizonte_dias=1,
        versao_modelo=versao,
        hash_inputs=versao,
        procedencia=proc,
        estado_semantico=EstadoSemantico.MEDIDO,
        chave_idempotencia=f"bt:{versao}",
        janela=janela,
        metricas_por_alvo={
            ALVO_REVENUE: metricas(n, mae_spend * 1.1, wape_rev, pair_ids=pair_ids_por_alvo[ALVO_REVENUE]),
            ALVO_SPEND: metricas(n, mae_spend, wape_rev * 0.9, pair_ids=pair_ids_por_alvo[ALVO_SPEND]),
        },
        naive_por_alvo={
            ALVO_REVENUE: metricas(n, mae_spend * 1.3, wape_rev + 0.05, pair_ids=pair_ids_por_alvo[ALVO_REVENUE]),
            ALVO_SPEND: metricas(n, mae_spend + 1, wape_rev, pair_ids=pair_ids_por_alvo[ALVO_SPEND]),
        },
        falhas_parciais=(),
        leakage_detectado=False,
        n_total=n,
        pair_ids_por_alvo=pair_ids_por_alvo,
        population_hash=population_hash,
        cenario=CENARIO_OBSERVADO,
    )


def versao_modelo(version_id: str, papel: str, alvo: str = ALVO_SPEND) -> ModelVersion:
    proc = procedencia_sintetica()
    return ModelVersion(
        version_id=version_id,
        papel=papel,
        alvo=alvo,
        feature_set_id="orakul-features-asof-lagged/v1",
        code_hash="c" * 64,
        artifact_hash="a" * 64,
        criado_em=agora(),
        procedencia=proc,
        estado_semantico=EstadoSemantico.MEDIDO,
        chave_idempotencia=f"mv:{version_id}",
        mutacao_campanha=False,
    )
