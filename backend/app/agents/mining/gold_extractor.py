"""
Gold Extractor + seed normalization — faithful port of n8n-peneirador-kw.json
node "⛏️ Gold Extractor1" (and the shared normalizeSeed helper).

Given one Google Ads `results` payload for the current seed, it:
  - extracts keyword metrics (micros -> currency),
  - merges into the running master_bank (highest volume wins per keyword),
  - picks the next seed (top gold not yet used, by normalized form),
  - decides whether to continue looping.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Dict, List

_MICROS = 1_000_000


def normalize_seed(s: Any) -> str:
    """Port of normalizeSeed: lower, trim, strip accents, split, sort, join."""
    text = str(s or "").lower().strip()
    norm = unicodedata.normalize("NFD", text)
    no_accents = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    parts = [p for p in no_accents.split() if p]
    parts.sort()
    return " ".join(parts)


def _micros_to_2(micros: Any) -> float:
    return round((float(micros or 0) / _MICROS), 2)


def extract_gold(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Port of the '⛏️ Gold Extractor1' Code node.

    `payload` carries: results, loop_iteration, max_loops, min_volume_gold,
    seed_keyword, master_bank (list), used_seeds (list), used_seeds_norm (list),
    plus the config passthrough fields.
    """
    raw_results: List[Dict[str, Any]] = payload.get("results") or []
    if not isinstance(raw_results, list):
        raw_results = []

    current_loop = int(payload.get("loop_iteration") or 0)
    max_loops = int(payload.get("max_loops") or 5)
    min_volume_gold = int(payload.get("min_volume_gold") or 10)
    current_seed = str(payload.get("seed_keyword") or "").lower().strip()
    current_seed_norm = normalize_seed(current_seed)

    master_bank = list(payload.get("master_bank") or [])
    used_seeds = list(payload.get("used_seeds") or [])
    used_seeds_norm = list(payload.get("used_seeds_norm") or [])

    if current_seed and current_seed not in used_seeds:
        used_seeds.append(current_seed)
    if current_seed_norm and current_seed_norm not in used_seeds_norm:
        used_seeds_norm.append(current_seed_norm)

    extracted: List[Dict[str, Any]] = []
    for item in raw_results:
        m = item.get("keywordIdeaMetrics") or {}
        kw = str(item.get("text") or "").lower().strip()
        if not kw:
            continue
        extracted.append(
            {
                "keyword": kw,
                "volume": int(m.get("avgMonthlySearches") or 0),
                "cpc": _micros_to_2(m.get("averageCpcMicros")),
                "low_bid": _micros_to_2(m.get("lowTopOfPageBidMicros")),
                "high_bid": _micros_to_2(m.get("highTopOfPageBidMicros")),
                "competition": str(m.get("competition") or "UNKNOWN").upper(),
                "competition_index": int(m.get("competitionIndex") or 0),
                "found_in_loop": current_loop,
                "seed_origin": current_seed,
            }
        )

    bank_map: Dict[str, Dict[str, Any]] = {}
    for kw in master_bank:
        if kw and kw.get("keyword"):
            bank_map[kw["keyword"]] = kw
    for kw in extracted:
        existing = bank_map.get(kw["keyword"])
        if not existing or kw["volume"] > existing["volume"]:
            bank_map[kw["keyword"]] = kw
    updated_bank = list(bank_map.values())

    golds = [
        k
        for k in updated_bank
        if (k.get("volume") or 0) >= min_volume_gold
        and normalize_seed(k["keyword"]) not in used_seeds_norm
    ]
    golds.sort(key=lambda k: (k.get("volume") or 0), reverse=True)

    next_seed = golds[0]["keyword"] if golds else None
    should_continue = bool(
        next_seed
        and normalize_seed(next_seed) != current_seed_norm
        and current_loop < (max_loops - 1)
        and len(extracted) > 0
    )

    existing_keys = {m["keyword"] for m in master_bank if m.get("keyword")}
    new_keywords = len([k for k in extracted if k["keyword"] not in existing_keys])

    if not should_continue:
        if current_loop >= (max_loops - 1):
            reason = "MAX_LOOPS_REACHED"
        elif not next_seed:
            reason = "NO_MORE_GOLDS"
        elif len(extracted) == 0:
            reason = "API_EMPTY"
        else:
            reason = "DUPLICATE_SEED_NORM"
    else:
        reason = "GOLD_FOUND"

    return {
        "loop": {
            "current": current_loop,
            "max": max_loops,
            "should_continue": should_continue,
            "next_seed": next_seed,
            "reason": reason,
        },
        "master_bank": updated_bank,
        "used_seeds": used_seeds,
        "used_seeds_norm": used_seeds_norm,
        "iteration_stats": {
            "loop_number": current_loop,
            "seed_used": current_seed,
            "all_seeds_used": used_seeds,
            "api_results": len(raw_results),
            "new_keywords": new_keywords,
            "bank_before": len(master_bank),
            "bank_after": len(updated_bank),
            "golds_remaining": len(golds),
            "top_5_golds": [f"{g['keyword']} ({g['volume']})" for g in golds[:5]],
        },
    }
