"""Provas das duas guardas refutadas: G1 (gates tipados) e G5 (ledger honesto)."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from volc_agent_harness.v3.failures import FailureClass, HarnessFailure  # noqa: E402
from volc_agent_harness.v3.gate_runner import (  # noqa: E402
    GateRunner, LocalRunner, run_gate_with_ledger,
)
from volc_agent_harness.v3.gate_types import from_spec  # noqa: E402
from volc_agent_harness.v3.ledger import (  # noqa: E402
    EvidenceLedger, context_digest, env_fingerprint,
)

PY_PROJ = "/Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign/backend/.venv/bin/python"
TOOLCHAIN = {"python": PY_PROJ, "git": "/usr/bin/git"}


class G1GatesTipados(unittest.TestCase):
    """A refutação: `python -c "import os;os.remove(x)"` atravessava tudo."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.wt = Path(self.tmp.name)
        (self.wt / "backend" / "tests").mkdir(parents=True)
        (self.wt / "backend" / "tests" / "test_x.py").write_text(
            "def test_a():\n    assert True\n")
        subprocess.run(["git", "init", "-q", str(self.wt)], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_nao_existe_tipo_generico(self):
        with self.assertRaises(HarnessFailure) as e:
            from_spec(1, {"kind": "generic", "argv": ["python", "-c", "x"]})
        self.assertEqual(e.exception.classe, FailureClass.SPEC_ERROR)
        self.assertIn("genérico", e.exception.resumo)

    def test_missao_nao_escreve_o_argv(self):
        """O tipo constrói a linha; `-c` não tem onde entrar."""

        g = from_spec(1, {"kind": "pytest", "targets": ["backend/tests"]})
        argv = g.build(worktree=self.wt, toolchain=TOOLCHAIN)
        self.assertEqual(argv[:3], [PY_PROJ, "-m", "pytest"])
        self.assertNotIn("-c", argv)
        self.assertNotIn("-e", argv)

    def test_flag_fora_da_allowlist_recusada(self):
        for flag in ("-c", "--command", "-e", "--eval", "--exec"):
            with self.subTest(flag=flag):
                g = from_spec(1, {"kind": "pytest", "targets": ["backend/tests"],
                                  "flags": [flag]})
                with self.assertRaises(HarnessFailure) as e:
                    g.build(worktree=self.wt, toolchain=TOOLCHAIN)
                self.assertEqual(e.exception.classe, FailureClass.AUTHORIZATION_BLOCK)

    def test_caminho_absoluto_e_travessia_recusados(self):
        for alvo in ("/etc/passwd", "../fora", "backend/../../fora"):
            with self.subTest(alvo=alvo):
                g = from_spec(1, {"kind": "pytest", "targets": [alvo]})
                with self.assertRaises(HarnessFailure) as e:
                    g.build(worktree=self.wt, toolchain=TOOLCHAIN)
                self.assertEqual(e.exception.classe, FailureClass.AUTHORIZATION_BLOCK)

    def test_git_diff_check_nao_tem_como_declarar_clean_ou_reset(self):
        g = from_spec(1, {"kind": "git_diff_check"})
        argv = g.build(worktree=self.wt, toolchain=TOOLCHAIN)
        self.assertEqual(argv[1:], ["diff", "--check"])
        for perigoso in ("clean", "reset", "checkout"):
            self.assertNotIn(perigoso, argv)

    def test_npm_script_exige_script_declarado(self):
        (self.wt / "package.json").write_text(json.dumps({"scripts": {"build": "vite build"}}))
        ok = from_spec(1, {"kind": "npm_script", "script": "build"})
        self.assertEqual(ok.build(worktree=self.wt, toolchain={"npm": "/usr/bin/env"})[-2:],
                         ["run", "build"])
        ruim = from_spec(1, {"kind": "npm_script", "script": "inexistente"})
        with self.assertRaises(HarnessFailure) as e:
            ruim.build(worktree=self.wt, toolchain={"npm": "/usr/bin/env"})
        self.assertEqual(e.exception.classe, FailureClass.SPEC_ERROR)

    def test_npm_script_leva_digest_do_lockfile_para_a_evidencia(self):
        (self.wt / "package.json").write_text(json.dumps({"scripts": {"build": "x"}}))
        (self.wt / "package-lock.json").write_text('{"lockfileVersion":3}')
        g = from_spec(1, {"kind": "npm_script", "script": "build"})
        inputs = g.evidence_inputs(worktree=self.wt)
        self.assertIn("package.json", inputs)
        self.assertIn("package-lock.json", inputs)

    def test_tracked_script_exige_rastreado(self):
        (self.wt / "scripts").mkdir()
        (self.wt / "scripts" / "solto.py").write_text("print(1)\n")
        g = from_spec(1, {"kind": "tracked_script", "script_path": "scripts/solto.py"})
        with self.assertRaises(HarnessFailure) as e:
            g.build(worktree=self.wt, toolchain=TOOLCHAIN)
        self.assertEqual(e.exception.classe, FailureClass.AUTHORIZATION_BLOCK)

    def test_runner_nao_afirma_conter_filesystem(self):
        """Honestidade do contrato: o local não sandboxa."""

        self.assertFalse(LocalRunner.contains_filesystem)
        self.assertIn("execute", GateRunner.__abstractmethods__)


class _RunnerContador(GateRunner):
    contains_filesystem = False
    name = "contador"

    def __init__(self, exit_code: int = 0):
        self.execucoes: list[list[str]] = []
        self.exit_code = exit_code

    def execute(self, *, argv, cwd, env, timeout):
        self.execucoes.append(list(argv))
        return self.exit_code, "saida", ""


class G5LedgerHonesto(unittest.TestCase):
    """A refutação: lookup depois de executar é etiqueta falsa."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.wt = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.wt)], check=True)
        self.led = EvidenceLedger(self.wt / "led.sqlite")
        self.ctx = context_digest(acceptance_text="a1", base_sha="s",
                                  candidate_sha=None, lineage_root=None)
        self.fp = env_fingerprint({"PATH": "/a"})

    def tearDown(self):
        self.tmp.cleanup()

    def _rodar(self, runner, prod="p1"):
        return run_gate_with_ledger(
            gate_index=1, argv=["echo", "ok"], worktree=self.wt, env={}, timeout=30,
            ledger=self.led, acceptance_id="P10-T17-A1", base_sha="s",
            candidate_sha=None, context_digest=self.ctx, env_fingerprint=self.fp,
            production_digest=prod, test_digest="t1", run_id="r1", worker_id="wr",
            runner=runner,
        )

    def test_A_primeira_execucao_verde(self):
        r = _RunnerContador()
        out = self._rodar(r)
        self.assertEqual(len(r.execucoes), 1)
        self.assertEqual(out.execution_mode, "executed")
        self.assertEqual(out.status, "green")
        self.assertIsNotNone(out.evidence_id)

    def test_B_mesmos_inputs_reutiliza_sem_executar(self):
        r = _RunnerContador()
        self._rodar(r)
        out = self._rodar(r)
        self.assertEqual(len(r.execucoes), 1, "o segundo gate NÃO pode rodar")
        self.assertEqual(out.execution_mode, "reused")
        self.assertIsNotNone(out.source_evidence_id)

    def test_C_dimensao_material_muda_executa_de_novo(self):
        r = _RunnerContador()
        self._rodar(r, prod="p1")
        out = self._rodar(r, prod="p2")
        self.assertEqual(len(r.execucoes), 2)
        self.assertEqual(out.execution_mode, "executed")

    def test_D_gate_vermelho_e_gravado_antes_de_qualquer_raise(self):
        r = _RunnerContador(exit_code=1)
        out = self._rodar(r)
        self.assertEqual(out.status, "red")
        self.assertIsNotNone(out.evidence_id, "vermelho precisa estar no ledger")

    def test_E_vermelho_nunca_e_reutilizado_como_verde(self):
        vermelho = _RunnerContador(exit_code=1)
        self._rodar(vermelho)
        verde = _RunnerContador(exit_code=0)
        out = self._rodar(verde)
        self.assertEqual(out.execution_mode, "executed",
                         "prova vermelha não pode virar reuso verde")
        self.assertEqual(len(verde.execucoes), 1)

    def test_ordem_e_lookup_antes_de_executar(self):
        """Prova estrutural: no código, lookup vem antes de runner.execute."""

        import inspect
        from volc_agent_harness.v3 import gate_runner

        fonte = inspect.getsource(gate_runner.run_gate_with_ledger)
        self.assertLess(fonte.index("ledger.lookup("), fonte.index("runner.execute("))
        self.assertLess(fonte.index("runner.execute("), fonte.index("ledger.record("))

    def test_timeout_vira_status_proprio_e_e_registrado(self):
        class _Timeout(GateRunner):
            name = "timeout"

            def execute(self, *, argv, cwd, env, timeout):
                raise subprocess.TimeoutExpired(argv, timeout)

        out = self._rodar(_Timeout())
        self.assertEqual(out.status, "timeout")
        self.assertIsNotNone(out.evidence_id)


if __name__ == "__main__":
    unittest.main()
