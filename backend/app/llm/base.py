"""
LLM abstractions: a thin async chat client, a grounding (search) client, and
the high-level DiscoveryEngine contract the agents orchestrate.

O extrator defensivo de JSON (port do Code node do n8n) MUDOU DE CASA: vive em
`app/llm/json_defensivo.py` porque passou a ter um segundo consumidor fora do
backend (`volc_ads/copy/`). É re-exportado aqui — todo import existente de
`app.llm.base import extract_json` continua valendo, e não há segunda cópia.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from app.llm.json_defensivo import extract_json, repair_json_delimiters


class LLMClient(ABC):
    """A minimal async chat client returning raw text."""

    name: str = "llm"
    model: Optional[str] = None

    @abstractmethod
    async def complete(self, system: str, user: str) -> str:
        """Return the model's text completion."""
        raise NotImplementedError

    async def complete_json(self, system: str, user: str) -> Dict[str, Any]:
        return extract_json(await self.complete(system, user))


class GroundingClient(ABC):
    """External search/grounding (e.g. Perplexity Sonar Pro)."""

    name: str = "grounding"

    @abstractmethod
    async def search(self, query: str) -> str:
        raise NotImplementedError


class DiscoveryEngine(ABC):
    """
    High-level engine the agents call. Either backed by a real LLM
    (LLMEngine) or by the deterministic MockEngine.
    """

    name: str = "engine"
    model: Optional[str] = None

    @abstractmethod
    async def discover(
        self,
        country: str,
        native_language: Optional[str],
        count: int,
        grounding_notes: str = "",
    ) -> Dict[str, Any]:
        """Return the full GOD MODE JSON: meta, cultural_intelligence, personas, seeds, insights."""
        raise NotImplementedError

    @abstractmethod
    async def mine(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Return a keyword cluster JSON for one opportunity."""
        raise NotImplementedError

    @abstractmethod
    async def build_funnel(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Return a 5-page funnel JSON for one opportunity."""
        raise NotImplementedError


__all__ = [
    "extract_json",
    "repair_json_delimiters",
    "LLMClient",
    "GroundingClient",
    "DiscoveryEngine",
]
