"""
KeywordMiningAgent (Phase 2) — turns one approved opportunity into a
keyword cluster (tree) via the engine, then computes numeric aggregates
(total_volume proxy from qualitative volumes, avg CPC from parsed ranges).
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.agents.base import BaseAgent
from app.scoring import VOLUME_SCORE, parse_cpc_range

_VALID_VOL = {"low", "medium", "high", "very_high"}
_VALID_COMP = {"low", "medium", "high"}
_VALID_INTENT = {"informational", "navigational", "calculator", "comparison"}


class KeywordMiningAgent(BaseAgent):
    name = "KeywordMiningAgent"
    phase = "mining"

    async def run(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        start = self._timer()
        raw = await self.ctx.engine.mine(opportunity)

        nodes: List[Dict[str, Any]] = []
        cpc_avgs: List[float] = []
        volume_total = 0
        currency = None

        for k in raw.get("keywords") or []:
            if not isinstance(k, dict) or not k.get("keyword"):
                continue
            vol = str(k.get("volume", "")).lower()
            comp = str(k.get("competition", "")).lower()
            intent = str(k.get("intent", "")).lower()
            node = {
                "keyword": str(k["keyword"]),
                "volume": vol if vol in _VALID_VOL else None,
                "cpc_local": k.get("cpc_local"),
                "competition": comp if comp in _VALID_COMP else None,
                "intent": intent if intent in _VALID_INTENT else None,
            }
            nodes.append(node)
            volume_total += VOLUME_SCORE.get(node["volume"], 0)
            parsed = parse_cpc_range(node["cpc_local"])
            if parsed["avg"] is not None:
                cpc_avgs.append(parsed["avg"])
                currency = currency or parsed["currency"]

        avg_cpc = round(sum(cpc_avgs) / len(cpc_avgs), 4) if cpc_avgs else None

        cluster = {
            "opportunity_id": opportunity.get("id"),
            "run_id": opportunity.get("run_id"),
            "cluster_name": raw.get("cluster_name") or f"Cluster: {opportunity.get('main_keyword')}",
            "main_keyword": raw.get("main_keyword") or opportunity.get("main_keyword"),
            "intent": (str(raw.get("intent", "")).lower() if str(raw.get("intent", "")).lower() in _VALID_INTENT else opportunity.get("intent")),
            "keywords": nodes,
            "total_volume": float(volume_total) if nodes else None,
            "avg_cpc_local": avg_cpc,
            "currency": currency,
        }
        self.log(
            f"Cluster minerado: {len(nodes)} keywords.",
            step="mine",
            duration_ms=self._elapsed_ms(start),
            payload={"cluster_name": cluster["cluster_name"]},
        )
        return cluster
