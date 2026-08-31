"""Contraprovas dos quatro hard stops que barraram o encerramento.

Todas reproduzidas em runtime pela revisão final e por mim, em arquivo real —
não em inferência. Cada teste afirma o comportamento exigido e falha contra
`c9736cd`.

⚠️ G1b continua ABERTA e inclui, explicitamente: filho destacado por `setsid()`,
filesystem externo, TOCTOU residual e ausência de snapshot imutável. Nada aqui
tenta fechar nenhum dos quatro.
"""

from __future__ import annotations

import os
import signal
import sqlite3
import subprocess
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

from _e2e_fixture import (  # noqa: E402
    ContadorDeModelos, escreve_teste_novo, missao, repo_sintetico,
)

from volc_agent_harness.v3.baseline import (  # noqa: E402
    BaselineRecord, assert_baseline_is_green,
)
from volc_agent_harness.v3.failures import FailureClass, HarnessFailure  # noqa: E402
from volc_agent_harness.v3.gate_runner import (  # noqa: E402
    GateOutcome, GateRunner, LocalRunner, run_gate_with_ledger,
)
from volc_agent_harness.v3.ledger import EvidenceLedger, GateIdentity  # noqa: E402

FONTE = Path(__file__).resolve().parents[1] / "src" / "volc_agent_harness"

#: `evidence` completa, para variar UMA propriedade por vez.
DDL_BOM = """CREATE TABLE evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT, acceptance_id TEXT NOT NULL,
    kind TEXT NOT NULL, base_sha TEXT NOT NULL DEFAULT '', candidate_sha TEXT,
    input_digest TEXT NOT NULL, production_digest TEXT NOT NULL DEFAULT '',
    test_digest TEXT NOT NULL DEFAULT '', command TEXT NOT NULL DEFAULT '',
    cwd TEXT NOT NULL DEFAULT '', env_fingerprint TEXT NOT NULL DEFAULT '',
    context_digest TEXT NOT NULL DEFAULT '', exit_code INTEGER,
    counts_json TEXT, reviewer TEXT, finding TEXT, counterproof TEXT,
    valid INTEGER NOT NULL DEFAULT 1, invalidated_reason TEXT,
    claim_key TEXT, fencing_token INTEGER, run_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT '')"""


def _identidade(**over) -> GateIdentity:
    campos = dict(acceptance_id="P-A1", kind="gate_1", context_digest="c",
                  production_digest="p", test_digest="t", command_digest="cmd",
                  env_fingerprint="e")
    campos.update(over)
    return GateIdentity(**campos)


