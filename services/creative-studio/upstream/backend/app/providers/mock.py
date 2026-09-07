"""Mock image provider — generates solid-color PNG placeholders programmatically.

No external API calls. Safe to use in tests and local dev without API keys.
"""

from __future__ import annotations

import io
import hashlib

from PIL import Image, ImageDraw, ImageFont

from app.providers.base import ImageProvider, ImageResult
from app.utils.image import parse_dimensions as _parse_dimensions

_PALETTE = [
    (30, 58, 138),   # Navy blue
    (37, 99, 235),   # Blue
    (249, 115, 22),  # Orange
    (234, 179, 8),   # Yellow
    (15, 118, 110),  # Teal
    (109, 40, 217),  # Purple
]

_DIMENSIONS: dict[str, tuple[int, int]] = {
    "1:1":  (1080, 1080),
    "4:5":  (1080, 1350),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "3:4":  (1080, 1440),
    "4:3":  (1440, 1080),
}


class MockImageProvider(ImageProvider):
    async def generate(
        self,
        logo_base64: str,
        logo_mime_type: str,
        blueprint: str,
        aspect_ratio: str = "",
        content_type: str = "meta-ads",
        dimensions: str = "",
    ) -> ImageResult:
        w, h = _parse_dimensions(dimensions) or _DIMENSIONS.get(aspect_ratio, (1080, 1350))
        color_idx = int(hashlib.md5(blueprint.encode()).hexdigest(), 16) % len(_PALETTE)
        bg_color = _PALETTE[color_idx]

        img = Image.new("RGB", (w, h), bg_color)
        draw = ImageDraw.Draw(img)

        label = "APROVA\n[MOCK CRIATIVO]"
        try:
            font = ImageFont.load_default(size=60)
        except TypeError:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), label, font=font)
        x = (w - (bbox[2] - bbox[0])) // 2
        y = (h - (bbox[3] - bbox[1])) // 2
        draw.text((x + 2, y + 2), label, fill=(0, 0, 0, 128), font=font, align="center")
        draw.text((x, y), label, fill=(255, 255, 255), font=font, align="center")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return ImageResult(data=buf.getvalue(), mime_type="image/png")
