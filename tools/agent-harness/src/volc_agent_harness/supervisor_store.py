"""Ledger SQLite durável do supervisor, fora das fontes editoriais."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


ACTIVE_STATES = {
    "claimed",
    "initializing",
    "running",
    "gating",
    "reviewing",
}

ALLOWED_TRANSITIONS = {
    "claimed": {"initializing", "running", "cancelled", "interrupted"},
    "initializing": {"running", "failed", "cancelled", "interrupted"},
    "running": {
        "gating",
        "reviewing",
        "ready_for_human",
        "changes_requested",
        "blocked",
        "failed",
        "cancelled",
        "interrupted",
    },
    "gating": {
        "reviewing",
        "changes_requested",
        "blocked",
        "failed",
        "cancelled",
        "interrupted",
    },
    "reviewing": {
        "ready_for_human",
        "changes_requested",
        "blocked",
        "failed",
        "cancelled",
        "interrupted",
    },
    "interrupted": {"claimed", "blocked"},
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat()


def ownership_overlaps(left: list[str], right: list[str]) -> bool:
    """Compara prefixos de ownership sem confundir `src/a` com `src/ab`."""

    def parts(value: str) -> tuple[str, ...]:
        return tuple(part for part in Path(value).parts if part not in {".", ""})

    for a_value in left:
        a = parts(a_value)
        for b_value in right:
            b = parts(b_value)
            shorter = min(len(a), len(b))
            if a[:shorter] == b[:shorter]:
                return True
    return False


class SupervisorStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS claims (
                    idempotency_key TEXT PRIMARY KEY,
                    supervisor_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    roadmap_sha TEXT NOT NULL,
                    contract_digest TEXT NOT NULL,
                    base_sha TEXT NOT NULL,
                    lineage_root_sha TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    owner_nonce TEXT NOT NULL,
                    owner_pid INTEGER NOT NULL,
                    ownership_json TEXT NOT NULL,
                    lease_expires_at TEXT NOT NULL,
                    run_dir TEXT,
                    candidate_sha TEXT,
                    resume_base_sha TEXT,
                    tree_fingerprint TEXT,
                    finding_fingerprint TEXT,
                    failure_fingerprint TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS claims_state_idx ON claims(state);
                CREATE INDEX IF NOT EXISTS claims_task_idx ON claims(task_id);

                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    idempotency_key TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_event_hash TEXT,
                    event_hash TEXT NOT NULL,
                    FOREIGN KEY(idempotency_key) REFERENCES claims(idempotency_key)
                );
                """
            )
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(claims)").fetchall()
            }
            if "tree_fingerprint" not in columns:
                connection.execute(
                    "ALTER TABLE claims ADD COLUMN tree_fingerprint TEXT"
                )
            if "finding_fingerprint" not in columns:
                connection.execute(
                    "ALTER TABLE claims ADD COLUMN finding_fingerprint TEXT"
                )
            if "failure_fingerprint" not in columns:
                connection.execute(
                    "ALTER TABLE claims ADD COLUMN failure_fingerprint TEXT"
                )
            if "contract_digest" not in columns:
                connection.execute(
                    "ALTER TABLE claims ADD COLUMN contract_digest TEXT"
                )
            if "lineage_root_sha" not in columns:
                connection.execute(
                    "ALTER TABLE claims ADD COLUMN lineage_root_sha TEXT"
                )
            if "resume_base_sha" not in columns:
                connection.execute(
                    "ALTER TABLE claims ADD COLUMN resume_base_sha TEXT"
                )
            connection.commit()

    @staticmethod
    def idempotency_key(
        task_id: str, contract_digest: str, base_sha: str, attempt: int
    ) -> str:
        raw = f"{task_id}:{contract_digest}:{base_sha}:{attempt}".encode()
        return hashlib.sha256(raw).hexdigest()

    def claim(
        self,
        *,
        supervisor_id: str,
        job_id: str,
        task_id: str,
        roadmap_sha: str,
        contract_digest: str,
        base_sha: str,
        lineage_root_sha: str,
        attempt: int,
        ownership: list[str],
        lease_seconds: int,
        max_writer_concurrency: int,
    ) -> dict[str, Any] | None:
        key = self.idempotency_key(task_id, contract_digest, base_sha, attempt)
        now = utc_now()
        expires = now + timedelta(seconds=lease_seconds)
        nonce = uuid.uuid4().hex
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM claims WHERE idempotency_key = ?", (key,)
            ).fetchone()
            if existing is not None:
                return None

            active = connection.execute(
                "SELECT * FROM claims WHERE state IN "
                "('claimed','initializing','running','gating','reviewing')"
            ).fetchall()
            live = []
            for row in active:
                if datetime.fromisoformat(row["lease_expires_at"]) <= now:
                    try:
                        os.kill(int(row["owner_pid"]), 0)
                    except (OSError, ValueError):
                        owner_alive = False
                    else:
                        owner_alive = True
                    if owner_alive:
                        live.append(row)
                        continue
                    connection.execute(
                        "UPDATE claims SET state='interrupted', updated_at=? "
                        "WHERE idempotency_key=?",
                        (_iso(now), row["idempotency_key"]),
                    )
                    self._append_event_connection(
                        connection,
                        row["idempotency_key"],
                        "job.interrupted",
                        {"reason": "lease_expired"},
                    )
                    continue
                live.append(row)
            if len(live) >= max_writer_concurrency:
                return None
            if any(
                ownership_overlaps(ownership, json.loads(row["ownership_json"]))
                for row in live
            ):
                return None

            connection.execute(
                """
                INSERT INTO claims (
                    idempotency_key, supervisor_id, job_id, task_id,
                    roadmap_sha, contract_digest, base_sha, lineage_root_sha,
                    attempt, state, owner_nonce,
                    owner_pid, ownership_json, lease_expires_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'claimed', ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    supervisor_id,
                    job_id,
                    task_id,
                    roadmap_sha,
                    contract_digest,
                    base_sha,
                    lineage_root_sha,
                    attempt,
                    nonce,
                    os.getpid(),
                    json.dumps(ownership, ensure_ascii=False),
                    _iso(expires),
                    _iso(now),
                    _iso(now),
                ),
            )
            self._append_event_connection(
                connection,
                key,
                "job.claimed",
                {"task_id": task_id, "job_id": job_id, "attempt": attempt},
            )
            return {
                "idempotency_key": key,
                "owner_nonce": nonce,
                "lease_expires_at": _iso(expires),
            }

    def renew(
        self,
        key: str,
        owner_nonce: str,
        lease_seconds: int,
    ) -> bool:
        now = utc_now()
        expires = now + timedelta(seconds=lease_seconds)
        with self.transaction() as connection:
            current = connection.execute(
                "SELECT state, owner_nonce FROM claims WHERE idempotency_key=?",
                (key,),
            ).fetchone()
            if (
                current is None
                or current["owner_nonce"] != owner_nonce
                or current["state"] not in ACTIVE_STATES
            ):
                return False
            connection.execute(
                "UPDATE claims SET lease_expires_at=?, updated_at=? "
                "WHERE idempotency_key=?",
                (_iso(expires), _iso(now), key),
            )
            self._append_event_connection(
                connection,
                key,
                "job.heartbeat",
                {"lease_expires_at": _iso(expires)},
            )
            return True

    def transition(
        self,
        key: str,
        state: str,
        *,
        payload: dict[str, Any] | None = None,
        run_dir: str | None = None,
        candidate_sha: str | None = None,
        resume_base_sha: str | None = None,
        tree_fingerprint: str | None = None,
        finding_fingerprint: str | None = None,
        failure_fingerprint: str | None = None,
        error: str | None = None,
    ) -> None:
        now = _iso()
        with self.transaction() as connection:
            current = connection.execute(
                "SELECT state FROM claims WHERE idempotency_key=?", (key,)
            ).fetchone()
            if current is None:
                raise KeyError(key)
            allowed = ALLOWED_TRANSITIONS.get(current["state"], set())
            if state not in allowed:
                raise ValueError(
                    f"transição ilegal: {current['state']} -> {state}"
                )
            connection.execute(
                """
                UPDATE claims
                SET state=?, run_dir=COALESCE(?, run_dir),
                    candidate_sha=COALESCE(?, candidate_sha),
                    resume_base_sha=COALESCE(?, resume_base_sha),
                    tree_fingerprint=COALESCE(?, tree_fingerprint),
                    finding_fingerprint=COALESCE(?, finding_fingerprint),
                    failure_fingerprint=COALESCE(?, failure_fingerprint),
                    error=COALESCE(?, error), updated_at=?
                WHERE idempotency_key=?
                """,
                (
                    state,
                    run_dir,
                    candidate_sha,
                    resume_base_sha,
                    tree_fingerprint,
                    finding_fingerprint,
                    failure_fingerprint,
                    error,
                    now,
                    key,
                ),
            )
            self._append_event_connection(
                connection,
                key,
                f"job.{state}",
                payload or {},
            )

    def _append_event_connection(
        self,
        connection: sqlite3.Connection,
        key: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        previous = connection.execute(
            "SELECT event_hash FROM events WHERE idempotency_key=? "
            "ORDER BY sequence DESC LIMIT 1",
            (key,),
        ).fetchone()
        previous_hash = previous["event_hash"] if previous else None
        occurred_at = _iso()
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        event_material = json.dumps(
            {
                "idempotency_key": key,
                "event_type": event_type,
                "occurred_at": occurred_at,
                "payload": payload,
                "previous_event_hash": previous_hash,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
        event_hash = hashlib.sha256(event_material).hexdigest()
        event_id = hashlib.sha256(
            f"{key}:{event_type}:{event_hash}".encode()
        ).hexdigest()
        connection.execute(
            """
            INSERT INTO events (
                event_id, idempotency_key, event_type, occurred_at,
                payload_json, previous_event_hash, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                key,
                event_type,
                occurred_at,
                payload_json,
                previous_hash,
                event_hash,
            ),
        )

    def snapshot(self) -> list[dict[str, Any]]:
        """Fotografia operacional pública, sem credenciais de ownership."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT
                    idempotency_key, supervisor_id, job_id, task_id,
                    roadmap_sha, contract_digest, base_sha,
                    lineage_root_sha, attempt, state, owner_pid,
                    ownership_json, lease_expires_at, run_dir,
                    candidate_sha, resume_base_sha, tree_fingerprint,
                    finding_fingerprint, failure_fingerprint, error,
                    created_at, updated_at
                FROM claims
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def latest(self, task_id: str, contract_digest: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM claims WHERE task_id=? AND contract_digest=? "
                "ORDER BY attempt DESC, created_at DESC LIMIT 1",
                (task_id, contract_digest),
            ).fetchone()
        return dict(row) if row is not None else None

    def history(self, task_id: str, contract_digest: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM claims WHERE task_id=? AND contract_digest=? "
                "ORDER BY attempt ASC, created_at ASC",
                (task_id, contract_digest),
            ).fetchall()
        return [dict(row) for row in rows]