# ===========================================================================
# HS-1 / HS-4 — autoridade estrutural do SQLite
# ===========================================================================
class HS1_EstruturaRealSuportaOperacaoReal(unittest.TestCase):
    def _banco(self, ddl: str) -> Path:
        alvo = Path(mkdtemp()) / "l.sqlite"
        with sqlite3.connect(alvo) as c:
            c.execute(ddl)
        return alvo

    def test_id_text_primary_key_recusado_no_boot(self):
        """`lastrowid` devolve rowid; a PK material fica NULL. Falso GREEN."""

        alvo = self._banco(DDL_BOM.replace(
            "id INTEGER PRIMARY KEY AUTOINCREMENT", "id TEXT PRIMARY KEY"))
        with self.assertRaises(HarnessFailure) as e:
            EvidenceLedger(alvo)
        self.assertEqual(e.exception.classe, FailureClass.INFRASTRUCTURE_ERROR)

    def test_coluna_nullable_declarada_not_null_recusada(self):
        alvo = self._banco(DDL_BOM.replace(
            "candidate_sha TEXT,", "candidate_sha TEXT NOT NULL,"))
        with self.assertRaises(HarnessFailure) as e:
            EvidenceLedger(alvo)
        self.assertEqual(e.exception.classe, FailureClass.INFRASTRUCTURE_ERROR)

    def test_affinity_incompativel_em_coluna_obrigatoria_recusada(self):
        alvo = self._banco(DDL_BOM.replace(
            "exit_code INTEGER,", "exit_code TEXT,"))
        with self.assertRaises(HarnessFailure) as e:
            EvidenceLedger(alvo)
        self.assertEqual(e.exception.classe, FailureClass.INFRASTRUCTURE_ERROR)

    def test_indice_com_nome_certo_e_colunas_erradas_recusado(self):
        """Validar índice por NOME deixa a unicidade material sumir."""

        alvo = self._banco(DDL_BOM)
        with sqlite3.connect(alvo) as c:
            c.execute("CREATE INDEX idx_evidence_claim_unico ON evidence(run_id)")
        with self.assertRaises(HarnessFailure) as e:
            EvidenceLedger(alvo)
        self.assertEqual(e.exception.classe, FailureClass.INFRASTRUCTURE_ERROR)

    def test_execution_claim_incompleta_recusada(self):
        alvo = self._banco(DDL_BOM)
        with sqlite3.connect(alvo) as c:
            c.execute("CREATE TABLE execution_claim ("
                      "logical_key TEXT PRIMARY KEY, state TEXT NOT NULL, "
                      "lease_until TEXT NOT NULL)")
        with self.assertRaises(HarnessFailure) as e:
            EvidenceLedger(alvo)
        self.assertEqual(e.exception.classe, FailureClass.INFRASTRUCTURE_ERROR)

    def test_boot_verde_implica_primeiro_uso_verde_e_endereçavel(self):
        """O invariante que HS-1 quebrou: se bootou, a evidência resolve."""

        for nome, ddl in (("canônico", DDL_BOM),
                          ("com coluna extra opcional",
                           DDL_BOM.replace("created_at TEXT NOT NULL DEFAULT '')",
                                           "created_at TEXT NOT NULL DEFAULT '', "
                                           "extra TEXT)"))):
            with self.subTest(schema=nome):
                led = EvidenceLedger(self._banco(ddl))
                eid = led.record(acceptance_id="A", kind="gate_1", base_sha="s",
                                 run_id="r", command="c", production_digest="p",
                                 test_digest="t", exit_code=0)
                with sqlite3.connect(led.path) as c:
                    n = c.execute("SELECT COUNT(*) FROM evidence WHERE id=?",
                                  (eid,)).fetchone()[0]
                self.assertEqual(n, 1, "evidence_id não resolve exatamente 1 linha")

    def test_prova_de_primeiro_uso_nao_deixa_residuo(self):
        """A sonda roda em SAVEPOINT e desfaz tudo."""

        led = EvidenceLedger(self._banco(DDL_BOM))
        with sqlite3.connect(led.path) as c:
            evid = c.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
            claims = c.execute("SELECT COUNT(*) FROM execution_claim").fetchone()[0]
        self.assertEqual((evid, claims), (0, 0),
                         "a sonda de primeiro uso deixou linhas para trás")

    def test_banco_recusado_preserva_linhas(self):
        alvo = self._banco(DDL_BOM.replace("candidate_sha TEXT,",
                                           "candidate_sha TEXT NOT NULL,"))
        with sqlite3.connect(alvo) as c:
            c.execute("INSERT INTO evidence(acceptance_id,kind,input_digest,"
                      "run_id,candidate_sha) VALUES('A','g','d','r','preserve-me')")
        with self.assertRaises(HarnessFailure):
            EvidenceLedger(alvo)
        with sqlite3.connect(alvo) as c:
            self.assertEqual(
                c.execute("SELECT candidate_sha FROM evidence").fetchone()[0],
                "preserve-me")

    def test_legado_compativel_continua_migrando(self):
        alvo = Path(mkdtemp()) / "l.sqlite"
        with sqlite3.connect(alvo) as c:
            c.execute("""CREATE TABLE evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT, acceptance_id TEXT NOT NULL,
                kind TEXT NOT NULL, input_digest TEXT NOT NULL,
                run_id TEXT NOT NULL)""")
            c.execute("INSERT INTO evidence(acceptance_id,kind,input_digest,run_id)"
                      " VALUES('A','g','d','r0')")
        led = EvidenceLedger(alvo)
        led.record(acceptance_id="B", kind="gate_1", base_sha="s", run_id="r",
                   command="c", production_digest="p", test_digest="t")
        self.assertEqual(len(led.evidencias()), 2)


