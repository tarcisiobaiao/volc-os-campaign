"""
Entity-level arbitrage scoring. Reuses the audited keyword formula
(app.scoring.calc_arbitrage_score) but evaluates the ENTITY's potential from
its qualitative levels (volume/rpm/competition/confidence + tier), mapping the
LLM's PT/ES labels ("Alto", "Muito alto", "Baixa") to the canonical scale.
"""
from __future__ import annotations

import unicodedata
from typing import Optional, Tuple

from app.scoring import calc_arbitrage_score, estimated_roi_signal

_QUAL = {"low", "medium", "high", "very_high"}


def _norm(label: Optional[str]) -> Optional[str]:
    if not label:
        return None
    t = unicodedata.normalize("NFD", str(label).strip().lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    if t in _QUAL:
        return t
    if t in ("muito alto", "muito alta", "very high", "muy alto", "muy alta", "altissimo"):
        return "very_high"
    if t in ("alto", "alta", "high"):
        return "high"
    if t in ("medio", "media", "medium", "moderado", "moderada"):
        return "medium"
    if t in ("baixo", "baixa", "bajo", "baja", "low"):
        return "low"
    return None


def normalize_level(label: Optional[str]) -> Optional[str]:
    """Public: PT/ES level label -> low|medium|high|very_high (or None)."""
    return _norm(label)


def compute_entity_score(opp: dict) -> Tuple[Optional[float], Optional[float], str]:
    """
    Return (score, roi_signal, source).

    Prefer a deterministic score from the qualitative levels (auditable); fall
    back to the LLM-provided `score` if levels are insufficient.
    """
    volume = _norm(opp.get("volume_level"))
    rpm = _norm(opp.get("rpm_level"))
    comp = _norm(opp.get("competition_level"))
    conf = _norm(opp.get("confidence_level"))
    tier = (opp.get("gold_tier") or "B")
    tier = tier if tier in ("S", "A", "B", "EXPERIMENTAL") else "B"

    cpc_min = opp.get("cpc_min")
    cpc_max = opp.get("cpc_max")
    cpc_avg = None
    if isinstance(cpc_min, (int, float)) and isinstance(cpc_max, (int, float)):
        cpc_avg = round((cpc_min + cpc_max) / 2, 4)
    elif isinstance(cpc_min, (int, float)):
        cpc_avg = float(cpc_min)

    if any([volume, rpm, comp, conf]):
        score = calc_arbitrage_score(volume, rpm, comp, conf, tier)
        roi = opp.get("roi_signal")
        if roi is None and rpm:
            roi = estimated_roi_signal(rpm, cpc_avg)
        return score, roi, "computed"

    # fallback: trust the LLM score
    llm_score = opp.get("score")
    if isinstance(llm_score, (int, float)):
        return round(float(llm_score), 4), opp.get("roi_signal"), "llm"
    return None, opp.get("roi_signal"), "none"
