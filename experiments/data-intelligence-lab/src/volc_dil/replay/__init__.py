"""Replay econômico v0 do laboratório (SINTÉTICO, malha fechada, as_of por decisão)."""
from .avaliacao import alocacao_oraculo, metricas, relatorio_cenario
from .cenario import EspecCenario, Mundo, catalogo, cenario_mini
from .motor import ExecucaoReplay, cortar_as_of, executar, validar_decisao
from .politicas import (
    ContextoDecisao, Decisao, Estatica, GulosaConservadora, Igual, Proporcional, baselines, proporcional_ingenua,
)

__all__ = [
    "ContextoDecisao", "Decisao", "EspecCenario", "Estatica", "ExecucaoReplay", "GulosaConservadora", "Igual",
    "Mundo", "Proporcional", "alocacao_oraculo", "baselines", "catalogo", "cenario_mini", "cortar_as_of",
    "executar", "metricas", "proporcional_ingenua", "relatorio_cenario", "validar_decisao",
]
