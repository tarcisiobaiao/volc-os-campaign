"""BrandGuardianAgent — validates logo metadata before generation.

For preset variants (aprova-main), logo data is loaded from backend assets —
no base64 is expected from the client.
For custom-upload, validates the base64 data sent by the client.
"""

from __future__ import annotations

import base64
import logging

from app.schemas import LogoPayload

log = logging.getLogger(__name__)

_ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
_PRESET_VARIANTS = {"aprova-main"}
_MIN_B64_LENGTH = 100


class BrandGuardianAgent:
    def validate(self, logo: LogoPayload) -> None:
        """Validate logo metadata. Raises ValueError on invalid payload."""

        # Preset logos are loaded server-side — no client data expected
        if logo.variant in _PRESET_VARIANTS:
            log.debug(
                "BrandGuardian: preset logo OK — variant=%s label=%r",
                logo.variant,
                logo.assetLabel,
            )
            return

        # custom-upload: full validation
        if not logo.data:
            raise ValueError("Custom logo data is empty.")

        if len(logo.data) < _MIN_B64_LENGTH:
            raise ValueError(
                f"Logo data too short ({len(logo.data)} chars). "
                "Expected a valid base64-encoded image."
            )

        try:
            base64.b64decode(logo.data, validate=True)
        except Exception:
            raise ValueError(
                "Logo data is not valid base64. "
                "Send raw base64 without 'data:' prefix."
            )

        if logo.mimeType.lower() not in _ALLOWED_MIME_TYPES:
            raise ValueError(
                f"Unsupported logo MIME type '{logo.mimeType}'. "
                f"Allowed: {sorted(_ALLOWED_MIME_TYPES)}"
            )

        log.debug(
            "BrandGuardian: custom logo OK — mime=%s bytes~=%d",
            logo.mimeType,
            len(logo.data) * 3 // 4,
        )
