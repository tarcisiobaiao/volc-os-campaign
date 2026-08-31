import json
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from volc_agent_harness.models import MissionSpec
from volc_agent_harness.supervisor import eligibility_reason, run_once
from volc_agent_harness.supervisor_models import SupervisorJobSpec, SupervisorQueueSpec
from volc_agent_harness.supervisor_store import SupervisorStore, ownership_overlaps


def mission_payload(
    base_sha: str, task_id: str = "P01-T09", ratchet: bool = False
) -> dict:
    payload = {
        # O supervisor V3 despacha SOMENTE missão compilada: schema 3 com aceite
        # atômico e envelope de ownership declarados.
        "mission_schema_version": 3,
        "acceptance_ids": [f"{task_id}-A1"],
        "ownership_envelope": ["src/qg"],
        "mission_id": "supervisor-pilot",
        "title": "Supervisor pilot",
        "base_ref": base_sha,
        "briefing": "Implement the bounded pilot",
        "mode": "implementation",
        "task_ids": [task_id],
        "commit_message": "feat(test): supervisor pilot",
        # `{"argv": ["true"]}` era exatamente o argv livre que G1a fechou.
        # O equivalente tipado e read-only é o diff-check.
        "gates": [{"kind": "git_diff_check"}],
        "workers": [
            {
                "id": "codex-writer",
                "provider": "codex",
                "role": "writer",
                "lens": "Implement",
                "allowed_paths": ["src/qg"],
                "writable_paths": ["src/qg"],
            },
            {
                "id": "codex-reviewer",
                "provider": "codex",
                "role": "reviewer",
                "model": "gpt-5.5",
                "effort": "xhigh",
                "lens": "Review",
                "allowed_paths": ["src/qg"],
            },
        ],
    }
    if ratchet:
        payload["ratchet"] = {"enabled": True, "max_writer_attempts": 3}
    return payload


