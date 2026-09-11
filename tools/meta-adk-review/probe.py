"""Single paid capability probe. Exact model and search grounding are mandatory."""
from __future__ import annotations

import argparse
import asyncio
from importlib.metadata import version
import json
from pathlib import Path

from google.genai import types

from auth import gemini_client
from config import MODEL, THINKING


async def probe(credential_root: Path, receipt: Path) -> int:
    receipt.parent.mkdir(parents=True, exist_ok=True)
    if receipt.exists():
        raise RuntimeError("probe receipt already exists")
    receipt.write_text(json.dumps({
        "status": "dispatch_reserved",
        "requested_model": MODEL,
        "thinking": THINKING,
        "google_search": True,
    }, indent=2))
    api = gemini_client(credential_root.resolve())
    result: dict[str, object] = {
        "requested_model": MODEL,
        "thinking": THINKING,
        "google_search": True,
        "google_adk": version("google-adk"),
        "google_genai": version("google-genai"),
    }
    try:
        response = await api.aio.models.generate_content(
            model=MODEL,
            contents=(
                "Use Google Search now. Find the official Meta flexible ad format documentation. "
                "Return one direct developers.facebook.com URL and one sentence naming the documented "
                "supported campaign objectives. This is only a capability probe."
            ),
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.HIGH,
                    include_thoughts=False,
                ),
                tools=[types.Tool(google_search=types.GoogleSearch())],
                max_output_tokens=3_000,
            ),
        )
        grounding = response.candidates[0].grounding_metadata if response.candidates else None
        grounded = bool(grounding and grounding.web_search_queries and grounding.grounding_chunks)
        result.update({
            "effective_model": response.model_version,
            "model_verified": response.model_version == MODEL,
            "grounding_verified": grounded,
            "usage": response.usage_metadata.model_dump(mode="json", exclude_none=True)
            if response.usage_metadata else {},
            "grounding": grounding.model_dump(mode="json", exclude_none=True) if grounding else {},
            "visible_text": response.text,
        })
        result["status"] = "verified" if result["model_verified"] and grounded else "capability_unverified"
    except Exception as exc:
        result.update({
            "status": "provider_error",
            "error_type": type(exc).__name__,
            "error_code": getattr(exc, "code", None),
        })
    finally:
        await api.aio.aclose()
        api.close()
    receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({
        key: value for key, value in result.items()
        if key not in {"visible_text", "grounding"}
    }, ensure_ascii=False))
    return 0 if result["status"] == "verified" else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credential-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    arguments = parser.parse_args()
    raise SystemExit(asyncio.run(probe(arguments.credential_root, arguments.receipt)))
