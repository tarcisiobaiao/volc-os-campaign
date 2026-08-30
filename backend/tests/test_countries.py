"""
Tests for the canonical 195-country dataset, resolver, geo mapper and the
generated TS artifact. Run: cd backend && pytest -q
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.agents.mining.geo import GeoLanguageMapper, resolve_geo
from app.data.countries import COUNTRIES, fallback_countries, flag_emoji, resolve_country

WEBGO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# --- dataset integrity --------------------------------------------------------
def test_exactly_195_active_sovereign():
    active_sovereign = [c for c in COUNTRIES if c["is_active"] and c["is_sovereign"]]
    assert len(active_sovereign) == 195


def test_unique_iso2_and_iso3():
    iso2 = [c["country_code"] for c in COUNTRIES]
    iso3 = [c["iso3"] for c in COUNTRIES]
    assert len(set(iso2)) == 195
    assert len(set(iso3)) == 195
    assert all(len(c) == 2 for c in iso2)
    assert all(len(c) == 3 for c in iso3)


def test_required_fields_present():
    for c in COUNTRIES:
        assert c["country_name"], c
        assert c["native_language"], c
        assert c["flag_emoji"], c
        assert c["market_tier"] in ("high_value", "medium_value", "volume_play"), c


def test_includes_vatican_and_palestine_not_taiwan():
    codes = {c["country_code"] for c in COUNTRIES}
    assert "VA" in codes and "PS" in codes          # Holy See + Palestine
    assert "TW" not in codes and "XK" not in codes  # Taiwan / Kosovo are NOT UN members


def test_flag_emoji_derivation():
    assert flag_emoji("BR") == "🇧🇷"
    assert flag_emoji("GB") == "🇬🇧"


# --- resolution ---------------------------------------------------------------
@pytest.mark.parametrize("q,iso2", [
    ("Brasil", "BR"), ("Brazil", "BR"), ("BR", "BR"), ("BRA", "BR"), ("brasil", "BR"),
    ("Reino Unido", "GB"), ("United Kingdom", "GB"), ("GB", "GB"), ("GBR", "GB"), ("UK", "GB"),
    ("México", "MX"), ("mexico", "MX"), ("MEX", "MX"),
    ("Suíça", "CH"), ("suica", "CH"), ("Switzerland", "CH"),
    ("Estados Unidos", "US"), ("United States", "US"), ("eua", "US"), ("USA", "US"),
])
def test_resolve_by_name_alias_accent(q, iso2):
    c = resolve_country(q)
    assert c is not None and c["country_code"] == iso2


def test_resolve_prefers_code():
    assert resolve_country("qualquer", code="DE")["country_code"] == "DE"
    assert resolve_country(None, code="DEU")["country_code"] == "DE"


def test_market_tier_classification_is_coherent():
    by = {c["country_code"]: c["market_tier"] for c in COUNTRIES}
    assert by["US"] == "high_value" and by["GB"] == "high_value" and by["JP"] == "high_value"
    assert by["BR"] == "medium_value" and by["MX"] == "medium_value"
    assert by["AO"] == "volume_play"  # Angola


# --- geo mapper ---------------------------------------------------------------
def test_geo_mapper_known_geo_target():
    gb = GeoLanguageMapper.map("Reino Unido", "GB")
    assert gb["resolved"] and gb["Criteria_ID"] == 2826 and gb["language_constant"] == 1000
    br = GeoLanguageMapper.map("brasil", None)
    assert br["country_code"] == "BR" and br["Criteria_ID"] == 2076


def test_geo_mapper_resolves_but_geo_target_may_be_null():
    # Angola is in the 195 but has no confident Google Ads geo target -> null, not invented
    ao = GeoLanguageMapper.map("Angola", "AO")
    assert ao["resolved"] is True
    assert ao["Criteria_ID"] is None and ao["geo_target_known"] is False
    assert ao["language_code"] == "pt"  # still resolves language


def test_geo_mapper_unresolved_is_safe():
    x = GeoLanguageMapper.map("Atlântida", "ZZ")
    assert x["resolved"] is False and x["Criteria_ID"] is None


def test_resolve_geo_returns_canonical():
    assert resolve_geo("Kenya")["country_code"] == "KE"


# --- API fallback -------------------------------------------------------------
def test_fallback_countries_returns_195():
    fb = fallback_countries()
    assert len(fb) == 195
    assert all({"country_code", "country_name", "native_language", "market_tier", "flag_emoji"} <= set(c) for c in fb)


# --- generated TS artifact cross-check ----------------------------------------
def test_generated_ts_has_195_countries():
    ts_path = os.path.join(WEBGO, "src", "data", "pautadorCountries.ts")
    assert os.path.exists(ts_path), "rode backend/scripts/gen_country_artifacts.py"
    text = open(ts_path, encoding="utf-8").read()
    assert text.count('"country_code"') == 195
