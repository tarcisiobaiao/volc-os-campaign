"""Runtime-mutable API keys.

Lets the frontend change the OpenAI / Gemini keys at runtime (without editing
.env or redeploying). On persistent local/VM hosts, overrides are persisted to
runtime_config.json (gitignored). On serverless hosts such as Vercel, the file
system may be read-only or ephemeral, so Vercel environment variables remain the
production source of truth.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import settings

_PATH = Path(__file__).parent.parent / "runtime_config.json"
_KEYS = ("openai_api_key", "gemini_api_key")

log = logging.getLogger(__name__)


def _read() -> dict:
    if not _PATH.exists():
        return {}
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - never let a bad file crash startup
        log.warning("runtime_config: could not read %s (%s)", _PATH.name, exc)
        return {}


def load_into_settings() -> None:
    """Apply persisted overrides onto the in-memory settings (call at startup)."""
    data = _read()
    applied = []
    for key in _KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            setattr(settings, key, value.strip())
            applied.append(key)
    if applied:
        log.info("runtime_config: applied overrides for %s", applied)


def update(updates: dict) -> list[str]:
    """Persist + apply key overrides. Returns the list of changed keys."""
    data = _read()
    changed = []
    for key in _KEYS:
        value = updates.get(key)
        if isinstance(value, str) and value.strip():
            data[key] = value.strip()
            setattr(settings, key, value.strip())
            changed.append(key)
    if changed:
        try:
            _PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
            log.info("runtime_config: updated %s", changed)
        except OSError as exc:
            log.warning(
                "runtime_config: could not persist overrides to %s (%s); "
                "using in-memory values for this process",
                _PATH.name,
                exc,
            )
    return changed


def mask(value: str) -> str:
    """Mask a secret for display, keeping a hint of which key it is."""
    if not value:
        return ""
    return f"{value[:6]}…{value[-4:]}" if len(value) > 12 else "•••"


def status() -> dict:
    """Masked, safe-to-expose view of which keys are configured and from where."""
    overrides = _read()

    def src(key: str) -> str:
        return "runtime" if overrides.get(key) else ("env" if getattr(settings, key) else "missing")

    return {
        "openai": {"configured": bool(settings.openai_api_key), "masked": mask(settings.openai_api_key), "source": src("openai_api_key")},
        "gemini": {"configured": bool(settings.gemini_api_key), "masked": mask(settings.gemini_api_key), "source": src("gemini_api_key")},
    }
