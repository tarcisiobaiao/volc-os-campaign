"""Executor Gemini 3.7 Flash confinado à worktree e ao ownership.

O modelo recebe somente ferramentas locais explícitas. Não há shell genérico,
rede, acesso a segredos ou escrita fora dos caminhos declarados pela missão.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types

from .adapters import AdapterError, AdapterRequest, _emit_heartbeat


_SKIP_PARTS = {
    ".git", ".env", ".venv", ".venv-adk", ".venv-graphify",
    "node_modules", "dist", "build", "coverage", "__pycache__",
}
_READ_LIMIT = 250
_SEARCH_LIMIT = 200
_FILE_LIMIT = 1_000_000
_WRITE_LIMIT = 400_000


def _inside(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class WorkspaceTools:
    def __init__(self, request: AdapterRequest) -> None:
        self.request = request
        self.root = request.worktree.resolve()
        self.allowed = tuple(path.rstrip("/") for path in request.allowed_paths)
        self.writable = tuple(path.rstrip("/") for path in request.writable_paths)
        self.allowed_roots = tuple(
            (self.root / path).resolve() for path in self.allowed
        )

    def _is_allowed(self, normalized: str) -> bool:
        return any(
            normalized == prefix or normalized.startswith(prefix + "/")
            for prefix in self.allowed
        )

    def _is_writable(self, normalized: str) -> bool:
        return any(
            normalized == prefix or normalized.startswith(prefix + "/")
            for prefix in self.writable
        )

    def _resolved_is_allowed(self, resolved: Path) -> bool:
        return any(
            resolved == allowed_root or _inside(allowed_root, resolved)
            for allowed_root in self.allowed_roots
        )

    def _resolve(self, relative_path: str, *, write: bool = False) -> Path:
        raw = Path(relative_path)
        if raw.is_absolute() or ".." in raw.parts:
            raise ValueError("caminho precisa ser relativo e não pode conter '..'")
        if any(part in _SKIP_PARTS or part.startswith(".env") for part in raw.parts):
            raise ValueError("caminho protegido")
        resolved = (self.root / raw).resolve()
        if not _inside(self.root, resolved):
            raise ValueError("caminho saiu da worktree")
        normalized = raw.as_posix()
        if not self._is_allowed(normalized):
            raise PermissionError(f"fora do escopo autorizado: {normalized}")
        if not self._resolved_is_allowed(resolved):
            raise PermissionError(
                f"caminho resolve fora do escopo autorizado: {normalized}"
            )
        if write:
            if self.request.mode != "workspace_write":
                raise PermissionError("agente read-only não pode escrever")
            if not self._is_writable(normalized):
                raise PermissionError(f"caminho é somente leitura: {normalized}")
        return resolved

    def _scoped_roots(self, relative_path: str) -> list[Path]:
        """Projeta uma busca ampla somente nos descendentes autorizados.

        Pedir `.` ou `volc_ads` não amplia a allowlist: apenas seleciona os
        roots autorizados que já vivem abaixo desse ancestral. Isso evita que
        um revisor morra ao fazer uma busca natural e, ao mesmo tempo, impede
        a leitura de qualquer irmão não declarado.
        """
        raw = Path(relative_path)
        if raw.is_absolute() or ".." in raw.parts:
            raise ValueError("caminho precisa ser relativo e não pode conter '..'")
        if any(part in _SKIP_PARTS or part.startswith(".env") for part in raw.parts):
            raise ValueError("caminho protegido")
        normalized = raw.as_posix()
        if normalized in {"", "."}:
            normalized = "."

        if normalized != "." and self._is_allowed(normalized):
            return [self._resolve(normalized)]

        prefix = "" if normalized == "." else normalized.rstrip("/") + "/"
        selected = [allowed for allowed in self.allowed if allowed.startswith(prefix)]
        if not selected:
            raise PermissionError(f"fora do escopo autorizado: {normalized}")

        roots: list[Path] = []
        for allowed in sorted(selected, key=lambda item: (item.count("/"), item)):
            if any(
                allowed == parent or allowed.startswith(parent.rstrip("/") + "/")
                for parent in selected
                if parent != allowed and parent.count("/") < allowed.count("/")
            ):
                continue
            root = self._resolve(allowed)
            if root.exists():
                roots.append(root)
        return roots

    def read_file(self, path: str, start_line: int = 1, end_line: int = 250) -> dict[str, Any]:
        """Read at most 250 lines from one UTF-8 file inside the worktree."""
        target = self._resolve(path)
        if not target.is_file() or target.stat().st_size > _FILE_LIMIT:
            return {"error": "arquivo ausente ou grande demais"}
        start = max(1, start_line)
        end = min(max(start, end_line), start + _READ_LIMIT - 1)
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        return {
            "path": path,
            "start": start,
            "end": min(end, len(lines)),
            "text": "\n".join(lines[start - 1:end]),
        }

    def list_files(self, pattern: str) -> dict[str, Any]:
        """List up to 200 files matching one relative glob pattern."""
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            return {"error": "padrão inseguro"}
        found: list[str] = []
        if not any(marker in pattern for marker in ("*", "?", "[")):
            roots = self._scoped_roots(pattern)
            candidates = (
                item
                for root in roots
                for item in ([root] if root.is_file() else root.rglob("*"))
            )
        else:
            candidates = self.root.glob(pattern)
        for item in candidates:
            if not item.is_file():
                continue
            relative = item.relative_to(self.root)
            parts = relative.parts
            if any(part in _SKIP_PARTS or part.startswith(".env") for part in parts):
                continue
            normalized = relative.as_posix()
            if not self._is_allowed(normalized):
                continue
            if not self._resolved_is_allowed(item.resolve()):
                continue
            found.append(normalized)
            if len(found) >= _SEARCH_LIMIT:
                break
        return {"files": sorted(found), "truncated": len(found) >= _SEARCH_LIMIT}

    def search_text(self, query: str, path: str = ".") -> dict[str, Any]:
        """Search literal text below a relative path, capped at 200 matches."""
        roots = self._scoped_roots(path)
        candidates = (
            item
            for root in roots
            for item in ([root] if root.is_file() else root.rglob("*"))
        )
        matches: list[dict[str, Any]] = []
        for item in candidates:
            if not item.is_file():
                continue
            if not self._resolved_is_allowed(item.resolve()):
                continue
            parts = item.relative_to(self.root).parts
            if any(part in _SKIP_PARTS or part.startswith(".env") for part in parts):
                continue
            try:
                if item.stat().st_size > _FILE_LIMIT:
                    continue
                lines = item.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for number, line in enumerate(lines, 1):
                if query in line:
                    matches.append({
                        "path": item.relative_to(self.root).as_posix(),
                        "line": number,
                        "text": line[:500],
                    })
                    if len(matches) >= _SEARCH_LIMIT:
                        return {"matches": matches, "truncated": True}
        return {"matches": matches, "truncated": False}

    def write_file(self, path: str, content: str) -> dict[str, Any]:
        """Create or replace one owned UTF-8 text file."""
        if len(content.encode("utf-8")) > _WRITE_LIMIT:
            return {"error": "conteúdo grande demais"}
        target = self._resolve(path, write=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"ok": True, "path": path, "bytes": len(content.encode("utf-8"))}

    def replace_text(self, path: str, old: str, new: str) -> dict[str, Any]:
        """Replace exactly one occurrence in one owned UTF-8 file."""
        target = self._resolve(path, write=True)
        text = target.read_text(encoding="utf-8")
        count = text.count(old)
        if count != 1:
            return {"error": f"esperava 1 ocorrência, encontrei {count}"}
        updated = text.replace(old, new, 1)
        if len(updated.encode("utf-8")) > _WRITE_LIMIT:
            return {"error": "arquivo resultante grande demais"}
        target.write_text(updated, encoding="utf-8")
        return {"ok": True, "path": path}

    def show_diff(self) -> dict[str, Any]:
        """Show owned uncommitted diff or the owned HEAD commit diff."""
        result = subprocess.run(
            ["git", "diff", "--", *self.allowed],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode == 0 and not result.stdout:
            result = subprocess.run(
                ["git", "show", "--format=", "--", *self.allowed],
                cwd=self.root,
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
        return {
            "returncode": result.returncode,
            "diff": result.stdout[-40_000:],
            "truncated": len(result.stdout) > 40_000,
        }


def _thinking_level(effort: str) -> str:
    return "LOW" if effort == "low" else "MEDIUM" if effort == "medium" else "HIGH"


def _extract_final_json(events: list[Any]) -> dict[str, Any]:
    texts: list[str] = []
    for event in reversed(events):
        output = getattr(event, "output", None)
        if isinstance(output, dict):
            if set(output) == {"result"} and isinstance(output["result"], str):
                texts.append(output["result"])
                continue
            return output
        if isinstance(output, str) and output.strip():
            texts.append(output)
        content = getattr(event, "content", None)
        if not content:
            continue
        if hasattr(event, "is_final_response") and not event.is_final_response():
            continue
        for part in content.parts or []:
            if getattr(part, "text", None):
                texts.append(part.text)
    if not texts:
        raise AdapterError("Gemini não devolveu resposta final")
    raw = texts[0].strip()
    if raw.startswith("```"):
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise AdapterError("Gemini devolveu JSON final inválido") from error
    if not isinstance(payload, dict):
        raise AdapterError("Gemini não devolveu objeto JSON")
    return payload


async def run_gemini_worker(request: AdapterRequest) -> dict[str, Any]:
    if request.model != "gemini-3.7-flash":
        raise AdapterError("provider Gemini exige model='gemini-3.7-flash' sem fallback")
    if request.network_access:
        raise AdapterError("Gemini workers não recebem navegação externa nesta versão")
    request.run_dir.mkdir(parents=True, exist_ok=True)
    if not os.environ.get("GEMINI_API_KEY"):
        raise AdapterError("GEMINI_API_KEY ausente no ambiente do supervisor")
    tools = WorkspaceTools(request)
    model_versions: list[str] = []

    def verify_model(*, callback_context: Any, llm_response: Any) -> None:
        del callback_context
        version = getattr(llm_response, "model_version", None)
        if version:
            model_versions.append(version)
            if version != "gemini-3.7-flash":
                raise AdapterError(
                    f"modelo efetivo inesperado: {version}; fallback recusado"
                )
    schema = request.schema_path.read_text(encoding="utf-8")
    instruction = (
        request.prompt
        + "\n\nUse somente as ferramentas locais fornecidas. Não tente shell, rede ou segredos. "
        + "Ao terminar, responda exclusivamente com um objeto JSON válido neste schema:\n"
        + schema
    )
    agent = LlmAgent(
        name=request.worker_id.replace("-", "_"),
        description="Executor VOLC confinado a uma worktree e ownership explícito.",
        model=request.model,
        instruction=instruction,
        tools=[tools.read_file, tools.list_files, tools.search_text, tools.show_diff]
        + ([tools.write_file, tools.replace_text] if request.mode == "workspace_write" else []),
        generate_content_config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(
                thinking_level=_thinking_level(request.effort),
                include_thoughts=False,
            ),
            max_output_tokens=65_536,
        ),
        mode="task",
        after_model_callback=verify_model,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
    runner = InMemoryRunner(agent=agent, app_name="volc_gemini_worker")
    loop = asyncio.get_running_loop()
    started = loop.time()
    _emit_heartbeat(request, state="started", elapsed_seconds=0, silence_seconds=0)
    task = asyncio.create_task(
        runner.run_debug(
            "Execute a missão até o aceite e devolva o JSON final.",
            user_id="volc-local",
            session_id=f"gemini-{request.worker_id}",
            quiet=True,
        )
    )
    try:
        while not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=request.heartbeat_seconds)
            except TimeoutError:
                elapsed = loop.time() - started
                _emit_heartbeat(request, state="active", elapsed_seconds=elapsed, silence_seconds=0)
                if elapsed >= request.timeout_seconds:
                    task.cancel()
                    raise AdapterError(f"{request.worker_id} excedeu {request.timeout_seconds}s")
        events = await task
    finally:
        await runner.close()
    elapsed = loop.time() - started
    if not model_versions:
        raise AdapterError("Gemini não informou model_version; execução não auditável")
    _emit_heartbeat(
        request,
        state="completed",
        elapsed_seconds=elapsed,
        silence_seconds=0,
        returncode=0,
    )
    return _extract_final_json(events)
