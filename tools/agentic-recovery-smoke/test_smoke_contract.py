import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools/agentic-recovery-smoke/run.py"
SPEC = importlib.util.spec_from_file_location("agentic_recovery_smoke", MODULE_PATH)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = smoke
SPEC.loader.exec_module(smoke)


class SmokeContractTest(unittest.TestCase):
    def test_preflight_local_is_safe(self):
        status = smoke.preflight()
        self.assertTrue(status["ok"], status["errors"])
        self.assertNotIn("DEEPSEEK_API_KEY", json.dumps(status))

    def test_scenarios_exist(self):
        contract = smoke._load_contract()
        ids = {item["id"] for item in contract["scenarios"]}
        self.assertEqual(
            ids,
            {"redator-invalid-json-loop", "search-low-delivery-readonly"},
        )

    def test_output_rejects_external_write(self):
        with self.assertRaises(Exception):
            smoke.RecoveryResult(
                verdict="repaired",
                summary="ok",
                evidence_ids=[],
                missing_information=[],
                proposed_recipe=None,
                external_writes=1,
                confidence=1,
            )

    def test_structured_result_accepts_json_after_reasoning(self):
        result = smoke._structured_result(
            "Análise interna.\n```json\n"
            '{"verdict":"recommendation","summary":"troca local",'
            '"evidence_ids":[],"missing_information":[],'
            '"proposed_recipe":"substituir apenas o trecho",'
            '"external_writes":0,"confidence":0.8}'
            "\n```"
        )
        self.assertEqual(result.verdict, "recommendation")

    def test_structured_result_rejects_prose_without_json(self):
        with self.assertRaises(RuntimeError):
            smoke._structured_result("parece resolvido")


if __name__ == "__main__":
    unittest.main()
