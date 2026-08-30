"""Intervalos e confiança. Calibração fora da amostra quando houver resíduos walk-forward."""

from __future__ import annotations

import math
from typing import Optional, Sequence

from .contratos import Confidence, PredictionInterval, SourceReceipt
from .excecoes import ContratoInvalido
from .hashes import chave_idempotencia, hash_canonico, id_canonico
from .semantica import EstadoSemantico


def margem_quantil(residuos_abs: Sequence[float], nominal: float = 0.90, minimo: int = 7) -> Optional[float]:
    """Quantil split-conformal de rank ceil((n+1)*nominal), com método higher."""

    if not 0.0 < nominal < 1.0:
        raise ContratoInvalido("nominal deve estar entre 0 e 1")
    if minimo < 1:
        raise ContratoInvalido("mínimo de calibração inválido")
    if len(residuos_abs) < minimo:
        return None
    if any(not math.isfinite(float(r)) or float(r) < 0 for r in residuos_abs):
        raise ContratoInvalido("resíduo de calibração deve ser finito e não negativo")
    ordenados = sorted(float(r) for r in residuos_abs)
    rank_um_indexado = min(len(ordenados), math.ceil((len(ordenados) + 1) * nominal))
    return ordenados[rank_um_indexado - 1]


def intervalo_de_ponto(
    *,
    previsao_id: str,
    campanha_id: str,
    alvo: str,
    ponto_micros: Optional[int],
    margem_brl: Optional[float],
    observado_em: str,
    janela_inicio: str,
    janela_fim: str,
    horizonte_dias: int,
    versao_modelo: str,
    hash_inputs: str,
    procedencia: SourceReceipt,
    n_calibracao: int,
    fora_da_amostra: bool,
    conta_id: Optional[str],
    pair_id: str,
    cenario: str,
    artifact_hash: str,
    nominal: float = 0.90,
) -> Optional[PredictionInterval]:
    if ponto_micros is None or margem_brl is None or not fora_da_amostra:
        return None
    margem = int(round(margem_brl * 1_000_000))
    lower = max(0, ponto_micros - margem)
    upper = ponto_micros + margem
    estado = EstadoSemantico.MEDIDO if fora_da_amostra else EstadoSemantico.ANTIGO
    return PredictionInterval(
        interval_id=id_canonico("interval", previsao_id=previsao_id, pair_id=pair_id, artifact_hash=artifact_hash),
        campanha_id=campanha_id,
        conta_id=conta_id,
        observado_em=observado_em,
        janela_inicio=janela_inicio,
        janela_fim=janela_fim,
        horizonte_dias=horizonte_dias,
        versao_modelo=versao_modelo,
        hash_inputs=hash_inputs,
        procedencia=procedencia,
        estado_semantico=estado,
        chave_idempotencia=chave_idempotencia(
            kind="interval",
            conta_id=conta_id,
            previsao=previsao_id,
            pair_id=pair_id,
            cenario=cenario,
            artifact_hash=artifact_hash,
        ),
        alvo=alvo,
        nominal=nominal,
        lower_micros=lower,
        upper_micros=upper,
        metodo="split_conformal_abs_residual_higher/v1",
        calibrado_fora_da_amostra=fora_da_amostra,
        n_calibracao=n_calibracao,
        pair_id=pair_id,
        cenario=cenario,
        artifact_hash=artifact_hash,
    )


def confianca_de_cobertura(
    *,
    previsao_id: str,
    campanha_id: str,
    cobertura_empirica: Optional[float],
    n: int,
    observado_em: str,
    janela_inicio: str,
    janela_fim: str,
    horizonte_dias: int,
    versao_modelo: str,
    hash_inputs: str,
    procedencia: SourceReceipt,
    conta_id: Optional[str],
) -> Confidence:
    suficiente = n >= 21 and cobertura_empirica is not None
    return Confidence(
        confidence_id=f"conf:{previsao_id}",
        campanha_id=campanha_id,
        conta_id=conta_id,
        observado_em=observado_em,
        janela_inicio=janela_inicio,
        janela_fim=janela_fim,
        horizonte_dias=horizonte_dias,
        versao_modelo=versao_modelo,
        hash_inputs=hash_canonico({"n": n, "cob": cobertura_empirica}),
        procedencia=procedencia,
        estado_semantico=EstadoSemantico.MEDIDO if suficiente else EstadoSemantico.AUSENTE,
        chave_idempotencia=chave_idempotencia(kind="confidence", previsao=previsao_id),
        cobertura_empirica=cobertura_empirica,
        cobertura_nominal=0.90,
        n_avaliacao=n,
        evidencia_suficiente=suficiente,
        notas=() if suficiente else ("cobertura_in_sample_nao_e_calibracao",),
    )
