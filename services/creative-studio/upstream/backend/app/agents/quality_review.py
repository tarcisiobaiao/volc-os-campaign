"""QualityReviewAgent — validates generated image results."""

from __future__ import annotations

import logging

from app.providers.base import ImageResult

log = logging.getLogger(__name__)

_MIN_BYTES = 1024        # < 1 KB → almost certainly empty or broken
_ALLOWED_MIME = {"image/png", "image/jpeg", "image/jpg", "image/webp"}


class QualityReviewAgent:
    def is_valid(self, result: ImageResult) -> bool:
        """Return True if the result passes technical quality checks."""
        if not result.data:
            log.warning("QualityReview: rejected — empty data")
            return False

        if len(result.data) < _MIN_BYTES:
            log.warning(
                "QualityReview: rejected — image too small (%d bytes)", len(result.data)
            )
            return False

        if result.mime_type.lower() not in _ALLOWED_MIME:
            log.warning(
                "QualityReview: rejected — unexpected mime type '%s'", result.mime_type
            )
            return False

        log.debug(
            "QualityReview: accepted — %d bytes (%s)", len(result.data), result.mime_type
        )
        return True
