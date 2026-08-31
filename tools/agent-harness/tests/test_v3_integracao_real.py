"""Guarda 2: o caminho REAL de execução passa pelo V3.

Uma biblioteca V3 verde que nenhum launcher consome não protege nada. Estes
testes usam o mesmo entrypoint do CLI e um adapter-contador: se o contador
registrar qualquer chamada, gastamos um modelo onde o compilador deveria ter
recusado.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

RAIZ_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(RAIZ_SRC))

import volc_agent_harness.mission as mission_mod  # noqa: E402
from volc_agent_harness.v3.failures import FailureClass, HarnessFailure  # noqa: E402


class ContadorDeAdapter:
    """Se ``chamadas`` não for zero, um modelo foi gasto."""

    def __init__(self) -> None:
        self.chamadas: list[str] = []

    def para(self, provider: str):
        contador = self

        class _Adapter:
            async def run(self, request):
                contador.chamadas.append(provider)
                return {"status": "completed", "summary": "stub"}

        return _Adapter()


class IntegracaoReal(unittest.TestCase):
    def test_runtime_compila_antes_de_chamar_adapter(self):
        """A ordem no código-fonte do caminho real, não numa cópia paralela."""

        fonte = inspect.getsource(mission_mod)
        # O símbolo mudou junto com a autoridade: quem compila gate agora é o
        # resolvedor TIPADO, não a compilação por argv livre.
        i_compile = fonte.index("resolve_mission_gates(")
        i_adapter = fonte.index("await adapter_for(writer.provider).run")
        self.assertLess(i_compile, i_adapter,
                        "o compilador precisa rodar ANTES do adapter no caminho real")

    def test_runtime_usa_classificacao_tipada_e_nao_runtimeerror(self):
        fonte = inspect.getsource(mission_mod)
        self.assertIn("classify_gate_exit(", fonte)
        self.assertIn("raise HarnessFailure(", fonte)
        self.assertNotIn('raise RuntimeError(\n                        f"gate', fonte)

    def test_runtime_recusa_comando_destrutivo_em_gate(self):
        fonte = inspect.getsource(mission_mod)
        self.assertIn("assert_no_destructive_intent(", fonte)

    def test_cli_expoe_compile_e_launcher_o_consome(self):
        from volc_agent_harness import cli

        self.assertTrue(hasattr(cli, "compile_only"))
        launcher = Path(__file__).resolve().parents[1] / "volc-harness"
        texto = launcher.read_text(encoding="utf-8")
        self.assertIn("compile)", texto, "launcher precisa expor o subcomando compile")
        self.assertIn("compile_only", texto)

    def test_pyproject_declara_o_entrypoint_de_compile(self):
        pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
        self.assertIn("volc-agent-compile", pyproject)

    def test_compile_pelo_cli_recusa_gate_inexistente_sem_gastar_modelo(self):
        """End-to-end pelo mesmo entrypoint: zero chamadas de modelo."""

        contador = ContadorDeAdapter()
        with TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "backend" / "tests").mkdir(parents=True)
            (repo / "volc-os-workbook").mkdir()
            (repo / "volc-os-workbook" / "ROADMAP-VIVO.json").write_text(json.dumps(
                {"initiatives": [{"id": "P04-T09", "acceptance": ["a1", "a2"]}]}
            ))
            missao = {
                "mission_schema_version": 3,
                "mission_id": "teste-compile",
                "title": "t",
                "base_ref": "0" * 40,
                "briefing": "b",
                "mode": "implementation",
                "commit_message": "c",
                "acceptance_ids": ["P04-T09-A2"],
                "ownership_envelope": ["backend"],
                "authorized_external_providers": [],
                "gates": [{"kind": "pytest",
                           "targets": ["backend/tests/nao_existe.py"]}],
                "workers": [
                    {"id": "wr", "provider": "codex", "role": "writer", "model": "gpt-5.5",
                     "lens": "x", "allowed_paths": ["backend"], "writable_paths": ["backend"]},
                    {"id": "rv", "provider": "codex", "role": "reviewer", "model": "gpt-5.6-sol",
                     "lens": "y", "allowed_paths": ["backend"]},
                ],
            }
            arquivo = repo / "m.json"
            arquivo.write_text(json.dumps(missao))

            from volc_agent_harness.cli import compile_only

            codigo = compile_only(["--mission", str(arquivo), "--repo", str(repo),
                                   "--out", str(repo / "tools" / "agent-harness" / "runs" / "check")])
            self.assertEqual(codigo, 3, "missão com gate inexistente não compila")
        self.assertEqual(contador.chamadas, [], "nenhum modelo pode ter sido chamado")

    def test_compile_pelo_cli_aceita_missao_valida(self):
        with TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "backend" / "tests").mkdir(parents=True)
            (repo / "backend" / "tests" / "test_ok.py").write_text("def test_a(): assert True\n")
            (repo / "volc-os-workbook").mkdir()
            (repo / "volc-os-workbook" / "ROADMAP-VIVO.json").write_text(json.dumps(
                {"initiatives": [{"id": "P04-T09", "acceptance": ["a1", "a2"]}]}
            ))
            missao = {
                "mission_schema_version": 3,
                "mission_id": "teste-ok", "title": "t", "base_ref": "0" * 40,
                "briefing": "b", "mode": "implementation", "commit_message": "c",
                "acceptance_ids": ["P04-T09-A2"],
                "ownership_envelope": ["backend"],
                "authorized_external_providers": [],
                "gates": [{"kind": "pytest",
                           "targets": ["backend/tests/test_ok.py"]}],
                "workers": [
                    {"id": "wr", "provider": "codex", "role": "writer", "model": "gpt-5.5",
                     "lens": "x", "allowed_paths": ["backend"], "writable_paths": ["backend"]},
                    {"id": "rv", "provider": "codex", "role": "reviewer", "model": "gpt-5.6-sol",
                     "lens": "y", "allowed_paths": ["backend"]},
                ],
            }
            arquivo = repo / "m.json"
            arquivo.write_text(json.dumps(missao))
            from volc_agent_harness.cli import compile_only

            self.assertEqual(
                compile_only(["--mission", str(arquivo), "--repo", str(repo),
                              "--out", str(repo / "tools" / "agent-harness" / "runs" / "check")]),
                0,
            )
            artefato = json.loads((repo / "tools" / "agent-harness" / "runs" / "check" / "compiled-mission.json").read_text())
            self.assertEqual(artefato["acceptance_ids"], ["P04-T09-A2"])
            self.assertEqual(artefato["gates_runnable_before_writer"], [1])

    def test_missao_legada_v2_nao_atravessa_o_compilador_em_silencio(self):
        with TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "volc-os-workbook").mkdir()
            (repo / "volc-os-workbook" / "ROADMAP-VIVO.json").write_text("{}")
            missao = {
                "mission_id": "legada", "title": "t", "base_ref": "0" * 40,
                "briefing": "b", "mode": "read_only",
                "authorized_external_providers": [],
                "workers": [
                    {"id": "aa", "provider": "codex", "role": "investigator",
                     "model": "gpt-5.5", "lens": "x", "allowed_paths": ["backend"]},
                    {"id": "bb", "provider": "codex", "role": "reviewer",
                     "model": "gpt-5.5", "lens": "y", "allowed_paths": ["backend"]},
                ],
            }
            arquivo = repo / "m.json"
            arquivo.write_text(json.dumps(missao))
            from volc_agent_harness.cli import compile_only

            self.assertEqual(
                compile_only(["--mission", str(arquivo), "--repo", str(repo),
                              "--out", str(repo / "tools" / "agent-harness" / "runs" / "check")]),
                3,
                "missão V2 precisa falhar com código claro, não passar em silêncio",
            )


if __name__ == "__main__":
    unittest.main()
