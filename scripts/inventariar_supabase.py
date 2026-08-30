#!/usr/bin/env python3
"""Inventário somente-leitura do catálogo PostgREST do VOLC O.S.

Não lê conteúdo de colunas sensíveis. Coleta apenas catálogo, contagem planejada
e limites temporais de colunas públicas de data.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = Path("/private/tmp/volc-supabase-inventory.json")
OPENAPI = Path("/private/tmp/volc-supabase-openapi.json")


def load_env(path: Path) -> None:
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def request(url: str, key: str, *, count: bool = False):
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    if count:
        headers["Prefer"] = "count=exact"
        headers["Range"] = "0-0"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.headers, resp.read()


def count_from_range(value: str | None):
    if not value or "/" not in value:
        return None
    tail = value.rsplit("/", 1)[1]
    return int(tail) if tail.isdigit() else None


def first_value(base: str, key: str, table: str, column: str, descending: bool):
    query = urllib.parse.urlencode({
        "select": column,
        "order": f"{column}.{'desc' if descending else 'asc'}.nullslast",
        "limit": "1",
    })
    _headers, body = request(f"{base}/rest/v1/{urllib.parse.quote(table)}?{query}", key)
    rows = json.loads(body)
    return rows[0].get(column) if rows else None


def inspect_table(base: str, key: str, name: str, definition: dict):
    props = definition.get("properties") or {}
    temporal_candidates = [
        "date", "report_date", "visited_at", "event_date", "effective_date",
        "started_at", "created_at", "criado_em", "updated_at", "atualizado_em",
    ]
    temporal = next((c for c in temporal_candidates if c in props), None)
    result = {
        "name": name,
        "columns": sorted(props),
        "column_count": len(props),
        "exact_count": None,
        "temporal_column": temporal,
        "first": None,
        "last": None,
        "error": None,
    }
    try:
        query = urllib.parse.urlencode({"select": temporal or next(iter(props), "*") , "limit": "1"})
        headers, _body = request(
            f"{base}/rest/v1/{urllib.parse.quote(name)}?{query}", key, count=True
        )
        result["exact_count"] = count_from_range(headers.get("Content-Range"))
        if temporal and result["exact_count"]:
            result["first"] = first_value(base, key, name, temporal, False)
            result["last"] = first_value(base, key, name, temporal, True)
    except Exception as exc:  # erro é inventariado, não repetido indefinidamente
        result["error"] = re.sub(r"[\r\n]+", " ", str(exc))[:300]
    return result


def main():
    load_env(ROOT / ".env")
    base = os.environ["VITE_SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    if not OPENAPI.exists():
        _headers, body = request(f"{base}/rest/v1/", key)
        OPENAPI.write_bytes(body)
    catalog = json.loads(OPENAPI.read_text())
    definitions = catalog.get("definitions") or {}
    rpc_paths = sorted(p for p in (catalog.get("paths") or {}) if p.startswith("/rpc/"))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(inspect_table, base, key, name, definition)
                   for name, definition in definitions.items()]
        tables = [future.result() for future in futures]
    tables.sort(key=lambda item: item["name"])
    payload = {
        "count_semantics": "exact (contagem retornada pelo PostgREST)",
        "tables_and_views": tables,
        "rpc_paths": rpc_paths,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({
        "tables_and_views": len(tables),
        "rpcs": len(rpc_paths),
        "with_count": sum(t["exact_count"] is not None for t in tables),
        "with_error": sum(t["error"] is not None for t in tables),
        "output": str(OUT),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
