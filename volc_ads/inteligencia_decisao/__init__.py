"""Kernel puro do laboratório de inteligência de decisão VOLC.

O pacote não conhece HTTP, Supabase, n8n, Google Ads nem segredo. A entrada é
uma fotografia já observada; a saída é diagnóstico e proposta T1 bloqueada.
"""

from .critica import CriticoDeterministico, PortaCritica
from .normalizacao_google_ads import (
    CoberturaGraoGoogleAds,
    ErroNormalizacaoGoogleAds,
    EstadoCoberturaGoogleAds,
    ReciboCoberturaGoogleAds,
    normalizar_linhas_google_ads,
)
from .pipeline import executar_pipeline
from .replay import carregar_cenario, catalogo_de_cenarios, executar_replay

__all__ = [
    "CoberturaGraoGoogleAds",
    "CriticoDeterministico",
    "ErroNormalizacaoGoogleAds",
    "EstadoCoberturaGoogleAds",
    "PortaCritica",
    "ReciboCoberturaGoogleAds",
    "carregar_cenario",
    "catalogo_de_cenarios",
    "executar_pipeline",
    "executar_replay",
    "normalizar_linhas_google_ads",
]
