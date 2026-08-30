"""
API tests for the rewired /mine and /funnel endpoints (offline / mock).

Run:  cd backend && pytest -q
"""
from __future__ import annotations

import os
import sys

# Force a fully-offline, mock configuration BEFORE importing the app.
for _k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "PERPLEXITY_API_KEY", "PAUTADOR_API_KEY", "DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD"):
    os.environ[_k] = ""
os.environ["PAUTADOR_ENGINE"] = "mock"
os.environ["PAUTADOR_KW_ENGINE"] = "mock"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings

get_settings.cache_clear()  # drop any cached real-env settings

from app.main import app  # noqa: E402

client = TestClient(app)

OPP = {
    "id": 0, "country": "Reino Unido", "country_code": "GB", "native_language": "en-GB",
    "keyword": "universal credit application", "main_keyword": "universal credit",
    "tier": "S", "category": "S3", "intent": "informational", "persona": "Liam",
    "pain_point": "duvida", "reasoning": "alto rpm", "variations": ["universal credit 2025"],
    "expansion_hooks": ["como aplicar"], "status": "discovered",
}


def test_mine_dry_mock_returns_rich_output():
    r = client.post("/api/pautador/opportunities/0/mine", json={"opportunity": OPP})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["engine"] == "mock"
    assert body["persisted"] is False
    assert len(body["production_ads_queue"]) > 0
    assert len(body["content_seo_queue"]) > 0
    assert any(s.startswith("google_ads") for s in body["services_used"])
    assert body["cluster"]["keywords"]  # backward-compat cluster present
    # rich contract fields now exposed (verified by the adversarial review)
    assert body["funnel_prospector"] is not None
    assert isinstance(body["raw_keywords"], list) and len(body["raw_keywords"]) > 0
    assert isinstance(body["duration_ms"], int)


def test_funnel_dry_with_inline_cluster():
    mine = client.post("/api/pautador/opportunities/0/mine", json={"opportunity": OPP}).json()
    r = client.post("/api/pautador/opportunities/0/funnel", json={"opportunity": OPP, "cluster": mine})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["funnel"]["pages"]) == 5
    assert len(body["writing_jobs"]) == 5
    assert body["funnel_strategy"] is not None


def test_funnel_dry_without_cluster_still_builds():
    # In DRY mode there's no DB to enforce mine-first; the funnel falls back to
    # the opportunity's own data (the 409 guard is for DB-backed cards).
    r = client.post("/api/pautador/opportunities/0/funnel", json={"opportunity": OPP})
    assert r.status_code == 200, r.text
    assert len(r.json()["funnel"]["pages"]) == 5


def test_funnel_db_without_cluster_returns_409(monkeypatch):
    """DB-backed opportunity with no prior mining -> clear 409 'minere antes'."""

    class FakeSupa:
        def __init__(self, settings):
            pass

        enabled = True

        async def get_opportunity(self, opp_id):
            return {**OPP, "id": opp_id, "run_id": 1}

        async def get_latest_cluster(self, opp_id):
            return None

    monkeypatch.setattr("app.routers.pautador.SupabaseService", FakeSupa)
    r = client.post("/api/pautador/opportunities/42/funnel", json={})
    assert r.status_code == 409
    assert "Minere a oportunidade antes" in r.json()["detail"]


def test_mine_missing_opportunity_returns_404():
    # no DB, no inline opportunity -> 404 with a clear hint
    r = client.post("/api/pautador/opportunities/99/mine", json={})
    assert r.status_code == 404


def test_health_reports_kw_readiness_without_secrets():
    body = client.get("/api/pautador/health").json()
    assert "google_ads" in body and "dataforseo" in body and "kw_engine" in body
    ga = body["google_ads"]
    assert set(ga.keys()) == {"mode", "ready", "missing"}
    # ready/mode depend on the local .env; assert the SHAPE + invariants only.
    assert isinstance(ga["ready"], bool)
    assert ga["mode"] in {"none", "service_account", "oauth_refresh_token"}
    # health must NEVER leak secret VALUES — `missing` carries only key names
    assert all("=" not in m for m in ga["missing"])
