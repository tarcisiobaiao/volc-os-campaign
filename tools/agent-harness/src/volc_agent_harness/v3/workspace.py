"""Preparo de worktree sem destruição.

O harness NUNCA executa ``rm -rf`` para preparar um caminho. Um diretório
preexistente pode conter colheita não integrada, trabalho de outro writer ou
simplesmente algo que ninguém autorizou apagar. A guarda é fail-closed: ou o
caminho está livre, ou é uma worktree registrada e reutilizável, ou escolhemos
um caminho novo — nunca apagamos.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .failures import FailureClass, HarnessFailure


@dataclass(frozen=True)
class WorkspacePlan:
    path: Path
    reused: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {"path": str(self.path), "reused": self.reused, "reason": self.reason}


def prepare(
    *,
    desired: Path,
    registry: Any | None = None,
    mission_id: str = "",
    allow_unique_fallback: bool = True,
) -> WorkspacePlan:
    """Devolve um caminho utilizável sem jamais apagar nada.

    Ordem: caminho livre → worktree registrada e liberada da MESMA missão →
    caminho único novo. Se nada disso valer, falha fechado.
    """

    desired = Path(desired)
    if not desired.exists():
        return WorkspacePlan(desired, reused=False, reason="caminho livre")

    registrada = None
    if registry is not None:
        registrada = next(
            (r for r in registry.snapshot() if r["path"] == str(desired)), None
        )

    if registrada is not None:
        if registrada["status"] == "writer_active":
            raise HarnessFailure(
                FailureClass.OWNERSHIP_ERROR,
                "caminho ocupado por writer ativo",
                detalhe=f"{desired} pertence à missão {registrada['mission_id']}",
                reproducao=f"consulte o registry para {desired}",
            )
        if registrada.get("harvest_sha"):
            raise HarnessFailure(
                FailureClass.AUTHORIZATION_BLOCK,
                "caminho guarda colheita não integrada; apagar exige decisão humana",
                detalhe=f"{desired} -> harvest {registrada['harvest_sha']}",
            )
        if registrada["mission_id"] == mission_id:
            return WorkspacePlan(desired, reused=True, reason="worktree registrada da mesma missão")

    if allow_unique_fallback:
        for _ in range(8):
            candidato = desired.with_name(f"{desired.name}-{secrets.token_hex(3)}")
            if not candidato.exists():
                return WorkspacePlan(candidato, reused=False, reason="caminho único novo")

    raise HarnessFailure(
        FailureClass.OWNERSHIP_ERROR,
        "caminho preexistente e não reutilizável; o harness não apaga diretório",
        detalhe=str(desired),
        reproducao=f"ls -la {desired}",
    )


def assert_no_destructive_intent(argv: list[str] | tuple[str, ...]) -> None:
    """Recusa qualquer gate ou comando que tente remover árvore."""

    texto = " ".join(argv)
    proibidos = ("rm -rf", "rm -fr", "rm -r ", "shutil.rmtree", "git clean -", "--force-remove")
    achado = [p for p in proibidos if p in texto]
    if achado:
        raise HarnessFailure(
            FailureClass.AUTHORIZATION_BLOCK,
            "comando destrutivo recusado pelo harness",
            detalhe=", ".join(achado),
            reproducao=texto[:200],
        )
