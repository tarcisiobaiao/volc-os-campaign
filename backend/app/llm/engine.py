"""
LLMEngine — binds a raw LLMClient to the Pautador prompts and returns the
parsed JSON contracts for each phase.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.llm.base import DiscoveryEngine, LLMClient
from app.prompts import (
    FUNNEL_BUILDER_SYSTEM_PROMPT,
    GOD_MODE_SYSTEM_PROMPT,
    KEYWORD_MINING_SYSTEM_PROMPT,
    build_discovery_mission,
    build_funnel_mission,
    build_mining_mission,
)


class LLMEngine(DiscoveryEngine):
    def __init__(self, client: LLMClient):
        self.client = client
        self.name = client.name
        self.model = client.model

    async def discover(
        self,
        country: str,
        native_language: Optional[str],
        count: int,
        grounding_notes: str = "",
    ) -> Dict[str, Any]:
        today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
        mission = build_discovery_mission(country, count=count, today=today)
        if grounding_notes:
            mission += (
                "\n\n## DOSSIÊ DE GROUNDING (Perplexity)\n"
                "Use estes fatos verificados. NÃO invente programas/órgãos:\n"
                f"{grounding_notes}"
            )
        return await self.client.complete_json(GOD_MODE_SYSTEM_PROMPT, mission)

    async def mine(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        return await self.client.complete_json(
            KEYWORD_MINING_SYSTEM_PROMPT, build_mining_mission(opportunity)
        )

    async def build_funnel(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        return await self.client.complete_json(
            FUNNEL_BUILDER_SYSTEM_PROMPT, build_funnel_mission(opportunity)
        )
