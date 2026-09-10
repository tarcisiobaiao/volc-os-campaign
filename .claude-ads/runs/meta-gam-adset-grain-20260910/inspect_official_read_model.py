from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def env_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def main() -> None:
    env = env_file(ROOT / ".env.server")
    base = env["SUPABASE_URL"].rstrip("/")
    if urllib.parse.urlparse(base).hostname != "database.agenciavolc.com.br":
        raise SystemExit("autoridade Supabase inesperada")
    key = env["SUPABASE_SERVICE_ROLE_KEY"]
    resources = {
        "trafego_meta_insight_daily": "select=nivel&limit=1",
        "trafego_meta_adset": "select=meta_adset_id&limit=1",
        "trafego_meta_campaign": "select=meta_campaign_id&limit=1",
        "vw_trafego_meta_financeiro_conjunto_dia": "select=metric_scope,metric_version&limit=1",
        "vw_trafego_meta_financeiro_campanha_dia": "select=metric_scope,metric_version&limit=1",
        "vw_trafego_meta_financeiro_conjunto_dia_gam": "select=metric_scope,metric_version,mapping_status&limit=1",
        "daily_campaign_metrics": "select=campaign_id&limit=1",
        "gam_metrics": "select=utm_campaign_value&limit=1",
    }
    result: dict[str, dict[str, object]] = {}
    for resource, query in resources.items():
        request = urllib.request.Request(f"{base}/rest/v1/{resource}?{query}")
        request.add_header("apikey", key)
        request.add_header("Authorization", f"Bearer {key}")
        request.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                rows = json.loads(response.read() or b"[]")
                result[resource] = {
                    "available": True,
                    "sample_rows": len(rows),
                    "sample_fields": sorted(rows[0]) if rows else [],
                }
        except urllib.error.HTTPError as exc:
            result[resource] = {"available": False, "http_status": exc.code}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
