"""Execute one focused Meta lane in a pre-created isolated Git worktree."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from google.adk.agents.run_config import RunConfig
from google.adk.runners import InMemoryRunner

from auth import gemini_client
from config import LANES, lane
from host import Host, safe
from workflow import build_workflow
from tasks import TICKETS
from ticket_workflow import build_ticket_workflow


async def execute(args: argparse.Namespace) -> int:
    ticket = TICKETS[args.task] if args.task else None
    selected = ticket.scoped_lane() if ticket else lane(args.lane)
    host: Host | None = None
    api = None
    runner = None
    try:
        host = Host(args, selected)
        api = gemini_client(args.credential_root.resolve())
        root_workflow = (build_ticket_workflow(host, api, ticket, args.rounds) if ticket
                         else build_workflow(host, api, selected, args.rounds))
        runner = InMemoryRunner(node=root_workflow, app_name=f"volc_meta_{selected.slug}")
        async with asyncio.timeout(args.timeout):
            await runner.run_debug(
                "Execute a missão atribuída, implementando e testando os critérios de aceite fornecidos.",
                quiet=True,
                run_config=RunConfig(max_llm_calls=args.max_calls),
            )
        return 0 if host.status == 'candidate_requires_lead_review' else 1
    except Exception as exc:
        if host:
            host.status = "stopped_" + type(exc).__name__
            host.stop_reason = safe(str(exc))[:1800]
            host.record("error", error_type=type(exc).__name__, message=safe(str(exc))[:1800])
        else:
            print(json.dumps({"status": "host_initialization_failed", "error": safe(exc)}))
        return 2
    finally:
        if runner:
            await runner.close()
        if api:
            await api.aio.aclose()
            api.close()
        if host:
            report = host.finish()
            print(json.dumps({
                "status": report["status"],
                "lane": report["lane"],
                "calls": report["calls"],
                "tokens": report["tokens"]["total"],
                "edits": report["edits"],
                "grounding_verified": report["grounding_verified"],
                "effective_models": report["effective_models"],
            }, ensure_ascii=False))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--workspace", type=Path, required=True)
    result.add_argument("--run-dir", type=Path, required=True)
    result.add_argument("--credential-root", type=Path, required=True)
    result.add_argument("--lane", choices=sorted(LANES), required=True)
    result.add_argument("--task", choices=sorted(TICKETS))
    result.add_argument("--rounds", type=int, choices=range(1, 4), default=2)
    result.add_argument("--max-calls", type=int, default=20)
    result.add_argument("--max-tokens", type=int, default=120_000)
    result.add_argument("--max-edits", type=int, default=12)
    result.add_argument("--timeout", type=int, default=1_800)
    return result


if __name__ == "__main__":
    args = parser().parse_args()
    if not 6 <= args.max_calls <= 40:
        raise SystemExit("--max-calls must be between 6 and 40")
    if not 20_000 <= args.max_tokens <= 300_000:
        raise SystemExit("--max-tokens must be between 20000 and 300000")
    if not 1 <= args.max_edits <= 20:
        raise SystemExit("--max-edits must be between 1 and 20")
    if not 300 <= args.timeout <= 3_600:
        raise SystemExit("--timeout must be between 300 and 3600")
    raise SystemExit(asyncio.run(execute(args)))
