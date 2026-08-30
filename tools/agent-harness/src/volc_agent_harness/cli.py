"""CLI para executar investigação ou implementação isolada com revisão."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .mission import run
from .models import MissionSpec


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mission", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    mission = MissionSpec.model_validate_json(
        args.mission.read_text(encoding="utf-8")
    )
    run_dir, result = run(args.repo, mission)
    print(f"run: {result['run_id']}")
    print(f"base: {result['base_sha']}")
    print(f"resultado: {'ok' if result['ok'] else 'com falhas'}")
    if result.get("writer_commit"):
        print(f"commit do writer: {result['writer_commit']}")
    if result.get("candidate_status"):
        print(f"candidato: {result['candidate_status']}")
    for worker in result["workers"]:
        print(
            f"- {worker['worker_id']} ({worker['provider']} / "
            f"{worker.get('model') or 'default'} / {worker.get('effort', 'default')}): "
            f"{'ok' if worker['ok'] else worker.get('error', 'falhou')}"
        )
    print(f"artefatos: {run_dir}")
    accepted = result["ok"] and result.get("candidate_status") not in {
        "changes_requested",
        "blocked",
    }
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
