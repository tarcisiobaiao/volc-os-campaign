import json
from pathlib import Path

import pytest

from funnelforge.domain.models import (
    EditorialIntent, EditorialLink, FunnelPlan, Page, PageRole, RunState, StepStatus,
)
from funnelforge.pipeline import steps
from funnelforge.pipeline.pagespec import enforce_pagespec, pagespec_for
from funnelforge.pipeline.pipeline import _profit_ledger, _reachable_page_count
from funnelforge.pipeline.routing import (
    bind_official_route, build_funnel_routes, validate_funnel_graph,
)
from funnelforge.pipeline.validators.checks import run_validators
from funnelforge.prompts import render
from tests.test_routing import _settings


def plan():
    pages = []
    for n, slug, role, targets, label in (
        (1, "cursos", PageRole.LP, ["inscricao-p2", "escolher-pr"], "Guia de cursos"),
        (2, "escolher-pr", PageRole.PRESELL,
         ["requisitos-p1", "inscricao-p2"], "Escolher um curso"),
        (3, "requisitos-p1", PageRole.SOLUTION, ["inscricao-p2"], "Ver requisitos"),
        (4, "inscricao-p2", PageRole.SOLUTION, ["requisitos-p1"], "Guia de inscrição"),
    ):
        pages.append(Page(
            page_number=n, slug=slug, role=role, ordinal=max(0, n - 2),
            page_type={PageRole.LP: "LANDING PAGE", PageRole.PRESELL: "HUB",
                       PageRole.SOLUTION: "SOLUTION"}[role],
            h1_title=label,
            editorial=EditorialIntent(
                reader_question=f"Dúvida {slug}?", useful_delivery=f"Entrega {slug}",
                cta_label=label,
                links=[EditorialLink(target=t, reason=f"Consultar {t}") for t in targets]),
        ))
    return FunnelPlan(total_pages=len(pages), pages=pages)


def test_contextual_routing_preserves_relevance_not_ordinal():
    p, settings = plan(), _settings()
    build_funnel_routes(p, settings)
    assert [r.target for r in p.pages[0].routes] == ["inscricao-p2", "escolher-pr"]
    assert p.pages[-1].routes[0].target == "requisitos-p1"
    assert p.pages[0].routes[0].anchor == "Guia de inscrição"
    assert p.pages[0].routes[0].reason == "Consultar inscricao-p2"
    assert _reachable_page_count(p) == 4  # Voluntary navigation cycles are finite in BFS.
    assert not validate_funnel_graph(p, settings, research_pending=True)
    assert validate_funnel_graph(p, settings)  # No verified official exit yet.
    bind_official_route(p.pages[-1], ["https://oficial.example/cursos"],
                        role=PageRole.SOLUTION, is_terminal=True, terminal_official=True)
    assert not validate_funnel_graph(p, settings)


@pytest.mark.parametrize("target", ["inexistente-p9", "requisitos-p1", "cursos"])
def test_contextual_plan_rejects_missing_self_or_lp_target(target):
    p = plan()
    p.pages[2].editorial.links = [EditorialLink(target=target, reason="Escolher")]
    with pytest.raises(ValueError):
        build_funnel_routes(p, _settings())
    assert all(not page.routes for page in p.pages)  # Atomic validation before mutation.


def test_incomplete_contract_or_duplicate_route_never_falls_back():
    p = plan()
    p.pages[2].editorial = None
    with pytest.raises(ValueError, match="contract|link"):
        build_funnel_routes(p, _settings())
    p = plan()
    p.pages[0].editorial.links *= 2
    with pytest.raises(ValueError):
        build_funnel_routes(p, _settings())


def test_contextual_plan_is_not_cloned_or_renamed(config_files):
    from tests.test_steps_prompt_routing import _deps
    from tests.fakes import FakeLLM
    deps = _deps(config_files, FakeLLM(responses=[]))
    deps.settings.run.presell_hubs = 3
    p = plan()
    state = RunState(run_id="context", plan=p)
    before = [(x.slug, x.editorial.model_dump()) for x in p.pages]
    steps.expand_presell_hubs(state, deps)
    assert [(x.slug, x.editorial.model_dump()) for x in p.pages] == before


