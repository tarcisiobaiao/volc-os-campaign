"""
Seed Queue Builder — faithful port of n8n-peneirador-kw.json node
"🌱 Seed Queue Builder1": parse the Seed Optimizer JSON, dedupe by lowercased
keyword, require >= 3, cap at 5, attach rank.
"""
from __future__ import annotations

from typing import Any, Dict, List


class SeedQueueError(ValueError):
    """Raised when the Seed Optimizer did not return >= 3 valid seeds."""


def parse_seed_optimizer_output(
    ai_output: Any, *, min_seeds: int = 3, max_seeds: int = 5
) -> List[Dict[str, Any]]:
    """Port of '🌱 Seed Queue Builder1'.

    Accepts the parsed object {seed_keywords:[...]} (or a raw list). Returns a
    list of {seed_keyword, seed_angle, seed_reasoning, seed_rank}.
    """
    if isinstance(ai_output, dict):
        candidates = ai_output.get("seed_keywords")
    elif isinstance(ai_output, list):
        candidates = ai_output
    else:
        candidates = None
    if not isinstance(candidates, list):
        candidates = []

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for entry in candidates:
        if isinstance(entry, dict):
            raw_kw = entry.get("keyword") or entry.get("seed_keyword") or ""
            angle = entry.get("angle")
            reasoning = entry.get("reasoning") or ""
        else:
            raw_kw = entry
            angle = None
            reasoning = ""
        keyword = str(raw_kw or "").strip().lower()
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        deduped.append({"keyword": keyword, "angle": angle, "reasoning": reasoning})

    if len(deduped) < min_seeds:
        raise SeedQueueError(
            f"O AI Seed Optimizer não retornou ao menos {min_seeds} seeds válidas."
        )

    return [
        {
            "seed_keyword": seed["keyword"],
            "seed_angle": seed["angle"],
            "seed_reasoning": seed["reasoning"],
            "seed_rank": i + 1,
        }
        for i, seed in enumerate(deduped[:max_seeds])
    ]


def fallback_seeds(main_keyword: str, *, max_seeds: int = 5) -> List[Dict[str, Any]]:
    """Deterministic seeds when no LLM is available (mock path).

    Position 1 is ALWAYS the original keyword (ipsis litteris rule), followed by
    a few realistic angle variations.
    """
    base = (main_keyword or "").strip()
    variants = [
        (base, "institucional"),
        (f"{base} requisitos", "dor"),
        (f"{base} como funciona", "alivio_popular"),
        (f"{base} online", "operacional"),
        (f"{base} valor", "cultural_local"),
    ]
    seen = set()
    out: List[Dict[str, Any]] = []
    for kw, angle in variants:
        key = kw.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "seed_keyword": key,
                "seed_angle": angle,
                "seed_reasoning": "[mock] seed determinística (sem LLM).",
                "seed_rank": len(out) + 1,
            }
        )
        if len(out) >= max_seeds:
            break
    return out
