"""Criação segura de uma worktree exclusiva por trabalhador."""

from __future__ import annotations

import os
from typing import Any

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


_SAFE_SLUG = re.compile(r"[^a-z0-9_-]+")


def _git(repo: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.stdout.strip()


def _git_bytes(repo: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=60,
    )
    return result.stdout


def safe_slug(value: str) -> str:
    value = _SAFE_SLUG.sub("-", value.lower()).strip("-_")
    if not value:
        raise ValueError("slug vazio")
    return value


@dataclass(frozen=True)
class WorktreeInfo:
    worker_id: str
    path: Path
    branch: str
    base_sha: str


class WorktreeManager:
    def __init__(self, repo: Path):
        self.repo = repo.resolve()
        self.root = self.repo / ".agent-worktrees"

    def resolve_base(self, base_ref: str) -> str:
        return _git(self.repo, "rev-parse", "--verify", f"{base_ref}^{{commit}}")

    def resolve_implementation_base(
        self, base_ref: str, lineage_root_sha: str | None = None
    ) -> str:
        base_sha = self.resolve_base(base_ref)
        if base_sha != base_ref:
            raise ValueError("base_ref de implementação não resolveu para o SHA informado")
        root = lineage_root_sha or base_sha
        if self.resolve_base(root) != root:
            raise ValueError("lineage_root_sha não resolveu para o SHA informado")
        authority_head = self.resolve_base("HEAD")
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", root, authority_head],
            cwd=self.repo,
            check=False,
            timeout=60,
        )
        if result.returncode != 0:
            raise ValueError(
                "a raiz da linhagem precisa ser ancestral do HEAD controlador"
            )
        if lineage_root_sha is not None:
            result = subprocess.run(
                ["git", "merge-base", "--is-ancestor", root, base_sha],
                cwd=self.repo,
                check=False,
                timeout=60,
            )
            if result.returncode != 0:
                raise ValueError("base_ref corretivo escapou da linhagem autorizada")
        elif base_sha != root:
            raise ValueError("base_ref inicial inválido")
        return base_sha

    def create(
        self,
        run_id: str,
        worker_id: str,
        base_sha: str,
        *,
        registry: Any | None = None,
        mission_id: str = "",
    ) -> WorktreeInfo:
        """Cria a worktree sem jamais apagar nada.

        Antes: ``FileExistsError`` cru quando o caminho existia. Agora a decisão
        passa por ``workspace.prepare``, que confere colisão, respeita colheita
        preservada e escolhe caminho único em vez de destruir.
        """

        from .v3.workspace import prepare

        run_slug = safe_slug(run_id)
        worker_slug = safe_slug(worker_id)
        desejado = (self.root / run_slug / worker_slug).resolve()
        if self.root.resolve() not in desejado.parents:
            raise ValueError("worktree escapou do diretório permitido")

        plano = prepare(
            desired=desejado, registry=registry, mission_id=mission_id or run_id
        )
        path = plano.path
        if self.root.resolve() not in path.parents:
            raise ValueError("fallback de worktree escapou do diretório permitido")

        branch = f"agent/{run_slug}/{worker_slug}"
        _git(self.repo, "check-ref-format", "--branch", branch)
        branch_exists = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
            cwd=self.repo,
            check=False,
        ).returncode == 0
        if branch_exists:
            raise FileExistsError(f"branch já existe: {branch}")

        path.parent.mkdir(parents=True, exist_ok=True)
        _git(self.repo, "worktree", "add", "-b", branch, str(path), base_sha)
        self.assert_clean(path)
        if registry is not None:
            # Claim transacional: a worktree ganha dono registrado antes de
            # qualquer writer tocá-la, e dois writers nunca dividem o caminho.
            registry.claim(
                worktree=str(path),
                mission_id=mission_id or run_id,
                branch=branch,
                base_sha=base_sha,
                writer_pid=os.getpid(),
            )
        return WorktreeInfo(worker_slug, path, branch, base_sha)

    @staticmethod
    def assert_clean(path: Path) -> None:
        status = _git(path, "status", "--porcelain")
        if status:
            raise RuntimeError(f"worker alterou uma worktree read-only: {path}")

    @staticmethod
    def changed_paths(path: Path) -> list[str]:
        tracked = _git_bytes(path, "diff", "--name-only", "-z").split(b"\0")
        staged = _git_bytes(
            path, "diff", "--cached", "--name-only", "-z"
        ).split(b"\0")
        untracked = _git_bytes(
            path, "ls-files", "--others", "--exclude-standard", "-z"
        ).split(b"\0")
        return sorted(
            {
                raw.decode("utf-8", errors="strict")
                for raw in (*tracked, *staged, *untracked)
                if raw
            }
        )

    @staticmethod
    def assert_only_allowed(path: Path, allowed_paths: list[str]) -> list[str]:
        staged_before = _git(path, "diff", "--cached", "--name-only")
        if staged_before:
            raise RuntimeError("writer alterou o index; somente o harness pode fazer git add")
        changed = WorktreeManager.changed_paths(path)
        if not changed:
            raise RuntimeError("writer terminou sem produzir alteração")

        def is_allowed(candidate: str) -> bool:
            return any(
                candidate == allowed or candidate.startswith(f"{allowed.rstrip('/')}/")
                for allowed in allowed_paths
            )

        protected_prefixes = (
            ".claude/",
            ".codex/",
            ".git/",
            "graphify-out/",
            "docs/volc-os-graph/",
            "supabase/migrations/",
        )
        protected_exact = {
            ".env",
            ".vercel/project.json",
            "volc-os-workbook/ROADMAP-VIVO.json",
        }

        def is_protected(candidate: str) -> bool:
            name = Path(candidate).name
            return (
                candidate in protected_exact
                or candidate.startswith(protected_prefixes)
                or name == "settings.local.json"
                or name.startswith(".env")
            )

        ignored = [
            raw.decode("utf-8", errors="strict")
            for raw in _git_bytes(
                path,
                "ls-files",
                "--others",
                "--ignored",
                "--exclude-standard",
                "-z",
            ).split(b"\0")
            if raw
        ]
        protected_ignored = [candidate for candidate in ignored if is_protected(candidate)]
        if protected_ignored:
            raise RuntimeError(
                "writer criou arquivo protegido ignorado: "
                + ", ".join(protected_ignored)
            )

        rejected = [
            candidate
            for candidate in changed
            if not is_allowed(candidate)
            or is_protected(candidate)
            or (path / candidate).is_symlink()
        ]
        if rejected:
            raise RuntimeError(
                "writer saiu do ownership permitido: " + ", ".join(rejected)
            )
        return changed

    @staticmethod
    def assert_head_unchanged(path: Path, expected_sha: str) -> None:
        actual = _git(path, "rev-parse", "HEAD")
        if actual != expected_sha:
            raise RuntimeError(
                f"writer moveu HEAD ({actual}); esperado {expected_sha}"
            )

    @staticmethod
    def commit_writer(path: Path, message: str, changed_paths: list[str]) -> str:
        subprocess.run(
            ["git", "diff", "--check"],
            cwd=path,
            check=True,
            timeout=60,
        )
        subprocess.run(
            ["python3", "scripts/verificar_segredos.py"],
            cwd=path,
            check=True,
            timeout=120,
        )
        subprocess.run(
            ["git", "add", "--", *changed_paths],
            cwd=path,
            check=True,
            timeout=60,
        )
        staged = sorted(
            raw.decode("utf-8")
            for raw in _git_bytes(
                path, "diff", "--cached", "--name-only", "-z"
            ).split(b"\0")
            if raw
        )
        if staged != changed_paths:
            raise RuntimeError("o index difere da lista de ownership validada")
        subprocess.run(
            ["git", "diff", "--cached", "--check"],
            cwd=path,
            check=True,
            timeout=60,
        )
        subprocess.run(
            [
                "git",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.hooksPath=/dev/null",
                "commit",
                "-m",
                message,
            ],
            cwd=path,
            check=True,
            timeout=120,
        )
        return _git(path, "rev-parse", "HEAD")
