from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from funnelforge.config.perfil import aplicar_perfil
from funnelforge.domain.models import PageRole, RunState
from funnelforge.pipeline.doctrine import doctrine_context
from funnelforge.pipeline.pagespec import enforce_pagespec, pagespec_for
from funnelforge.pipeline.routing import (
    bind_official_route, build_funnel_routes, resolve_page_links, validate_funnel_graph,
)
from funnelforge.pipeline.steps import _write_ctx
from funnelforge.pipeline.taxonomy import contract_advisories
from funnelforge.pipeline.validators.checks import official_link_density
from funnelforge.prompts import render
from tests.test_routing import _plan, _settings


URL = "https://institution.example/courses"


def official_settings():
    return aplicar_perfil(_settings(), {"tema": {"terminal_exit_policy": "official"}})


def test_profile_is_opt_in_typed_and_does_not_mutate_shared_settings():
    original = _settings()
    selected = aplicar_perfil(original, {"tema": {"terminal_exit_policy": "official"}})
    assert selected.run.terminal_exit_policy == "official"
    assert original.run.terminal_exit_policy == "cross_funnel"
    assert selected.routing == original.routing
    with pytest.raises(ValidationError):
        aplicar_perfil(original, {"tema": {"terminal_exit_policy": "anything"}})


def test_official_terminal_requires_research_then_has_no_cross_funnel():
    settings, plan = official_settings(), _plan()
    build_funnel_routes(plan, settings)
    page = plan.pages[-1]
    assert page.routes == []
    assert validate_funnel_graph(plan, settings, research_pending=True) == []
    assert any(i.code == "terminal_no_exit" for i in validate_funnel_graph(plan, settings))
    spec = pagespec_for(settings, PageRole.SOLUTION, terminal=True)
    assert any(i.code == "target_missing" for i in enforce_pagespec(
        [], spec, slug=page.slug, h1_by_slug={}))
    for _ in range(2):
        bind_official_route(page, [URL], role=PageRole.SOLUTION,
                            is_terminal=True, terminal_official=True)
    assert len(page.routes) == 1
    assert page.routes[0].kind == "external_official"
    assert enforce_pagespec(page.routes, spec, slug=page.slug, h1_by_slug={}) == []
    assert validate_funnel_graph(plan, settings) == []
    assert resolve_page_links(page, settings, authorized_external=[URL])[0]["href"] == URL
    with pytest.raises(ValueError):
        resolve_page_links(page, settings, authorized_external=[])


def test_resumed_cross_funnel_is_removed_and_rejected_source_is_not_restored(tmp_path):
    plan = _plan()
    build_funnel_routes(plan, _settings())
    page = plan.pages[-1]
    assert page.routes[0].kind == "cross_funnel"
    state = RunState(run_id="official-test", plan=plan, official_links={page.page_number: []})
    deps = SimpleNamespace(settings=official_settings(), out_dir=tmp_path,
                           screenshots=None, fact_verifier=None)
    ctx = _write_ctx(state, page, deps)
    assert ctx["terminal_official"] is True
    assert page.routes == []
    assert ctx["official_links"] == []
    assert official_link_density("<p>No evidence</p>", ctx)


@pytest.mark.parametrize("html", [
    "<p>No link</p>",
    f'<img src="{URL}">',
    '<a href="https://creditoup.com.br/unrelated-credit/">Another funnel</a>',
    '<a href="https://institution.example/unverified-path">Guessed path</a>',
    '<a href="/rec/unrelated/">Relative route</a>',
])
def test_official_terminal_body_fails_closed(html):
    ctx = {"role": PageRole.SOLUTION, "is_terminal": True,
           "terminal_official": True, "official_links": [URL]}
    assert official_link_density(html, ctx)


def test_official_terminal_keeps_rich_link_density_and_legacy_exemption():
    ctx = {"role": PageRole.SOLUTION, "is_terminal": True,
           "terminal_official": True, "official_links": [URL, URL + "/faq"]}
    one = f'<p><a href="{URL}">Official catalogue</a></p>'
    assert official_link_density(one, ctx)
    assert official_link_density(one + f'<a href="{URL}/faq">FAQ</a>', ctx) == []
    ctx["terminal_official"] = False
    assert official_link_density("<p>Legacy terminal</p>", ctx) == []


def test_official_terminal_prompt_does_not_require_recirculation():
    prompt = render(
        "redator_pages", role="SOLUTION", is_terminal=True, terminal_official=True,
        headline="Guide", objective="Explain", skeleton="Steps", keywords="course",
        facts="{}", domain="https://publisher.example", author_name="Editor",
        author_credential="", cnpj="", official_links=[URL],
        routes=[{"kind": "external_official", "anchor": "Official catalogue", "href": URL}],
        **doctrine_context(),
    ).lower()
    assert "saída oficial verificada" in prompt
    assert "só recircula" not in prompt
    assert "sem canal oficial nesta página" not in prompt
    assert "os dois pro mesmo destino" not in prompt


def test_official_advisory_defers_only_until_research():
    plan, settings = _plan(), official_settings()
    build_funnel_routes(plan, settings)
    assert not contract_advisories(plan, terminal_official=True, research_pending=True)
    assert contract_advisories(plan, terminal_official=True)
    bind_official_route(plan.pages[-1], [URL], role=PageRole.SOLUTION,
                        is_terminal=True, terminal_official=True)
    assert not contract_advisories(plan, terminal_official=True)


def test_official_mode_does_not_change_mid_pages_or_allow_recirculation():
    selected, original = official_settings(), _settings()
    assert pagespec_for(selected, PageRole.SOLUTION) == pagespec_for(original, PageRole.SOLUTION)
    legacy_plan = _plan()
    build_funnel_routes(legacy_plan, original)
    page = legacy_plan.pages[-1]
    spec = pagespec_for(selected, PageRole.SOLUTION, terminal=True)
    assert enforce_pagespec(page.routes, spec, slug=page.slug, h1_by_slug={})
