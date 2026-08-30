"""
DiscoveryOrchestrator — runs the human-in-the-loop discovery pipeline:

  CountryResearch (grounding) -> engine.discover (GOD MODE)
    -> PersonaArchaeology -> AttentionFlow
    -> CriticValidator -> ArbitrageScoring

Returns a plain dict that the router validates into DiscoveryResponse and
persists. Each agent appends to ctx.logs (persisted to pautador_agent_logs).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.agents.arbitrage_scoring import ArbitrageScoringAgent
from app.agents.attention_flow import AttentionFlowAgent
from app.agents.base import AgentContext
from app.agents.country_research import CountryResearchAgent
from app.agents.critic_validator import CriticValidatorAgent
from app.agents.persona_archaeology import PersonaArchaeologyAgent


class DiscoveryOrchestrator:
    def __init__(self, ctx: AgentContext):
        self.ctx = ctx

    async def run(
        self,
        country: str,
        native_language: Optional[str],
        count: int = 40,
    ) -> Dict[str, Any]:
        ctx = self.ctx

        # Phase 1 — grounding (no-op on mock)
        grounding_notes, grounding_calls = await CountryResearchAgent(ctx).run(country)

        # GOD MODE seed generation (single authoritative call, faithful to prototype)
        discovery_json = await ctx.engine.discover(
            country, native_language, count, grounding_notes=grounding_notes
        )

        meta = discovery_json.get("meta") or {}
        resolved_lang = native_language or meta.get("native_language")
        market_tier = meta.get("market_tier")

        # Phases 2 & 3 — normalize personas + insights
        personas = PersonaArchaeologyAgent(ctx).run(discovery_json)
        insights = AttentionFlowAgent(ctx).run(discovery_json)

        # Critic — sanitize/validate seeds
        seeds, warnings = CriticValidatorAgent(ctx).run(
            discovery_json.get("seeds") or [], expected_count=count
        )

        # Scoring — enrich + stats
        opportunities, stats = ArbitrageScoringAgent(ctx).run(seeds, country, resolved_lang)

        cultural = discovery_json.get("cultural_intelligence") or {}
        # ensure all CI keys exist
        cultural = {
            "key_institutions": cultural.get("key_institutions") or [],
            "main_benefits_programs": cultural.get("main_benefits_programs") or [],
            "unique_cultural_pains": cultural.get("unique_cultural_pains") or [],
            "upcoming_events": cultural.get("upcoming_events") or [],
            "digital_friction_apps": cultural.get("digital_friction_apps") or [],
        }

        return {
            "meta": {
                "country": country,
                "native_language": resolved_lang,
                "market_tier": market_tier if market_tier in ("high_value", "medium_value", "volume_play") else None,
                "engine": ctx.engine.name,
                "model": ctx.engine.model,
                "grounding_calls": grounding_calls,
                "generated_at": meta.get("generated_at") or datetime.now(timezone.utc).isoformat(),
            },
            "cultural_intelligence": cultural,
            "personas": personas,
            "insights": insights,
            "opportunities": opportunities,
            "stats": stats,
            "warnings": warnings,
        }
