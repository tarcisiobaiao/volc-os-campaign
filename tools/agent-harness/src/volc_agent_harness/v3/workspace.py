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


#: Executáveis que um gate pode invocar. Allowlist, não blacklist: o Sol provou
#: que `find alvo -delete` e `sh -c` com tabulação atravessavam a lista negra.
_EXECUTAVEIS_DE_GATE = frozenset({
    "python", "python3", "python3.14", "pytest", "tsc", "vitest", "vite",
    "node", "npm", "npx", "env", "true", "false", "git", "compileall",
})

#: Shells nunca entram: dentro deles cabe qualquer coisa.
_SHELLS = frozenset({"sh", "bash", "zsh", "fish", "dash", "ksh"})


def assert_gate_executable_is_allowed(argv: Sequence[str]) -> None:
    """Recusa shell e executável fora da allowlist.

    Blacklist de comandos destrutivos é um jogo perdido: sempre falta uma
    variante. Aqui o gate declara o que roda, e o que não está previsto não roda.
    """

    if not argv:
        raise HarnessFailure(FailureClass.SPEC_ERROR, "gate sem argv")
    i = 0
    if Path(argv[0]).name == "env":
        i = 1
        while i < len(argv) and "=" in argv[i] and not argv[i].startswith("="):
            i += 1
    if i >= len(argv):
        raise HarnessFailure(FailureClass.SPEC_ERROR, "gate com env, mas sem comando")
    nome = Path(argv[i]).name
    if nome in _SHELLS:
        raise HarnessFailure(
            FailureClass.AUTHORIZATION_BLOCK,
            "gate não pode invocar shell",
            detalhe=nome,
            reproducao=" ".join(argv)[:200],
        )
    if nome not in _EXECUTAVEIS_DE_GATE:
        raise HarnessFailure(
            FailureClass.AUTHORIZATION_BLOCK,
            "executável de gate fora da allowlist",
            detalhe=f"{nome} não está entre {sorted(_EXECUTAVEIS_DE_GATE)}",
            reproducao=" ".join(argv)[:200],
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
        # Qualquer whitespace, não só espaço: o Sol passou tabulação.
        if any(c.isspace() for c in token):
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
    ("find", {"-delete"}),      # find alvo -delete apaga sem rm
    ("find", {"-exec"}),        # find ... -exec rm {} +
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
