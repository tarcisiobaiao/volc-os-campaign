#!/usr/bin/env python3
"""Inventaria Markdown e SQL com evidência do Git e do Mapa Vivo.

O relatório não declara arquivos mortos automaticamente. Ele separa estados,
duplicatas exatas, risco SQL e filas de revisão para apoiar decisões humanas.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "graphify-out" / "graph.json"
OUT_JSON = ROOT / "docs" / "architecture" / "repository-inventory.json"
OUT_MD = ROOT / "docs" / "architecture" / "REPOSITORY-INVENTORY.md"

CORE_DOCS = {"README.md", "CLAUDE.md", "AGENTS.md", "PRODUCT.md"}
MUTATION_HIGH = re.compile(r"\b(?:DELETE|DROP|TRUNCATE)\b", re.I)
MUTATION_MEDIUM = re.compile(
    r"\b(?:UPDATE|INSERT|ALTER|CREATE\s+OR\s+REPLACE|CREATE\s+TRIGGER)\b", re.I
)


def git_lines(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def graph_index() -> tuple[dict[str, int], dict[str, int]]:
    if not GRAPH.exists():
        return {}, {}
    payload = json.loads(GRAPH.read_text(encoding="utf-8"))
    node_source: dict[str, str] = {}
    nodes_by_source: Counter[str] = Counter()
    degree_by_node: Counter[str] = Counter()
    for node in payload.get("nodes", []):
        node_id = str(node.get("id", ""))
        source = str(node.get("source_file", "") or "")
        node_source[node_id] = source
        if source:
            nodes_by_source[source] += 1
    for link in payload.get("links", []):
        degree_by_node[str(link.get("source", ""))] += 1
        degree_by_node[str(link.get("target", ""))] += 1
    degree_by_source: Counter[str] = Counter()
    for node_id, degree in degree_by_node.items():
        source = node_source.get(node_id)
        if source:
            degree_by_source[source] += degree
    return dict(nodes_by_source), dict(degree_by_source)


def classify(path: str) -> str:
    lower = path.lower()
    name = Path(path).name.lower()
    if path in CORE_DOCS:
        return "project-control"
    if "/archive/" in f"/{lower}":
        return "archived"
    if lower.startswith(("graphify-out/", "testsprite_tests/results/")):
        return "generated"
    if "/reference/" in f"/{lower}" or lower.startswith("volc_ads/google_ads_api/"):
        return "reference"
    if "auditoria" in lower or "revisao-" in lower or "/audits/" in f"/{lower}":
        return "audit"
    if "/prompts/" in f"/{lower}" or name in {"prompt.md", "referencia-n8n-sniper.md"}:
        return "runtime-contract"
    if lower.endswith(".sql"):
        if lower.startswith("sql/diagnostics/") or any(
            token in name for token in ("debug", "diagnostico", "query_")
        ):
            return "sql-diagnostic"
        if any(token in name for token in ("test_", "validate_", "validation", "smoke")):
            return "sql-validation"
        if lower.startswith(("src/sql/pautador/", "src/sql/joinads/", "src/sql/volc-sync/")):
            return "sql-migration-line"
        if re.match(r"src/sql/v[67]_\d+", lower):
            return "sql-migration-line"
        if lower.startswith("src/sql/"):
            return "sql-needs-lineage"
        return "sql-needs-review"
    if name == "readme.md":
        return "module-guide"
    if lower.startswith("docs/") and any(
        token in name for token in ("prd", "spec", "roadmap", "checklist", "comece-aqui")
    ):
        return "product-document"
    return "documentation"


def sql_risk(text: str) -> str:
    if MUTATION_HIGH.search(text):
        return "high"
    if MUTATION_MEDIUM.search(text):
        return "medium"
    return "read-only-or-ddl-free"


def main() -> None:
    tracked = set(git_lines("ls-files"))
    candidates = [
        path for path in git_lines("ls-files", "-co", "--exclude-standard")
        if Path(path).suffix.lower() in {".md", ".sql"}
    ]
    nodes_by_source, degree_by_source = graph_index()
    records = []
    duplicate_index: dict[str, list[str]] = defaultdict(list)

    for path in sorted(set(candidates)):
        absolute = ROOT / path
        if not absolute.is_file():
            continue
        raw = absolute.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        duplicate_index[digest].append(path)
        text = raw.decode("utf-8", errors="replace")
        record = {
            "path": path,
            "extension": absolute.suffix.lower(),
            "classification": classify(path),
            "tracked": path in tracked,
            "bytes": len(raw),
            "lines": text.count("\n") + (1 if text else 0),
            "sha256": digest,
            "graph_nodes": nodes_by_source.get(path, 0),
            "graph_degree": degree_by_source.get(path, 0),
            "sql_risk": sql_risk(text) if absolute.suffix.lower() == ".sql" else None,
        }
        records.append(record)

    duplicates = [paths for paths in duplicate_index.values() if len(paths) > 1]
    classes = Counter(record["classification"] for record in records)
    risks = Counter(
        record["sql_risk"] for record in records if record["sql_risk"] is not None
    )
    generated_at = datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds")
    payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "warning": "candidate não significa morto; exclusão exige revisão humana e gates",
        "summary": {
            "files": len(records),
            "markdown": sum(record["extension"] == ".md" for record in records),
            "sql": sum(record["extension"] == ".sql" for record in records),
            "tracked": sum(record["tracked"] for record in records),
            "untracked": sum(not record["tracked"] for record in records),
            "exact_duplicate_groups": len(duplicates),
            "classifications": dict(sorted(classes.items())),
            "sql_risk": dict(sorted(risks.items())),
        },
        "exact_duplicates": duplicates,
        "files": records,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    high_risk = [
        record for record in records
        if record["extension"] == ".sql" and record["sql_risk"] == "high"
    ]
    review = [
        record for record in records
        if record["classification"] in {"sql-needs-lineage", "sql-needs-review", "audit"}
    ]
    lines = [
        "# Inventário de higiene do repositório",
        "",
        f"Gerado em `{generated_at}` por `scripts/auditar_repositorio.py`.",
        "",
        "> Este relatório organiza evidências. Ele não declara arquivos mortos automaticamente.",
        "",
        "## Resumo",
        "",
        f"- {len(records)} arquivos: {payload['summary']['markdown']} Markdown e {payload['summary']['sql']} SQL;",
        f"- {payload['summary']['tracked']} versionados e {payload['summary']['untracked']} ainda não versionados;",
        f"- {len(duplicates)} grupos de duplicatas exatas;",
        f"- {len(high_risk)} SQL com palavras de mutação de alto risco.",
        "",
        "## Classificações",
        "",
        "| Classe | Arquivos |",
        "|---|---:|",
    ]
    lines.extend(f"| `{key}` | {value} |" for key, value in sorted(classes.items()))
    lines += ["", "## Duplicatas exatas", ""]
    if duplicates:
        for group in duplicates:
            lines.append("- " + " ↔ ".join(f"`{path}`" for path in group))
    else:
        lines.append("Nenhuma.")
    lines += [
        "",
        "## SQL de alto risco",
        "",
        "Arquivos abaixo contêm `DELETE`, `DROP` ou `TRUNCATE`. Isso não prova que",
        "estejam errados, mas impede aplicação automática.",
        "",
        "| Path | Classe | Nós no grafo | Grau |",
        "|---|---|---:|---:|",
    ]
    lines.extend(
        f"| `{record['path']}` | `{record['classification']}` | "
        f"{record['graph_nodes']} | {record['graph_degree']} |"
        for record in high_risk
    )
    lines += [
        "",
        "## Fila da próxima onda",
        "",
        "| Path | Classe | Risco SQL | Nós no grafo | Grau |",
        "|---|---|---|---:|---:|",
    ]
    lines.extend(
        f"| `{record['path']}` | `{record['classification']}` | "
        f"{record['sql_risk'] or '—'} | {record['graph_nodes']} | {record['graph_degree']} |"
        for record in review[:120]
    )
    lines += [
        "",
        "O inventário completo e legível por máquina está em",
        "`docs/architecture/repository-inventory.json`.",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
