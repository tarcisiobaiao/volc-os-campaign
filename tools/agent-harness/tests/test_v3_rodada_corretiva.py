"""FASE 0 da rodada corretiva — os nove bloqueadores, em vermelho.

Cada teste aqui reproduz um fato que o Sol ou a lente de completude provou
executando, e afirma o comportamento correto. Todos falham contra `01e5cf2`,
e é isso que os torna prova em vez de descrição.

⚠️ NADA aqui fecha G1b. A coleta do pytest continua importando `conftest.py` e
módulos de teste com os privilégios do harness depois destas correções; o que
muda é que ela passa a ser reivindicada, medida e auditada — contabilidade, não
contenção.
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
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _e2e_fixture import ContadorDeModelos, git, missao, repo_sintetico  # noqa: E402

import volc_agent_harness.mission as mission_mod  # noqa: E402
from volc_agent_harness.v3.failures import FailureClass, HarnessFailure  # noqa: E402
from volc_agent_harness.v3.gate_runner import (  # noqa: E402
    GateRunner, run_gate_with_ledger,
)
from volc_agent_harness.v3.ledger import (  # noqa: E402
    ClaimOutcome, EvidenceLedger, GateIdentity,
)

FONTE = Path(__file__).resolve().parents[1] / "src" / "volc_agent_harness"


def _le_argv_de_dicionario(arquivo: Path) -> list[int]:
    """Linhas que leem ``argv`` de um dicionário — o padrão da missão crua.

    ``gate_plan["gates"][i]["argv"]`` é o argv CONSTRUÍDO pelo compilador e é
    legítimo. ``BaselineRecord.argv`` também: é atributo de um registro, não
    leitura da missão. O padrão que não pode existir é ``.get("argv", ...)`` —
    ele só faz sentido sobre o dicionário BRUTO da missão, onde o campo pode
    faltar, e é exatamente por poder faltar que a guarda virava no-op.

    A outra metade do invariante (``mission.gates`` só como entrada do
    resolvedor) já é provada em `test_v3_g1a_contraprovas`.
    """

    import ast

    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    return [
        no.lineno for no in ast.walk(arvore)
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
        and no.func.attr == "get" and no.args
        and isinstance(no.args[0], ast.Constant) and no.args[0].value == "argv"
    ]


def _identidade(**over) -> GateIdentity:
    campos = dict(acceptance_id="P-A1", kind="gate_1", context_digest="c",
                  production_digest="p", test_digest="t", command_digest="cmd",
                  env_fingerprint="e")
    campos.update(over)
    return GateIdentity(**campos)


# ===========================================================================
# 1 — `volc-harness compile` neutralizando a guarda com gate tipado
# ===========================================================================
class B1_CompileNaoNeutralizaAGuarda(unittest.TestCase):
    """`gate.get("argv", [])` com gate tipado devolve `[]`: guarda no-op.

    É o mesmo defeito que motivou a missão inteira — proteção escrita que o
    caminho produtivo não atravessa — reintroduzido no entrypoint `compile`.
    """

    def test_prewriter_nao_le_argv_da_missao(self):
        """Por AST, não por busca de texto.

        O comentário que EXPLICA o defeito antigo cita `gate.get("argv", [])`
        literalmente, e deve continuar citando. Uma prova que casa string não
        distingue a explicação do defeito — e obrigar o código a não falar sobre
        o próprio erro seria a régua errada.
        """

        ofensores = _le_argv_de_dicionario(FONTE / "v3" / "pipeline.py")
        self.assertEqual(ofensores, [],
                         "o prewriter ainda lê argv de dicionário de missão")

    def test_guarda_do_compile_recebe_argv_resolvido_e_nao_vazio(self):
        import ast
        import inspect

        from volc_agent_harness.v3 import pipeline

        fonte = inspect.getsource(pipeline.prewriter_phase)
        self.assertIn("assert_no_destructive_intent(", fonte)
        self.assertIn("assert_gate_executable_is_allowed(", fonte)
        # A guarda precisa vir DEPOIS da compilação: antes dela não existe argv.
        self.assertLess(fonte.index("compile_mission("),
                        fonte.index("assert_no_destructive_intent("))
        ast.parse(fonte)

    def test_compile_produz_o_mesmo_plano_resolvido_que_o_runtime(self):
        from volc_agent_harness.cli import compile_only

        with TemporaryDirectory() as tmp:
            repo = repo_sintetico(Path(tmp))
            alvo = missao(repo, mode="read_only", commit_message=None,
                          gates=[{"kind": "catalog", "gate_id": "backend-unit"}],
                          workers=[
                              {"id": "inv-a", "provider": "codex", "model": "gpt-5.5",
                               "lens": "x", "allowed_paths": ["backend"]},
                              {"id": "inv-b", "provider": "codex", "model": "gpt-5.5",
                               "lens": "y", "allowed_paths": ["backend"]},
                          ])
            saida = StringIO()
            with redirect_stdout(saida):
                codigo = compile_only([
                    "--mission", str(alvo), "--repo", str(repo),
                    "--out", str(repo / "tools" / "agent-harness" / "runs" / "chk"),
                ])
            self.assertEqual(codigo, 0, saida.getvalue())
            plano = json.loads(
                (repo / "tools" / "agent-harness" / "runs" / "chk"
                 / "gate-plan.json").read_text(encoding="utf-8"))
        gate = plano["gates"][0]
        for chave in ("kind", "gate_id", "binding_digest", "argv",
                      "runnable_before_writer"):
            self.assertIn(chave, gate, f"plano do compile sem {chave}")
        self.assertEqual(gate["gate_id"], "backend-unit")

    def test_gate_nao_tipado_falha_no_compile_antes_de_qualquer_execucao(self):
        from volc_agent_harness.cli import compile_only

        with TemporaryDirectory() as tmp:
            repo = repo_sintetico(Path(tmp))
            alvo = repo / "m.json"
            bruto = json.loads(
                missao(repo, mode="read_only", commit_message=None,
                       workers=[
                           {"id": "inv-a", "provider": "codex", "model": "gpt-5.5",
                            "lens": "x", "allowed_paths": ["backend"]},
                           {"id": "inv-b", "provider": "codex", "model": "gpt-5.5",
                            "lens": "y", "allowed_paths": ["backend"]},
                       ]).read_text())
            bruto["gates"] = [{"argv": ["python3", "-c", "import os"]}]
            alvo.write_text(json.dumps(bruto), encoding="utf-8")
            saida = StringIO()
            with redirect_stdout(saida):
                codigo = compile_only([
                    "--mission", str(alvo), "--repo", str(repo),
                    "--out", str(repo / "tools" / "agent-harness" / "runs" / "chk"),
                ])
        self.assertEqual(codigo, 3, saida.getvalue())
        self.assertIn("SPEC_ERROR", saida.getvalue())


# ===========================================================================
# 2 — coleta pytest executando código sem claim/ledger
# ===========================================================================
class B2_ColetaPassaPeloLedger(unittest.TestCase):
    """Coleta importa `conftest.py`: é execução de código, não leitura."""

    def test_assert_pytest_collects_nao_usa_subprocess_direto(self):
        import ast
        import inspect

        from volc_agent_harness.v3 import gate_compiler

        fonte = inspect.getsource(gate_compiler.assert_pytest_collects)
        arvore = ast.parse(fonte.lstrip())
        diretos = [
            no.lineno for no in ast.walk(arvore)
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
            and no.func.attr == "run" and isinstance(no.func.value, ast.Name)
            and no.func.value.id == "subprocess"
        ]
        self.assertEqual(diretos, [],
                         "a coleta ainda cria subprocesso fora do ledger")

    def test_coleta_exige_contexto_de_ledger(self):
        from volc_agent_harness.v3.gate_compiler import (
            ColetaContexto, assert_pytest_collects,
        )

        self.assertIn("ctx", assert_pytest_collects.__code__.co_varnames)
        self.assertIn("ledger", ColetaContexto.__dataclass_fields__)

    def test_coleta_grava_evidencia_com_kind_proprio(self):
        """Comportamental: a coleta roda, e deixa rastro com identidade própria."""

        from volc_agent_harness.v3.gate_compiler import (
            ColetaContexto, assert_pytest_collects,
        )

        class _GateFalso:
            index = 1
            kind = "pytest"
            binding = None
            collect_only_argv = [sys.executable, "-c",
                                 "print('3 tests collected in 0.01s')"]

        with TemporaryDirectory() as tmp:
            led = EvidenceLedger(Path(tmp) / "l.sqlite")
            ctx = ColetaContexto(
                ledger=led, acceptance_id="P-A1", base_sha="s",
                context_digest="c", env_fingerprint="e", production_digest="p",
                test_digest="t", run_id="r", worker_id="w")
            contados = assert_pytest_collects(
                _GateFalso(), tree=Path(tmp), ctx=ctx, env={})
            self.assertEqual(contados, 3)
            linhas = led.evidencias()
            self.assertEqual(len(linhas), 1)
            self.assertEqual(linhas[0]["kind"], "collect_gate_1")

    def test_coleta_reutilizada_preserva_a_contagem(self):
        """No reuso o stdout é vazio; a contagem tem de vir do registro."""

        from volc_agent_harness.v3.gate_compiler import (
            ColetaContexto, assert_pytest_collects,
        )

        class _GateFalso:
            index = 1
            kind = "pytest"
            binding = None
            collect_only_argv = [sys.executable, "-c",
                                 "print('7 tests collected in 0.02s')"]

        with TemporaryDirectory() as tmp:
            led = EvidenceLedger(Path(tmp) / "l.sqlite")
            ctx = ColetaContexto(
                ledger=led, acceptance_id="P-A1", base_sha="s",
                context_digest="c", env_fingerprint="e", production_digest="p",
                test_digest="t", run_id="r", worker_id="w")
            primeiro = assert_pytest_collects(_GateFalso(), tree=Path(tmp),
                                              ctx=ctx, env={})
            segundo = assert_pytest_collects(_GateFalso(), tree=Path(tmp),
                                             ctx=ctx, env={})
            self.assertEqual((primeiro, segundo), (7, 7))
            self.assertEqual(len(led.evidencias()), 1,
                             "a segunda coleta não podia rodar de novo")


# ===========================================================================
# 3 — runner bloqueado por tempo maior que o lease
# ===========================================================================
class _RunnerLento(GateRunner):
    name = "lento"

    def __init__(self, segundos: float = 2.0):
        self.segundos = segundos
        self.ativos = 0
        self.maximo = 0
        self.trava = threading.Lock()
        self.comecou = threading.Event()

    def execute(self, *, argv, cwd, env, timeout):
        with self.trava:
            self.ativos += 1
            self.maximo = max(self.maximo, self.ativos)
            self.comecou.set()
        time.sleep(self.segundos)
        with self.trava:
            self.ativos -= 1
        return 0, "ok", ""


class B3_LeaseNaoVenceComRunnerVivo(unittest.TestCase):
    """Sem heartbeat, um lease curto abre duas execuções físicas."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.led = EvidenceLedger(Path(self.tmp.name) / "l.sqlite")

    def tearDown(self):
        self.tmp.cleanup()

    def _comum(self, runner, **over):
        base = dict(
            gate_index=1, argv=["mesmo"], worktree=Path(self.tmp.name), env={},
            timeout=30, ledger=self.led, acceptance_id="P-A1", base_sha="s",
            candidate_sha=None, context_digest="c", env_fingerprint="e",
            production_digest="p", test_digest="t", runner=runner,
            lease_seconds=1, wait_seconds=0.0,
        )
        base.update(over)
        return base

    def test_heartbeat_mantem_o_lease_e_impede_segunda_execucao(self):
        runner = _RunnerLento(3.0)
        saidas: list = []
        fio = threading.Thread(target=lambda: saidas.append(
            run_gate_with_ledger(**self._comum(runner, run_id="r1", worker_id="w1"))))
        fio.start()
        runner.comecou.wait(timeout=10)
        time.sleep(1.4)                      # bem além do lease nominal de 1s
        segundo = run_gate_with_ledger(
            **self._comum(runner, run_id="r2", worker_id="w2", wait_seconds=0.5))
        fio.join(timeout=30)

        self.assertEqual(runner.maximo, 1,
                         "o heartbeat precisa segurar o lease durante a execução")
        self.assertNotEqual(segundo.claim_outcome,
                            ClaimOutcome.RECLAIMED_AFTER_EXPIRY.value,
                            "lease renovado não pode ser retomado")

    def test_dono_que_perde_o_lease_nunca_devolve_ok(self):
        """Mesmo perdendo, o resultado não pode chegar verde ao chamador."""

        ident = _identidade(command_digest="mesmo-cmd")
        claim = self.led.acquire(ident, run_id="r1", worker_id="w1",
                                 lease_seconds=1, wait_seconds=0.0)
        time.sleep(1.2)
        self.led.acquire(ident, run_id="r2", worker_id="w2",
                         lease_seconds=60, wait_seconds=0.0)
        gravou = self.led.complete(
            claim, state="green", base_sha="s", run_id="r1", command="c",
            production_digest="p", test_digest="t", exit_code=0)
        self.assertIsNone(gravou, "dono obsoleto gravou evidência")


