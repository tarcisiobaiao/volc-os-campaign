"""Vocabulário fechado do contrato econômico do laboratório.

Os nomes de `EstadoMedida` e `MetodoAtribuicao` espelham o núcleo econômico
`volc_ads/economia/nucleo.py` que hoje só existe em branches `wip/*` (commit
043c77f5). O laboratório NÃO importa aquele módulo: replica o vocabulário para
que o handoff de integração seja um mapeamento 1:1, não uma tradução.
"""
from __future__ import annotations

import enum


class ValueKind(str, enum.Enum):
    """Classe epistemológica de um valor monetário. Nunca muda por afirmação de modelo."""

    OBSERVED_AUCTION_SIGNAL = "observed_auction_signal"  # lance Prebid, floor, CPM visto no browser
    ESTIMATED_REVENUE = "estimated_revenue"  # projeção/nowcast/modelo
    REPORTED_REVENUE = "reported_revenue"  # relatório da plataforma, preliminar ou fechado
    RECONCILED_REVENUE = "reconciled_revenue"  # reconciliada no grão em que a fonte prova
    BUSINESS_VALUE = "business_value"  # valor de negócio declarado (meta, margem-alvo)


# Classes que podem compor receita econômica em lucro. Sinal e estimativa não entram.
RECEITA_CONTABIL = frozenset({ValueKind.REPORTED_REVENUE, ValueKind.RECONCILED_REVENUE})
# Classes aceitas como rótulo econômico de um surrogate (o alvo a prever).
ROTULO_ECONOMICO = frozenset({ValueKind.RECONCILED_REVENUE})


class EstadoMedida(str, enum.Enum):
    MEDIDO = "medido"
    ZERO_CONFIRMADO = "zero_confirmado"
    AUSENTE = "ausente"
    NAO_COLETADO = "nao_coletado"
    FALHA = "falha"
    NAO_ATRIBUIVEL = "nao_atribuivel"
    NAO_APLICAVEL = "nao_aplicavel"


COM_VALOR = frozenset({EstadoMedida.MEDIDO, EstadoMedida.ZERO_CONFIRMADO})
# A pior causa vence quando estados sem valor são combinados.
GRAVIDADE = (
    EstadoMedida.FALHA,
    EstadoMedida.NAO_COLETADO,
    EstadoMedida.AUSENTE,
    EstadoMedida.NAO_ATRIBUIVEL,
    EstadoMedida.NAO_APLICAVEL,
)


class MetodoAtribuicao(str, enum.Enum):
    DETERMINISTIC_CLICK_ID = "deterministic_click_id"
    DETERMINISTIC_SESSION = "deterministic_session"
    DETERMINISTIC_UTM = "deterministic_utm"
    DECLARED_CAMPAIGN_FUNNEL = "declared_campaign_funnel"
    AGGREGATE_CAMPAIGN_DATE = "aggregate_campaign_date"
    INFERRED = "inferred"
    UNRECONCILED = "unreconciled"
    NOT_IDENTIFIABLE = "not_identifiable"
    NAO_APLICAVEL = "nao_aplicavel"  # métricas de plataforma da própria entidade (custo, cliques)


class Cobertura(str, enum.Enum):
    COMPLETA = "complete"
    PARCIAL = "partial"
    DESCONHECIDA = "unknown"


class Maturidade(str, enum.Enum):
    PRELIMINAR = "preliminary"
    MADURA = "mature"
    REVISADA = "revised"


class Metrica(str, enum.Enum):
    CUSTO = "cost"
    RECEITA = "revenue"
    CLIQUES = "clicks"
    IMPRESSOES = "impressions"
    SESSOES = "sessions"
    CONVERSOES = "conversions"
    SINAL = "signal"  # sinal comportamental/leilão (não monetário ou monetário-sinal)


METRICAS_MONETARIAS = frozenset({Metrica.CUSTO, Metrica.RECEITA})
METRICAS_CONTAGEM = frozenset(
    {Metrica.CLIQUES, Metrica.IMPRESSOES, Metrica.SESSOES, Metrica.CONVERSOES}
)
