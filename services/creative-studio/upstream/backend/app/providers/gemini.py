"""Gemini image provider."""

from __future__ import annotations

import base64
import json
import logging

import httpx

from app.config import settings
from app.prompts import get_gemini_guidelines
from app.providers.base import ImageProvider, ImageResult

log = logging.getLogger(__name__)

_GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:streamGenerateContent"
)

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)

_DIMENSIONS_MAP: dict[str, str] = {
    "1:1":  "1080x1080",
    "4:5":  "1080x1350",
    "9:16": "1080x1920",
    "16:9": "1920x1080",
    "3:4":  "1080x1440",
    "4:3":  "1440x1080",
    "2:3":  "1080x1620",
    "3:2":  "1620x1080",
    "4:1":  "2160x540",
    "21:9": "2520x1080",
}


class GeminiImageProvider(ImageProvider):
    """Calls the Gemini multimodal API to generate one image per invocation."""

    async def generate(
        self,
        logo_base64: str,
        logo_mime_type: str,
        blueprint: str,
        aspect_ratio: str = "",
        content_type: str = "meta-ads",
        dimensions: str = "",
    ) -> ImageResult:
        url = _GEMINI_ENDPOINT.format(model=settings.gemini_model)

        dimensoes = dimensions or _DIMENSIONS_MAP.get(aspect_ratio, "1080x1350")
        ratio_instruction = (
            f"CRITICAL CANVAS REQUIREMENT: Generate this image in {aspect_ratio} aspect ratio "
            f"({dimensoes} pixels). The composition MUST fill the entire canvas completely. "
            f"Do not add letterboxing, padding, or empty borders."
            if aspect_ratio
            else ""
        )

        brand_guidelines = get_gemini_guidelines(content_type)

        text_parts: list[dict] = [{"text": brand_guidelines}]
        if ratio_instruction:
            text_parts.append({"text": ratio_instruction})
        text_parts.append({"text": blueprint})

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": logo_mime_type or "image/png",
                                "data": logo_base64,
                            }
                        },
                        *text_parts,
                    ],
                }
            ],
            "generationConfig": {
                "responseModalities": ["IMAGE", "TEXT"],
            },
        }

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": settings.gemini_api_key,
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code != 200:
            raise RuntimeError(
                f"Gemini API error {resp.status_code}: {resp.text[:500]}"
            )

        return self._extract_image(resp.content)

    def _extract_image(self, raw: bytes) -> ImageResult:
        text = raw.decode("utf-8", errors="replace").strip()

        chunks: list[dict] = []
        try:
            parsed = json.loads(text)
            chunks = parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("{"):
                    try:
                        chunks.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

        for chunk in chunks:
            for candidate in chunk.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    inline = part.get("inlineData")
                    if inline and inline.get("data"):
                        img_bytes = base64.b64decode(inline["data"])
                        mime = inline.get("mimeType", "image/png")
                        log.debug("Gemini image extracted: %d bytes (%s)", len(img_bytes), mime)
                        return ImageResult(data=img_bytes, mime_type=mime)

        raise RuntimeError(
            "Gemini returned no image. Response preview: " + text[:300]
        )
