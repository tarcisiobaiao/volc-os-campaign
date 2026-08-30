"""Estados semânticos: ausência, zero medido, falha, N/A e antigo são distintos."""

from __future__ import annotations

from enum import Enum

from .excecoes import ContratoInvalido


class EstadoSemantico(str, Enum):
    AUSENTE = "ausente"
    ZERO_MEDIDO = "zero_medido"
    MEDIDO = "medido"
    FALHA = "falha"
    NAO_APLICAVEL = "nao_aplicavel"
    ANTIGO = "antigo"
    HIPOTESE = "hipotese"


def estado_de_valor_monetario(
    micros: int | None,
    *,
    fonte_falhou: bool = False,
    aplicavel: bool = True,
    antigo: bool = False,
    observacao_existe: bool = False,
) -> EstadoSemantico:
    """Classifica um valor sem colapsar ausência em zero."""

    if not aplicavel:
        return EstadoSemantico.NAO_APLICAVEL
    if fonte_falhou:
        return EstadoSemantico.FALHA
    if not observacao_existe or micros is None:
        return EstadoSemantico.AUSENTE
    if antigo:
        return EstadoSemantico.ANTIGO
    if micros == 0:
        return EstadoSemantico.ZERO_MEDIDO
    return EstadoSemantico.MEDIDO


def valor_numerico_ou_nulo(estado: EstadoSemantico, micros: int | None) -> int | None:
    """Só MEDIDO e ZERO_MEDIDO devolvem número. Ausência nunca vira 0."""

    validar_estado_valor(estado, micros)
    if estado in (EstadoSemantico.MEDIDO, EstadoSemantico.ZERO_MEDIDO):
        return micros
    return None


def validar_estado_valor(
    estado: EstadoSemantico,
    micros: int | None,
    *,
    contexto: str = "valor",
    permitir_antigo_com_valor: bool = True,
) -> None:
    """Recusa pares estado/valor contraditórios em vez de corrigi-los calado."""

    if micros is not None and (not isinstance(micros, int) or isinstance(micros, bool)):
        raise ContratoInvalido(f"{contexto}: micros deve ser inteiro")
    if estado is EstadoSemantico.ZERO_MEDIDO and micros != 0:
        raise ContratoInvalido(f"{contexto}: ZERO_MEDIDO exige exatamente 0")
    if estado is EstadoSemantico.MEDIDO:
        if micros is None:
            raise ContratoInvalido(f"{contexto}: MEDIDO exige número")
        if micros == 0:
            raise ContratoInvalido(f"{contexto}: zero observado exige ZERO_MEDIDO")
    if estado in (
        EstadoSemantico.AUSENTE,
        EstadoSemantico.FALHA,
        EstadoSemantico.NAO_APLICAVEL,
    ) and micros is not None:
        raise ContratoInvalido(f"{contexto}: {estado.value} não pode carregar número")
    if estado is EstadoSemantico.ANTIGO and not permitir_antigo_com_valor and micros is not None:
        raise ContratoInvalido(f"{contexto}: valor antigo não pode alimentar o modelo")
    if estado is EstadoSemantico.HIPOTESE and micros is None:
        raise ContratoInvalido(f"{contexto}: HIPOTESE exige valor explícito")
