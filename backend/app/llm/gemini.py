"""Google Gemini chat client (Generative Language API v1beta, via httpx)."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

import httpx

from app.config import Settings
from app.llm.base import LLMClient

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiClient(LLMClient):
    def __init__(
        self,
        settings: Settings,
        model: Optional[str] = None,
        *,
        temperature: float = 0.9,
    ):
        self.settings = settings
        self.api_key = settings.resolved_gemini_key
        # Accept both "gemini-3.5-flash" and "models/gemini-3.1-pro-preview".
        # The base URL already ends in /models, so strip a leading "models/"
        # to avoid a doubled path (.../models/models/...).
        raw_model = model or settings.pautador_gemini_model
        self.model = (raw_model or "").strip().removeprefix("models/")
        if not 0 <= temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
        self.temperature = temperature
        self.name = "gemini"
        # TELEMETRIA da última chamada (tokens, latência, modelo pedido e
        # servido, motivo de parada). Atributo de instância, como
        # `modelo_servido`, para não mudar o tipo de retorno de `complete`.
        self.ultimo_uso: Optional[Dict[str, Any]] = None

    async def complete(self, system: str, user: str) -> str:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY not configured")

        url = f"{_BASE}/{self.model}:generateContent"
        generation_config = {
            "temperature": self.temperature,
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
        inicio = time.perf_counter()
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, params={"key": self.api_key}, json=payload)
            resp.raise_for_status()
            data = resp.json()
        uso = data.get("usageMetadata") or {}
        cands = data.get("candidates") or [{}]
        self.ultimo_uso = {
            "modelo_solicitado": self.model,
            "modelo_servido": data.get("modelVersion") or None,
            "entrada": int(uso.get("promptTokenCount") or 0),
            # tokens de raciocínio são cobrados como saída
            "saida": int(uso.get("candidatesTokenCount") or 0)
                     + int(uso.get("thoughtsTokenCount") or 0),
            "latencia_ms": int((time.perf_counter() - inicio) * 1000),
            "motivo_de_parada": (cands[0] or {}).get("finishReason"),
        }

        # O modelo que REALMENTE respondeu. O provider pode servir um alias por
        # outro literal, e sem isto a procedência gravava sempre o que foi
        # PEDIDO — um rebaixamento silencioso ficava indetectável depois.
        # Fica como atributo de instância para não mexer no tipo de retorno,
        # que outros consumidores (Pautador) já dependem de ser `str`.
        self.modelo_servido = data.get("modelVersion") or None

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
