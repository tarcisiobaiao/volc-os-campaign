"""Image/base64 utility helpers."""

from __future__ import annotations

import base64
import io
import math

from PIL import Image


def strip_data_url_prefix(value: str) -> tuple[str, str]:
    """Accept a data URL or raw base64 and return (raw_base64, mime_type).

    The frontend's api.ts already strips the prefix before sending, but this
    handles both formats defensively.
    """
    if value.startswith("data:"):
        header, _, data = value.partition(",")
        mime = header.split(":")[1].split(";")[0] if ":" in header else "image/png"
        return data, mime
    return value, "image/png"


def base64_byte_size(b64: str) -> int:
    """Approximate decoded byte count without actually decoding."""
    return len(b64) * 3 // 4


# ── gpt-image-2 sizing ────────────────────────────────────────────────────────
# gpt-image-2 accepts arbitrary WIDTHxHEIGHT, but ALL of these must hold:
#   - both edges divisible by 16
#   - aspect ratio between 1:3 and 3:1
#   - max edge <= 3840px
#   - total pixels between 655,360 and 8,294,400
# So target sizes like 1080x1350 / 1200x628 / 1600x900 are NOT directly valid
# (edges not /16) and must be snapped before requesting generation.

_GPT_IMAGE_MIN_PIXELS = 655_360
_GPT_IMAGE_MAX_PIXELS = 8_294_400
_GPT_IMAGE_MAX_EDGE = 3840
# Standard always-valid fallbacks by orientation (work on every gpt-image model).
STANDARD_SIZES: dict[str, tuple[int, int]] = {
    "square": (1024, 1024),
    "portrait": (1024, 1536),
    "landscape": (1536, 1024),
}


def parse_dimensions(value: str) -> tuple[int, int] | None:
    """Parse a 'WxH' string into (width, height); return None if invalid."""
    if not value:
        return None
    try:
        w_str, _, h_str = value.lower().partition("x")
        w, h = int(w_str.strip()), int(h_str.strip())
    except (ValueError, AttributeError):
        return None
    if w <= 0 or h <= 0:
        return None
    return w, h


def _round16(x: float) -> int:
    return max(16, int(round(x / 16)) * 16)


def native_generation_size(
    target_w: int, target_h: int, max_edge: int = 1536
) -> tuple[int, int]:
    """Cheapest gpt-image-2-valid native size to render before upscaling to target.

    Preserves the target aspect ratio (so the model composes for the right canvas,
    no cropping needed downstream), caps the longest edge at ``max_edge`` to keep
    token cost low, snaps both edges to multiples of 16, and clamps to the model's
    pixel/edge/aspect constraints.
    """
    max_edge = min(max_edge, _GPT_IMAGE_MAX_EDGE)
    long_edge = max(target_w, target_h)
    scale = min(1.0, max_edge / long_edge)
    w = _round16(target_w * scale)
    h = _round16(target_h * scale)

    # Enforce 1:3..3:1 aspect (snap should never break it for our presets, but guard).
    if w > 3 * h:
        w = _round16(3 * h)
    if h > 3 * w:
        h = _round16(3 * w)

    # Enforce minimum pixel count by scaling AREA up proportionally (keeps aspect;
    # adding a constant to both edges would drag the ratio toward 1:1).
    if w * h < _GPT_IMAGE_MIN_PIXELS:
        factor = math.sqrt(_GPT_IMAGE_MIN_PIXELS / (w * h))
        w = _round16(w * factor)
        h = _round16(h * factor)
        # Nudge only the shorter edge to clear any residual rounding shortfall.
        while w * h < _GPT_IMAGE_MIN_PIXELS:
            if w <= h:
                w += 16
            else:
                h += 16

    # Enforce maximum pixel count / edge by scaling down.
    while w * h > _GPT_IMAGE_MAX_PIXELS or max(w, h) > _GPT_IMAGE_MAX_EDGE:
        w = _round16(w * 0.95)
        h = _round16(h * 0.95)

    return w, h


def orientation_of(target_w: int, target_h: int) -> str:
    if target_w == target_h:
        return "square"
    return "portrait" if target_w < target_h else "landscape"


