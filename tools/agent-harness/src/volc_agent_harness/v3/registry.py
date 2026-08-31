"""Registro transacional de worktrees. Um writer por worktree, sempre."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .failures import FailureClass, HarnessFailure
from .sqlite_support import conectar

SCHEMA = """
CREATE TABLE IF NOT EXISTS worktrees (
    path            TEXT PRIMARY KEY,
    mission_id      TEXT NOT NULL,
    branch          TEXT NOT NULL,
    writer_pid      INTEGER,
    base_sha        TEXT NOT NULL,
    harvest_sha     TEXT,
    status          TEXT NOT NULL,
    last_heartbeat  TEXT,
    owner           TEXT,
    worker_id       TEXT,
    role            TEXT,
    files_json      TEXT,
    cleanup_eligible INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);
"""


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class WorktreeRegistry:
    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        c = self._conn()
        try:
            c.executescript(SCHEMA)
            _migrar(c)
        finally:
            c.close()

    def _conn(self) -> sqlite3.Connection:
        # isolation_level=None: controlamos a transação à mão, porque o BEGIN
        # implícito do sqlite3 só dispara no primeiro DML — e o SELECT de
        # verificação viria ANTES dele, deixando uma janela real entre checar e
        # inserir. Aqui o BEGIN IMMEDIATE é explícito e vem primeiro.
        #
        # O WAL é NEGOCIADO, não imposto: `PRAGMA journal_mode=WAL` pede lock
        # exclusivo e o busy handler do SQLite não é acionado em todos os
        # caminhos dessa troca. Impor a cada conexão fazia duas inicializações
        # simultâneas colidirem com `OperationalError: database is locked` —
        # era isso que deixava `test_E_duas_inicializacoes_concorrentes`
        # intermitente, e "inicialização concorrente provada" era uma prova que
        # falhava em ~40% das execuções.
        #
        # A conexão mora em `sqlite_support`, API interna pública: importar
        # `_conectar` privado do ledger era acoplamento que ninguém vê até
        # alguém renomear o símbolo.
        return conectar(self.path)

    def claim(
        self, *, worktree: str, mission_id: str, branch: str, base_sha: str,
        writer_pid: int | None = None, owner: str | None = None,
        worker_id: str | None = None, role: str | None = None,
    ) -> None:
        """Reivindica a worktree. Dois writers no mesmo caminho é impossível."""

        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")   # o lock nasce ANTES do SELECT
            atual = c.execute(
                "SELECT * FROM worktrees WHERE path=?", (worktree,)
            ).fetchone()
            if atual is not None and atual["status"] == "writer_active":
                if _pid_vivo(atual["writer_pid"]):
                    raise HarnessFailure(
                        FailureClass.OWNERSHIP_ERROR,
                        "worktree já tem um writer ativo",
                        detalhe=(
                            f"{worktree} ocupada por missão {atual['mission_id']} "
                            f"(pid {atual['writer_pid']})"
                        ),
                        evidencia={"worktree": worktree, "pid": atual["writer_pid"]},
                    )
            if atual is None:
                c.execute(
                    "INSERT INTO worktrees(path,mission_id,branch,writer_pid,base_sha,status,"
                    "last_heartbeat,owner,files_json,cleanup_eligible,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,0,?)",
                    (worktree, mission_id, branch, writer_pid, base_sha,
                     "writer_active" if (role or "writer") == "writer" else "reader_active",
                     _agora(), owner, "[]", _agora()),
                )
            else:
                # Atualização CONDICIONAL: nunca rouba um claim ativo cujo dono
                # ainda vive. O UPSERT incondicional anterior permitia isso.
                alteradas = c.execute(
                    "UPDATE worktrees SET mission_id=?,branch=?,writer_pid=?,status=?,"
                    "last_heartbeat=?,owner=? WHERE path=? AND status<>'writer_active'",
                    (mission_id, branch, writer_pid,
                     "writer_active" if (role or "writer") == "writer" else "reader_active",
                     _agora(), owner, worktree),
                ).rowcount
                if alteradas == 0:
                    raise HarnessFailure(
                        FailureClass.OWNERSHIP_ERROR,
                        "perdeu a corrida pela worktree",
                        detalhe=worktree,
                    )
            c.execute(
                "UPDATE worktrees SET worker_id=?, role=? WHERE path=?",
                (worker_id, role, worktree),
            )
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise
        finally:
            c.close()

    def release(self, *, worktree: str, status: str, harvest_sha: str | None = None) -> None:
        c = self._conn()
        try:
            c.execute(
                "UPDATE worktrees SET status=?, writer_pid=NULL, harvest_sha=COALESCE(?,harvest_sha),"
                " last_heartbeat=? WHERE path=?",
                (status, harvest_sha, _agora(), worktree),
            )
        finally:
            c.close()

    def snapshot(self) -> list[dict[str, Any]]:
        c = self._conn()
        try:
            return [dict(r) for r in c.execute("SELECT * FROM worktrees ORDER BY created_at")]
        finally:
            c.close()

    def gc_plan(self) -> list[dict[str, Any]]:
        """Plano de limpeza. Candidato não integrado NUNCA é elegível."""

        plano = []
        for r in self.snapshot():
            elegivel = (
                r["status"] in {"released", "superseded"}
                and not r["harvest_sha"]
            )
            plano.append({
                "path": r["path"],
                "mission_id": r["mission_id"],
                "status": r["status"],
                "harvest_sha": r["harvest_sha"],
                "cleanup_eligible": elegivel,
                "motivo": (
                    "sem colheita e já liberada" if elegivel
                    else "preserva candidato não integrado" if r["harvest_sha"]
                    else "ainda ativa"
                ),
            })
        return plano


#: Colunas acrescentadas depois da primeira versão do registry. `CREATE TABLE
#: IF NOT EXISTS` não evolui um banco que já existe — ele simplesmente não faz
#: nada. Um registry criado antes destas colunas quebrava o boot inteiro com
#: `sqlite3.OperationalError: no such column: worker_id`, e o harness morria
#: antes de despachar qualquer revisor.
COLUNAS_EVOLUTIVAS: tuple[tuple[str, str], ...] = (
    ("worker_id", "TEXT"),
    ("role", "TEXT"),
)


def _colunas(conn: sqlite3.Connection, tabela: str) -> set[str]:
    return {linha[1] for linha in conn.execute(f"PRAGMA table_info({tabela})")}


def _migrar(conn: sqlite3.Connection) -> list[str]:
    """Acrescenta só o que falta, sob transação, preservando os registros.

    Inspeção explícita do schema, não `try/except OperationalError`: uma exceção
    capturada esconde a diferença entre "coluna já existe" e "o banco está
    corrompido".
    """

    existentes = _colunas(conn, "worktrees")
    faltando = [(nome, tipo) for nome, tipo in COLUNAS_EVOLUTIVAS
                if nome not in existentes]
    if not faltando:
        return []                      # inicialização repetida é no-op
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Reconsulta dentro da transação: outra instância pode ter migrado
        # entre a leitura acima e o lock.
        existentes = _colunas(conn, "worktrees")
        aplicadas = []
        for nome, tipo in COLUNAS_EVOLUTIVAS:
            if nome not in existentes:
                conn.execute(f"ALTER TABLE worktrees ADD COLUMN {nome} {tipo}")
                aplicadas.append(nome)
        conn.execute("COMMIT")
        return aplicadas
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def _pid_vivo(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError, PermissionError):
        return False
    return True
