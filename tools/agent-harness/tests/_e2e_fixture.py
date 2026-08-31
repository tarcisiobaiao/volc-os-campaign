"""Repositório sintético e adapter-contador compartilhados pelas provas E2E.

O contador não é decoração: se ele registrar uma chamada onde o compilador
deveria ter recusado, um modelo foi gasto — o custo exato que o Harness V3
existe para evitar. A versão anterior deste fixture declarava um contador que
NUNCA era instalado, então ``assertEqual(CONTADOR, [])`` passava mesmo que o
runtime tivesse chamado os quatro providers.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

GIT_ID = ("-c", "user.name=t", "-c", "user.email=t@t")


def git(tree: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(tree), *args],
                       capture_output=True, text=True, check=True)
    return r.stdout.strip()


@dataclass
class ContadorDeModelos:
    """Instalado de verdade sobre ``mission.adapter_for``."""

    chamadas: list[dict[str, Any]] = field(default_factory=list)
    escrita: Callable[[Path], None] | None = None

    def adapter_for(self, provider: str):
        contador = self

        class _Fake:
            async def run(self, request):
                contador.chamadas.append({
                    "provider": provider,
                    "worker_id": request.worker_id,
                    "mode": request.mode,
                    "worktree": str(request.worktree),
                })
                if request.mode == "workspace_write" and contador.escrita is not None:
                    contador.escrita(Path(request.worktree))
                return {
                    "status": "completed",
                    "summary": "stub",
                    "verdict": "accept",
                    "confirmed_findings": [],
                    "curation_handoff": {"task_ids": [], "state": "partial"},
                }

        return _Fake()

    @property
    def writers(self) -> list[dict[str, Any]]:
        return [c for c in self.chamadas if c["mode"] == "workspace_write"]

    @property
    def readers(self) -> list[dict[str, Any]]:
        return [c for c in self.chamadas if c["mode"] != "workspace_write"]


CATALOGO_PADRAO = {
    "catalog_version": 1,
    "gates": {
        "backend-unit": {
            "kind": "pytest",
            "targets": ["backend/tests"],
            "description": "suíte unitária do backend",
        },
        "diff-limpo": {"kind": "git_diff_check", "description": "diff sem lixo"},
    },
}


def repo_sintetico(raiz: Path, *, catalogo: dict[str, Any] | None = None) -> Path:
    """Repositório mínimo com Roadmap, teste verde e catálogo rastreado."""

    (raiz / "backend" / "tests").mkdir(parents=True)
    (raiz / "volc-os-workbook").mkdir()
    (raiz / "tools" / "agent-harness").mkdir(parents=True)
    (raiz / "backend" / "tests" / "test_base.py").write_text(
        "def test_verde():\n    assert True\n", encoding="utf-8")
    (raiz / "volc-os-workbook" / "ROADMAP-VIVO.json").write_text(
        json.dumps({"initiatives": [{"id": "P10-T17", "acceptance": ["a1", "a2", "a3"]}]}),
        encoding="utf-8")
    (raiz / "tools" / "agent-harness" / "gate-catalog.json").write_text(
        json.dumps(catalogo if catalogo is not None else CATALOGO_PADRAO, indent=2),
        encoding="utf-8")
    (raiz / ".gitignore").write_text("tools/agent-harness/runs/\n.agent-worktrees/\n",
                                     encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(raiz)], check=True)
    git(raiz, "add", "-A")
    subprocess.run(["git", "-C", str(raiz), *GIT_ID, "commit", "-q", "-m", "base"],
                   check=True, capture_output=True)
    return raiz


def missao(repo: Path, **over: Any) -> Path:
    base = git(repo, "rev-parse", "HEAD")
    m: dict[str, Any] = {
        "mission_schema_version": 3,
        "mission_id": "e2e-produtiva",
        "title": "smoke",
        "base_ref": base,
        "briefing": "b",
        "mode": "implementation",
        "commit_message": "candidato sintético",
        "acceptance_ids": ["P10-T17-A1"],
        "ownership_envelope": ["backend"],
        "task_ids": ["P10-T17"],
        "authorized_external_providers": [],
        "gates": [{"kind": "catalog", "gate_id": "backend-unit"}],
        "workers": [
            {"id": "wr", "provider": "codex", "role": "writer", "model": "gpt-5.5",
             "lens": "x", "allowed_paths": ["backend"], "writable_paths": ["backend"]},
            {"id": "rv", "provider": "codex", "role": "reviewer", "model": "gpt-5.6-sol",
             "lens": "y", "allowed_paths": ["backend"]},
        ],
    }
    m.update(over)
    destino = repo / "missao.json"
    destino.write_text(json.dumps(m, indent=2), encoding="utf-8")
    return destino


def escreve_teste_novo(worktree: Path) -> None:
    (worktree / "backend" / "tests" / "test_novo.py").write_text(
        "def test_do_writer():\n    assert True\n", encoding="utf-8")
