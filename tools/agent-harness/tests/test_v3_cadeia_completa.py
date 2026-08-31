"""Cadeia completa pelo entrypoint oficial, com adapter fake determinístico.

Prova as duas cadeias que importam:
  * positiva — compila, cria worktree, chama o writer UMA vez, produz arquivo
    permitido, passa pelo postwriter, roda gate verde, adjudica e colhe;
  * de falha — gate vermelho gera failure.json e NENHUM harvest falso.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

CHAMADAS: list[str] = []

#: Missão real aponta o gate para o interpretador do projeto, que tem pytest.
#: `sys.executable` aqui é o Python do harness, que não tem — usar ele faria o
#: teste medir a ausência de pytest em vez do pipeline.
PYTEST_PY = "/Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign/backend/.venv/bin/python"


class _FakeAdapter:
    """Determinístico: escreve o arquivo declarado e devolve resultado válido."""

    def __init__(self, provider: str, papel: str, escrever: tuple[str, str] | None):
        self.provider, self.papel, self.escrever = provider, papel, escrever

    async def run(self, request):
        CHAMADAS.append(f"{self.provider}:{request.worker_id}")
        if self.escrever is not None:
            alvo = Path(request.worktree) / self.escrever[0]
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_text(self.escrever[1], encoding="utf-8")
        if self.papel == "writer":
            return {
                "status": "completed",
                "summary": "escreveu o arquivo declarado",
                "changed_paths": [self.escrever[0]] if self.escrever else [],
                "curation_handoff": {"task_ids": ["P10-T17"], "state": "partial",
                                     "proofs": [], "gaps": []},
            }
        return {"status": "completed", "verdict": "accept",
                "summary": "sem objeção", "confirmed_findings": []}


def _repo(tmp: str) -> tuple[Path, str]:
    r = Path(tmp)
    (r / "backend" / "tests").mkdir(parents=True)
    (r / "volc-os-workbook").mkdir()
    (r / "backend" / "tests" / "test_base.py").write_text(
        "def test_verde():\n    assert True\n")
    (r / "volc-os-workbook" / "ROADMAP-VIVO.json").write_text(json.dumps(
        {"initiatives": [{"id": "P10-T17", "acceptance": ["a1", "a2"]}]}))
    # O harness roda o scanner de segredo antes de commitar o candidato. Um repo
    # sintético precisa ter o script, como o repo real tem.
    (r / "scripts").mkdir()
    (r / "scripts" / "verificar_segredos.py").write_text(
        "import sys\nsys.exit(0)\n")
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    subprocess.run(["git", "-C", str(r), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-q", "-m", "base"], check=True, capture_output=True)
    base = subprocess.run(["git", "-C", str(r), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    return r, base


def _missao(repo: Path, base: str, gates) -> Path:
    m = {
        "mission_schema_version": 3,
        "mission_id": "cadeia-completa", "title": "cadeia", "base_ref": base,
        "briefing": "b", "mode": "implementation", "commit_message": "feat: cadeia",
        "acceptance_ids": ["P10-T17-A1"], "ownership_envelope": ["backend"],
        "task_ids": ["P10-T17"], "authorized_external_providers": [],
        "produced_paths": [{"path": "backend/tests/test_novo.py", "required": True}],
        "gates": gates,
        "workers": [
            {"id": "wr", "provider": "codex", "role": "writer", "model": "gpt-5.5",
             "lens": "x", "allowed_paths": ["backend"], "writable_paths": ["backend/tests"]},
            {"id": "rv", "provider": "codex", "role": "reviewer", "model": "gpt-5.6-sol",
             "lens": "y", "allowed_paths": ["backend"]},
        ],
    }
    p = repo / "m.json"
    p.write_text(json.dumps(m))
    return p


ARQUIVO_NOVO = ("backend/tests/test_novo.py", "def test_produzido():\n    assert True\n")

ARTEFATOS_ESPERADOS = (
    "compiled-mission.json", "gate-plan.json", "ownership-proposal.json",
    "baseline.json", "postwriter-report.json", "evidence.json",
    "adjudication.json", "harvest.json",
)


def _adapter_para(provider):
    papel = "writer" if _adapter_para.proximo == "writer" else "reviewer"
    escrever = ARQUIVO_NOVO if papel == "writer" else None
    _adapter_para.proximo = "reviewer"
    return _FakeAdapter(provider, papel, escrever)


class CadeiaPositiva(unittest.TestCase):
    def setUp(self) -> None:
        CHAMADAS.clear()
        _adapter_para.proximo = "writer"

    def test_cadeia_completa_verde(self):
        from volc_agent_harness.cli import main as cli_main

        with TemporaryDirectory() as tmp:
            repo, base = _repo(tmp)
            missao = _missao(repo, base, [
                {"argv": [PYTEST_PY, "-m", "pytest",
                          "backend/tests/test_novo.py", "-q",
                          "-p", "no:cacheprovider"]},
            ])
            with mock.patch("volc_agent_harness.mission.adapter_for", _adapter_para):
                codigo = cli_main(["--mission", str(missao), "--repo", str(repo)])

            run_dirs = sorted((repo / "tools" / "agent-harness" / "runs").iterdir())
            self.assertTrue(run_dirs, "o runtime precisa criar o diretório do run")
            run_dir = run_dirs[-1]

            faltando = [a for a in ARTEFATOS_ESPERADOS if not (run_dir / a).is_file()]
            self.assertEqual(faltando, [], f"artefatos ausentes: {faltando}")
            self.assertFalse((run_dir / "failure.json").exists(),
                             "cadeia verde não produz failure.json")

            writers = [c for c in CHAMADAS if c.endswith(":wr")]
            self.assertEqual(len(writers), 1, "o writer é chamado exatamente uma vez")

            compilada = json.loads((run_dir / "compiled-mission.json").read_text())
            self.assertEqual(compilada["acceptance_ids"], ["P10-T17-A1"])
            self.assertEqual(compilada["writable_paths"], ["backend/tests"])

            pos = json.loads((run_dir / "postwriter-report.json").read_text())
            self.assertEqual(pos["produced_present"], ["backend/tests/test_novo.py"])
            self.assertEqual(pos["outside_ownership"], [])

            colheita = json.loads((run_dir / "harvest.json").read_text())
            self.assertTrue(colheita["ownership_respected"])
            self.assertIn("backend/tests/test_novo.py", colheita["files"])
            self.assertIsNone(colheita["red_gate"])
            self.assertEqual(len(colheita["sha"]), 40)

            adj = json.loads((run_dir / "adjudication.json").read_text())
            self.assertIn(adj["veredito"], {"ACEITAR", "CORRIGIR", "BLOQUEADO"})

            resultado = json.loads((run_dir / "mission-result.json").read_text())
            self.assertTrue(resultado["ok"])
            self.assertEqual(codigo, 0)


class CadeiaDeFalha(unittest.TestCase):
    def setUp(self) -> None:
        CHAMADAS.clear()
        _adapter_para.proximo = "writer"

    def test_gate_vermelho_produz_failure_sem_harvest_falso(self):
        from volc_agent_harness.cli import main as cli_main

        with TemporaryDirectory() as tmp:
            repo, base = _repo(tmp)
            # O produced nasce, mas um segundo gate reprova de verdade.
            (repo / "backend" / "tests" / "test_vermelho.py").write_text(
                "def test_reprova():\n    assert False\n")
            subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
                            "-c", "user.email=t@t", "commit", "-q", "-m", "vermelho"],
                           check=True, capture_output=True)
            base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                  capture_output=True, text=True, check=True).stdout.strip()
            missao = _missao(repo, base, [
                {"argv": [PYTEST_PY, "-m", "pytest",
                          "backend/tests/test_novo.py", "-q",
                          "-p", "no:cacheprovider"]},
                {"argv": [PYTEST_PY, "-m", "pytest",
                          "backend/tests/test_vermelho.py", "-q",
                          "-p", "no:cacheprovider"]},
            ])
            with mock.patch("volc_agent_harness.mission.adapter_for", _adapter_para):
                codigo = cli_main(["--mission", str(missao), "--repo", str(repo)])

            run_dir = sorted((repo / "tools" / "agent-harness" / "runs").iterdir())[-1]
            self.assertTrue((run_dir / "failure.json").is_file())
            self.assertFalse((run_dir / "harvest.json").exists(),
                             "gate vermelho não pode produzir harvest")
            falha = json.loads((run_dir / "failure.json").read_text())
            self.assertIn(falha["classe"], {"BASELINE_ERROR", "MERIT_FAILURE"})
            self.assertIn(falha["destino"] or "", {"baseline_reconciliation",
                                                   "writer_or_harvest"})
            self.assertNotEqual(codigo, 0)


if __name__ == "__main__":
    unittest.main()