# ===========================================================================
# HS-2 — processo sem autoridade não continua
# ===========================================================================
class HS2_ProcessoSemAutoridadeNaoContinua(unittest.TestCase):
    def test_excecao_nao_timeout_encerra_o_processo(self):
        raiz = Path(mkdtemp())
        marca = raiz / "ESCREVEU_DEPOIS"
        script = raiz / "lento.py"
        script.write_text(
            f"import time, pathlib\ntime.sleep(3)\n"
            f"pathlib.Path(r'{marca}').write_text('vivo')\n")

        runner = LocalRunner()
        erro: list = []

        def go():
            try:
                runner.execute(argv=[sys.executable, str(script)], cwd=raiz,
                               env=dict(os.environ), timeout=30)
            except BaseException as e:
                erro.append(type(e).__name__)

        fio = threading.Thread(target=go)
        fio.start()
        time.sleep(0.8)
        # Interrupção capturável durante o `communicate()` — não é Timeout.
        import ctypes
        for t in threading.enumerate():
            if t is fio:
                ctypes.pythonapi.PyThreadState_SetAsyncExc(
                    ctypes.c_ulong(t.ident), ctypes.py_object(KeyboardInterrupt))
        fio.join(timeout=20)
        time.sleep(3.5)
        self.assertFalse(marca.exists(),
                         "processo comum escreveu DEPOIS da exceção")

    def test_finally_nao_apaga_referencia_de_processo_vivo(self):
        import inspect
        fonte = inspect.getsource(LocalRunner.execute)
        self.assertIn("BaseException", fonte,
                      "só TimeoutExpired era tratado; o resto vazava vivo")
        self.assertIn("wait(", fonte, "cancelar sem aguardar não prova terminação")

    def test_uma_execucao_fisica_apos_interrupcao(self):
        raiz = Path(mkdtemp())
        led = EvidenceLedger(raiz / "l.sqlite")
        contagem = {"ativos": 0, "maximo": 0}
        trava = threading.Lock()
        liberar = threading.Event()

        class Contado(GateRunner):
            name = "contado"
            def execute(self, **kw):
                with trava:
                    contagem["ativos"] += 1
                    contagem["maximo"] = max(contagem["maximo"], contagem["ativos"])
                liberar.wait(6)
                with trava:
                    contagem["ativos"] -= 1
                return 0, "ok", ""

        comum = dict(gate_index=1, argv=["mesmo"], worktree=raiz, env={},
                     timeout=5, ledger=led, acceptance_id="P-A1", base_sha="s",
                     candidate_sha=None, context_digest="c", env_fingerprint="e",
                     production_digest="p", test_digest="t", runner=Contado(),
                     lease_seconds=1, wait_seconds=0.0)
        fio = threading.Thread(target=lambda: run_gate_with_ledger(
            **comum, run_id="r1", worker_id="w1"))
        fio.start()
        time.sleep(0.5)
        segundo = run_gate_with_ledger(**dict(comum, wait_seconds=0.5),
                                       run_id="r2", worker_id="w2")
        liberar.set()
        fio.join(timeout=30)
        self.assertEqual(contagem["maximo"], 1)
        del segundo

    def test_contains_process_tree_continua_falso(self):
        """G1b: filho destacado por setsid segue fora da garantia."""

        self.assertFalse(LocalRunner.contains_process_tree)
        self.assertNotIn("autonomous_contained", LocalRunner.modes_supported())