class SupervisorStoreTest(unittest.TestCase):
    def test_public_snapshot_never_exposes_owner_nonce(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = SupervisorStore(Path(temp) / "supervisor.sqlite")
            claim = store.claim(
                supervisor_id="volc",
                job_id="one",
                task_id="P01-T09",
                roadmap_sha="r" * 64,
                contract_digest="c" * 64,
                base_sha="a" * 40,
                lineage_root_sha="a" * 40,
                attempt=1,
                ownership=["src/qg"],
                lease_seconds=60,
                max_writer_concurrency=1,
            )
            assert claim is not None

            snapshot = store.snapshot()

            self.assertEqual(len(snapshot), 1)
            self.assertNotIn("owner_nonce", snapshot[0])
            self.assertNotIn(claim["owner_nonce"], json.dumps(snapshot))

    def test_ownership_overlap_respects_path_segments(self) -> None:
        self.assertTrue(ownership_overlaps(["src/qg"], ["src/qg/cards"]))
        self.assertTrue(ownership_overlaps(["src"], ["src/qg"]))
        self.assertFalse(ownership_overlaps(["src/a"], ["src/ab"]))

    def test_claim_is_idempotent_and_blocks_overlapping_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = SupervisorStore(Path(temp) / "supervisor.sqlite")
            common = {
                "supervisor_id": "volc",
                "roadmap_sha": "r" * 64,
                "contract_digest": "c" * 64,
                "base_sha": "a" * 40,
                "lineage_root_sha": "a" * 40,
                "attempt": 1,
                "lease_seconds": 3600,
                "max_writer_concurrency": 2,
            }
            first = store.claim(
                **common,
                job_id="one",
                task_id="P01-T09",
                ownership=["src/qg"],
            )
            duplicate = store.claim(
                **common,
                job_id="one",
                task_id="P01-T09",
                ownership=["src/qg"],
            )
            overlap = store.claim(
                **common,
                job_id="two",
                task_id="P01-T10",
                ownership=["src/qg/cards"],
            )
            disjoint = store.claim(
                **common,
                job_id="three",
                task_id="P01-T11",
                ownership=["backend/api"],
            )
            self.assertIsNotNone(first)
            self.assertIsNone(duplicate)
            self.assertIsNone(overlap)
            self.assertIsNotNone(disjoint)

    def test_events_form_hash_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "supervisor.sqlite"
            store = SupervisorStore(database)
            claim = store.claim(
                supervisor_id="volc",
                job_id="one",
                task_id="P01-T09",
                roadmap_sha="r" * 64,
                contract_digest="c" * 64,
                base_sha="a" * 40,
                lineage_root_sha="a" * 40,
                attempt=1,
                ownership=["src/qg"],
                lease_seconds=3600,
                max_writer_concurrency=1,
            )
            assert claim
            store.transition(claim["idempotency_key"], "running")
            store.transition(claim["idempotency_key"], "ready_for_human")
            with sqlite3.connect(database) as connection:
                rows = connection.execute(
                    "SELECT previous_event_hash, event_hash FROM events "
                    "ORDER BY sequence"
                ).fetchall()
            self.assertIsNone(rows[0][0])
            self.assertEqual(rows[1][0], rows[0][1])
            self.assertEqual(rows[2][0], rows[1][1])

    def test_terminal_state_refuses_resurrection(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = SupervisorStore(Path(temp) / "supervisor.sqlite")
            claim = store.claim(
                supervisor_id="volc",
                job_id="one",
                task_id="P01-T09",
                roadmap_sha="r" * 64,
                contract_digest="c" * 64,
                base_sha="a" * 40,
                lineage_root_sha="a" * 40,
                attempt=1,
                ownership=["src/qg"],
                lease_seconds=3600,
                max_writer_concurrency=1,
            )
            assert claim
            store.transition(claim["idempotency_key"], "running")
            store.transition(claim["idempotency_key"], "ready_for_human")
            with self.assertRaisesRegex(ValueError, "transição ilegal"):
                store.transition(claim["idempotency_key"], "running")

    def test_expired_lease_becomes_interrupted_before_new_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "supervisor.sqlite"
            store = SupervisorStore(database)
            first = store.claim(
                supervisor_id="volc",
                job_id="one",
                task_id="P01-T09",
                roadmap_sha="r" * 64,
                contract_digest="c" * 64,
                base_sha="a" * 40,
                lineage_root_sha="a" * 40,
                attempt=1,
                ownership=["src/qg"],
                lease_seconds=60,
                max_writer_concurrency=1,
            )
            assert first
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "UPDATE claims SET lease_expires_at='2000-01-01T00:00:00+00:00', "
                    "owner_pid=99999999"
                )
            second = store.claim(
                supervisor_id="volc",
                job_id="two",
                task_id="P01-T10",
                roadmap_sha="r" * 64,
                contract_digest="c" * 64,
                base_sha="a" * 40,
                lineage_root_sha="a" * 40,
                attempt=1,
                ownership=["src/qg"],
                lease_seconds=60,
                max_writer_concurrency=1,
            )
            self.assertIsNotNone(second)
            states = {item["task_id"]: item["state"] for item in store.snapshot()}
            self.assertEqual(states["P01-T09"], "interrupted")
            self.assertEqual(states["P01-T10"], "claimed")

    def test_expired_lease_with_live_owner_never_releases_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "supervisor.sqlite"
            store = SupervisorStore(database)
            common = {
                "supervisor_id": "volc",
                "roadmap_sha": "r" * 64,
                "contract_digest": "c" * 64,
                "base_sha": "a" * 40,
                "lineage_root_sha": "a" * 40,
                "attempt": 1,
                "ownership": ["src/qg"],
                "lease_seconds": 60,
                "max_writer_concurrency": 1,
            }
            first = store.claim(
                **common, job_id="one", task_id="P01-T09"
            )
            assert first
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "UPDATE claims SET lease_expires_at='2000-01-01T00:00:00+00:00'"
                )
            second = store.claim(
                **common, job_id="two", task_id="P01-T10"
            )
            self.assertIsNone(second)
            self.assertTrue(
                store.renew(first["idempotency_key"], first["owner_nonce"], 60)
            )


