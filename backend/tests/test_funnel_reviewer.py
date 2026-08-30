"""
FunnelReviewer (R7) — revisor invisível de funil, fail-open. Ver
docs/superpowers/plans/2026-07-23-pautador-pro-nicho-idioma-funil.md Task 9.

Cobre:
  (a) happy path: o revisor devolve o mesmo shape (`funnel_strategy`/`pages`/
      `changes`) que o Gemini corrigiu, preservando as chaves de página do
      arquiteto (page_factory/architect_pages_to_funnel_pages continuam
      funcionando a jusante).
  (b) fail-open em exceção: se `complete_json` lançar, `review` retorna o
      funil ORIGINAL (funnel_strategy/pages do architect_output) com
      `changes=[]`, sem propagar a exceção.
  (c) fail-open sem chave Gemini: ctx/settings sem `gemini_api_key` também
      retorna o funil original intocado.
  (d) o system prompt do revisor menciona as checagens de idioma, datas
      (ano), tom e relevância/factual.

Run:  cd backend && pytest tests/test_funnel_reviewer.py -v
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
from app.agents.funnel_pro.reviewer import REVIEWER_SYSTEM_PROMPT, FunnelReviewer
from app.config import Settings, get_settings
from app.llm.mock import MockEngine

get_settings.cache_clear()


def _ctx(gemini_key: str | None = None) -> AgentContext:
    s = Settings(gemini_api_key=gemini_key, google_api_key=None, supabase_url=None, supabase_service_role_key=None)
    return AgentContext(settings=s, engine=MockEngine(), grounding=None)


def _architect_output() -> Dict[str, Any]:
    return {
        "funnel_strategy": {"avatar_summary": "Motoristas", "tone_voice": "Direto", "total_pages": 2},
        "pages": [
            {
                "page_number": 1,
                "page_type": "LANDING PAGE",
                "h1_title": "SOAT 2024: guia completo",
                "slug": "soat-guia",
                "intro_section": "Intro em inglês (errado).",
                "emotional_objective": "Engajar",
                "main_content_structure": ["H2: O que é", "H2: Requisitos"],
                "closing_section": "Fechamento.",
                "hook_to_next_page": "Avançar",
                "next_page_slug": "soat-p2",
                "target_keywords": ["soat"],
            },
            {
                "page_number": 2,
                "page_type": "SOLUÇÃO",
                "h1_title": "Como falar com o suporte",
                "slug": "soat-contato",
                "intro_section": "Ponte.",
                "emotional_objective": "Concluir",
                "main_content_structure": ["H2: Contato"],
                "closing_section": "Fim.",
                "hook_to_next_page": "",
                "next_page_slug": "",
                "target_keywords": ["contato soat"],
            },
        ],
    }


def _entity_facts() -> Dict[str, Any]:
    return {
        "official_source": "RUNT",
        "related_systems": ["RUNT", "Fasecolda"],
        "description": "O SOAT é emitido automaticamente via cruzamento de dados no RUNT — não há cadastro manual.",
    }


# --- (a) happy path: Gemini corrige e o revisor devolve o shape corrigido ------
def test_review_happy_path_returns_corrected_shape_with_architect_keys(monkeypatch):
    corrected = {
        "funnel_strategy": {"avatar_summary": "Motoristas colombianos", "tone_voice": "Direto", "total_pages": 1},
        "pages": [
            {
                "page_number": 1,
                "page_type": "LANDING PAGE",
                "h1_title": "SOAT: guia completo",
                "slug": "soat-guia",
                "intro_section": "Intro em espanhol (correta).",
                "emotional_objective": "Engajar",
                "main_content_structure": ["H2: O que é", "H2: Requisitos", "H2: Como consultar", "H2: Erros comuns"],
                "closing_section": "Fechamento.",
                "hook_to_next_page": "",
                "next_page_slug": "",
                "target_keywords": ["soat"],
            }
        ],
        "changes": [
            "Removido ano do h1_title da P1",
            "Traduzido intro_section para es-CO",
            "Página de 'contato' fundida na P1 (rasa/desnecessária)",
            "Corrigido processo: inscrição é automática (RUNT), não manual",
        ],
    }

    class _FakeClient:
        async def complete_json(self, system: str, user: str) -> Dict[str, Any]:
            return corrected

    monkeypatch.setattr(FunnelReviewer, "_gemini", lambda self: _FakeClient())

    ctx = _ctx(gemini_key="fake-key")
    reviewer = FunnelReviewer(ctx)
    result = asyncio.run(
        reviewer.review(_architect_output(), entity_facts=_entity_facts(), forced_language="es-CO")
    )

    assert result["funnel_strategy"] == corrected["funnel_strategy"]
    assert result["pages"] == corrected["pages"]
    assert result["changes"] == corrected["changes"]
    # chaves de página do arquiteto preservadas (page_factory/architect_pages_to_funnel_pages)
    expected_keys = {
        "page_number", "page_type", "h1_title", "slug", "intro_section",
        "emotional_objective", "main_content_structure", "closing_section",
        "hook_to_next_page", "next_page_slug", "target_keywords",
    }
    for page in result["pages"]:
        assert expected_keys.issubset(page.keys())


# --- (b) fail-open em exceção ---------------------------------------------------
def test_review_fail_open_on_exception_returns_original_untouched(monkeypatch):
    class _FakeClient:
        async def complete_json(self, system: str, user: str) -> Dict[str, Any]:
            raise RuntimeError("Gemini timeout")

    monkeypatch.setattr(FunnelReviewer, "_gemini", lambda self: _FakeClient())

    ctx = _ctx(gemini_key="fake-key")
    reviewer = FunnelReviewer(ctx)
    architect_output = _architect_output()

    result = asyncio.run(
        reviewer.review(architect_output, entity_facts=_entity_facts(), forced_language="es-CO")
    )

    assert result["funnel_strategy"] == architect_output["funnel_strategy"]
    assert result["pages"] == architect_output["pages"]
    assert result["changes"] == []


# --- (c) fail-open sem chave Gemini ---------------------------------------------
def test_review_fail_open_without_gemini_key_returns_original_untouched():
    ctx = _ctx(gemini_key=None)
    reviewer = FunnelReviewer(ctx)
    architect_output = _architect_output()

    result = asyncio.run(
        reviewer.review(architect_output, entity_facts=_entity_facts(), forced_language="es-CO")
    )

    assert result["funnel_strategy"] == architect_output["funnel_strategy"]
    assert result["pages"] == architect_output["pages"]
    assert result["changes"] == []


# --- (d) unusable model output also fails open ----------------------------------
def test_review_fail_open_when_model_output_is_unusable(monkeypatch):
    class _FakeClient:
        async def complete_json(self, system: str, user: str) -> Dict[str, Any]:
            return {"nonsense": True}

    monkeypatch.setattr(FunnelReviewer, "_gemini", lambda self: _FakeClient())

    ctx = _ctx(gemini_key="fake-key")
    reviewer = FunnelReviewer(ctx)
    architect_output = _architect_output()

    result = asyncio.run(
        reviewer.review(architect_output, entity_facts=_entity_facts(), forced_language="es-CO")
    )

    assert result["funnel_strategy"] == architect_output["funnel_strategy"]
    assert result["pages"] == architect_output["pages"]
    assert result["changes"] == []


# --- (e) prompt menciona idioma, datas, tom e relevância/factual ---------------
def test_reviewer_system_prompt_mentions_required_checks():
    prompt_lower = REVIEWER_SYSTEM_PROMPT.lower()
    assert "idioma" in prompt_lower
    assert "ano" in prompt_lower or "data" in prompt_lower
    assert "tom" in prompt_lower
    assert "relevância" in prompt_lower or "relevancia" in prompt_lower
    assert "automátic" in prompt_lower or "automatic" in prompt_lower  # sinal factual/processual
