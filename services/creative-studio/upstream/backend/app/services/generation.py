"""GenerationService — top-level service wired by main.py."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from app.agents.brand_guardian import BrandGuardianAgent
from app.agents.creative_strategist import CreativeStrategistAgent
from app.agents.image_generator import ImageGeneratorAgent
from app.agents.orchestrator import OrchestratorAgent
from app.agents.quality_review import QualityReviewAgent
from app.config import settings
from app.progress import ProgressEvent
from app.providers.base import ImageProvider
from app.providers.gemini import GeminiImageProvider
from app.providers.mock import MockImageProvider
from app.providers.openai_image import OpenAIImageProvider
from app.schemas import GenerateRequest
from app.services.packager import ZipPackager


log = logging.getLogger(__name__)


def _build_provider() -> ImageProvider:
    provider = settings.image_provider
    if provider == "mock":
        return MockImageProvider()
    if provider == "gemini":
        return GeminiImageProvider()
    if provider in ("openai-image", "openai"):
        return OpenAIImageProvider()
    log.warning("Unknown IMAGE_PROVIDER=%r — defaulting to openai-image", provider)
    return OpenAIImageProvider()


class GenerationService:
    def __init__(self) -> None:
        provider = _build_provider()
        self._orchestrator = OrchestratorAgent(
            brand_guardian=BrandGuardianAgent(),
            creative_strategist=CreativeStrategistAgent(),
            image_generator=ImageGeneratorAgent(provider),
            quality_reviewer=QualityReviewAgent(),
        )
        self._packager = ZipPackager()

    async def generate_zip(self, request: GenerateRequest) -> bytes:
        """Run the full pipeline and return a ZIP of generated images."""
        images = await self._orchestrator.run(request)
        return self._packager.pack(images)

    def generate_events(self, request: GenerateRequest) -> AsyncIterator[ProgressEvent]:
        """Stream the pipeline as ProgressEvents (for the SSE endpoint)."""
        return self._orchestrator.run_events(request)
