"""Contraprovas da microcorreção final — A a F.

Modelo de ameaça FIXADO para `supervised_local`: o armazenamento local do
harness é confiável DURANTE a execução. Escrita hostil concorrente no SQLite
está fora de escopo e pertence a G1b. Schema inesperado ou trigger presente NO
BOOT é incompatibilidade, e é recusado.

⚠️ Nada aqui muda G1b: filho com `setsid()`, filesystem externo, TOCTOU residual
e ausência de snapshot imutável seguem abertos. `contains_process_tree` continua
False, e há prova disso.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import mkdtemp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from volc_agent_harness.v3.failures import FailureClass, HarnessFailure  # noqa: E402
from volc_agent_harness.v3.gate_runner import (  # noqa: E402
    GateRunner, LocalRunner, run_gate_with_ledger,
)
from volc_agent_harness.v3.ledger import EvidenceLedger, GateIdentity  # noqa: E402

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
# A — HS-2: encerramento REAL do grupo
# ===========================================================================
class A_GrupoDeProcessosEncerradoDeVerdade(unittest.TestCase):
    """`proc.wait()` do líder não é prova de morte do grupo.

    Um filho no MESMO grupo — sem `setsid()` — que instala handler de SIGTERM
    sobrevivia: o líder morria, `wait()` retornava, e o laço saía sem nunca
    escalar para KILL. Instalar handler de TERM para desligar com calma é
    comportamento normal de programa, não ataque.
    """

    def _cenario(self, raiz: Path) -> tuple[Path, Path, Path]:
        marca, pid_file, pronto = (raiz / "TARDIO", raiz / "PID", raiz / "PRONTO")
        (raiz / "filho.py").write_text(
            "import signal, time, pathlib\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            f"pathlib.Path(r'{pronto}').write_text('ok')\n"
            "time.sleep(6)\n"
            f"pathlib.Path(r'{marca}').write_text('escrevi depois')\n")
        (raiz / "pai.py").write_text(
            "import subprocess, sys, time, pathlib\n"
            f"f = subprocess.Popen([sys.executable, r'{raiz}/filho.py'])\n"
            f"pathlib.Path(r'{pid_file}').write_text(str(f.pid))\n"
            "time.sleep(30)\n")
        return marca, pid_file, pronto

    def test_filho_no_mesmo_grupo_que_ignora_term_e_encerrado(self):
        raiz = Path(mkdtemp())
        marca, pid_file, pronto = self._cenario(raiz)
        runner = LocalRunner()
        original = subprocess.Popen.communicate

        def explode(self, *a, **kw):
            if kw.get("timeout") is not None:
                # Interrompe SÓ depois que o handler está instalado. Antes
                # disso o TERM mataria o filho por default e a prova mediria
                # outra coisa.
                for _ in range(500):
                    if pronto.exists():
                        break
                    time.sleep(0.02)
                raise KeyboardInterrupt("interrupção com filho pronto")
            return original(self, *a, **kw)

        subprocess.Popen.communicate = explode
        try:
            with self.assertRaises(KeyboardInterrupt):
                runner.execute(argv=[sys.executable, str(raiz / "pai.py")],
                               cwd=raiz, env=dict(os.environ), timeout=30)
        finally:
            subprocess.Popen.communicate = original

        self.assertTrue(pronto.exists(), "o cenário não chegou a ser montado")
        pid = int(pid_file.read_text())
        time.sleep(7)
        vivo = True
        try:
            os.kill(pid, 0)
        except (OSError, ProcessLookupError):
            vivo = False
        if vivo:                                   # pragma: no cover
            os.kill(pid, 9)
        self.assertFalse(vivo, "o filho do mesmo grupo sobreviveu ao encerramento")
        self.assertFalse(marca.exists(), "marcador tardio foi escrito")

    def test_encerrar_escala_para_kill_e_confere_o_grupo(self):
        import inspect
        fonte = inspect.getsource(LocalRunner._encerrar)
        self.assertIn("SIGKILL", fonte)
        self.assertIn("_grupo_existe", fonte,
                      "morte do líder não é prova de morte do grupo")
        # A graça mora em `_aguardar_grupo`, que é quem conta o tempo.
        espera = inspect.getsource(LocalRunner._aguardar_grupo)
        self.assertIn("monotonic", espera, "graça precisa de relógio monotônico")

    def test_grupo_que_nao_morre_falha_fechado(self):
        raiz = Path(mkdtemp())
        runner = LocalRunner()
        runner._grupo_existe = lambda _pgid: True      # nunca some
        # Processo VIVO: com um já colhido, `getpgid` levanta e `_encerrar`
        # retorna cedo — a prova mediria o caminho errado.
        (raiz / "longo.py").write_text("import time\ntime.sleep(20)\n")
        proc = subprocess.Popen([sys.executable, str(raiz / "longo.py")],
                                cwd=raiz, start_new_session=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: (proc.kill(), proc.wait()))
        with self.assertRaises(HarnessFailure) as e:
            runner._encerrar(proc)
        self.assertEqual(e.exception.classe, FailureClass.INFRASTRUCTURE_ERROR)

    def test_setsid_continua_fora_do_contrato(self):
        self.assertFalse(LocalRunner.contains_process_tree)
        self.assertNotIn("autonomous_contained", LocalRunner.modes_supported())


# ===========================================================================
# B — triggers no ledger são incompatibilidade
# ===========================================================================
class B_TriggersRecusadosNoBoot(unittest.TestCase):
    def _com_trigger(self, alvo_tabela: str) -> Path:
        alvo = Path(mkdtemp()) / "l.sqlite"
        with sqlite3.connect(alvo) as c:
            c.execute(DDL_BOM)
            c.execute(f"""CREATE TRIGGER t_hostil AFTER INSERT ON {alvo_tabela}
                          BEGIN DELETE FROM evidence WHERE id = NEW.id; END""")
        return alvo

    def test_trigger_em_evidence_recusado(self):
        with self.assertRaises(HarnessFailure) as e:
            EvidenceLedger(self._com_trigger("evidence"))
        self.assertEqual(e.exception.classe, FailureClass.INFRASTRUCTURE_ERROR)

    def test_trigger_em_execution_claim_recusado(self):
        alvo = Path(mkdtemp()) / "l.sqlite"
        with sqlite3.connect(alvo) as c:
            c.execute(DDL_BOM)
            c.execute("CREATE TABLE execution_claim (logical_key TEXT PRIMARY KEY,"
                      " state TEXT NOT NULL DEFAULT 'abandoned')")
            c.execute("""CREATE TRIGGER t_claim AFTER UPDATE ON execution_claim
                         BEGIN UPDATE execution_claim SET lease_until=9e999; END""")
        with self.assertRaises(HarnessFailure) as e:
            EvidenceLedger(alvo)
        self.assertEqual(e.exception.classe, FailureClass.INFRASTRUCTURE_ERROR)

    def test_banco_com_trigger_e_preservado(self):
        alvo = self._com_trigger("evidence")
        antes = alvo.stat().st_size
        with self.assertRaises(HarnessFailure):
            EvidenceLedger(alvo)
        with sqlite3.connect(alvo) as c:
            triggers = [l[0] for l in c.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'")]
        self.assertEqual(triggers, ["t_hostil"], "o harness apagou o trigger")
        self.assertGreater(alvo.stat().st_size, 0)
        del antes

    def test_schema_oficial_nao_tem_trigger(self):
        led = EvidenceLedger(Path(mkdtemp()) / "novo.sqlite")
        with sqlite3.connect(led.path) as c:
            n = c.execute("SELECT COUNT(*) FROM sqlite_master "
                          "WHERE type='trigger'").fetchone()[0]
        self.assertEqual(n, 0)


# ===========================================================================
# C — sonda imprevisível, pelos métodos públicos
# ===========================================================================
class C_SondaPublicaEImprevisivel(unittest.TestCase):
    def test_sonda_usa_nonce_e_nao_valor_fixo(self):
        import inspect
        from volc_agent_harness.v3 import ledger

        fonte = inspect.getsource(ledger._prova_de_primeiro_uso)
        # Só o CÓDIGO: a docstring cita o literal antigo para explicar o
        # defeito, e proibir a explicação seria a régua errada.
        codigo = fonte.split('"""')[2] if fonte.count('"""') >= 2 else fonte
        self.assertNotIn("'sonda'", codigo,
                         "marcador fixo é santo-e-senha, não sonda")
        self.assertIn("secrets", codigo, "o nonce precisa ser imprevisível")

    def test_sonda_passa_pelos_metodos_publicos(self):
        import inspect
        from volc_agent_harness.v3 import ledger

        # `acquire`/`complete` abrem conexão própria e não enxergam o SAVEPOINT
        # da migração; a prova pela API pública roda sobre uma CÓPIA do banco.
        fonte = inspect.getsource(EvidenceLedger._provar_api_publica)
        for metodo in ("acquire(", "complete(", "claim_atual("):
            self.assertIn(metodo, fonte,
                          f"a sonda precisa exercer {metodo} de verdade")
        self.assertIn("secrets", fonte, "o nonce precisa ser imprevisível")

    def test_sonda_nao_deixa_linha_persistida(self):
        led = EvidenceLedger(Path(mkdtemp()) / "l.sqlite")
        with sqlite3.connect(led.path) as c:
            evid = c.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
            claims = c.execute("SELECT COUNT(*) FROM execution_claim").fetchone()[0]
        self.assertEqual((evid, claims), (0, 0))

    def test_boot_verde_implica_evidencia_resolvivel(self):
        led = EvidenceLedger(Path(mkdtemp()) / "l.sqlite")
        eid = led.record(acceptance_id="A", kind="gate_1", base_sha="s",
                         run_id="r", command="c", production_digest="p",
                         test_digest="t", exit_code=0)
        with sqlite3.connect(led.path) as c:
            n = c.execute("SELECT COUNT(*) FROM evidence WHERE id=?",
                          (eid,)).fetchone()[0]
        self.assertEqual(n, 1)


# ===========================================================================
# D — defaults comparados de verdade
# ===========================================================================
class D_DefaultsComparados(unittest.TestCase):
    def _banco(self, ddl: str) -> Path:
        alvo = Path(mkdtemp()) / "l.sqlite"
        with sqlite3.connect(alvo) as c:
            c.execute(ddl)
        return alvo

    def test_default_material_ausente_recusado(self):
        alvo = self._banco(DDL_BOM.replace(
            "valid INTEGER NOT NULL DEFAULT 1", "valid INTEGER NOT NULL"))
        with self.assertRaises(HarnessFailure) as e:
            EvidenceLedger(alvo)
        self.assertEqual(e.exception.classe, FailureClass.INFRASTRUCTURE_ERROR)

    def test_default_equivalente_com_sintaxe_diferente_aceito(self):
        """`''`, `("")` e `''` são o mesmo default para o SQLite."""

        for variante in ("DEFAULT ('')", "DEFAULT ''", "DEFAULT (('') )"):
            with self.subTest(sintaxe=variante):
                alvo = self._banco(DDL_BOM.replace(
                    "base_sha TEXT NOT NULL DEFAULT ''",
                    f"base_sha TEXT NOT NULL {variante}"))
                EvidenceLedger(alvo)      # não pode levantar

    def test_coluna_nullable_sem_default_continua_valida(self):
        EvidenceLedger(self._banco(DDL_BOM))     # candidate_sha é nullable

    def test_tem_default_participa_da_divergencia(self):
        import inspect
        from volc_agent_harness.v3 import sqlite_support

        fonte = inspect.getsource(sqlite_support.ColunaEsperada.divergencia)
        self.assertIn("if self.tem_default", fonte,
                      "tem_default precisa poder REPROVAR, não só ser lido")
        self.assertIn("default material ausente", fonte)


# ===========================================================================
# E — índice parcial e predicado
# ===========================================================================
class E_IndiceParcialEPredicado(unittest.TestCase):
    def _banco_com_indice(self, ddl_indice: str) -> Path:
        alvo = Path(mkdtemp()) / "l.sqlite"
        with sqlite3.connect(alvo) as c:
            c.execute(DDL_BOM)
            c.execute(ddl_indice)
        return alvo

    def test_indice_total_onde_o_contrato_espera_parcial_recusado(self):
        alvo = self._banco_com_indice(
            "CREATE UNIQUE INDEX idx_evidence_claim_unico "
            "ON evidence(claim_key, fencing_token)")
        with self.assertRaises(HarnessFailure) as e:
            EvidenceLedger(alvo)
        self.assertEqual(e.exception.classe, FailureClass.INFRASTRUCTURE_ERROR)

    def test_predicado_divergente_recusado(self):
        alvo = self._banco_com_indice(
            "CREATE UNIQUE INDEX idx_evidence_claim_unico "
            "ON evidence(claim_key, fencing_token) WHERE valid = 1")
        with self.assertRaises(HarnessFailure) as e:
            EvidenceLedger(alvo)
        self.assertEqual(e.exception.classe, FailureClass.INFRASTRUCTURE_ERROR)

    def test_predicado_esperado_aceito(self):
        alvo = self._banco_com_indice(
            "CREATE UNIQUE INDEX idx_evidence_claim_unico "
            "ON evidence(claim_key, fencing_token) WHERE claim_key IS NOT NULL")
        EvidenceLedger(alvo)                      # não pode levantar

    def test_indice_criado_pelo_harness_e_parcial(self):
        led = EvidenceLedger(Path(mkdtemp()) / "l.sqlite")
        with sqlite3.connect(led.path) as c:
            sql = c.execute("SELECT sql FROM sqlite_master "
                            "WHERE name='idx_evidence_claim_unico'").fetchone()[0]
        self.assertIn("WHERE", sql.upper())


# ===========================================================================
# F — HS-3 sem atacante hostil
# ===========================================================================
class F_ClaimRetomavelSemAtacante(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(mkdtemp())
        self.led = EvidenceLedger(self.raiz / "l.sqlite")

    def test_retry_terminaliza_apos_falha_transitoria(self):
        claim = self.led.acquire(_identidade(), run_id="r", worker_id="w",
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
            self.assertTrue(self.led.abandon(claim))
        finally:
            self.led._conn = original
        self.assertEqual(self.led.claims_ativos(), [])

    def test_falha_persistente_deixa_lease_finito_e_retomavel(self):
        ident = _identidade()
        claim = self.led.acquire(ident, run_id="r1", worker_id="w1",
                                 lease_seconds=1, wait_seconds=0.0)
        original = self.led._conn
        self.led._conn = lambda: (_ for _ in ()).throw(
            sqlite3.OperationalError("banco fora do ar"))
        try:
            self.led.abandon(claim)
        except HarnessFailure:
            pass
        finally:
            self.led._conn = original

        linha = self.led.claim_atual(ident)
        self.assertLess(float(linha["lease_until"]) - time.time(), 5,
                        "lease precisa ser FINITO")
        time.sleep(1.2)
        novo = self.led.acquire(ident, run_id="r2", worker_id="w2",
                                lease_seconds=60, wait_seconds=0.0)
        self.assertEqual(novo.outcome.value, "reclaimed_after_expiry")

    def test_nenhum_claim_irrecuperavel_apos_excecao_capturavel(self):
        class Explode(GateRunner):
            name = "explode"
            def execute(self, **kw): raise OSError("spawn falhou")

        run_gate_with_ledger(
            gate_index=1, argv=["x"], worktree=self.raiz, env={}, timeout=10,
            ledger=self.led, acceptance_id="P-A1", base_sha="s",
            candidate_sha=None, context_digest="c", env_fingerprint="e",
            production_digest="p", test_digest="t", run_id="r", worker_id="w",
            runner=Explode(), lease_seconds=60, wait_seconds=0.0)
        self.assertEqual(self.led.claims_ativos(apenas_vivos=True), [])


if __name__ == "__main__":
    unittest.main()
