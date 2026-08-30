"""
Phase 1 — Cultural & political immersion.

Runs the 5 mandatory Perplexity grounding queries (when a real grounding
client is configured) and returns a consolidated dossier the discovery
engine can cite. With mock/no grounding it is a no-op (0 calls).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Tuple

from app.agents.base import AgentContext, BaseAgent
from app.prompts import PERPLEXITY_GROUNDING_QUERIES


class CountryResearchAgent(BaseAgent):
    name = "CountryResearchAgent"
    phase = "discovery"

    async def run(self, country: str) -> Tuple[str, int]:
        grounding = self.ctx.grounding
        if grounding is None or grounding.name.startswith("mock"):
            self.log("Grounding desativado/mock — pulando Perplexity (Fase 1).", step="grounding")
            return "", 0

        year = datetime.now(timezone.utc).year
        queries = [
            (key, tpl.format(country=country, year=year, next_year=year + 1))
            for key, tpl in PERPLEXITY_GROUNDING_QUERIES
        ]
        start = self._timer()
        # return_exceptions=True: failures arrive as items in `results`, handled per-query below
        results = await asyncio.gather(
            *[grounding.search(q) for _, q in queries], return_exceptions=True
        )

        notes = []
        calls = 0
        for (key, _), res in zip(queries, results):
            if isinstance(res, Exception):
                self.log(f"Consulta '{key}' falhou: {res}", level="warn", step=key)
                continue
            calls += 1
            notes.append(f"### {key}\n{res}")

        self.log(
            f"Grounding concluído: {calls}/{len(queries)} consultas.",
            step="grounding",
            duration_ms=self._elapsed_ms(start),
        )
        return "\n\n".join(notes), calls
