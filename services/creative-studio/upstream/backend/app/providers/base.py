from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ImageResult:
    data: bytes
    mime_type: str


class ImageProvider(ABC):
    """Abstract interface for image generation backends."""

    @abstractmethod
    async def generate(
        self,
        logo_base64: str,
        logo_mime_type: str,
        blueprint: str,
        aspect_ratio: str = "",
        content_type: str = "meta-ads",
        dimensions: str = "",
    ) -> ImageResult:
        """Generate one image from a logo + visual blueprint prompt.

        dimensions: exact target pixels 'WxH' (e.g. '1080x1350'). When provided
        it takes precedence over aspect_ratio for sizing the output.
        """
