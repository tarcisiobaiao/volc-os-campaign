"""Inspect one parallel Meta ADK run without making provider calls."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def lane_status(run_dir: Path) -> dict[str, Any]:
    events = []
    event_file = run_dir / "events.jsonl"
    if event_file.exists():
        for line in event_file.read_text().splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                break
    report_path = run_dir / "REPORT.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    calls = Counter(row.get("agent") for row in events if row.get("event") == "dispatch")
    last_time = datetime.fromisoformat(events[-1]["time"]) if events else None
    return {
        "status": report.get("status", "running_or_not_started"),
        "calls_by_agent": dict(calls),
        "tokens": report.get("tokens", {}).get("total", sum(
            row.get("usage", {}).get("total_token_count", 0) or 0
            for row in events if row.get("event") == "response"
        )),
        "grounded_responses": sum(bool(row.get("grounded")) for row in events),
        "edits": sum(row.get("event") == "edit" for row in events),
        "rounds": [row.get("verdict") for row in events if row.get("event") == "round"],
        "last_event": events[-1].get("event") if events else None,
        "seconds_since_event": round((datetime.now(timezone.utc) - last_time).total_seconds())
        if last_time else None,
    }


def overall(root: Path) -> dict[str, Any]:
    manifest_path = root / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    lanes = {}
    runs = root / "runs"
    if runs.exists():
        for child in sorted(runs.iterdir()):
            if child.is_dir():
                lanes[child.name] = lane_status(child)
    return {
        "root": str(root.resolve()),
        "manifest_status": manifest.get("status", "missing_manifest"),
        "model": manifest.get("model"),
        "thinking": manifest.get("thinking"),
        "lanes": lanes,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(overall(arguments.run_root), ensure_ascii=False, indent=2))
