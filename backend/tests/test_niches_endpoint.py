"""
Testes do catálogo de nichos (R1): resolve_niches() + GET/POST /api/pautador/niches.
Run:  cd backend && pytest -q
"""
from __future__ import annotations

import os
import sys

# Força ambiente offline/mock ANTES de importar o app (sem Supabase -> fallback seed).
for _k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "PERPLEXITY_API_KEY", "PAUTADOR_API_KEY", "DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD"):
    os.environ[_k] = ""
os.environ["PAUTADOR_ENGINE"] = "mock"
os.environ["PAUTADOR_KW_ENGINE"] = "mock"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from app.config import get_settings
from app.data.niches import SEED_NICHES, resolve_niches

get_settings.cache_clear()  # drop any cached real-env settings

from app.main import app  # noqa: E402

client = TestClient(app)


def test_resolve_niches_filters_by_slug():
    result = resolve_niches(["financas"])
    assert len(result) == 1
    assert result[0]["slug"] == "financas"
    assert result[0] == next(n for n in SEED_NICHES if n["slug"] == "financas")


def test_resolve_niches_empty_slugs_returns_all():
    assert resolve_niches([]) == SEED_NICHES
    assert resolve_niches(None) == SEED_NICHES


def test_resolve_niches_uses_db_rows_when_given():
    db_rows = [{"slug": "custom", "label": "Custom"}]
    assert resolve_niches(["custom"], db_rows=db_rows) == db_rows
    assert resolve_niches(["financas"], db_rows=db_rows) == []


def test_get_niches_returns_seed_fallback_without_supabase():
    r = client.get("/api/pautador/niches")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "seed"
    assert len(body["niches"]) >= 6
    for niche in body["niches"]:
        assert "slug" in niche
        assert "label" in niche
        assert "guidance" in niche
        assert "allowed_verticals" in niche


class _FakeSupaDuplicateNiche:
    """SupabaseService fake (enabled=True, sem rede) que simula a violação de
    `UNIQUE(slug)` do PostgREST/Postgres ao criar um nicho já existente."""

    enabled = True

    def __init__(self, settings=None):
        pass

    async def insert_niche(self, payload):
        raise RuntimeError(
            "409 Client Error: Conflict for url: .../pautador_niches — "
            'duplicate key value violates unique constraint "pautador_niches_slug_key" '
            "(code 23505)"
        )


def test_post_niches_duplicate_slug_returns_409(monkeypatch):
    """FIX 3: violação de UNIQUE(slug) deve virar um 409 amigável, não um 5xx cru."""
    monkeypatch.setattr("app.routers.entities.SupabaseService", _FakeSupaDuplicateNiche)
    r = client.post("/api/pautador/niches", json={"slug": "financas", "label": "Finanças"})
    assert r.status_code == 409, r.text
    assert "já existe" in r.json()["detail"].lower()


class _FakeSupaBrokenNiche:
    """Falha genérica (não-duplicata) -> continua virando 502, como os demais
    mutadores do router."""

    enabled = True

    def __init__(self, settings=None):
        pass

    async def insert_niche(self, payload):
        raise RuntimeError("connection reset by peer")


def test_post_niches_generic_error_returns_502(monkeypatch):
    monkeypatch.setattr("app.routers.entities.SupabaseService", _FakeSupaBrokenNiche)
    r = client.post("/api/pautador/niches", json={"slug": "novo-nicho", "label": "Novo"})
    assert r.status_code == 502, r.text