# ===========================================================================
# 4 e 5 — complete() com lease vencido, e complete() duplicado
# ===========================================================================
class B4_CompleteRespeitaLeaseEEstado(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.led = EvidenceLedger(Path(self.tmp.name) / "l.sqlite")
        self.args = dict(state="green", base_sha="s", run_id="r1", command="c",
                         production_digest="p", test_digest="t", exit_code=0)

    def tearDown(self):
        self.tmp.cleanup()

    def test_complete_com_lease_vencido_e_recusado(self):
        claim = self.led.acquire(_identidade(), run_id="r1", worker_id="w1",
                                 lease_seconds=1, wait_seconds=0.0)
        time.sleep(1.2)
        self.assertIsNone(self.led.complete(claim, **self.args),
                          "lease vencido não conclui, mesmo sem ninguém ter retomado")

    def test_complete_duplicado_nao_cria_segunda_evidencia(self):
        claim = self.led.acquire(_identidade(), run_id="r1", worker_id="w1",
                                 lease_seconds=120, wait_seconds=0.0)
        primeiro = self.led.complete(claim, **self.args)
        segundo = self.led.complete(claim, **self.args)
        self.assertIsNotNone(primeiro)
        self.assertEqual(len(self.led.evidencias()), 1,
                         "um claim/fence produziu duas evidências")
        self.assertIn(segundo, {primeiro, None},
                      "repetição legítima é idempotente ou recusada, nunca duplica")


# ===========================================================================
# 6 — OSError deixando o claim running
# ===========================================================================
class B6_ExcecaoDoRunnerVirouEstadoTerminal(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.led = EvidenceLedger(Path(self.tmp.name) / "l.sqlite")

    def tearDown(self):
        self.tmp.cleanup()

    def _rodar(self, excecao):
        class _Quebra(GateRunner):
            name = "quebra"

            def execute(self, *, argv, cwd, env, timeout):
                raise excecao

        return run_gate_with_ledger(
            gate_index=1, argv=["/usr/bin/true"], worktree=Path(self.tmp.name),
            env={}, timeout=10, ledger=self.led, acceptance_id="P-A1",
            base_sha="s", candidate_sha=None, context_digest="c",
            env_fingerprint="e", production_digest="p", test_digest="t",
            run_id="r", worker_id="w", runner=_Quebra(),
            lease_seconds=60, wait_seconds=0.0,
        )

    def test_oserror_vira_infra_registrada_e_claim_terminal(self):
        saida = self._rodar(OSError("spawn falhou"))
        self.assertEqual(saida.status, "infrastructure")
        self.assertFalse(saida.ok)
        self.assertIsNotNone(saida.evidence_id, "INFRA precisa estar no ledger")
        self.assertEqual(self.led.claims_ativos(), [],
                         "nenhum claim pode ficar running depois da exceção")

    def test_excecao_arbitraria_tambem_vira_infra(self):
        saida = self._rodar(RuntimeError("runner explodiu"))
        self.assertEqual(saida.status, "infrastructure")
        self.assertIsNotNone(saida.evidence_id)
        self.assertEqual(self.led.claims_ativos(), [])


# ===========================================================================
# 7 — schema legado do EvidenceLedger
# ===========================================================================
LEDGER_LEGADO = """
CREATE TABLE evidence (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    acceptance_id     TEXT NOT NULL,
    kind              TEXT NOT NULL,
    base_sha          TEXT NOT NULL,
    candidate_sha     TEXT,
    input_digest      TEXT NOT NULL,
    production_digest TEXT NOT NULL,
    test_digest       TEXT NOT NULL,
    command           TEXT NOT NULL,
    exit_code         INTEGER,
    counts_json       TEXT,
    valid             INTEGER NOT NULL DEFAULT 1,
    run_id            TEXT NOT NULL,
    created_at        TEXT NOT NULL
);
"""


def _colunas(conn, tabela: str) -> set[str]:
    return {l[1] for l in conn.execute(f"PRAGMA table_info({tabela})")}


def _tabelas(conn) -> set[str]:
    return {l[0] for l in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


class B7_MigracaoRetrocompativelDoLedger(unittest.TestCase):
    """`CREATE TABLE IF NOT EXISTS` não evolui banco que já existe."""

    def _legado(self, destino: Path) -> None:
        with sqlite3.connect(destino) as c:
            c.executescript(LEDGER_LEGADO)
            c.execute(
                "INSERT INTO evidence(acceptance_id,kind,base_sha,input_digest,"
                "production_digest,test_digest,command,exit_code,counts_json,"
                "run_id,created_at) VALUES('P-A1','gate_1','s','d','p','t','x',0,"
                "'{}','r0','2026-01-01')")

    def test_banco_legado_migra_preservando_linhas(self):
        with TemporaryDirectory() as tmp:
            alvo = Path(tmp) / "l.sqlite"
            self._legado(alvo)
            EvidenceLedger(alvo)
            with sqlite3.connect(alvo) as c:
                cols = _colunas(c, "evidence")
                tabs = _tabelas(c)
                linhas = c.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
        for esperado in ("cwd", "env_fingerprint", "context_digest"):
            self.assertIn(esperado, cols, f"coluna {esperado} não foi migrada")
        self.assertIn("execution_claim", tabs)
        self.assertEqual(linhas, 1, "a linha legada precisa sobreviver")

    def test_reabrir_duas_vezes_e_no_op(self):
        with TemporaryDirectory() as tmp:
            alvo = Path(tmp) / "l.sqlite"
            self._legado(alvo)
            EvidenceLedger(alvo)
            EvidenceLedger(alvo)
            with sqlite3.connect(alvo) as c:
                self.assertEqual(
                    c.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 1)

    def test_duas_inicializacoes_concorrentes(self):
        with TemporaryDirectory() as tmp:
            alvo = Path(tmp) / "l.sqlite"
            self._legado(alvo)
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
            self.assertEqual(erros, [], f"migração concorrente falhou: {erros}")

    def test_migracao_nao_usa_excecao_como_inspecao(self):
        """A inspeção mora em `sqlite_support`; o ledger declara e delega."""

        import inspect

        from volc_agent_harness.v3 import ledger, sqlite_support

        suporte = inspect.getsource(sqlite_support)
        self.assertIn("PRAGMA table_info", suporte)
        self.assertNotIn("except sqlite3.OperationalError", suporte.split(
            "def conectar")[1].split("def tabelas")[0].replace(
            "except sqlite3.OperationalError:\n                time.sleep", ""))

        fonte = inspect.getsource(ledger)
        self.assertIn("migrar(", fonte, "o ledger precisa chamar a migração")
        self.assertNotIn("executescript(", fonte,
                         "executescript não evolui banco existente")

    def test_registry_nao_importa_simbolo_privado_do_ledger(self):
        fonte = (FONTE / "v3" / "registry.py").read_text(encoding="utf-8")
        self.assertNotIn("from .ledger import _conectar", fonte)
        self.assertNotIn("import _conectar", fonte)


# ===========================================================================
# 8 — falha depois do run_dir sem failure.json
# ===========================================================================
class B8_FronteiraDeErroCobreOsArtefatos(unittest.TestCase):
    """`metadata.json` era escrito fora do `try` — nos dois modos."""

    def test_falha_ao_gravar_metadata_produz_failure_json(self):
        import volc_agent_harness.mission as mm

        with TemporaryDirectory() as tmp:
            repo = repo_sintetico(Path(tmp))
            from volc_agent_harness.v3.run_artifacts import RunArtifacts

            contador = ContadorDeModelos()
            original_adapter = mm.adapter_for
            original_escrever = RunArtifacts.escrever
            estado = {"explodiu": False}

            def _escrever(self, nome, conteudo):
                # A escrita passou a ser atômica via os.replace; interceptar
                # `Path.write_text` não pega mais nada. A prova acompanha o
                # ponto real de gravação.
                if nome == "metadata.json" and not estado["explodiu"]:
                    estado["explodiu"] = True
                    raise OSError("disk full")
                return original_escrever(self, nome, conteudo)

            mm.adapter_for = contador.adapter_for
            RunArtifacts.escrever = _escrever
            try:
                alvo = missao(repo, gates=[{"kind": "catalog",
                                            "gate_id": "diff-limpo"}])
                saida = StringIO()
                with redirect_stdout(saida):
                    from volc_agent_harness.cli import main as cli_main
                    codigo = cli_main(["--mission", str(alvo), "--repo", str(repo)])
            finally:
                RunArtifacts.escrever = original_escrever
                mm.adapter_for = original_adapter

            runs = sorted((repo / "tools" / "agent-harness" / "runs").iterdir())
            self.assertEqual(codigo, 4, saida.getvalue())
            self.assertTrue(runs, "o run_dir foi criado")
            self.assertTrue((runs[-1] / "failure.json").is_file(),
                            "falha depois do run_dir precisa deixar artefato")
            registro = json.loads((runs[-1] / "failure.json").read_text())
            self.assertIn("fase", registro, "failure.json precisa nomear a fase")
            self.assertEqual(contador.chamadas, [])


# ===========================================================================
# 9 — colisão lógica entre dois subdiretórios quando cwd é omitido
# ===========================================================================
class B9_CwdRelativoEntraNaIdentidade(unittest.TestCase):
    """Nem cwd absoluto (nunca reutiliza) nem cwd omitido (colide)."""

    def _ident(self, cwd_rel: str) -> GateIdentity:
        return GateIdentity.for_gate(
            acceptance_id="P-A1", gate_index=1, argv=["cmd"], context_digest="c",
            production_digest="p", test_digest="t", env_fingerprint="e",
            cwd_rel=cwd_rel)

    def test_cwd_relativo_diferente_gera_identidade_diferente(self):
        self.assertNotEqual(self._ident("backend").logical_key,
                            self._ident("volc_ads").logical_key)

    def test_mesma_raiz_relativa_em_worktrees_diferentes_reutiliza(self):
        self.assertEqual(self._ident(".").logical_key, self._ident(".").logical_key)

    def test_cwd_fora_da_worktree_e_bloqueado(self):
        for fora in ("..", "../fora", "/etc"):
            with self.subTest(cwd=fora):
                with self.assertRaises(HarnessFailure) as e:
                    self._ident(fora)
                self.assertEqual(e.exception.classe,
                                 FailureClass.AUTHORIZATION_BLOCK)


# ===========================================================================
# Caminhos legados: nenhuma segunda implementação executável
# ===========================================================================
class B10_LegadoFailClosed(unittest.TestCase):
    def test_funcoes_legadas_nao_executam_nada(self):
        from volc_agent_harness.v3 import baseline, pipeline

        alvos = [
            (pipeline, "run_baseline"),
            (pipeline, "postwriter_phase"),
            (pipeline, "classify_and_record"),
            (baseline, "measure"),
        ]
        for modulo, nome in alvos:
            with self.subTest(alvo=f"{modulo.__name__}.{nome}"):
                fn = getattr(modulo, nome, None)
                if fn is None:
                    continue                     # removida: também é aceitável
                with self.assertRaises(HarnessFailure) as e:
                    fn()
                self.assertEqual(e.exception.classe,
                                 FailureClass.LEGACY_PATH_DISABLED)

    def test_nenhum_caminho_produtivo_le_argv_da_missao(self):
        import ast

        ofensores: list[str] = []
        for arquivo in sorted(FONTE.rglob("*.py")):
            rel = arquivo.relative_to(FONTE).as_posix()
            if rel.startswith("v3/gate_runner"):
                continue                         # fronteira autorizada de execução
            texto = arquivo.read_text(encoding="utf-8")
            ofensores.extend(f"{rel}:{linha}" for linha in
                             _le_argv_de_dicionario(arquivo))
            arvore = ast.parse(texto)
            for no in ast.walk(arvore):
                if (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                        and no.func.attr == "run"
                        and isinstance(no.func.value, ast.Name)
                        and no.func.value.id == "subprocess"
                        and rel.startswith("v3/")
                        and rel not in {"v3/harvest.py", "v3/gate_catalog.py",
                                        "v3/gate_types.py"}):
                    ofensores.append(f"{rel}:{no.lineno}: subprocess.run")
        self.assertEqual(ofensores, [],
                         "caminho produtivo ainda executa ou lê argv por fora")


if __name__ == "__main__":
    unittest.main()
