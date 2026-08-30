import json
import io
import sys
import tempfile
import unittest
import subprocess
from contextlib import redirect_stdout
from pathlib import Path

from volc_agent_harness.adapters import AdapterRequest, _execute
from volc_agent_harness.gemini_worker import WorkspaceTools, _thinking_level
from volc_agent_harness.models import MissionSpec, WorkerSpec
from volc_agent_harness.mission import _worker_node, _worker_prompt
from volc_agent_harness.security import redact, sanitized_environment
from volc_agent_harness.worktrees import WorktreeInfo, safe_slug
from volc_agent_harness.worktrees import WorktreeManager


class HarnessContractsTest(unittest.TestCase):
    def _commit_all(self, root: Path) -> None:
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(
            [
                "git", "-c", "user.name=VOLC Test",
                "-c", "user.email=volc@example.invalid",
                "commit", "-qm", "fixture",
            ],
            cwd=root,
            check=True,
        )

    def test_mission_requires_two_unique_workers(self) -> None:
        mission = MissionSpec.model_validate(
            {
                "mission_id": "pilot",
                "title": "Pilot",
                "base_ref": "HEAD",
                "briefing": "Inspect",
                "authorized_external_providers": ["anthropic"],
                "workers": [
                    {
                        "id": "claude-a",
                        "provider": "claude",
                        "lens": "A",
                        "allowed_paths": ["src"],
                    },
                    {
                        "id": "codex-b",
                        "provider": "codex",
                        "lens": "B",
                        "allowed_paths": ["backend"],
                    },
                ],
            }
        )
        self.assertEqual(len(mission.workers), 2)
        self.assertEqual(mission.heartbeat_seconds, 20)

    def test_environment_does_not_forward_project_secrets(self) -> None:
        env = sanitized_environment(
            {
                "PATH": "/bin",
                "HOME": "/tmp/home",
                "SUPABASE_SERVICE_ROLE_KEY": "secret",
                "OPENAI_API_KEY": "secret",
            }
        )
        self.assertEqual(env["PATH"], "/bin")
        self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", env)
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("GEMINI_API_KEY", env)

    def test_redacts_tokens(self) -> None:
        self.assertEqual(
            redact("SERVICE_ROLE_TOKEN=abcdef0123456789"),
            "SERVICE_ROLE_TOKEN=[REDACTED]",
        )

    def test_slug_is_safe_for_branch_and_path(self) -> None:
        self.assertEqual(safe_slug("Pilot Search/Zero"), "pilot-search-zero")

    def test_adk_node_name_normalizes_worker_hyphen(self) -> None:
        mission = MissionSpec.model_validate(
            {
                "mission_id": "pilot",
                "title": "Pilot",
                "base_ref": "HEAD",
                "briefing": "Inspect",
                "authorized_external_providers": ["anthropic"],
                "workers": [
                    {
                        "id": "claude-architecture",
                        "provider": "claude",
                        "lens": "A",
                        "allowed_paths": ["src"],
                    },
                    {
                        "id": "codex-adversarial",
                        "provider": "codex",
                        "lens": "B",
                        "allowed_paths": ["backend"],
                    },
                ],
            }
        )
        worker = mission.workers[0]
        node = _worker_node(
            mission,
            worker,
            WorktreeInfo(worker.id, Path("/tmp/w"), "b", "a" * 40),
            Path("/tmp/schema.json"),
            Path("/tmp/run"),
        )
        self.assertEqual(node.name, "claude_architecture")

    def test_worker_schema_is_accepted_by_both_clis(self) -> None:
        schema_path = (
            Path(__file__).parents[1]
            / "src"
            / "volc_agent_harness"
            / "schemas"
            / "worker-result.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertNotIn("$schema", schema)
        self.assertEqual(schema["type"], "object")

    def test_worker_prompt_caps_shell_output(self) -> None:
        mission = MissionSpec.model_validate(
            {
                "mission_id": "pilot",
                "title": "Pilot",
                "base_ref": "HEAD",
                "briefing": "Inspect",
                "authorized_external_providers": ["anthropic"],
                "workers": [
                    {
                        "id": "claude-a",
                        "provider": "claude",
                        "lens": "A",
                        "allowed_paths": ["src"],
                    },
                    {
                        "id": "codex-b",
                        "provider": "codex",
                        "lens": "B",
                        "allowed_paths": ["backend"],
                    },
                ],
            }
        )
        prompt = _worker_prompt(mission, mission.workers[0], "a" * 40)
        self.assertIn("no máximo 200 linhas", prompt)
        self.assertIn("Nunca varra o repositório inteiro", prompt)
        self.assertIn("fatias de no máximo 250 linhas", prompt)
        self.assertIn("uma ferramenta por vez", prompt)

    def test_implementation_requires_one_codex_writer_full_sha_and_gates(self) -> None:
        mission = MissionSpec.model_validate(
            {
                "mission_id": "implementation-pilot",
                "title": "Implementation pilot",
                "base_ref": "a" * 40,
                "briefing": "Implement one vertical slice",
                "mode": "implementation",
                "authorized_external_providers": ["anthropic"],
                "commit_message": "feat(test): pilot",
                "gates": [{"argv": ["python3", "-m", "unittest"]}],
                "workers": [
                    {
                        "id": "codex-writer",
                        "provider": "codex",
                        "role": "writer",
                        "model": "gpt-5.6-sol",
                        "effort": "xhigh",
                        "lens": "Implement",
                        "allowed_paths": ["src"],
                        "writable_paths": ["src"],
                    },
                    {
                        "id": "claude-reviewer",
                        "provider": "claude",
                        "role": "reviewer",
                        "model": "opus",
                        "effort": "max",
                        "lens": "Review",
                        "allowed_paths": ["src"],
                    },
                ],
            }
        )
        self.assertEqual(mission.mode, "implementation")
        self.assertEqual(mission.workers[0].model, "gpt-5.6-sol")
        self.assertEqual(mission.workers[1].effort, "max")

    def test_provider_defaults_are_explicit_and_economical(self) -> None:
        claude = WorkerSpec.model_validate({
            "id": "claude-reader", "provider": "claude", "lens": "read",
            "allowed_paths": ["src"],
        })
        codex = WorkerSpec.model_validate({
            "id": "codex-writer", "provider": "codex", "role": "writer",
            "lens": "write", "allowed_paths": ["src"],
        })
        self.assertEqual(claude.model, "opus")
        self.assertEqual(codex.model, "gpt-5.6-sol")
        self.assertEqual(codex.effort, "high")

    def test_implementation_accepts_exact_gemini_writer(self) -> None:
        mission = MissionSpec.model_validate({
            "mission_id": "gemini-implementation",
            "title": "Gemini implementation",
            "base_ref": "a" * 40,
            "briefing": "Implement one slice",
            "mode": "implementation",
            "authorized_external_providers": ["google_gemini"],
            "commit_message": "feat(test): gemini",
            "gates": [{"argv": ["true"]}],
            "workers": [
                {
                    "id": "gemini-writer", "provider": "gemini", "role": "writer",
                    "model": "gemini-3.7-flash", "effort": "high",
                    "lens": "Implement", "allowed_paths": ["src"],
                    "writable_paths": ["src"],
                },
                {
                    "id": "codex-reviewer", "provider": "codex", "role": "reviewer",
                    "model": "gpt-5.5", "effort": "xhigh",
                    "lens": "Review", "allowed_paths": ["src"],
                },
            ],
        })
        self.assertEqual(mission.workers[0].provider, "gemini")

    def test_gemini_rejects_model_fallback_and_unsupported_effort(self) -> None:
        base = {
            "id": "gemini-reader", "provider": "gemini", "role": "investigator",
            "model": "gemini-3.7-flash", "effort": "high",
            "lens": "Inspect", "allowed_paths": ["src"],
        }
        WorkerSpec.model_validate(base)
        with self.assertRaisesRegex(ValueError, "gemini-3.7-flash"):
            WorkerSpec.model_validate({**base, "model": "gemini-fallback"})
        with self.assertRaisesRegex(ValueError, "low, medium ou high"):
            WorkerSpec.model_validate({**base, "effort": "xhigh"})

    def test_writer_read_context_does_not_expand_write_ownership(self) -> None:
        worker = WorkerSpec.model_validate({
            "id": "gemini-writer", "provider": "gemini", "role": "writer",
            "model": "gemini-3.7-flash", "effort": "high", "lens": "Implement",
            "allowed_paths": ["src/owned", "src/context.py"],
            "writable_paths": ["src/owned"],
        })
        self.assertEqual(worker.effective_writable_paths, ["src/owned"])
        with self.assertRaisesRegex(ValueError, "subconjunto"):
            WorkerSpec.model_validate({**worker.model_dump(), "writable_paths": ["backend"]})

    def test_gemini_thinking_is_hidden_and_capped_at_high(self) -> None:
        self.assertEqual(_thinking_level("low"), "LOW")
        self.assertEqual(_thinking_level("medium"), "MEDIUM")
        self.assertEqual(_thinking_level("high"), "HIGH")

    def test_gemini_workspace_restricts_reads_writes_and_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "src" / "owned").mkdir(parents=True)
            (root / "src" / "context.txt").write_text("context\n", encoding="utf-8")
            (root / "private.txt").write_text("private\n", encoding="utf-8")
            self._commit_all(root)
            request = AdapterRequest(
                worker_id="gemini-writer", worktree=root, prompt="x",
                schema_path=root / "schema.json", run_dir=root / "run",
                timeout_seconds=60, mode="workspace_write", model="gemini-3.7-flash",
                allowed_paths=("src/owned", "src/context.txt"),
                writable_paths=("src/owned",),
            )
            tools = WorkspaceTools(request)
            self.assertTrue(tools.write_file("src/owned/new.py", "ok\n")["ok"])
            self.assertEqual(tools.read_file("src/context.txt")["text"], "context")
            (root / "src" / "owned" / "untracked.txt").write_text(
                "must not leave this machine\n", encoding="utf-8"
            )
            self.assertIn(
                "não rastreado",
                tools.read_file("src/owned/untracked.txt")["error"],
            )
            self.assertNotIn(
                "src/owned/untracked.txt",
                tools.list_files("src/owned/*")["files"],
            )
            self.assertEqual(
                tools.search_text("must not leave", "src/owned")["matches"],
                [],
            )
            with self.assertRaises(PermissionError):
                tools.write_file("src/context.txt", "no\n")
            with self.assertRaises(PermissionError):
                tools.read_file("private.txt")
            with self.assertRaisesRegex(ValueError, "protegido"):
                tools.read_file(".env.local")

    def test_worker_rejects_repository_root_as_allowed_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "caminhos relativos seguros"):
            WorkerSpec.model_validate({
                "id": "gemini-reader",
                "provider": "gemini",
                "model": "gemini-3.7-flash",
                "lens": "Inspect",
                "allowed_paths": ["."],
            })

    def test_gemini_workspace_rejects_symlink_escape_from_allowed_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "src" / "owned").mkdir(parents=True)
            (root / "src" / "private").mkdir(parents=True)
            (root / "src" / "private" / "secret.txt").write_text(
                "secret\n", encoding="utf-8"
            )
            (root / "src" / "owned" / "escape").symlink_to(
                root / "src" / "private", target_is_directory=True
            )
            self._commit_all(root)
            request = AdapterRequest(
                worker_id="gemini-reader", worktree=root, prompt="x",
                schema_path=root / "schema.json", run_dir=root / "run",
                timeout_seconds=60, mode="read_only", model="gemini-3.7-flash",
                allowed_paths=("src/owned",), writable_paths=(),
            )
            tools = WorkspaceTools(request)
            with self.assertRaisesRegex(PermissionError, "resolve fora"):
                tools.read_file("src/owned/escape/secret.txt")
            self.assertEqual(tools.search_text("secret")["matches"], [])

    def test_implementation_rejects_moving_base_ref(self) -> None:
        payload = {
            "mission_id": "implementation-pilot",
            "title": "Implementation pilot",
            "base_ref": "HEAD",
            "briefing": "Implement",
            "mode": "implementation",
            "authorized_external_providers": ["anthropic"],
            "commit_message": "feat(test): pilot",
            "gates": [{"argv": ["true"]}],
            "workers": [
                {
                    "id": "codex-writer",
                    "provider": "codex",
                    "role": "writer",
                    "lens": "Implement",
                    "allowed_paths": ["src"],
                    "writable_paths": ["src"],
                },
                {
                    "id": "claude-reviewer",
                    "provider": "claude",
                    "role": "reviewer",
                    "lens": "Review",
                    "allowed_paths": ["src"],
                },
            ],
        }
        with self.assertRaisesRegex(ValueError, "SHA completo"):
            MissionSpec.model_validate(payload)

    def test_corrective_base_must_descend_from_authorized_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "one.txt").write_text("one\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run([
                "git", "-c", "user.name=VOLC Test",
                "-c", "user.email=volc@example.invalid",
                "commit", "-qm", "one",
            ], cwd=root, check=True)
            root_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=root, check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            subprocess.run(["git", "branch", "-M", "main"], cwd=root, check=True)
            (root / "one.txt").write_text("two\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run([
                "git", "-c", "user.name=VOLC Test",
                "-c", "user.email=volc@example.invalid",
                "commit", "-qm", "two",
            ], cwd=root, check=True)
            candidate = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=root, check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            manager = WorktreeManager(root)
            self.assertEqual(
                manager.resolve_implementation_base(candidate, root_sha),
                candidate,
            )

    def test_ownership_rejects_ignored_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / ".gitignore").write_text(".env*\n", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "ok.txt").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=VOLC Test",
                    "-c",
                    "user.email=volc-test@example.invalid",
                    "commit",
                    "-qm",
                    "base",
                ],
                cwd=root,
                check=True,
            )
            (root / "src" / "ok.txt").write_text("changed\n", encoding="utf-8")
            (root / ".env.local").write_text("SECRET=x\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "arquivo protegido ignorado"):
                WorktreeManager.assert_only_allowed(root, ["src"])


class AdapterStreamTest(unittest.IsolatedAsyncioTestCase):
    async def test_accepts_jsonl_line_larger_than_asyncio_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = AdapterRequest(
                worker_id="large-line",
                worktree=root,
                prompt="",
                schema_path=root / "unused.json",
                run_dir=root / "run",
                timeout_seconds=30,
            )
            await _execute(
                [sys.executable, "-c", "print('x' * 100_000)"],
                request,
            )
            output = (request.run_dir / "stdout.jsonl").read_text(
                encoding="utf-8"
            )
            self.assertEqual(len(output), 100_001)

    async def test_silent_process_is_reported_but_not_killed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = AdapterRequest(
                worker_id="silent-worker",
                worktree=root,
                prompt="",
                schema_path=root / "unused.json",
                run_dir=root / "run",
                timeout_seconds=30,
                heartbeat_seconds=1,
            )
            terminal = io.StringIO()
            with redirect_stdout(terminal):
                await _execute(
                    [
                        sys.executable,
                        "-c",
                        "import time; time.sleep(1.2)",
                    ],
                    request,
                )

            heartbeats = [
                json.loads(line)
                for line in (request.run_dir / "heartbeat.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(heartbeats[0]["state"], "started")
            self.assertIn("active", [item["state"] for item in heartbeats])
            self.assertEqual(heartbeats[-1]["state"], "completed")
            self.assertIn("heartbeat OK silent-worker", terminal.getvalue())


if __name__ == "__main__":
    unittest.main()
