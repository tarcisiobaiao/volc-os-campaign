#!/usr/bin/env python3
"""Reconstrói o Mapa Vivo VOLC em uma ordem única, segura e reproduzível.

Por padrão, regenera a fonte operacional a partir dos snapshots locais, extrai a
camada técnica por AST, funde as duas e recria todos os formatos derivados.
Use ``--refresh-live`` para atualizar primeiro o inventário somente-leitura do
Supabase. Use ``--reuse-technical`` apenas quando código e SQL não mudaram.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import venv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".graphify-cache" / "code"
STATUS = ROOT / "graphify-out" / "UPDATE_STATUS.json"
RUNTIME_DB = Path("/private/tmp/volc-supabase-inventory.json")
RUNTIME_CLICKUP = Path("/private/tmp/volc-clickup-tasks-p0.json")
SAFE_DB = ROOT / "docs" / "volc-os-graph" / "supabase-snapshot-2026-08-22.json"
SAFE_CLICKUP = ROOT / "docs" / "volc-os-graph" / "clickup-snapshot-2026-08-22.json"
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".sql"}
CODE_NAMES = {"package.json", "package-lock.json", "tsconfig.json", "vite.config.ts"}


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-live", action="store_true",
                        help="refaz o inventário somente-leitura do Supabase")
    parser.add_argument("--reuse-technical", action="store_true",
                        help="reusa o último AST; permitido somente sem mudanças de código/SQL")
    parser.add_argument("--bootstrap", action="store_true",
                        help="cria .venv-graphify e instala a versão fixada")
    parser.add_argument("--check", action="store_true",
                        help="apenas verifica se os insumos mudaram desde a última atualização")
    return parser.parse_args()


def run(command: list[str]) -> None:
    print("→", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def bootstrap() -> Path:
    target = ROOT / ".venv-graphify"
    if not target.exists():
        venv.EnvBuilder(with_pip=True).create(target)
    python = target / "bin" / "python"
    run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements-graphify.txt")])
    return python


def graphify_python(do_bootstrap: bool) -> Path:
    configured = os.environ.get("GRAPHIFY_PYTHON")
    candidates = [
        Path(configured) if configured else None,
        ROOT / ".venv-graphify" / "bin" / "python",
        Path(sys.executable),
    ]
    for candidate in candidates:
        if not candidate or not candidate.exists():
            continue
        result = subprocess.run(
            [str(candidate), "-c", "import graphify"],
            capture_output=True,
        )
        if result.returncode == 0:
            return candidate
    if do_bootstrap:
        return bootstrap()
    raise SystemExit(
        "Graphify não está instalado no ambiente permanente. Execute uma vez:\n"
        "  python3 scripts/atualizar_grafo_volc_os.py --bootstrap\n"
        "ou defina GRAPHIFY_PYTHON para um Python que contenha graphifyy[sql]==0.9.48."
    )


def tracked_inputs() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    paths = []
    for raw in result.stdout.splitlines():
        path = ROOT / raw
        if not path.is_file():
            continue
        if path.suffix.lower() in CODE_SUFFIXES or path.name in CODE_NAMES:
            paths.append(path)
    business = ROOT / "docs" / "volc-os-graph" / "volc-os-graph.json"
    if business.exists():
        paths.append(business)
    return sorted(set(paths))


def input_digest() -> tuple[str, int]:
    digest = hashlib.sha256()
    paths = tracked_inputs()
    for path in paths:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest(), len(paths)


def git_head() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT,
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def ensure_runtime_snapshots() -> None:
    if not RUNTIME_DB.exists():
        if not SAFE_DB.exists():
            raise SystemExit("Snapshot sanitizado do Supabase não encontrado.")
        shutil.copy2(SAFE_DB, RUNTIME_DB)
    if not RUNTIME_CLICKUP.exists() and SAFE_CLICKUP.exists():
        safe = json.loads(SAFE_CLICKUP.read_text(encoding="utf-8"))
        payload = {
            "tasks": [
                {"id": item.get("id"), "name": item.get("name"),
                 "status": {"status": item.get("status")}}
                for item in safe.get("tasks", [])
            ]
        }
        RUNTIME_CLICKUP.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_status(*, refreshed_live: bool, reused_technical: bool, python: Path) -> None:
    hybrid = json.loads((ROOT / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    business = json.loads((ROOT / "docs" / "volc-os-graph" / "volc-os-graph.json").read_text(encoding="utf-8"))
    digest, files = input_digest()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip() != ""
    try:
        version = subprocess.run(
            [str(python), "-c", "import importlib.metadata; print(importlib.metadata.version('graphifyy'))"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        version = "unknown"
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds"),
        "built_at_commit": git_head(),
        "working_tree_dirty_at_build": dirty,
        "input_sha256": digest,
        "input_file_count": files,
        "graphify_version": version,
        "live_sources_refreshed": refreshed_live,
        "technical_layer_reused": reused_technical,
        "sources": {
            "operational": "docs/volc-os-graph/volc-os-graph.json",
            "technical": ".graphify-cache/code/graphify-out/graph.json",
            "canonical_hybrid": "graphify-out/graph.json",
        },
        "counts": {
            "operational_nodes": len(business["nodes"]),
            "operational_edges": len(business["edges"]),
            "hybrid_nodes": len(hybrid["nodes"]),
            "hybrid_edges": len(hybrid["links"]),
        },
        "freshness_rule": (
            "Execute scripts/atualizar_grafo_volc_os.py --check; mudanças no digest "
            "exigem reconstrução. Decisões de negócio novas ainda exigem curadoria humana."
        ),
    }
    STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def check_status() -> int:
    if not STATUS.exists():
        print(json.dumps({"current": False, "reason": "UPDATE_STATUS.json ausente"}, ensure_ascii=False))
        return 1
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    digest, files = input_digest()
    current = digest == status.get("input_sha256")
    print(json.dumps({
        "current": current,
        "generated_at": status.get("generated_at"),
        "built_at_commit": status.get("built_at_commit"),
        "current_commit": git_head(),
        "input_file_count": files,
        "reason": "insumos idênticos" if current else "código, SQL ou fonte operacional mudou",
    }, ensure_ascii=False, indent=2))
    return 0 if current else 1


def main() -> None:
    options = args()
    if options.check:
        raise SystemExit(check_status())

    python = graphify_python(options.bootstrap)
    run([sys.executable, str(ROOT / "scripts" / "verificar_segredos.py")])
    if options.refresh_live:
        run([sys.executable, str(ROOT / "scripts" / "inventariar_supabase.py")])
    ensure_runtime_snapshots()
    run([sys.executable, str(ROOT / "scripts" / "gerar_grafo_volc_os.py")])

    technical = CACHE / "graphify-out" / "graph.json"
    if options.reuse_technical:
        if not technical.exists():
            raise SystemExit("Não há camada técnica em cache; execute sem --reuse-technical.")
    else:
        run([
            str(python), "-m", "graphify", "extract", str(ROOT),
            "--code-only", "--max-workers", "1", "--out", str(CACHE),
        ])

    run([
        str(python), str(ROOT / "scripts" / "gerar_graphify_volc_os.py"),
        "--code-graph", str(technical),
    ])
    run([str(python), str(ROOT / "scripts" / "exportar_grafo_volc_os.py")])
    run([sys.executable, str(ROOT / "scripts" / "gerar_explorador_neural_volc_os.py")])
    run([sys.executable, str(ROOT / "scripts" / "auditar_repositorio.py")])
    write_status(
        refreshed_live=options.refresh_live,
        reused_technical=options.reuse_technical,
        python=python,
    )
    print(f"✓ Mapa Vivo atualizado. Estado: {STATUS}")


if __name__ == "__main__":
    main()
