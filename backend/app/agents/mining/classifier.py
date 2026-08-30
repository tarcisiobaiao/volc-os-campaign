"""
Gold Miner classifier — faithful port of n8n-peneirador-kw.json node
"Code in JavaScript6" (🏆 GOLD MINER V11 — MULTILINGUAL TIME WARP EDITION).

Classifies merged keywords into:
  - production_ads_queue  (titans + future + gems, vol-sorted, dedup, top 200)
  - content_seo_queue     (questions + hidden_trends + seasonal, dedup, top 50)
Applies multilingual Time Warp (past year -> current, except debt/history),
trend analysis and seasonal-peak detection.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

QUESTION_WORDS = [
    # PT-BR
    "como", "porque", "por que", "onde", "qual", "quais",
    "quando", "quanto", "quem", "o que é", "pra que",
    # ES
    "cómo", "porque", "por qué", "dónde", "donde", "cuál",
    "cuáles", "cuándo", "cuando", "cuánto", "quién", "qué es",
    # EN
    "how", "why", "where", "which", "when", "what is",
    "what are", "who", "how to", "how much", "how many",
    # FR
    "comment", "pourquoi", "où", "quel", "quelle", "quand",
    "combien", "qui", "qu'est-ce",
    # DE
    "wie", "warum", "wo", "welche", "welcher", "wann",
    "wieviel", "wer", "was ist",
    # IT
    "come", "perché", "dove", "quale", "quali", "quando",
    "quanto", "chi", "cosa è", "cos'è",
]

DEBT_EXCLUSION_WORDS = [
    # PT-BR
    "atrasado", "atrasada", "vencido", "vencida", "divida", "dívida",
    "debito", "débito", "anterior", "passado", "retroativo", "retroativa",
    "resultado", "resultados", "histórico", "encerrado", "finalizado",
    # ES
    "atrasado", "atrasada", "vencido", "vencida", "deuda", "débito",
    "anterior", "pasado", "retroactivo", "resultado", "resultados",
    "histórico", "cerrado", "finalizado",
    # EN
    "overdue", "expired", "debt", "debit", "previous", "past",
    "retroactive", "result", "results", "historical", "closed",
    "ended", "finished", "final", "recap", "review", "summary",
    # FR
    "arriéré", "expiré", "dette", "antérieur", "passé",
    "résultat", "résultats", "historique", "terminé", "clôturé",
    # DE
    "überfällig", "abgelaufen", "schuld", "schulden", "vorherig",
    "vergangen", "ergebnis", "ergebnisse", "historisch", "beendet",
    # IT
    "scaduto", "scaduta", "debito", "anteriore", "passato",
    "risultato", "risultati", "storico", "terminato", "chiuso",
]

MONTH_WORDS = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    "enero": 1, "febrero": 2, "marzo": 3, "abril_es": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto_es": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "janvier": 1, "février": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
    "januar": 1, "februar": 2, "märz": 3, "april_de": 4,
    "mai_de": 5, "juni": 6, "juli": 7, "august_de": 8,
    "september_de": 9, "oktober": 10, "november_de": 11, "dezember": 12,
    "gennaio": 1, "febbraio": 2, "marzo_it": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto_it": 8,
    "settembre": 9, "ottobre": 10, "novembre_it": 11, "dicembre": 12,
}
_MONTH_PATTERNS = [re.sub(r"_[a-z]{2}$", "", m) for m in MONTH_WORDS.keys()]
UNIQUE_MONTHS = list(dict.fromkeys(_MONTH_PATTERNS))


def _contains_any(text: str, words: List[str]) -> bool:
    return any(w in text for w in words)


def _detect_month(text: str) -> Optional[str]:
    for month in UNIQUE_MONTHS:
        if month in text:
            return month
    return None


def _trend_score(monthly: Any) -> int:
    if not isinstance(monthly, list) or len(monthly) < 3:
        return 0
    ordered = sorted(monthly, key=lambda x: (x.get("year", 0), x.get("month", 0)))
    recent3 = ordered[-3:]
    older3 = ordered[:3]
    avg_recent = sum(x.get("search_volume", 0) or 0 for x in recent3) / len(recent3)
    avg_older = sum(x.get("search_volume", 0) or 0 for x in older3) / len(older3)
    if avg_older == 0:
        return 999 if avg_recent > 0 else 0
    return round(((avg_recent - avg_older) / avg_older) * 100)


def _detect_seasonal_peak(monthly: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(monthly, list) or len(monthly) < 6:
        return None
    best = monthly[0]
    for x in monthly:
        if (x.get("search_volume", 0) or 0) > (best.get("search_volume", 0) or 0):
            best = x
    avg = sum(x.get("search_volume", 0) or 0 for x in monthly) / len(monthly)
    if (best.get("search_volume", 0) or 0) > avg * 2.5:
        return {
            "month": best.get("month"),
            "year": best.get("year"),
            "spike_ratio": round((best.get("search_volume", 0) or 0) / avg * 10) / 10,
        }
    return None


def gold_miner_classify(raw_keywords: List[Dict[str, Any]], *, today: Optional[datetime] = None) -> Dict[str, Any]:
    """Port of GOLD MINER V11. `today` injectable for deterministic tests."""
    date = today or datetime.now(timezone.utc)
    current_year = date.year
    last_year = current_year - 1
    next_year = current_year + 1
    two_years_ago = current_year - 2

    CY, LY, NY, TY = str(current_year), str(last_year), str(next_year), str(two_years_ago)

    config = {
        "volume_titan": 20000,
        "volume_scale": 5000,
        "max_cpc_scale": 0.60,
        "volume_gem": 1000,
        "years_target": [CY, NY],
        "years_warp": [LY, TY],
        "max_content_queue": 50,
        "max_ads_queue": 200,
    }

    gold = {
        "titans": [], "future": [], "gems": [], "hidden_trends": [],
        "questions": [], "seasonal": [], "discards": [],
    }

    for k in raw_keywords:
        vol = int(k.get("volume") or 0)
        cpc = float(k.get("cpc") or 0)
        comp = str(k.get("competition") or "").upper()
        monthly = k.get("monthly_searches") or []

        kw_text = str(k.get("keyword") or "").lower()
        display_keyword = str(k.get("keyword") or "")
        tags = list(k.get("smart_tags") or [])
        reliability = k.get("data_reliability") or "LOW"
        warp_reason = ""

        # TIME WARP
        for old_year in config["years_warp"]:
            if old_year in kw_text:
                if not _contains_any(kw_text, DEBT_EXCLUSION_WORDS):
                    display_keyword = display_keyword.replace(old_year, CY)
                    kw_text = display_keyword.lower()
                    tags.append("TIME_WARP")
                    warp_reason = f" [{old_year}→{CY}]"
                else:
                    tags.append("HISTORICAL_REFERENCE")
                break

        trend = _trend_score(monthly)
        peak = _detect_seasonal_peak(monthly)
        if trend > 200:
            tags.append("EXPLOSIVE_TREND")
        elif trend > 100:
            tags.append("STRONG_TREND")
        elif trend > 50:
            tags.append("RISING")
        elif trend < -50:
            tags.append("DECLINING")
        if peak:
            tags.append("SEASONAL")
        if _detect_month(kw_text):
            tags.append("MONTH_SPECIFIC")

        processed = {
            "keyword": display_keyword,
            "volume": vol,
            "cpc": cpc,
            "competition": comp,
            "tags": tags,
            "trend_score": trend,
            "seasonal_peak": peak,
            "reason": "",
        }
        approved = False

        # R1 questions
        if _contains_any(kw_text, QUESTION_WORDS):
            tags.append("USER_QUESTION")
            gold["questions"].append({**processed})

        # R2 hidden trends
        if vol == 0 and k.get("source") == "google_autocomplete":
            tags.append("HIDDEN_TREND")
            processed["reason"] = "Google Autocomplete suggestion — no historical data yet."
            gold["hidden_trends"].append(processed)
            continue

        # R3 dead keywords
        if vol == 0 and reliability == "HIGH":
            gold["discards"].append(display_keyword + " (vol=0 confirmed)")
            continue

        # R4 seasonal spike
        if peak and (peak.get("spike_ratio") or 0) > 3:
            tags.append("SEASONAL_SPIKE")
            processed["reason"] = f"Seasonal spike {peak['spike_ratio']}x avg (M{peak['month']}){warp_reason}"
            gold["seasonal"].append({**processed})

        # R5 ads classification
        if vol >= config["volume_titan"]:
            tags.append("VOLUME_TITAN")
            processed["reason"] = f"Massive Volume ({round(vol / 1000)}k){warp_reason}"
            gold["titans"].append(processed)
            approved = True
        elif any(y in kw_text for y in config["years_target"]):
            tags.append("FUTURE_TREND")
            processed["reason"] = f"Temporal Trend{warp_reason}"
            gold["future"].append(processed)
            approved = True
        elif vol >= config["volume_scale"] and cpc <= config["max_cpc_scale"]:
            tags.append("SCALE_OPPORTUNITY")
            processed["reason"] = f"Good Volume + Affordable CPC{warp_reason}"
            gold["gems"].append(processed)
            approved = True
        elif vol >= config["volume_gem"] and (comp == "LOW" or cpc < 0.20):
            tags.append("HIDDEN_GEM")
            processed["reason"] = f"Low Competition / Low Cost{warp_reason}"
            gold["gems"].append(processed)
            approved = True
        elif vol >= 100 and trend > 200:
            tags.append("EXPLOSIVE_MICRO")
            processed["reason"] = f"Low volume but {trend}% growth{warp_reason}"
            gold["gems"].append(processed)
            approved = True

        if not approved and "USER_QUESTION" not in tags:
            gold["discards"].append(display_keyword)

    def _sort_key(x: Dict[str, Any]):
        return (x.get("volume", 0), x.get("trend_score", 0))

    ads_queue = sorted(
        [*gold["titans"], *gold["future"], *gold["gems"]], key=_sort_key, reverse=True
    )
    content_queue = [*gold["questions"], *gold["hidden_trends"], *gold["seasonal"]]

    def _dedup(arr: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        m: Dict[str, Dict[str, Any]] = {}
        for item in arr:
            key = str(item.get("keyword", "")).lower().strip()
            if key not in m or (item.get("volume", 0) > (m[key].get("volume", 0) or 0)):
                m[key] = item
        return list(m.values())

    unique_ads = _dedup(ads_queue)[: config["max_ads_queue"]]
    unique_content = _dedup(content_queue)[: config["max_content_queue"]]

    return {
        "summary": {
            "total_analyzed": len(raw_keywords),
            "ads_approved": len(unique_ads),
            "content_ideas": len(unique_content),
            "year_context": {"current": CY, "last": LY, "next": NY, "warped_from": config["years_warp"]},
            "breakdown": {
                "titans": len(gold["titans"]),
                "gems": len(gold["gems"]),
                "future": len(gold["future"]),
                "seasonal": len(gold["seasonal"]),
                "hidden_trends": len(gold["hidden_trends"]),
                "questions": len(gold["questions"]),
                "discards": len(gold["discards"]),
            },
            "languages_supported": ["pt-br", "es", "en", "fr", "de", "it"],
        },
        "production_ads_queue": unique_ads,
        "content_seo_queue": unique_content,
    }
