"""Preflight sem efeitos colaterais para o harness multiagente.

Esta etapa não chama modelos, não cria worktrees e não escreve no repositório.
Ela apenas prova que ADK, Claude Code, Codex e Git estão disponíveis e registra
qual commit realmente servirá de base para as futuras worktrees.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

import google.adk
from google.adk import Workflow


def _run(command: Sequence[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return result.stdout.strip() or result.stderr.strip()


def _command_version(binary: str, *arguments: str) -> dict[str, Any]:
    resolved = shutil.which(binary)
    if not resolved:
        return {"available": False, "path": None, "version": None}
    try:
        version = _run([resolved, *arguments]).splitlines()[0]
    except (OSError, subprocess.SubprocessError) as error:
        return {
            "available": False,
            "path": resolved,
            "version": None,
            "error": type(error).__name__,
        }
    return {"available": True, "path": resolved, "version": version}


def parse_worktrees(porcelain: str) -> list[dict[str, str]]:
    worktrees: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw_line in porcelain.splitlines() + [""]:
        line = raw_line.strip()
        if not line:
            if current:
                worktrees.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    return worktrees


def collect_preflight(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    head = _run(["git", "rev-parse", "HEAD"], cwd=repo)
    branch = _run(["git", "branch", "--show-current"], cwd=repo)
    status = _run(["git", "status", "--porcelain"], cwd=repo)
    worktrees = parse_worktrees(
        _run(["git", "worktree", "list", "--porcelain"], cwd=repo)
    )

    # Instancia o runtime novo do ADK 2.x sem modelo e sem rede. Isso detecta
    # uma instalação parcialmente quebrada antes de qualquer tarefa real.
    workflow = Workflow(name="volc_preflight", edges=[])

    return {
        "ok": True,
        "adk": {
            "version": google.adk.__version__,
            "workflow_runtime": type(workflow).__name__,
        },
        "providers": {
            "claude": _command_version("claude", "--version"),
            "codex": _command_version("codex", "--version"),
            "gemini": {
                "available": bool(os.environ.get("GEMINI_API_KEY")),
                "path": "google-genai/ADK",
                "version": (
                    f"google-genai {importlib.metadata.version('google-genai')} / "
                    "gemini-3.7-flash"
                    if os.environ.get("GEMINI_API_KEY")
                    else None
                ),
                "optional": True,
            },
            "deepseek": {
                "available": bool(os.environ.get("DEEPSEEK_API_KEY")),
                "path": "bounded-sniper",
                "version": "deepseek-v4-flash" if os.environ.get("DEEPSEEK_API_KEY") else None,
                "optional": True,
            },
        },
        "repository": {
            "root": str(repo),
            "head": head,
            "branch": branch,
            "dirty": bool(status),
            "dirty_entries": len(status.splitlines()) if status else 0,
            "writer_warning": (
                "Worktrees novas partem do commit HEAD e não recebem mudanças "
                "não commitadas desta árvore."
                if status
                else None
            ),
            "worktrees": worktrees,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = collect_preflight(args.repo)
    providers_ok = all(
        provider["available"]
        for provider in report["providers"].values()
        if not provider.get("optional")
    )
    report["ok"] = providers_ok

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"ADK {report['adk']['version']}: ok")
        for name, provider in report["providers"].items():
            state = provider["version"] if provider["available"] else "indisponível"
            print(f"{name}: {state}")
        repository = report["repository"]
        print(f"base: {repository['branch']} @ {repository['head'][:12]}")
        print(f"árvore suja: {repository['dirty_entries']} entrada(s)")
        if repository["writer_warning"]:
            print(f"ATENÇÃO: {repository['writer_warning']}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
