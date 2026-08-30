"""Execução portátil e fail-closed dos gates de uma missão.

Worktrees Git não carregam ambientes virtuais ignorados.  Um gate pode declarar
``backend/.venv/bin/python`` por ser a identidade do ambiente da aplicação, mas
esse caminho normalmente só existe na worktree principal.  A resolução abaixo
reaproveita *somente* esse interpretador, sem copiar o venv nem cair
silenciosamente no Python do harness.
"""

from __future__ import annotations

import os
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from typing import Iterator


class GateConfigurationError(RuntimeError):
    """O gate não possui um executável verificável."""


@dataclass(frozen=True)
class ResolvedGate:
    argv: list[str]
    executable_index: int
    declared_executable: str
    resolved_executable: str


def _command_index(argv: Sequence[str]) -> int:
    if not argv:
        raise GateConfigurationError("gate sem argv")
    if Path(argv[0]).name != "env":
        return 0

    # Suporta o subconjunto seguro usado nas missões: `env NAME=VALUE comando`.
    # Opções de `env` mudam a interpretação e precisam ser declaradas de forma
    # explícita no harness antes de serem aceitas.
    index = 1
    while index < len(argv) and "=" in argv[index] and not argv[index].startswith("="):
        name, _value = argv[index].split("=", 1)
        if not name or not name.replace("_", "a").isalnum():
            raise GateConfigurationError(f"atribuição inválida em gate: {argv[index]!r}")
        index += 1
    if index >= len(argv):
        raise GateConfigurationError("gate com env, mas sem comando")
    if argv[index].startswith("-"):
        raise GateConfigurationError("opção de env não suportada em gate")
    return index


def _git_worktree_roots(repo: Path) -> list[Path]:
    completed = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    roots: list[Path] = []
    for line in completed.stdout.splitlines():
        if line.startswith("worktree "):
            root = Path(line.removeprefix("worktree ")).resolve()
            if root not in roots:
                roots.append(root)
    return roots


def _git_primary_worktree(repo: Path) -> Path:
    """Return the repository's primary worktree, never an agent-owned tree.

    ``git worktree list --porcelain`` documents the main worktree as the first
    entry.  Agent worktrees are writable by the model, so their ignored venvs
    cannot be trusted as gate executables.
    """

    roots = _git_worktree_roots(repo)
    if not roots:
        raise GateConfigurationError("repositório sem worktree primária registrada")
    return roots[0]


def _is_project_venv_python(value: str) -> bool:
    parts = Path(value).parts
    return len(parts) >= 3 and parts[-3:] in {
        (".venv", "bin", "python"),
        (".venv", "bin", "python3"),
        (".venv", "bin", "python3.14"),
    }


def find_project_venv(*, repo: Path, worktree: Path) -> Path | None:
    """Encontra o venv canônico somente na worktree primária do repositório."""

    del worktree  # explicita que uma worktree de agente nunca é fonte confiável
    candidate = (_git_primary_worktree(repo) / "backend" / ".venv").absolute()
    python = candidate / "bin" / "python"
    if python.is_file() and os.access(python, os.X_OK):
        return candidate
    return None


@contextmanager
def project_venv_overlay(*, repo: Path, worktree: Path) -> Iterator[Path | None]:
    """Expõe temporariamente o venv ignorado para scripts versionados legados.

    Alguns gates chamam um script que, corretamente, procura
    ``$RAIZ/backend/.venv``. Como o venv é ignorado pelo Git, ele não existe
    na worktree do agente. O link vive apenas durante os gates e é removido no
    ``finally``; nunca entra no diff ou no commit.
    """

    source = find_project_venv(repo=repo, worktree=worktree)
    target = (worktree.resolve() / "backend" / ".venv").absolute()
    created = False
    parent_created = False
    if source is not None and target != source:
        if target.exists() or target.is_symlink():
            raise GateConfigurationError(
                f"overlay de venv recusou destino preexistente: {target}"
            )
        if not target.parent.exists():
            target.parent.mkdir(parents=True)
            parent_created = True
        target.symlink_to(source, target_is_directory=True)
        created = True
    try:
        yield source
    finally:
        if created:
            if not target.is_symlink() or target.readlink() != source:
                raise GateConfigurationError(
                    f"overlay de venv foi alterado durante o gate: {target}"
                )
            target.unlink()
            if parent_created:
                target.parent.rmdir()


def resolve_gate_argv(argv: Sequence[str], *, repo: Path, worktree: Path) -> ResolvedGate:
    """Resolve o executável sem mudar a semântica declarada do gate.

    Executáveis comuns (`npm`, `python3`, scripts versionados) permanecem
    intocados. Apenas um Python sob ``.venv/bin`` ausente na worktree pode ser
    localizado em outra worktree registrada do mesmo repositório.
    """

    resolved = list(argv)
    command_index = _command_index(resolved)
    declared = resolved[command_index]
    declared_path = Path(declared)

    if declared_path.is_absolute():
        if not declared_path.is_file() or not os.access(declared_path, os.X_OK):
            raise GateConfigurationError(
                f"executável absoluto do gate não existe ou não é executável: {declared}"
            )
        return ResolvedGate(resolved, command_index, declared, str(declared_path))

    if "/" not in declared:
        # A resolução pelo PATH continua a cargo de subprocess/execvp. Não
        # substituímos `python3` por outro interpretador por conveniência.
        return ResolvedGate(resolved, command_index, declared, declared)

    # Não use ``resolve()`` no executável: o Python de um venv é normalmente
    # um symlink. Executar o alvo da symlink perde ``sys.prefix`` e, com ele, as
    # dependências instaladas no ambiente virtual.
    local = (worktree.resolve() / declared_path).absolute()
    is_project_venv = _is_project_venv_python(declared)
    if not is_project_venv and local.is_file() and os.access(local, os.X_OK):
        return ResolvedGate(resolved, command_index, declared, str(local))

    if not is_project_venv:
        raise GateConfigurationError(
            f"executável relativo do gate ausente na worktree: {declared}"
        )

    candidate = (_git_primary_worktree(repo) / declared_path).absolute()
    if candidate.is_file() and os.access(candidate, os.X_OK):
        resolved[command_index] = str(candidate)
        return ResolvedGate(
            resolved,
            command_index,
            declared,
            str(candidate),
        )

    raise GateConfigurationError(
        "interpretador do gate não encontrado na worktree primária registrada: "
        f"{candidate}"
    )
