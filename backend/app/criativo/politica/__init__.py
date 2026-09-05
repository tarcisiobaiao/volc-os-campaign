"""Portão de política e identidade de terceiro sobre a peça de mídia paga.

⚠️ Este módulo NÃO é uma quarta autoridade de criativos. Ele não guarda peça,
não gera peça e não decide formato: Estúdio, Bancada e Cofre continuam donos
disso. O que mora aqui é uma pergunta que nenhum deles respondia — *esta peça
pode ir para mídia paga?* — e o recibo assinado que registra a resposta.
"""
from .gate import (  # noqa: F401
    FLAG_ESTRITO,
    AutorizacaoDeTerceiro,
    PoliticaCriativaRecusou,
    avaliar,
    exigir_liberacao,
    modo_estrito,
)
from .recibo import (  # noqa: F401
    BLOCKED_BY_POLICY,
    CLEAR,
    DECISOES,
    DECISOES_QUE_LIBERAM,
    GATE_UNAVAILABLE,
    THIRD_PARTY_IDENTITY_AUTHORIZED,
    THIRD_PARTY_IDENTITY_UNVERIFIED,
    Detector,
    ReciboDePolitica,
    ReciboInvalido,
)

__all__ = [
    "AutorizacaoDeTerceiro", "PoliticaCriativaRecusou", "avaliar",
    "exigir_liberacao", "modo_estrito", "FLAG_ESTRITO", "ReciboDePolitica", "ReciboInvalido", "Detector",
    "CLEAR", "THIRD_PARTY_IDENTITY_AUTHORIZED",
    "THIRD_PARTY_IDENTITY_UNVERIFIED", "BLOCKED_BY_POLICY", "GATE_UNAVAILABLE",
    "DECISOES", "DECISOES_QUE_LIBERAM",
]
