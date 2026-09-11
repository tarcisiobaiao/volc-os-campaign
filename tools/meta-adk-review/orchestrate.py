"""Prepare isolated worktrees and run all focused ADK lanes concurrently."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from config import LANES, MODEL, THINKING


def git(source: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()


def require_committed_harness(source: Path, base: str) -> None:
    subprocess.check_call(
        ["git", "-C", str(source), "cat-file", "-e", f"{base}:tools/meta-adk-review/run_lane.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def runtime_launcher(path: Path) -> Path:
    """Return an absolute venv launcher without following its interpreter symlink."""
    return path.absolute()


def prepare_worktree(source: Path, root: Path, lane_name: str, base: str, run_id: str) -> tuple[Path, str]:
    workspace = root / "worktrees" / lane_name
    branch = f"sprint/meta-adk-v2-{lane_name}-{run_id.lower()}"
    workspace.parent.mkdir(parents=True, exist_ok=True)
    if workspace.exists():
        raise RuntimeError(f"refusing existing worktree path: {workspace}")
    subprocess.check_call(
        ["git", "-C", str(source), "worktree", "add", "-b", branch, str(workspace), base]
    )
    return workspace, branch


async def stream_lane(
    runtime: Path,
    source: Path,
    root: Path,
    lane_name: str,
    workspace: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    lane_run = root / "runs" / lane_name
    lane_run.parent.mkdir(parents=True, exist_ok=True)
    log_path = root / "logs" / f"{lane_name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(runtime), str(workspace / "tools/meta-adk-review/run_lane.py"),
        "--workspace", str(workspace),
        "--run-dir", str(lane_run),
        "--credential-root", str(source),
        "--lane", lane_name,
        "--rounds", str(args.rounds),
        "--max-calls", str(args.max_calls),
        "--max-tokens", str(args.max_tokens),
        "--max-edits", str(args.max_edits),
        "--timeout", str(args.timeout),
    ]
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "en_US.UTF-8",
        "PYTHONUNBUFFERED": "1",
        "VOLC_META_ADK_DEPENDENCY_ROOT": str(source),
    }
    with log_path.open("wb") as log:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=workspace,
            env=env,
            stdout=log,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        returncode = await process.wait()
    report_path = lane_run / "REPORT.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {
        "status": "missing_report",
        "lane": lane_name,
    }
    return {
        "lane": lane_name,
        "returncode": returncode,
        "workspace": str(workspace),
        "run_dir": str(lane_run),
        "log": str(log_path),
        "report": report,
    }


async def main(args: argparse.Namespace) -> int:
    source = args.source.resolve()
    # Keep the venv launcher path. Path.resolve() follows bin/python to the
    # global interpreter and silently drops the venv site-packages.
    runtime = runtime_launcher(args.runtime)
    base = args.base or git(source, "rev-parse", "HEAD")
    require_committed_harness(source, base)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = (args.output_root / f"volc-meta-adk-v2-{run_id}").resolve()
    root.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "status": "preparing",
        "source": str(source),
        "base": base,
        "model": MODEL,
        "thinking": THINKING,
        "lanes": {},
        "limits_per_lane": {
            "rounds": args.rounds,
            "max_calls": args.max_calls,
            "max_tokens": args.max_tokens,
            "max_edits": args.max_edits,
            "timeout_seconds": args.timeout,
        },
        "external_mutations_allowed": False,
    }
    manifest_path = root / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    probe_command = [
        str(runtime), str(source / "tools/meta-adk-review/probe.py"),
        "--credential-root", str(source),
        "--receipt", str(root / "PROBE.json"),
    ]
    probe = await asyncio.create_subprocess_exec(*probe_command, cwd=source)
    if await probe.wait() != 0:
        manifest["status"] = "probe_failed"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        print(json.dumps({"status": "probe_failed", "root": str(root)}))
        return 2

    prepared: dict[str, Path] = {}
    for lane_name in sorted(LANES):
        workspace, branch = prepare_worktree(source, root, lane_name, base, run_id)
        prepared[lane_name] = workspace
        manifest["lanes"][lane_name] = {"workspace": str(workspace), "branch": branch}
    manifest["status"] = "prepared" if args.prepare_only else "running"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps({"status": manifest["status"], "root": str(root), "lanes": sorted(prepared)}))
    if args.prepare_only:
        return 0

    results = await asyncio.gather(*(
        stream_lane(runtime, source, root, lane_name, workspace, args)
        for lane_name, workspace in prepared.items()
    ))
    manifest["results"] = results
    manifest["status"] = "completed_requires_lead_review"
    manifest["totals"] = {
        "calls": sum(item["report"].get("calls", 0) for item in results),
        "tokens": sum(item["report"].get("tokens", {}).get("total", 0) for item in results),
        "edits": sum(item["report"].get("edits", 0) for item in results),
        "candidate_lanes": [
            item["lane"] for item in results
            if item["report"].get("status") == "candidate_requires_lead_review"
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps({
        "status": manifest["status"],
        "root": str(root),
        "totals": manifest["totals"],
    }, ensure_ascii=False))
    return 0 if all(item["returncode"] == 0 for item in results) else 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--source", type=Path, required=True)
    result.add_argument("--runtime", type=Path, required=True)
    result.add_argument("--output-root", type=Path, default=Path("/private/tmp"))
    result.add_argument("--base")
    result.add_argument("--rounds", type=int, choices=(1, 2, 3), default=2)
    result.add_argument("--max-calls", type=int, default=26)
    result.add_argument("--max-tokens", type=int, default=180_000)
    result.add_argument("--max-edits", type=int, default=12)
    result.add_argument("--timeout", type=int, default=1_800)
    result.add_argument("--prepare-only", action="store_true")
    return result


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(parser().parse_args())))
