"""Perplexity Sonar Pro grounding client (the mandated external validation tool)."""
from __future__ import annotations

import httpx

from app.config import Settings
from app.llm.base import GroundingClient

_URL = "https://api.perplexity.ai/chat/completions"


class PerplexityGrounding(GroundingClient):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_key = settings.perplexity_api_key
        self.model = settings.pautador_perplexity_model
        self.name = "perplexity"

    async def search(self, query: str) -> str:
        if not self.api_key:
            raise RuntimeError("PERPLEXITY_API_KEY not configured")

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise research assistant. Answer with verified facts, real program/agency names, and concrete figures. Be concise.",
                },
                {"role": "user", "content": query},
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            resp = await client.post(_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"Perplexity returned no choices: {data}")
        return (choices[0].get("message") or {}).get("content") or ""
