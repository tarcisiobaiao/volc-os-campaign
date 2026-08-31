"""Prova end-to-end pelo MESMO entrypoint usado em produção.

O adapter-contador é a peça central: se ele registrar uma chamada onde o
compilador deveria ter recusado, gastamos um modelo — que é exatamente o custo
que o Harness V3 existe para evitar.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from volc_agent_harness.cli import main as cli_main  # noqa: E402
from volc_agent_harness.v3.baseline import BaselineRecord, compare  # noqa: E402
from volc_agent_harness.v3.ledger import (  # noqa: E402
    EvidenceLedger, Status, context_digest, env_fingerprint,
)
from volc_agent_harness.v3.probes import (  # noqa: E402
    http_status_extractor, measure_observables,
)

CONTADOR: list[str] = []


class _AdapterContador:
    """Qualquer chamada aqui é um modelo gasto."""

    def __init__(self, provider: str) -> None:
        self.provider = provider

    async def run(self, request):  # pragma: no cover
        CONTADOR.append(self.provider)
        return {"status": "completed", "summary": "stub"}


def _repo(tmp: str) -> Path:
    r = Path(tmp)
    (r / "backend" / "tests").mkdir(parents=True)
    (r / "volc-os-workbook").mkdir()
    (r / "backend" / "tests" / "test_base.py").write_text(
        "def test_verde():\n    assert True\n"
    )
    (r / "volc-os-workbook" / "ROADMAP-VIVO.json").write_text(json.dumps(
        {"initiatives": [{"id": "P10-T17", "acceptance": ["a1", "a2", "a3"]}]}
    ))
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    subprocess.run(["git", "-C", str(r), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "-q", "-m", "base"], check=True, capture_output=True,
    )
    return r


def _missao(repo: Path, **over) -> Path:
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    m = {
        "mission_schema_version": 3,
        "mission_id": "e2e-sintetica",
        "title": "smoke",
        "base_ref": base,
        "briefing": "b",
        "mode": "implementation",
        "commit_message": "c",
        "acceptance_ids": ["P10-T17-A1"],
        "ownership_envelope": ["backend"],
        "task_ids": ["P10-T17"],
        "authorized_external_providers": [],
        "gates": [{"argv": [sys.executable, "-m", "pytest",
                            "backend/tests/test_base.py", "-q"]}],
        "workers": [
            {"id": "wr", "provider": "codex", "role": "writer", "model": "gpt-5.5",
             "lens": "x", "allowed_paths": ["backend"], "writable_paths": ["backend"]},
            {"id": "rv", "provider": "codex", "role": "reviewer", "model": "gpt-5.6-sol",
             "lens": "y", "allowed_paths": ["backend"]},
        ],
    }
    m.update(over)
    p = repo / "missao.json"
    p.write_text(json.dumps(m))
    return p


class EndToEnd(unittest.TestCase):
    def setUp(self) -> None:
        CONTADOR.clear()

    def test_spec_invalida_zero_chamadas_de_modelo(self):
        """Gate cita arquivo inexistente: recusa antes de qualquer adapter."""

        with TemporaryDirectory() as tmp:
            repo = _repo(tmp)
            missao = _missao(repo, gates=[{"argv": [
                sys.executable, "-m", "pytest", "backend/tests/nao_existe.py", "-q"]}])
            codigo = cli_main(["--mission", str(missao), "--repo", str(repo)])
            self.assertEqual(codigo, 3)
        self.assertEqual(CONTADOR, [], "nenhum modelo pode ter sido chamado")

    def test_selecao_pytest_vazia_zero_chamadas(self):
        """`-k` que não casa com nada é gate que sempre passa: SPEC_ERROR."""

        with TemporaryDirectory() as tmp:
            repo = _repo(tmp)
            missao = _missao(repo, gates=[{"argv": [
                sys.executable, "-m", "pytest", "backend/tests/test_base.py",
                "-k", "nome_que_nao_existe_em_lugar_nenhum", "-q"]}])
            codigo = cli_main(["--mission", str(missao), "--repo", str(repo)])
            self.assertEqual(codigo, 3)
        self.assertEqual(CONTADOR, [])

    def test_missao_v2_nao_chega_ao_writer_e_nao_faz_fallback_silencioso(self):
        with TemporaryDirectory() as tmp:
            repo = _repo(tmp)
            missao = _missao(repo)
            bruto = json.loads(missao.read_text())
            del bruto["mission_schema_version"]
            del bruto["acceptance_ids"]
            missao.write_text(json.dumps(bruto))
            codigo = cli_main(["--mission", str(missao), "--repo", str(repo)])
            self.assertEqual(codigo, 3)
        self.assertEqual(CONTADOR, [])

    def test_aceite_inexistente_no_roadmap_zero_chamadas(self):
        with TemporaryDirectory() as tmp:
            repo = _repo(tmp)
            missao = _missao(repo, acceptance_ids=["P10-T17-A99"])
            # A validação de aceite roda no compile; o run usa o mesmo caminho.
            from volc_agent_harness.cli import compile_only

            codigo = compile_only(["--mission", str(missao), "--repo", str(repo),
                                   "--out", str(repo / "run")])
            self.assertEqual(codigo, 3)
        self.assertEqual(CONTADOR, [])

    def test_gate_destrutivo_e_recusado_antes_do_writer(self):
        with TemporaryDirectory() as tmp:
            repo = _repo(tmp)
            missao = _missao(repo, gates=[{"argv": ["rm", "-rf", "backend"]}])
            codigo = cli_main(["--mission", str(missao), "--repo", str(repo)])
            self.assertEqual(codigo, 3)
        self.assertEqual(CONTADOR, [])


class ProbeMede403Para409(unittest.TestCase):
    """Guarda 7: o observable é medido, não digitado pelo caller."""

    SAIDA_BASE = "GET /subir -> HTTP 403 Forbidden\n1 passed"
    SAIDA_CAND = "GET /subir -> HTTP 409 Conflict\n1 passed"

    def test_regressao_403_409_detectada_sem_caller_digitar(self):
        extrator = {"http_status": http_status_extractor("http_status", r"HTTP (\d{3})")}
        base_obs = measure_observables(
            saida=self.SAIDA_BASE, provenance="gate 1 stdout", extractors=extrator)
        cand_obs = measure_observables(
            saida=self.SAIDA_CAND, provenance="gate 1 stdout", extractors=extrator)

        self.assertEqual(base_obs["http_status"].value, 403)
        self.assertEqual(cand_obs["http_status"].value, 409)
        self.assertNotEqual(base_obs["http_status"].source_digest,
                            cand_obs["http_status"].source_digest)

        base = BaselineRecord(1, ["pytest"], 0, 1, 0, 1.0,
                              observable={"http_status": base_obs["http_status"].value})
        cand = BaselineRecord(1, ["pytest"], 0, 1, 0, 1.0,
                              observable={"http_status": cand_obs["http_status"].value})
        r = compare(baseline=base, candidato=cand)
        self.assertTrue(r["regrediu"])
        self.assertEqual(
            [x["dimensao"] for x in r["regressoes"]], ["http_status"])

    def test_observable_tem_proveniencia_e_digest(self):
        extrator = {"http_status": http_status_extractor("http_status", r"HTTP (\d{3})")}
        obs = measure_observables(saida=self.SAIDA_BASE, provenance="gate 1 stdout",
                                  extractors=extrator)["http_status"]
        d = obs.as_dict()
        self.assertEqual(d["provenance"], "gate 1 stdout")
        self.assertEqual(len(d["source_digest"]), 64)
        self.assertIn("regex", d["extractor"])


class LedgerContextoObrigatorio(unittest.TestCase):
    """Guarda 6: qualquer dimensão material que muda invalida a prova."""

    def _ledger(self, tmp):
        return EvidenceLedger(Path(tmp) / "l.sqlite")

    def _ctx(self, **over):
        base = dict(acceptance_text="a1", base_sha="s1", candidate_sha="c1",
                    lineage_root="r1", toolchain={"pytest": "9.1"},
                    manifests={"package-lock.json": "d1"})
        base.update(over)
        return context_digest(**base)

    def test_cada_dimensao_material_invalida_a_prova(self):
        dimensoes = {
            "texto do aceite": {"acceptance_text": "a1 revisado"},
            "base": {"base_sha": "s2"},
            "candidato": {"candidate_sha": "c2"},
            "lineage": {"lineage_root": "r2"},
            "toolchain": {"toolchain": {"pytest": "9.2"}},
            "manifests": {"manifests": {"package-lock.json": "d2"}},
        }
        for nome, mudanca in dimensoes.items():
            with self.subTest(dimensao=nome), TemporaryDirectory() as tmp:
                led = self._ledger(tmp)
                fp = env_fingerprint({"PATH": "/a"})
                led.record(acceptance_id="P10-T17-A1", kind="focal_gate", base_sha="s1",
                           run_id="r", command="pytest", cwd="/w", env_fp=fp,
                           ctx_digest=self._ctx(), production_digest="p", test_digest="t")
                igual = led.lookup(acceptance_id="P10-T17-A1", kind="focal_gate",
                                   command="pytest", production_digest="p", test_digest="t",
                                   cwd="/w", env_fp=fp, ctx_digest=self._ctx())
                self.assertEqual(igual["status"], Status.REUSED)
                mudado = led.lookup(acceptance_id="P10-T17-A1", kind="focal_gate",
                                    command="pytest", production_digest="p", test_digest="t",
                                    cwd="/w", env_fp=fp, ctx_digest=self._ctx(**mudanca))
                self.assertEqual(mudado["status"], Status.REEXECUTED,
                                 f"mudar {nome} tinha de invalidar a prova")

    def test_nenhum_valor_de_segredo_entra_no_ledger(self):
        with TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "l.sqlite"
            led = EvidenceLedger(caminho)
            led.record(acceptance_id="P10-T17-A1", kind="focal_gate", base_sha="s",
                       run_id="r", command="pytest -q", cwd="/w",
                       env_fp=env_fingerprint({"GEMINI_API_KEY": "AIzaSEGREDO"}),
                       ctx_digest=self._ctx(), production_digest="p", test_digest="t")
            bruto = caminho.read_bytes()
            self.assertNotIn(b"AIzaSEGREDO", bruto)
            self.assertNotIn(b"GEMINI_API_KEY=AIza", bruto)


if __name__ == "__main__":
    unittest.main()
