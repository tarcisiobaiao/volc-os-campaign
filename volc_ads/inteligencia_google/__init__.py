"""Coleta persistente, read-only, da inteligencia oficial do Google Ads."""

from .alvo import AlvoColeta, ErroAlvoDivergente, ErroAlvoInvalido
from .coletor import (
    ColetorGoogleInteligencia, executar_coleta, executar_coleta_alvo,
    executar_coleta_pmax,
)
from .modelo import EstadoColeta, EstadoValor, DocumentoColeta, Metrica
from .pmax import ErroCanalNaoPMax, ProntidaoPMax, resumo_sanitizado

__all__ = [
    "AlvoColeta",
    "ColetorGoogleInteligencia",
    "DocumentoColeta",
    "ErroAlvoDivergente",
    "ErroAlvoInvalido",
    "ErroCanalNaoPMax",
    "EstadoColeta",
    "EstadoValor",
    "Metrica",
    "ProntidaoPMax",
    "executar_coleta",
    "executar_coleta_alvo",
    "executar_coleta_pmax",
    "resumo_sanitizado",
]
