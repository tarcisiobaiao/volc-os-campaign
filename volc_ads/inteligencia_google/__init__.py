"""Coleta persistente, read-only, da inteligencia oficial do Google Ads."""

from .coletor import ColetorGoogleInteligencia, executar_coleta
from .modelo import EstadoColeta, EstadoValor, DocumentoColeta, Metrica

__all__ = [
    "ColetorGoogleInteligencia",
    "DocumentoColeta",
    "EstadoColeta",
    "EstadoValor",
    "Metrica",
    "executar_coleta",
]
