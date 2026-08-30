"""
ArbitrageScoringAgent — enriches each validated seed with the arbitrage
score + parsed CPC + ROI signal (scoring.py), attaches locale/workflow
fields, and computes run-level stats (mirrors the n8n summary builder).
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from app.agents.base import BaseAgent
from app.scoring import enrich_seed


class ArbitrageScoringAgent(BaseAgent):
    name = "ArbitrageScoringAgent"
    phase = "discovery"

    def run(
        self,
        seeds: List[Dict[str, Any]],
        country: str,
        native_language: Optional[str],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        opportunities: List[Dict[str, Any]] = []
        for i, seed in enumerate(seeds):
            enriched = enrich_seed(seed, i)
            enriched.update(
                {
                    "country": country,
                    "native_language": native_language,
                    "status": "discovered",
                    "source": "agent",
                }
            )
            opportunities.append(enriched)

        # rank by score desc (stable)
        opportunities.sort(key=lambda o: o.get("arbitrage_score") or 0, reverse=True)

        stats = self._build_stats(opportunities)
        self.log(
            f"{len(opportunities)} oportunidades pontuadas (avg {stats['avg_arbitrage_score']}).",
            step="scoring",
            payload={"by_tier": stats["by_tier"]},
        )
        return opportunities, stats

    @staticmethod
    def _build_stats(opps: List[Dict[str, Any]]) -> Dict[str, Any]:
        n = len(opps)
        by_tier = Counter(o.get("tier") for o in opps)
        by_category = Counter(o.get("category") for o in opps)
        by_timing = Counter(o.get("timing") for o in opps)
        by_intent = Counter(o.get("intent") for o in opps)
        persona_counts = Counter(o.get("persona") for o in opps if o.get("persona"))

        total_score = sum((o.get("arbitrage_score") or 0) for o in opps)
        avg = round(total_score / n, 2) if n else 0.0

        top_persona = None
        if persona_counts:
            name, count = persona_counts.most_common(1)[0]
            top_persona = {"persona": name, "count": count}

        return {
            "total_seeds": n,
            "by_tier": {k: v for k, v in by_tier.items() if k is not None},
            "by_category": {k: v for k, v in by_category.items() if k is not None},
            "by_timing": {k: v for k, v in by_timing.items() if k is not None},
            "by_intent": {k: v for k, v in by_intent.items() if k is not None},
            "avg_arbitrage_score": avg,
            "top_persona_by_volume": top_persona,
            "seasonal_opportunities": sum(1 for o in opps if o.get("has_seasonal_window")),
            "trending_opportunities": sum(1 for o in opps if o.get("is_trending")),
            "evergreen_opportunities": sum(1 for o in opps if o.get("timing") == "evergreen"),
        }
