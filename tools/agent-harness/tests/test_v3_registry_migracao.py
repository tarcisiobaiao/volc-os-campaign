"""Evolução do registry: CREATE TABLE IF NOT EXISTS não migra nada.

Um registry criado antes das colunas `worker_id` e `role` derrubava o harness
inteiro no boot com `sqlite3.OperationalError: no such column: worker_id` — antes
de despachar qualquer revisor, e terminando só em traceback.
"""

from __future__ import annotations

import sqlite3
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from volc_agent_harness.v3.failures import FailureClass, classify_exception  # noqa: E402
from volc_agent_harness.v3.registry import (  # noqa: E402
    COLUNAS_EVOLUTIVAS, WorktreeRegistry, _colunas, _migrar,
)

SCHEMA_LEGADO = """
CREATE TABLE worktrees (
    path TEXT PRIMARY KEY, mission_id TEXT NOT NULL, branch TEXT NOT NULL,
    writer_pid INTEGER, base_sha TEXT NOT NULL, harvest_sha TEXT,
    status TEXT NOT NULL, last_heartbeat TEXT, owner TEXT, files_json TEXT,
    cleanup_eligible INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
"""

LINHA_LEGADA = (
    "/wt/legado", "missao-antiga", "agent/b", 4242, "sha-base", "harvest-sha",
    "released", "2026-08-30T00:00:00Z", "dono", "[]", 0, "2026-08-30T00:00:00Z",
)


def _banco_legado(caminho: Path) -> None:
    with sqlite3.connect(caminho) as c:
        c.executescript(SCHEMA_LEGADO)
        c.execute(
            "INSERT INTO worktrees VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", LINHA_LEGADA
        )


class MigracaoDoRegistry(unittest.TestCase):
    def test_A_banco_legado_nao_tem_as_colunas(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "r.sqlite"
            _banco_legado(p)
            with sqlite3.connect(p) as c:
                self.assertNotIn("worker_id", _colunas(c, "worktrees"))

    def test_B_C_abrir_migra_e_preserva_a_linha(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "r.sqlite"
            _banco_legado(p)
            reg = WorktreeRegistry(p)

            with sqlite3.connect(p) as c:
                cols = _colunas(c, "worktrees")
            for nome, _ in COLUNAS_EVOLUTIVAS:
                self.assertIn(nome, cols, f"{nome} precisa existir após a migração")

            legada = [r for r in reg.snapshot() if r["path"] == "/wt/legado"][0]
            self.assertEqual(legada["mission_id"], "missao-antiga")
            self.assertEqual(legada["base_sha"], "sha-base")
            self.assertEqual(legada["harvest_sha"], "harvest-sha")
            self.assertEqual(legada["status"], "released")
            self.assertEqual(legada["writer_pid"], 4242)
            self.assertIsNone(legada["worker_id"], "coluna nova nasce nula")

            reg.claim(worktree="/wt/novo", mission_id="m2", branch="b2",
                      base_sha="s2", worker_id="rv", role="reviewer")
            novo = [r for r in reg.snapshot() if r["path"] == "/wt/novo"][0]
            self.assertEqual(novo["worker_id"], "rv")
            self.assertEqual(novo["role"], "reviewer")

    def test_C_segunda_inicializacao_e_no_op(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "r.sqlite"
            _banco_legado(p)
            WorktreeRegistry(p)
            with sqlite3.connect(p) as c:
                antes = (sorted(_colunas(c, "worktrees")),
                         c.execute("SELECT * FROM worktrees ORDER BY path").fetchall())
                self.assertEqual(_migrar(c), [], "migrar de novo não altera nada")
            WorktreeRegistry(p)
            with sqlite3.connect(p) as c:
                depois = (sorted(_colunas(c, "worktrees")),
                          c.execute("SELECT * FROM worktrees ORDER BY path").fetchall())
            self.assertEqual(antes, depois)

    def test_D_banco_novo_nasce_no_schema_atual(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "novo.sqlite"
            WorktreeRegistry(p)
            with sqlite3.connect(p) as c:
                cols = _colunas(c, "worktrees")
            for nome, _ in COLUNAS_EVOLUTIVAS:
                self.assertIn(nome, cols)

    def test_E_duas_inicializacoes_concorrentes(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "r.sqlite"
            _banco_legado(p)
            barreira = threading.Barrier(2)
            erros: list[BaseException] = []

            def abrir():
                try:
                    barreira.wait(timeout=10)
                    WorktreeRegistry(p)
                except BaseException as exc:   # pragma: no cover
                    erros.append(exc)

            fios = [threading.Thread(target=abrir) for _ in range(2)]
            for f in fios:
                f.start()
            for f in fios:
                f.join(timeout=20)

            self.assertEqual(erros, [], f"migração concorrente falhou: {erros}")
            with sqlite3.connect(p) as c:
                cols = _colunas(c, "worktrees")
                linhas = c.execute("SELECT COUNT(*) FROM worktrees").fetchone()[0]
            self.assertIn("worker_id", cols)
            self.assertEqual(linhas, 1, "a linha legada continua única")

    def test_migracao_nao_usa_excecao_como_inspecao(self):
        """Inspeção explícita, não try/except OperationalError."""

        import inspect
        from volc_agent_harness.v3 import registry

        import ast

        self.assertIn("PRAGMA table_info", inspect.getsource(registry._colunas))
        # Por AST, não por texto: a docstring FALA de OperationalError de
        # propósito, para explicar por que não a usamos.
        arvore = ast.parse(inspect.getsource(registry._migrar))
        capturados = [
            ast.unparse(h.type)
            for n in ast.walk(arvore) if isinstance(n, ast.Try)
            for h in n.handlers if h.type is not None
        ]
        self.assertNotIn("OperationalError", " ".join(capturados))
        self.assertNotIn("sqlite3.OperationalError", " ".join(capturados))

    def test_falha_de_boot_e_infraestrutura(self):
        erro = sqlite3.OperationalError("no such column: worker_id")
        self.assertEqual(classify_exception(erro), FailureClass.INFRASTRUCTURE_ERROR)


if __name__ == "__main__":
    unittest.main()
