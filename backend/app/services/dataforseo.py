"""
DataForSEO client — Google Autocomplete + Related Keywords Labs.

Ported from n8n-peneirador-kw.json nodes:
  - "🔮 Google Autocomplete2"  -> /v3/serp/google/autocomplete/live/advanced
  - "🧠 Related Keywords Labs2" -> /v3/dataforseo_labs/google/related_keywords/live

Auth: HTTP Basic (login:password). The n8n JSON had a hardcoded Authorization
header; it is MIGRATED to env (DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD) and never
copied into code. When unconfigured, `enabled` is False and the mining pipeline
uses a deterministic mock instead.
"""
from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

import httpx

from app.config import Settings

_AUTOCOMPLETE_URL = "https://api.dataforseo.com/v3/serp/google/autocomplete/live/advanced"
_RELATED_URL = "https://api.dataforseo.com/v3/dataforseo_labs/google/related_keywords/live"


class DataForSeoClient:
    name = "dataforseo"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.login = settings.dataforseo_login or ""
        self.password = settings.dataforseo_password or ""

    @property
    def enabled(self) -> bool:
        return bool(self.login and self.password)

    def _headers(self) -> Dict[str, str]:
        token = base64.b64encode(f"{self.login}:{self.password}".encode()).decode()
        return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

    async def _post(self, url: str, body: List[Dict[str, Any]]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            resp = await client.post(url, headers=self._headers(), json=body)
            resp.raise_for_status()
            return resp.json()

    async def autocomplete(
        self, keyword: str, location_code: int, language_code: str
    ) -> Dict[str, Any]:
        """Raw Google Autocomplete response (tasks[].result[].items[])."""
        if not self.enabled:
            raise RuntimeError("DataForSEO not configured (DATAFORSEO_LOGIN/PASSWORD).")
        body = [{"keyword": keyword, "location_code": location_code, "language_code": language_code}]
        return await self._post(_AUTOCOMPLETE_URL, body)

    async def related_keywords(
        self, keyword: str, location_code: int, language_short: str, *, depth: int = 3, limit: int = 100
    ) -> Dict[str, Any]:
        """Raw Related Keywords Labs response (tasks[].result[].items[])."""
        if not self.enabled:
            raise RuntimeError("DataForSEO not configured (DATAFORSEO_LOGIN/PASSWORD).")
        body = [
            {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_short,
                "depth": depth,
                "include_seed_keyword": False,
                "include_serp_info": False,
                "ignore_synonyms": False,
                "include_clickstream_data": False,
                "replace_with_core_keyword": False,
                "limit": limit,
            }
        ]
        return await self._post(_RELATED_URL, body)


# --- pure extractors (ported from the n8n "Extract ..." Code nodes) -----------

def extract_autocomplete(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Port of n8n 'Extract Autocomplete2' — dedup by lowercased keyword."""
    tasks = raw.get("tasks") or []
    keywords: List[Dict[str, Any]] = []
    for task in tasks:
        result = task.get("result") or []
        if not result:
            continue
        items_list = result[0].get("items") or []
        for item in items_list:
            text = item.get("keyword") or item.get("suggestion") or item.get("title")
            if text and isinstance(text, str):
                keywords.append(
                    {
                        "keyword": text.strip(),
                        "volume": 0,
                        "cpc": 0,
                        "low_bid": 0,
                        "high_bid": 0,
                        "competition": "UNKNOWN",
                        "competition_index": 0,
                        "monthly_searches": [],
                        "source": "google_autocomplete",
                        "original_type": item.get("type"),
                        "needs_enrichment": True,
                    }
                )
    # dedup exact (lowercased), keep first
    unique: Dict[str, Dict[str, Any]] = {}
    for k in keywords:
        key = k["keyword"].lower()
        if key not in unique:
            unique[key] = k
    return list(unique.values())


def extract_related(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Port of n8n 'Extract Related KW2'."""
    tasks = raw.get("tasks") or []
    items_list: List[Dict[str, Any]] = []
    if tasks:
        result = tasks[0].get("result") or []
        if result:
            items_list = result[0].get("items") or []
    out: List[Dict[str, Any]] = []
    for item in items_list:
        kd = item.get("keyword_data") or {}
        info = kd.get("keyword_info") or {}
        out.append(
            {
                "keyword": kd.get("keyword") or item.get("keyword"),
                "volume": info.get("search_volume") or 0,
                "cpc": info.get("cpc") or 0,
                "low_bid": info.get("low_top_of_page_bid") or 0,
                "high_bid": info.get("high_top_of_page_bid") or 0,
                "competition": info.get("competition_level") or "UNKNOWN",
                "competition_index": info.get("competition_index") or 0,
                "monthly_searches": info.get("monthly_searches") or [],
                "source": "related_keywords_labs",
            }
        )
    return out
