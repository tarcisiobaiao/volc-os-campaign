"""
CriticValidatorAgent — guards the seed set before scoring/persistence.

- normalizes & validates enums (tier/category/qualitative/intent/timing)
- drops seeds missing required fields or with unrecoverable tier/category
- deduplicates by lower(keyword)
- checks the 8/14/12/6 tier distribution and emits warnings (never hard-fails)
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.agents.base import BaseAgent

_TIERS = {"S", "A", "B", "EXPERIMENTAL"}
_CATEGORIES = {
    "S1", "S2", "S3", "S4", "S5", "S6",
    "A1", "A2", "A3", "A4",
    "B1", "B2", "B3", "EXP",
}
_QUAL4 = {"low", "medium", "high", "very_high"}
_COMPETITION = {"low", "medium", "high"}
_INTENT = {"informational", "navigational", "calculator", "comparison"}
_TIMING = {"evergreen", "seasonal", "event_driven", "trending"}
_TARGET = {"S": 8, "A": 14, "B": 12, "EXPERIMENTAL": 6}

_TIER_ALIASES = {"EXP": "EXPERIMENTAL", "EXPERIMENT": "EXPERIMENTAL"}


def _norm_enum(value: Any, allowed: set, default: Any = None) -> Any:
    if value is None:
        return default
    v = str(value).strip().lower()
    return v if v in allowed else default


class CriticValidatorAgent(BaseAgent):
    name = "CriticValidatorAgent"
    phase = "discovery"

    def run(self, seeds: List[Dict[str, Any]], expected_count: int = 40) -> Tuple[List[Dict[str, Any]], List[str]]:
        warnings: List[str] = []
        cleaned: List[Dict[str, Any]] = []
        seen: set = set()
        dropped = 0

        for seed in seeds or []:
            if not isinstance(seed, dict):
                dropped += 1
                continue
            keyword = (seed.get("keyword") or "").strip()
            main_keyword = (seed.get("main_keyword") or "").strip()
            tier = str(seed.get("tier") or "").strip().upper()
            tier = _TIER_ALIASES.get(tier, tier)
            category = str(seed.get("category") or "").strip().upper()

            if not keyword or not main_keyword or tier not in _TIERS or category not in _CATEGORIES:
                dropped += 1
                continue

            dedupe_key = keyword.lower()
            if dedupe_key in seen:
                dropped += 1
                continue
            seen.add(dedupe_key)

            cleaned.append(
                {
                    **seed,
                    "keyword": keyword,
                    "main_keyword": main_keyword,
                    "tier": tier,
                    "category": category,
                    "volume_estimate": _norm_enum(seed.get("volume_estimate"), _QUAL4),
                    "rpm_potential": _norm_enum(seed.get("rpm_potential"), _QUAL4),
                    "competition_estimate": _norm_enum(seed.get("competition_estimate"), _COMPETITION),
                    "confidence": _norm_enum(seed.get("confidence"), _QUAL4),
                    "intent": _norm_enum(seed.get("intent"), _INTENT),
                    "timing": _norm_enum(seed.get("timing"), _TIMING),
                    "variations": [str(v) for v in (seed.get("variations") or [])],
                    "expansion_hooks": [str(v) for v in (seed.get("expansion_hooks") or [])],
                }
            )

        if dropped:
            warnings.append(f"{dropped} seed(s) descartada(s) por inválida(s)/duplicada(s).")

        if len(cleaned) != expected_count:
            warnings.append(f"Esperado {expected_count} seeds, obtido {len(cleaned)}.")

        # distribution check (advisory only)
        counts = {t: 0 for t in _TIERS}
        for s in cleaned:
            counts[s["tier"]] += 1
        if expected_count == 40:
            for tier, target in _TARGET.items():
                if counts[tier] != target:
                    warnings.append(
                        f"Distribuição de tier {tier}: {counts[tier]} (alvo {target})."
                    )

        self.log(
            f"Validação: {len(cleaned)} seeds válidas, {dropped} descartadas.",
            step="validate",
            payload={"counts": counts, "warnings": warnings},
        )
        return cleaned, warnings
