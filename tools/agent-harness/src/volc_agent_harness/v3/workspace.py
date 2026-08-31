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
from typing import Any, Sequence

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


def _normalizar(argv: Sequence[str]) -> list[list[str]]:
    """Quebra em comandos e expande flags agrupadas.

    ``rm -rf``, ``rm -r -f``, ``rm --recursive --force`` e ``rm -f -r`` são o
    mesmo comando escrito de quatro jeitos. Comparar string crua deixava três
    deles passarem.
    """

    comandos: list[list[str]] = [[]]
    for token in argv:
        if token in {"&&", "||", ";", "|"}:
            comandos.append([])
            continue
        # `sh -c "rm -rf x"` esconde o comando dentro de um argumento
        if " " in token and any(p in token for p in ("rm ", "git clean", "find ")):
            comandos.append(token.split())
            continue
        comandos[-1].append(token)

    expandidos: list[list[str]] = []
    for cmd in comandos:
        saida: list[str] = []
        for token in cmd:
            if token.startswith("--"):
                saida.append(token.lower())
            elif token.startswith("-") and len(token) > 1:
                saida.extend(f"-{letra.lower()}" for letra in token[1:])
            else:
                saida.append(token)
        expandidos.append(saida)
    return expandidos


#: (executável, flags que juntas tornam o comando destrutivo)
_ASSINATURAS_DESTRUTIVAS = (
    ("rm", {"-r", "-f"}),
    ("rm", {"--recursive", "--force"}),
    ("rm", {"-r", "--force"}),
    ("rm", {"--recursive", "-f"}),
    ("clean", {"-f"}),          # git clean -fdx e variantes
    ("clean", {"--force"}),
)


def assert_no_destructive_intent(argv: Sequence[str]) -> None:
    """Recusa qualquer gate ou comando que remova árvore.

    A comparação é por argv normalizado, não por substring: flags agrupadas,
    separadas, longas e escondidas em ``sh -c`` chegam todas ao mesmo ponto.
    """

    for cmd in _normalizar(argv):
        if not cmd:
            continue
        nomes = {Path(t).name for t in cmd if not t.startswith("-")}
        flags = {t for t in cmd if t.startswith("-")}
        for executavel, exigidas in _ASSINATURAS_DESTRUTIVAS:
            if executavel in nomes and exigidas <= flags:
                raise HarnessFailure(
                    FailureClass.AUTHORIZATION_BLOCK,
                    "comando destrutivo recusado pelo harness",
                    detalhe=f"{executavel} com {sorted(exigidas)}",
                    reproducao=" ".join(argv)[:200],
                )
        if "rmtree" in " ".join(cmd):
            raise HarnessFailure(
                FailureClass.AUTHORIZATION_BLOCK,
                "comando destrutivo recusado pelo harness",
                detalhe="shutil.rmtree",
                reproducao=" ".join(argv)[:200],
            )
