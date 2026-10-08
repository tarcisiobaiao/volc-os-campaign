"""Regenera `catalogo_gaql_v25.json` a partir do SERVIDOR (GoogleAdsFieldService).

Somente leitura: `SearchGoogleAdsFields` não toca conta nenhuma. Usa
`~/google-ads.yaml`.

⚠️ Por que o servidor e não o SDK: o descriptor do proto diz que
`asset_group.asset_coverage.ad_strength_action_items.action_item_type` existe,
e o endpoint o recusa com UNRECOGNIZED_FIELD (medido em 01/09 e 08/10/2026).
Só o catálogo do servidor diz o que é SELECIONÁVEL em GAQL.

Uso:
    backend/.venv/bin/python volc_ads/google_ads_api/atualizar_catalogo_gaql.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

DESTINO = Path(__file__).with_name("catalogo_gaql_v25.json")
VERSAO = "v25"


def main() -> int:
    from google.ads.googleads.client import GoogleAdsClient

    c = GoogleAdsClient.load_from_storage(version=VERSAO)
    svc = c.get_service("GoogleAdsFieldService")
    q = "SELECT name, category, selectable, filterable, sortable"
    campos = {}
    for f in svc.search_google_ads_fields(query=q):
        campos[f.name] = [f.category.name, f.selectable, f.filterable, f.sortable]
    doc = {
        "fonte": "GoogleAdsFieldService.SearchGoogleAdsFields",
        "versao_api": VERSAO,
        "versao_lib": version("google-ads"),
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "colunas": ["categoria", "selecionavel", "filtravel", "ordenavel"],
        "campos": dict(sorted(campos.items())),
    }
    DESTINO.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n",
                       encoding="utf-8")
    print(f"{len(campos)} campos → {DESTINO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