class SupervisorEligibilityTest(unittest.TestCase):
    def test_v1_requires_explicit_claude_authentication(self) -> None:
        payload = mission_payload("a" * 40)
        payload["workers"][1].update({
            "provider": "claude", "model": "opus", "effort": "high"
        })
        payload["authorized_external_providers"] = ["anthropic"]
        mission = MissionSpec.model_validate(payload)
        job = SupervisorJobSpec(
            job_id="supervisor-pilot",
            task_id="P01-T09",
            mission_path="mission.json",
        )
        tasks = {
            "P01-T09": {
                "id": "P01-T09", "status": "todo", "acceptance": ["x"]
            }
        }
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                eligibility_reason(
                    repo=Path("."), job=job, tasks=tasks,
                    mission=mission, base_sha="a" * 40,
                ),
                "credencial explícita ausente para provider: "
                "VOLC_CLAUDE_CODE_OAUTH_TOKEN",
            )
        with patch.dict(
            "os.environ", {"VOLC_CLAUDE_CODE_OAUTH_TOKEN": "dedicated"}, clear=True
        ):
            self.assertIsNone(
                eligibility_reason(
                    repo=Path("."), job=job, tasks=tasks,
                    mission=mission, base_sha="a" * 40,
                )
            )

    def test_supervisor_claim_uses_writer_write_scope_not_read_context(self) -> None:
        from volc_agent_harness.models import MissionSpec
        from volc_agent_harness.supervisor import _writer_ownership

        mission = MissionSpec.model_validate({
            "mission_schema_version": 3,
            "acceptance_ids": ["P01-T09-A1"],
            "ownership_envelope": ["src/qg"],
            "mission_id": "owned-write-scope",
            "title": "Owned write scope",
            "base_ref": "a" * 40,
            "briefing": "Implement",
            "mode": "implementation",
            "commit_message": "test: scope",
            # `{"argv": ["true"]}` era exatamente o argv livre que G1a fechou.
        # O equivalente tipado e read-only é o diff-check.
        "gates": [{"kind": "git_diff_check"}],
            "workers": [
                {
                    "id": "writer", "provider": "codex", "role": "writer",
                    "model": "gpt-5.6-sol", "effort": "high", "lens": "write",
                    "allowed_paths": ["src/owned", "docs/context.md"],
                    "writable_paths": ["src/owned"],
                },
                {
                    "id": "reviewer", "provider": "codex", "role": "reviewer",
                    "model": "gpt-5.5", "effort": "xhigh", "lens": "review",
                    "allowed_paths": ["src/owned"],
                },
            ],
        })
        self.assertEqual(_writer_ownership(mission), ["src/owned"])

    def setUp(self) -> None:
        self.job = SupervisorJobSpec(
            job_id="supervisor-pilot",
            task_id="P01-T09",
            mission_path="mission.json",
        )
        self.mission = MissionSpec.model_validate(mission_payload("a" * 40))
        self.tasks = {
            "P01-T09": {
                "id": "P01-T09",
                "status": "todo",
                "acceptance": ["prova nominal"],
            }
        }

    def reason(self) -> str | None:
        return eligibility_reason(
            repo=Path("."),
            job=self.job,
            tasks=self.tasks,
            mission=self.mission,
            base_sha="a" * 40,
        )

    def test_eligible_task_has_explicit_acceptance_and_linkage(self) -> None:
        self.assertIsNone(self.reason())

    def test_editorial_order_never_becomes_dependency(self) -> None:
        self.tasks["P01-T09"]["order"] = 9
        self.tasks["P01-T08"] = {"id": "P01-T08", "status": "todo"}
        self.assertIsNone(self.reason())

    def test_declared_open_dependency_blocks(self) -> None:
        self.tasks["P01-T09"]["dependencies"] = ["P01-T08"]
        self.tasks["P01-T08"] = {"id": "P01-T08", "status": "partial"}
        self.assertEqual(self.reason(), "dependência aberta: P01-T08")

    def test_missing_acceptance_blocks(self) -> None:
        self.tasks["P01-T09"].pop("acceptance")
        self.assertEqual(self.reason(), "critérios de aceite ausentes")

    def test_missing_task_linkage_blocks(self) -> None:
        self.mission = MissionSpec.model_validate(
            mission_payload("a" * 40, task_id="P01-T10")
        )
        self.tasks["P01-T10"] = {
            "id": "P01-T10",
            "status": "todo",
            "acceptance": ["x"],
        }
        self.assertEqual(self.reason(), "missão não declara o task_id do job")


