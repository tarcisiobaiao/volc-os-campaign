"""OpenAI gpt-image-2 provider via Images Edit API.

gpt-image-2 accepts arbitrary WIDTHxHEIGHT, but every requested size must have
both edges divisible by 16 (so platform sizes like 1080x1350 / 1200x628 / 1600x900
are NOT directly valid). Cost scales with pixel area, so the cheap-but-sharp path
is: render at a cost-capped native size that matches the TARGET aspect ratio, then
upscale locally with Pillow (LANCZOS) to the exact requested pixels — $0 extra API
cost versus paying ~5x for a native 4K render.
"""

from __future__ import annotations

import base64
import io
import logging

from openai import AsyncOpenAI, BadRequestError

from app.config import settings
from app.prompts import get_gemini_guidelines
from app.providers.base import ImageProvider, ImageResult
from app.utils.image import (
    STANDARD_SIZES,
    fit_cover,
    native_generation_size,
    orientation_of,
    parse_dimensions,
)

log = logging.getLogger(__name__)

# Fallback target pixels when the request omits exact dimensions (legacy callers).
_RATIO_FALLBACK: dict[str, tuple[int, int]] = {
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "3:4": (1080, 1440),
    "4:3": (1440, 1080),
    "2:3": (1080, 1620),
    "3:2": (1620, 1080),
}


class OpenAIImageProvider(ImageProvider):
    """Calls the OpenAI Images Edit API with gpt-image-2, sending the logo as reference."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    def _resolve_target(self, aspect_ratio: str, dimensions: str) -> tuple[int, int]:
        target = parse_dimensions(dimensions)
        if target:
            return target
        return _RATIO_FALLBACK.get(aspect_ratio, (1080, 1350))

    async def _edit(self, logo_bytes: bytes, prompt: str, size: str):
        logo_file = io.BytesIO(logo_bytes)
        logo_file.name = "aprova-logo.png"
        return await self._client.images.edit(
            model=settings.openai_image_model,
            image=logo_file,
            prompt=prompt,
            size=size,
            quality=settings.image_quality,
            n=1,
        )

    async def generate(
        self,
        logo_base64: str,
        logo_mime_type: str,
        blueprint: str,
        aspect_ratio: str = "",
        content_type: str = "meta-ads",
        dimensions: str = "",
    ) -> ImageResult:
        target_w, target_h = self._resolve_target(aspect_ratio, dimensions)
        native_w, native_h = native_generation_size(
            target_w, target_h, settings.image_native_max_edge
        )
        target_label = f"{target_w}x{target_h}"

        brand_guidelines = get_gemini_guidelines(content_type)
        ratio_label = aspect_ratio or f"{target_w}:{target_h}"
        prompt = (
            f"{brand_guidelines}\n\n"
            f"The provided image is the official Aprova Concursos logo, ALREADY in the correct color "
            f"treatment for this design (white monochrome for dark/green/photo backgrounds, original "
            f"colors for white/light backgrounds). "
            f"Place it exactly as-is in the designated corner — small, clean, unmodified. "
            f"Do NOT recolor, redesign, or redraw it. Treat it as a pre-existing asset to embed in the layout.\n\n"
            f"CANVAS: {ratio_label} aspect ratio, final deliverable {target_label} pixels. "
            f"Compose for this exact aspect ratio and fill the entire canvas. No letterboxing or empty borders.\n\n"
            f"VISUAL BLUEPRINT:\n{blueprint}"
        )

        logo_bytes = base64.b64decode(logo_base64)

        log.info(
            "OpenAIImageProvider: target=%s native=%dx%d quality=%s content_type=%s",
            target_label,
            native_w,
            native_h,
            settings.image_quality,
            content_type,
        )

        size = f"{native_w}x{native_h}"
        try:
            response = await self._edit(logo_bytes, prompt, size)
        except BadRequestError as exc:
            # Only a size/parameter rejection is fixable by retrying at a standard size.
            # Anything else (auth, quota, unrelated 400) must surface with its true cause
            # instead of being silently retried at a useless larger size.
            msg = str(exc).lower()
            if not any(k in msg for k in ("size", "dimension", "pixel", "resolution")):
                raise
            fallback = STANDARD_SIZES[orientation_of(target_w, target_h)]
            fallback_size = f"{fallback[0]}x{fallback[1]}"
            log.warning(
                "OpenAIImageProvider: native size %s rejected (%s) — retrying at standard %s",
                size,
                exc,
                fallback_size,
            )
            response = await self._edit(logo_bytes, prompt, fallback_size)

        if not response.data:
            raise RuntimeError("gpt-image-2 returned no data")
        img_b64 = response.data[0].b64_json
        if not img_b64:
            raise RuntimeError("gpt-image-2 returned empty b64_json")

        img_bytes = base64.b64decode(img_b64)
        # Scale-to-cover + center-crop to the EXACT target pixels (no distortion).
        img_bytes = fit_cover(img_bytes, target_w, target_h)
        log.info("OpenAIImageProvider: delivered %s — %d bytes", target_label, len(img_bytes))
        return ImageResult(data=img_bytes, mime_type="image/png")
