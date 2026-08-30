"""OpenAI chat client (Chat Completions API, via httpx)."""
from __future__ import annotations

from typing import Optional

import httpx

from app.config import Settings
from app.llm.base import LLMClient

_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIClient(LLMClient):
    def __init__(self, settings: Settings, model: Optional[str] = None):
        self.settings = settings
        self.api_key = settings.openai_api_key
        self.model = model or settings.pautador_openai_model
        self.name = "openai"

    async def complete(self, system: str, user: str) -> str:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not configured")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.9,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            resp = await client.post(_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"OpenAI returned no choices: {data}")
        content = (choices[0].get("message") or {}).get("content")
        if not content:
            raise RuntimeError(f"OpenAI returned empty content: {data}")
        return content
