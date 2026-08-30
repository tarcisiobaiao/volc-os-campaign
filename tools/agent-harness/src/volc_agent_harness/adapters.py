"""Adapters read-only para Claude Code e Codex CLI."""

from __future__ import annotations

import asyncio
import json
import os
import signal
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

from .security import redact, sanitized_environment


MAX_LOG_BYTES = 25 * 1024 * 1024
SILENCE_WARNING_SECONDS = 180


@dataclass(frozen=True)
class AdapterRequest:
    worker_id: str
    worktree: Path
    prompt: str
    schema_path: Path
    run_dir: Path
    timeout_seconds: int
    heartbeat_seconds: int = 20
    mode: str = "read_only"
    model: str | None = None
    effort: str = "high"
    network_access: bool = False


class AdapterError(RuntimeError):
    pass


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def _emit_heartbeat(
    request: AdapterRequest,
    *,
    state: str,
    elapsed_seconds: float,
    silence_seconds: float,
    returncode: int | None = None,
) -> None:
    stdout_bytes = _size(request.run_dir / "stdout.jsonl")
    stderr_bytes = _size(request.run_dir / "stderr.log")
    payload = {
        "at": datetime.now(timezone.utc).isoformat(),
        "worker_id": request.worker_id,
        "state": state,
        "elapsed_seconds": round(elapsed_seconds, 1),
        "silence_seconds": round(silence_seconds, 1),
        "stdout_bytes": stdout_bytes,
        "stderr_bytes": stderr_bytes,
        "returncode": returncode,
    }
    with (request.run_dir / "heartbeat.jsonl").open(
        "a", encoding="utf-8"
    ) as output:
        output.write(json.dumps(payload, ensure_ascii=False) + "\n")

    clock = datetime.now().astimezone().strftime("%H:%M:%S")
    marker = "OK" if state in {"started", "active", "completed"} else "AVISO"
    detail = (
        f"ativo {int(elapsed_seconds)}s | sem evento {int(silence_seconds)}s | "
        f"stdout {stdout_bytes // 1024} KiB"
    )
    if returncode is not None:
        detail += f" | exit {returncode}"
    print(
        f"[{clock}] heartbeat {marker} {request.worker_id} | {state} | {detail}",
        flush=True,
    )


async def _terminate(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    for sig, grace in ((signal.SIGINT, 10), (signal.SIGTERM, 5)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=grace)
            return
        except TimeoutError:
            continue
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    await process.wait()


async def _pump(
    stream: asyncio.StreamReader,
    destination: Path,
    *,
    redact_content: bool,
    activity: list[float],
) -> bool:
    size = 0
    overflow = False
    with destination.open("w", encoding="utf-8") as output:
        while chunk := await stream.readline():
            activity[0] = asyncio.get_running_loop().time()
            size += len(chunk)
            if size > MAX_LOG_BYTES:
                overflow = True
                continue
            text = chunk.decode("utf-8", errors="replace")
            output.write(redact(text) if redact_content else text)
            output.flush()
    return overflow


async def _execute(argv: list[str], request: AdapterRequest) -> int:
    request.run_dir.mkdir(parents=True, exist_ok=True)
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=request.worktree,
        env=sanitized_environment(),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        # Claude pode devolver um tool_result inteiro em uma única linha JSONL.
        # O limite padrão de 64 KiB faz readline() cair e deixa o produtor
        # bloqueado no pipe com aparência de worker inativo.
        limit=MAX_LOG_BYTES + 1,
        start_new_session=True,
    )
    assert process.stdin and process.stdout and process.stderr
    process.stdin.write(request.prompt.encode("utf-8"))
    await process.stdin.drain()
    process.stdin.close()

    loop = asyncio.get_running_loop()
    activity = [loop.time()]
    started_at = loop.time()
    stdout_task = asyncio.create_task(
        _pump(
            process.stdout,
            request.run_dir / "stdout.jsonl",
            redact_content=True,
            activity=activity,
        )
    )
    stderr_task = asyncio.create_task(
        _pump(
            process.stderr,
            request.run_dir / "stderr.log",
            redact_content=True,
            activity=activity,
        )
    )
    deadline = loop.time() + request.timeout_seconds
    _emit_heartbeat(
        request,
        state="started",
        elapsed_seconds=0,
        silence_seconds=0,
    )
    try:
        while process.returncode is None:
            remaining = deadline - loop.time()
            if remaining <= 0:
                now = loop.time()
                _emit_heartbeat(
                    request,
                    state="timeout",
                    elapsed_seconds=now - started_at,
                    silence_seconds=now - activity[0],
                )
                await _terminate(process)
                raise AdapterError(
                    f"{request.worker_id} excedeu {request.timeout_seconds}s"
                )
            try:
                await asyncio.wait_for(
                    process.wait(),
                    timeout=min(request.heartbeat_seconds, remaining),
                )
            except TimeoutError:
                now = loop.time()
                inactive_for = now - activity[0]
                state = (
                    "active"
                    if inactive_for < SILENCE_WARNING_SECONDS
                    else "alive_without_output"
                )
                _emit_heartbeat(
                    request,
                    state=state,
                    elapsed_seconds=now - started_at,
                    silence_seconds=inactive_for,
                )
        returncode = process.returncode
    finally:
        stdout_overflow, stderr_overflow = await asyncio.gather(
            stdout_task, stderr_task
        )
        if stdout_overflow or stderr_overflow:
            await _terminate(process)
            raise AdapterError(f"{request.worker_id} excedeu o limite de log")

    now = loop.time()
    _emit_heartbeat(
        request,
        state="completed" if returncode == 0 else "failed",
        elapsed_seconds=now - started_at,
        silence_seconds=now - activity[0],
        returncode=returncode,
    )

    if returncode != 0:
        stderr = (request.run_dir / "stderr.log").read_text(
            encoding="utf-8", errors="replace"
        )
        raise AdapterError(
            f"{request.worker_id} terminou com exit={returncode}: {stderr[-800:]}"
        )
    return returncode


