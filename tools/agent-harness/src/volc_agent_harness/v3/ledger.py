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
    cwd               TEXT NOT NULL DEFAULT '',
    env_fingerprint   TEXT NOT NULL DEFAULT '',
    context_digest    TEXT NOT NULL DEFAULT '',
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


#: Variáveis que mudam materialmente o resultado de um gate. Valores de segredo
#: NUNCA entram: só a PRESENÇA da chave, e o hash do conjunto.
_ENV_MATERIAL = (
    "PATH", "PYTHONPATH", "VIRTUAL_ENV", "VOLC_HARNESS_NODE_MODULES",
    "PYTHONDONTWRITEBYTECODE", "NODE_ENV", "TZ", "LANG",
)


def env_fingerprint(env: Mapping[str, str] | None = None) -> str:
    """Impressão do ambiente, sem valor de segredo.

    Uma prova medida com outro PATH, outro venv ou outro overlay de node não é a
    mesma prova. Mas o valor de nenhuma credencial entra aqui — só o nome das
    chaves presentes e o conteúdo das variáveis materiais e não sensíveis.
    """

    import os as _os

    fonte = dict(env if env is not None else _os.environ)
    partes = []
    for chave in _ENV_MATERIAL:
        partes.append(f"{chave}={fonte.get(chave, '')}")
    sensiveis = sorted(
        k for k in fonte
        if any(m in k.upper() for m in ("KEY", "TOKEN", "SECRET", "PASSWORD", "OAUTH"))
    )
    partes.append("presentes=" + ",".join(sensiveis))  # nomes, nunca valores
    return hashlib.sha256("|".join(partes).encode()).hexdigest()


def _input_digest(*partes: str) -> str:
    """Digest do conjunto de inputs materiais de uma prova."""

    return hashlib.sha256("|".join(partes).encode()).hexdigest()


def context_digest(
    *,
    acceptance_text: str,
    base_sha: str,
    candidate_sha: str | None,
    lineage_root: str | None,
    toolchain: Mapping[str, str] | None = None,
    manifests: Mapping[str, str] | None = None,
) -> str:
    """Contexto material de uma prova, além do código e dos testes.

    O texto canônico do aceite entra: se o critério mudou, a prova antiga não
    responde mais à mesma pergunta. Toolchain e lockfiles entram porque o mesmo
    comando sobre outra versão de dependência é outro experimento.
    """

    partes = [
        f"acceptance={acceptance_text}",
        f"base={base_sha}",
        f"candidate={candidate_sha or ''}",
        f"lineage={lineage_root or ''}",
    ]
    for nome, valor in sorted((toolchain or {}).items()):
        partes.append(f"tool:{nome}={valor}")
    for nome, valor in sorted((manifests or {}).items()):
        partes.append(f"manifest:{nome}={valor}")
    return hashlib.sha256("|".join(partes).encode()).hexdigest()


@dataclass
class EvidenceLedger:
    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        # IMMEDIATE + WAL: o ledger é escrito por lanes concorrentes.
        c = sqlite3.connect(self.path, timeout=30.0, isolation_level="IMMEDIATE")
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=FULL")
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
        cwd: str = "",
        env_fp: str | None = None,
        ctx_digest: str | None = None,
        exit_code: int | None = None,
        counts: Mapping[str, Any] | None = None,
        reviewer: str | None = None,
        finding: str | None = None,
        counterproof: str | None = None,
    ) -> int:
        fingerprint = env_fp if env_fp is not None else env_fingerprint()
        ctx = ctx_digest or ""
        input_digest = _input_digest(
            kind, production_digest, test_digest, command, cwd, fingerprint, ctx
        )
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO evidence(acceptance_id,kind,base_sha,candidate_sha,input_digest,"
                "production_digest,test_digest,command,cwd,env_fingerprint,context_digest,"
                "exit_code,counts_json,reviewer,finding,counterproof,valid,run_id,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
                (
                    acceptance_id, kind, base_sha, candidate_sha, input_digest,
                    production_digest, test_digest, command, cwd, fingerprint, ctx, exit_code,
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
        cwd: str = "",
        env_fp: str | None = None,
        ctx_digest: str | None = None,
    ) -> dict[str, Any]:
        """Decide entre reutilizar e reexecutar."""

        if kind in NUNCA_REUTILIZAVEIS:
            return {
                "status": Status.NEW,
                "reason": f"'{kind}' atesta o estado do mundo e nunca é reutilizada",
                "evidence": None,
            }
        fingerprint = env_fp if env_fp is not None else env_fingerprint()
        ctx = ctx_digest or ""
        input_digest = _input_digest(
            kind, production_digest, test_digest, command, cwd, fingerprint, ctx
        )
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
        if anterior["cwd"] != cwd:
            mudou.append("diretório de trabalho")
        if anterior["env_fingerprint"] != fingerprint:
            mudou.append("ambiente")
        if anterior["context_digest"] != ctx:
            mudou.append("contexto (aceite, base, candidato, toolchain ou manifests)")
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
