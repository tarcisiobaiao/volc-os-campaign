"""GateRunner: onde o gate roda, e o ledger que reserva antes de executar.

Duas refutações moram aqui.

**G1** — análise de argv não contém código. O que contém é o LUGAR: worktree
descartável registrada, cwd fixo nela, ambiente sanitizado, e diff depois. Esta
abstração existe para que um backend de sandbox real possa entrar depois sem
reescrever o pipeline. Enquanto ele não existir e não for provado, ``LocalRunner``
NÃO afirma proteção do filesystem externo — apenas reduz superfície e detecta.

**G5** — a primeira correção trocou a ordem (``lookup`` antes de executar) e
achou que bastava. Não bastava: ``lookup`` responde, não reserva. Dois
consumidores simultâneos recebiam ambos ``NEW_EVIDENCE`` e ambos executavam. A
ordem agora é **identidade → claim transacional → (reuso | execução) →
conclusão fenced**, e não existe caminho que pule o claim.
"""

from __future__ import annotations

import hashlib
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .failures import FailureClass, classify_gate_exit
from .ledger import ClaimOutcome, GateIdentity


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


#: Estado do gate → estado terminal do claim. Um mapa explícito, porque
#: "infrastructure" e "infra" divergirem em silêncio custaria uma prova perdida.
_ESTADO_DO_CLAIM = {
    "green": "green",
    "red": "red",
    "timeout": "timeout",
    "infrastructure": "infra",
}

#: E o caminho de volta, para relatar o que outro consumidor observou.
_STATUS_DO_ESTADO = {
    "green": "green",
    "red": "red",
    "timeout": "timeout",
    "infra": "infrastructure",
    "abandoned": "infrastructure",
}


@dataclass
class GateOutcome:
    gate_index: int
    argv: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    execution_mode: str          # executed | reused | waited | reclaimed | lease_timeout
    status: str                  # green | red | timeout | infrastructure
    evidence_id: int | None = None
    source_evidence_id: int | None = None
    claim_outcome: str = ""
    fencing_token: int = 0
    waited_seconds: float = 0.0
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
            "claim_outcome": self.claim_outcome,
            "fencing_token": self.fencing_token,
            "waited_seconds": round(self.waited_seconds, 3),
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
    binding_digest: str = "",
    lease_seconds: int = 900,
    wait_seconds: float = 30.0,
) -> GateOutcome:
    """identidade → claim → (reuso | execução) → conclusão fenced. Nunca o inverso."""

    runner = runner or LocalRunner()
    comando = " ".join(argv)
    identidade = GateIdentity.for_gate(
        acceptance_id=acceptance_id, gate_index=gate_index, argv=argv,
        context_digest=context_digest, production_digest=production_digest,
        test_digest=test_digest, env_fingerprint=env_fingerprint,
        binding_digest=binding_digest,
    )

    # 1. CLAIM ANTES. `lookup` responde uma pergunta; só o claim reserva.
    claim = ledger.acquire(
        identidade, run_id=run_id, worker_id=worker_id,
        lease_seconds=lease_seconds, wait_seconds=wait_seconds,
        allow_reuse=allow_reuse,
    )
    inicio = _agora()
    comum = dict(
        gate_index=gate_index, argv=list(argv), claim_outcome=claim.outcome.value,
        fencing_token=claim.fencing_token, waited_seconds=claim.waited_seconds,
        started_at=inicio,
    )

    if claim.outcome is ClaimOutcome.REUSED_GREEN:
        # 2a. Reuso real: nenhum subprocesso é criado. `waited` quando houve
        #     espera de verdade — a evidência precisa distinguir os dois.
        anterior = claim.evidence or {}
        return GateOutcome(
            exit_code=0, stdout="", stderr="", duration_s=0.0,
            execution_mode="waited" if claim.aguardou else "reused",
            status="green", source_evidence_id=anterior.get("id"),
            evidence_id=anterior.get("id"), completed_at=_agora(), **comum,
        )

    if claim.outcome is ClaimOutcome.OBSERVED_NON_GREEN:
        # 2b. Outro consumidor rodou o MESMO experimento e ele não ficou verde.
        #     Repetir não muda o resultado, e não-verde nunca vira verde.
        anterior = claim.evidence or {}
        return GateOutcome(
            exit_code=int(anterior.get("exit_code") or 1), stdout="", stderr="",
            duration_s=0.0, execution_mode="waited",
            status=_STATUS_DO_ESTADO.get(claim.previous_state or "red", "red"),
            source_evidence_id=anterior.get("id"),
            evidence_id=anterior.get("id"), completed_at=_agora(), **comum,
        )

    if claim.outcome is ClaimOutcome.LEASE_TIMEOUT:
        # 2c. Alguém vivo segura o claim. Não roubamos e não executamos — mas a
        #     espera esgotada é fato auditável, então vira evidência não-verde.
        evidencia = ledger.record(
            acceptance_id=acceptance_id, kind=identidade.kind, base_sha=base_sha,
            candidate_sha=candidate_sha, run_id=run_id, command=comando,
            cwd=str(worktree), env_fp=env_fingerprint, ctx_digest=context_digest,
            production_digest=production_digest, test_digest=test_digest,
            exit_code=None,
            counts={"execution_mode": "lease_timeout", "status": "infrastructure",
                    "claim_outcome": claim.outcome.value, "worker_id": worker_id,
                    "waited_seconds": round(claim.waited_seconds, 3)},
            identity=identidade,
        )
        return GateOutcome(
            exit_code=75, stdout="", stderr="lease de outro consumidor ainda vivo",
            duration_s=claim.waited_seconds, execution_mode="lease_timeout",
            status="infrastructure", evidence_id=evidencia, completed_at=_agora(),
            **comum,
        )

    # 3. Execução, com snapshot antes e depois. Só quem segura o token chega aqui.
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

    modo = ("reclaimed" if claim.outcome is ClaimOutcome.RECLAIMED_AFTER_EXPIRY
            else "executed")
    resultado = GateOutcome(
        exit_code=exit_code, stdout=out, stderr=err, duration_s=dur,
        execution_mode=modo, status=status, completed_at=_agora(),
        tree_delta=sorted(depois - antes), **comum,
    )

    # 4. CONCLUSÃO FENCED, sempre — verde, vermelho, timeout e infraestrutura —
    #    ANTES de qualquer raise do chamador. Gravar evidência e fechar o claim
    #    acontecem na mesma transação: quem perdeu o lease não escreve.
    resultado.evidence_id = ledger.complete(
        claim, state=_ESTADO_DO_CLAIM[status], base_sha=base_sha,
        candidate_sha=candidate_sha, run_id=run_id, command=comando,
        cwd=str(worktree), production_digest=production_digest,
        test_digest=test_digest, exit_code=resultado.exit_code,
        counts={
            "execution_mode": resultado.execution_mode,
            "status": resultado.status,
            "claim_outcome": claim.outcome.value,
            "fencing_token": claim.fencing_token,
            "worker_id": worker_id,
            "stdout_digest": _digest(resultado.stdout),
            "stderr_digest": _digest(resultado.stderr),
            "started_at": resultado.started_at,
            "completed_at": resultado.completed_at,
            "runner": runner.name,
            "contains_filesystem": runner.contains_filesystem,
        },
    )
    if resultado.evidence_id is None:
        # Perdemos o lease durante a execução. O resultado existe, mas não é
        # autoridade: quem retomou o claim é que responde por esta identidade.
        resultado.execution_mode = "abandoned"
    return resultado
