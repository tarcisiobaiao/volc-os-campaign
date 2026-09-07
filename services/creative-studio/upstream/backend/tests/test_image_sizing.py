"""gpt-image-2 sizing — guarantee every front format adapts to a valid size,
and that fit_cover hits exact target pixels without distortion.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.utils.image import (
    fit_cover,
    is_valid_gpt_image_size,
    native_generation_size,
    parse_dimensions,
)

# Mirror of the dimensions offered by src/components/FormatSelector.tsx + fixed
# content-type ratios (news 4:5, pinterest 9:16). Keep in sync with the front.
FRONT_FORMATS = [
    "1080x1080",  # 1:1
    "1080x1350",  # 4:5
    "1080x1920",  # 9:16
    "1920x1080",  # 16:9
    "1200x628",   # 1.91:1
    "1600x900",   # 16:9
    "2160x3840",  # 9:16 4K
    "3840x2160",  # 16:9 4K
]


@pytest.mark.parametrize("dims", FRONT_FORMATS)
def test_every_front_format_maps_to_valid_gpt_image_size(dims):
    w, h = parse_dimensions(dims)
    nw, nh = native_generation_size(w, h, max_edge=1536)
    assert is_valid_gpt_image_size(nw, nh), f"{dims} -> {nw}x{nh} is not a valid gpt-image-2 size"


def test_validity_predicate_rejects_bad_sizes():
    assert not is_valid_gpt_image_size(1080, 1350)   # edges not /16
    assert not is_valid_gpt_image_size(4000, 1024)   # edge > 3840
    assert not is_valid_gpt_image_size(3200, 1024)   # ratio > 3:1
    assert is_valid_gpt_image_size(1024, 1024)       # standard square
    assert is_valid_gpt_image_size(1536, 1024)       # standard landscape


def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 120, 80)).save(buf, format="PNG")
    return buf.getvalue()


def test_fit_cover_same_aspect_is_exact():
    out = fit_cover(_png(864, 1080), 1080, 1350)  # 4:5 -> 4:5
    with Image.open(io.BytesIO(out)) as img:
        assert img.size == (1080, 1350)


def test_fit_cover_different_aspect_no_distortion():
    # Source 3:2, target 1.91:1 — must crop-to-fill, never stretch.
    out = fit_cover(_png(1536, 1024), 1200, 628)
    with Image.open(io.BytesIO(out)) as img:
        assert img.size == (1200, 628)