def test_contextual_pagespec_does_not_confuse_semantics_with_shared_words():
    p, settings = plan(), _settings()
    build_funnel_routes(p, settings)
    page = p.pages[-1]
    page.routes[0].anchor = "Quem pode participar"
    bind_official_route(page, ["https://oficial.example/cursos"], role=PageRole.SOLUTION,
                        is_terminal=True, terminal_official=True)
    spec = pagespec_for(settings, PageRole.SOLUTION, terminal=True,
                        contextual=True, page_count=len(p.pages))
    assert not enforce_pagespec(page.routes, spec, slug=page.slug,
                                h1_by_slug={x.slug: x.h1_title for x in p.pages})
    page.routes.pop()  # Official source remains mandatory.
    assert any(i.code == "target_missing" for i in enforce_pagespec(
        page.routes, spec, slug=page.slug, h1_by_slug={}))


def test_contextual_validator_selection_preserves_html_security():
    issues = run_validators(
        ["min_headings", "forward_only", "gutenberg_blocks"],
        "<script>fetch('/steal')</script>", {"contextual_editorial": True})
    assert issues
    assert not any(i.code == "min_headings" for i in issues)


def test_measurement_unknown_is_not_a_fabricated_session_metric():
    p = plan()
    build_funnel_routes(p, _settings())
    ledger = _profit_ledger(RunState(run_id="context", plan=p))
    assert ledger["reachable_pages"] == 4
    assert ledger["pv_per_session"] is None
    assert ledger["measurement_status"] == "not_collected"


def test_judge_receives_reader_contract_and_does_not_duplicate_content():
    page = plan().pages[2]
    prompt = render("judge", page_type="SOLUTION", content="UNIQUE_SENTINEL",
                    editorial=page.editorial.model_dump(), facts="Fonte local")
    assert prompt.count("UNIQUE_SENTINEL") == 1
    assert "useful_delivery" in prompt and "destination_relevance" in prompt
    assert "requisitos-p1?" in prompt
    assert "3 a 5 órgãos" not in prompt


@pytest.mark.parametrize("score", [None, 3, 8])
def test_contextual_judge_checks_scores_even_if_model_says_approved(config_files, score):
    from tests.test_steps_prompt_routing import _deps
    from tests.fakes import FakeLLM
    scores = {"compliance": 9, "cta_discipline": 9, "destination_relevance": 9}
    if score is not None:
        scores["useful_delivery"] = score
    verdict = json.dumps({"approved": True, "blocking": False, "scores": scores})
    deps = _deps(config_files, FakeLLM(responses=[verdict]))
    p = plan()
    build_funnel_routes(p, deps.settings)
    state = RunState(run_id="context", plan=p)
    steps._judge_page(state, p.pages[2], "Texto sem entrega", deps)
    assert (state.step_status["judge_p3"].status is StepStatus.FAILED) == (score != 8)


def test_pautador_factory_roles_and_engine_keep_the_editorial_graph(monkeypatch):
    repo = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(repo / "backend"))
    from app.agents.funnel_pro.page_factory import architect_pages_to_funnel_pages, page_factory
    from app.entities.funnel_roles import apply_roles_and_slugs
    from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
    raw = {"pages": [p.model_dump(mode="json") for p in plan().pages]}
    pages, jobs = apply_roles_and_slugs(
        architect_pages_to_funnel_pages(raw), page_factory(raw)["writingJobs"])
    result = plano_do_funnel_architecture({"pages": pages, "writing_jobs": jobs})
    assert all(p.editorial for p in result.pages)
    build_funnel_routes(result, _settings())
    assert [r.target for r in result.pages[0].routes] == ["inscricao-p2", "escolher-pr"]


def test_contextual_link_validation_accepts_planned_backlink_not_invented_url():
    ctx = {"contextual_editorial": True, "domain": "https://site.example",
           "resolved_internal_routes": ["https://site.example/rec/requisitos-p1"]}
    assert not run_validators(["contextual_links"],
                              '<a href="/rec/requisitos-p1/#idade">Quem pode participar</a>', ctx)
    issues = run_validators(["contextual_links"],
                            '<a href="/rec/matricula-garantida">Ver curso</a>', ctx)
    assert [i.code for i in issues] == ["unplanned_internal_link"]