class SupervisorRunTest(unittest.TestCase):
    def _repository(self, root: Path) -> str:
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        roadmap = {
            "initiatives": [
                {
                    "id": "P01",
                    "tasks": [
                        {
                            "id": "P01-T09",
                            "status": "todo",
                            "acceptance": ["candidate reviewed"],
                        }
                    ],
                }
            ]
        }
        (root / "volc-os-workbook").mkdir()
        (root / "volc-os-workbook" / "ROADMAP-VIVO.json").write_text(
            json.dumps(roadmap), encoding="utf-8"
        )
        (root / "seed.txt").write_text("base\n", encoding="utf-8")
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
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def _candidate_commits(self, root: Path) -> tuple[str, str]:
        original_branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        subprocess.run(["git", "switch", "-qc", "candidate-fixtures"], cwd=root, check=True)
        commits = []
        for value in ("candidate-one\n", "candidate-two\n"):
            (root / "seed.txt").write_text(value, encoding="utf-8")
            subprocess.run(["git", "add", "seed.txt"], cwd=root, check=True)
            subprocess.run(
                [
                    "git", "-c", "user.name=VOLC Test",
                    "-c", "user.email=volc-test@example.invalid",
                    "commit", "-qm", value.strip(),
                ],
                cwd=root,
                check=True,
            )
            commits.append(subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=root, check=True,
                capture_output=True, text=True,
            ).stdout.strip())
        subprocess.run(["git", "switch", "-q", original_branch], cwd=root, check=True)
        return commits[0], commits[1]

    def _add_roadmap_tasks(self, root: Path, *task_ids: str) -> str:
        path = root / "volc-os-workbook" / "ROADMAP-VIVO.json"
        roadmap = json.loads(path.read_text(encoding="utf-8"))
        tasks = roadmap["initiatives"][0]["tasks"]
        known = {task["id"] for task in tasks}
        tasks.extend(
            {
                "id": task_id,
                "status": "todo",
                "acceptance": [f"{task_id} reviewed"],
            }
            for task_id in task_ids
            if task_id not in known
        )
        path.write_text(json.dumps(roadmap), encoding="utf-8")
        subprocess.run(["git", "add", str(path)], cwd=root, check=True)
        subprocess.run(
            [
                "git", "-c", "user.name=VOLC Test",
                "-c", "user.email=volc-test@example.invalid",
                "commit", "-qm", "add concurrent roadmap fixtures",
            ],
            cwd=root,
            check=True,
        )
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True,
            capture_output=True, text=True,
        ).stdout.strip()

    def test_v1_runs_disjoint_jobs_in_the_same_wave(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            head = self._add_roadmap_tasks(root, "P01-T10")
            for name, task_id, ownership in (
                ("one", "P01-T09", "src/one"),
                ("two", "P01-T10", "src/two"),
            ):
                payload = mission_payload(head, task_id=task_id)
                payload["mission_id"] = f"mission-{name}"
                payload["workers"][0]["allowed_paths"] = [ownership]
                payload["workers"][0]["writable_paths"] = [ownership]
                payload["workers"][1]["allowed_paths"] = [ownership]
                (root / f"{name}.json").write_text(
                    json.dumps(payload), encoding="utf-8"
                )
            queue = SupervisorQueueSpec(
                supervisor_id="volc-v1",
                max_writer_concurrency=2,
                jobs=[
                    {
                        "job_id": "one", "task_id": "P01-T09",
                        "mission_path": "one.json", "priority": 1,
                    },
                    {
                        "job_id": "two", "task_id": "P01-T10",
                        "mission_path": "two.json", "priority": 2,
                    },
                ],
            )
            barrier = threading.Barrier(2)
            active: set[str] = set()
            active_lock = threading.Lock()

            def fake_runner(_repo: Path, mission: MissionSpec):
                with active_lock:
                    active.add(mission.mission_id)
                barrier.wait(timeout=2)
                run_dir = root / "runs" / mission.mission_id
                run_dir.mkdir(parents=True)
                return run_dir, {
                    "ok": True,
                    "writer_commit": head,
                    "candidate_status": "ready_for_human",
                }

            result = run_once(
                root,
                queue,
                store=SupervisorStore(root / "runs" / "supervisor.sqlite"),
                runner=fake_runner,
            )

            self.assertEqual(result["status"], "batch")
            self.assertEqual(active, {"mission-one", "mission-two"})
            self.assertEqual(
                [item["job_id"] for item in result["results"]],
                ["one", "two"],
            )
            self.assertTrue(
                all(item["status"] == "ready_for_human" for item in result["results"])
            )

    def test_v1_keeps_overlapping_job_for_a_later_wave(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            head = self._add_roadmap_tasks(root, "P01-T10")
            for name, task_id in (("one", "P01-T09"), ("two", "P01-T10")):
                payload = mission_payload(head, task_id=task_id)
                payload["mission_id"] = f"mission-{name}"
                payload["workers"][0]["allowed_paths"] = ["src/shared"]
                payload["workers"][0]["writable_paths"] = ["src/shared"]
                payload["workers"][1]["allowed_paths"] = ["src/shared"]
                (root / f"{name}.json").write_text(
                    json.dumps(payload), encoding="utf-8"
                )
            queue = SupervisorQueueSpec(
                supervisor_id="volc-v1",
                max_writer_concurrency=2,
                jobs=[
                    {"job_id": "one", "task_id": "P01-T09", "mission_path": "one.json"},
                    {"job_id": "two", "task_id": "P01-T10", "mission_path": "two.json"},
                ],
            )
            calls: list[str] = []

            def fake_runner(_repo: Path, mission: MissionSpec):
                calls.append(mission.mission_id)
                run_dir = root / "runs" / mission.mission_id
                run_dir.mkdir(parents=True)
                return run_dir, {
                    "ok": True,
                    "writer_commit": head,
                    "candidate_status": "ready_for_human",
                }

            result = run_once(
                root,
                queue,
                store=SupervisorStore(root / "runs" / "supervisor.sqlite"),
                runner=fake_runner,
            )

            self.assertEqual(calls, ["mission-one"])
            self.assertEqual(result["status"], "batch")
            self.assertEqual(result["blockers"], [{
                "job_id": "two",
                "reason": "ownership sobreposto com one",
            }])

    def test_writer_concurrency_accepts_one_through_four(self) -> None:
        for value in range(1, 5):
            queue = SupervisorQueueSpec(
                supervisor_id="volc-v1",
                max_writer_concurrency=value,
                jobs=[{
                    "job_id": "one", "task_id": "P01-T09",
                    "mission_path": "one.json",
                }],
            )
            self.assertEqual(queue.max_writer_concurrency, value)

    def test_writer_concurrency_rejects_zero_and_five(self) -> None:
        for value in (0, 5):
            with self.assertRaises(ValueError):
                SupervisorQueueSpec(
                    supervisor_id="volc-v1",
                    max_writer_concurrency=value,
                    jobs=[{
                        "job_id": "one", "task_id": "P01-T09",
                        "mission_path": "one.json",
                    }],
                )

    def test_ready_candidate_is_recorded_and_never_dispatched_twice(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            head = self._repository(root)
            mission_path = root / "mission.json"
            mission_path.write_text(
                json.dumps(mission_payload(head)), encoding="utf-8"
            )
            queue = SupervisorQueueSpec(
                supervisor_id="volc",
                jobs=[
                    {
                        "job_id": "pilot",
                        "task_id": "P01-T09",
                        "mission_path": "mission.json",
                    }
                ],
            )
            store = SupervisorStore(root / "runs" / "supervisor.sqlite")
            calls = []

            def fake_runner(_repo: Path, _mission: MissionSpec):
                calls.append(True)
                run_dir = root / "runs" / "run-1"
                run_dir.mkdir(parents=True)
                return run_dir, {
                    "ok": True,
                    "writer_commit": head,
                    "candidate_status": "ready_for_human",
                }

            first = run_once(root, queue, store=store, runner=fake_runner)
            second = run_once(root, queue, store=store, runner=fake_runner)
            self.assertEqual(first["status"], "ready_for_human")
            self.assertEqual(second["status"], "idle")
            self.assertEqual(len(calls), 1)

    def test_ok_execution_with_changes_requested_is_not_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            head = self._repository(root)
            (root / "mission.json").write_text(
                json.dumps(mission_payload(head)), encoding="utf-8"
            )
            queue = SupervisorQueueSpec(
                supervisor_id="volc",
                jobs=[
                    {
                        "job_id": "pilot",
                        "task_id": "P01-T09",
                        "mission_path": "mission.json",
                    }
                ],
            )
            store = SupervisorStore(root / "runs" / "supervisor.sqlite")

            def fake_runner(_repo: Path, _mission: MissionSpec):
                run_dir = root / "runs" / "run-1"
                run_dir.mkdir(parents=True)
                return run_dir, {
                    "ok": True,
                    "writer_commit": head,
                    "candidate_status": "changes_requested",
                    "workers": [{
                        "role": "reviewer",
                        "result": {
                            "confirmed_findings": [{"title": "corrigir"}],
                            "required_changes": ["corrigir"],
                        },
                    }],
                }

            result = run_once(root, queue, store=store, runner=fake_runner)
            self.assertEqual(result["status"], "changes_requested")

    def test_ready_without_real_git_candidate_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            head = self._repository(root)
            (root / "mission.json").write_text(
                json.dumps(mission_payload(head)), encoding="utf-8"
            )
            queue = SupervisorQueueSpec(
                supervisor_id="volc",
                jobs=[{
                    "job_id": "pilot", "task_id": "P01-T09",
                    "mission_path": "mission.json",
                }],
            )
            store = SupervisorStore(root / "runs" / "supervisor.sqlite")

            def fake_runner(_repo: Path, _mission: MissionSpec):
                run_dir = root / "runs" / "invalid"
                run_dir.mkdir(parents=True)
                return run_dir, {
                    "ok": True,
                    "writer_commit": "b" * 40,
                    "candidate_status": "ready_for_human",
                }

            result = run_once(root, queue, store=store, runner=fake_runner)
            self.assertEqual(result["status"], "blocked")

    def test_ratchet_feeds_review_findings_to_bounded_corrective_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            head = self._repository(root)
            candidate_one, candidate_two = self._candidate_commits(root)
            (root / "mission.json").write_text(
                json.dumps(mission_payload(head, ratchet=True)), encoding="utf-8"
            )
            queue = SupervisorQueueSpec(
                supervisor_id="volc",
                jobs=[{
                    "job_id": "pilot",
                    "task_id": "P01-T09",
                    "mission_path": "mission.json",
                    "max_attempts": 3,
                }],
            )
            store = SupervisorStore(root / "runs" / "supervisor.sqlite")
            seen: list[MissionSpec] = []

            def fake_runner(_repo: Path, mission: MissionSpec):
                seen.append(mission)
                run_dir = root / "runs" / f"run-{mission.attempt}"
                run_dir.mkdir(parents=True)
                if mission.attempt == 1:
                    result = {
                        "run_id": "run-1",
                        "ok": True,
                        "writer_commit": candidate_one,
                        "candidate_status": "changes_requested",
                        "workers": [{
                            "role": "reviewer",
                            "result": {
                                "confirmed_findings": [{
                                    "severity": "high",
                                    "title": "ausência virou zero",
                                    "evidence": "src/x.py:10",
                                }],
                                "required_changes": ["preservar None"],
                            },
                        }],
                    }
                else:
                    result = {
                        "run_id": "run-2",
                        "ok": True,
                        "writer_commit": candidate_two,
                        "candidate_status": "ready_for_human",
                        "workers": [],
                    }
                (run_dir / "mission-result.json").write_text(
                    json.dumps(result), encoding="utf-8"
                )
                return run_dir, result

            result = run_once(root, queue, store=store, runner=fake_runner)

            self.assertEqual(result["status"], "ready_for_human")
            self.assertEqual(result["attempt"], 2)
            self.assertEqual([mission.attempt for mission in seen], [1, 2])
            self.assertEqual(seen[1].base_ref, candidate_one)
            self.assertEqual(seen[1].lineage_root_sha, head)
            self.assertIn("preservar None", seen[1].briefing)

    def test_ratchet_blocks_same_tree_without_third_model_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            head = self._repository(root)
            candidate_one, _candidate_two = self._candidate_commits(root)
            (root / "mission.json").write_text(
                json.dumps(mission_payload(head, ratchet=True)), encoding="utf-8"
            )
            queue = SupervisorQueueSpec(
                supervisor_id="volc",
                jobs=[{
                    "job_id": "pilot",
                    "task_id": "P01-T09",
                    "mission_path": "mission.json",
                    "max_attempts": 3,
                }],
            )
            store = SupervisorStore(root / "runs" / "supervisor.sqlite")
            calls = 0

            def fake_runner(_repo: Path, mission: MissionSpec):
                nonlocal calls
                calls += 1
                run_dir = root / "runs" / f"run-{mission.attempt}"
                run_dir.mkdir(parents=True)
                result = {
                    "ok": True,
                    "writer_commit": candidate_one,
                    "candidate_status": "changes_requested",
                    "workers": [{
                        "role": "reviewer",
                        "result": {
                            "confirmed_findings": [{"title": "continua quebrado"}],
                            "required_changes": ["corrigir de verdade"],
                        },
                    }],
                }
                (run_dir / "mission-result.json").write_text(
                    json.dumps(result), encoding="utf-8"
                )
                return run_dir, result

            result = run_once(root, queue, store=store, runner=fake_runner)

            self.assertEqual(result["status"], "blocked")
            self.assertIn("sem progresso", result["reason"])
            self.assertEqual(calls, 2)

    def test_ratchet_blocks_a_b_a_oscillation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            head = self._repository(root)
            candidate_one, candidate_two = self._candidate_commits(root)
            (root / "mission.json").write_text(
                json.dumps(mission_payload(head, ratchet=True)), encoding="utf-8"
            )
            queue = SupervisorQueueSpec(
                supervisor_id="volc",
                jobs=[{
                    "job_id": "pilot", "task_id": "P01-T09",
                    "mission_path": "mission.json", "max_attempts": 3,
                }],
            )
            store = SupervisorStore(root / "runs" / "supervisor.sqlite")
            candidates = [candidate_one, candidate_two, candidate_one]
            calls = 0

            def fake_runner(_repo: Path, mission: MissionSpec):
                nonlocal calls
                candidate = candidates[calls]
                calls += 1
                run_dir = root / "runs" / f"aba-{mission.attempt}"
                run_dir.mkdir(parents=True)
                result = {
                    "ok": True,
                    "writer_commit": candidate,
                    "candidate_status": "changes_requested",
                    "workers": [{
                        "role": "reviewer",
                        "result": {
                            "confirmed_findings": [{"title": f"falha-{calls}"}],
                            "required_changes": [f"corrigir-{calls}"],
                        },
                    }],
                }
                (run_dir / "mission-result.json").write_text(
                    json.dumps(result), encoding="utf-8"
                )
                return run_dir, result

            result = run_once(root, queue, store=store, runner=fake_runner)
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(calls, 3)

    def test_ratchet_blocks_repeated_finding_even_when_tree_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            head = self._repository(root)
            candidate_one, candidate_two = self._candidate_commits(root)
            (root / "mission.json").write_text(
                json.dumps(mission_payload(head, ratchet=True)), encoding="utf-8"
            )
            queue = SupervisorQueueSpec(
                supervisor_id="volc",
                jobs=[{
                    "job_id": "pilot", "task_id": "P01-T09",
                    "mission_path": "mission.json", "max_attempts": 3,
                }],
            )
            candidates = iter((candidate_one, candidate_two))

            def fake_runner(_repo: Path, mission: MissionSpec):
                run_dir = root / "runs" / f"finding-{mission.attempt}"
                run_dir.mkdir(parents=True)
                result = {
                    "ok": True,
                    "writer_commit": next(candidates),
                    "candidate_status": "changes_requested",
                    "workers": [{
                        "role": "reviewer",
                        "result": {
                            "confirmed_findings": [{"title": "mesma falha"}],
                            "required_changes": ["mesma correção"],
                        },
                    }],
                }
                (run_dir / "mission-result.json").write_text(
                    json.dumps(result), encoding="utf-8"
                )
                return run_dir, result

            result = run_once(
                root, queue,
                store=SupervisorStore(root / "runs" / "supervisor.sqlite"),
                runner=fake_runner,
            )
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["attempt"], 2)

    def test_failed_gate_can_feed_one_bounded_corrective_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            head = self._repository(root)
            candidate_one, _ = self._candidate_commits(root)
            (root / "mission.json").write_text(
                json.dumps(mission_payload(head, ratchet=True)), encoding="utf-8"
            )
            queue = SupervisorQueueSpec(
                supervisor_id="volc",
                jobs=[{
                    "job_id": "pilot", "task_id": "P01-T09",
                    "mission_path": "mission.json", "max_attempts": 3,
                }],
            )
            seen: list[MissionSpec] = []

            def fake_runner(_repo: Path, mission: MissionSpec):
                seen.append(mission)
                run_dir = root / "runs" / f"gate-{mission.attempt}"
                run_dir.mkdir(parents=True)
                if mission.attempt == 1:
                    result = {
                        "ok": False,
                        "workers": [{
                            "worker_id": "codex-writer",
                            "role": "writer",
                            "error": "RuntimeError: gate 1 falhou com exit=1",
                        }],
                    }
                else:
                    result = {
                        "ok": True,
                        "writer_commit": candidate_one,
                        "candidate_status": "ready_for_human",
                    }
                (run_dir / "mission-result.json").write_text(
                    json.dumps(result), encoding="utf-8"
                )
                return run_dir, result

            result = run_once(
                root, queue,
                store=SupervisorStore(root / "runs" / "supervisor.sqlite"),
                runner=fake_runner,
            )
            self.assertEqual(result["status"], "ready_for_human")
            self.assertEqual([item.attempt for item in seen], [1, 2])
            self.assertEqual(seen[1].base_ref, head)
            self.assertIn("gate 1 falhou", seen[1].briefing)

    def test_restart_refuses_corrupt_corrective_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            head = self._repository(root)
            candidate_one, _ = self._candidate_commits(root)
            (root / "mission.json").write_text(
                json.dumps(mission_payload(head, ratchet=True)), encoding="utf-8"
            )
            first_queue = SupervisorQueueSpec(
                supervisor_id="volc",
                jobs=[{
                    "job_id": "pilot", "task_id": "P01-T09",
                    "mission_path": "mission.json", "max_attempts": 1,
                }],
            )
            store_path = root / "runs" / "supervisor.sqlite"

            def first_runner(_repo: Path, _mission: MissionSpec):
                run_dir = root / "runs" / "corrupt"
                run_dir.mkdir(parents=True)
                return run_dir, {
                    "ok": True,
                    "writer_commit": candidate_one,
                    "candidate_status": "changes_requested",
                    "workers": [{
                        "role": "reviewer",
                        "result": {
                            "confirmed_findings": [{"title": "não persistido"}],
                            "required_changes": ["não persistido"],
                        },
                    }],
                }

            first = run_once(
                root, first_queue,
                store=SupervisorStore(store_path), runner=first_runner,
            )
            self.assertEqual(first["status"], "changes_requested")
            calls = 0

            def forbidden_runner(_repo: Path, _mission: MissionSpec):
                nonlocal calls
                calls += 1
                raise AssertionError("não deveria executar")

            second_queue = SupervisorQueueSpec(
                supervisor_id="volc",
                jobs=[{
                    "job_id": "pilot", "task_id": "P01-T09",
                    "mission_path": "mission.json", "max_attempts": 3,
                }],
            )
            second = run_once(
                root, second_queue,
                store=SupervisorStore(store_path), runner=forbidden_runner,
            )
            self.assertEqual(second["status"], "idle")
            self.assertIn("recibo corretivo", second["blockers"][0]["reason"])
            self.assertEqual(calls, 0)

    def test_restart_preserves_lineage_after_main_advances(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original_head = self._repository(root)
            candidate_one, candidate_two = self._candidate_commits(root)
            mission_path = root / "mission.json"
            mission_path.write_text(
                json.dumps(mission_payload(original_head, ratchet=True)),
                encoding="utf-8",
            )
            first_queue = SupervisorQueueSpec(
                supervisor_id="volc",
                jobs=[{
                    "job_id": "pilot", "task_id": "P01-T09",
                    "mission_path": "mission.json", "max_attempts": 1,
                }],
            )
            store_path = root / "runs" / "supervisor.sqlite"

            def first_runner(_repo: Path, mission: MissionSpec):
                run_dir = root / "runs" / "restart-1"
                run_dir.mkdir(parents=True)
                result = {
                    "ok": True,
                    "writer_commit": candidate_one,
                    "candidate_status": "changes_requested",
                    "workers": [{
                        "role": "reviewer",
                        "result": {
                            "confirmed_findings": [{"title": "persistir raiz"}],
                            "required_changes": ["preservar raiz original"],
                        },
                    }],
                }
                (run_dir / "mission-result.json").write_text(
                    json.dumps(result), encoding="utf-8"
                )
                return run_dir, result

            first = run_once(
                root, first_queue,
                store=SupervisorStore(store_path), runner=first_runner,
            )
            self.assertEqual(first["status"], "changes_requested")

            (root / "main-advanced.txt").write_text("parallel\n", encoding="utf-8")
            subprocess.run(["git", "add", "main-advanced.txt"], cwd=root, check=True)
            subprocess.run(
                [
                    "git", "-c", "user.name=VOLC Test",
                    "-c", "user.email=volc-test@example.invalid",
                    "commit", "-qm", "advance main",
                ], cwd=root, check=True,
            )
            new_head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=root, check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            mission_path.write_text(
                json.dumps(mission_payload(new_head, ratchet=True)), encoding="utf-8"
            )
            seen: list[MissionSpec] = []

            def second_runner(_repo: Path, mission: MissionSpec):
                seen.append(mission)
                run_dir = root / "runs" / "restart-2"
                run_dir.mkdir(parents=True)
                return run_dir, {
                    "ok": True,
                    "writer_commit": candidate_two,
                    "candidate_status": "ready_for_human",
                }

            second_queue = SupervisorQueueSpec(
                supervisor_id="volc",
                jobs=[{
                    "job_id": "pilot", "task_id": "P01-T09",
                    "mission_path": "mission.json", "max_attempts": 3,
                }],
            )
            second = run_once(
                root, second_queue,
                store=SupervisorStore(store_path), runner=second_runner,
            )
            self.assertEqual(second["status"], "ready_for_human")
            self.assertEqual(seen[0].base_ref, candidate_one)
            self.assertEqual(seen[0].lineage_root_sha, original_head)

    def test_wall_budget_blocks_even_if_runner_claims_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            head = self._repository(root)
            candidate_one, _ = self._candidate_commits(root)
            payload = mission_payload(head, ratchet=True)
            payload["ratchet"]["max_wall_seconds"] = 60
            (root / "mission.json").write_text(json.dumps(payload), encoding="utf-8")
            queue = SupervisorQueueSpec(
                supervisor_id="volc",
                jobs=[{
                    "job_id": "pilot", "task_id": "P01-T09",
                    "mission_path": "mission.json", "max_attempts": 3,
                }],
            )

            def fake_runner(_repo: Path, _mission: MissionSpec):
                run_dir = root / "runs" / "wall"
                run_dir.mkdir(parents=True)
                return run_dir, {
                    "ok": True,
                    "writer_commit": candidate_one,
                    "candidate_status": "ready_for_human",
                }

            with patch(
                "volc_agent_harness.supervisor.time.monotonic",
                side_effect=[0.0, 0.0, 61.0],
            ):
                result = run_once(
                    root, queue,
                    store=SupervisorStore(root / "runs" / "supervisor.sqlite"),
                    runner=fake_runner,
                )
            self.assertEqual(result["status"], "blocked")
            self.assertIn("tempo", result["reason"])


if __name__ == "__main__":
    unittest.main()
