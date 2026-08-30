"""Drift de feature e de erro. Amostra pequena ≠ ausência de drift."""

from __future__ import annotations

from typing import Sequence

from .constantes import N_MINIMO_TREINO
from .contratos import DriftSignal, SourceReceipt
from .hashes import chave_idempotencia, hash_canonico, id_canonico
from .semantica import EstadoSemantico


def _media(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mu = _media(xs)
    return (sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def sinal_drift(
    *,
    referencia: Sequence[float],
    atual: Sequence[float],
    tipo: str,
    feature: str | None,
    procedencia: SourceReceipt,
    observado_em: str,
    janela_inicio: str,
    janela_fim: str,
    versao_modelo: str,
    campanha_id: str | None,
    conta_id: str | None = None,
    limiar_z: float = 2.0,
) -> DriftSignal:
    suficiente = len(referencia) >= N_MINIMO_TREINO and len(atual) >= 7
    mag = None
    acao = "nenhuma"
    estado = EstadoSemantico.AUSENTE
    if suficiente:
        sd = _std(referencia) or 1.0
        mag = abs(_media(atual) - _media(referencia)) / sd
        estado = EstadoSemantico.MEDIDO
        if mag >= limiar_z:
            acao = "usar_baseline"
    notas: tuple[str, ...]
    if not suficiente:
        notas = ("evidencia_insuficiente_nao_e_vitoria",)
        acao = "indisponivel"
    elif acao == "usar_baseline":
        notas = ("drift_suspende_influencia_do_challenger",)
    else:
        notas = ()
    return DriftSignal(
        signal_id=id_canonico(
            "drift",
            conta_id=conta_id,
            campanha_id=campanha_id,
            tipo=tipo,
            feature=feature,
            janela_inicio=janela_inicio,
            janela_fim=janela_fim,
            versao_modelo=versao_modelo,
        ),
        campanha_id=campanha_id,
        conta_id=conta_id,
        observado_em=observado_em,
        janela_inicio=janela_inicio,
        janela_fim=janela_fim,
        horizonte_dias=1,
        versao_modelo=versao_modelo,
        hash_inputs=hash_canonico({
            "referencia": tuple(float(x) for x in referencia),
            "atual": tuple(float(x) for x in atual),
            "tipo": tipo,
            "feature": feature,
            "limiar_z": limiar_z,
            "conta_id": conta_id,
            "campanha_id": campanha_id,
            "janela_inicio": janela_inicio,
            "janela_fim": janela_fim,
            "versao_modelo": versao_modelo,
        }),
        procedencia=procedencia,
        estado_semantico=estado,
        chave_idempotencia=chave_idempotencia(
            kind="drift",
            conta_id=conta_id,
            campanha_id=campanha_id,
            t=tipo,
            f=feature,
            janela_inicio=janela_inicio,
            janela_fim=janela_fim,
            versao_modelo=versao_modelo,
        ),
        tipo=tipo,
        feature=feature,
        mag=mag,
        evidencia_suficiente=suficiente,
        acao=acao,
        notas=notas,
    )
