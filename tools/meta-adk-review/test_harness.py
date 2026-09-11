from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from google import genai

from config import LANES, MODEL, THINKING, lane
from host import Host, digest, safe
from orchestrate import runtime_launcher
from status import lane_status
from workflow import build_workflow
from tasks import TICKETS, Ticket, preload
from ticket_workflow import apply_proposal, build_ticket_workflow


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

    def test_after_tool_callback_uses_adk_2_keyword_contract(self):
        parameters = inspect.signature(Host.after_tool).parameters
        self.assertIn("tool_response", parameters)
        self.assertNotIn("response", parameters)

    def test_repeated_tool_and_premature_engineer_diff_are_refused(self):
        context = SimpleNamespace(agent_name="meta_engineer")
        gate = SimpleNamespace(name="run_gate")
        first = self.host.before_tool(gate, {"gate": "diff", "target": ""}, context)
        self.assertIn("error", first)
        repeated = self.host.before_tool(gate, {"gate": "diff", "target": ""}, context)
        self.assertIn("identical", repeated["error"])

    def test_mapper_final_call_is_forced_tool_free(self):
        request = MagicMock()
        request.config.tools = ["tool"]
        request.config.tool_config = "config"
        request.contents = []
        self.host.role_calls["meta_code_mapper"] = self.host.role_limits["meta_code_mapper"] - 1
        self.host.before_model(MagicMock(agent_name="meta_code_mapper"), request)
        self.assertEqual(request.config.tools, [])
        self.assertIsNone(request.config.tool_config)
        self.assertIn("highest-confidence defect", request.contents[-1].parts[0].text)

    def test_same_test_is_allowed_again_after_edit(self):
        context = SimpleNamespace(agent_name='meta_engineer')
        tool = SimpleNamespace(name='run_gate')
        args = {'gate': 'backend', 'target': str(self.test.relative_to(self.root))}
        self.assertIsNone(self.host.before_tool(tool, args, context))
        self.assertIn('error', self.host.before_tool(tool, args, context))
        relative = str(self.source.relative_to(self.root))
        read = self.host.read_file(relative)
        self.host.replace_text(relative, read['sha256'], 'value = 1', 'value = 2')
        self.assertIsNone(self.host.before_tool(tool, args, context))

    def test_created_test_can_be_read_patched_and_exported(self):
        path = 'backend/tests/test_meta_draft_created.py'
        self.host.create_test_file(path, 'def test_created():\n    assert True\n')
        read = self.host.read_file(path)
        self.assertNotIn('error', read)
        result = self.host.replace_text(path, read['sha256'], 'assert True', 'assert 1 == 1')
        self.assertTrue(result['ok'])
        self.assertIn('assert 1 == 1', self.host.show_diff()['diff'])
        self.host.finish()
        self.assertIn('test_meta_draft_created.py', (self.run_dir / 'candidate.diff').read_text())

    def test_focused_ticket_seeds_source_hash_without_paid_mapper(self):
        path = str(self.source.relative_to(self.root))
        test = str(self.test.relative_to(self.root))
        ticket = Ticket('fixture', 'wizard_ux', 'Fix fixture', 'value is 1', ('value is 2',),
                        ((path, 1, 10),), (path, test), test, 'official docs')
        api = genai.Client(api_key='fixture-not-a-real-key')
        root = build_workflow(self.host, api, ticket.scoped_lane(), 2, ticket)
        edges = {(e.from_node.name, e.to_node.name) for e in root.graph.edges}
        self.assertIn(('__START__', 'curated_code_map'), edges)
        self.assertNotIn(('__START__', 'meta_code_mapper'), edges)
        self.assertEqual(self.host.read_hashes[path], digest(self.source.read_text()))
        api.close()

    def test_tickets_do_not_overlap_writes(self):
        writes = [set(t.writes) for t in TICKETS.values()]
        for i, paths in enumerate(writes):
            for other in writes[i + 1:]:
                self.assertFalse(paths & other)

    def test_structured_proposal_executes_multiple_edits_with_initial_sha(self):
        path = str(self.source.relative_to(self.root))
        sha = digest(self.source.read_text())
        result = apply_proposal(self.host, json.dumps({'summary': 'fix', 'blocked_reason': '', 'edits': [
            {'path': path, 'sha256': sha, 'old': 'value = 1', 'new': 'value = 2'},
            {'path': path, 'sha256': sha, 'old': 'value = 2', 'new': 'value = 3'},
        ]}))
        self.assertEqual(result['applied'], 2)
        self.assertEqual(self.source.read_text(), 'value = 3\n')

    def test_structured_proposal_checks_all_anchors_before_first_edit(self):
        path = str(self.source.relative_to(self.root))
        sha = digest(self.source.read_text())
        result = apply_proposal(self.host, json.dumps({'summary': 'fix', 'blocked_reason': '', 'edits': [
            {'path': path, 'sha256': sha, 'old': 'value = 1', 'new': 'value = 2'},
            {'path': path, 'sha256': sha, 'old': 'missing anchor', 'new': 'value = 3'},
        ]}))
        self.assertIn('error', result)
        self.assertEqual(self.source.read_text(), 'value = 1\n')

    def test_structured_report_without_patch_is_not_implementation(self):
        result = apply_proposal(self.host, json.dumps({'summary': 'recommend changes', 'blocked_reason': '', 'edits': []}))
        self.assertIn('error', result)
        self.assertEqual(self.host.edits, 0)

    def test_real_adk_state_handoff_applies_patch_and_routes_to_candidate(self):
        from google.adk.models.base_llm import BaseLlm
        from google.adk.models.llm_response import LlmResponse
        from google.adk.runners import InMemoryRunner
        from google.genai import types

        path = str(self.source.relative_to(self.root))
        target = str(self.test.relative_to(self.root))
        ticket = Ticket('fixture', 'wizard_ux', 'Fixture change', 'value=1', ('value=2',),
                        ((path, 1, 10),), (path, target), target, 'official docs')
        responses = iter([
            'Official documentation supports the fixture.',
            json.dumps({'summary': 'change fixture', 'blocked_reason': '', 'edits': [
                {'path': path, 'sha256': digest(self.source.read_text()), 'old': 'value = 1', 'new': 'value = 2'}]}),
            json.dumps({'verdict': 'candidate', 'findings': [], 'coverage': ['value=2'], 'remaining': [], 'summary': 'ok'}),
        ])

        class FixtureModel(BaseLlm):
            model: str = MODEL

            async def generate_content_async(self, llm_request, stream=False):
                yield LlmResponse(model_version=MODEL,
                    content=types.Content(role='model', parts=[types.Part(text=next(responses))]),
                    usage_metadata=types.GenerateContentResponseUsageMetadata(total_token_count=10),
                    grounding_metadata=types.GroundingMetadata(web_search_queries=['fixture'], grounding_chunks=[
                        types.GroundingChunk(web=types.GroundingChunkWeb(uri='https://react.dev', title='React'))]))

        async def fixture_gate(gate, target=''):
            result = {'gate': gate, 'target': target, 'returncode': 0, 'edits': self.host.edits}
            self.host.gates[gate + ':' + target] = result
            return result

        async def exercise():
            with patch('ticket_workflow.Gemini', return_value=FixtureModel()), patch.object(self.host, 'run_gate', fixture_gate):
                workflow = build_ticket_workflow(self.host, None, ticket, 2)
                runner = InMemoryRunner(node=workflow, app_name='fixture')
                try:
                    await runner.run_debug('Execute fixture', quiet=True)
                finally:
                    await runner.close()

        asyncio.run(exercise())
        self.assertEqual(self.source.read_text(), 'value = 2\n')
        self.assertEqual(self.host.calls, 3)
        self.assertEqual(self.host.status, 'candidate_requires_lead_review')

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
