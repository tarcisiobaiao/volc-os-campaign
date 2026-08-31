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
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, isolation_level="IMMEDIATE")
        c.row_factory = sqlite3.Row
        return c

    def claim(
        self, *, worktree: str, mission_id: str, branch: str, base_sha: str,
        writer_pid: int | None = None, owner: str | None = None,
    ) -> None:
        """Reivindica a worktree. Dois writers no mesmo caminho é impossível."""

        with self._conn() as c:
            atual = c.execute(
                "SELECT * FROM worktrees WHERE path=?", (worktree,)
            ).fetchone()
            if atual is not None and atual["status"] == "writer_active":
                vivo = _pid_vivo(atual["writer_pid"])
                if vivo:
                    raise HarnessFailure(
                        FailureClass.OWNERSHIP_ERROR,
                        "worktree já tem um writer ativo",
                        detalhe=(
                            f"{worktree} ocupada por missão {atual['mission_id']} "
                            f"(pid {atual['writer_pid']})"
                        ),
                        evidencia={"worktree": worktree, "pid": atual["writer_pid"]},
                    )
            c.execute(
                "INSERT INTO worktrees(path,mission_id,branch,writer_pid,base_sha,status,"
                "last_heartbeat,owner,files_json,cleanup_eligible,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,0,?) "
                "ON CONFLICT(path) DO UPDATE SET mission_id=excluded.mission_id,"
                "branch=excluded.branch,writer_pid=excluded.writer_pid,"
                "status=excluded.status,last_heartbeat=excluded.last_heartbeat,"
                "owner=excluded.owner",
                (worktree, mission_id, branch, writer_pid, base_sha, "writer_active",
                 _agora(), owner, "[]", _agora()),
            )

    def release(self, *, worktree: str, status: str, harvest_sha: str | None = None) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE worktrees SET status=?, writer_pid=NULL, harvest_sha=COALESCE(?,harvest_sha),"
                " last_heartbeat=? WHERE path=?",
                (status, harvest_sha, _agora(), worktree),
            )

    def snapshot(self) -> list[dict[str, Any]]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM worktrees ORDER BY created_at")]

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


def _pid_vivo(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError, PermissionError):
        return False
    return True