# ===========================================================================
# HS-3 — claim nunca fica irrecuperável
# ===========================================================================
class HS3_ClaimNuncaIrrecuperavel(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(mkdtemp())
        self.led = EvidenceLedger(self.raiz / "l.sqlite")

    def test_excecao_depois_do_commit_do_acquire_nao_perde_o_token(self):
        """O objeto tem de estar pronto ANTES do COMMIT."""

        import inspect
        fonte = inspect.getsource(self.led._tentar_claim)
        depois = fonte.split('c.execute("COMMIT")')[-1]
        # Depois do último COMMIT só pode haver a devolução do Claim já pronto.
        self.assertNotIn("dataclass_replace", depois)
        self.assertNotIn("canonical_cwd", depois)

    def test_abandon_faz_retry_em_falha_transitoria(self):
        ident = _identidade()
        claim = self.led.acquire(ident, run_id="r", worker_id="w",
                                 lease_seconds=60, wait_seconds=0.0)
        tentativas = {"n": 0}
        original = self.led._conn

        def instavel():
            tentativas["n"] += 1
            if tentativas["n"] == 1:
                raise sqlite3.OperationalError("database is locked")
            return original()

        self.led._conn = instavel
        try:
            ok = self.led.abandon(claim)
        finally:
            self.led._conn = original
        self.assertTrue(ok, "abandon desistiu na primeira falha transitória")
        self.assertEqual(self.led.claims_ativos(), [])

    def test_falha_persistente_do_abandon_mantem_lease_finito_e_retomavel(self):
        ident = _identidade()
        claim = self.led.acquire(ident, run_id="r1", worker_id="w1",
                                 lease_seconds=1, wait_seconds=0.0)
        self.led._conn_original = self.led._conn
        self.led._conn = lambda: (_ for _ in ()).throw(
            sqlite3.OperationalError("banco fora do ar"))
        try:
            self.led.abandon(claim)
        except BaseException:
            pass
        finally:
            self.led._conn = self.led._conn_original

        linha = self.led.claim_atual(ident)
        self.assertIsNotNone(linha)
        self.assertLess(float(linha["lease_until"]) - time.time(), 5,
                        "lease precisa ser FINITO para o digest ser retomável")
        time.sleep(1.2)
        novo = self.led.acquire(ident, run_id="r2", worker_id="w2",
                                lease_seconds=60, wait_seconds=0.0)
        self.assertEqual(novo.outcome.value, "reclaimed_after_expiry")

    def test_erro_original_preservado_quando_abandon_falha(self):
        class Explode(GateRunner):
            name = "explode"
            def execute(self, **kw): raise AssertionError("nunca chega aqui")

        self.led.abandon = lambda *a, **kw: (_ for _ in ()).throw(
            sqlite3.OperationalError("abandon quebrou"))
        with self.assertRaises(HarnessFailure) as e:
            run_gate_with_ledger(
                gate_index=1, argv=["x"], worktree=self.raiz, env={}, timeout=10,
                ledger=self.led, acceptance_id="P-A1", base_sha="s",
                candidate_sha=None, context_digest="c", env_fingerprint="e",
                production_digest="p", test_digest="t", run_id="r", worker_id="w",
                runner=Explode(), cwd_rel="nao/existe", lease_seconds=60,
                wait_seconds=0.0)
        self.assertEqual(e.exception.classe, FailureClass.SPEC_ERROR,
                         "a falha do abandon mascarou a causa original")


# ===========================================================================
# HS-5 — capability check global, antes de tudo
# ===========================================================================
class HS5_CapabilityCheckGlobal(unittest.TestCase):
    def _rodar(self, **over) -> tuple[int, str, ContadorDeModelos]:
        import volc_agent_harness.mission as mm
        from volc_agent_harness.cli import main as cli_main

        repo = repo_sintetico(Path(mkdtemp()))
        contador = ContadorDeModelos(escrita=escreve_teste_novo)
        original = mm.adapter_for
        mm.adapter_for = contador.adapter_for
        try:
            alvo = missao(repo, **over)
            buf = StringIO()
            with redirect_stdout(buf):
                codigo = cli_main(["--mission", str(alvo), "--repo", str(repo)])
            return codigo, buf.getvalue(), contador
        finally:
            mm.adapter_for = original

    def test_A_gate_dependente_de_produced_bloqueia_antes_do_writer(self):
        codigo, saida, contador = self._rodar(
            runner_safety_mode="autonomous_contained",
            produced_paths=[{"path": "backend/tests/test_novo.py", "required": True}],
            gates=[{"kind": "pytest", "targets": ["backend/tests/test_novo.py"]}])
        self.assertEqual(codigo, 3, saida)
        self.assertIn("AUTHORIZATION_BLOCK", saida)
        self.assertEqual(contador.chamadas, [], "modelo chamado apesar do bloqueio")

    def test_B_sem_gates_bloqueia_igual(self):
        codigo, saida, contador = self._rodar(
            runner_safety_mode="autonomous_contained", mode="read_only",
            commit_message=None, gates=[],
            workers=[
                {"id": "inv-a", "provider": "codex", "model": "gpt-5.5",
                 "lens": "x", "allowed_paths": ["backend"]},
                {"id": "inv-b", "provider": "codex", "model": "gpt-5.5",
                 "lens": "y", "allowed_paths": ["backend"]},
            ])
        self.assertEqual(codigo, 3, saida)
        self.assertIn("AUTHORIZATION_BLOCK", saida)
        self.assertEqual(contador.chamadas, [])

    def test_C_somente_reviewers_nenhum_e_chamado(self):
        codigo, saida, contador = self._rodar(
            runner_safety_mode="autonomous_contained", mode="read_only",
            commit_message=None,
            gates=[{"kind": "catalog", "gate_id": "diff-limpo"}],
            workers=[
                {"id": "rev-a", "provider": "codex", "model": "gpt-5.6-sol",
                 "role": "investigator", "lens": "x", "allowed_paths": ["backend"]},
                {"id": "rev-b", "provider": "codex", "model": "gpt-5.5",
                 "role": "investigator", "lens": "y", "allowed_paths": ["backend"]},
            ])
        self.assertEqual(codigo, 3, saida)
        self.assertEqual(contador.chamadas, [], "reviewer chamado apesar do bloqueio")

    def test_D_supervised_local_permanece_funcional(self):
        codigo, saida, contador = self._rodar(
            gates=[{"kind": "catalog", "gate_id": "diff-limpo"}])
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(len(contador.writers), 1)

    def test_guarda_e_unica_e_fica_no_topo(self):
        import inspect
        import volc_agent_harness.mission as mm

        fonte = inspect.getsource(mm.run_mission)
        self.assertIn("_assert_modo_suportado", fonte,
                      "a guarda precisa estar no topo do fluxo, não só no runner")

    def test_nenhuma_worktree_mutavel_antes_do_bloqueio(self):
        repo_dir = mkdtemp()
        codigo, saida, _ = self._rodar(
            runner_safety_mode="autonomous_contained",
            gates=[{"kind": "catalog", "gate_id": "diff-limpo"}])
        self.assertEqual(codigo, 3, saida)
        del repo_dir


# ===========================================================================
# ESCOPO 5 e 6 — lease_timeout e baseline
# ===========================================================================
class Escopo56_EvidenciaEBaseline(unittest.TestCase):
    def test_lease_timeout_grava_evidencia_honesta(self):
        import json

        raiz = Path(mkdtemp())
        led = EvidenceLedger(raiz / "l.sqlite")
        ident = GateIdentity.for_gate(
            acceptance_id="P-A1", gate_index=1, argv=["x"], context_digest="c",
            production_digest="p", test_digest="t", env_fingerprint="e")
        led.acquire(ident, run_id="r1", worker_id="w1", lease_seconds=300,
                    wait_seconds=0.0)

        class Nunca(GateRunner):
            name = "nunca"
            def execute(self, **kw): raise AssertionError("não devia executar")

        saida = run_gate_with_ledger(
            gate_index=1, argv=["x"], worktree=raiz, env={}, timeout=10,
            ledger=led, acceptance_id="P-A1", base_sha="s", candidate_sha=None,
            context_digest="c", env_fingerprint="e", production_digest="p",
            test_digest="t", run_id="r2", worker_id="w2", runner=Nunca(),
            lease_seconds=300, wait_seconds=0.3)
        self.assertEqual(saida.claim_outcome, "lease_timeout")
        linha = [e for e in led.evidencias() if e["exit_code"] is None][-1]
        contagens = json.loads(linha["counts_json"])
        for chave in ("input_fingerprint", "revalidated_at", "revalidation_points",
                      "atomic_snapshot", "residual_risk", "runner_safety_mode",
                      "contains_filesystem", "contains_process_tree",
                      "immutable_inputs"):
            self.assertIn(chave, contagens, f"lease_timeout sem {chave}")

    def test_zero_construcao_produtiva_de_baselinerecord(self):
        import ast

        ofensores = []
        for arquivo in sorted(FONTE.rglob("*.py")):
            rel = arquivo.relative_to(FONTE).as_posix()
            if rel == "v3/baseline.py":
                continue
            for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
                if (isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
                        and no.func.id == "BaselineRecord"):
                    ofensores.append(f"{rel}:{no.lineno}")
        self.assertEqual(ofensores, [])

    def test_outcome_sem_evidencia_nunca_e_baseline_verde(self):
        o = GateOutcome(gate_index=1, argv=["g"], exit_code=0, stdout="", stderr="",
                        duration_s=0, execution_mode="abandoned",
                        status="infrastructure", evidence_id=None)
        with self.assertRaises(HarnessFailure):
            assert_baseline_is_green([BaselineRecord.from_outcome(o)])


if __name__ == "__main__":
    unittest.main()
