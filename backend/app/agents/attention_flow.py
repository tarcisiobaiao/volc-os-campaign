"""Phase 3 — Attention flow mapping. Normalizes the engine's insights to schema."""
from __future__ import annotations

from typing import Any, Dict

from app.agents.base import BaseAgent


class AttentionFlowAgent(BaseAgent):
    name = "AttentionFlowAgent"
    phase = "discovery"

    def run(self, discovery_json: Dict[str, Any]) -> Dict[str, str]:
        raw = discovery_json.get("insights") or {}
        insights = {
            "market_observation": raw.get("market_observation") or "",
            "untapped_angle": raw.get("untapped_angle") or "",
            "recommended_deep_dive": raw.get("recommended_deep_dive") or "",
            "cultural_warning": raw.get("cultural_warning") or "",
        }
        self.log("Insights de fluxo de atenção normalizados.", step="attention_flow")
        return insights
