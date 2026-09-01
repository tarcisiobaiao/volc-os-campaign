"""Coleta persistente, read-only, da inteligencia oficial do Google Ads."""

from .alvo import AlvoColeta, ErroAlvoDivergente, ErroAlvoInvalido
from .coletor import (
    ColetorGoogleInteligencia, executar_coleta, executar_coleta_alvo,
    executar_coleta_pmax,
)
from .modelo import EstadoColeta, EstadoValor, DocumentoColeta, Metrica
from .pmax import ErroCanalNaoPMax, ProntidaoPMax, resumo_sanitizado
from .releitura import (
    ErroReleitura, ErroReleituraAmbigua, IdentidadeDaFotografia,
    avaliar_prontidao_relida, fotografia_do_ledger, fotografia_relida,
    prontidao_do_ledger,
)

__all__ = [
    "AlvoColeta",
    "ColetorGoogleInteligencia",
    "DocumentoColeta",
    "ErroAlvoDivergente",
    "ErroAlvoInvalido",
    "ErroCanalNaoPMax",
    "ErroReleitura",
    "ErroReleituraAmbigua",
    "EstadoColeta",
    "EstadoValor",
    "IdentidadeDaFotografia",
    "Metrica",
    "ProntidaoPMax",
    "avaliar_prontidao_relida",
    "executar_coleta",
    "executar_coleta_alvo",
    "executar_coleta_pmax",
    "fotografia_do_ledger",
    "fotografia_relida",
    "prontidao_do_ledger",
    "resumo_sanitizado",
]
