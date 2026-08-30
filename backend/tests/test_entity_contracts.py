"""
Contratos de nicho/sazonalidade + niche_slug (R1/R2/R4).
Cobre: EntityDiscoveryRequest.niches/seasonality (com defaults backward-compatible)
e EntitySpec.niche_slug.

Run:  cd backend && pytest tests/test_entity_contracts.py -v
"""
from __future__ import annotations

import os
import sys

# offline/mock BEFORE importing the app (padrão dos demais testes do projeto)
for _k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "PERPLEXITY_API_KEY", "PAUTADOR_API_KEY"):
    os.environ[_k] = ""
os.environ["PAUTADOR_ENGINE"] = "mock"
os.environ["PAUTADOR_KW_ENGINE"] = "mock"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pydantic import ValidationError

from app.entities.schemas import EntityDiscoveryRequest, EntitySpec


def test_discovery_request_accepts_niches_and_seasonality():
    r = EntityDiscoveryRequest(country="Brasil", niches=["financas"], seasonality="evergreen")
    assert r.niches == ["financas"]
    assert r.seasonality == "evergreen"


def test_discovery_request_defaults_are_backward_compatible():
    r = EntityDiscoveryRequest(country="Brasil")
    assert r.niches == []
    assert r.seasonality is None


def test_seasonality_rejects_invalid():
    with pytest.raises(ValidationError):
        EntityDiscoveryRequest(country="Brasil", seasonality="quarterly")


def test_entity_spec_has_niche_slug():
    # EntitySpec só exige `canonical_name` — demais campos (inclusive niche_slug) são opcionais.
    e = EntitySpec(canonical_name="RUT", niche_slug="servicos_governo")
    assert e.niche_slug == "servicos_governo"
