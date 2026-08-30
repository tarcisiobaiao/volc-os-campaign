"""
Arbitrage scoring — faithful Python port of the n8n
"VOLC SEED ORACLE — RESULT PROCESSOR" Code node (Code in JavaScript2).

The nota de arbitragem (arbitrage_score) is the auditable heart of the
engine. It is intentionally pure (no I/O, no randomness) so it is fully
reproducible and unit-tested against the worked examples in
PAUTADOR_PRO_GOD_MODE.md.

    baseScore = volume*0.25 + rpm*0.40 + competition_inverted*0.35
    final     = baseScore * confidence_multiplier * tier_weight   (round 2dp)

RPM and competition carry the most weight because they are the profit
factors of the arbitrage (RPM > CPC). Tier S (1.5x) can push a score
above 100.
"""
from __future__ import annotations

import math
import re
from typing import Any, Optional


def _round2_half_up(value: float) -> float:
    """
    Replicate JS `Math.round(x * 100) / 100` (round-half-UP), NOT Python's
    round() which is banker's rounding. This keeps scores identical to the
    n8n prototype (e.g. 23.625 -> 23.63, not 23.62).
    """
    return math.floor(value * 100 + 0.5) / 100

# Qualitative -> numeric maps (verbatim from the n8n Code node)
VOLUME_SCORE = {"very_high": 100, "high": 75, "medium": 50, "low": 25}
RPM_SCORE = {"very_high": 100, "high": 75, "medium": 50, "low": 25}
COMPETITION_SCORE = {"low": 100, "medium": 50, "high": 25}  # INVERTED: low competition = best
CONFIDENCE_SCORE = {"very_high": 1.0, "high": 0.85, "medium": 0.7, "low": 0.5}
TIER_WEIGHT = {"S": 1.5, "A": 1.2, "B": 1.0, "EXPERIMENTAL": 0.9}

# Defaults applied when a value is missing/unknown (match the n8n `|| x` fallbacks)
_DEFAULT_VOLUME = 25
_DEFAULT_RPM = 25
_DEFAULT_COMPETITION = 50
_DEFAULT_CONFIDENCE = 0.7
_DEFAULT_TIER = 1.0

# Currency symbol -> ISO code (robustness improvement over the n8n parser,
# which only handled a trailing 3-letter code).
_SYMBOL_TO_CCY = {
    "R$": "BRL",
    "£": "GBP",
    "€": "EUR",
    "$": "USD",
    "¥": "JPY",
    "₹": "INR",
    "₩": "KRW",
    "kr": "SEK",
    "Q": "GTQ",
}


def calc_arbitrage_score(
    volume_estimate: Optional[str],
    rpm_potential: Optional[str],
    competition_estimate: Optional[str],
    confidence: Optional[str],
    tier: Optional[str],
) -> float:
    """Compute the arbitrage score from qualitative estimates. Rounded to 2dp."""
    vol = VOLUME_SCORE.get(volume_estimate, _DEFAULT_VOLUME)
    rpm = RPM_SCORE.get(rpm_potential, _DEFAULT_RPM)
    comp = COMPETITION_SCORE.get(competition_estimate, _DEFAULT_COMPETITION)
    conf = CONFIDENCE_SCORE.get(confidence, _DEFAULT_CONFIDENCE)
    tier_mult = TIER_WEIGHT.get(tier, _DEFAULT_TIER)

    base = (vol * 0.25) + (rpm * 0.40) + (comp * 0.35)
    adjusted = base * conf * tier_mult
    return _round2_half_up(adjusted)


def parse_cpc_range(cpc_string: Any) -> dict:
    """
    Parse a local-currency CPC range into {min, max, avg, currency, raw}.

    Handles the canonical agent format ("0.30-0.60 EUR"), symbol-prefixed
    display formats ("£1.20-£3.50"), and PT/ES locale ("0,10 a 0,30 SEK").
    """
    empty = {"min": None, "max": None, "avg": None, "currency": None, "raw": cpc_string}
    if not cpc_string or not isinstance(cpc_string, str):
        return empty

    text = cpc_string.strip()

    # currency: prefer an explicit 3-letter ISO code, else a known symbol
    currency: Optional[str] = None
    code = re.search(r"\b([A-Z]{3})\b", text)
    if code:
        currency = code.group(1)
    else:
        # longest symbol first so 'R$' wins over '$' regardless of dict order
        for sym in sorted(_SYMBOL_TO_CCY, key=len, reverse=True):
            if sym in text:
                currency = _SYMBOL_TO_CCY[sym]
                break

    # numbers: support both "." and "," as decimal separators
    raw_nums = re.findall(r"\d+(?:[.,]\d+)?", text)
    nums = [float(n.replace(",", ".")) for n in raw_nums]
    if not nums:
        return {"min": None, "max": None, "avg": None, "currency": currency, "raw": cpc_string}

    mn = nums[0]
    mx = nums[1] if len(nums) > 1 else nums[0]
    if mx < mn:
        mn, mx = mx, mn
    avg = round((mn + mx) / 2, 4)
    return {"min": mn, "max": mx, "avg": avg, "currency": currency, "raw": cpc_string}


def estimated_roi_signal(rpm_potential: Optional[str], cpc_avg: Optional[float]) -> Optional[float]:
    """Proxy for return signal: RPM_score / cpc_avg (rounded 2dp). None if no CPC."""
    if not cpc_avg or cpc_avg <= 0:
        return None
    rpm = RPM_SCORE.get(rpm_potential, _DEFAULT_RPM)
    return _round2_half_up(rpm / cpc_avg)


def _seed_id(index: int) -> str:
    return f"seed_{index + 1:03d}"


def enrich_seed(seed: dict, index: int) -> dict:
    """
    Enrich a raw agent seed with derived fields (seed_id, arbitrage_score,
    parsed CPC, ROI signal, timing flags, counts) — mirrors enrichSeed() in
    the n8n Code node. Returns a NEW dict (does not mutate the input).
    """
    cpc = parse_cpc_range(seed.get("cpc_estimate_local"))
    timing = seed.get("timing")
    variations = seed.get("variations") or []
    hooks = seed.get("expansion_hooks") or []

    enriched = dict(seed)
    enriched.update(
        {
            "seed_id": seed.get("seed_id") or _seed_id(index),
            "arbitrage_score": calc_arbitrage_score(
                seed.get("volume_estimate"),
                seed.get("rpm_potential"),
                seed.get("competition_estimate"),
                seed.get("confidence"),
                seed.get("tier"),
            ),
            "cpc_min": cpc["min"],
            "cpc_max": cpc["max"],
            "cpc_avg": cpc["avg"],
            "currency": cpc["currency"],
            "estimated_roi_signal": estimated_roi_signal(seed.get("rpm_potential"), cpc["avg"]),
            "has_seasonal_window": timing in ("seasonal", "event_driven"),
            "is_trending": timing == "trending",
            "variations_count": len(variations),
            "expansion_hooks_count": len(hooks),
        }
    )
    return enriched
