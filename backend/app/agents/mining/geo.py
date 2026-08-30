"""
Geo + Language Mapper — now backed by the canonical 195-country dataset
(app.data.countries), replacing the old ~17-country hardcoded map.

Resolves a country by ISO2, ISO3, PT-BR name, English name, native name or
alias (accent- and case-insensitive). For Google Ads / DataForSEO it exposes
google_ads_geo_target + language_constant + language_code/short — which may be
NULL when not confidently known (the orchestrator then warns and falls back to
mock instead of querying the wrong geo).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.data.countries import resolve_country


def resolve_geo(
    country_name: Optional[str] = None,
    country_code: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return the canonical country dict (or None). Tries code first, then name."""
    return resolve_country(country_name, code=country_code)


class GeoLanguageMapper:
    """Adapter for the mining pipeline. Entry point is the Pautador card's country."""

    name = "GeoLanguageMapper"

    @staticmethod
    def map(country_name: Optional[str], country_code: Optional[str]) -> Dict[str, Any]:
        geo = resolve_country(country_name, code=country_code)
        if not geo:
            return {
                "País_Geo": country_name or "Não encontrado",
                "Criteria_ID": None,
                "language_code": None,
                "language_short": None,
                "language_constant": None,
                "currency_code": None,
                "country_code": (country_code or None),
                "resolved": False,
                "geo_target_known": False,
            }
        return {
            "País_Geo": geo["country_name"],
            "Criteria_ID": geo.get("google_ads_geo_target"),
            "language_code": geo.get("language_code"),
            "language_short": geo.get("language_short"),
            "language_constant": geo.get("language_constant"),
            "currency_code": geo.get("currency_code"),
            "country_code": geo.get("country_code"),
            "resolved": True,
            "geo_target_known": geo.get("google_ads_geo_target") is not None,
        }
