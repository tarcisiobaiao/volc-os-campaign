"""Provas do overlay efêmero de node_modules.

O defeito que originou este módulo: gates de frontend chamavam
``<primaria>/node_modules/.bin/vitest`` por caminho absoluto — o binário existia —
mas ``vitest.config.ts`` faz ``import ... from "vitest"``, resolvido por Node a
partir da worktree, que não tem ``node_modules``. O gate morria com
``ERR_MODULE_NOT_FOUND`` parecendo defeito do candidato.
"""

from __future__ import annotations

import json
import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from volc_agent_harness.gates import (
    GateConfigurationError,
    NODE_MODULES_ENV,
    declared_node_modules,
    project_node_modules_overlay,
)


@contextmanager
def _declarando(root: Path | None):
    anterior = os.environ.get(NODE_MODULES_ENV)
    if root is None:
        os.environ.pop(NODE_MODULES_ENV, None)
    else:
        os.environ[NODE_MODULES_ENV] = str(root)
    try:
        yield
    finally:
        if anterior is None:
            os.environ.pop(NODE_MODULES_ENV, None)
        else:
            os.environ[NODE_MODULES_ENV] = anterior


def _projeto_com_deps(base: Path, lock: str = '{"lockfileVersion":3}') -> Path:
    """Projeto instalado: node_modules com .bin e um lockfile ao lado."""

    projeto = base / "primaria"
    (projeto / "node_modules" / ".bin").mkdir(parents=True)
    (projeto / "node_modules" / "vitest").mkdir()
    (projeto / "package-lock.json").write_text(lock)
    return projeto / "node_modules"


def _worktree(base: Path, lock: str = '{"lockfileVersion":3}') -> Path:
    tree = base / "worktree"
    tree.mkdir()
    (tree / "package-lock.json").write_text(lock)
    return tree


class NodeOverlayTest(unittest.TestCase):
    def test_dependencia_valida_gera_vinculo_e_proveniencia_sanitizada(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            deps = _projeto_com_deps(base)
            tree = _worktree(base)
            with _declarando(deps), project_node_modules_overlay(worktree=tree) as prov:
                alvo = tree / "node_modules"
                self.assertTrue(alvo.is_symlink())
                self.assertEqual(alvo.readlink(), deps)
                self.assertTrue((alvo / "vitest").is_dir())
                self.assertEqual(prov["overlay"], "criado")
                self.assertEqual(prov["lockfile"], "package-lock.json")
                self.assertEqual(len(prov["lockfile_sha256"]), 64)
                # proveniencia nao vaza caminho pessoal completo
                self.assertTrue(str(prov["raiz"]).startswith("…"))
                self.assertNotIn(str(base), json.dumps(prov))

    def test_raiz_ausente_nao_cria_overlay(self):
        with TemporaryDirectory() as tmp:
            tree = _worktree(Path(tmp))
            with _declarando(None), project_node_modules_overlay(worktree=tree) as prov:
                self.assertIsNone(prov)
                self.assertFalse((tree / "node_modules").exists())

    def test_raiz_declarada_inexistente_falha_fechado(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            tree = _worktree(base)
            with _declarando(base / "nao-existe" / "node_modules"):
                with self.assertRaises(GateConfigurationError):
                    with project_node_modules_overlay(worktree=tree):
                        pass

    def test_raiz_sem_bin_e_recusada_como_nao_instalada(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "primaria" / "node_modules").mkdir(parents=True)
            (base / "primaria" / "package-lock.json").write_text("{}")
            tree = _worktree(base, "{}")
            with _declarando(base / "primaria" / "node_modules"):
                with self.assertRaises(GateConfigurationError):
                    declared_node_modules()

    def test_lockfile_divergente_falha_fechado(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            deps = _projeto_com_deps(base, '{"lockfileVersion":3,"a":1}')
            tree = _worktree(base, '{"lockfileVersion":3,"a":2}')
            with _declarando(deps):
                with self.assertRaises(GateConfigurationError) as erro:
                    with project_node_modules_overlay(worktree=tree):
                        pass
            self.assertIn("diverge", str(erro.exception))
            self.assertFalse((tree / "node_modules").exists())

    def test_lockfile_so_de_um_lado_falha_fechado(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            deps = _projeto_com_deps(base)
            tree = base / "worktree"
            tree.mkdir()  # sem lockfile
            with _declarando(deps):
                with self.assertRaises(GateConfigurationError):
                    with project_node_modules_overlay(worktree=tree):
                        pass

    def test_node_modules_preexistente_nao_e_sobrescrito_nem_repontado(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            deps = _projeto_com_deps(base)
            tree = _worktree(base)
            proprio = tree / "node_modules"
            proprio.mkdir()
            (proprio / "MARCA").write_text("meu")
            with _declarando(deps), project_node_modules_overlay(worktree=tree) as prov:
                self.assertEqual(prov["overlay"], "preexistente")
                self.assertFalse(proprio.is_symlink())
                self.assertEqual((proprio / "MARCA").read_text(), "meu")
            self.assertTrue((proprio / "MARCA").is_file())

    def test_limpeza_apos_sucesso(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            deps = _projeto_com_deps(base)
            tree = _worktree(base)
            with _declarando(deps), project_node_modules_overlay(worktree=tree):
                self.assertTrue((tree / "node_modules").is_symlink())
            self.assertFalse((tree / "node_modules").exists())
            self.assertFalse((tree / "node_modules").is_symlink())
            self.assertTrue((deps / ".bin").is_dir())  # origem intacta

    def test_limpeza_apos_falha_ou_timeout(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            deps = _projeto_com_deps(base)
            tree = _worktree(base)
            for erro in (RuntimeError("gate vermelho"), TimeoutError("timeout")):
                with self.subTest(erro=type(erro).__name__):
                    with self.assertRaises(type(erro)):
                        with _declarando(deps), project_node_modules_overlay(worktree=tree):
                            self.assertTrue((tree / "node_modules").is_symlink())
                            raise erro
                    self.assertFalse((tree / "node_modules").is_symlink())
                    self.assertFalse((tree / "node_modules").exists())


if __name__ == "__main__":
    unittest.main()
