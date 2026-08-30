# funnel-forge/src/funnelforge/pipeline/phrase_registry.py
"""Cross-run persistent registry of published boilerplate-prone phrases (CARD-0007).

The intra-run uniqueness guard (`pipeline/uniqueness.py`) only compares drafts
written in the SAME run, so it can never catch a phrase that recurs across
DIFFERENT funnels/days on the same site -- e.g. the PRESELL opening CTA line
("Toque na opção certa e ..."), which an LLM tends to regenerate in
near-identical form run after run. Left unchecked, dozens of pages sharing
that literal sentence becomes a SCALED-CONTENT fingerprint (Google policy
risk). This module is the persistence layer for that cross-run check: a
small JSON file recording every phrase of a given `kind` seen so far, so
`validators/checks.py`'s `opening_line_unique` can compare today's opening
line against every prior one via `pipeline.uniqueness.jaccard`.

Pure stdlib, no pydantic/adapter dependency -- callers (steps.py) own the
Settings/deps plumbing and just pass this module a plain `Path`.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA_VERSION = 1
_SPACE_RE = re.compile(r"\s+")


def normalize_line(text: str) -> str:
    """Lowercase, strip accents/emoji/punctuation, collapse whitespace -- so
    two phrases differing only in casing, an emoji, or a stray comma still
    compare as the SAME phrase for idempotent recording."""
    decomposed = unicodedata.normalize("NFKD", text.strip().lower())
    kept: list[str] = []
    for ch in decomposed:
        if unicodedata.combining(ch):
            continue
        kept.append(ch if unicodedata.category(ch)[0] in ("L", "N") else " ")
    return _SPACE_RE.sub(" ", "".join(kept)).strip()


def _read_entries(path: Path) -> list[dict]:
    """Every entry in the registry at `path`, or [] if it is absent,
    unreadable, or not valid JSON in the expected shape -- ALWAYS tolerant,
    never raises."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(raw, dict):
        return []
    entries = raw.get("entries")
    return entries if isinstance(entries, list) else []


def load_lines(path: Path, kind: str) -> list[str]:
    """Every recorded raw `text` for `kind`, oldest first."""
    return [
        e["text"] for e in _read_entries(path)
        if isinstance(e, dict) and e.get("kind") == kind and isinstance(e.get("text"), str)
    ]


def record(path: Path, kind: str, text: str, slug: str, run_id: str) -> None:
    """Append `text` under `kind` to the registry at `path`, unless an entry
    of the SAME kind already normalizes to the same phrase (idempotent -- a
    resumed/retried page recording the same line twice never duplicates).
    Written atomically: a `.tmp` sibling is written in full, then renamed
    over `path` (same pattern as `Runner.checkpoint`)."""
    entries = _read_entries(path)
    target = normalize_line(text)
    already_recorded = any(
        isinstance(e, dict) and e.get("kind") == kind
        and normalize_line(e.get("text", "")) == target
        for e in entries
    )
    if already_recorded:
        return
    entries.append({
        "kind": kind,
        "text": text,
        "slug": slug,
        "run_id": run_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    })
    payload = {"version": _SCHEMA_VERSION, "entries": entries}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f"{path.name}.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
