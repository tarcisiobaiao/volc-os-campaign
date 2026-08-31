"""Contraprovas do encerramento em supervised_local — F1–F4 e capacidades.

Autoridade: docs/architecture/HARNESS-V3-SUPERVISED-CLOSURE-SPEC.json.

Cada teste afirma o comportamento exigido pela SPEC e falha contra `da3cfe1`.
Os quatro defeitos foram provados em runtime pela revisão adversarial, não
inferidos de leitura.

⚠️ Nada aqui fecha G1b, e nada aqui tenta fechar. `supervised_local` convive com
o risco residual DECLARADO; `autonomous_contained` fica bloqueado até existir
runner que contenha filesystem, árvore de processos e insumos.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import threading
import time
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import mkdtemp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _e2e_fixture import ContadorDeModelos, missao, repo_sintetico  # noqa: E402

from volc_agent_harness.v3.baseline import (  # noqa: E402
    BaselineRecord, assert_baseline_is_green,
)
from volc_agent_harness.v3.failures import FailureClass, HarnessFailure  # noqa: E402
from volc_agent_harness.v3.gate_runner import (  # noqa: E402
    GateRunner, LocalRunner, run_gate_with_ledger,
)
from volc_agent_harness.v3.ledger import EvidenceLedger  # noqa: E402

FONTE = Path(__file__).resolve().parents[1] / "src" / "volc_agent_harness"


def _outcome_sem_autoridade():
    from volc_agent_harness.v3.gate_runner import GateOutcome

    return GateOutcome(
        gate_index=1, argv=["gate"], exit_code=0, stdout="", stderr="",
        duration_s=0.0, execution_mode="abandoned", status="infrastructure",
        evidence_id=None)


# ===========================================================================
# F1 — autoridade do baseline
# ===========================================================================
class F1_BaselineExigeAutoridade(unittest.TestCase):
    def test_runtime_nao_constroi_baselinerecord_a_mao(self):
        """Prova estrutural: `from_outcome` é a única porta produtiva."""

        import ast

        ofensores: list[str] = []
        for arquivo in sorted(FONTE.rglob("*.py")):
            rel = arquivo.relative_to(FONTE).as_posix()
            if rel == "v3/baseline.py":
                continue                       # onde `from_outcome` é definido
            arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                if (isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
                        and no.func.id == "BaselineRecord"):
                    ofensores.append(f"{rel}:{no.lineno}")
        self.assertEqual(ofensores, [],
                         "construção manual descarta ok/status/evidence_id")

    def test_outcome_sem_evidencia_nunca_vira_baseline_verde(self):
        alvo = _outcome_sem_autoridade()
        with self.assertRaises(HarnessFailure) as e:
            assert_baseline_is_green([BaselineRecord.from_outcome(alvo)])
        self.assertIn(e.exception.classe,
                      {FailureClass.INFRASTRUCTURE_ERROR, FailureClass.BASELINE_ERROR})

    def test_registro_sem_campos_de_autoridade_falha_fechado(self):
        """O filtro condicional deixava passar registro que não afirma nada."""

        mudo = BaselineRecord(gate_index=1, argv=["g"], exit_code=0, passed=None,
                              failed=None, duration_s=0.0)
        with self.assertRaises(HarnessFailure):
            assert_baseline_is_green([mudo])

    def test_baseline_verde_legitimo_continua_passando(self):
        from volc_agent_harness.v3.gate_runner import GateOutcome

        bom = GateOutcome(gate_index=1, argv=["g"], exit_code=0, stdout="",
                          stderr="", duration_s=0.1, execution_mode="executed",
                          status="green", evidence_id=7)
        assert_baseline_is_green([BaselineRecord.from_outcome(bom)])


# ===========================================================================
# F2 — claim sempre terminal após exceção capturável
# ===========================================================================
class F2_ClaimNuncaFicaRunning(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(mkdtemp())
        (self.raiz / "sub").mkdir()
        self.led = EvidenceLedger(self.raiz / "l.sqlite")

    def _rodar(self, **over):
        class Verde(GateRunner):
            name = "verde"
            def execute(self, **kw): return 0, "ok", ""

        base = dict(
            gate_index=1, argv=["x"], worktree=self.raiz, env={}, timeout=10,
            ledger=self.led, acceptance_id="P-A1", base_sha="s",
            candidate_sha=None, context_digest="c", env_fingerprint="e",
            production_digest="p", test_digest="t", run_id="r", worker_id="w",
            runner=Verde(), lease_seconds=60, wait_seconds=0.0,
        )
        base.update(over)
        return run_gate_with_ledger(**base)

    def test_erro_de_cwd_abandona_o_claim(self):
        with self.assertRaises(HarnessFailure):
            self._rodar(cwd_rel="nao/existe")
        self.assertEqual(self.led.claims_ativos(), [],
                         "claim ficou running depois de erro de cwd")

    def test_erro_no_snapshot_abandona_o_claim(self):
        import volc_agent_harness.v3.gate_runner as gr

        original = gr._snapshot
        gr._snapshot = lambda _wt: (_ for _ in ()).throw(OSError("git quebrou"))
        try:
            with self.assertRaises(BaseException):
                self._rodar()
        finally:
            gr._snapshot = original
        self.assertEqual(self.led.claims_ativos(), [])

    def test_erro_no_enrich_counts_abandona_o_claim(self):
        def explode(_code, _out, _err):
            raise ValueError("enriquecimento quebrou")

        with self.assertRaises(BaseException):
            self._rodar(enrich_counts=explode)
        self.assertEqual(self.led.claims_ativos(), [])

    def test_erro_na_entrada_do_heartbeat_abandona_o_claim(self):
        import volc_agent_harness.v3.gate_runner as gr

        original = gr._Heartbeat.__enter__
        gr._Heartbeat.__enter__ = lambda self: (_ for _ in ()).throw(
            RuntimeError("thread não subiu"))
        try:
            with self.assertRaises(BaseException):
                self._rodar()
        finally:
            gr._Heartbeat.__enter__ = original
        self.assertEqual(self.led.claims_ativos(), [])

    def test_erro_no_complete_abandona_o_claim(self):
        original = self.led.complete
        self.led.complete = lambda *a, **kw: (_ for _ in ()).throw(
            sqlite3.OperationalError("banco sumiu"))
        try:
            with self.assertRaises(BaseException):
                self._rodar()
        finally:
            self.led.complete = original
        self.assertEqual(self.led.claims_ativos(), [])

    def test_erro_original_e_relancado_e_nao_mascarado(self):
        def explode(_code, _out, _err):
            raise ValueError("marcador-do-erro-original")

        with self.assertRaises(ValueError) as e:
            self._rodar(enrich_counts=explode)
        self.assertIn("marcador-do-erro-original", str(e.exception))

    def test_falha_do_abandon_nao_mascara_o_erro_original(self):
        self.led.abandon = lambda *a, **kw: (_ for _ in ()).throw(
            sqlite3.OperationalError("abandon também quebrou"))
        with self.assertRaises(HarnessFailure):
            self._rodar(cwd_rel="nao/existe")

    def test_complete_valido_nunca_e_sobrescrito_por_abandon(self):
        saida = self._rodar()
        self.assertTrue(saida.ok)
        claim = self.led.claim_atual_por_evidencia(saida.evidence_id) \
            if hasattr(self.led, "claim_atual_por_evidencia") else None
        del claim
        linhas = [l for l in self.led.evidencias() if l["exit_code"] == 0]
        self.assertEqual(len(linhas), 1)
        self.assertEqual(self.led.claims_ativos(), [])


# ===========================================================================
# F3 — migração estrutural
# ===========================================================================
class F3_MigracaoEstrutural(unittest.TestCase):
    def _banco(self, ddl_extra: str = "") -> Path:
        from volc_agent_harness.v3.ledger import DDL_EVIDENCE

        alvo = Path(mkdtemp()) / "l.sqlite"
        ddl = DDL_EVIDENCE
        if ddl_extra:
            ddl = ddl.replace("created_at        TEXT NOT NULL",
                              f"created_at TEXT NOT NULL, {ddl_extra}")
        with sqlite3.connect(alvo) as c:
            c.execute(ddl)
        return alvo

    def test_not_null_sem_default_recusa_no_boot(self):
        alvo = self._banco("must_fill TEXT NOT NULL")
        with self.assertRaises(HarnessFailure) as e:
            EvidenceLedger(alvo)
        self.assertEqual(e.exception.classe, FailureClass.INFRASTRUCTURE_ERROR)

    def test_boot_verde_implica_primeiro_uso_verde(self):
        """Nunca 'boot verde, primeiro INSERT vermelho'."""

        for extra in ("", "extra_opcional TEXT", "com_default TEXT NOT NULL DEFAULT ''"):
            with self.subTest(extra=extra or "canônico"):
                alvo = self._banco(extra)
                led = EvidenceLedger(alvo)          # se bootou, tem de funcionar
                led.record(acceptance_id="A", kind="gate_1", base_sha="s",
                           run_id="r", command="c", production_digest="p",
                           test_digest="t")
                self.assertEqual(len(led.evidencias()), 1)

    def test_pk_divergente_recusa_no_boot(self):
        alvo = Path(mkdtemp()) / "l.sqlite"
        with sqlite3.connect(alvo) as c:
            c.execute("""CREATE TABLE evidence (
                id INTEGER, acceptance_id TEXT NOT NULL, kind TEXT NOT NULL,
                input_digest TEXT NOT NULL, run_id TEXT NOT NULL,
                PRIMARY KEY (acceptance_id, kind))""")
        with self.assertRaises(HarnessFailure) as e:
            EvidenceLedger(alvo)
        self.assertEqual(e.exception.classe, FailureClass.INFRASTRUCTURE_ERROR)

    def test_banco_recusado_nao_perde_linhas(self):
        alvo = self._banco("must_fill TEXT NOT NULL")
        with sqlite3.connect(alvo) as c:
            c.execute("INSERT INTO evidence(acceptance_id,kind,base_sha,input_digest,"
                      "production_digest,test_digest,command,run_id,created_at,must_fill)"
                      " VALUES('A','g','s','d','p','t','c','r','x','preserve-me')")
        with self.assertRaises(HarnessFailure):
            EvidenceLedger(alvo)
        with sqlite3.connect(alvo) as c:
            self.assertEqual(
                c.execute("SELECT must_fill FROM evidence").fetchone()[0], "preserve-me")

    def test_legado_compativel_migra_preservando_linhas(self):
        alvo = Path(mkdtemp()) / "l.sqlite"
        with sqlite3.connect(alvo) as c:
            c.execute("""CREATE TABLE evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                acceptance_id TEXT NOT NULL, kind TEXT NOT NULL,
                input_digest TEXT NOT NULL, run_id TEXT NOT NULL)""")
            c.execute("INSERT INTO evidence(acceptance_id,kind,input_digest,run_id)"
                      " VALUES('A','g','d','r0')")
        led = EvidenceLedger(alvo)
        led.record(acceptance_id="B", kind="gate_1", base_sha="s", run_id="r",
                   command="c", production_digest="p", test_digest="t")
        self.assertEqual(len(led.evidencias()), 2, "a linha legada sumiu")

    def test_unique_material_do_claim_e_exigido(self):
        """Sem o UNIQUE parcial, `complete()` duplicado deixa de ser barrado."""

        from volc_agent_harness.v3.ledger import GateIdentity

        alvo = Path(mkdtemp()) / "l.sqlite"
        led = EvidenceLedger(alvo)
        with sqlite3.connect(alvo) as c:
            indices = {l[0] for l in c.execute(
                "SELECT name FROM sqlite_master WHERE type='index'")}
        self.assertIn("idx_evidence_claim_unico", indices)
        del GateIdentity


# ===========================================================================
# F4 — o heartbeat precisa ser realmente chamado
# ===========================================================================
class F4_HeartbeatRealmenteExercitado(unittest.TestCase):
    def test_prova_de_concorrencia_invoca_o_heartbeat(self):
        """A prova antiga passava com ZERO chamadas: lease 126s, runner 4s."""

        raiz = Path(mkdtemp())
        led = EvidenceLedger(raiz / "l.sqlite")
        chamadas = {"n": 0, "falhas": 0}
        original = led.heartbeat
        comecou = threading.Event()
        liberar = threading.Event()

        def instavel(claim, **kw):
            chamadas["n"] += 1
            if chamadas["n"] == 2:
                chamadas["falhas"] += 1
                raise sqlite3.OperationalError("database is locked")
            return original(claim, **kw)

        led.heartbeat = instavel

        class Bloqueado(GateRunner):
            name = "bloqueado"
            def __init__(self):
                self.trava = threading.Lock(); self.ativos = 0; self.maximo = 0
            def execute(self, **kw):
                with self.trava:
                    self.ativos += 1
                    self.maximo = max(self.maximo, self.ativos)
                comecou.set()
                liberar.wait(20)
                with self.trava:
                    self.ativos -= 1
                return 0, "ok", ""

        runner = Bloqueado()
        saidas: list = []
        comum = dict(gate_index=1, argv=["mesmo"], worktree=raiz, env={},
                     timeout=1, ledger=led, acceptance_id="P-A1", base_sha="s",
                     candidate_sha=None, context_digest="c", env_fingerprint="e",
                     production_digest="p", test_digest="t", runner=runner,
                     lease_seconds=1, wait_seconds=0.0,
                     heartbeat_interval_seconds=0.15)

        fio = threading.Thread(target=lambda: saidas.append(
            run_gate_with_ledger(**comum, run_id="r1", worker_id="w1")))
        fio.start()
        comecou.wait(timeout=10)
        # Evento, não sleep: espera o heartbeat ser exercitado de verdade.
        for _ in range(400):
            if chamadas["n"] >= 3:
                break
            time.sleep(0.01)
        segundo = dict(comum, wait_seconds=0.4)
        saidas.append(run_gate_with_ledger(**segundo, run_id="r2", worker_id="w2"))
        liberar.set()
        fio.join(timeout=30)

        self.assertGreaterEqual(chamadas["n"], 2,
                                "o heartbeat injetado nunca foi chamado")
        self.assertGreaterEqual(chamadas["falhas"], 1,
                                "a falha transitória não ocorreu durante o runner")
        self.assertEqual(runner.maximo, 1, "duas execuções físicas concorrentes")
        self.assertFalse(any(s.status == "green" and s.evidence_id is None
                             for s in saidas), "ok=True sem evidence_id")

    def test_intervalo_do_heartbeat_e_injetavel(self):
        import inspect
        self.assertIn("heartbeat_interval_seconds",
                      inspect.signature(run_gate_with_ledger).parameters)


# ===========================================================================
# CAPACIDADES — supervised_local permitido, autonomous_contained fail-closed
# ===========================================================================
class Capacidades_ContratoDoRunner(unittest.TestCase):
    def test_localrunner_declara_as_tres_capacidades_como_falsas(self):
        self.assertFalse(LocalRunner.contains_filesystem)
        self.assertFalse(LocalRunner.contains_process_tree)
        self.assertFalse(LocalRunner.immutable_inputs)

    def test_localrunner_suporta_supervised_e_nao_autonomous(self):
        suportados = LocalRunner.modes_supported()
        self.assertIn("supervised_local", suportados)
        self.assertNotIn("autonomous_contained", suportados)

    def test_missao_declara_runner_safety_mode_com_default_supervisionado(self):
        from volc_agent_harness.models import MissionSpec

        self.assertIn("runner_safety_mode", MissionSpec.model_fields)
        self.assertEqual(
            MissionSpec.model_fields["runner_safety_mode"].default,
            "supervised_local")

    def test_autonomous_contained_recusado_antes_de_modelo_ou_subprocesso(self):
        import volc_agent_harness.mission as mm
        from volc_agent_harness.cli import main as cli_main

        repo = repo_sintetico(Path(mkdtemp()))
        contador = ContadorDeModelos()
        original = mm.adapter_for
        mm.adapter_for = contador.adapter_for
        try:
            alvo = missao(repo, runner_safety_mode="autonomous_contained",
                          gates=[{"kind": "catalog", "gate_id": "diff-limpo"}])
            buffer = StringIO()
            with redirect_stdout(buffer):
                codigo = cli_main(["--mission", str(alvo), "--repo", str(repo)])
            saida = buffer.getvalue()
        finally:
            mm.adapter_for = original
        self.assertEqual(codigo, 3, saida)
        self.assertIn("AUTHORIZATION_BLOCK", saida)
        self.assertEqual(contador.chamadas, [],
                         "nenhum modelo pode ter sido chamado")

    def test_nunca_degrada_autonomous_para_supervised_em_silencio(self):
        import inspect
        import volc_agent_harness.mission as mm

        fonte = inspect.getsource(mm)
        self.assertNotIn('runner_safety_mode = "supervised_local"', fonte,
                         "degradação silenciosa de modo")


# ===========================================================================
# EVIDÊNCIA HONESTA
# ===========================================================================
class EvidenciaHonesta(unittest.TestCase):
    def test_counts_registram_o_risco_residual_e_as_capacidades(self):
        raiz = Path(mkdtemp())
        led = EvidenceLedger(raiz / "l.sqlite")

        class Verde(GateRunner):
            name = "verde"
            def execute(self, **kw): return 0, "ok", ""

        run_gate_with_ledger(
            gate_index=1, argv=["x"], worktree=raiz, env={}, timeout=10,
            ledger=led, acceptance_id="P-A1", base_sha="s", candidate_sha=None,
            context_digest="c", env_fingerprint="e", production_digest="p",
            test_digest="t", run_id="r", worker_id="w", runner=Verde(),
            lease_seconds=60, wait_seconds=0.0)
        contagens = json.loads(led.evidencias()[0]["counts_json"])
        for chave in ("input_fingerprint", "revalidated_at", "revalidation_points",
                      "atomic_snapshot", "residual_risk", "contains_filesystem",
                      "contains_process_tree", "immutable_inputs",
                      "runner_safety_mode"):
            self.assertIn(chave, contagens, f"evidência sem {chave}")
        self.assertFalse(contagens["atomic_snapshot"])
        self.assertEqual(contagens["residual_risk"], "G1b")


if __name__ == "__main__":
    unittest.main()
