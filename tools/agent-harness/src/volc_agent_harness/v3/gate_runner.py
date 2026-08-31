"""GateRunner: onde o gate roda, e o ledger honesto.

Duas refutações do Sol moram aqui.

**G1** — análise de argv não contém código. O que contém é o LUGAR: worktree
descartável registrada, cwd fixo nela, ambiente sanitizado, e diff depois. Esta
abstração existe para que um backend de sandbox real possa entrar depois sem
reescrever o pipeline. Enquanto ele não existir e não for provado, ``LocalRunner``
NÃO afirma proteção do filesystem externo — apenas reduz superfície e detecta.

**G5** — o ledger mentia. A ordem no runtime era ``subprocess.run`` → ``lookup``
→ ``record``: consultava reuso DEPOIS de executar, podendo etiquetar
``REUSED_WITH_VALID_DIGEST`` sem ter reaproveitado nada, e um gate vermelho
levantava antes do bloco do ledger, então falha nunca era registrada.

A ordem correta, imposta aqui: **digest → lookup → (reuse | execute) → record →
adjudicar/levantar**.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .failures import FailureClass, HarnessFailure, classify_gate_exit


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


@dataclass
class GateOutcome:
    gate_index: int
    argv: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    execution_mode: str          # executed | reused
    status: str                  # green | red | timeout | infrastructure
    evidence_id: int | None = None
    source_evidence_id: int | None = None
    started_at: str = ""
    completed_at: str = ""
    tree_delta: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "green"

    def as_dict(self) -> dict[str, Any]:
        return {
            "gate_index": self.gate_index,
            "argv": self.argv,
            "exit_code": self.exit_code,
            "duration_s": round(self.duration_s, 3),
            "execution_mode": self.execution_mode,
            "status": self.status,
            "evidence_id": self.evidence_id,
            "source_evidence_id": self.source_evidence_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "stdout_digest": _digest(self.stdout),
            "stderr_digest": _digest(self.stderr),
            "tree_delta": self.tree_delta,
        }


class GateRunner(ABC):
    """Backend de execução. Local hoje; sandbox/container amanhã."""

    #: Declaração honesta do que o backend garante.
    contains_filesystem: bool = False
    name: str = "abstract"

    @abstractmethod
    def execute(
        self, *, argv: Sequence[str], cwd: Path, env: Mapping[str, str], timeout: int
    ) -> tuple[int, str, str]:
        ...


class LocalRunner(GateRunner):
    """Subprocesso local em worktree descartável.

    NÃO contém o filesystem externo: um teste pode escrever fora da worktree.
    O que fazemos é reduzir superfície (gates tipados), fixar o cwd, sanitizar o
    ambiente e DETECTAR alteração inesperada pelo diff posterior.
    """

    contains_filesystem = False
    name = "local"

    def execute(self, *, argv, cwd, env, timeout):
        r = subprocess.run(
            list(argv), cwd=cwd, env=dict(env), capture_output=True,
            text=True, timeout=timeout, check=False,
        )
        return r.returncode, r.stdout, r.stderr


def _snapshot(worktree: Path) -> set[str]:
    r = subprocess.run(
        ["git", "-C", str(worktree), "status", "--porcelain"],
        capture_output=True, text=True, check=False,
    )
    return {l[3:].strip() for l in r.stdout.splitlines() if l.strip()}


def run_gate_with_ledger(
    *,
    gate_index: int,
    argv: Sequence[str],
    worktree: Path,
    env: Mapping[str, str],
    timeout: int,
    ledger: Any,
    acceptance_id: str,
    base_sha: str,
    candidate_sha: str | None,
    context_digest: str,
    env_fingerprint: str,
    production_digest: str,
    test_digest: str,
    run_id: str,
    worker_id: str,
    runner: GateRunner | None = None,
    allow_reuse: bool = True,
) -> GateOutcome:
    """digest → lookup → (reuse | execute) → record. Nunca o inverso."""

    runner = runner or LocalRunner()
    comando = " ".join(argv)
    kind = f"gate_{gate_index}"

    # 1. LOOKUP ANTES. Consultar depois de executar é etiqueta falsa.
    consulta = ledger.lookup(
        acceptance_id=acceptance_id, kind=kind, command=comando,
        production_digest=production_digest, test_digest=test_digest,
        cwd=str(worktree), env_fp=env_fingerprint, ctx_digest=context_digest,
    ) if allow_reuse else {"status": "NEW_EVIDENCE", "evidence": None}

    anterior = consulta.get("evidence")
    reutilizavel = (
        consulta["status"] == "REUSED_WITH_VALID_DIGEST"
        and anterior is not None
        and anterior.get("exit_code") == 0      # vermelho NUNCA vira verde
    )

    inicio = _agora()
    if reutilizavel:
        # 2a. Reuso real: nenhum subprocesso é criado.
        resultado = GateOutcome(
            gate_index=gate_index, argv=list(argv), exit_code=0,
            stdout="", stderr="", duration_s=0.0,
            execution_mode="reused", status="green",
            source_evidence_id=anterior.get("id"),
            started_at=inicio, completed_at=_agora(),
        )
    else:
        # 2b. Execução, com snapshot antes e depois.
        antes = _snapshot(worktree)
        t0 = time.monotonic()
        try:
            exit_code, out, err = runner.execute(
                argv=argv, cwd=worktree, env=env, timeout=timeout)
            status = "green" if exit_code == 0 else None
        except subprocess.TimeoutExpired:
            exit_code, out, err, status = 124, "", "timeout", "timeout"
        dur = time.monotonic() - t0
        if status is None:
            classe = classify_gate_exit(
                exit_code=exit_code, argv=list(argv), stdout=out, stderr=err)
            status = ("infrastructure"
                      if classe is FailureClass.INFRASTRUCTURE_ERROR else "red")
        depois = _snapshot(worktree)
        resultado = GateOutcome(
            gate_index=gate_index, argv=list(argv), exit_code=exit_code,
            stdout=out, stderr=err, duration_s=dur,
            execution_mode="executed", status=status,
            started_at=inicio, completed_at=_agora(),
            tree_delta=sorted(depois - antes),
        )

    # 3. RECORD SEMPRE, inclusive vermelho, timeout e infraestrutura — antes de
    #    qualquer raise. Era exatamente isso que faltava.
    resultado.evidence_id = ledger.record(
        acceptance_id=acceptance_id, kind=kind, base_sha=base_sha,
        candidate_sha=candidate_sha, run_id=run_id, command=comando,
        cwd=str(worktree), env_fp=env_fingerprint, ctx_digest=context_digest,
        production_digest=production_digest, test_digest=test_digest,
        exit_code=resultado.exit_code,
        counts={
            "execution_mode": resultado.execution_mode,
            "status": resultado.status,
            "worker_id": worker_id,
            "stdout_digest": _digest(resultado.stdout),
            "stderr_digest": _digest(resultado.stderr),
            "source_evidence_id": resultado.source_evidence_id,
            "started_at": resultado.started_at,
            "completed_at": resultado.completed_at,
            "runner": runner.name,
            "contains_filesystem": runner.contains_filesystem,
        },
    )
    return resultado
