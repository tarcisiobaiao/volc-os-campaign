"""ZipPackager — assembles generated images into a ZIP archive."""

from __future__ import annotations

import io
import zipfile
from datetime import datetime

from app.providers.base import ImageResult


def _ext(mime_type: str) -> str:
    return {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/webp": "webp",
    }.get(mime_type.lower(), "png")


class ZipPackager:
    def pack(self, images: list[tuple[int, ImageResult]]) -> bytes:
        """Pack images into a ZIP and return raw bytes."""
        buf = io.BytesIO()

        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for num, img in sorted(images, key=lambda t: t[0]):
                ext = _ext(img.mime_type)
                filename = f"aprova-ad-{num}.{ext}"
                zf.writestr(filename, img.data)

        return buf.getvalue()
