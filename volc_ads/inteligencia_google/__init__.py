"""Coleta persistente, read-only, da inteligencia oficial do Google Ads."""

from .alvo import AlvoColeta, ErroAlvoDivergente, ErroAlvoInvalido
from .coletor import ColetorGoogleInteligencia, executar_coleta, executar_coleta_alvo
from .modelo import EstadoColeta, EstadoValor, DocumentoColeta, Metrica

__all__ = [
    "AlvoColeta",
    "ColetorGoogleInteligencia",
    "DocumentoColeta",
    "ErroAlvoDivergente",
    "ErroAlvoInvalido",
    "EstadoColeta",
    "EstadoValor",
    "Metrica",
    "executar_coleta",
    "executar_coleta_alvo",
]
