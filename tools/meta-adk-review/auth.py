"""Host-only Gemini authentication. Values are never exposed as agent tools."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values
from google import genai
from google.genai import types


def gemini_client(credential_root: Path) -> genai.Client:
    values: dict[str, str | None] = {}
    for path in (
        credential_root / ".env.server",
        credential_root / "backend/.env",
        credential_root / "backend/.env.local",
    ):
        if path.is_file():
            values.update(dotenv_values(path, interpolate=False))
    key = os.environ.get("GEMINI_API_KEY") or values.get("GEMINI_API_KEY") or values.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("Gemini credential unavailable to host")
    return genai.Client(
        api_key=key,
        vertexai=False,
        http_options=types.HttpOptions(
            timeout=180_000,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
