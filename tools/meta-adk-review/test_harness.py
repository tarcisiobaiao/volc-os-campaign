from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock

from google import genai

from config import LANES, MODEL, THINKING, lane
from host import Host, digest, safe
from orchestrate import runtime_launcher
from status import lane_status
from workflow import build_workflow


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(
            ["git", "checkout", "-qb", "sprint/meta-adk-v2-fixture"], cwd=self.root, check=True
        )
        self.source = self.root / "backend/app/trafego/meta/draft_storage.py"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("value = 1\n")
        self.test = self.root / "backend/tests/test_meta_draft_fixture.py"
        self.test.parent.mkdir(parents=True)
        self.test.write_text("def test_fixture():\n    assert True\n")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(
            [
                "git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "-qm", "fixture",
            ],
            cwd=self.root,
            check=True,
        )
        self.run_dir = self.root.parent / (self.root.name + "-report")
        self.args = argparse.Namespace(
            workspace=self.root,
            run_dir=self.run_dir,
            max_calls=8,
            max_tokens=10_000,
            max_edits=4,
            timeout=600,
        )
        os.environ["VOLC_META_ADK_DEPENDENCY_ROOT"] = str(self.root)
        self.host = Host(self.args, lane("wizard_ux"))

    def tearDown(self):
        self.temp.cleanup()
        if self.run_dir.exists():
            import shutil
            shutil.rmtree(self.run_dir)

    def test_exact_model_and_high_are_immutable(self):
        self.assertEqual(MODEL, "gemini-3.8-flash")
        self.assertEqual(THINKING, "HIGH")

    def test_four_focused_lanes_have_disjoint_names(self):
        self.assertEqual(set(LANES), {"wizard_ux", "creative_system", "publishing_contract", "measurement_ops"})
        self.assertEqual(len({item.slug for item in LANES.values()}), 4)

    def test_secret_traversal_symlink_and_cross_lane_writes_are_refused(self):
        for path in ("../x.py", "/etc/passwd", "backend/.env", "docs/secret.json"):
            with self.assertRaises(ValueError):
                self.host._path(path)
        link = self.source.with_name("link.py")
        link.symlink_to(self.source)
        with self.assertRaises(ValueError):
            self.host._path("backend/app/trafego/meta/link.py", write=True)
        with self.assertRaises(ValueError):
            self.host._path("backend/app/criativo/execucao.py", write=True)

    def test_guarded_patch_applies_and_invalidates_old_gate(self):
        relative = str(self.source.relative_to(self.root))
        read = self.host.read_file(relative)
        self.host.gates["backend:x"] = {"returncode": 0}
        result = self.host.replace_text(relative, read["sha256"], "value = 1", "value = 2")
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(self.source.read_text(), "value = 2\n")
        self.assertEqual(self.host.gates, {})

    def test_stale_patch_is_refused(self):
        relative = str(self.source.relative_to(self.root))
        read = self.host.read_file(relative)
        self.source.write_text("value = 3\n")
        result = self.host.replace_text(relative, read["sha256"], "value = 3", "value = 4")
        self.assertIn("error", result)
        self.assertEqual(self.source.read_text(), "value = 3\n")

    def test_new_file_is_restricted_to_test_prefix_and_never_overwrites(self):
        refused = self.host.create_test_file("backend/app/trafego/meta/new.py", "value = 1")
        self.assertIn("error", refused)
        created = self.host.create_test_file(
            "backend/tests/test_meta_draft_new.py", "def test_new():\n    assert True"
        )
        self.assertTrue(created.get("ok"), created)
        again = self.host.create_test_file(
            "backend/tests/test_meta_draft_new.py", "def test_new():\n    assert False"
        )
        self.assertIn("error", again)

    def test_budget_blocks_before_dispatch(self):
        self.host.calls = self.args.max_calls
        with self.assertRaises(RuntimeError):
            self.host.before_model(MagicMock(agent_name="meta_engineer"), MagicMock())

    def test_effective_model_mismatch_fails_closed(self):
        response = MagicMock(model_version="other-model")
        with self.assertRaises(RuntimeError):
            self.host.after_model(MagicMock(agent_name="meta_engineer"), response)

    def test_candidate_requires_patch_grounding_and_post_edit_test(self):
        raw = json.dumps({
            "verdict": "candidate", "findings": [], "coverage": [], "remaining": [], "summary": "ok"
        })
        self.host.grounded = True
        self.host.edits = 1
        self.host.gates["backend:x"] = {
            "gate": "backend", "target": "x", "returncode": 0, "edits": 1
        }
        route = self.host.evaluate_critic(raw, max_rounds=2)
        self.assertEqual(self.host.status, "candidate_requires_lead_review")
        self.assertEqual(route, "done")

    def test_topology_is_graph_parallel_recon_then_routed_cycle(self):
        api = genai.Client(api_key="fixture-not-a-real-key")
        root = build_workflow(self.host, api, lane("wizard_ux"), rounds=2)
        self.assertEqual(root.name, "meta_wizard_ux_workflow")
        self.assertEqual(root.max_concurrency, 2)
        edges = {(edge.from_node.name, edge.to_node.name, edge.route) for edge in root.graph.edges}
        self.assertIn(("__START__", "meta_api_researcher", None), edges)
        self.assertIn(("__START__", "meta_code_mapper", None), edges)
        self.assertIn(("meta_api_researcher", "reconnaissance_join", None), edges)
        self.assertIn(("meta_code_mapper", "reconnaissance_join", None), edges)
        self.assertIn(("route_after_critic", "meta_engineer", "revise"), edges)
        self.assertIn(("route_after_critic", "lane_terminal", "done"), edges)
        api.close()

    def test_sensitive_output_is_redacted(self):
        self.assertNotIn("person@example.com", safe("person@example.com"))
        self.assertNotIn("AIza" + "x" * 30, safe("AIza" + "x" * 30))

    def test_status_tolerates_partial_last_event(self):
        events = self.run_dir / "events.jsonl"
        events.write_text(json.dumps({
            "time": "2026-09-11T00:00:00+00:00", "event": "dispatch", "agent": "meta_engineer"
        }) + "\n{")
        result = lane_status(self.run_dir)
        self.assertEqual(result["calls_by_agent"], {"meta_engineer": 1})

    def test_orchestrator_keeps_virtualenv_launcher_path(self):
        launcher = self.root / "venv/bin/python"
        launcher.parent.mkdir(parents=True)
        launcher.symlink_to(Path("/usr/bin/python3"))
        self.assertEqual(runtime_launcher(launcher), launcher)
        self.assertNotEqual(runtime_launcher(launcher), launcher.resolve())


if __name__ == "__main__":
    unittest.main()
