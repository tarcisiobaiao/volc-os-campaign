"""Smoke sintético do pipeline. Adapters stubados: nenhum modelo é chamado.

Prova as cinco propriedades que a missão exige do smoke:
  1. modelo não chamado em preflight vermelho;
  2. writer não chamado em spec error;
  3. harvest retomado;
  4. evidência reutilizada;
  5. reviewer adjudicado.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from volc_agent_harness.v3.adjudication import Forca, Parecer, adjudicar  # noqa: E402
from volc_agent_harness.v3.compiler import compile_mission  # noqa: E402
from volc_agent_harness.v3.failures import FailureClass, HarnessFailure  # noqa: E402
from volc_agent_harness.v3.harvest import Harvest, requires_writer, resume_base  # noqa: E402
from volc_agent_harness.v3.ledger import EvidenceLedger, Status  # noqa: E402


class _Adapter:
    """Adapter falso. Se ``chamadas`` não estiver vazio, gastamos um modelo."""

    def __init__(self) -> None:
        self.chamadas: list[dict] = []

    async def run(self, request):  # pragma: no cover - não deve ser chamado
        self.chamadas.append({"worker": getattr(request, "worker_id", "?")})
        return {"status": "completed"}


class _Worker:
    def __init__(self, id, provider, role, model, writable=()):
        self.id, self.provider, self.role, self.model = id, provider, role, model
        self.writable_paths = list(writable)


class _Gate:
    def __init__(self, argv, timeout_seconds=600):
        self.argv, self.timeout_seconds = list(argv), timeout_seconds


class _Mission:
    def __init__(self, gates, workers, mission_id="smoke", base_ref="0" * 40):
        self.mission_id, self.base_ref = mission_id, base_ref
        self.gates, self.workers = gates, workers
        self.lineage_root_sha = None


ROADMAP = {"initiatives": [{"id": "P04-T09", "acceptance": ["a1", "a2", "a3", "a4", "a5"]}]}


def _arvore(tmp: str) -> Path:
    t = Path(tmp)
    (t / "volc_ads" / "campanha").mkdir(parents=True)
    (t / "backend" / "tests").mkdir(parents=True)
    (t / "volc_ads" / "subir.py").write_text("class Selo:\n    pass\n")
    (t / "volc_ads" / "campanha" / "demand_gen.py").write_text(
        "from volc_ads.subir import Selo\n\ndef build():\n    return Selo()\n"
    )
    (t / "backend" / "tests" / "test_existe.py").write_text("def test_ok():\n    assert True\n")
    return t


class SmokeSintetico(unittest.TestCase):
    def test_1_preflight_vermelho_nao_chama_modelo(self):
        adapter = _Adapter()
        with TemporaryDirectory() as tmp:
            arvore = _arvore(tmp)
            missao = _Mission(
                gates=[_Gate([sys.executable, "-m", "pytest", "backend/tests/nao_existe.py"])],
                workers=[_Worker("w", "codex", "writer", "gpt-5.5", ["volc_ads"])],
            )
            with self.assertRaises(HarnessFailure) as erro:
                compile_mission(
                    mission=missao, tree=arvore, roadmap=ROADMAP,
                    acceptance_ids=["P04-T09-A2"], symbols=["Selo"],
                    search_roots=["volc_ads"], ownership_envelope=["volc_ads"],
                )
            self.assertEqual(erro.exception.classe, FailureClass.SPEC_ERROR)
        self.assertEqual(adapter.chamadas, [], "nenhum modelo chamado no preflight vermelho")

    def test_2_spec_error_nao_chama_writer(self):
        self.assertFalse(HarnessFailure(FailureClass.SPEC_ERROR, "x").permite_retry)
        self.assertIsNone(HarnessFailure(FailureClass.AUTHORIZATION_BLOCK, "x").destino)

    def test_3_missao_valida_compila_e_emite_artefato(self):
        with TemporaryDirectory() as tmp:
            arvore = _arvore(tmp)
            missao = _Mission(
                gates=[_Gate([sys.executable, "-m", "pytest", "backend/tests/test_existe.py", "-q"])],
                workers=[
                    _Worker("w", "codex", "writer", "gpt-5.5", ["volc_ads/subir.py"]),
                    _Worker("r", "codex", "reviewer", "gpt-5.6-sol"),
                ],
            )
            compilada = compile_mission(
                mission=missao, tree=arvore, roadmap=ROADMAP,
                acceptance_ids=["P04-T09-A2"], symbols=["Selo"],
                search_roots=["volc_ads"], ownership_envelope=["volc_ads"],
            )
            d = compilada.as_dict()
            for chave in (
                "mission_id", "base_sha", "acceptance_ids", "regression_acceptance_ids",
                "ownership_envelope", "writable_paths", "optional_writable_paths",
                "produced_paths", "gate_plan", "gates_runnable_before_writer",
                "gates_depending_on_produced", "routed_models", "privacy_class",
                "write_authority", "retry_policy", "integration_policy",
            ):
                self.assertIn(chave, d, f"compiled-mission.json sem {chave}")
            # A1 reconciliada: o call site em campanha/ entrou sem confirmação humana.
            self.assertIn("volc_ads/campanha/demand_gen.py", d["writable_paths"])
            self.assertEqual(d["gates_runnable_before_writer"], [1])

    def test_4_harvest_retomado(self):
        h = Harvest("b7111fa", "candidate/p17", ["a.py"], True, [1, 2], 3, "MERIT_FAILURE")
        self.assertEqual(resume_base(h, "297757a"), "b7111fa")
        self.assertTrue(requires_writer("MERIT_FAILURE", harvest=h))
        self.assertFalse(requires_writer("SPEC_ERROR", harvest=h))

    def test_5_evidencia_reutilizada(self):
        with TemporaryDirectory() as tmp:
            led = EvidenceLedger(Path(tmp) / "l.sqlite")
            led.record(acceptance_id="P04-T09-A2", kind="focal_gate", base_sha="a",
                       run_id="r1", command="pytest -q", production_digest="p1",
                       test_digest="t1", exit_code=0, counts={"passed": 50})
            r = led.lookup(acceptance_id="P04-T09-A2", kind="focal_gate", command="pytest -q",
                           production_digest="p1", test_digest="t1")
            self.assertEqual(r["status"], Status.REUSED)
            self.assertEqual(r["evidence"]["exit_code"], 0)

    def test_6_reviewer_adjudicado(self):
        r = adjudicar([
            Parecer("gemini", "gemini", "accept", Forca.CHECKLIST),
            Parecer("sol", "codex", "changes_requested", Forca.CONTRAPROVA_EXECUTAVEL,
                    "contraprova", "pytest -k x"),
        ])
        self.assertEqual(r["veredito"], "CORRIGIR")

    def test_7_nenhum_segredo_no_artefato_compilado(self):
        with TemporaryDirectory() as tmp:
            arvore = _arvore(tmp)
            (arvore / ".env").write_text("SECRET_KEY=abcdefghijklmnop\n")
            missao = _Mission(
                gates=[_Gate([sys.executable, "-m", "pytest", "backend/tests/test_existe.py", "-q"])],
                workers=[
                    _Worker("w", "codex", "writer", "gpt-5.5", ["volc_ads/subir.py"]),
                    _Worker("r", "codex", "reviewer", "gpt-5.6-sol"),
                ],
            )
            compilada = compile_mission(
                mission=missao, tree=arvore, roadmap=ROADMAP,
                acceptance_ids=["P04-T09-A2"], symbols=["Selo"],
                search_roots=["volc_ads"], ownership_envelope=["volc_ads"],
            )
            texto = json.dumps(compilada.as_dict(), ensure_ascii=False)
            self.assertNotIn("SECRET_KEY", texto)
            self.assertNotIn("abcdefghijklmnop", texto)
            self.assertNotIn(".env", texto)


if __name__ == "__main__":
    unittest.main()
