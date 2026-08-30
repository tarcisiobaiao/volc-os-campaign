"""Google Gemini chat client (Generative Language API v1beta, via httpx)."""
from __future__ import annotations

from typing import Optional

import httpx

from app.config import Settings
from app.llm.base import LLMClient

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiClient(LLMClient):
    def __init__(self, settings: Settings, model: Optional[str] = None):
        self.settings = settings
        self.api_key = settings.resolved_gemini_key
        # Accept both "gemini-3.5-flash" and "models/gemini-3.1-pro-preview".
        # The base URL already ends in /models, so strip a leading "models/"
        # to avoid a doubled path (.../models/models/...).
        raw_model = model or settings.pautador_gemini_model
        self.model = (raw_model or "").strip().removeprefix("models/")
        self.name = "gemini"

    async def complete(self, system: str, user: str) -> str:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY not configured")

        url = f"{_BASE}/{self.model}:generateContent"
        generation_config = {
            "temperature": 0.9,
            "responseMimeType": "application/json",
        }
        # Only cap output tokens if explicitly configured. Omitting lets each
        # model use its own outputTokenLimit (e.g. gemini-3.x flash = 65536),
        # avoiding MAX_TOKENS truncation of the GOD MODE JSON. A hardcoded 8192
        # is too small for "thinking" models (thinking tokens eat the budget).
        max_tokens = self.settings.pautador_gemini_max_output_tokens
        if max_tokens:
            generation_config["maxOutputTokens"] = max_tokens

        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": generation_config,
        }
        # timeout de GERAÇÃO, não de API: ver `llm_timeout_seconds` no config.
        timeout = getattr(self.settings, "llm_timeout_seconds", None) or self.settings.request_timeout_seconds
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, params={"key": self.api_key}, json=payload)
            resp.raise_for_status()
            data = resp.json()

        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError(f"Gemini returned no candidates: {data}")
        cand = candidates[0]
        parts = cand.get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
        if not text:
            reason = cand.get("finishReason")
            raise RuntimeError(f"Gemini returned empty text (finishReason={reason})")
        return text
