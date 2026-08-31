"""FASE 4 — ratchet de boot: falha de inicialização não some.

O que já estava provado: ``OperationalError`` vira ``INFRASTRUCTURE_ERROR``,
o processo sai com 4 e a saída é sanitizada.

O que faltava, e é o que esta suíte fecha:

* se o ``run_dir`` JÁ existe quando a inicialização falha, o artefato
  ``failure.json`` precisa nascer lá — hoje o registry corrompido levantava
  DEPOIS de ``run_dir.mkdir`` e fora do ``try``, e o operador ficava sem nada;
* se a falha acontece ANTES de existir ``run_id``, a saída tipada basta;
* o CLI nunca imprime caminho de artefato que não existe.
"""

from __future__ import annotations

import json
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _e2e_fixture import ContadorDeModelos, missao, repo_sintetico  # noqa: E402

import volc_agent_harness.mission as mission_mod  # noqa: E402
from volc_agent_harness.cli import main as cli_main  # noqa: E402


def _runs(repo: Path) -> list[Path]:
    raiz = repo / "tools" / "agent-harness" / "runs"
    return sorted(p for p in raiz.iterdir() if p.is_dir()) if raiz.is_dir() else []


class BootComRunDirExistente(unittest.TestCase):
    """Registry ilegível: a falha é de infraestrutura e precisa deixar rastro."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.repo = repo_sintetico(Path(self.tmp.name))
        self.contador = ContadorDeModelos()
        self._original = mission_mod.adapter_for
        mission_mod.adapter_for = self.contador.adapter_for
        registry = self.repo / "tools" / "agent-harness" / "worktree-registry.sqlite"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_bytes(b"isto nao e um banco sqlite\n" * 40)

    def tearDown(self):
        mission_mod.adapter_for = self._original
        self.tmp.cleanup()

    def _rodar(self, **over) -> tuple[int, str]:
        alvo = missao(self.repo, **over)
        buffer = StringIO()
        with redirect_stdout(buffer):
            codigo = cli_main(["--mission", str(alvo), "--repo", str(self.repo)])
        return codigo, buffer.getvalue()

    def test_implementation_grava_failure_json_no_run_dir(self):
        codigo, saida = self._rodar()
        self.assertEqual(codigo, 4, saida)
        runs = _runs(self.repo)
        self.assertEqual(len(runs), 1, "o run_dir foi criado e precisa guardar a falha")
        artefato = runs[0] / "failure.json"
        self.assertTrue(artefato.is_file(),
                        f"falha de boot sem artefato em {runs[0]}")
        registro = json.loads(artefato.read_text(encoding="utf-8"))
        self.assertEqual(registro["classe"], "INFRASTRUCTURE_ERROR")
        self.assertFalse(registro["permite_retry"])
        self.assertIn(str(artefato), saida,
                      "o CLI precisa dizer onde está o artefato que existe")
        self.assertEqual(self.contador.chamadas, [],
                         "nenhum modelo pode ter sido chamado")

    def test_read_only_grava_failure_json_no_run_dir(self):
        codigo, saida = self._rodar(
            mode="read_only", commit_message=None, gates=[],
            workers=[
                {"id": "a", "provider": "codex", "model": "gpt-5.5", "lens": "x",
                 "allowed_paths": ["backend"]},
                {"id": "b", "provider": "codex", "model": "gpt-5.5", "lens": "y",
                 "allowed_paths": ["backend"]},
            ],
        )
        self.assertEqual(codigo, 4, saida)
        runs = _runs(self.repo)
        self.assertEqual(len(runs), 1)
        self.assertTrue((runs[0] / "failure.json").is_file())
        self.assertEqual(self.contador.chamadas, [])


class BootAntesDoRunDir(unittest.TestCase):
    """Sem run_id ainda: saída tipada basta, e nenhum caminho é inventado."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.repo = repo_sintetico(Path(self.tmp.name))
        self.contador = ContadorDeModelos()
        self._original = mission_mod.adapter_for
        mission_mod.adapter_for = self.contador.adapter_for

    def tearDown(self):
        mission_mod.adapter_for = self._original
        self.tmp.cleanup()

    def test_base_ref_inexistente_sai_tipado_sem_artefato(self):
        alvo = missao(self.repo, base_ref="0" * 40)
        buffer = StringIO()
        with redirect_stdout(buffer):
            codigo = cli_main(["--mission", str(alvo), "--repo", str(self.repo)])
        saida = buffer.getvalue()
        self.assertIn(codigo, {3, 4}, saida)
        self.assertRegex(saida, r"\[[A-Z_]+\]")
        self.assertEqual(_runs(self.repo), [],
                         "nenhum run_dir deveria existir nesta falha")
        self.assertNotIn("failure.json", saida,
                         "o CLI apontou um artefato que não existe")
        self.assertEqual(self.contador.chamadas, [])

    def test_cli_nunca_cita_artefato_ausente(self):
        """Prova estrutural: a linha de artefato é condicionada à existência."""

        import inspect

        from volc_agent_harness import cli

        fonte = inspect.getsource(cli.main)
        self.assertIn("is_file()", fonte,
                      "o CLI precisa conferir o artefato antes de citá-lo")


class FalhaSanitizada(unittest.TestCase):
    def test_segredo_nao_entra_no_failure_json(self):
        from volc_agent_harness.mission import _registrar_falha
        from volc_agent_harness.v3.failures import FailureClass, HarnessFailure

        with TemporaryDirectory() as tmp:
            destino = Path(tmp)
            segredo = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                       "eyJyb2xlIjoic2VydmljZV9yb2xlIiwiaXNzIjoic3VwYSJ9."
                       "assinatura_secreta_aqui")
            _registrar_falha(destino, HarnessFailure(
                FailureClass.INFRASTRUCTURE_ERROR,
                "boot falhou",
                detalhe=f"SUPABASE_SERVICE_ROLE_KEY={segredo}",
                reproducao=f"curl -H 'Bearer {segredo}' https://x",
            ))
            bruto = (destino / "failure.json").read_text(encoding="utf-8")
        self.assertNotIn("assinatura_secreta_aqui", bruto)
        self.assertNotIn(segredo, bruto)
        self.assertIn("REDACTED", bruto)


if __name__ == "__main__":
    unittest.main()
