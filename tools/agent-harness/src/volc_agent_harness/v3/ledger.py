"""Evidence Ledger: prova válida não se repete, e prova em curso não duplica.

Na primeira rodada o ledger sabia dizer "reuso" — depois do fato. A refutação de
G5 foi física: dois consumidores com o mesmo digest e uma ``Barrier`` executaram
o gate DUAS vezes e gravaram DUAS evidências ``EXECUTED``. ``lookup`` responde
uma pergunta; ele não RESERVA nada, e entre a resposta e a execução cabe o outro
consumidor inteiro.

O que fecha a corrida é o **execution claim**: uma linha por identidade lógica,
criada sob ``BEGIN IMMEDIATE``, com dono, lease e fencing token. Quem tem o
claim executa; quem chega depois aguarda de forma limitada e recebe um veredito
nomeado — ``reused_green``, ``observed_non_green``, ``lease_timeout`` ou
``reclaimed_after_expiry``.

⚠️ LIMITE DECLARADO — isto NÃO é exactly-once
---------------------------------------------
Um crash depois do claim e antes da conclusão deixa o lease vencer, e o próximo
consumidor reexecuta. É a escolha correta (a alternativa é travar um digest para
sempre), mas é reexecução real. O que está provado é mais estreito e mais
honesto: **no máximo uma execução física concorrente**, e **fencing da
conclusão** — o dono que perdeu o lease não grava resultado.

Há provas que nunca são reutilizadas, por definição — o gate final de
integração, o scanner de segredo, o diff-check, a prova de árvore limpa, a
equivalência material e o build final. Elas atestam o estado do mundo agora, não
uma propriedade do código.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

#: Versão do contrato de identidade lógica. Entra no digest de propósito:
#: mudar a forma de identificar uma prova invalida as antigas em vez de
#: compará-las com régua diferente.
LEDGER_CONTRACT_VERSION = 2

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

CREATE TABLE IF NOT EXISTS execution_claim (
    logical_key      TEXT PRIMARY KEY,
    contract_version INTEGER NOT NULL,
    acceptance_id    TEXT NOT NULL,
    kind             TEXT NOT NULL,
    input_digest     TEXT NOT NULL,
    owner_token      TEXT NOT NULL,
    fencing_token    INTEGER NOT NULL,
    state            TEXT NOT NULL,
    claimed_at       TEXT NOT NULL,
    heartbeat_at     TEXT NOT NULL,
    lease_until      REAL NOT NULL,
    completed_at     TEXT,
    run_id           TEXT NOT NULL,
    worker_id        TEXT NOT NULL,
    evidence_id      INTEGER,
    owner_pid        INTEGER
);
CREATE INDEX IF NOT EXISTS idx_claim_estado ON execution_claim(state, lease_until);
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

#: Estados terminais de um claim. Só ``green`` é reaproveitável.
ESTADOS_TERMINAIS = frozenset({"green", "red", "timeout", "infra", "abandoned"})
ESTADOS_NAO_VERDES = frozenset({"red", "timeout", "infra", "abandoned"})


class Status(str):
    REUSED = "REUSED_WITH_VALID_DIGEST"
    REEXECUTED = "REEXECUTED_INPUT_CHANGED"
    INVALIDATED = "INVALIDATED"
    NEW = "NEW_EVIDENCE"


class ClaimOutcome(str, Enum):
    """O que aconteceu com a tentativa de reservar a execução."""

    ACQUIRED = "acquired"
    REUSED_GREEN = "reused_green"
    OBSERVED_NON_GREEN = "observed_non_green"
    LEASE_TIMEOUT = "lease_timeout"
    RECLAIMED_AFTER_EXPIRY = "reclaimed_after_expiry"


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


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


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
    return _sha("|".join(partes))


def _input_digest(
    *,
    kind: str,
    production_digest: str,
    test_digest: str,
    command_digest: str,
    env_fingerprint: str,
    context_digest: str,
    contract_version: int = LEDGER_CONTRACT_VERSION,
) -> str:
    """Digest do conjunto de inputs materiais de uma prova.

    ``cwd`` NÃO entra, de propósito. A versão anterior o incluía, e como cada
    run nasce numa worktree nova o digest nunca repetia: o ledger jamais
    reutilizou uma prova em produção, só em teste. O caminho absoluto do
    diretório não é insumo material — o conteúdo dos arquivos, o contexto e o
    ambiente são. ``cwd`` continua gravado na coluna, para auditoria.
    """

    return _sha("|".join([
        str(contract_version), kind, production_digest, test_digest,
        command_digest, env_fingerprint, context_digest,
    ]))


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
    return _sha("|".join(partes))


@dataclass(frozen=True)
class GateIdentity:
    """Identidade lógica de uma execução de gate.

    Todos os elementos materiais exigidos pelo contrato entram: aceite,
    contexto, produção, testes, comando/gate, ambiente e versão do contrato.
    """

    acceptance_id: str
    kind: str
    context_digest: str
    production_digest: str
    test_digest: str
    command_digest: str
    env_fingerprint: str
    contract_version: int = LEDGER_CONTRACT_VERSION

    @staticmethod
    def for_gate(
        *,
        acceptance_id: str,
        gate_index: int,
        argv: Sequence[str],
        kind_prefix: str = "gate",
        context_digest: str,
        production_digest: str,
        test_digest: str,
        env_fingerprint: str,
        binding_digest: str = "",
        cwd: str = "",
    ) -> "GateIdentity":
        del cwd    # gravado como metadado, nunca como identidade — ver _input_digest
        return GateIdentity(
            acceptance_id=acceptance_id,
            kind=f"{kind_prefix}_{gate_index}",
            context_digest=context_digest,
            production_digest=production_digest,
            test_digest=test_digest,
            command_digest=_sha(" ".join(argv) + "|" + binding_digest),
            env_fingerprint=env_fingerprint,
        )

    @property
    def input_digest(self) -> str:
        return _input_digest(
            kind=self.kind,
            production_digest=self.production_digest,
            test_digest=self.test_digest,
            command_digest=self.command_digest,
            env_fingerprint=self.env_fingerprint,
            context_digest=self.context_digest,
            contract_version=self.contract_version,
        )

    @property
    def logical_key(self) -> str:
        return _sha(f"{self.contract_version}|{self.acceptance_id}|{self.input_digest}")


@dataclass(frozen=True)
class Claim:
    """Reserva de execução. ``owner_token`` é ``None`` quando não houve reserva."""

    identity: GateIdentity
    outcome: ClaimOutcome
    owner_token: str | None
    fencing_token: int
    run_id: str = ""
    worker_id: str = ""
    waited_seconds: float = 0.0
    #: Houve espera REAL por um claim alheio. `waited_seconds` sempre traz
    #: alguns microssegundos do próprio laço; usá-lo como booleano marcava todo
    #: reuso como "waited" e apagava a distinção que a evidência precisa fazer.
    aguardou: bool = False
    previous_state: str | None = None
    evidence: dict[str, Any] | None = None

    @property
    def executa(self) -> bool:
        """Só quem segura o token executa."""

        return self.outcome in {ClaimOutcome.ACQUIRED,
                                ClaimOutcome.RECLAIMED_AFTER_EXPIRY}

    def as_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "fencing_token": self.fencing_token,
            "aguardou": self.aguardou,
            "waited_seconds": round(self.waited_seconds, 3),
            "previous_state": self.previous_state,
            "logical_key": self.identity.logical_key,
        }


def _conectar(path: Path) -> sqlite3.Connection:
    """Conexão com WAL negociado, não imposto.

    ``PRAGMA journal_mode=WAL`` pede lock exclusivo e o busy handler do SQLite
    não é chamado em todos os caminhos dessa troca. Impor o pragma a cada
    conexão fazia duas inicializações simultâneas colidirem com
    ``OperationalError: database is locked`` — o defeito que ainda deixa
    ``test_E_duas_inicializacoes_concorrentes`` intermitente no registry.
    Aqui o modo é CONSULTADO primeiro e só trocado quando difere, com repetição
    limitada.
    """

    c = sqlite3.connect(path, timeout=30.0, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=30000")
    atual = (c.execute("PRAGMA journal_mode").fetchone()[0] or "").lower()
    if atual != "wal":
        for tentativa in range(12):
            try:
                c.execute("PRAGMA journal_mode=WAL")
                break
            except sqlite3.OperationalError:
                time.sleep(0.05 * (tentativa + 1))
        else:                                   # WAL indisponível não é fatal
            pass
    c.execute("PRAGMA synchronous=FULL")
    return c


@dataclass
class EvidenceLedger:
    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        c = self._conn()
        try:
            c.executescript(SCHEMA)
        finally:
            c.close()

    def _conn(self) -> sqlite3.Connection:
        return _conectar(self.path)

    # -- evidência ---------------------------------------------------------

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
        identity: GateIdentity | None = None,
    ) -> int:
        c = self._conn()
        try:
            return self._inserir_evidencia(
                c, acceptance_id=acceptance_id, kind=kind, base_sha=base_sha,
                run_id=run_id, command=command, production_digest=production_digest,
                test_digest=test_digest, candidate_sha=candidate_sha, cwd=cwd,
                env_fp=env_fp, ctx_digest=ctx_digest, exit_code=exit_code,
                counts=counts, reviewer=reviewer, finding=finding,
                counterproof=counterproof, identity=identity,
            )
        finally:
            c.close()

    def _inserir_evidencia(
        self, c: sqlite3.Connection, *, acceptance_id: str, kind: str, base_sha: str,
        run_id: str, command: str, production_digest: str, test_digest: str,
        candidate_sha: str | None, cwd: str, env_fp: str | None,
        ctx_digest: str | None, exit_code: int | None,
        counts: Mapping[str, Any] | None, reviewer: str | None, finding: str | None,
        counterproof: str | None, identity: GateIdentity | None,
    ) -> int:
        fingerprint = env_fp if env_fp is not None else env_fingerprint()
        ctx = ctx_digest or ""
        digest = (identity.input_digest if identity is not None else _input_digest(
            kind=kind, production_digest=production_digest, test_digest=test_digest,
            command_digest=_sha(command), env_fingerprint=fingerprint,
            context_digest=ctx,
        ))
        cur = c.execute(
            "INSERT INTO evidence(acceptance_id,kind,base_sha,candidate_sha,input_digest,"
            "production_digest,test_digest,command,cwd,env_fingerprint,context_digest,"
            "exit_code,counts_json,reviewer,finding,counterproof,valid,run_id,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
            (
                acceptance_id, kind, base_sha, candidate_sha, digest,
                production_digest, test_digest, command, cwd, fingerprint, ctx,
                exit_code, json.dumps(dict(counts or {}), ensure_ascii=False),
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
        """Decide entre reutilizar e reexecutar. NÃO reserva — ver ``acquire``."""

        if kind in NUNCA_REUTILIZAVEIS:
            return {
                "status": Status.NEW,
                "reason": f"'{kind}' atesta o estado do mundo e nunca é reutilizada",
                "evidence": None,
            }
        fingerprint = env_fp if env_fp is not None else env_fingerprint()
        ctx = ctx_digest or ""
        digest = _input_digest(
            kind=kind, production_digest=production_digest, test_digest=test_digest,
            command_digest=_sha(command), env_fingerprint=fingerprint,
            context_digest=ctx,
        )
        return self._lookup_por_digest(
            acceptance_id=acceptance_id, kind=kind, input_digest=digest,
            production_digest=production_digest, test_digest=test_digest,
            command=command, cwd=cwd, fingerprint=fingerprint, ctx=ctx,
        )

    def _lookup_por_digest(
        self, *, acceptance_id: str, kind: str, input_digest: str,
        production_digest: str, test_digest: str, command: str, cwd: str,
        fingerprint: str, ctx: str,
    ) -> dict[str, Any]:
        c = self._conn()
        try:
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
        finally:
            c.close()
        if anterior is None:
            return {"status": Status.NEW, "reason": "primeira execução", "evidence": None}
        mudou = []
        if anterior["production_digest"] != production_digest:
            mudou.append("código de produção")
        if anterior["test_digest"] != test_digest:
            mudou.append("testes")
        if anterior["command"] != command:
            mudou.append("comando")
        if anterior["env_fingerprint"] != fingerprint:
            mudou.append("ambiente")
        if anterior["context_digest"] != ctx:
            mudou.append("contexto (aceite, base, candidato, toolchain ou manifests)")
        return {
            "status": Status.REEXECUTED,
            "reason": "mudou: " + ", ".join(mudou or ["input material"]),
            "evidence": anterior and dict(anterior),
        }

    def invalidate(self, *, acceptance_id: str, reason: str) -> int:
        c = self._conn()
        try:
            cur = c.execute(
                "UPDATE evidence SET valid=0, invalidated_reason=? "
                "WHERE acceptance_id=? AND valid=1",
                (reason, acceptance_id),
            )
            return cur.rowcount
        finally:
            c.close()

    def evidencias(self, *, acceptance_id: str | None = None) -> list[dict[str, Any]]:
        c = self._conn()
        try:
            if acceptance_id is None:
                cur = c.execute("SELECT * FROM evidence ORDER BY id")
            else:
                cur = c.execute(
                    "SELECT * FROM evidence WHERE acceptance_id=? ORDER BY id",
                    (acceptance_id,))
            return [dict(r) for r in cur]
        finally:
            c.close()

    # -- execution claim ---------------------------------------------------

    def claim_atual(self, identity: GateIdentity) -> dict[str, Any] | None:
        c = self._conn()
        try:
            linha = c.execute(
                "SELECT * FROM execution_claim WHERE logical_key=?",
                (identity.logical_key,),
            ).fetchone()
            return dict(linha) if linha is not None else None
        finally:
            c.close()

    def claims_ativos(self) -> list[dict[str, Any]]:
        c = self._conn()
        try:
            return [dict(r) for r in c.execute(
                "SELECT * FROM execution_claim WHERE state='running' ORDER BY claimed_at")]
        finally:
            c.close()

    def acquire(
        self,
        identity: GateIdentity,
        *,
        run_id: str,
        worker_id: str,
        lease_seconds: int = 900,
        wait_seconds: float = 30.0,
        poll_seconds: float = 0.1,
        allow_reuse: bool = True,
    ) -> Claim:
        """Reserva a execução, ou diz por que não reservou.

        Regras, todas dentro de ``BEGIN IMMEDIATE`` — o lock nasce ANTES do
        SELECT, senão existe janela real entre consultar e reivindicar:

        1. ninguém reivindicou ainda → ``acquired``;
        2. claim verde e reutilizável → ``reused_green``, sem subprocesso;
        3. claim vivo de outro dono → aguarda de forma limitada;
        4. lease vencido → ``reclaimed_after_expiry``, com fencing token NOVO;
        5. terminou não-verde enquanto aguardávamos → ``observed_non_green``;
        6. esgotou a espera com lease vivo → ``lease_timeout``.
        """

        if identity.kind in NUNCA_REUTILIZAVEIS:
            allow_reuse = False
        limite = time.monotonic() + max(0.0, wait_seconds)
        inicio = time.monotonic()
        esperou = False

        while True:
            resultado = self._tentar_claim(
                identity, run_id=run_id, worker_id=worker_id,
                lease_seconds=lease_seconds, allow_reuse=allow_reuse,
                esperou=esperou,
            )
            if resultado is not None:
                return dataclass_replace(
                    resultado, time.monotonic() - inicio, esperou)
            esperou = True
            if time.monotonic() >= limite:
                return Claim(
                    identity=identity, outcome=ClaimOutcome.LEASE_TIMEOUT,
                    owner_token=None, fencing_token=0, run_id=run_id,
                    worker_id=worker_id, waited_seconds=time.monotonic() - inicio,
                )
            time.sleep(poll_seconds)

    def _tentar_claim(
        self, identity: GateIdentity, *, run_id: str, worker_id: str,
        lease_seconds: int, allow_reuse: bool, esperou: bool,
    ) -> Claim | None:
        """Uma tentativa transacional. ``None`` significa 'aguarde e tente de novo'."""

        chave = identity.logical_key
        agora_ts = time.time()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            linha = c.execute(
                "SELECT * FROM execution_claim WHERE logical_key=?", (chave,)
            ).fetchone()

            if linha is not None and linha["state"] == "running" \
                    and float(linha["lease_until"]) > agora_ts:
                c.execute("COMMIT")
                return None                       # lease vivo: não se rouba

            if linha is not None and linha["state"] == "green" and allow_reuse:
                evidencia = None
                if linha["evidence_id"] is not None:
                    alvo = c.execute(
                        "SELECT * FROM evidence WHERE id=? AND valid=1",
                        (linha["evidence_id"],),
                    ).fetchone()
                    evidencia = dict(alvo) if alvo is not None else None
                if evidencia is not None and evidencia["exit_code"] == 0:
                    c.execute("COMMIT")
                    return Claim(
                        identity=identity, outcome=ClaimOutcome.REUSED_GREEN,
                        owner_token=None, fencing_token=int(linha["fencing_token"]),
                        run_id=run_id, worker_id=worker_id,
                        previous_state="green", evidence=evidencia,
                    )

            if linha is not None and esperou and linha["state"] in ESTADOS_NAO_VERDES:
                # Aguardamos ESTE claim terminar e ele terminou não-verde. Repetir
                # o mesmo experimento não muda o resultado; o consumidor recebe o
                # veredito observado, e vermelho nunca vira verde.
                evidencia = None
                if linha["evidence_id"] is not None:
                    alvo = c.execute(
                        "SELECT * FROM evidence WHERE id=?", (linha["evidence_id"],)
                    ).fetchone()
                    evidencia = dict(alvo) if alvo is not None else None
                c.execute("COMMIT")
                return Claim(
                    identity=identity, outcome=ClaimOutcome.OBSERVED_NON_GREEN,
                    owner_token=None, fencing_token=int(linha["fencing_token"]),
                    run_id=run_id, worker_id=worker_id,
                    previous_state=linha["state"], evidence=evidencia,
                )

            token = secrets.token_hex(16)
            expirou = (linha is not None and linha["state"] == "running"
                       and float(linha["lease_until"]) <= agora_ts)
            fencing = int(linha["fencing_token"]) + 1 if linha is not None else 1
            lease_until = agora_ts + max(1, int(lease_seconds))
            if linha is None:
                c.execute(
                    "INSERT INTO execution_claim(logical_key,contract_version,acceptance_id,"
                    "kind,input_digest,owner_token,fencing_token,state,claimed_at,"
                    "heartbeat_at,lease_until,run_id,worker_id,owner_pid) "
                    "VALUES(?,?,?,?,?,?,?,'running',?,?,?,?,?,?)",
                    (chave, identity.contract_version, identity.acceptance_id,
                     identity.kind, identity.input_digest, token, fencing,
                     _agora(), _agora(), lease_until, run_id, worker_id, os.getpid()),
                )
            else:
                # Condicional pelo fencing token: se outro consumidor tomou o
                # claim entre o SELECT e aqui, a atualização não pega ninguém.
                alteradas = c.execute(
                    "UPDATE execution_claim SET owner_token=?,fencing_token=?,state='running',"
                    "claimed_at=?,heartbeat_at=?,lease_until=?,completed_at=NULL,"
                    "run_id=?,worker_id=?,owner_pid=?,evidence_id=NULL "
                    "WHERE logical_key=? AND fencing_token=?",
                    (token, fencing, _agora(), _agora(), lease_until, run_id,
                     worker_id, os.getpid(), chave, int(linha["fencing_token"])),
                ).rowcount
                if alteradas == 0:
                    c.execute("COMMIT")
                    return None
            c.execute("COMMIT")
            return Claim(
                identity=identity,
                outcome=(ClaimOutcome.RECLAIMED_AFTER_EXPIRY if expirou
                         else ClaimOutcome.ACQUIRED),
                owner_token=token, fencing_token=fencing, run_id=run_id,
                worker_id=worker_id,
                previous_state=linha["state"] if linha is not None else None,
            )
        except BaseException:
            c.execute("ROLLBACK")
            raise
        finally:
            c.close()

    def heartbeat(self, claim: Claim, *, lease_seconds: int = 900) -> bool:
        """Renova o lease. ``False`` significa que o claim já não é nosso."""

        if claim.owner_token is None:
            return False
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            alteradas = c.execute(
                "UPDATE execution_claim SET heartbeat_at=?, lease_until=? "
                "WHERE logical_key=? AND owner_token=? AND fencing_token=? "
                "AND state='running'",
                (_agora(), time.time() + max(1, int(lease_seconds)),
                 claim.identity.logical_key, claim.owner_token, claim.fencing_token),
            ).rowcount
            c.execute("COMMIT")
            return alteradas == 1
        except BaseException:
            c.execute("ROLLBACK")
            raise
        finally:
            c.close()

    def complete(
        self,
        claim: Claim,
        *,
        state: str,
        base_sha: str,
        run_id: str,
        command: str,
        production_digest: str,
        test_digest: str,
        cwd: str = "",
        candidate_sha: str | None = None,
        exit_code: int | None = None,
        counts: Mapping[str, Any] | None = None,
    ) -> int | None:
        """Grava evidência e fecha o claim, na MESMA transação e sob fencing.

        Gravar a evidência fora da transação do fencing deixava a porta aberta
        para o dono antigo — o que perdeu o lease — registrar resultado sobre uma
        execução que já não era a autoridade. Aqui, ou o token ainda é o corrente
        e a evidência nasce, ou nada é escrito e o retorno é ``None``.
        """

        if claim.owner_token is None:
            return None
        if state not in ESTADOS_TERMINAIS:
            raise ValueError(f"estado terminal desconhecido: {state}")
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            linha = c.execute(
                "SELECT * FROM execution_claim WHERE logical_key=?",
                (claim.identity.logical_key,),
            ).fetchone()
            if (linha is None
                    or linha["owner_token"] != claim.owner_token
                    or int(linha["fencing_token"]) != claim.fencing_token):
                c.execute("COMMIT")
                return None                      # perdeu o lease: não escreve
            evidence_id = self._inserir_evidencia(
                c, acceptance_id=claim.identity.acceptance_id,
                kind=claim.identity.kind, base_sha=base_sha, run_id=run_id,
                command=command, production_digest=production_digest,
                test_digest=test_digest, candidate_sha=candidate_sha, cwd=cwd,
                env_fp=claim.identity.env_fingerprint,
                ctx_digest=claim.identity.context_digest, exit_code=exit_code,
                counts=counts, reviewer=None, finding=None, counterproof=None,
                identity=claim.identity,
            )
            c.execute(
                "UPDATE execution_claim SET state=?,completed_at=?,heartbeat_at=?,"
                "evidence_id=? WHERE logical_key=? AND fencing_token=?",
                (state, _agora(), _agora(), evidence_id,
                 claim.identity.logical_key, claim.fencing_token),
            )
            c.execute("COMMIT")
            return evidence_id
        except BaseException:
            c.execute("ROLLBACK")
            raise
        finally:
            c.close()


def dataclass_replace(claim: Claim, waited: float, aguardou: bool = False) -> Claim:
    """``Claim`` é frozen; a espera medida só existe depois do laço."""

    return Claim(
        identity=claim.identity, outcome=claim.outcome, owner_token=claim.owner_token,
        fencing_token=claim.fencing_token, run_id=claim.run_id,
        worker_id=claim.worker_id, waited_seconds=waited, aguardou=aguardou,
        previous_state=claim.previous_state, evidence=claim.evidence,
    )
