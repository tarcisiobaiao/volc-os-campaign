"""LLM clients, grounding, and the discovery-engine factory."""
from __future__ import annotations

from typing import Optional

from app.config import Settings
from app.llm.base import DiscoveryEngine, GroundingClient, LLMClient
from app.llm.mock import MockEngine, MockGrounding


def get_engine(settings: Settings, override: Optional[str] = None, model: Optional[str] = None) -> DiscoveryEngine:
    """Resolve the discovery engine. Falls back to MockEngine when no key/unknown."""
    engine = (override or settings.resolve_engine()).lower()

    if engine == "gemini" and settings.resolved_gemini_key:
        from app.llm.gemini import GeminiClient
        from app.llm.engine import LLMEngine

        return LLMEngine(GeminiClient(settings, model=model))

    if engine == "openai" and settings.openai_api_key:
        from app.llm.openai_client import OpenAIClient
        from app.llm.engine import LLMEngine

        return LLMEngine(OpenAIClient(settings, model=model))

    return MockEngine()


def get_grounding(settings: Settings) -> Optional[GroundingClient]:
    """Perplexity grounding client, or a no-op mock if disabled / keyless."""
    if settings.pautador_grounding_enabled and settings.perplexity_api_key:
        from app.llm.perplexity import PerplexityGrounding

        return PerplexityGrounding(settings)
    return MockGrounding()


__all__ = [
    "DiscoveryEngine",
    "GroundingClient",
    "LLMClient",
    "get_engine",
    "get_grounding",
]
