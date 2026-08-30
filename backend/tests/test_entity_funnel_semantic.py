"""
EntityFunnelOrchestrator — base semântica reforçada + idioma do país (R3/R9).
Ver docs/superpowers/plans/2026-07-23-pautador-pro-nicho-idioma-funil.md Task 8.

Cobre:
  (a) `forced_language` passado ao `FunnelProOrchestrator` é o locale COMPLETO
      resolvido via `resolve_country(entity.country, entity.country_code)
      ["native_language"]` (ex.: República Dominicana/DO -> "es-DO").
  (b) mesmo com POUCAS seed_queries, o `opp_like`/`cluster_like` entregues ao
      arquiteto carregam o stack semântico da descoberta: `reasoning` com a
      `description` da entidade, `expansion_hooks` com `related_systems`
      e/ou nomes das dores, e `cluster_like` com as dores (+ descrição) e as
      seed_queries — nunca material vazio/trivial.

Run:  cd backend && pytest tests/test_entity_funnel_semantic.py -v
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
from typing import Any, Dict, List, Optional

from app.agents.base import AgentContext
from app.config import Settings, get_settings
from app.entities.orchestrator import EntityFunnelOrchestrator
from app.llm.mock import MockEngine

get_settings.cache_clear()


def _ctx() -> AgentContext:
    s = Settings(gemini_api_key=None, google_api_key=None, supabase_url=None, supabase_service_role_key=None)
    return AgentContext(settings=s, engine=MockEngine(), grounding=None)


def _entity() -> Dict[str, Any]:
    return {
        "id": "ent-1",
        "run_id": "run-1",
        "canonical_name": "Cédula de Identidad",
        "full_name": "Cédula de Identidad y Electoral",
        "description": "Documento oficial dominicano exigido para votar, abrir conta bancária e assinar contratos.",
        "aliases": ["cedula", "cédula dominicana"],
        "related_systems": ["JCE", "Junta Central Electoral"],
        "official_source": "JCE",
        "country": "República Dominicana",
        "country_code": "DO",
        "language": None,
        "native_language": None,
    }


def _pains() -> List[Dict[str, Any]]:
    return [
        {
            "pain_name": "Cédula vencida",
            "pain_description": "O usuário não sabe como renovar a cédula vencida antes de uma eleição.",
            "user_goal": "Renovar a cédula rapidamente",
        },
        {
            "pain_name": "Perda do documento",
            "pain_description": "O usuário perdeu a cédula e precisa de uma 2ª via urgente.",
            "user_goal": "Emitir 2ª via",
        },
    ]


def _seed_queries() -> List[Dict[str, Any]]:
    # DE PROPÓSITO poucas — a base semântica deve vir de description/pains, não
    # depender de uma mineração de keywords robusta.
    return [{"query": "renovar cedula dominicana"}]


class _FakeArchitect:
    """Substitui o FunnelProOrchestrator real — só CAPTURA os kwargs do
    construtor e os args do `.run()`, sem chamar LLM nenhuma."""

    captured: Dict[str, Any] = {}

    def __init__(
        self,
        ctx: AgentContext,
        model_override: Optional[str] = None,
        forced_language: Optional[str] = None,
        admin_direction: Optional[str] = None,
    ):
        _FakeArchitect.captured["ctx"] = ctx
        _FakeArchitect.captured["model_override"] = model_override
        _FakeArchitect.captured["forced_language"] = forced_language
        _FakeArchitect.captured["admin_direction"] = admin_direction

    async def run(self, opportunity: Dict[str, Any], cluster: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        _FakeArchitect.captured["opportunity"] = opportunity
        _FakeArchitect.captured["cluster"] = cluster
        return {
            "funnel_strategy": {"avatar_summary": "Cidadãos dominicanos"},
            "pages": [{"page_number": 1, "page_type": "LANDING PAGE", "page_title": "P1"}],
            "writing_jobs": [],
            "services_used": ["gemini:funnel_architect"],
            "warnings": [],
        }


def test_entity_funnel_feeds_architect_full_semantic_stack_and_forced_language(monkeypatch):
    import app.agents.funnel_pro.orchestrator as architect_mod

    _FakeArchitect.captured = {}
    monkeypatch.setattr(architect_mod, "FunnelProOrchestrator", _FakeArchitect)

    ctx = _ctx()
    entity = _entity()
    pains = _pains()
    seed_queries = _seed_queries()

    result = asyncio.run(EntityFunnelOrchestrator(ctx).run(entity, pains, seed_queries))

    captured = _FakeArchitect.captured

    # (a) idioma forçado = locale COMPLETO do país (NÃO o ISO de 2 letras)
    assert captured["forced_language"] == "es-DO"

    # (b) opp_like carrega o stack semântico da descoberta
    opp_like = captured["opportunity"]
    assert entity["description"] in (opp_like.get("reasoning") or "")
    assert opp_like.get("native_language") == "es-DO"
    hooks = opp_like.get("expansion_hooks") or []
    assert "JCE" in hooks or "Junta Central Electoral" in hooks
    assert any(p["pain_name"] in hooks for p in pains)

    # (b) cluster_like carrega as dores (com descrição) e as seed_queries —
    # mesmo com poucas seed_queries, o material não é trivial.
    cluster_like = captured["cluster"]
    keywords_text = " ".join(str(k.get("keyword") or "") for k in (cluster_like.get("keywords") or []))
    assert "renovar cedula dominicana" in keywords_text

    seo_queue_text = " ".join(str(k.get("keyword") or "") for k in (cluster_like.get("content_seo_queue") or []))
    assert "Cédula vencida" in seo_queue_text
    assert "não sabe como renovar a cédula vencida" in seo_queue_text
    assert "2ª via urgente" in seo_queue_text

    # sanity: o orquestrador ainda entrega o funil normalmente (não regrediu)
    assert result["pages"]


# ---------------------------------------------------------------------------
# v7_12 — o Insights do card chega ao arquiteto como direcionamento
# ---------------------------------------------------------------------------

def test_admin_direction_chega_ao_arquiteto(monkeypatch):
    import app.agents.funnel_pro.orchestrator as architect_mod

    _FakeArchitect.captured = {}
    monkeypatch.setattr(architect_mod, "FunnelProOrchestrator", _FakeArchitect)

    texto = "Recorte para quem perdeu o prazo e precisa regularizar com multa."
    asyncio.run(
        EntityFunnelOrchestrator(_ctx()).run(
            _entity(), _pains(), _seed_queries(), admin_direction=texto
        )
    )
    assert _FakeArchitect.captured["admin_direction"] == texto


def test_sem_admin_direction_o_arquiteto_recebe_none(monkeypatch):
    """Caminho de todos os cards que existem hoje: nada muda."""
    import app.agents.funnel_pro.orchestrator as architect_mod

    _FakeArchitect.captured = {}
    monkeypatch.setattr(architect_mod, "FunnelProOrchestrator", _FakeArchitect)

    asyncio.run(EntityFunnelOrchestrator(_ctx()).run(_entity(), _pains(), _seed_queries()))
    assert _FakeArchitect.captured["admin_direction"] is None
