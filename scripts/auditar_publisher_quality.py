#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.publisher_quality import SnapshotInput, build_publisher_surface_snapshot, deterministic_json
from backend.app.publisher_quality.fetch import fetch_public_https_once


def _load_payload(path: Path | None) -> dict:
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventário read-only PublisherSurfaceSnapshot v1")
    parser.add_argument("--input", type=Path, help="Artefato JSON local: FunnelForge AdManifest + HTML/contexto sanitizado")
    parser.add_argument("--url", help="URL pública HTTPS autorizada, uma por execução; sem auth/cookies/forms")
    parser.add_argument("--output", type=Path, help="Arquivo JSON de saída")
    args = parser.parse_args(argv)

    payload = _load_payload(args.input)
    if args.url:
        if payload.get("html"):
            raise SystemExit("--url não pode ser combinado com html já presente no artefato")
        fetched = fetch_public_https_once(args.url)
        payload.update({"canonical_url": fetched["url"], "html": fetched["html"], "source": "public_https_read"})
    if not payload:
        raise SystemExit("informe --input e/ou --url")

    snapshot = build_publisher_surface_snapshot(SnapshotInput.from_mapping(payload))
    output = deterministic_json(snapshot)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