def is_valid_gpt_image_size(w: int, h: int) -> bool:
    """True if ``WxH`` is a size gpt-image-2 will accept directly.

    Per OpenAI docs: both edges divisible by 16, aspect ratio between 1:3 and 3:1,
    longest edge <= 3840px. Used to guarantee (via test) that every front-end format
    is adapted to a valid generation size before it reaches the API.
    """
    if w <= 0 or h <= 0:
        return False
    if w % 16 != 0 or h % 16 != 0:
        return False
    if max(w, h) > _GPT_IMAGE_MAX_EDGE:
        return False
    ratio = w / h
    return (1 / 3) - 1e-9 <= ratio <= 3 + 1e-9


def fit_cover(img_bytes: bytes, target_w: int, target_h: int) -> bytes:
    """Resize to EXACTLY ``target_w x target_h`` without distortion.

    Scale-to-cover + center-crop: when the source already matches the target aspect
    ratio (the normal path, since ``native_generation_size`` preserves it) this is a
    pure scale with no crop. When aspects differ — the size-fallback path or a future
    out-of-1:3..3:1 ratio — it scales to cover and center-crops the overflow instead
    of stretching. Ad creatives want a filled canvas, so cover beats letterboxing.
    """
    with Image.open(io.BytesIO(img_bytes)) as img:
        if img.size == (target_w, target_h) and img.mode == "RGB":
            return img_bytes
        rgb = img.convert("RGB")
        src_w, src_h = rgb.size
        scale = max(target_w / src_w, target_h / src_h)
        new_w = max(target_w, round(src_w * scale))
        new_h = max(target_h, round(src_h * scale))
        resized = rgb.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        cropped = resized.crop((left, top, left + target_w, top + target_h))
        out = io.BytesIO()
        cropped.save(out, format="PNG")
        return out.getvalue()


# ── Logo treatment (white monochrome on dark backgrounds) ─────────────────────
# Aprova green/dark are the DOMINANT backgrounds, so the colored logo has poor
# contrast there. The robust fix is to pre-recolor the logo to white with Pillow
# (the image model cannot reliably recolor a reference asset) and pick the variant
# by the background tone the blueprint describes.

# Explicit logo-treatment keywords the strategist is told to emit (SECTION 5).
_WHITE_LOGO_HINTS = (
    "white monochrome", "white version", "white logo", "logo branco", "logo branca",
    "monocromática branca", "monocromatica branca", "logo in white", "white aprova logo",
)
_COLOR_LOGO_HINTS = (
    "original colors", "original-color", "full color logo", "colored logo",
    "logo colorido", "logo colorida", "cores originais", "logo: original",
)
# Background-tone cues (secondary signal when no explicit logo treatment is stated).
_DARK_BG_HINTS = (
    "dark background", "fundo escuro", "green background", "deep green background",
    "navy background", "dark gradient", "full bleed", "darkened", "photographic background",
    "solid aprova green", "solid deep green", "#00a859", "#006837", "#1b2a49",
)
_LIGHT_BG_HINTS = (
    "white background", "fundo branco", "light background", "fundo claro",
    "off-white background", "#ffffff background", "clean white",
)


def should_use_white_logo(content_type: str, blueprint: str = "") -> bool:
    """Whether the logo should be placed as WHITE MONOCHROME (dark/green/photo
    background) instead of its original colors (white/light background).

    Priority: explicit logo treatment stated in the blueprint > background tone cues
    > content-type default (meta-ads/news are dark-dominant, pinterest is light)."""
    bl = blueprint.lower()
    if any(h in bl for h in _WHITE_LOGO_HINTS):
        return True
    if any(h in bl for h in _COLOR_LOGO_HINTS):
        return False
    if any(h in bl for h in _DARK_BG_HINTS):
        return True
    if any(h in bl for h in _LIGHT_BG_HINTS):
        return False
    return content_type != "pinterest"


def to_white_monochrome(png_bytes: bytes) -> bytes:
    """Recolor a transparent-background logo to solid white, preserving its alpha
    mask — the standard white-logo treatment for dark backgrounds."""
    with Image.open(io.BytesIO(png_bytes)) as im:
        rgba = im.convert("RGBA")
        alpha = rgba.getchannel("A")
        if alpha.getextrema()[0] == 255:
            # No transparency (logo baked on a solid bg): derive the mask from
            # luminance so the marks become white on transparent, not a white box.
            alpha = rgba.convert("L").point(lambda p: 0 if p > 240 else 255)
        white = Image.new("RGBA", rgba.size, (255, 255, 255, 0))
        white.putalpha(alpha)
        out = io.BytesIO()
        white.save(out, format="PNG")
        return out.getvalue()
