"""FASE 5 — E2E pelo MESMO entrypoint que o supervisor futuro vai usar.

Nada aqui chama função interna: tudo entra por ``cli.main``, como o operador e o
supervisor entram. O adapter-contador está de fato instalado sobre
``mission.adapter_for`` — a versão anterior desta prova declarava um contador que
ninguém instalava, então "nenhum modelo foi chamado" era verdade por construção,
não por evidência.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _e2e_fixture import ContadorDeModelos, git, missao, repo_sintetico  # noqa: E402

import volc_agent_harness.mission as mission_mod  # noqa: E402
from volc_agent_harness.cli import main as cli_main  # noqa: E402

SCRIPT_GATE = """\
import sys
from pathlib import Path

raiz = Path(__file__).resolve().parents[2]
vermelho = raiz / "backend" / "tests" / "SINALIZA_VERMELHO"
print("gate sintetico rodou")
raise SystemExit(1 if vermelho.exists() else 0)
"""

CATALOGO = {
    "catalog_version": 1,
    "gates": {
        "prova-sintetica": {
            "kind": "tracked_script",
            "script_path": "tools/agent-harness/gate_sintetico.py",
            "args": [],
            "description": "gate determinístico da prova E2E",
        },
        "diff-limpo": {"kind": "git_diff_check", "description": "diff sem conflito"},
    },
}


def _runs(repo: Path) -> list[Path]:
    raiz = repo / "tools" / "agent-harness" / "runs"
    return sorted((p for p in raiz.iterdir() if p.is_dir()),
                  key=lambda p: p.name) if raiz.is_dir() else []


def _evidencias(repo: Path, *, prefixo: str = "gate_") -> list[dict]:
    """Evidências do ledger. O baseline tem `kind` próprio e não se mistura."""

    banco = repo / "tools" / "agent-harness" / "evidence-ledger.sqlite"
    if not banco.is_file():
        return []
    with sqlite3.connect(banco) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute(
            "SELECT * FROM evidence WHERE kind LIKE ? ORDER BY id", (prefixo + "%",))]


class _E2E(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.repo = repo_sintetico(Path(self.tmp.name), catalogo=CATALOGO)
        (self.repo / "tools" / "agent-harness" / "gate_sintetico.py").write_text(
            SCRIPT_GATE, encoding="utf-8")
        git(self.repo, "add", "-A")
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=t",
                        "-c", "user.email=t@t", "commit", "-q", "-m", "gate"],
                       check=True, capture_output=True)
        self.contador = ContadorDeModelos(escrita=self._escreve)
        self._original = mission_mod.adapter_for
        mission_mod.adapter_for = self.contador.adapter_for
        self.vermelho = False

    def tearDown(self):
        mission_mod.adapter_for = self._original
        self.tmp.cleanup()

    def _escreve(self, worktree: Path) -> None:
        (worktree / "backend" / "tests" / "test_novo.py").write_text(
            "def test_do_writer():\n    assert True\n", encoding="utf-8")
        if self.vermelho:
            (worktree / "backend" / "tests" / "SINALIZA_VERMELHO").write_text("x")

    def _rodar(self, **over) -> tuple[int, str]:
        over.setdefault("gates", [{"kind": "catalog", "gate_id": "prova-sintetica"}])
        alvo = missao(self.repo, **over)
        buffer = StringIO()
        with redirect_stdout(buffer):
            codigo = cli_main(["--mission", str(alvo), "--repo", str(self.repo)])
        return codigo, buffer.getvalue()


class CadeiaCompleta(_E2E):
    def test_missao_compila_resolve_gate_tipado_e_colhe(self):
        codigo, saida = self._rodar()
        self.assertEqual(codigo, 0, saida)
        run = _runs(self.repo)[-1]

        compilada = json.loads((run / "compiled-mission.json").read_text())
        self.assertEqual(compilada["mission_schema_version"], 3)
        gate = compilada["gate_plan"]["gates"][0]
        self.assertEqual(gate["kind"], "tracked_script")
        self.assertEqual(gate["gate_id"], "prova-sintetica")
        self.assertEqual(len(gate["binding_digest"]), 64)

        evidencia = json.loads((run / "evidence.json").read_text())
        self.assertEqual(len(evidencia), 1)
        self.assertEqual(evidencia[0]["execution_mode"], "executed")
        self.assertEqual(evidencia[0]["claim_outcome"], "acquired")
        self.assertEqual(evidencia[0]["status"], "green")

        colheita = json.loads((run / "harvest.json").read_text())
        self.assertEqual(colheita["green_gates"], [1])
        self.assertIn("backend/tests/test_novo.py", colheita["files"])
        self.assertTrue((run / "adjudication.json").is_file())

        linhas = _evidencias(self.repo)
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["exit_code"], 0)
        base = _evidencias(self.repo, prefixo="baseline_gate_")
        self.assertEqual(len(base), 1, "o baseline também é reivindicado e gravado")
        self.assertNotEqual(base[0]["input_digest"], linhas[0]["input_digest"],
                            "baseline e candidato não podem colidir na identidade")

    def test_writer_e_reviewer_chamados_uma_vez_e_na_ordem(self):
        codigo, saida = self._rodar()
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(len(self.contador.writers), 1)
        self.assertEqual([c["worker_id"] for c in self.contador.readers], ["rv"])
        self.assertEqual(self.contador.chamadas[0]["worker_id"], "wr",
                         "o writer precisa vir antes do revisor")

    def test_segunda_execucao_reutiliza_green(self):
        self.assertEqual(self._rodar()[0], 0)
        codigo, saida = self._rodar()
        self.assertEqual(codigo, 0, saida)
        run = _runs(self.repo)[-1]
        evidencia = json.loads((run / "evidence.json").read_text())
        self.assertEqual(evidencia[0]["execution_mode"], "reused",
                         "mesmo digest material: o gate não podia rodar de novo")
        self.assertEqual(evidencia[0]["claim_outcome"], "reused_green")
        self.assertEqual(evidencia[0]["status"], "green")

    def test_gate_vermelho_nao_gera_harvest_falso(self):
        self.vermelho = True
        codigo, saida = self._rodar()
        self.assertNotEqual(codigo, 0, saida)
        run = _runs(self.repo)[-1]
        self.assertFalse((run / "harvest.json").exists(),
                         "gate vermelho não colhe")
        falha = json.loads((run / "failure.json").read_text())
        self.assertIn(falha["classe"], {"MERIT_FAILURE", "SPEC_ERROR"})

        evidencia = json.loads((run / "evidence.json").read_text())
        self.assertEqual(evidencia[0]["status"], "red")
        linhas = _evidencias(self.repo)
        self.assertEqual([l["exit_code"] for l in linhas], [1],
                         "o vermelho precisa estar no ledger ANTES do failure")
        self.assertEqual(self.contador.readers, [],
                         "revisor não pode ser chamado sobre candidato vermelho")

    def test_gate_de_catalogo_ausente_nao_gasta_modelo(self):
        codigo, saida = self._rodar(
            gates=[{"kind": "catalog", "gate_id": "gate-inexistente"}])
        self.assertEqual(codigo, 3, saida)
        self.assertEqual(self.contador.chamadas, [])

    def test_catalogo_nao_rastreado_nao_gasta_modelo(self):
        git(self.repo, "rm", "-q", "--cached", "tools/agent-harness/gate-catalog.json")
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=t",
                        "-c", "user.email=t@t", "commit", "-q", "-m", "solta"],
                       check=True, capture_output=True)
        codigo, saida = self._rodar()
        self.assertEqual(codigo, 3, saida)
        self.assertEqual(self.contador.chamadas, [])

    def test_gate_que_altera_insumo_de_outro_gate_e_recusado(self):
        """A janela entre compilar e executar não fecha no primeiro gate.

        O writer não consegue tocar o script de um gate — o ownership barra
        antes. Mas o gate ANTERIOR roda código, e código altera arquivo. Este é
        o caso que obriga a revalidação a ficar dentro do laço, e não uma vez
        antes dele: o gate 1 reescreve o script auditado do gate 2.
        """

        alvo = self.repo / "tools" / "agent-harness" / "alvo.py"
        alvo.write_text("raise SystemExit(0)\n", encoding="utf-8")
        # O sabotador recebe o artefato PRODUZIDO pelo writer como argumento.
        # Isso o tira do baseline: gate que depende de produced_path não é
        # executável antes do writer, e é justamente na janela pós-writer que a
        # prova precisa acontecer.
        (self.repo / "tools" / "agent-harness" / "sabota.py").write_text(
            "import sys\n"
            "from pathlib import Path\n"
            "assert Path(sys.argv[1]).is_file(), sys.argv[1]\n"
            "raiz = Path(__file__).resolve().parents[2]\n"
            "(raiz / 'tools' / 'agent-harness' / 'alvo.py').write_text("
            "'raise SystemExit(0)  # trocado em tempo de execucao\\n')\n",
            encoding="utf-8")
        catalogo = json.loads(json.dumps(CATALOGO))
        catalogo["gates"]["sabotador"] = {
            "kind": "tracked_script",
            "script_path": "tools/agent-harness/sabota.py",
            "args": ["backend/tests/test_novo.py"],
            "description": "gate que altera o insumo do gate seguinte",
        }
        catalogo["gates"]["alvo"] = {
            "kind": "tracked_script",
            "script_path": "tools/agent-harness/alvo.py",
            "args": [],
            "description": "gate cujo script é alterado durante a execução",
        }
        (self.repo / "tools" / "agent-harness" / "gate-catalog.json").write_text(
            json.dumps(catalogo, indent=2), encoding="utf-8")
        git(self.repo, "add", "-A")
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=t",
                        "-c", "user.email=t@t", "commit", "-q", "-m", "sabotador"],
                       check=True, capture_output=True)

        codigo, saida = self._rodar(
            produced_paths=[{"path": "backend/tests/test_novo.py"}],
            gates=[
                {"kind": "catalog", "gate_id": "sabotador"},
                {"kind": "catalog", "gate_id": "alvo"},
            ],
        )
        self.assertNotEqual(codigo, 0, saida)
        run = _runs(self.repo)[-1]
        falha = json.loads((run / "failure.json").read_text())
        self.assertEqual(falha["classe"], "STALE_INPUT")
        self.assertFalse(falha["permite_retry"],
                         "insumo trocado não se conserta relançando writer")
        self.assertFalse((run / "harvest.json").exists())
        evidencia = json.loads((run / "evidence.json").read_text())
        self.assertEqual(len(evidencia), 1,
                         "o gate 1 mediu; o gate 2 nem chegou a rodar")


class SemCaminhoParalelo(unittest.TestCase):
    """O runtime não pode ter dois jeitos de executar gate."""

    #: Módulos do caminho produtivo que NÃO podem executar nada por conta
    #: própria. `mission.py` é o runtime; `pipeline.py` é o entrypoint de
    #: `volc-harness compile`.
    #:
    #: `baseline.measure` continua tendo `subprocess.run` — mas o runtime não o
    #: chama mais (ver `test_runtime_nao_mede_baseline_fora_do_ledger`). Ele
    #: sobrou como primitiva de biblioteca consumida por `pipeline.run_baseline`,
    #: que hoje nenhum entrypoint alcança. É candidato de inventário, não lixo
    #: comprovado: some numa limpeza com evidência, não no meio desta entrega.
    SEM_SUBPROCESS = ("mission.py", "v3/pipeline.py")

    def _subprocess_runs(self, modulo: str) -> list[tuple[str, int]]:
        import ast

        fonte_dir = Path(__file__).resolve().parents[1] / "src" / "volc_agent_harness"
        arvore = ast.parse((fonte_dir / modulo).read_text(encoding="utf-8"))
        achados = []
        for no in ast.walk(arvore):
            if not isinstance(no, ast.Call):
                continue
            alvo = no.func
            if (isinstance(alvo, ast.Attribute) and alvo.attr == "run"
                    and isinstance(alvo.value, ast.Name)
                    and alvo.value.id == "subprocess"):
                achados.append((modulo, no.lineno))
        return achados

    def test_nenhum_modulo_produtivo_executa_gate_fora_do_ledger(self):
        ofensores = [x for m in self.SEM_SUBPROCESS for x in self._subprocess_runs(m)]
        self.assertEqual(ofensores, [],
                         "execução de gate fora do ledger ainda existe")

    def test_runtime_nao_mede_baseline_fora_do_ledger(self):
        """`measure` sumiu do runtime; o que sobrou é biblioteca sem chamador."""

        fonte_dir = Path(__file__).resolve().parents[1] / "src" / "volc_agent_harness"
        runtime = (fonte_dir / "mission.py").read_text(encoding="utf-8")
        self.assertNotIn("measure(", runtime)
        self.assertNotIn("import measure", runtime)

        alcancado = [
            arquivo.name
            for arquivo in fonte_dir.rglob("*.py")
            if arquivo.name not in {"pipeline.py", "baseline.py"}
            and "run_baseline(" in arquivo.read_text(encoding="utf-8")
        ]
        self.assertEqual(alcancado, [],
                         f"pipeline.run_baseline ganhou chamador: {alcancado}")

    def test_baseline_do_runtime_passa_pelo_claim(self):
        """Medir o base é executar. Dois runs simultâneos mediriam duas vezes."""

        import inspect

        import volc_agent_harness.mission as mission_mod

        fonte = inspect.getsource(mission_mod._run_implementation_mission)
        antes_do_writer = fonte.split("await adapter_for(writer.provider).run")[0]
        self.assertIn("run_gate_with_ledger(", antes_do_writer,
                      "o baseline precisa reivindicar antes de medir")
        self.assertIn('production_digest=f"baseline:', antes_do_writer,
                      "baseline e candidato não podem colidir na mesma identidade")

    def test_sonda_de_coleta_e_o_unico_subprocess_tolerado(self):
        """`--collect-only` não emite veredito sobre o candidato.

        Ele responde "este gate coleta algum teste?" — uma pergunta sobre a
        ESPECIFICAÇÃO, não sobre o mérito do código. Por isso continua fora do
        ledger, e por isso a exceção é nomeada aqui em vez de ficar implícita.
        """

        achados = self._subprocess_runs("v3/gate_compiler.py")
        self.assertEqual(len(achados), 1, f"subprocess inesperado: {achados}")

        import inspect

        from volc_agent_harness.v3 import gate_compiler

        fonte = inspect.getsource(gate_compiler.assert_pytest_collects)
        self.assertIn("subprocess.run(", fonte)
        self.assertIn("--collect-only", " ".join(
            gate_compiler.assert_pytest_collects.__doc__.split()))


if __name__ == "__main__":
    unittest.main()
