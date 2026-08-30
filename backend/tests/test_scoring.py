"""
TDD for the arbitrage scoring core — a faithful Python port of the n8n
"VOLC SEED ORACLE — RESULT PROCESSOR" Code node.

Expected values are taken DIRECTLY from PAUTADOR_PRO_GOD_MODE.md worked
examples (Reino Unido seeds), so the port is provably reproducible:

  seed_001  vol very_high, rpm high,      comp low,    conf very_high, S  -> 135.0
  seed_002  vol high,      rpm very_high, comp medium, conf very_high, S  -> 114.38
  seed_005  vol very_high, rpm high,      comp medium, conf very_high, S  -> 108.75
  seed_003  vol very_high, rpm medium,    comp low,    conf high,      S  -> 102.0
  seed_017  vol very_high, rpm very_high, comp high,   conf very_high, A  ->  88.5

Run standalone:  python tests/test_scoring.py
Or with pytest:  pytest tests/test_scoring.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.scoring import (  # noqa: E402
    calc_arbitrage_score,
    parse_cpc_range,
    estimated_roi_signal,
    enrich_seed,
)


def test_seed_001_pure_gold():
    assert calc_arbitrage_score("very_high", "high", "low", "very_high", "S") == 135.0


def test_seed_002():
    assert calc_arbitrage_score("high", "very_high", "medium", "very_high", "S") == 114.38


def test_seed_005():
    assert calc_arbitrage_score("very_high", "high", "medium", "very_high", "S") == 108.75


def test_seed_003_confidence_high():
    assert calc_arbitrage_score("very_high", "medium", "low", "high", "S") == 102.0


def test_seed_017_tier_a():
    assert calc_arbitrage_score("very_high", "very_high", "high", "very_high", "A") == 88.5


def test_defaults_when_missing():
    # vol 25, rpm 25, comp 50, conf 0.7, tier 1.0
    # (25*.25 + 25*.40 + 50*.35) * 0.7 * 1.0 = 33.75 * 0.7 = 23.625 -> 23.63
    assert calc_arbitrage_score(None, None, None, None, None) == 23.63
    assert calc_arbitrage_score("bogus", "bogus", "bogus", "bogus", "bogus") == 23.63


def test_experimental_tier_weight():
    # EXPERIMENTAL multiplier is 0.9
    s = calc_arbitrage_score("high", "high", "low", "high", "EXPERIMENTAL")
    base = 75 * 0.25 + 75 * 0.40 + 100 * 0.35  # 18.75 + 30 + 35 = 83.75
    assert s == round(base * 0.85 * 0.9, 2)


def test_parse_cpc_currency_code_suffix():
    r = parse_cpc_range("0.30-0.60 EUR")
    assert r["min"] == 0.30 and r["max"] == 0.60 and r["avg"] == 0.45
    assert r["currency"] == "EUR"


def test_parse_cpc_symbol_prefix():
    r = parse_cpc_range("£1.20-£3.50")
    assert r["min"] == 1.20 and r["max"] == 3.50 and r["avg"] == 2.35
    assert r["currency"] == "GBP"


def test_parse_cpc_portuguese_comma_and_a():
    r = parse_cpc_range("0,10 a 0,30 SEK")
    assert r["min"] == 0.10 and r["max"] == 0.30
    assert r["currency"] == "SEK"


def test_parse_cpc_empty():
    r = parse_cpc_range(None)
    assert r["min"] is None and r["avg"] is None and r["currency"] is None


def test_roi_signal():
    # rpm high -> 75 ; cpc_avg 2.35 -> 75/2.35 = 31.91
    assert estimated_roi_signal("high", 2.35) == 31.91
    assert estimated_roi_signal("high", 0) is None
    assert estimated_roi_signal("high", None) is None


def test_enrich_seed_shape():
    seed = {
        "keyword": "how to recover government gateway id without authenticator app",
        "main_keyword": "gateway authenticator app",
        "tier": "S",
        "volume_estimate": "very_high",
        "rpm_potential": "high",
        "competition_estimate": "low",
        "confidence": "very_high",
        "cpc_estimate_local": "£1.20-£3.50",
        "timing": "evergreen",
        "variations": ["a", "b"],
        "expansion_hooks": ["x"],
    }
    e = enrich_seed(seed, 0)
    assert e["seed_id"] == "seed_001"
    assert e["arbitrage_score"] == 135.0
    assert e["cpc_min"] == 1.20 and e["cpc_max"] == 3.50 and e["cpc_avg"] == 2.35
    assert e["currency"] == "GBP"
    assert e["estimated_roi_signal"] == round(75 / 2.35, 2)
    assert e["has_seasonal_window"] is False
    assert e["is_trending"] is False
    assert e["variations_count"] == 2
    assert e["expansion_hooks_count"] == 1


def _run_standalone():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_standalone() else 0)
