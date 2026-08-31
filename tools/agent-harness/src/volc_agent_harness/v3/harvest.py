"""Harvest & Resume: colheita é ponto de partida, não lixo.

Seis vezes na rodada anterior um writer produziu trabalho correto e um gate
posterior — quase sempre defeituoso — barrou a entrega. Sem colheita, cada
retentativa recomeçaria do ``base_ref`` e jogaria fora o que já estava certo.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .failures import FailureClass, HarnessFailure


@dataclass
class Harvest:
    sha: str
    branch: str
    files: list[str]
    ownership_respected: bool
    green_gates: list[int]
    red_gate: int | None
    failure_class: str
    findings: list[str] = field(default_factory=list)
    next_minimal_step: str = ""
    supersedes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sha": self.sha,
            "branch": self.branch,
            "files": self.files,
            "ownership_respected": self.ownership_respected,
            "green_gates": self.green_gates,
            "red_gate": self.red_gate,
            "failure_class": self.failure_class,
            "findings": self.findings,
            "next_minimal_step": self.next_minimal_step,
            "supersedes": self.supersedes,
        }


def _git(tree: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(tree), *args], capture_output=True, text=True, check=True)
    return r.stdout.strip()


def preserve(
    *,
    tree: Path,
    branch: str,
    message: str,
    allowed_paths: Sequence[str],
    green_gates: Sequence[int] = (),
    red_gate: int | None = None,
    failure_class: str = "",
    findings: Sequence[str] = (),
    next_minimal_step: str = "",
    supersedes: Sequence[str] = (),
    author: tuple[str, str] = ("Tarcisio Bely", "tarcisio@agenciavolc.com.br"),
) -> Harvest:
    """Confere ownership, commita a colheita e devolve ``harvest.json``."""

    porcelain = _git(tree, "status", "--porcelain")
    arquivos = [linha[3:].strip() for linha in porcelain.splitlines() if linha.strip()]
    if not arquivos:
        raise HarnessFailure(
            FailureClass.SPEC_ERROR,
            "não há trabalho para colher",
            detalhe=str(tree),
        )

    fora = [
        f for f in arquivos
        if not any(f == p or f.startswith(p.rstrip("/") + "/") for p in allowed_paths)
    ]
    ownership_ok = not fora

    _git(tree, "checkout", "-q", "-b", branch)
    _git(tree, "add", "-A")
    subprocess.run(
        ["git", "-C", str(tree), "-c", f"user.name={author[0]}",
         "-c", f"user.email={author[1]}", "commit", "-q", "-m", message],
        capture_output=True, text=True, check=True,
    )
    sha = _git(tree, "rev-parse", "HEAD")

    return Harvest(
        sha=sha,
        branch=branch,
        files=arquivos,
        ownership_respected=ownership_ok,
        green_gates=list(green_gates),
        red_gate=red_gate,
        failure_class=failure_class,
        findings=list(findings),
        next_minimal_step=next_minimal_step,
        supersedes=list(supersedes),
    )


def resume_base(harvest: Harvest | None, base_sha: str) -> str:
    """A próxima tentativa parte da colheita, nunca do zero."""

    return harvest.sha if harvest is not None else base_sha


def requires_writer(failure_class: str, *, harvest: Harvest | None) -> bool:
    """Uma validação read-only, como a B4, não abre writer.

    Se a colheita existe e a falha foi de especificação ou infraestrutura, o que
    falta é consertar o gate e revalidar — não produzir código novo.
    """

    from .failures import FailureClass as F

    if harvest is None:
        return True
    return failure_class not in {
        F.SPEC_ERROR.value,
        F.INFRASTRUCTURE_ERROR.value,
        F.BASELINE_ERROR.value,
        F.OWNERSHIP_ERROR.value,
        F.AUTHORIZATION_BLOCK.value,
    }
