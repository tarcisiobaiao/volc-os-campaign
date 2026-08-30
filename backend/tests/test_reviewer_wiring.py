"""
Task 10 — Wiring do revisor (R7) entre o Arquiteto e `apply_roles_and_slugs`.
Ver docs/superpowers/plans/2026-07-23-pautador-pro-nicho-idioma-funil.md Task 10.

Cobre:
  (a) Ordem: architect -> reviewer -> apply_roles_and_slugs. As páginas que
      chegam em `apply_roles_and_slugs` já são as REVISADAS (não as brutas do
      arquiteto) — e as páginas canônicas + writing_jobs da resposta final
      também refletem a saída revisada (regeneradas via page_factory /
      architect_pages_to_funnel_pages).
  (b) Fail-open: se `FunnelReviewer.review` lançar, `EntityFunnelOrchestrator.run`
      completa mesmo assim (sem 500) e entrega o funil ORIGINAL do arquiteto.
  (c) Invisibilidade: `changes` do revisor nunca aparece na resposta (só logs).

Run:  cd backend && pytest tests/test_reviewer_wiring.py -v
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
from typing import Any, Dict, List

import app.entities.funnel_roles as funnel_roles_mod
from app.agents.base import AgentContext
from app.agents.funnel_pro.reviewer import FunnelReviewer
from app.config import Settings, get_settings
from app.entities.orchestrator import EntityFunnelOrchestrator
from app.llm.mock import MockEngine

get_settings.cache_clear()


def _ctx() -> AgentContext:
    # sem chave Gemini -> arquiteto usa o fallback determinístico (offline),
    # e o revisor (sem chave) também cairia no fail-open — mas nos testes
    # abaixo o `FunnelReviewer.review` é monkeypatchado diretamente, então o
    # que importa aqui é isolar a rede: nunca chamar LLM de verdade.
    s = Settings(gemini_api_key=None, google_api_key=None, supabase_url=None, supabase_service_role_key=None)
    return AgentContext(settings=s, engine=MockEngine(), grounding=None)


def _entity() -> Dict[str, Any]:
    return {
        "id": "ent-1",
        "run_id": "run-1",
        "canonical_name": "RUT",
        "full_name": "Registro Único Tributario",
        "description": "Documento fiscal colombiano exigido para diversos trâmites.",
        "aliases": ["rut dian"],
        "related_systems": ["DIAN"],
        "official_source": "DIAN",
        "country": "Colômbia",
        "country_code": "CO",
        "language": None,
        "native_language": None,
    }


def _pains() -> List[Dict[str, Any]]:
    return [
        {"pain_name": "RUT vencido", "pain_description": "Usuário não sabe como renovar.", "user_goal": "Renovar o RUT"},
    ]


def _seed_queries() -> List[Dict[str, Any]]:
    return [{"query": "actualizar rut dian"}]


def _mark_pages_as_reviewed(raw_output: Dict[str, Any]) -> Dict[str, Any]:
    """Simula o revisor: mesmo shape architect (funnel_strategy + pages), mas
    com `h1_title == 'REVIEWED'` em todas as páginas (marca detectável depois
    do pipeline pages->canonical: `h1_title` vira `page_title`)."""
    marked_pages = []
    for p in raw_output.get("pages") or []:
        marked = dict(p)
        marked["h1_title"] = "REVIEWED"
        marked_pages.append(marked)
    return {
        "funnel_strategy": raw_output.get("funnel_strategy") or {},
        "pages": marked_pages,
        "changes": ["marcado para teste (h1_title -> REVIEWED)"],
    }


def test_reviewer_runs_before_apply_roles_and_slugs(monkeypatch):
    """architect -> reviewer -> roles/slugs: `apply_roles_and_slugs` deve
    receber as páginas JÁ REVISADAS, e a resposta final (pages/writing_jobs)
    deve estar em sincronia com a saída revisada (regenerada), não com a
    saída bruta do arquiteto."""
    captured: Dict[str, Any] = {}

    async def _fake_review(self, architect_output, *, entity_facts, forced_language):
        return _mark_pages_as_reviewed(architect_output)

    monkeypatch.setattr(FunnelReviewer, "review", _fake_review)

    real_apply = funnel_roles_mod.apply_roles_and_slugs

    def _capturing_apply(pages, writing_jobs):
        # snapshot ANTES de apply_roles_and_slugs mutar as páginas in-place
        captured["pages"] = [dict(p) for p in pages]
        captured["writing_jobs"] = [dict(j) for j in writing_jobs]
        return real_apply(pages, writing_jobs)

    monkeypatch.setattr(funnel_roles_mod, "apply_roles_and_slugs", _capturing_apply)

    ctx = _ctx()
    result = asyncio.run(EntityFunnelOrchestrator(ctx).run(_entity(), _pains(), _seed_queries()))

    # apply_roles_and_slugs recebeu as páginas JÁ revisadas (não as brutas)
    assert captured.get("pages"), "apply_roles_and_slugs deveria ter recebido páginas"
    assert all(p.get("page_title") == "REVIEWED" for p in captured["pages"])

    # a resposta final também reflete o funil revisado (canonical pages e
    # writing_jobs regenerados a partir da saída do revisor)
    assert result["pages"] and all(p.get("page_title") == "REVIEWED" for p in result["pages"])
    assert result["writing_jobs"]
    assert all(
        (wj.get("writer_briefing") or {}).get("headline") == "REVIEWED"
        for wj in result["writing_jobs"]
    )

    # invisibilidade: `changes` do revisor NUNCA aparece na resposta (só logs)
    assert "changes" not in result


def test_reviewer_output_pages_are_resequenced_before_apply_roles_and_slugs(monkeypatch):
    """FIX 2 (R8 bug): o revisor pode fundir/derrubar páginas, deixando
    `page_number` não-contíguo (ex.: 1,3,5 numa saída com 3 páginas restantes).
    `apply_roles_and_slugs`/`architect_pages_to_funnel_pages` atribuem
    papel/posição a partir de `page_number` -> sem renumerar, um gap mislabela
    o funil (ex.: Pre-sell "some"). O orchestrator deve renumerar 1..N, na
    ORDEM atual das páginas, antes de regenerar pages/writing_jobs."""
    async def _fake_review_with_gaps(self, architect_output, *, entity_facts, forced_language):
        src = architect_output.get("pages") or []
        # simula R8: derruba as páginas 2 e 4 (índices 1 e 3), preservando a
        # ORDEM relativa das 3 que sobraram, com page_number não-contíguo.
        kept = [dict(src[i]) for i in (0, 2, 4)]
        for p, n in zip(kept, (1, 3, 5)):
            p["page_number"] = n
        return {
            "funnel_strategy": architect_output.get("funnel_strategy") or {},
            "pages": kept,
            "changes": ["merge simulado (R8)"],
        }

    monkeypatch.setattr(FunnelReviewer, "review", _fake_review_with_gaps)

    real_apply = funnel_roles_mod.apply_roles_and_slugs
    captured: Dict[str, Any] = {}

    def _capturing_apply(pages, writing_jobs):
        captured["pages"] = [dict(p) for p in pages]
        return real_apply(pages, writing_jobs)

    monkeypatch.setattr(funnel_roles_mod, "apply_roles_and_slugs", _capturing_apply)

    ctx = _ctx()
    result = asyncio.run(EntityFunnelOrchestrator(ctx).run(_entity(), _pains(), _seed_queries()))

    # apply_roles_and_slugs recebeu as páginas com `position` RENUMERADA 1..N,
    # na mesma ordem relativa das páginas revisadas (1,3,5 -> 1,2,3), não
    # ordenadas/filtradas por outro critério.
    positions = [p.get("position") for p in captured["pages"]]
    assert positions == [1, 2, 3]
    titles = [p.get("page_title") for p in captured["pages"]]
    assert titles == ["RUT — página 1", "RUT — página 3", "RUT — página 5"]

    # papéis corretos na resposta final: sem o fix, a posição 3 (gap) vira
    # Pre-sell ausente / rótulo de solução errado.
    roles = [p.get("role") for p in result["pages"]]
    assert roles == ["landing", "presell", "solution"]
    role_labels = [p.get("role_label") for p in result["pages"]]
    assert role_labels == ["Landing Page (Pouso)", "Pre-sell", "Página Solução 1"]


def test_reviewer_failure_is_fail_open(monkeypatch):
    """Se `FunnelReviewer.review` lançar, o fluxo deve completar (sem exceção
    propagada) entregando o funil ORIGINAL do arquiteto."""
    async def _raising_review(self, architect_output, *, entity_facts, forced_language):
        raise RuntimeError("boom: revisor quebrado de propósito")

    monkeypatch.setattr(FunnelReviewer, "review", _raising_review)

    ctx = _ctx()
    # não deve levantar exceção (fail-open) — se levantar, o teste falha aqui
    result = asyncio.run(EntityFunnelOrchestrator(ctx).run(_entity(), _pains(), _seed_queries()))

    assert result["pages"], "o funil original do arquiteto deve ser entregue mesmo com o revisor falhando"
    assert all(p.get("page_title") != "REVIEWED" for p in result["pages"])
    assert "changes" not in result
