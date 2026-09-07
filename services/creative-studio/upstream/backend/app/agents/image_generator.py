"""ImageGeneratorAgent — wraps an ImageProvider with logging."""

from __future__ import annotations

import base64
import logging

from app.providers.base import ImageProvider, ImageResult
from app.schemas import VariationContext
from app.utils.image import should_use_white_logo, to_white_monochrome

log = logging.getLogger(__name__)


class ImageGeneratorAgent:
    def __init__(self, provider: ImageProvider) -> None:
        self._provider = provider

    async def generate(
        self, variation: VariationContext, blueprint: str
    ) -> ImageResult:
        log.info(
            "ImageGenerator: generating variation %d/%d via %s (type=%s)",
            variation.variacao_numero,
            variation.total_variacoes,
            type(self._provider).__name__,
            variation.content_type,
        )

        # On dark/green backgrounds the colored logo has no contrast — send the
        # white-monochrome variant instead (pre-recolored; the model only places it).
        logo_b64 = variation.logo_base64
        if should_use_white_logo(variation.content_type, blueprint):
            try:
                white = to_white_monochrome(base64.b64decode(logo_b64))
                logo_b64 = base64.b64encode(white).decode()
                log.info("ImageGenerator: applied white-monochrome logo (dark background)")
            except Exception as exc:
                log.warning("ImageGenerator: white-logo conversion failed (%s) — using original", exc)

        result = await self._provider.generate(
            logo_base64=logo_b64,
            logo_mime_type=variation.logo_mime_type,
            blueprint=blueprint,
            aspect_ratio=variation.aspect_ratio,
            content_type=variation.content_type,
            dimensions=variation.dimensoes,
        )
        log.info(
            "ImageGenerator: variation %d done — %d bytes (%s)",
            variation.variacao_numero,
            len(result.data),
            result.mime_type,
        )
        return result
