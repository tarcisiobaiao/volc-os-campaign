"""FASE 0 da rodada final — Lotes A, B, C e o ratchet falso, em vermelho.

Cada teste afirma o comportamento correto e falha contra `e559986`. Os fatos que
eles reproduzem foram provados por três fontes independentes: Sol, Gemini e as
minhas próprias contraprovas.

⚠️ Nada aqui fecha G1b. Mesmo com a fronteira completa de insumos, sobra janela
entre a última medição e o `execve`, e entre o `execve` e a leitura de cada
arquivo pelo processo. Fechar isso exige sandbox ou snapshot imutável.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory, mkdtemp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _e2e_fixture import ContadorDeModelos, git, missao, repo_sintetico  # noqa: E402

from volc_agent_harness.v3.failures import FailureClass, HarnessFailure  # noqa: E402
from volc_agent_harness.v3.gate_runner import (  # noqa: E402
    GateRunner, run_gate_with_ledger,
)
from volc_agent_harness.v3.gate_resolution import resolve_mission_gates  # noqa: E402
from volc_agent_harness.v3.ledger import (  # noqa: E402
    ClaimOutcome, EvidenceLedger, GateIdentity,
)

FONTE = Path(__file__).resolve().parents[1] / "src" / "volc_agent_harness"

CATALOGO = {"catalog_version": 1, "gates": {
    "unit": {"kind": "pytest", "targets": ["backend/tests"], "description": "d"},
    "script": {"kind": "tracked_script",
               "script_path": "tools/agent-harness/alvo.py",
               "args": [], "description": "d"},
}}


def _repo_completo() -> Path:
    """Repo com teste, conftest, config, TS, manifests e script de catálogo."""

    raiz = Path(mkdtemp()) / "repo"
    raiz.mkdir()
    repo_sintetico(raiz, catalogo=CATALOGO)
    (raiz / "tools" / "agent-harness" / "alvo.py").write_text("raise SystemExit(0)\n")
    (raiz / "backend" / "tests" / "conftest.py").write_text("import os\n")
    (raiz / "pytest.ini").write_text("[pytest]\n")
    (raiz / "pyproject.toml").write_text("[project]\nname='x'\n")
    (raiz / "tsconfig.json").write_text('{"compilerOptions":{}}\n')
    (raiz / "src").mkdir()
    (raiz / "src" / "app.ts").write_text("export const a = 1;\n")
    (raiz / "backend" / "producao.py").write_text("VALOR = 1\n")
    (raiz / "package.json").write_text(json.dumps({"scripts": {"build": "tsc"}}))
    (raiz / "package-lock.json").write_text('{"lockfileVersion":3}')
    git(raiz, "add", "-A")
    subprocess.run(["git", "-C", str(raiz), "-c", "user.name=t",
                    "-c", "user.email=t@t", "commit", "-q", "-m", "base"],
                   check=True, capture_output=True)
    return raiz


# ===========================================================================
# LOTE A — fronteira completa de insumos
# ===========================================================================
class A1_FingerprintCanonicoDaArvore(unittest.TestCase):
    def test_modulo_de_fingerprint_existe_e_e_estavel(self):
        from volc_agent_harness.v3.fingerprint import tree_fingerprint

        a, b = _repo_completo(), _repo_completo()
        self.assertEqual(tree_fingerprint(a), tree_fingerprint(b),
                         "mesmo conteúdo em worktrees diferentes tem de dar igual")

    def test_qualquer_arquivo_rastreado_muda_o_fingerprint(self):
        from volc_agent_harness.v3.fingerprint import tree_fingerprint

        for rel, novo in (
            ("backend/tests/test_base.py", "def test_x():\n    assert False\n"),
            ("backend/tests/conftest.py", "import sys\n"),
            ("pytest.ini", "[pytest]\naddopts=-x\n"),
            ("pyproject.toml", "[project]\nname='y'\n"),
            ("backend/producao.py", "VALOR = 2\n"),
            ("tsconfig.json", '{"compilerOptions":{"strict":true}}\n'),
            ("src/app.ts", "export const a = 2;\n"),
            ("package.json", json.dumps({"scripts": {"build": "vite"}})),
            ("package-lock.json", '{"lockfileVersion":4}'),
            ("tools/agent-harness/alvo.py", "raise SystemExit(1)\n"),
        ):
            with self.subTest(arquivo=rel):
                raiz = _repo_completo()
                antes = tree_fingerprint(raiz)
                (raiz / rel).write_text(novo)
                self.assertNotEqual(antes, tree_fingerprint(raiz),
                                    f"{rel} não entrou no fingerprint")

    def test_modo_de_execucao_entra_no_fingerprint(self):
        from volc_agent_harness.v3.fingerprint import tree_fingerprint

        raiz = _repo_completo()
        alvo = raiz / "tools" / "agent-harness" / "alvo.py"
        antes = tree_fingerprint(raiz)
        alvo.chmod(0o755)
        self.assertNotEqual(antes, tree_fingerprint(raiz),
                            "bit de execução é material")

    def test_symlink_entra_pelo_destino_textual(self):
        from volc_agent_harness.v3.fingerprint import tree_fingerprint

        raiz = _repo_completo()
        (raiz / "atalho").symlink_to("backend/producao.py")
        git(raiz, "add", "-A")
        antes = tree_fingerprint(raiz)
        (raiz / "atalho").unlink()
        (raiz / "atalho").symlink_to("backend/tests/test_base.py")
        git(raiz, "add", "-A")
        self.assertNotEqual(antes, tree_fingerprint(raiz),
                            "destino do symlink é material")

    def test_symlink_que_escapa_e_bloqueado(self):
        from volc_agent_harness.v3.fingerprint import tree_fingerprint

        raiz = _repo_completo()
        (raiz / "fuga").symlink_to("../../etc/passwd")
        git(raiz, "add", "-A")
        with self.assertRaises(HarnessFailure) as e:
            tree_fingerprint(raiz)
        self.assertEqual(e.exception.classe, FailureClass.AUTHORIZATION_BLOCK)

    def test_runs_caches_e_artefatos_do_harness_ficam_fora(self):
        from volc_agent_harness.v3.fingerprint import tree_fingerprint

        raiz = _repo_completo()
        antes = tree_fingerprint(raiz)
        (raiz / "tools" / "agent-harness" / "runs").mkdir(parents=True, exist_ok=True)
        (raiz / "tools" / "agent-harness" / "runs" / "x.json").write_text("{}")
        (raiz / "tools" / "agent-harness" / "evidence-ledger.sqlite").write_bytes(b"x")
        (raiz / "__pycache__").mkdir(exist_ok=True)
        (raiz / "__pycache__" / "a.pyc").write_bytes(b"x")
        self.assertEqual(antes, tree_fingerprint(raiz),
                         "artefato do próprio harness não pode invalidar prova")

    def test_produced_autorizado_entra_mesmo_untracked(self):
        from volc_agent_harness.v3.fingerprint import tree_fingerprint

        raiz = _repo_completo()
        novo = raiz / "backend" / "tests" / "test_produzido.py"
        antes = tree_fingerprint(raiz, extra_paths=["backend/tests/test_produzido.py"])
        novo.write_text("def test_p():\n    assert True\n")
        self.assertNotEqual(
            antes, tree_fingerprint(raiz, extra_paths=["backend/tests/test_produzido.py"]),
            "produced declarado é observável pelo gate e precisa entrar")


class A2_BindingCobreATreeParaTodoTipo(unittest.TestCase):
    def test_tipos_sem_insumo_proprio_ganham_digest_da_arvore(self):
        raiz = _repo_completo()
        for spec in ({"kind": "pytest", "targets": ["backend/tests"]},
                     {"kind": "unittest", "start_dir": "backend"},
                     {"kind": "catalog", "gate_id": "unit"},
                     {"kind": "catalog", "gate_id": "script"}):
            with self.subTest(spec=spec.get("kind")):
                g = resolve_mission_gates(
                    gates=[spec], tree=raiz,
                    toolchain={"python": sys.executable, "git": "/usr/bin/git"})[0]
                self.assertTrue(g.binding.tree_digest,
                                "todo gate precisa vincular a árvore relevante")


class A3_RevalidacaoNosQuatroPontos(unittest.TestCase):
    """Antes do acquire, depois da espera, antes do reuse e antes do execute."""

    def setUp(self):
        self.raiz = _repo_completo()
        self.led = EvidenceLedger(Path(mkdtemp()) / "l.sqlite")
        self.gate = resolve_mission_gates(
            gates=[{"kind": "catalog", "gate_id": "script"}], tree=self.raiz,
            toolchain={"python": sys.executable, "git": "/usr/bin/git"})[0]

    def _comum(self, **over):
        base = dict(
            gate_index=1, argv=self.gate.argv, worktree=self.raiz, env={},
            timeout=30, ledger=self.led, acceptance_id="P-A1", base_sha="s",
            candidate_sha=None, context_digest="c", env_fingerprint="e",
            production_digest="p", test_digest="t", gate=self.gate,
            lease_seconds=60, wait_seconds=10.0,
        )
        base.update(over)
        return base

    def test_runner_recebe_o_gate_verificavel_e_nao_so_uma_string(self):
        import inspect
        assinatura = inspect.signature(run_gate_with_ledger)
        self.assertIn("gate", assinatura.parameters,
                      "sem o ResolvedGate não há como revalidar depois da espera")

    def test_alteracao_antes_do_acquire_recusa(self):
        (self.raiz / "tools" / "agent-harness" / "alvo.py").write_text("raise SystemExit(1)\n")
        with self.assertRaises(HarnessFailure) as e:
            run_gate_with_ledger(**self._comum(run_id="r", worker_id="w"))
        self.assertEqual(e.exception.classe, FailureClass.STALE_INPUT)

    def _durante_a_espera(self, mutacao, estado_a: str):
        """A segura o claim; o teste altera; A conclui; B acorda e revalida."""

        ident = GateIdentity.for_gate(
            acceptance_id="P-A1", gate_index=1, argv=self.gate.argv,
            context_digest="c", production_digest="p", test_digest="t",
            env_fingerprint="e", binding_digest=self.gate.binding.digest())
        claim_a = self.led.acquire(ident, run_id="ra", worker_id="wa",
                                   lease_seconds=60, wait_seconds=0.0)
        resultado: list = []
        erro: list = []

        class Conta(GateRunner):
            name = "conta"
            def __init__(self): self.n = 0
            def execute(self, **kw): self.n += 1; return 0, "", ""

        conta = Conta()

        def consumidor_b():
            try:
                resultado.append(run_gate_with_ledger(
                    **self._comum(run_id="rb", worker_id="wb", runner=conta)))
            except HarnessFailure as exc:
                erro.append(exc)

        fio = threading.Thread(target=consumidor_b)
        fio.start()
        time.sleep(0.4)                       # B entra na espera
        mutacao(self.raiz)                    # C: altera durante a espera
        self.led.complete(claim_a, state=estado_a, base_sha="s", run_id="ra",
                          command="c", production_digest="p", test_digest="t",
                          exit_code=0 if estado_a == "green" else 1)
        fio.join(timeout=60)
        return resultado, erro, conta

    def test_alteracao_durante_espera_recusa_o_reuso(self):
        res, erro, conta = self._durante_a_espera(
            lambda r: (r / "backend" / "tests" / "test_base.py").write_text("x=1\n"),
            "green")
        self.assertTrue(erro, f"B reutilizou GREEN sobre conteúdo alterado: {res}")
        self.assertEqual(erro[0].classe, FailureClass.STALE_INPUT)
        self.assertEqual(conta.n, 0)

    def test_alteracao_durante_espera_recusa_a_execucao(self):
        res, erro, conta = self._durante_a_espera(
            lambda r: (r / "backend" / "tests" / "test_base.py").write_text("y=2\n"),
            "red")
        self.assertTrue(erro, f"B executou sob identidade antiga: {res}")
        self.assertEqual(erro[0].classe, FailureClass.STALE_INPUT)
        self.assertEqual(conta.n, 0, "nada pode ter rodado sob o vínculo velho")

    def test_claim_nao_fica_running_quando_o_vinculo_expira(self):
        self._durante_a_espera(
            lambda r: (r / "pytest.ini").write_text("[pytest]\naddopts=-x\n"), "red")
        self.assertEqual(self.led.claims_ativos(), [],
                         "claim adquirido e abandonado por STALE precisa fechar")

    def test_todas_as_oito_alteracoes_invalidam(self):
        alvos = {
            "teste": ("backend/tests/test_base.py", "def t():\n    pass\n"),
            "conftest": ("backend/tests/conftest.py", "import json\n"),
            "pytest.ini": ("pytest.ini", "[pytest]\naddopts=-q\n"),
            "pyproject": ("pyproject.toml", "[project]\nname='z'\n"),
            "producao": ("backend/producao.py", "VALOR = 9\n"),
            "tsconfig": ("tsconfig.json", '{"compilerOptions":{"strict":1}}\n'),
            "typescript": ("src/app.ts", "export const a = 3;\n"),
            "package": ("package.json", json.dumps({"scripts": {"build": "x"}})),
            "lockfile": ("package-lock.json", '{"lockfileVersion":9}'),
            "script": ("tools/agent-harness/alvo.py", "raise SystemExit(2)\n"),
        }
        for nome, (rel, novo) in alvos.items():
            with self.subTest(alteracao=nome):
                self.setUp()
                res, erro, conta = self._durante_a_espera(
                    lambda r, rel=rel, novo=novo: (r / rel).write_text(novo), "green")
                self.assertTrue(erro, f"{nome} não invalidou: {res}")
                self.assertEqual(erro[0].classe, FailureClass.STALE_INPUT)


class A4_BaselineEColetaAtravessamAMesmaFronteira(unittest.TestCase):
    def test_baseline_revalida_antes_de_entrar_no_ledger(self):
        import inspect
        import volc_agent_harness.mission as m

        fonte = inspect.getsource(m._run_implementation_mission)
        i_base = fonte.index('kind_prefix="baseline_gate"')
        # A revalidação mora DENTRO de `run_gate_with_ledger` e é disparada por
        # receber o gate verificável. Exigir a chamada literal aqui mediria o
        # lugar errado: o que importa é que o baseline não entre sem o gate.
        self.assertIn("gate=gate", fonte[:i_base],
                      "baseline entra no ledger sem o gate verificável")

    def test_coleta_revalida_antes_de_entrar_no_ledger(self):
        import inspect
        from volc_agent_harness.v3 import gate_compiler

        fonte = inspect.getsource(gate_compiler.assert_pytest_collects)
        self.assertIn("gate=", fonte,
                      "a coleta precisa passar o gate verificável ao runner")


# ===========================================================================
# LOTE B — autoridade do resultado
# ===========================================================================
class B5_HeartbeatRobusto(unittest.TestCase):
    def test_lease_efetivo_cobre_o_timeout_do_gate(self):
        """Estratégia A: lease >= timeout + margem, calculado pelo runtime."""

        from volc_agent_harness.v3.gate_runner import lease_efetivo

        self.assertGreaterEqual(lease_efetivo(lease_seconds=1, timeout=600), 600)

    def test_runner_e_cancelavel(self):
        from volc_agent_harness.v3.gate_runner import GateRunner, LocalRunner

        self.assertTrue(hasattr(GateRunner, "cancel"))
        self.assertTrue(hasattr(LocalRunner, "cancel"))

    def test_falha_transitoria_isolada_nao_mata_o_heartbeat(self):
        """A tolerância é medida em TEMPO DE LEASE, não em N tentativas.

        Testado em isolamento de propósito: com `lease_efetivo` cobrindo
        `timeout + margem`, um teste ponta a ponta teria intervalo de dezenas de
        segundos e não exerceria a lógica de tolerância nenhuma vez.
        """

        from volc_agent_harness.v3.gate_runner import _Heartbeat
        from volc_agent_harness.v3.ledger import Claim, ClaimOutcome, GateIdentity

        tentativas = {"n": 0}

        class LedgerInstavel:
            def heartbeat(self, claim, **kw):
                tentativas["n"] += 1
                if tentativas["n"] in (1, 3):
                    raise sqlite3.OperationalError("database is locked")
                return True

        ident = GateIdentity(acceptance_id="A", kind="gate_1", context_digest="c",
                             production_digest="p", test_digest="t",
                             command_digest="cmd", env_fingerprint="e")
        claim = Claim(ident, ClaimOutcome.ACQUIRED, "owner", 1)
        with _Heartbeat(LedgerInstavel(), claim, lease_seconds=4) as batida:
            time.sleep(3.2)
            perdeu = batida.perdeu.is_set()
        self.assertGreaterEqual(tentativas["n"], 3, "o heartbeat parou de tentar")
        self.assertFalse(perdeu, "falha transitória isolada matou a renovação")

    def test_falha_persistente_desiste_e_cancela_o_processo(self):
        from volc_agent_harness.v3.gate_runner import GateRunner, _Heartbeat
        from volc_agent_harness.v3.ledger import Claim, ClaimOutcome, GateIdentity

        class SempreQuebrado:
            def heartbeat(self, claim, **kw):
                raise sqlite3.OperationalError("locked")

        class Cancelavel(GateRunner):
            name = "cancelavel"
            def __init__(self): self.cancelado = False
            def execute(self, **kw): return 0, "", ""
            def cancel(self): self.cancelado = True

        ident = GateIdentity(acceptance_id="A", kind="gate_1", context_digest="c",
                             production_digest="p", test_digest="t",
                             command_digest="cmd", env_fingerprint="e")
        claim = Claim(ident, ClaimOutcome.ACQUIRED, "owner", 1)
        runner = Cancelavel()
        with _Heartbeat(SempreQuebrado(), claim, lease_seconds=2,
                        runner=runner) as batida:
            time.sleep(3.0)
            perdeu = batida.perdeu.is_set()
        self.assertTrue(perdeu, "falha persistente precisa sinalizar lease perdido")
        self.assertTrue(runner.cancelado,
                        "perder o lease precisa ENCERRAR o processo")

    def test_uma_execucao_fisica_sob_falhas_transitorias_injetadas(self):
        raiz = Path(mkdtemp())
        led = EvidenceLedger(raiz / "l.sqlite")
        original = led.heartbeat
        led.heartbeat = lambda c, **kw: (_ for _ in ()).throw(
            sqlite3.OperationalError("locked")) if c.fencing_token == 1 else original(c, **kw)

        class Contador(GateRunner):
            name = "contador"
            def __init__(self):
                self.trava = threading.Lock(); self.ativos = 0; self.maximo = 0
                self.liberar = threading.Event()
            def execute(self, **kw):
                with self.trava:
                    self.ativos += 1; self.maximo = max(self.maximo, self.ativos)
                self.liberar.wait(4)
                with self.trava: self.ativos -= 1
                return 0, "ok", ""

        runner = Contador()
        comum = dict(gate_index=1, argv=["mesmo"], worktree=raiz, env={}, timeout=6,
                     ledger=led, acceptance_id="P-A1", base_sha="s",
                     candidate_sha=None, context_digest="c", env_fingerprint="e",
                     production_digest="p", test_digest="t", runner=runner,
                     lease_seconds=1, wait_seconds=0.0)
        saidas: list = []
        f1 = threading.Thread(target=lambda: saidas.append(
            run_gate_with_ledger(**comum, run_id="r1", worker_id="w1")))
        f1.start(); time.sleep(1.4)
        saidas.append(run_gate_with_ledger(**comum, run_id="r2", worker_id="w2"))
        runner.liberar.set(); f1.join(timeout=30)
        self.assertEqual(runner.maximo, 1,
                         "falha transitória do heartbeat abriu segunda execução")
        self.assertFalse(any(s.ok and s.evidence_id is None for s in saidas))

    def test_quem_perde_o_lease_tem_o_subprocesso_encerrado(self):
        from volc_agent_harness.v3.gate_runner import _Heartbeat
        import inspect
        fonte = inspect.getsource(_Heartbeat)
        self.assertIn("cancel(", fonte,
                      "perder o lease precisa ENCERRAR o processo, não só sinalizar")


class B6_BaselinePropagaAutoridade(unittest.TestCase):
    def test_baseline_sem_evidencia_nao_e_verde(self):
        from volc_agent_harness.v3.baseline import (
            BaselineRecord, assert_baseline_is_green,
        )
        from volc_agent_harness.v3.gate_runner import GateOutcome

        o = GateOutcome(gate_index=1, argv=["g"], exit_code=0, stdout="", stderr="",
                        duration_s=0, execution_mode="abandoned",
                        status="infrastructure", evidence_id=None)
        r = BaselineRecord.from_outcome(o)
        with self.assertRaises(HarnessFailure) as e:
            assert_baseline_is_green([r])
        self.assertIn(e.exception.classe,
                      {FailureClass.BASELINE_ERROR, FailureClass.INFRASTRUCTURE_ERROR})

    def test_baseline_verde_exige_ok_status_e_evidencia(self):
        from volc_agent_harness.v3.baseline import (
            BaselineRecord, assert_baseline_is_green,
        )
        from volc_agent_harness.v3.gate_runner import GateOutcome

        bom = GateOutcome(gate_index=1, argv=["g"], exit_code=0, stdout="", stderr="",
                          duration_s=0, execution_mode="executed", status="green",
                          evidence_id=7)
        assert_baseline_is_green([BaselineRecord.from_outcome(bom)])


class B7_CwdHonrado(unittest.TestCase):
    def test_execucao_usa_worktree_mais_cwd_rel(self):
        raiz = Path(mkdtemp())
        (raiz / "sub").mkdir()
        led = EvidenceLedger(raiz / "l.sqlite")
        visto: list[Path] = []

        class Captura(GateRunner):
            name = "captura"
            def execute(self, *, argv, cwd, env, timeout):
                visto.append(Path(cwd)); return 0, "", ""

        saida = run_gate_with_ledger(
            gate_index=1, argv=["x"], worktree=raiz, env={}, timeout=10, ledger=led,
            acceptance_id="P-A1", base_sha="s", candidate_sha=None,
            context_digest="c", env_fingerprint="e", production_digest="p",
            test_digest="t", run_id="r", worker_id="w", runner=Captura(),
            cwd_rel="sub", lease_seconds=60, wait_seconds=0.0)
        # `.resolve()` dos dois lados: o runtime canonicaliza para poder conferir
        # contenção, e no macOS /var é symlink de /private/var.
        self.assertEqual(visto[0].resolve(), (raiz / "sub").resolve())
        self.assertTrue(saida.ok)

    def test_cwd_rel_inexistente_falha_antes_de_executar(self):
        raiz = Path(mkdtemp())
        led = EvidenceLedger(raiz / "l.sqlite")

        class Nunca(GateRunner):
            name = "nunca"
            def execute(self, **kw): raise AssertionError("não podia executar")

        with self.assertRaises(HarnessFailure):
            run_gate_with_ledger(
                gate_index=1, argv=["x"], worktree=raiz, env={}, timeout=10,
                ledger=led, acceptance_id="P-A1", base_sha="s", candidate_sha=None,
                context_digest="c", env_fingerprint="e", production_digest="p",
                test_digest="t", run_id="r", worker_id="w", runner=Nunca(),
                cwd_rel="nao/existe", lease_seconds=60, wait_seconds=0.0)

    def test_evidencia_registra_cwd_relativo_e_efetivo(self):
        raiz = Path(mkdtemp())
        (raiz / "sub").mkdir()
        led = EvidenceLedger(raiz / "l.sqlite")

        class Ok(GateRunner):
            name = "ok"
            def execute(self, **kw): return 0, "", ""

        run_gate_with_ledger(
            gate_index=1, argv=["x"], worktree=raiz, env={}, timeout=10, ledger=led,
            acceptance_id="P-A1", base_sha="s", candidate_sha=None,
            context_digest="c", env_fingerprint="e", production_digest="p",
            test_digest="t", run_id="r", worker_id="w", runner=Ok(),
            cwd_rel="sub", lease_seconds=60, wait_seconds=0.0)
        linha = led.evidencias()[0]
        self.assertEqual(linha["cwd"], "sub")
        contagens = json.loads(linha["counts_json"])
        self.assertEqual(Path(contagens["cwd_efetivo"]).resolve(),
                         (raiz / "sub").resolve())


class B8_CompleteSemFallbackPermissivo(unittest.TestCase):
    def setUp(self):
        self.led = EvidenceLedger(Path(mkdtemp()) / "l.sqlite")
        self.ident = GateIdentity(acceptance_id="P-A1", kind="gate_1",
                                  context_digest="c", production_digest="p",
                                  test_digest="t", command_digest="cmd",
                                  env_fingerprint="e")
        self.args = dict(state="green", base_sha="s", run_id="r", command="c",
                         production_digest="p", test_digest="t", exit_code=0)

    def test_duplicado_identico_devolve_a_mesma_evidencia(self):
        c = self.led.acquire(self.ident, run_id="r", worker_id="w",
                             lease_seconds=120, wait_seconds=0.0)
        a = self.led.complete(c, **self.args)
        b = self.led.complete(c, **self.args)
        self.assertEqual(a, b)
        self.assertEqual(len(self.led.evidencias()), 1)

    def test_duplicado_divergente_falha_e_nunca_vira_verde(self):
        c = self.led.acquire(self.ident, run_id="r", worker_id="w",
                             lease_seconds=120, wait_seconds=0.0)
        self.led.complete(c, **{**self.args, "state": "red", "exit_code": 1})
        with self.assertRaises(HarnessFailure) as e:
            self.led.complete(c, **self.args)
        self.assertEqual(e.exception.classe, FailureClass.INFRASTRUCTURE_ERROR)

    def test_evidencia_vermelha_nao_satisfaz_conclusao_verde(self):
        import sqlite3 as s3
        c = self.led.acquire(self.ident, run_id="r", worker_id="w",
                             lease_seconds=120, wait_seconds=0.0)
        conn = s3.connect(self.led.path)
        with conn:
            conn.execute(
                "INSERT INTO evidence(acceptance_id,kind,base_sha,input_digest,"
                "production_digest,test_digest,command,exit_code,counts_json,valid,"
                "claim_key,fencing_token,run_id,created_at) "
                "VALUES('P-A1','gate_1','s','d','p','t','c',1,'{}',1,?,?,'r','x')",
                (self.ident.logical_key, c.fencing_token))
        conn.close()
        with self.assertRaises(HarnessFailure):
            self.led.complete(c, **self.args)

    def test_claim_sempre_terminal_depois_de_excecao(self):
        class Explode(GateRunner):
            name = "explode"
            def execute(self, **kw): raise OSError("spawn falhou")

        raiz = Path(mkdtemp())
        led = EvidenceLedger(raiz / "l.sqlite")
        run_gate_with_ledger(
            gate_index=1, argv=["x"], worktree=raiz, env={}, timeout=10, ledger=led,
            acceptance_id="P-A1", base_sha="s", candidate_sha=None,
            context_digest="c", env_fingerprint="e", production_digest="p",
            test_digest="t", run_id="r", worker_id="w", runner=Explode(),
            lease_seconds=60, wait_seconds=0.0)
        self.assertEqual(led.claims_ativos(), [])


# ===========================================================================
# LOTE C — migração completa das DUAS tabelas
# ===========================================================================
class C_MigracaoDasDuasTabelas(unittest.TestCase):
    def test_obrigatorias_cobrem_todas_as_colunas_usadas(self):
        from volc_agent_harness.v3.ledger import OBRIGATORIAS

        por_tabela = {t: set(c) for t, c in OBRIGATORIAS}
        self.assertIn("execution_claim", por_tabela,
                      "execution_claim precisa de obrigatórias próprias")
        usadas_evidence = {
            "acceptance_id", "kind", "base_sha", "candidate_sha", "input_digest",
            "production_digest", "test_digest", "command", "cwd", "env_fingerprint",
            "context_digest", "exit_code", "counts_json", "valid", "claim_key",
            "fencing_token", "run_id", "created_at",
        }
        faltando = usadas_evidence - por_tabela.get("evidence", set())
        self.assertEqual(faltando, set(), f"evidence sem conferir: {sorted(faltando)}")
        usadas_claim = {
            "logical_key", "contract_version", "acceptance_id", "kind",
            "input_digest", "owner_token", "fencing_token", "state", "claimed_at",
            "heartbeat_at", "lease_until", "completed_at", "run_id", "worker_id",
            "evidence_id", "owner_pid",
        }
        faltando = usadas_claim - por_tabela.get("execution_claim", set())
        self.assertEqual(faltando, set(),
                         f"execution_claim sem conferir: {sorted(faltando)}")

    def test_execution_claim_legada_e_migrada(self):
        alvo = Path(mkdtemp()) / "l.sqlite"
        with sqlite3.connect(alvo) as c:
            c.executescript("""
              CREATE TABLE evidence (id INTEGER PRIMARY KEY AUTOINCREMENT,
                acceptance_id TEXT NOT NULL, kind TEXT NOT NULL,
                input_digest TEXT NOT NULL, run_id TEXT NOT NULL);
              CREATE TABLE execution_claim (logical_key TEXT PRIMARY KEY,
                state TEXT NOT NULL);
            """)
            c.execute("INSERT INTO execution_claim VALUES('antigo','green')")
        led = EvidenceLedger(alvo)
        ident = GateIdentity(acceptance_id="P-A1", kind="gate_1", context_digest="c",
                             production_digest="p", test_digest="t",
                             command_digest="cmd", env_fingerprint="e")
        claim = led.acquire(ident, run_id="r", worker_id="w", lease_seconds=60,
                            wait_seconds=0.0)
        self.assertEqual(claim.outcome, ClaimOutcome.ACQUIRED)
        with sqlite3.connect(alvo) as c:
            n = c.execute("SELECT COUNT(*) FROM execution_claim "
                          "WHERE logical_key='antigo'").fetchone()[0]
        self.assertEqual(n, 1, "linha legada precisa sobreviver")

    def test_primeiro_uso_funciona_depois_da_migracao(self):
        alvo = Path(mkdtemp()) / "l.sqlite"
        with sqlite3.connect(alvo) as c:
            c.executescript("""CREATE TABLE evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                acceptance_id TEXT NOT NULL, kind TEXT NOT NULL,
                input_digest TEXT NOT NULL, run_id TEXT NOT NULL);""")
        led = EvidenceLedger(alvo)
        led.record(acceptance_id="A", kind="gate_1", base_sha="s", run_id="r",
                   command="c", production_digest="p", test_digest="t")
        self.assertEqual(len(led.evidencias()), 1)

    def test_schema_irrecuperavel_falha_sem_apagar(self):
        alvo = Path(mkdtemp()) / "l.sqlite"
        with sqlite3.connect(alvo) as c:
            c.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY, lixo TEXT)")
            c.execute("INSERT INTO evidence(lixo) VALUES('preserve-me')")
        with self.assertRaises(HarnessFailure) as e:
            EvidenceLedger(alvo)
        self.assertEqual(e.exception.classe, FailureClass.INFRASTRUCTURE_ERROR)
        with sqlite3.connect(alvo) as c:
            self.assertEqual(
                c.execute("SELECT lixo FROM evidence").fetchone()[0], "preserve-me")

    def test_duas_inicializacoes_concorrentes_sobre_legado(self):
        alvo = Path(mkdtemp()) / "l.sqlite"
        with sqlite3.connect(alvo) as c:
            c.executescript("""CREATE TABLE evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                acceptance_id TEXT NOT NULL, kind TEXT NOT NULL,
                input_digest TEXT NOT NULL, run_id TEXT NOT NULL);""")
        barreira = threading.Barrier(2)
        erros: list[BaseException] = []

        def abrir():
            try:
                barreira.wait(timeout=10)
                EvidenceLedger(alvo)
            except BaseException as exc:      # pragma: no cover
                erros.append(exc)

        fios = [threading.Thread(target=abrir) for _ in range(2)]
        for f in fios:
            f.start()
        for f in fios:
            f.join(timeout=30)
        self.assertEqual(erros, [])


# ===========================================================================
# BL-11 — o ratchet de disk-full que passava por construção
# ===========================================================================
class BL11_DiskFullPersistente(unittest.TestCase):
    """O mock antigo falhava só na primeira escrita e deixava failure.json passar."""

    def _rodar(self, falhar_em) -> tuple[int, str, Path]:
        from volc_agent_harness.v3.run_artifacts import RunArtifacts
        import volc_agent_harness.mission as mm
        from volc_agent_harness.cli import main as cli_main

        from _e2e_fixture import escreve_teste_novo

        repo = repo_sintetico(Path(mkdtemp()))
        contador = ContadorDeModelos(escrita=escreve_teste_novo)
        original_adapter, original_escrever = mm.adapter_for, RunArtifacts.escrever

        def _escrever(self, nome, conteudo):
            if falhar_em(nome):
                raise OSError(28, "No space left on device")
            return original_escrever(self, nome, conteudo)

        mm.adapter_for = contador.adapter_for
        RunArtifacts.escrever = _escrever
        try:
            alvo = missao(repo, gates=[{"kind": "catalog", "gate_id": "diff-limpo"}])
            buffer = StringIO()
            with redirect_stdout(buffer):
                codigo = cli_main(["--mission", str(alvo), "--repo", str(repo)])
        finally:
            RunArtifacts.escrever = original_escrever
            mm.adapter_for = original_adapter
        return codigo, buffer.getvalue(), repo

    def test_metadata_existe_e_a_escrita_seguinte_falha(self):
        codigo, saida, repo = self._rodar(lambda nome: nome != "metadata.json")
        runs = sorted((repo / "tools" / "agent-harness" / "runs").iterdir())
        self.assertEqual(codigo, 4, saida)
        self.assertTrue((runs[-1] / "metadata.json").is_file(),
                        "metadata precisa existir neste cenário")
        self.assertIn("INFRASTRUCTURE_ERROR", saida)

    def test_disco_cheio_persistente_ainda_sai_tipado_sem_inventar_artefato(self):
        codigo, saida, repo = self._rodar(lambda nome: True)
        self.assertEqual(codigo, 4, saida)
        self.assertRegex(saida, r"\[[A-Z_]+\]")
        self.assertNotIn("artefato:", saida,
                         "sem failure.json no disco, não se anuncia artefato")


if __name__ == "__main__":
    unittest.main()
