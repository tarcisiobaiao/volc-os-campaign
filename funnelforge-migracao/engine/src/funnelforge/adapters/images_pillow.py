from __future__ import annotations
import io
from pathlib import Path
from PIL import Image


class PillowImageProcessor:
    def to_webp(
        self, data: bytes, out_path: Path, quality: int = 80
    ) -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.save(out_path, format="WEBP", quality=quality, method=6)
        return out_path

    def screenshot_to_webp(
        self, data: bytes, out_path: Path, *,
        max_height: int = 1200, max_width: int = 800, quality: int = 80,
        profile: str = "mobile", desktop_max_width: int = 1200,
    ) -> Path:
        """Process a raw PNG screenshot into a body-ready webp (CARD-0005 / B2):

        ``profile="mobile"`` (default, legacy behaviour):
        1. DETERMINISTIC crop from the TOP down to at most ``max_height`` px --
           drops the below-the-fold overflow a full-page capture may carry;
        2. downscale to at most ``max_width`` px wide (aspect preserved);
        3. encode webp at ``quality``.

        ``profile="desktop"``: NO height crop -- a desktop capture (1366x768
        viewport) is already the above-the-fold, so squeezing it into the
        mobile 1200px-height box would be wrong. Just downscale to at most
        ``desktop_max_width`` px wide (aspect preserved) and encode.

        Intelligent vision/OCR cropping of the useful screen area (ignoring
        header/cookie banners) is an EXPLICIT follow-up (v2) -- here the crop is
        purely deterministic. Same webp encoder settings as ``to_webp``."""
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.open(io.BytesIO(data)).convert("RGB")
        if profile == "desktop":
            width, height = img.size
            if width > desktop_max_width:
                new_height = max(1, round(height * desktop_max_width / width))
                img = img.resize((desktop_max_width, new_height))
        else:
            width, height = img.size
            if height > max_height:
                img = img.crop((0, 0, width, max_height))
            width, height = img.size
            if width > max_width:
                new_height = max(1, round(height * max_width / width))
                img = img.resize((max_width, new_height))
        img.save(out_path, format="WEBP", quality=quality, method=6)
        return out_path
