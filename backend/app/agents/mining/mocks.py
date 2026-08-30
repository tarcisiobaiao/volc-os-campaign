"""
Deterministic mocks for Google Ads Keyword Planner and DataForSEO.

These produce payloads shaped EXACTLY like the real APIs so the pure extractors
(app.services.dataforseo.extract_*, app.agents.mining.gold_extractor) run
unchanged. Everything is seeded off the keyword string (no randomness) so runs
are reproducible. Clearly labelled engine='mock' upstream.
"""
from __future__ import annotations

from typing import Any, Dict, List

_MICROS = 1_000_000


def _seed_int(text: str) -> int:
    """Stable non-negative hash (no Math.random / no PYTHONHASHSEED dependence)."""
    h = 2166136261
    for ch in (text or ""):
        h = (h ^ ord(ch)) * 16777619 & 0xFFFFFFFF
    return h


def _suffixes() -> List[str]:
    return [
        "como funciona", "passo a passo", "online", "2025", "2026", "valor",
        "requisitos", "calculadora", "prazo", "documentos", "consulta", "login",
        "quem tem direito", "calendario", "simulação", "app", "portal", "atualizado",
    ]


def mock_keyword_ideas(seed_keyword: str, geo_target: int, language_constant: int) -> List[Dict[str, Any]]:
    """Mock of Google Ads generateKeywordIdeas `results` array."""
    base = _seed_int(seed_keyword)
    comps = ["LOW", "MEDIUM", "HIGH"]
    results: List[Dict[str, Any]] = [
        {
            "text": seed_keyword,
            "keywordIdeaMetrics": {
                "avgMonthlySearches": 5000 + (base % 45000),
                "averageCpcMicros": (50_000 + (base % 800_000)),
                "lowTopOfPageBidMicros": 40_000 + (base % 200_000),
                "highTopOfPageBidMicros": 300_000 + (base % 1_500_000),
                "competition": comps[base % 3],
                "competitionIndex": base % 100,
            },
        }
    ]
    for i, suf in enumerate(_suffixes()):
        h = _seed_int(f"{seed_keyword}|{suf}")
        vol = (h % 60000)
        results.append(
            {
                "text": f"{seed_keyword} {suf}".strip(),
                "keywordIdeaMetrics": {
                    "avgMonthlySearches": vol,
                    "averageCpcMicros": (10_000 + (h % 600_000)),
                    "lowTopOfPageBidMicros": 10_000 + (h % 150_000),
                    "highTopOfPageBidMicros": 200_000 + (h % 1_200_000),
                    "competition": comps[h % 3],
                    "competitionIndex": h % 100,
                },
            }
        )
    return results


def mock_autocomplete(keyword: str, location_code: int, language_code: str) -> Dict[str, Any]:
    """Mock of DataForSEO autocomplete raw response."""
    qwords = ["como", "quando", "quem tem direito", "onde", "qual o valor de", "porque"]
    items = [
        {"type": "autocomplete", "keyword": f"{q} {keyword}".strip()} for q in qwords
    ]
    items += [{"type": "autocomplete", "keyword": f"{keyword} {s}".strip()} for s in ("2026", "online", "passo a passo")]
    return {"tasks": [{"result": [{"items": items}]}]}


def mock_related(keyword: str, location_code: int, language_short: str, limit: int = 100) -> Dict[str, Any]:
    """Mock of DataForSEO related_keywords raw response."""
    base = _seed_int(keyword)
    comps = ["LOW", "MEDIUM", "HIGH"]
    items: List[Dict[str, Any]] = []
    for i, suf in enumerate(_suffixes()):
        h = _seed_int(f"rel|{keyword}|{suf}")
        items.append(
            {
                "keyword_data": {
                    "keyword": f"{keyword} {suf}".strip(),
                    "keyword_info": {
                        "search_volume": h % 40000,
                        "cpc": round((h % 300) / 100, 2),
                        "low_top_of_page_bid": round((h % 150) / 100, 2),
                        "high_top_of_page_bid": round((h % 900) / 100, 2),
                        "competition_level": comps[h % 3],
                        "competition_index": h % 100,
                        "monthly_searches": [
                            {"year": 2025, "month": m, "search_volume": (h * m) % 40000}
                            for m in range(1, 13)
                        ],
                    },
                }
            }
        )
    return {"tasks": [{"result": [{"items": items[:limit]}]}]}
