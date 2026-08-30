"""
funnel_pro — idioma forçado, grounding semântico anti-branco, intro/fechamento
propagados (R3/R4/R9). Ver docs/superpowers/plans/2026-07-23-pautador-pro-nicho-idioma-funil.md
Task 7.

Cobre:
  (a) `_supporting_data` nunca colapsa para só `- {main_keyword}` quando a
      oportunidade tem base semântica (reasoning/variations/expansion_hooks),
      mesmo com cluster vazio.
  (b) `architect_pages_to_funnel_pages` e `page_factory` propagam
      `intro_section`/`closing_section` (arrays de bullets pt-BR; com default
      "" quando ausentes).
  (c) `forced_language` (novo kwarg opcional) é o que vira `lingua` no prompt
      do arquiteto — com fallback para `opportunity.native_language`.
  (d) arquiteto vazio -> retry único; se AINDA vazio, cai no fallback
      determinístico (funil nunca fica em branco) COM aviso explícito (sem
      mascarar silenciosamente).

Run:  cd backend && pytest tests/test_funnel_grounding.py -v
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
from app.agents.funnel_pro.orchestrator import FunnelProOrchestrator
from app.agents.funnel_pro.page_factory import architect_pages_to_funnel_pages, page_factory
from app.config import Settings, get_settings
from app.llm.mock import MockEngine

get_settings.cache_clear()


def _ctx(gemini_key: str | None = None) -> AgentContext:
    s = Settings(gemini_api_key=gemini_key, google_api_key=None, supabase_url=None, supabase_service_role_key=None)
    return AgentContext(settings=s, engine=MockEngine(), grounding=None)


# --- (a) grounding semântico: nunca colapsa para só o main_keyword -------------
def test_supporting_data_grounds_on_opportunity_when_cluster_is_empty():
    opportunity = {
        "main_keyword": "SOAT Colombia",
        "reasoning": "SOAT é obrigatório para veículos e gera alta busca recorrente por renovação.",
        "variations": ["seguro SOAT", "SOAT vigente", "consultar SOAT"],
        "expansion_hooks": ["RUNT", "multas por SOAT vencido"],
    }
    out = FunnelProOrchestrator._supporting_data(None, opportunity)

    assert out != f"- {opportunity['main_keyword']}"
    assert len(out.splitlines()) > 1
    assert "SOAT é obrigatório" in out
    assert "seguro SOAT" in out
    assert "RUNT" in out


def test_supporting_data_still_collapses_to_main_keyword_when_truly_empty():
    # sem cluster e sem NENHUM material semântico -> último recurso (não deve travar)
    out = FunnelProOrchestrator._supporting_data(None, {"main_keyword": "tema seco"})
    assert out == "- tema seco"


def test_user_questions_incorporates_expansion_hooks_even_with_cluster():
    cluster = {"content_seo_queue": [{"keyword": "como renovar soat"}]}
    opportunity = {"expansion_hooks": ["RUNT", "multa vencida"]}
    out = FunnelProOrchestrator._user_questions(cluster, opportunity)
    assert "como renovar soat" in out
    assert "RUNT" in out
    assert "multa vencida" in out


# --- (b) intro_section/closing_section propagados ------------------------------
def test_architect_pages_to_funnel_pages_propagates_intro_closing():
    ai_output = {
        "funnel_strategy": {"avatar_summary": "Motoristas"},
        "pages": [
            {
                "page_number": 1,
                "page_type": "LANDING PAGE",
                "h1_title": "Título",
                "slug": "pagina-1",
                "emotional_objective": "Engajar",
                "main_content_structure": ["H2: Bloco 1"],
                "hook_to_next_page": "Avançar",
                "next_page_slug": "pagina-2",
                "intro_section": ["Abrir com I1", "Provocar I2"],
                "closing_section": ["Recapitular C1", "Reforçar C2"],
            }
        ],
    }
    pages = architect_pages_to_funnel_pages(ai_output)
    assert pages[0]["intro_section"] == ["Abrir com I1", "Provocar I2"]
    assert pages[0]["closing_section"] == ["Recapitular C1", "Reforçar C2"]


def test_architect_pages_to_funnel_pages_defaults_intro_closing_when_absent():
    # compat com páginas de mock/fallback que ainda não têm os campos novos
    ai_output = {
        "funnel_strategy": {},
        "pages": [{"page_number": 1, "page_type": "LANDING PAGE", "h1_title": "T", "slug": "s"}],
    }
    pages = architect_pages_to_funnel_pages(ai_output)
    assert pages[0]["intro_section"] == ""
    assert pages[0]["closing_section"] == ""


def test_page_factory_writer_briefing_carries_intro_closing():
    ai_output = {
        "funnel_strategy": {"avatar_summary": "A", "tone_voice": "T"},
        "pages": [
            {
                "page_number": 1,
                "page_type": "LANDING PAGE",
                "h1_title": "Título",
                "slug": "pagina-1",
                "main_content_structure": ["H2: x"],
                "intro_section": ["Abrir com gancho", "Prometer esclarecer X"],
                "closing_section": ["Recapitular valor entregue"],
            }
        ],
    }
    factory = page_factory(ai_output)
    briefing = factory["writingJobs"][0]["writer_briefing"]
    assert briefing["intro_section"] == ["Abrir com gancho", "Prometer esclarecer X"]
    assert briefing["closing_section"] == ["Recapitular valor entregue"]


def test_page_factory_writer_briefing_defaults_intro_closing_when_absent():
    ai_output = {
        "funnel_strategy": {},
        "pages": [{"page_number": 1, "page_type": "LANDING PAGE", "h1_title": "T", "slug": "s"}],
    }
    briefing = page_factory(ai_output)["writingJobs"][0]["writer_briefing"]
    assert briefing["intro_section"] == ""
    assert briefing["closing_section"] == ""


# --- (c) forced_language vira `lingua` no prompt do arquiteto -------------------
def test_forced_language_overrides_native_language_in_architect_prompt(monkeypatch):
    import app.agents.funnel_pro.orchestrator as orch_mod

    captured: Dict[str, Any] = {}

    def fake_builder(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "MISSAO-FAKE"

    class _FakeClient:
        async def complete_json(self, system_prompt: str, mission: str) -> Dict[str, Any]:
            return {
                "funnel_strategy": {},
                "pages": [{"page_number": 1, "page_type": "LANDING PAGE", "h1_title": "T", "slug": "s"}],
            }

    monkeypatch.setattr(orch_mod, "build_funnel_architect_user", fake_builder)
    monkeypatch.setattr(FunnelProOrchestrator, "_gemini", lambda self: _FakeClient())

    ctx = _ctx(gemini_key="fake-key")
    orch = FunnelProOrchestrator(ctx, forced_language="es-DO")
    opportunity = {"main_keyword": "tema", "native_language": "pt-BR"}
    asyncio.run(orch.run(opportunity))

    assert captured.get("lingua") == "es-DO"


def test_forced_language_falls_back_to_opportunity_native_language_when_absent(monkeypatch):
    import app.agents.funnel_pro.orchestrator as orch_mod

    captured: Dict[str, Any] = {}

    def fake_builder(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "MISSAO-FAKE"

    class _FakeClient:
        async def complete_json(self, system_prompt: str, mission: str) -> Dict[str, Any]:
            return {
                "funnel_strategy": {},
                "pages": [{"page_number": 1, "page_type": "LANDING PAGE", "h1_title": "T", "slug": "s"}],
            }

    monkeypatch.setattr(orch_mod, "build_funnel_architect_user", fake_builder)
    monkeypatch.setattr(FunnelProOrchestrator, "_gemini", lambda self: _FakeClient())

    ctx = _ctx(gemini_key="fake-key")
    orch = FunnelProOrchestrator(ctx)  # sem forced_language -> compat com callers legados
    opportunity = {"main_keyword": "tema", "native_language": "es-CO"}
    asyncio.run(orch.run(opportunity))

    assert captured.get("lingua") == "es-CO"


# --- (d) arquiteto vazio: retry único, depois fallback COM aviso explícito -----
def test_empty_architect_retries_once_then_falls_back_with_explicit_warning():
    calls = {"n": 0}

    class _FakeEmptyClient:
        async def complete_json(self, system_prompt: str, mission: str) -> Dict[str, Any]:
            calls["n"] += 1
            return {"funnel_strategy": {}, "pages": []}

    orig_gemini = FunnelProOrchestrator._gemini
    FunnelProOrchestrator._gemini = lambda self: _FakeEmptyClient()  # type: ignore[assignment]
    try:
        ctx = _ctx(gemini_key="fake-key")
        orch = FunnelProOrchestrator(ctx)
        opportunity = {"main_keyword": "tema", "variations": ["v1"]}
        result = asyncio.run(orch.run(opportunity))
    finally:
        FunnelProOrchestrator._gemini = orig_gemini  # type: ignore[assignment]

    assert calls["n"] == 2  # 1ª tentativa + 1 retry — nunca mais que isso
    assert len(result["pages"]) > 0  # funil NUNCA fica em branco (safety net)
    assert any("vazio" in w.lower() for w in result["warnings"])  # aviso explícito
    assert "funnel_architect:fallback" in result["services_used"]


def test_no_gemini_key_still_uses_fallback_without_retry():
    """Sem chave Gemini (client is None) é o modo mock/dry legítimo — não conta
    como caso de "arquiteto vazio" e não deve gerar o aviso de grounding."""
    ctx = _ctx(gemini_key=None)
    orch = FunnelProOrchestrator(ctx)
    opportunity = {"main_keyword": "tema"}
    result = asyncio.run(orch.run(opportunity))

    assert len(result["pages"]) > 0
    assert not any("vazio" in w.lower() for w in result["warnings"])
