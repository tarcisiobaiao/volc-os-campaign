"""Evidence Ledger: prova válida não se repete.

Na rodada anterior, revisores foram reexecutados sobre inputs idênticos e gates
focais rodaram várias vezes sem que nada material tivesse mudado. O ledger torna
o reuso explícito e auditável: uma prova vale enquanto o digest de TODOS os seus
inputs materiais permanecer igual.

Há provas que nunca são reutilizadas, por definição — o gate final de
integração, o scanner de segredo, o diff-check, a prova de árvore limpa, a
equivalência material e o build final. Elas atestam o estado do mundo agora, não
uma propriedade do código.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence (
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
    reviewer          TEXT,
    finding           TEXT,
    counterproof      TEXT,
    valid             INTEGER NOT NULL DEFAULT 1,
    invalidated_reason TEXT,
    run_id            TEXT NOT NULL,
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_lookup
    ON evidence(acceptance_id, kind, input_digest, valid);
"""

#: Provas que atestam o estado do mundo, não uma propriedade do código.
NUNCA_REUTILIZAVEIS = frozenset({
    "integration_gate",
    "secret_scan",
    "diff_check",
    "clean_tree",
    "material_equivalence",
    "final_build",
})


class Status(str):
    REUSED = "REUSED_WITH_VALID_DIGEST"
    REEXECUTED = "REEXECUTED_INPUT_CHANGED"
    INVALIDATED = "INVALIDATED"
    NEW = "NEW_EVIDENCE"


def digest_files(tree: Path, paths: Iterable[str]) -> str:
    """Digest estável do conteúdo material. Ordem não importa."""

    h = hashlib.sha256()
    for p in sorted(set(paths)):
        alvo = tree / p
        h.update(p.encode())
        h.update(b"\0")
        h.update(alvo.read_bytes() if alvo.is_file() else b"<ausente>")
        h.update(b"\0")
    return h.hexdigest()


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EvidenceLedger:
    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def record(
        self,
        *,
        acceptance_id: str,
        kind: str,
        base_sha: str,
        run_id: str,
        command: str,
        production_digest: str,
        test_digest: str,
        candidate_sha: str | None = None,
        exit_code: int | None = None,
        counts: Mapping[str, Any] | None = None,
        reviewer: str | None = None,
        finding: str | None = None,
        counterproof: str | None = None,
    ) -> int:
        input_digest = hashlib.sha256(
            f"{kind}|{production_digest}|{test_digest}|{command}".encode()
        ).hexdigest()
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO evidence(acceptance_id,kind,base_sha,candidate_sha,input_digest,"
                "production_digest,test_digest,command,exit_code,counts_json,reviewer,finding,"
                "counterproof,valid,run_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
                (
                    acceptance_id, kind, base_sha, candidate_sha, input_digest,
                    production_digest, test_digest, command, exit_code,
                    json.dumps(dict(counts or {}), ensure_ascii=False),
                    reviewer, finding, counterproof, run_id, _agora(),
                ),
            )
            return int(cur.lastrowid)

    def lookup(
        self,
        *,
        acceptance_id: str,
        kind: str,
        command: str,
        production_digest: str,
        test_digest: str,
    ) -> dict[str, Any]:
        """Decide entre reutilizar e reexecutar."""

        if kind in NUNCA_REUTILIZAVEIS:
            return {
                "status": Status.NEW,
                "reason": f"'{kind}' atesta o estado do mundo e nunca é reutilizada",
                "evidence": None,
            }
        input_digest = hashlib.sha256(
            f"{kind}|{production_digest}|{test_digest}|{command}".encode()
        ).hexdigest()
        with self._conn() as c:
            linha = c.execute(
                "SELECT * FROM evidence WHERE acceptance_id=? AND kind=? AND input_digest=? "
                "AND valid=1 ORDER BY id DESC LIMIT 1",
                (acceptance_id, kind, input_digest),
            ).fetchone()
            if linha is not None:
                return {
                    "status": Status.REUSED,
                    "reason": "todos os inputs materiais mantiveram o digest",
                    "evidence": dict(linha),
                }
            anterior = c.execute(
                "SELECT * FROM evidence WHERE acceptance_id=? AND kind=? "
                "ORDER BY id DESC LIMIT 1",
                (acceptance_id, kind),
            ).fetchone()
        if anterior is None:
            return {"status": Status.NEW, "reason": "primeira execução", "evidence": None}
        mudou = []
        if anterior["production_digest"] != production_digest:
            mudou.append("código de produção")
        if anterior["test_digest"] != test_digest:
            mudou.append("testes")
        if anterior["command"] != command:
            mudou.append("comando")
        return {
            "status": Status.REEXECUTED,
            "reason": "mudou: " + ", ".join(mudou or ["input material"]),
            "evidence": dict(anterior),
        }

    def invalidate(self, *, acceptance_id: str, reason: str) -> int:
        with self._conn() as c:
            cur = c.execute(
                "UPDATE evidence SET valid=0, invalidated_reason=? "
                "WHERE acceptance_id=? AND valid=1",
                (reason, acceptance_id),
            )
            return cur.rowcount
