"""
Descoberta com foco de nicho + filtro sazonal + idioma forçado (R1/R2/R3).
Cobre o descarte no `EntityDiscoveryOrchestrator.run` (engine mock — sem chave Gemini
no ambiente de teste): (a) niches restringe por niche_slug/vertical; (b) seasonality
restringe por temporal_window; (c) forced_language é resolvido do país e passado ao
mission builder; (d) sem filtros, nada é descartado (backward-compat).

Run:  cd backend && pytest tests/test_discovery_filter.py -v
"""
from __future__ import annotations

import os
import sys

# offline/mock ANTES de importar o app (padrão dos demais testes do projeto)
for _k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "PERPLEXITY_API_KEY", "PAUTADOR_API_KEY"):
    os.environ[_k] = ""
os.environ["PAUTADOR_ENGINE"] = "mock"
os.environ["PAUTADOR_KW_ENGINE"] = "mock"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from typing import Any, Dict

from app.agents.base import AgentContext
from app.config import Settings, get_settings
from app.entities.mock import mock_entity_discovery
import app.entities.orchestrator as orch_mod
from app.entities.orchestrator import EntityDiscoveryOrchestrator
from app.llm.mock import MockEngine

get_settings.cache_clear()


def _ctx() -> AgentContext:
    s = Settings(gemini_api_key=None, google_api_key=None, supabase_url=None, supabase_service_role_key=None)
    return AgentContext(settings=s, engine=MockEngine(), grounding=None)


# --- (a) filtro por nicho ------------------------------------------------------
def test_niche_filter_discards_entities_outside_selected_niche():
    disc = asyncio.run(
        EntityDiscoveryOrchestrator(_ctx()).run("Brasil", "BR", "pt-BR", 12, niches=["financas"])
    )
    entities = disc["entities"]
    assert 0 < len(entities) < 12  # algo foi descartado, mas não tudo
    # tudo que sobrou pertence ao(s) vertical(is) permitido(s) do nicho "financas"
    for item in entities:
        assert item["entity"]["vertical"] in {"financas", "credito", "seguros"}
    assert any("descartad" in w and "nicho" in w for w in disc["warnings"])


# --- (b) filtro por sazonalidade ------------------------------------------------
def test_seasonality_evergreen_discards_non_perene():
    disc = asyncio.run(
        EntityDiscoveryOrchestrator(_ctx()).run("Brasil", "BR", "pt-BR", 12, seasonality="evergreen")
    )
    entities = disc["entities"]
    assert 0 < len(entities) < 12
    for item in entities:
        assert item["opportunity"]["temporal_window"] == "Perene"
    assert any("descartad" in w and "sazonalidade" in w for w in disc["warnings"])


# --- (c) idioma forçado resolvido do país e passado ao mission builder ----------
def test_forced_language_resolved_and_passed_to_mission_builder(monkeypatch):
    captured: Dict[str, Any] = {}

    def fake_mission(*args: Any, **kwargs: Any) -> str:
        captured.update(kwargs)
        return "MISSAO-FAKE"

    class _FakeClient:
        model = "fake-gemini"

        async def complete_json(self, system_prompt: str, mission: str) -> Dict[str, Any]:
            return mock_entity_discovery("República Dominicana", "DO", None, 3)

    monkeypatch.setattr(orch_mod, "build_entity_discovery_mission", fake_mission)
    monkeypatch.setattr(orch_mod, "_gemini", lambda settings, model=None: _FakeClient())

    disc = asyncio.run(
        EntityDiscoveryOrchestrator(_ctx()).run("República Dominicana", "DO", None, 3)
    )
    assert disc["engine"] == "gemini"
    assert captured.get("forced_language") == "es-DO"


# --- (d) sem niches/seasonality -> nada é descartado (backward-compat) ---------
def test_no_filters_discards_nothing():
    disc = asyncio.run(
        EntityDiscoveryOrchestrator(_ctx()).run("Colômbia", "CO", "es-CO", 5)
    )
    assert len(disc["entities"]) == 5
    assert not any("descartad" in w for w in disc["warnings"])