def _validate(payload: Any, schema_path: Path) -> dict[str, Any]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(payload, schema)
    if not isinstance(payload, dict):
        raise AdapterError("resultado estruturado não é um objeto")
    return payload


class ClaudeAdapter:
    async def run(self, request: AdapterRequest) -> dict[str, Any]:
        schema = json.loads(request.schema_path.read_text(encoding="utf-8"))
        tools = ["Read", "Grep", "Glob"]
        if request.network_access:
            tools.extend(["WebFetch", "WebSearch"])
        if request.mode == "workspace_write":
            tools.extend(["Edit", "Write", "Bash"])
        argv = [
            "claude",
            "-p",
            "--safe-mode",
            "--permission-mode",
            "acceptEdits" if request.mode == "workspace_write" else "plan",
            "--tools",
            ",".join(tools),
            "--mcp-config",
            '{"mcpServers":{}}',
            "--strict-mcp-config",
            "--input-format",
            "text",
            "--output-format",
            "stream-json",
            "--json-schema",
            json.dumps(schema, separators=(",", ":")),
            "--no-session-persistence",
            "--prompt-suggestions",
            "false",
            "--effort",
            request.effort,
            "--verbose",
        ]
        if request.model:
            argv[2:2] = ["--model", request.model]
        await _execute(argv, request)
        events = []
        for line in (request.run_dir / "stdout.jsonl").read_text(
            encoding="utf-8"
        ).splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        for event in reversed(events):
            if event.get("type") != "result":
                continue
            if event.get("is_error"):
                raise AdapterError(f"Claude reportou erro: {event.get('result', '')}")
            payload = event.get("structured_output")
            if payload is None and isinstance(event.get("result"), str):
                payload = json.loads(event["result"])
            if payload is not None:
                return _validate(payload, request.schema_path)
        raise AdapterError("Claude não devolveu evento result estruturado")


class CodexAdapter:
    async def run(self, request: AdapterRequest) -> dict[str, Any]:
        result_path = request.run_dir / "result.json"
        argv = [
            "codex",
            "-a",
            "never",
            "exec",
            "--cd",
            str(request.worktree),
            "--sandbox",
            "workspace-write" if request.mode == "workspace_write" else "read-only",
            "--ephemeral",
            "--ignore-user-config",
            "--strict-config",
            "--output-schema",
            str(request.schema_path),
            "--json",
            "--output-last-message",
            str(result_path),
            "--color",
            "never",
            "-c",
            f'model_reasoning_effort="{request.effort}"',
            "-",
        ]
        if request.model:
            argv[4:4] = ["--model", request.model]
        await _execute(argv, request)
        if not result_path.exists():
            raise AdapterError("Codex não produziu result.json")
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        return _validate(payload, request.schema_path)


def adapter_for(provider: str) -> ClaudeAdapter | CodexAdapter:
    if provider == "claude":
        return ClaudeAdapter()
    if provider == "codex":
        return CodexAdapter()
    raise ValueError(f"provider desconhecido: {provider}")
