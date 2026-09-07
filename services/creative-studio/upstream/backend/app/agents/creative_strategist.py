"""CreativeStrategistAgent — generates visual blueprints via OpenAI."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from app.config import settings
from app.prompts import (
    RESEARCH_SYSTEM,
    build_research_prompt,
    build_user_prompt,
    get_system_prompt,
)
from app.schemas import VariationContext

log = logging.getLogger(__name__)

# Gemini exposes an OpenAI-compatible Chat Completions API — lets us drive a
# Gemini text model (e.g. gemini-3.5-flash) for blueprints with the same client.
_GEMINI_OPENAI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"


class CreativeStrategistAgent:
    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None
        self._gemini_client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            if not settings.openai_api_key:
                raise RuntimeError(
                    "OPENAI_API_KEY is not set. "
                    "Set it in backend/.env or use IMAGE_PROVIDER=mock for testing."
                )
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    def _get_gemini_client(self) -> AsyncOpenAI:
        if self._gemini_client is None:
            if not settings.gemini_api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY is not set — required for a Gemini blueprint model."
                )
            self._gemini_client = AsyncOpenAI(
                api_key=settings.gemini_api_key, base_url=_GEMINI_OPENAI_BASE
            )
        return self._gemini_client

    def _client_for_model(self, model: str) -> AsyncOpenAI:
        return self._get_gemini_client() if model.startswith("gemini") else self._get_client()

    async def research_context(self, content_type: str, objetivo_campanha: str) -> str:
        """Gather real, current concurso facts via hosted web search (Responses API).

        Runs ONCE per request; the brief is shared across all variations so every
        art is enriched with the same verified data. Hosted web_search requires a
        web-search-capable model (NOT base gpt-4o) — see settings.strategist_model.
        Degrades gracefully to an empty brief on any failure.
        """
        if not settings.enable_web_search:
            return ""

        try:
            response = await self._get_client().responses.create(
                model=settings.strategist_model,
                tools=[{"type": "web_search"}],
                input=[
                    {"role": "system", "content": RESEARCH_SYSTEM},
                    {"role": "user", "content": build_research_prompt(content_type, objetivo_campanha)},
                ],
            )
            brief = (getattr(response, "output_text", "") or "").strip()
            log.info("CreativeStrategist: research brief gathered — %d chars (model=%s)", len(brief), settings.strategist_model)
            return brief
        except Exception as exc:
            log.warning(
                "CreativeStrategist: web-search research failed (%s) — proceeding without brief",
                exc,
            )
            return ""

    async def generate_blueprint(self, variation: VariationContext) -> str:
        """Return a visual blueprint string for the given variation."""
        system_prompt = get_system_prompt(variation.content_type)
        user_prompt = build_user_prompt(
            content_type=variation.content_type,
            objetivo_campanha=variation.objetivo_campanha,
            formato=variation.formato,
            dimensoes=variation.dimensoes,
            variacao_numero=variation.variacao_numero,
            total_variacoes=variation.total_variacoes,
            research_brief=variation.research_brief,
        )

        model = settings.blueprint_model_for(variation.content_type)
        client = self._client_for_model(model)

        log.debug(
            "CreativeStrategist: requesting blueprint for variation %d/%d (type=%s, model=%s)",
            variation.variacao_numero,
            variation.total_variacoes,
            variation.content_type,
            model,
        )

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.8,
            max_tokens=settings.blueprint_max_tokens,
        )

        blueprint = (response.choices[0].message.content or "").strip()

        log.debug(
            "CreativeStrategist: blueprint %d chars for variation %d (type=%s)",
            len(blueprint),
            variation.variacao_numero,
            variation.content_type,
        )
        return blueprint
