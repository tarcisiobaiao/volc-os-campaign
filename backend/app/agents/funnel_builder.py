"""
FunnelBuilderAgent (Phase 3) — turns one mined opportunity into a 5-page
funnel via the engine, then normalizes the pages to the contract.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.agents.base import BaseAgent

_STAGES = {"tofu", "mofu", "bofu"}
_DEFAULT_STAGE_BY_POS = {1: "tofu", 2: "tofu", 3: "mofu", 4: "mofu", 5: "bofu"}


class FunnelBuilderAgent(BaseAgent):
    name = "FunnelBuilderAgent"
    phase = "funnel"

    async def run(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        start = self._timer()
        raw = await self.ctx.engine.build_funnel(opportunity)

        pages: List[Dict[str, Any]] = []
        for idx, p in enumerate(raw.get("pages") or []):
            if not isinstance(p, dict):
                continue
            position = int(p.get("position") or (idx + 1))
            stage = str(p.get("stage", "")).lower()
            pages.append(
                {
                    "position": position,
                    "page_title": p.get("page_title") or f"Página {position}",
                    "avatar": p.get("avatar") or opportunity.get("persona"),
                    "stage": stage if stage in _STAGES else _DEFAULT_STAGE_BY_POS.get(position, "tofu"),
                    "emotional_goal": p.get("emotional_goal") or "",
                    "subtitles": [str(s) for s in (p.get("subtitles") or [])],
                    "internal_links": [str(s) for s in (p.get("internal_links") or [])],
                }
            )

        pages.sort(key=lambda x: x["position"])
        funnel = {
            "opportunity_id": opportunity.get("id"),
            "run_id": opportunity.get("run_id"),
            "funnel_name": raw.get("funnel_name") or f"Funil: {opportunity.get('main_keyword')}",
            "pages": pages,
        }
        self.log(
            f"Funil construído: {len(pages)} páginas.",
            step="funnel",
            duration_ms=self._elapsed_ms(start),
            payload={"funnel_name": funnel["funnel_name"]},
        )
        return funnel
