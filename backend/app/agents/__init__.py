"""Modular Pautador Pro agents (5-phase discovery + mining + funnel + critic)."""
from __future__ import annotations

from app.agents.arbitrage_scoring import ArbitrageScoringAgent
from app.agents.attention_flow import AttentionFlowAgent
from app.agents.country_research import CountryResearchAgent
from app.agents.critic_validator import CriticValidatorAgent
from app.agents.funnel_builder import FunnelBuilderAgent
from app.agents.keyword_mining import KeywordMiningAgent
from app.agents.orchestrator import DiscoveryOrchestrator
from app.agents.persona_archaeology import PersonaArchaeologyAgent

__all__ = [
    "ArbitrageScoringAgent",
    "AttentionFlowAgent",
    "CountryResearchAgent",
    "CriticValidatorAgent",
    "FunnelBuilderAgent",
    "KeywordMiningAgent",
    "PersonaArchaeologyAgent",
    "DiscoveryOrchestrator",
]
