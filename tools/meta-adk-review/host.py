"""Capability host: read broadly, edit narrowly, test without network."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import threading
import time
from typing import Any

from google.adk.models.llm_response import LlmResponse
from google.genai import types

from config import MODEL, THINKING, Lane

SECRET = re.compile(
    r"AIza[\w-]{25,}|\bsk-[\w-]{20,}|\bEAA[\w]{40,}|"
    r"eyJ[\w-]{20,}\.[\w-]{20,}\.[\w-]{10,}|"
    r"-----BEGIN [\w ]*PRIVATE KEY-----|postgres(?:ql)?://[^\s]+@"
)
PRIVATE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?<![\w])\d{12,}(?![\w])")
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".sql", ".md", ".css", ".json"}
PROTECTED_PARTS = {"node_modules", "graphify-out", "backups", "storage", ".git", ".claude-ads"}
PROTECTED_NAMES = ("credential", "secret", "receipt", "manifest", "snapshot", "lock.json")


def safe(value: Any) -> str:
    return PRIVATE.sub("[PRIVATE]", SECRET.sub("[SECRET]", str(value)))


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class Host:
    """Owns all side effects and audit data for one isolated lane."""

    role_limits = {
        "meta_api_researcher": 1,
        "meta_code_mapper": 5,
        "meta_engineer": 9,
        "meta_critic": 5,
    }

    def __init__(self, args: Any, lane: Lane):
        self.args = args
        self.lane = lane
        self.root = args.workspace.resolve()
        self.run_dir = args.run_dir.resolve()
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.started = time.monotonic()
        self.lock = threading.RLock()
        self.calls = 0
        self.tokens = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.thought_tokens = 0
        self.edits = 0
        self.rounds = 0
        self.last_edits = 0
        self.unchanged_rounds = 0
        self.grounded = False
        self.effective_models: set[str] = set()
        self.role_calls: dict[str, int] = {}
        self.read_hashes: dict[str, str] = {}
        self.gates: dict[str, dict[str, Any]] = {}
        self.status = "running"
        self.tracked = set(
            subprocess.check_output(["git", "ls-files"], cwd=self.root, text=True).splitlines()
        )
        self.base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root, text=True).strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=self.root, text=True
        ).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=self.root, text=True)
        if dirty:
            raise RuntimeError("candidate worktree must start clean")
        if not branch.startswith("sprint/meta-adk-v2-"):
            raise RuntimeError("candidate worktree must use a controlled sprint/meta-adk-v2-* branch")
        self.patch_binary = shutil.which("apply_patch")
        if not self.patch_binary:
            raise RuntimeError("apply_patch executable required")
        self.record(
            "start",
            lane=lane.slug,
            base=self.base,
            branch=branch,
            requested_model=MODEL,
            thinking=THINKING,
        )

    def record(self, event: str, **data: Any) -> None:
        row = {
            "time": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **data,
        }
        with self.lock, (self.run_dir / "events.jsonl").open("a") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _path(self, path: str, *, write: bool = False, create: bool = False) -> Path:
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts or any(part.startswith(".") for part in relative.parts):
            raise ValueError("protected path")
        target = self.root / relative
        if target.resolve() != target.absolute() or not target.resolve().is_relative_to(self.root):
            raise ValueError("symlink or outside workspace")
        if relative.suffix not in SOURCE_SUFFIXES or any(part in PROTECTED_PARTS for part in relative.parts):
            raise ValueError("not readable source")
        lowered = relative.name.lower()
        if any(word in lowered for word in PROTECTED_NAMES) or lowered.startswith(".env"):
            raise ValueError("sensitive or generated artifact")
        if not write and path not in self.tracked:
            raise ValueError("untracked file")
        if write and not path.startswith(self.lane.write_prefixes):
            raise ValueError("outside this lane's write scope")
        if create and target.exists():
            raise ValueError("new file already exists")
        if create and not path.startswith(self.lane.test_prefixes):
            raise ValueError("new files are restricted to lane test prefixes")
        return target

    def list_files(self, pattern: str = "*meta*") -> dict[str, Any]:
        """List tracked readable source paths matching one glob; result is capped."""
        files: list[str] = []
        for name in sorted(self.tracked):
            if not fnmatch.fnmatch(name.lower(), pattern.lower()):
                continue
            try:
                self._path(name)
            except ValueError:
                continue
            files.append(name)
        return {"files": files[:160], "total": len(files), "truncated": len(files) > 160}

    def read_file(self, path: str, start: int = 1, count: int = 180) -> dict[str, Any]:
        """Read tracked source lines and return the hash required for a guarded edit."""
        try:
            target = self._path(path)
            content = target.read_text()
            if len(content) > 650_000:
                raise ValueError("file too large; use source search")
            lines = content.splitlines()
            start = max(1, start)
            count = min(250, max(1, count))
            sha = digest(content)
            with self.lock:
                self.read_hashes[path] = sha
            text = "\n".join(
                f"{number + 1}: {line}"
                for number, line in enumerate(lines)
                if start - 1 <= number < start - 1 + count
            )
            self.record("read", path=path, sha256=sha, start=start, count=count)
            return {
                "path": path,
                "sha256": sha,
                "total_lines": len(lines),
                "text": safe(text),
            }
        except (OSError, ValueError) as exc:
            return {"error": safe(exc)}

    def search_source(self, query: str, prefix: str = "") -> dict[str, Any]:
        """Literal case-insensitive search over tracked source. No regex or shell."""
        if not query or len(query) > 160:
            return {"error": "provide a literal query of 1..160 characters"}
        matches: list[dict[str, Any]] = []
        for name in sorted(self.tracked):
            if prefix and not name.startswith(prefix):
                continue
            try:
                target = self._path(name)
                if target.stat().st_size > 650_000:
                    continue
                for number, line in enumerate(target.read_text().splitlines(), 1):
                    if query.casefold() in line.casefold():
                        matches.append({"path": name, "line": number, "text": safe(line[:500])})
                        if len(matches) == 60:
                            return {"matches": matches, "truncated": True}
            except (OSError, ValueError):
                continue
        return {"matches": matches, "truncated": False}

    def replace_text(self, path: str, sha256: str, old: str, new: str) -> dict[str, Any]:
        """Apply one exact replacement after a current read and SHA match."""
        try:
            target = self._path(path, write=True)
            content = target.read_text()
            with self.lock:
                if self.edits >= self.args.max_edits:
                    raise ValueError("edit budget exhausted")
                if self.read_hashes.get(path) != sha256 or digest(content) != sha256:
                    raise ValueError("stale file hash; read again")
            if not old or old == new or len(new) > 24_000 or content.count(old) != 1:
                raise ValueError("replacement must be unique, changed and within size limit")
            if SECRET.search(new) or "[SECRET]" in new or "[PRIVATE]" in new:
                raise ValueError("secret or redacted content refused")
            patch = "*** Begin Patch\n*** Update File: " + path + "\n@@\n"
            patch += "".join("-" + line + "\n" for line in old.splitlines())
            patch += "".join("+" + line + "\n" for line in new.splitlines())
            patch += "*** End Patch\n"
            completed = subprocess.run(
                [self.patch_binary],
                input=patch,
                cwd=self.root,
                text=True,
                capture_output=True,
                timeout=30,
            )
            if completed.returncode:
                return {"error": safe(completed.stderr[-1800:] or completed.stdout[-1800:])}
            with self.lock:
                self.edits += 1
                self.gates.clear()
                new_sha = digest(target.read_text())
                self.read_hashes[path] = new_sha
            self.record("edit", kind="replace", path=path, before_sha256=sha256, after_sha256=new_sha)
            return {"ok": True, "path": path, "sha256": new_sha}
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            return {"error": safe(exc)}

    def create_test_file(self, path: str, content: str) -> dict[str, Any]:
        """Create one new test source file inside this lane; existing files are never overwritten."""
        try:
            target = self._path(path, write=True, create=True)
            if self.edits >= self.args.max_edits or not content or len(content) > 24_000:
                raise ValueError("edit budget, empty content or size limit")
            if SECRET.search(content) or "[SECRET]" in content or "[PRIVATE]" in content:
                raise ValueError("secret or redacted content refused")
            target.parent.mkdir(parents=True, exist_ok=True)
            patch = "*** Begin Patch\n*** Add File: " + path + "\n"
            patch += "".join("+" + line + "\n" for line in content.splitlines())
            patch += "*** End Patch\n"
            completed = subprocess.run(
                [self.patch_binary], input=patch, cwd=self.root, text=True, capture_output=True, timeout=30
            )
            if completed.returncode:
                return {"error": safe(completed.stderr[-1800:] or completed.stdout[-1800:])}
            with self.lock:
                self.edits += 1
                self.gates.clear()
            self.record("edit", kind="create_test", path=path, after_sha256=digest(target.read_text()))
            return {"ok": True, "path": path, "sha256": digest(target.read_text())}
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            return {"error": safe(exc)}

    def show_diff(self) -> dict[str, Any]:
        """Return the current candidate diff and most recent test evidence."""
        output = subprocess.check_output(
            ["git", "diff", "--no-ext-diff", "--", ":(exclude)graphify-out"],
            cwd=self.root,
            text=True,
        )
        return {
            "diff": safe(output[:42_000]),
            "truncated": len(output) > 42_000,
            "gates": self.gates,
            "edits": self.edits,
        }

    async def run_gate(self, gate: str, target: str = "") -> dict[str, Any]:
        """Run diff, one eligible backend test, or one eligible frontend test without network."""
        if gate == "diff":
            argv = ["git", "diff", "--check"]
        elif gate in {"backend", "frontend"}:
            dependency_root = Path(os.environ["VOLC_META_ADK_DEPENDENCY_ROOT"]).resolve()
            if not target or not target.startswith(self.lane.test_prefixes):
                return {"error": "target is not an eligible lane test"}
            try:
                self._path(target)
            except ValueError:
                # A newly created lane test is intentionally untracked until lead integration.
                candidate = self.root / target
                if not candidate.is_file() or not target.startswith(self.lane.test_prefixes):
                    return {"error": "invalid test target"}
            if gate == "backend" and target.endswith(".py") and target.startswith("backend/tests/"):
                argv = [
                    str(dependency_root / "backend/.venv/bin/python"),
                    "-m", "pytest", "-q", "--disable-warnings",
                    "-p", "anyio.pytest_plugin", "-p", "pytest_asyncio.plugin", target,
                ]
            elif gate == "frontend" and target.endswith((".test.ts", ".test.tsx")):
                argv = [
                    str(dependency_root / "node_modules/.bin/vitest"), "run", "--configLoader", "runner",
                    "--no-cache", "--maxWorkers", "2", target,
                ]
            else:
                return {"error": "gate and target type do not match"}
        else:
            return {"error": "unknown gate"}

        if gate != "diff":
            readable = (self.root, dependency_root / "backend/.venv", dependency_root / "node_modules")
            allow_read = " ".join(f"(subpath {json.dumps(str(path))})" for path in readable)
            profile = (
                '(version 1)(allow default)(deny network*)'
                '(deny file-read* (subpath "/Users/mac") (subpath "/private/tmp"))'
                f'(allow file-read* {allow_read})(allow file-read-metadata)'
                '(deny file-write*)'
                f'(allow file-write* (subpath {json.dumps(str(self.root))}) (literal "/dev/null"))'
                '(deny file-read* (regex #"(^|/)\\.env([^/]*)(/|$)"))'
            )
            argv = ["/usr/bin/sandbox-exec", "-p", profile, *argv]
        tmp = self.root / ".test-tmp"
        tmp.mkdir(exist_ok=True)
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": "en_US.UTF-8",
            "TMPDIR": str(tmp),
            "PYTHONPATH": str(self.root / "backend"),
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "VITE_PAUTADOR_API_URL": "http://127.0.0.1:8000",
        }
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=self.root,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        timed_out = False
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout=240)
        except TimeoutError:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            output, _ = await process.communicate()
        result = {
            "gate": gate,
            "target": target,
            "returncode": process.returncode,
            "timed_out": timed_out,
            "output": safe(output.decode(errors="replace")[-10_000:]),
            "edits": self.edits,
        }
        with self.lock:
            self.gates[f"{gate}:{target}"] = result
        self.record("gate", **result)
        return result

    def before_model(self, callback_context: Any, llm_request: Any) -> LlmResponse | None:
        name = callback_context.agent_name
        with self.lock:
            if (
                self.calls >= self.args.max_calls
                or self.tokens >= self.args.max_tokens
                or time.monotonic() - self.started > self.args.timeout
            ):
                raise RuntimeError("bounded_run_budget_exhausted")
            count = self.role_calls.get(name, 0)
            limit = self.role_limits[name]
            if count >= limit:
                payload = (
                    '{"verdict":"revise","findings":[],"coverage":[],"remaining":'
                    '["stage call budget exhausted"],"summary":"Host stopped this stage."}'
                    if name == "meta_critic"
                    else "Host stopped this stage at its per-agent call budget. Report only observed evidence."
                )
                self.record("stage_budget", agent=name, calls=count)
                return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=payload)]))
            self.role_calls[name] = count + 1
            self.calls += 1
            call_number = self.calls
        if name in {"meta_engineer", "meta_critic"} and count == limit - 1:
            llm_request.config.tools = []
            llm_request.config.tool_config = None
            ending = (
                "Return the required strict verdict JSON now."
                if name == "meta_critic"
                else "Return changed files, current gates and remaining work now."
            )
            llm_request.contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part(text="Host: final tool-free response for this stage. " + ending)],
                )
            )
        self.record("dispatch", call=call_number, agent=name, model=MODEL, thinking=THINKING)
        return None

    def after_model(self, callback_context: Any, llm_response: Any) -> None:
        if llm_response.model_version != MODEL:
            raise RuntimeError("effective_model_mismatch_or_missing")
        usage = llm_response.usage_metadata
        grounding = llm_response.grounding_metadata
        grounded = bool(
            grounding and grounding.web_search_queries and grounding.grounding_chunks
        )
        with self.lock:
            self.effective_models.add(llm_response.model_version)
            if usage:
                self.tokens += usage.total_token_count or 0
                self.input_tokens += usage.prompt_token_count or 0
                self.output_tokens += usage.candidates_token_count or 0
                self.thought_tokens += usage.thoughts_token_count or 0
            self.grounded = self.grounded or grounded
        visible = ""
        if llm_response.content:
            visible = "".join(
                part.text
                for part in (llm_response.content.parts or [])
                if part.text and not part.thought
            )
        self.record(
            "response",
            agent=callback_context.agent_name,
            model=llm_response.model_version,
            grounded=grounded,
            usage=usage.model_dump(mode="json", exclude_none=True) if usage else {},
            grounding=grounding.model_dump(mode="json", exclude_none=True) if grounding else {},
            visible_text=safe(visible),
        )

    def before_tool(self, tool: Any, args: dict[str, Any], tool_context: Any) -> None:
        self.record(
            "tool",
            agent=tool_context.agent_name,
            name=tool.name,
            path=args.get("path") or args.get("target"),
            query=safe(args.get("query", ""))[:160],
        )

    def after_tool(self, tool: Any, args: dict[str, Any], tool_context: Any, response: Any) -> None:
        if isinstance(response, dict):
            self.record(
                "tool_result",
                agent=tool_context.agent_name,
                name=tool.name,
                error=safe(response.get("error", "")),
                count=len(response.get("files", response.get("matches", []))),
            )

    def evaluate_critic(self, raw: str, max_rounds: int) -> str:
        """Parse the independent verdict and return the Workflow route."""
        self.rounds += 1
        self.role_calls.pop("meta_engineer", None)
        self.role_calls.pop("meta_critic", None)
        try:
            cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()
            verdict = json.loads(cleaned)
        except (AttributeError, json.JSONDecodeError):
            verdict = {
                "verdict": "revise",
                "findings": ["critic output was not valid JSON"],
                "coverage": [],
                "remaining": ["obtain a valid independent verdict"],
                "summary": "Invalid critic output.",
            }
        self.unchanged_rounds = self.unchanged_rounds + 1 if self.edits == self.last_edits else 0
        self.last_edits = self.edits
        self.record("round", round=self.rounds, verdict=verdict, edits=self.edits)
        post_edit_tests = [
            gate for gate in self.gates.values()
            if gate["gate"] in {"backend", "frontend"}
            and gate["returncode"] == 0
            and gate["edits"] == self.edits
        ]
        all_green = bool(self.gates) and all(gate["returncode"] == 0 for gate in self.gates.values())
        if (
            verdict.get("verdict") == "candidate"
            and self.edits > 0
            and self.grounded
            and post_edit_tests
            and all_green
        ):
            self.status = "candidate_requires_lead_review"
            return "done"
        elif verdict.get("verdict") == "blocked" or self.unchanged_rounds >= 2:
            self.status = "partial_no_progress"
            return "done"
        elif self.rounds >= max_rounds:
            self.status = "partial_iteration_limit"
            return "done"
        return "revise"

    def finish(self) -> dict[str, Any]:
        if self.status == "running":
            self.status = "partial_iteration_limit"
        diff = subprocess.check_output(["git", "diff", "--no-ext-diff"], cwd=self.root, text=True)
        untracked = subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard"], cwd=self.root, text=True
        ).splitlines()
        report = {
            "status": self.status,
            "lane": self.lane.slug,
            "base": self.base,
            "requested_model": MODEL,
            "effective_models": sorted(self.effective_models),
            "thinking": THINKING,
            "grounding_verified": self.grounded,
            "calls": self.calls,
            "tokens": {
                "total": self.tokens,
                "input": self.input_tokens,
                "output": self.output_tokens,
                "thoughts": self.thought_tokens,
            },
            "rounds": self.rounds,
            "edits": self.edits,
            "gates": self.gates,
            "untracked_candidate_files": untracked,
            "meta_mutations": 0,
            "database_mutations": 0,
            "git_integrations": 0,
            "production_verified": False,
            "cost_usd": None,
            "billing_note": "Provider usage recorded; billed dollar amount is not returned by the API.",
        }
        (self.run_dir / "REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        (self.run_dir / "candidate.diff").write_text(diff)
        self.record("finish", status=self.status, calls=self.calls, tokens=self.tokens, edits=self.edits)
        return report
