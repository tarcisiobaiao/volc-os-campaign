import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "tools/agentic-recovery-smoke/sniper.py"
SPEC = importlib.util.spec_from_file_location("volc_sniper", PATH)
assert SPEC and SPEC.loader
sniper = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sniper
SPEC.loader.exec_module(sniper)


class SniperGuardTest(unittest.TestCase):
    def patch(self, scenario, replacement):
        return sniper.SniperPatch(
            scenario_id=scenario.id,
            target_id=scenario.target_id,
            observed_text=scenario.target,
            replacement=replacement,
            reason="reparo mínimo",
            confidence=0.9,
            external_writes=0,
        )

    def test_copy_changes_only_target_span(self):
        scenario = sniper.SCENARIOS["copy-flag-sniper"]
        repaired, errors = sniper._apply_guarded(
            scenario, self.patch(scenario, "disponível")
        )
        self.assertEqual(errors, [])
        self.assertEqual(
            repaired, "Receba seu benefício disponível agora com segurança."
        )

    def test_code_identifier_is_allowlisted_and_runs(self):
        scenario = sniper.SCENARIOS["python-variable-sniper"]
        repaired, errors = sniper._apply_guarded(
            scenario, self.patch(scenario, "orcamento_diario")
        )
        self.assertEqual(errors, [])
        self.assertIn("return orcamento_diario * dias", repaired)

    def test_code_rejects_arbitrary_payload(self):
        scenario = sniper.SCENARIOS["python-variable-sniper"]
        repaired, errors = sniper._apply_guarded(
            scenario, self.patch(scenario, "__import__('os').system('id')")
        )
        self.assertEqual(repaired, scenario.original)
        self.assertIn("identifier fora da allowlist", errors)


if __name__ == "__main__":
    unittest.main()
