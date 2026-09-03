"""
Consolidation ports from n8n-peneirador-kw.json:
  - final_classifier  -> "🏆 Final Classifier1" (MASTER CONSOLIDATOR V2)
  - mega_merge        -> "🔥 Mega Merger2" (MEGA MERGE STATE OF THE ART v2.0)
"""
from __future__ import annotations

import json
import unicodedata
from typing import Any, Dict, List, Optional


def _strong_normalize(s: Any) -> str:
    """Port of the Final Classifier `normalize`: lower, trim, strip accents,
    remove symbols, split, sort, join."""
    text = str(s or "").lower().strip()
    norm = unicodedata.normalize("NFD", text)
    no_accents = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    # remove non-word, non-space (\w in JS = [A-Za-z0-9_])
    cleaned = "".join(ch if (ch.isalnum() or ch == "_" or ch.isspace()) else " " for ch in no_accents)
    parts = [p for p in cleaned.split() if p]
    parts.sort()
    return " ".join(parts)


def _safe_parse(val: Any) -> List[Any]:
    if not val:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else []
        except Exception:  # noqa: BLE001
            return []
    return []


def final_classifier(all_runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Port of '🏆 Final Classifier1' (MASTER CONSOLIDATOR V2)."""
    if not all_runs:
        raise ValueError("Nenhum item recebido do DONE.")

    base_config = next((r for r in all_runs if r.get("geo_target") or r.get("language_code")), all_runs[0])

    build_map: Dict[str, Dict[str, Any]] = {}
    validation_map: Dict[str, Dict[str, Any]] = {}
    reports: List[Dict[str, Any]] = []

    for run in all_runs:
        master_bank = _safe_parse(run.get("master_bank"))
        reports.append(
            {"seed": run.get("seed_keyword"), "loop": run.get("loop_iteration"), "bank_size": len(master_bank)}
        )
        for kw in master_bank:
            key = _strong_normalize(kw.get("keyword"))
            if not key:
                continue
            normalized = {
                "keyword": kw.get("keyword"),
                "volume": kw.get("volume") or 0,
                "cpc": kw.get("cpc") or 0,
                "low_bid": kw.get("low_bid") or 0,
                "high_bid": kw.get("high_bid") or 0,
                "competition": kw.get("competition") or "UNKNOWN",
                "competition_index": kw.get("competition_index") or 0,
                # ⚠️ O ESTADO VIAJA JUNTO, E O DEFAULT É `unknown` — NUNCA
                # `measured`. Um banco vindo de uma origem que não grava estado
                # (autocomplete, contrato legado, fixture antiga) não pode ser
                # promovido a medido por omissão: seria a mesma coerção que
                # `or 0` fazia, uma camada acima e com nome melhor.
                "volume_estado": kw.get("volume_estado") or "unknown",
                "cpc_estado": kw.get("cpc_estado") or "unknown",
                "low_bid_estado": kw.get("low_bid_estado") or "unknown",
                "high_bid_estado": kw.get("high_bid_estado") or "unknown",
                "competition_index_estado": kw.get("competition_index_estado") or "unknown",
                "seed_origin": kw.get("seed_origin") or run.get("seed_keyword"),
                "found_in_loop": kw.get("found_in_loop", run.get("loop_iteration")),
                "variants": [],
            }
            existing = build_map.get(key)
            if not existing:
                build_map[key] = normalized
            elif normalized["volume"] > existing["volume"]:
                normalized["variants"] = list(
                    dict.fromkeys([*existing.get("variants", []), existing["keyword"], normalized["keyword"]])
                )
                build_map[key] = normalized
            else:
                existing["variants"] = list(
                    dict.fromkeys([*existing.get("variants", []), normalized["keyword"]])
                )
        for kw in master_bank:
            key = _strong_normalize(kw.get("keyword"))
            if not key:
                continue
            volume = kw.get("volume") or 0
            existing = validation_map.get(key)
            if not existing or volume > existing["volume"]:
                validation_map[key] = {"keyword": kw.get("keyword"), "volume": volume}

    build_queue = sorted(build_map.values(), key=lambda x: x["volume"], reverse=True)
    validation_keywords = sorted(validation_map.values(), key=lambda x: x["volume"], reverse=True)
    if not validation_keywords:
        validation_keywords = [{"keyword": i["keyword"], "volume": i["volume"]} for i in build_queue]

    loops_done = max((r.get("loop_iteration") or 0 for r in all_runs), default=0) + 1
    master_report = "\n".join(
        [
            "🧠 KEYWORD ENGINE CONSOLIDATION",
            "================================",
            "",
            f"Seed base: {base_config.get('seed_keyword')}",
            f"Loops executados: {loops_done}",
            f"Seeds processadas: {len(all_runs)}",
            f"Keywords únicas: {len(build_queue)}",
            "",
            "TOP 10:",
            *[f"- {k['keyword']} ({k['volume']})" for k in build_queue[:10]],
        ]
    )

    out = dict(base_config)
    out.update(
        {
            "build_queue": build_queue,
            "validation_keywords": validation_keywords,
            "master_report": master_report,
            "loop_runs": reports,
            "stats": {
                "seeds_processed": len(all_runs),
                "total_unique_keywords": len(build_queue),
                "validation_keywords": len(validation_keywords),
            },
        }
    )
    return out


def mega_merge(inputs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Port of '🔥 Mega Merger2'. Enriched keywords win; autocomplete fills gaps.

    Each input is a dict that is either {keywords:[...]} or a control_state
    (carrying master_bank/build_queue/validation_queue/loop_runs).
    """
    autocomplete_keywords: List[Dict[str, Any]] = []
    enriched_keywords: List[Dict[str, Any]] = []
    control_state: Optional[Dict[str, Any]] = None

    for json_item in inputs:
        kws = json_item.get("keywords")
        if isinstance(kws, list) and len(kws) > 0:
            sample = kws[0]
            if sample.get("needs_enrichment") is True or sample.get("source") == "google_autocomplete":
                autocomplete_keywords.extend(kws)
            else:
                enriched_keywords.extend(kws)
        elif (
            json_item.get("master_bank")
            or json_item.get("build_queue")
            or json_item.get("validation_queue")
            or json_item.get("loop_runs")
        ):
            control_state = json_item

    enriched_map: Dict[str, Dict[str, Any]] = {}
    for kw in enriched_keywords:
        enriched_map[str(kw.get("keyword", "")).lower().strip()] = kw
    for kw in autocomplete_keywords:
        key = str(kw.get("keyword", "")).lower().strip()
        if key not in enriched_map:
            enriched_map[key] = kw

    merged = list(enriched_map.values())
    merged.sort(key=lambda a: (a.get("volume") or 0), reverse=True)

    return {
        "keywords": merged,
        "total": len(merged),
        "control_state": control_state,
        "debug": {
            "inputs_received": len(inputs),
            "autocomplete_raw": len(autocomplete_keywords),
            "enriched_raw": len(enriched_keywords),
            "merged_unique": len(merged),
            "has_control_state": control_state is not None,
        },
    }
