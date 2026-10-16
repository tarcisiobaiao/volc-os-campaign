"""Vocabulário fechado da observação canônica append-only.

`StatusObservacao` é mais fino que o `EstadoMedida` herdado de `volc_dil.contracts`:
ele separa *ausência* (a fonte respondeu e não há linha) de *falha* (a fonte não
respondeu), de *atraso* (a fonte ainda não publicou), de *não suportado* (a fonte não
mede aquilo) e de *inválido* (a fonte respondeu algo que não passa no contrato).
O mapeamento para o contrato herdado fica em `MAPA_ESTADO_HERDADO` e perde
informação de propósito só na direção fina → grossa.
"""
from __future__ import annotations

import enum

from ...contracts.vocab import EstadoMedida, Metrica


class StatusObservacao(str, enum.Enum):
    OBSERVED = "observed"  # a fonte devolveu valor não nulo e diferente de zero, janela fechada
    ZERO_CONFIRMED = "zero_confirmed"  # a fonte devolveu explicitamente 0, janela fechada
    MISSING = "missing"  # a fonte respondeu com sucesso e não há linha/valor para a chave
    LATE = "late"  # esperado e ainda não publicado pela fonte (passou do SLA)
    UNAVAILABLE = "unavailable"  # a coleta falhou (HTTP 5xx, timeout, autenticação, quota)
    UNSUPPORTED = "unsupported"  # a fonte não mede essa métrica/grão
    INVALID = "invalid"  # a fonte respondeu, mas a resposta viola o contrato (bruto só no payload)
    PARTIAL = "partial"  # cobertura parcial declarada (ex.: janela ainda aberta)


class Unidade(str, enum.Enum):
    MICROS = "micros"  # dinheiro: inteiro em micros + moeda ISO-4217
    CONTAGEM = "contagem"  # inteiro >= 0, sem moeda


COM_VALOR_OBRIGATORIO = frozenset({StatusObservacao.OBSERVED, StatusObservacao.ZERO_CONFIRMED})
SEM_VALOR = frozenset(
    {
        StatusObservacao.MISSING,
        StatusObservacao.LATE,
        StatusObservacao.UNAVAILABLE,
        StatusObservacao.UNSUPPORTED,
        StatusObservacao.INVALID,
    }
)
# Todo status fora destes exige `motivo`.
SEM_MOTIVO_OBRIGATORIO = COM_VALOR_OBRIGATORIO

# cobertura parcial em partes por milhão (inteiro, sem float): 1..999_999
COBERTURA_PPM_MIN = 1
COBERTURA_PPM_MAX = 999_999

BIGINT_MIN = -(2**63)
BIGINT_MAX = 2**63 - 1

UNIDADE_DA_METRICA: dict[Metrica, frozenset[Unidade]] = {
    Metrica.CUSTO: frozenset({Unidade.MICROS}),
    Metrica.RECEITA: frozenset({Unidade.MICROS}),
    Metrica.CLIQUES: frozenset({Unidade.CONTAGEM}),
    Metrica.IMPRESSOES: frozenset({Unidade.CONTAGEM}),
    Metrica.SESSOES: frozenset({Unidade.CONTAGEM}),
    Metrica.CONVERSOES: frozenset({Unidade.CONTAGEM}),
    Metrica.SINAL: frozenset({Unidade.MICROS, Unidade.CONTAGEM}),
}

# Direção fina → grossa. `partial` depende de haver valor (ver `asof.para_contrato_economico`).
MAPA_ESTADO_HERDADO: dict[StatusObservacao, EstadoMedida] = {
    StatusObservacao.OBSERVED: EstadoMedida.MEDIDO,
    StatusObservacao.ZERO_CONFIRMED: EstadoMedida.ZERO_CONFIRMADO,
    StatusObservacao.MISSING: EstadoMedida.AUSENTE,
    StatusObservacao.LATE: EstadoMedida.NAO_COLETADO,
    StatusObservacao.UNAVAILABLE: EstadoMedida.FALHA,
    StatusObservacao.UNSUPPORTED: EstadoMedida.NAO_APLICAVEL,
    StatusObservacao.INVALID: EstadoMedida.FALHA,
    StatusObservacao.PARTIAL: EstadoMedida.MEDIDO,
}
