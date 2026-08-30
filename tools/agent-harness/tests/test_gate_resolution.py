import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from volc_agent_harness.gates import (
    GateConfigurationError,
    project_venv_overlay,
    resolve_gate_argv,
)


class GateResolutionTest(unittest.TestCase):
    def _repo_with_linked_worktree(self, root: Path) -> tuple[Path, Path]:
        repo = root / "repo"
        worker = root / "worker"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "VOLC Test"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "volc-test@example.invalid"],
            cwd=repo,
            check=True,
        )
        (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
        subprocess.run(
            ["git", "worktree", "add", "-qb", "worker", str(worker), "HEAD"],
            cwd=repo,
            check=True,
        )
        return repo, worker

    def test_resolves_missing_project_venv_from_registered_primary_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, worker = self._repo_with_linked_worktree(Path(temp))
            interpreter = repo / "backend" / ".venv" / "bin" / "python"
            interpreter.parent.mkdir(parents=True)
            interpreter.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            interpreter.chmod(0o755)

            gate = resolve_gate_argv(
                ["backend/.venv/bin/python", "-m", "pytest"],
                repo=repo,
                worktree=worker,
            )

            self.assertEqual(gate.declared_executable, "backend/.venv/bin/python")
            self.assertTrue(Path(gate.resolved_executable).samefile(interpreter))
            self.assertTrue(Path(gate.argv[0]).samefile(interpreter))
            self.assertTrue(gate.argv[0].endswith("backend/.venv/bin/python"))

    def test_resolves_command_after_env_assignments(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, worker = self._repo_with_linked_worktree(Path(temp))
            interpreter = repo / "backend" / ".venv" / "bin" / "python"
            interpreter.parent.mkdir(parents=True)
            interpreter.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            interpreter.chmod(0o755)

            gate = resolve_gate_argv(
                ["env", "PYTHONPATH=backend:.", "backend/.venv/bin/python", "-V"],
                repo=repo,
                worktree=worker,
            )

            self.assertEqual(gate.executable_index, 2)
            self.assertTrue(Path(gate.argv[2]).samefile(interpreter))
            self.assertTrue(gate.argv[2].endswith("backend/.venv/bin/python"))

    def test_does_not_fallback_for_an_arbitrary_missing_script(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, worker = self._repo_with_linked_worktree(Path(temp))
            with self.assertRaisesRegex(
                GateConfigurationError, "executável relativo do gate ausente"
            ):
                resolve_gate_argv(
                    ["scripts/missing.sh"],
                    repo=repo,
                    worktree=worker,
                )

    def test_missing_project_interpreter_fails_with_checked_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, worker = self._repo_with_linked_worktree(Path(temp))
            with self.assertRaisesRegex(
                GateConfigurationError, "worktree primária registrada"
            ):
                resolve_gate_argv(
                    ["backend/.venv/bin/python", "-m", "pytest"],
                    repo=repo,
                    worktree=worker,
                )

    def test_ignores_agent_owned_fake_venv(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, worker = self._repo_with_linked_worktree(Path(temp))
            canonical = repo / "backend" / ".venv" / "bin" / "python"
            canonical.parent.mkdir(parents=True)
            canonical.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            canonical.chmod(0o755)
            fake = worker / "backend" / ".venv" / "bin" / "python"
            fake.parent.mkdir(parents=True)
            fake.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
            fake.chmod(0o755)

            gate = resolve_gate_argv(
                ["backend/.venv/bin/python", "-V"],
                repo=repo,
                worktree=worker,
            )

            self.assertTrue(Path(gate.argv[0]).samefile(canonical))
            self.assertFalse(Path(gate.argv[0]).samefile(fake))

    def test_overlay_refuses_agent_owned_fake_venv(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, worker = self._repo_with_linked_worktree(Path(temp))
            canonical = repo / "backend" / ".venv" / "bin" / "python"
            canonical.parent.mkdir(parents=True)
            canonical.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            canonical.chmod(0o755)
            fake = worker / "backend" / ".venv" / "bin" / "python"
            fake.parent.mkdir(parents=True)
            fake.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
            fake.chmod(0o755)

            with self.assertRaisesRegex(GateConfigurationError, "destino preexistente"):
                with project_venv_overlay(repo=repo, worktree=worker):
                    pass

    def test_absolute_missing_interpreter_does_not_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, worker = self._repo_with_linked_worktree(Path(temp))
            with self.assertRaisesRegex(GateConfigurationError, "executável absoluto"):
                resolve_gate_argv(
                    [str(Path(temp) / "missing-python")],
                    repo=repo,
                    worktree=worker,
                )

    def test_path_command_is_left_for_execvp(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, worker = self._repo_with_linked_worktree(Path(temp))
            gate = resolve_gate_argv(["npm", "run", "build"], repo=repo, worktree=worker)
            self.assertEqual(gate.argv, ["npm", "run", "build"])
            self.assertEqual(gate.resolved_executable, "npm")

    def test_overlay_exposes_and_removes_primary_venv_for_legacy_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, worker = self._repo_with_linked_worktree(Path(temp))
            venv = repo / "backend" / ".venv"
            interpreter = venv / "bin" / "python"
            interpreter.parent.mkdir(parents=True)
            interpreter.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            interpreter.chmod(0o755)
            overlay = worker / "backend" / ".venv"

            with project_venv_overlay(repo=repo, worktree=worker) as source:
                self.assertTrue(overlay.is_symlink())
                self.assertTrue((overlay / "bin" / "python").samefile(interpreter))
                self.assertTrue(source and source.samefile(venv))

            self.assertFalse(overlay.exists())
            self.assertFalse(overlay.is_symlink())

    def test_overlay_refuses_preexisting_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, worker = self._repo_with_linked_worktree(Path(temp))
            interpreter = repo / "backend" / ".venv" / "bin" / "python"
            interpreter.parent.mkdir(parents=True)
            interpreter.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            interpreter.chmod(0o755)
            destination = worker / "backend" / ".venv"
            destination.mkdir(parents=True)

            with self.assertRaisesRegex(GateConfigurationError, "destino preexistente"):
                with project_venv_overlay(repo=repo, worktree=worker):
                    pass


if __name__ == "__main__":
    unittest.main()
