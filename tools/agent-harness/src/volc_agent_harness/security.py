"""Redução de ambiente e redação de logs dos subprocessos."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping


_SAFE_ENV_NAMES = {
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "TMPDIR",
    "TERM",
    "LANG",
    "CODEX_HOME",
    "CLAUDE_CONFIG_DIR",
}

_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\b")
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{12,}")
_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY|SERVICE_ROLE)[A-Z0-9_]*)\s*[:=]\s*([^\s,;]+)"
)


def sanitized_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    source = source or os.environ
    result = {
        key: value
        for key, value in source.items()
        if key in _SAFE_ENV_NAMES or key.startswith("LC_")
    }
    result.setdefault("LANG", "en_US.UTF-8")
    return result


def redact(text: str) -> str:
    text = _JWT.sub("[REDACTED_JWT]", text)
    text = _BEARER.sub("Bearer [REDACTED]", text)
    return _ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
