"""FASE 0 — contraprovas de G1a, preservadas em vermelho antes da correção.

G1a foi REFUTADA na rodada anterior com estes fatos: o ``MissionSpec`` aceitava
``GateSpec.argv`` livre, ``mission.py`` nunca chamava ``gate_types.from_spec`` e
``python -c``, ``node -e``, ``git reset`` e ``git checkout`` atravessavam a
validação da missão. Cada teste aqui é um daqueles fatos, escrito como asserção
do comportamento correto.

⚠️ O que estas provas NÃO afirmam: contenção de filesystem. Nada aqui fecha G1b.
Elas fecham política de DECLARAÇÃO — o que uma missão pode pedir — e não o que um
processo já iniciado consegue tocar no disco.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydantic import ValidationError  # noqa: E402

from volc_agent_harness.models import MissionSpec  # noqa: E402
from volc_agent_harness.v3.failures import FailureClass, HarnessFailure  # noqa: E402

_FIXTURE = Path(__file__).resolve().parent
sys.path.insert(0, str(_FIXTURE))
from _e2e_fixture import CATALOGO_PADRAO, git, repo_sintetico  # noqa: E402

FONTE = Path(__file__).resolve().parents[1] / "src" / "volc_agent_harness"


def _missao_bruta(**over):
    m = {
        "mission_schema_version": 3,
        "mission_id": "contraprova",
        "title": "t",
        "base_ref": "0" * 40,
        "briefing": "b",
        "mode": "implementation",
        "commit_message": "c",
        "acceptance_ids": ["P10-T17-A1"],
        "ownership_envelope": ["backend"],
        "authorized_external_providers": [],
        "gates": [{"kind": "pytest", "targets": ["backend/tests"]}],
        "workers": [
            {"id": "wr", "provider": "codex", "role": "writer", "model": "gpt-5.5",
             "lens": "x", "allowed_paths": ["backend"], "writable_paths": ["backend"]},
            {"id": "rv", "provider": "codex", "role": "reviewer", "model": "gpt-5.6-sol",
             "lens": "y", "allowed_paths": ["backend"]},
        ],
    }
    m.update(over)
    return m


class SchemaTresRecusaArgvLivre(unittest.TestCase):
    """A missão declara o TIPO. Ela nunca escreve a linha de comando."""

    def _recusa(self, gates) -> str:
        with self.assertRaises(ValidationError) as e:
            MissionSpec.model_validate(_missao_bruta(gates=gates))
        return str(e.exception)

    def test_python_dash_c_nao_e_declaravel(self):
        self._recusa([{"argv": ["python3", "-c", "import os; os.remove('x')"]}])

    def test_node_dash_e_nao_e_declaravel(self):
        self._recusa([{"argv": ["node", "-e", "require('fs').rmSync('x')"]}])

    def test_shell_dash_c_nao_e_declaravel(self):
        self._recusa([{"argv": ["sh", "-c", "rm -rf .."]}])

    def test_git_reset_nao_e_declaravel(self):
        self._recusa([{"argv": ["git", "reset", "--hard", "HEAD~1"]}])

    def test_git_checkout_nao_e_declaravel(self):
        self._recusa([{"argv": ["git", "checkout", "--", "."]}])

    def test_argv_generico_nao_e_declaravel(self):
        """Nem sequer um argv inofensivo: o campo não existe no schema 3."""

        self._recusa([{"argv": ["python3", "-m", "pytest", "backend/tests", "-q"]}])

    def test_kind_desconhecido_nao_e_declaravel(self):
        self._recusa([{"kind": "generic", "argv": ["true"]}])

    def test_gate_tipado_valido_continua_aceito(self):
        m = MissionSpec.model_validate(_missao_bruta())
        self.assertEqual(m.gates[0].kind, "pytest")
        self.assertFalse(hasattr(m.gates[0], "argv"))

    def test_schema_dois_ainda_aceita_argv_como_caminho_depreciado(self):
        """Compatibilidade explícita: schema 2 é recusado ANTES do modelo, no CLI."""

        legado = _missao_bruta(
            mission_schema_version=2, mode="read_only", commit_message=None,
            acceptance_ids=[], ownership_envelope=[],
            gates=[{"argv": ["python3", "-m", "pytest", "backend", "-q"]}],
            workers=[
                {"id": "a", "provider": "codex", "model": "gpt-5.5", "lens": "x",
                 "allowed_paths": ["backend"]},
                {"id": "b", "provider": "codex", "model": "gpt-5.5", "lens": "y",
                 "allowed_paths": ["backend"]},
            ],
        )
        m = MissionSpec.model_validate(legado)
        self.assertEqual(m.gates[0].argv[0], "python3")


class PytestNaoCarregaCodigoDaMissao(unittest.TestCase):
    """Nenhuma flag de carregamento de plugin ou de código vem da missão."""

    def test_flags_livres_nao_existem_mais_no_schema(self):
        with self.assertRaises(ValidationError):
            MissionSpec.model_validate(_missao_bruta(gates=[{
                "kind": "pytest", "targets": ["backend/tests"],
                "flags": ["-p", "meu_plugin"],
            }]))

    def test_p_e_plugins_recusados_em_qualquer_campo(self):
        for campo, valor in (
            ("plugins", ["meu_plugin"]),
            ("addopts", "-p meu_plugin"),
            ("k_expression", "a and $(rm -rf /)"),
        ):
            with self.subTest(campo=campo):
                with self.assertRaises(ValidationError):
                    MissionSpec.model_validate(_missao_bruta(gates=[{
                        "kind": "pytest", "targets": ["backend/tests"], campo: valor,
                    }]))

    def test_argv_construido_desabilita_cache_e_nao_tem_p_da_missao(self):
        from volc_agent_harness.v3.gate_types import from_spec

        with TemporaryDirectory() as tmp:
            wt = Path(tmp)
            (wt / "backend" / "tests").mkdir(parents=True)
            g = from_spec(1, {"kind": "pytest", "targets": ["backend/tests"]})
            argv = g.build(worktree=wt, toolchain={"python": sys.executable})
        self.assertEqual(argv[:3], [sys.executable, "-m", "pytest"])
        self.assertIn("no:cacheprovider", argv)
        for proibido in ("-c", "-e", "--exec", "--import-mode", "--rootdir"):
            self.assertNotIn(proibido, argv)


class ConteudoIndiretoExigeCatalogo(unittest.TestCase):
    """npm_script e tracked_script só existem por ID de catálogo rastreado."""

    def test_npm_script_direto_na_missao_e_recusado(self):
        with self.assertRaises(ValidationError):
            MissionSpec.model_validate(_missao_bruta(
                gates=[{"kind": "npm_script", "script": "build"}]))

    def test_tracked_script_direto_na_missao_e_recusado(self):
        with self.assertRaises(ValidationError):
            MissionSpec.model_validate(_missao_bruta(
                gates=[{"kind": "tracked_script", "script_path": "scripts/x.py"}]))

    def test_catalogo_precisa_ser_rastreado_pelo_git(self):
        from volc_agent_harness.v3.gate_catalog import load_catalog

        with TemporaryDirectory() as tmp:
            raiz = repo_sintetico(Path(tmp))
            catalogo = raiz / "tools" / "agent-harness" / "gate-catalog.json"
            git(raiz, "rm", "-q", "--cached", str(catalogo.relative_to(raiz)))
            with self.assertRaises(HarnessFailure) as e:
                load_catalog(raiz)
            self.assertEqual(e.exception.classe, FailureClass.AUTHORIZATION_BLOCK)

    def test_gate_id_inexistente_recusa_a_missao(self):
        from volc_agent_harness.v3.gate_catalog import load_catalog, resolve

        with TemporaryDirectory() as tmp:
            raiz = repo_sintetico(Path(tmp))
            cat = load_catalog(raiz)
            with self.assertRaises(HarnessFailure) as e:
                resolve(cat, "gate-que-ninguem-declarou")
            self.assertEqual(e.exception.classe, FailureClass.SPEC_ERROR)


class DigestRevalidadoAntesDaExecucao(unittest.TestCase):
    """Mudança entre compilar e executar vira STALE_INPUT, não gate silencioso."""

    def _repo_com_script(self, tmp: Path) -> Path:
        catalogo = {
            "catalog_version": 1,
            "gates": {
                "prova-script": {
                    "kind": "tracked_script",
                    "script_path": "tools/agent-harness/prova.py",
                    "args": [],
                    "description": "script rastreado de prova",
                },
                "prova-npm": {
                    "kind": "npm_script", "script": "verifica",
                    "description": "script npm rastreado",
                },
            },
        }
        raiz = repo_sintetico(tmp, catalogo=catalogo)
        (raiz / "tools" / "agent-harness" / "prova.py").write_text(
            "print('ok')\n", encoding="utf-8")
        (raiz / "package.json").write_text(
            json.dumps({"scripts": {"verifica": "node -v"}}), encoding="utf-8")
        git(raiz, "add", "-A")
        subprocess.run(["git", "-C", str(raiz), "-c", "user.name=t",
                        "-c", "user.email=t@t", "commit", "-q", "-m", "script"],
                       check=True, capture_output=True)
        return raiz

    def test_tracked_script_alterado_depois_da_compilacao_e_recusado(self):
        from volc_agent_harness.v3.gate_resolution import (
            assert_bindings_fresh, resolve_mission_gates,
        )

        with TemporaryDirectory() as tmp:
            raiz = self._repo_com_script(Path(tmp))
            resolvidos = resolve_mission_gates(
                gates=[{"kind": "catalog", "gate_id": "prova-script"}],
                tree=raiz, toolchain={"python": sys.executable},
            )
            assert_bindings_fresh(resolvidos, tree=raiz)   # verde antes da mudança
            (raiz / "tools" / "agent-harness" / "prova.py").write_text(
                "import shutil; shutil.rmtree('/')\n", encoding="utf-8")
            with self.assertRaises(HarnessFailure) as e:
                assert_bindings_fresh(resolvidos, tree=raiz)
            self.assertIn(e.exception.classe,
                          {FailureClass.STALE_INPUT, FailureClass.AUTHORIZATION_BLOCK})

    def test_npm_script_destrutivo_indireto_e_pego_pelo_digest(self):
        from volc_agent_harness.v3.gate_resolution import (
            assert_bindings_fresh, resolve_mission_gates,
        )

        with TemporaryDirectory() as tmp:
            raiz = self._repo_com_script(Path(tmp))
            resolvidos = resolve_mission_gates(
                gates=[{"kind": "catalog", "gate_id": "prova-npm"}],
                tree=raiz, toolchain={"python": sys.executable, "npm": "/usr/bin/env"},
            )
            assert_bindings_fresh(resolvidos, tree=raiz)
            (raiz / "package.json").write_text(
                json.dumps({"scripts": {"verifica": "rm -rf .."}}), encoding="utf-8")
            with self.assertRaises(HarnessFailure) as e:
                assert_bindings_fresh(resolvidos, tree=raiz)
            self.assertIn(e.exception.classe,
                          {FailureClass.STALE_INPUT, FailureClass.AUTHORIZATION_BLOCK})

    def test_catalogo_alterado_depois_da_compilacao_e_recusado(self):
        from volc_agent_harness.v3.gate_resolution import (
            assert_bindings_fresh, resolve_mission_gates,
        )

        with TemporaryDirectory() as tmp:
            raiz = repo_sintetico(Path(tmp))
            resolvidos = resolve_mission_gates(
                gates=[{"kind": "catalog", "gate_id": "backend-unit"}],
                tree=raiz, toolchain={"python": sys.executable},
            )
            envenenado = json.loads(json.dumps(CATALOGO_PADRAO))
            envenenado["gates"]["backend-unit"]["targets"] = ["backend"]
            (raiz / "tools" / "agent-harness" / "gate-catalog.json").write_text(
                json.dumps(envenenado, indent=2), encoding="utf-8")
            with self.assertRaises(HarnessFailure) as e:
                assert_bindings_fresh(resolvidos, tree=raiz)
            self.assertIn(e.exception.classe,
                          {FailureClass.STALE_INPUT, FailureClass.AUTHORIZATION_BLOCK})


# ---------------------------------------------------------------------------
# Prova estrutural por AST. `grep` acha o texto; a AST acha a CHAMADA.
# ---------------------------------------------------------------------------

def _arvore(modulo: str) -> ast.Module:
    return ast.parse((FONTE / modulo).read_text(encoding="utf-8"))


def _nomes_chamados(arvore: ast.AST) -> set[str]:
    nomes: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call):
            alvo = no.func
            if isinstance(alvo, ast.Name):
                nomes.add(alvo.id)
            elif isinstance(alvo, ast.Attribute):
                base = alvo.value
                if isinstance(base, ast.Name):
                    nomes.add(f"{base.id}.{alvo.attr}")
                nomes.add(alvo.attr)
    return nomes


def _grafo_de_chamadas(arvore: ast.Module) -> dict[str, set[str]]:
    grafo: dict[str, set[str]] = {}
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            grafo[no.name] = _nomes_chamados(no)
    return grafo


def _alcancaveis(grafo: dict[str, set[str]], raizes: list[str]) -> set[str]:
    vistos: set[str] = set()
    pilha = list(raizes)
    while pilha:
        atual = pilha.pop()
        if atual in vistos:
            continue
        vistos.add(atual)
        for chamado in grafo.get(atual, set()):
            if chamado in grafo and chamado not in vistos:
                pilha.append(chamado)
    return vistos


class MissionResolveGatesPeloCompiladorTipado(unittest.TestCase):
    """A refutação dizia: ``mission.py não chama gate_types.from_spec``."""

    def setUp(self):
        self.arvore = _arvore("mission.py")
        self.grafo = _grafo_de_chamadas(self.arvore)
        self.alcancaveis = _alcancaveis(
            self.grafo, ["run", "run_mission", "_run_implementation_mission",
                         "_run_read_only_mission", "_compilar_missao"])
        self.chamadas = set()
        for func in self.alcancaveis:
            self.chamadas |= self.grafo[func]

    def test_resolucao_tipada_e_alcancavel_a_partir_do_entrypoint(self):
        self.assertTrue(
            {"resolve_mission_gates", "from_spec"} & self.chamadas,
            "nenhum resolvedor tipado é alcançável a partir de run_mission",
        )

    def test_ledger_e_o_unico_executor_de_gate(self):
        self.assertIn("run_gate_with_ledger", self.chamadas)

    def test_nenhum_subprocess_run_no_caminho_produtivo(self):
        self.assertNotIn("subprocess.run", self.chamadas)

    def test_mission_nao_importa_subprocess(self):
        importados = {
            alias.name
            for no in ast.walk(self.arvore) if isinstance(no, ast.Import)
            for alias in no.names
        }
        self.assertNotIn("subprocess", importados,
                         "mission.py não precisa de subprocess: gates passam pelo runner")

    def test_nao_existe_fallback_generico_de_argv(self):
        fonte = (FONTE / "mission.py").read_text(encoding="utf-8")
        self.assertNotIn("resolve_gate_argv", fonte,
                         "resolução por argv livre é o fallback genérico refutado")
        self.assertNotIn("gate.argv", fonte)


if __name__ == "__main__":
    unittest.main()
