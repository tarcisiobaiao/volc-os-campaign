import json
from pathlib import Path

import pytest

from funnelforge.adapters.briefing_docx import DocxBriefingLoader
from funnelforge.config.settings import (
    AdsConfig, RoutingSpecConfig, RunConfig, Secrets, Settings, SiteConfig, load_settings,
)
from funnelforge.domain.models import (
    FunnelPlan, Page, PageDraft, PageRole, RunState, StepStatus, effective_role, resolve_route,
)
from funnelforge.pipeline.doctrine import APPROVED_CTA_EXEMPLARS
from funnelforge.pipeline.pagespec import (
    _anchor_congruent, _sig_tokens, enforce_pagespec, pagespec_for,
)
from funnelforge.pipeline.pipeline import Deps, run_pipeline
from funnelforge.pipeline.routing import (
    bind_official_route, build_funnel_routes, is_terminal_solution, reachable_slugs,
    resolve_page_links, validate_funnel_graph,
)
from funnelforge.pipeline.runner import Runner
from funnelforge.pipeline.validators.checks import run_validators
from funnelforge.pipeline import steps as st
from tests.fakes import FakeLLM
from tests.test_smoke_e2e import (
    IMAGE_PROMPT, JUDGE_JSON, P1_JSON, P1_MARKERS, RESEARCH_JSON, SEO_JSON, _page_html_for,
)


def _placement(i: int, n: int) -> str:
    if i == 0:
        return "hero"
    if i == n - 1:
        return "footer"
    return "inline"


def _anchor_for(target_h1: str, i: int) -> str:
    """Descriptive 3rd-person anchor congruent with the target H1 (shares a
    significant token so enforce_pagespec's anchor_congruent passes)."""
    base = APPROVED_CTA_EXEMPLARS[i % len(APPROVED_CTA_EXEMPLARS)]
    tok = next(iter(sorted(_sig_tokens(target_h1))), "")
    if not tok:
        return base
    return f"Ver o guia de {tok} >>>"


def _settings():
    # Honest graph (Plano A): LP -> 3 distinct pre-sells; each pre-sell fans out
    # to every solution (lead first); mid solutions advance forward-only + an
    # official link; the terminal solution recirculates cross-funnel only.
    routing = {
        "LP": RoutingSpecConfig(allowed_targets=["funnel"], required_targets=["funnel"],
            forbidden_targets=["self", "bare_rec", "external_official", "cross_funnel"],
            cta_min=3, cta_max=3, distinct_targets=True),
        "PRESELL": RoutingSpecConfig(allowed_targets=["funnel"], required_targets=["funnel"],
            forbidden_targets=["self", "bare_rec"], cta_min=2, cta_max=8, distinct_targets=True),
        "SOLUTION": RoutingSpecConfig(
            allowed_targets=["funnel", "external_official"],
            required_targets=["funnel", "external_official"],
            forbidden_targets=["self", "bare_rec", "cross_funnel"], cta_min=1, cta_max=5,
            distinct_targets=True),
        "SOLUTION_TERMINAL": RoutingSpecConfig(
            allowed_targets=["cross_funnel"], required_targets=["cross_funnel"],
            forbidden_targets=["self", "funnel", "external_official", "bare_rec"],
            cta_min=1, cta_max=1, distinct_targets=False),
    }
    # Sem allowlist de hosts: o canal oficial nao vem mais de configuracao. Quem
    # autoriza uma URL externa e a PESQUISA daquela pagina (ver URLS_DA_PESQUISA).
    site = SiteConfig(domain="https://creditoup.com.br", post_type="rec",
        cross_funnel_lps=["emprestimo-consignado"])
    return Settings(secrets=Secrets(), run=RunConfig(), site=site,
        steps={}, routing=routing, ads=AdsConfig())


# O que a pesquisa desta pagina teria devolvido e o motor verificado. E a UNICA
# fonte de URL externa autorizada -- nao existe lista por instalacao.
URLS_DA_PESQUISA = ["https://www.gov.br/fgts/saque-aniversario"]


def _ligar_canal_oficial(plan: FunnelPlan,
                         links: list[str] | None = None) -> None:
    """Reproduz o que `_write_ctx` faz por pagina: depois da pesquisa, liga a
    aresta `external_official` de cada SOLUTION nao-terminal com a URL que
    aquela pesquisa trouxe. O grafo seco (build_funnel_routes) nao tem essa
    aresta de proposito."""
    sols = [p for p in plan.pages if effective_role(p) is PageRole.SOLUTION]
    for pg in plan.pages:
        role = effective_role(pg)
        bind_official_route(pg, list(links if links is not None else URLS_DA_PESQUISA),
                            role=role,
                            is_terminal=role is PageRole.SOLUTION
                            and is_terminal_solution(pg, sols))


def _plan():
    """The target graph: 1 LP + 3 NEUTRAL presell HUBS (-pr1/2/3, rotated by
    index, no privileged lead) + 3 SOLUTION (`-p1/2/3`, ordinals 1/2/3)."""
    def p(n, t, s, o):
        return Page(page_number=n, page_type=t, h1_title=s.replace("-", " "),
                   slug=s, ordinal=o)
    return FunnelPlan(total_pages=7, pages=[
        p(1, "LANDING PAGE", "saque-fgts", 0),
        p(2, "PRESELL", "saque-fgts-pr1", 0),
        p(3, "PRESELL", "saque-fgts-pr2", 0),
        p(4, "PRESELL", "saque-fgts-pr3", 0),
        p(5, "SOLUTION", "saque-fgts-p1", 1),
        p(6, "SOLUTION", "saque-fgts-p2", 2),
        p(7, "SOLUTION", "saque-fgts-p3", 3),
    ])


def _enforce_all(plan: FunnelPlan, s: Settings) -> list:
    """Enforce pagespec on every page, selecting the terminal spec for the
    highest-ordinal SOLUTION (Task 6 `pagespec_for(..., terminal=)`)."""
    h1_by_slug = {pg.slug: pg.h1_title for pg in plan.pages}
    sols = [x for x in plan.pages if effective_role(x) is PageRole.SOLUTION]
    issues = []
    for pg in plan.pages:
        role = effective_role(pg)
        terminal = role is PageRole.SOLUTION and is_terminal_solution(pg, sols)
        spec = pagespec_for(s, role, terminal=terminal)
        issues += enforce_pagespec(pg.routes, spec, slug=pg.slug, h1_by_slug=h1_by_slug)
    return issues


# ---------------------------------------------------------------------------
# Task 7: LP -> 3 distinct pre-sells; pre-sell leads with lead_solution; mid
# solution forward-only; terminal solution cross-only.
# ---------------------------------------------------------------------------


def test_lp_routes_to_three_distinct_presells():
    plan, s = _plan(), _settings()
    build_funnel_routes(plan, s)
    lp = plan.pages[0]
    assert len(lp.routes) == 3
    targets = [r.target for r in lp.routes]
    assert set(targets) == {"saque-fgts-pr1", "saque-fgts-pr2", "saque-fgts-pr3"}
    assert len(set(targets)) == 3                 # distinct
    assert all(r.kind == "funnel" for r in lp.routes)


def test_presell_rotates_neutrally_by_prN_index_and_covers_all_solutions():
    """CARD-0009 (OVERRIDE-6): the presell fan-out order is a NEUTRAL rotation
    keyed on the `-prN` slug suffix -- offset=(N-1)%n -- NOT a privileged
    `lead_solution`. Each hub still fans out to EVERY solution (distinct
    targets, congruent anchors), but each one OPENS the choice block with a
    different solution, so no solution is privileged in the hero."""
    plan, s = _plan(), _settings()
    build_funnel_routes(plan, s)
    by = {p.slug: p for p in plan.pages}
    all_solutions = ["saque-fgts-p1", "saque-fgts-p2", "saque-fgts-p3"]
    n = len(all_solutions)
    # deterministic rotation: -prN starts at solutions[(N-1)%n], then walks the
    # ring in order.
    for pr_idx in (1, 2, 3):
        pr = f"saque-fgts-pr{pr_idx}"
        routes = by[pr].routes
        offset = (pr_idx - 1) % n
        expected_order = [all_solutions[(offset + k) % n] for k in range(n)]
        assert [r.target for r in routes] == expected_order, (pr, routes)
        assert routes[0].placement == "hero"
        assert {r.target for r in routes} == set(all_solutions)   # full fan-out
        assert len({r.target for r in routes}) == n               # distinct targets


def test_presell_hero_is_neutral_no_solution_always_first():
    """OVERRIDE-6: neutrality is independent of N -- across the 3 presells no
    single solution is ALWAYS the first (hero) button. (We assert distinctness
    of the openers, not a balanced distribution.)"""
    plan, s = _plan(), _settings()
    build_funnel_routes(plan, s)
    by = {p.slug: p for p in plan.pages}
    openers = [by[f"saque-fgts-pr{i}"].routes[0].target for i in (1, 2, 3)]
    assert len(set(openers)) > 1, openers          # no single hero solution
    # zero dependency on lead_solution_slug: the field no longer exists at all
    assert "lead_solution_slug" not in Page.model_fields


def test_mid_solution_fans_out_forward_plus_official():
    """OVERRIDE-1: a mid SOLUTION emits a forward funnel edge to EVERY
    subsequent solution (p1 -> {p2, p3}), not just ordinal+1. Still forward-only
    + acyclic; no mesh backward, no cross.

    O canal oficial NAO nasce aqui: `build_funnel_routes` roda antes da pesquisa
    e qualquer URL escolhida nesse instante seria chute de configuracao (era
    assim que um funil de entregador do iFood ganhava um botao apontando para
    gov.br). A aresta `external_official` so aparece depois, em
    `bind_official_route`, com a URL que a pesquisa daquela pagina trouxe."""
    plan, s = _plan(), _settings()
    build_funnel_routes(plan, s)
    p1 = plan.pages[4]      # saque-fgts-p1, ordinal 1
    funnel_targets = [r.target for r in p1.routes if r.kind == "funnel"]
    assert funnel_targets == ["saque-fgts-p2", "saque-fgts-p3"]   # ALL subsequent
    # estagio 1 -- grafo seco (antes da pesquisa): so arestas funnel.
    assert {r.kind for r in p1.routes} == {"funnel"}
    # every funnel edge advances (target ordinal strictly greater) -> acyclic
    by = {p.slug: p for p in plan.pages}
    for r in p1.routes:
        if r.kind == "funnel":
            assert by[r.target].ordinal > p1.ordinal

    # estagio 2 -- depois da pesquisa: a aresta oficial aparece, com a URL da
    # pesquisa, e o fan-out forward continua intacto.
    _ligar_canal_oficial(plan)
    kinds = [r.kind for r in p1.routes]
    assert "external_official" in kinds
    assert "cross_funnel" not in kinds                  # no cross in the middle
    oficiais = [r for r in p1.routes if r.kind == "external_official"]
    assert len(oficiais) == 1
    assert oficiais[0].target == URLS_DA_PESQUISA[0]
    assert [r.target for r in p1.routes if r.kind == "funnel"] == funnel_targets


def test_bind_official_route_e_idempotente_e_poupa_lp_presell_e_terminal():
    """`_write_ctx` roda duas vezes por pagina (redacao e gate final), entao
    ligar o canal oficial nao pode acumular rota. E so a SOLUTION nao-terminal
    cita canal oficial: LP/PRESELL nunca, e a terminal so recircula."""
    plan, s = _plan(), _settings()
    build_funnel_routes(plan, s)
    _ligar_canal_oficial(plan)
    _ligar_canal_oficial(plan)
    p1 = plan.pages[4]
    assert len([r for r in p1.routes if r.kind == "external_official"]) == 1
    for idx in (0, 1, 2, 3, 6):     # LP, os 3 hubs e a solucao terminal
        assert not any(r.kind == "external_official" for r in plan.pages[idx].routes)


def test_sem_pesquisa_a_solucao_fica_sem_canal_oficial_e_pagespec_reprova():
    """Fail-closed por AUSENCIA DE PROVA: se a pesquisa nao devolveu nenhuma URL
    externa, a solucao fica sem canal oficial e o pagespec acusa -- publicar uma
    solucao que manda o leitor a lugar nenhum e pior do que nao publicar."""
    plan, s = _plan(), _settings()
    build_funnel_routes(plan, s)
    _ligar_canal_oficial(plan, links=[])
    p1 = plan.pages[4]
    assert not any(r.kind == "external_official" for r in p1.routes)
    codes = {i.code for i in _enforce_all(plan, s)}
    assert "target_missing" in codes, codes


def test_terminal_solution_is_cross_funnel_only():
    plan, s = _plan(), _settings()
    build_funnel_routes(plan, s)
    p3 = plan.pages[6]      # saque-fgts-p3, ordinal 3 (max) -> terminal
    assert len(p3.routes) == 1
    assert p3.routes[0].kind == "cross_funnel"
    assert not any(r.kind in ("funnel", "external_official") for r in p3.routes)


def test_is_terminal_solution_helper():
    plan = _plan()
    sols = sorted((p for p in plan.pages if effective_role(p) is PageRole.SOLUTION),
                  key=lambda p: p.ordinal)
    by = {p.slug: p for p in sols}
    assert is_terminal_solution(by["saque-fgts-p3"], sols) is True
    assert is_terminal_solution(by["saque-fgts-p1"], sols) is False
    assert is_terminal_solution(by["saque-fgts-p2"], sols) is False
    assert is_terminal_solution(by["saque-fgts-p1"], []) is False


def test_full_graph_passes_pagespec():
    """O grafo completo e o de DEPOIS da pesquisa: `SOLUTION` exige
    `external_official` em `required_targets`, e essa aresta so existe apos
    `bind_official_route` -- que e o que o `step_write` faz antes de rodar o
    pagespec."""
    plan, s = _plan(), _settings()
    build_funnel_routes(plan, s)
    _ligar_canal_oficial(plan)
    assert _enforce_all(plan, s) == []


def test_resolve_page_links_same_domain_only():
    plan, s = _plan(), _settings()
    build_funnel_routes(plan, s)
    _ligar_canal_oficial(plan)          # sem isso a mid solution nao tem link externo
    mid_links = resolve_page_links(plan.pages[4], s,   # mid solution p1
                                   authorized_external=URLS_DA_PESQUISA)
    assert "external_official" in {ln["kind"] for ln in mid_links}
    for link in mid_links:
        # funnel -> /rec/<slug>; external_official -> a URL exata da pesquisa.
        assert link["href"].startswith("https://creditoup.com.br/rec/") \
            or link["href"] in URLS_DA_PESQUISA
    # sem o lastro da pesquisa a mesma rota nao resolve (fail-closed)
    with pytest.raises(ValueError):
        resolve_page_links(plan.pages[4], s)
    lp_links = resolve_page_links(plan.pages[0], s)
    assert {ln["href"] for ln in lp_links} == {
        "https://creditoup.com.br/rec/saque-fgts-pr1",
        "https://creditoup.com.br/rec/saque-fgts-pr2",
        "https://creditoup.com.br/rec/saque-fgts-pr3",
    }
    # terminal solution recirculates cross-funnel only
    term_links = resolve_page_links(plan.pages[6], s)
    assert {ln["kind"] for ln in term_links} == {"cross_funnel"}


def _all_button_links(elementor: list) -> set:
    """Every button href in the LP tree (buttons nest inside inner containers)."""
    out: set = set()

    def walk(n: object) -> None:
        if isinstance(n, dict):
            if n.get("widgetType") == "button":
                out.add(n["settings"]["link"]["url"])
            for c in n.get("elements", []) or []:
                walk(c)
        elif isinstance(n, list):
            for x in n:
                walk(x)

    walk(elementor)
    return out


def test_step_build_lp_hrefs_come_from_validated_routes_not_next_page_slug(tmp_path):
    """step_build's LP branch forms its button hrefs from ALL `page.routes` --
    the SAME winning graph pagespec/reachability validate -- one distinct
    pre-sell per button, not from a separately derived `next_page_slug`. Corrupt
    `next_page_slug` after routing ran to prove the built hrefs track the
    validated graph, not the field."""
    plan, s = _plan(), _settings()
    build_funnel_routes(plan, s)
    lp = plan.pages[0]
    lp.next_page_slug = "stale-slug-that-does-not-exist"

    # As rotas da LP sao todas `funnel` (a LP nunca cita canal oficial), entao
    # nao ha autorizacao externa em jogo aqui.
    expected = {
        resolve_route(r, domain=s.site.domain, post_type=s.site.post_type)
        for r in lp.routes
    }
    assert expected == {
        "https://creditoup.com.br/rec/saque-fgts-pr1",
        "https://creditoup.com.br/rec/saque-fgts-pr2",
        "https://creditoup.com.br/rec/saque-fgts-pr3",
    }

    runner = Runner(llm=FakeLLM(responses=[]), max_retries=0, runs_dir=tmp_path / "runs")
    deps = Deps(llm=FakeLLM(responses=[]), research=None, image_gen=None, image_proc=None,
                publisher=None, loader=None, settings=s, runner=runner)
    state = RunState(run_id="saque-fgts-20260715-101010")
    state.drafts[1] = PageDraft(page_number=1, page_type="LANDING PAGE", format="markers",
                               content=P1_MARKERS, word_count=1)
    st.step_build(state, lp, deps)

    run_dir = tmp_path / "runs" / state.run_id
    elementor = json.loads((run_dir / "p1.elementor.json").read_text(encoding="utf-8"))
    button_links = _all_button_links(elementor)
    # the 3 LP buttons carry the 3 DISTINCT pre-sell destinations
    assert button_links == expected
    assert "stale-slug-that-does-not-exist" not in " ".join(button_links)


def test_step_build_lp_fails_closed_when_fewer_than_3_distinct_destinations(tmp_path):
    """The honest LP must offer 3 DISTINCT pre-sell destinations. If routing
    collapsed to fewer distinct targets, step_build FAILS the page (fail-closed)
    instead of shipping a degenerate single-CTA LP."""
    plan, s = _plan(), _settings()
    build_funnel_routes(plan, s)
    lp = plan.pages[0]
    # collapse the graph to a single destination on every route
    for r in lp.routes:
        r.target = "saque-fgts-pr1"

    runner = Runner(llm=FakeLLM(responses=[]), max_retries=0, runs_dir=tmp_path / "runs")
    deps = Deps(llm=FakeLLM(responses=[]), research=None, image_gen=None, image_proc=None,
                publisher=None, loader=None, settings=s, runner=runner)
    state = RunState(run_id="saque-fgts-20260715-101010")
    state.plan = plan  # 3 pre-sells present -> the honest-funnel guard engages
    state.drafts[1] = PageDraft(page_number=1, page_type="LANDING PAGE", format="markers",
                               content=P1_MARKERS, word_count=1)
    st.step_build(state, lp, deps)

    res = state.step_status["build_p1"]
    assert res.status is StepStatus.FAILED
    assert "lp_destinos" in {i.code for i in res.issues}
    assert not (tmp_path / "runs" / state.run_id / "p1.elementor.json").exists()


def test_graph_valid_when_built():
    plan, s = _plan(), _settings()
    build_funnel_routes(plan, s)
    assert validate_funnel_graph(plan, s) == []


def test_graph_flags_terminal_without_cross_exit():
    plan, s = _plan(), _settings()
    s.site.cross_funnel_lps = []            # no exit configured
    build_funnel_routes(plan, s)
    codes = {i.code for i in validate_funnel_graph(plan, s)}
    assert "terminal_no_exit" in codes


def test_lp_reaches_all_presells_no_orphan():
    """LP now fans out to EVERY pre-sell (was: only the first one), so a
    3-pre-sell funnel has no structurally-unreachable pre-sell."""
    plan, s = _plan(), _settings()
    build_funnel_routes(plan, s)
    reached = reachable_slugs(plan)
    for pr in ("saque-fgts-pr1", "saque-fgts-pr2", "saque-fgts-pr3"):
        assert pr in reached, reached
    assert validate_funnel_graph(plan, s) == []


# ---------------------------------------------------------------------------
# Forward-only mesh removal must respect cta_max at scale (was: full-mesh cap).
# ---------------------------------------------------------------------------


def _plan_with_n_solutions(n: int) -> FunnelPlan:
    def p(num, t, s, o):
        return Page(page_number=num, page_type=t, h1_title=s.replace("-", " "),
                   slug=s, ordinal=o)
    pages = [p(1, "LANDING PAGE", "saque-fgts", 0)]
    pages += [p(2 + i, "PRESELL", f"saque-fgts-pr{i + 1}", 0) for i in range(3)]
    pages += [p(5 + i, "SOLUTION", f"saque-fgts-p{i + 1}", i + 1) for i in range(n)]
    return FunnelPlan(total_pages=len(pages), pages=pages)


def test_six_solution_funnel_passes_pagespec_no_cta_too_many():
    plan, s = _plan_with_n_solutions(6), _settings()
    build_funnel_routes(plan, s)
    codes = {i.code for i in _enforce_all(plan, s)}
    assert "cta_too_many" not in codes, codes
    assert "cta_too_few" not in codes, codes
    # fan-out forward: p1 -> {p2..p6} (5 funnel CTAs, within cta_max), the
    # terminal (p6) recirculates cross-funnel only.
    p1 = next(p for p in plan.pages if p.slug == "saque-fgts-p1")
    assert [r.target for r in p1.routes if r.kind == "funnel"] == [
        "saque-fgts-p2", "saque-fgts-p3", "saque-fgts-p4",
        "saque-fgts-p5", "saque-fgts-p6"]
    p6 = next(p for p in plan.pages if p.slug == "saque-fgts-p6")
    assert [r.kind for r in p6.routes] == ["cross_funnel"]
    assert validate_funnel_graph(plan, s) == []


def _solutions_sorted(plan: FunnelPlan) -> list[Page]:
    return sorted((p for p in plan.pages if effective_role(p) is PageRole.SOLUTION),
                  key=lambda p: p.ordinal)


def test_fan_out_all_subsequent_and_acyclic():
    """OVERRIDE-1: p_i -> {p_{i+1}..p_n} for every mid solution, and the whole
    solution band is a forward-only DAG (every funnel edge strictly advances the
    ordinal, so it can never cycle back)."""
    plan, s = _plan(), _settings()
    build_funnel_routes(plan, s)
    sols = _solutions_sorted(plan)
    by_slug = {p.slug: p for p in sols}
    # p1 -> {p2, p3}; p2 -> {p3}; p3 terminal (no funnel edge)
    p1, p2, p3 = sols
    assert [r.target for r in p1.routes if r.kind == "funnel"] == ["saque-fgts-p2", "saque-fgts-p3"]
    assert [r.target for r in p2.routes if r.kind == "funnel"] == ["saque-fgts-p3"]
    assert [r.kind for r in p3.routes] == ["cross_funnel"]
    # global acyclicity/forward-only invariant across every page
    for p in sols:
        for r in p.routes:
            if r.kind == "funnel":
                assert by_slug[r.target].ordinal > p.ordinal, (p.slug, r.target)


def test_fan_out_anchors_are_congruent_per_destination():
    """Each fan-out funnel route carries an anchor congruent to ITS OWN
    destination H1 (shares a significant token) -- proven with distinctive H1s
    so the check is meaningful, not a shared-theme accident."""
    plan = FunnelPlan(total_pages=7, pages=[
        Page(page_number=1, page_type="LANDING PAGE", h1_title="Saque FGTS",
             slug="fgts", ordinal=0),
        Page(page_number=2, page_type="PRESELL", h1_title="Hub", slug="fgts-pr1", ordinal=0),
        Page(page_number=3, page_type="PRESELL", h1_title="Hub", slug="fgts-pr2", ordinal=0),
        Page(page_number=4, page_type="PRESELL", h1_title="Hub", slug="fgts-pr3", ordinal=0),
        Page(page_number=5, page_type="SOLUTION", h1_title="Consultar o saldo pelo aplicativo",
             slug="fgts-p1", ordinal=1),
        Page(page_number=6, page_type="SOLUTION", h1_title="Saque-rescisao apos demissao",
             slug="fgts-p2", ordinal=2),
        Page(page_number=7, page_type="SOLUTION", h1_title="Saque-aniversario antecipado",
             slug="fgts-p3", ordinal=3),
    ])
    s = _settings()
    build_funnel_routes(plan, s)
    h1_by_slug = {p.slug: p.h1_title for p in plan.pages}
    p1 = plan.pages[4]
    funnel = [r for r in p1.routes if r.kind == "funnel"]
    assert [r.target for r in funnel] == ["fgts-p2", "fgts-p3"]
    for r in funnel:
        assert _anchor_congruent(r.anchor, h1_by_slug[r.target]), (r.anchor, r.target)


def test_fan_out_routes_pass_forward_only_validator_unchanged():
    """AC1 regression: the forward_only VALIDATOR (checks.py) already accepts any
    strictly-higher ordinal, so the fan-out passes it with NO change to the
    validator -- prove it green for a mid page that now has multiple funnel
    edges."""
    plan, s = _plan(), _settings()
    build_funnel_routes(plan, s)
    sols = _solutions_sorted(plan)
    order = {p.slug: p.ordinal for p in sols}
    p1 = sols[0]
    ctx = {"slug": p1.slug, "solution_order": order, "is_terminal": False,
           "parsed": {"routes": [r.model_dump() for r in p1.routes]}}
    assert run_validators(["forward_only"], "", ctx) == []


def test_canonical_three_solution_forward_chain():
    plan, s = _plan(), _settings()
    build_funnel_routes(plan, s)
    p1 = plan.pages[4]
    assert [r.target for r in p1.routes if r.kind == "funnel"] == ["saque-fgts-p2", "saque-fgts-p3"]
    p2 = plan.pages[5]
    assert [r.target for r in p2.routes if r.kind == "funnel"] == ["saque-fgts-p3"]
    assert validate_funnel_graph(plan, s) == []


# ---------------------------------------------------------------------------
# Fail-closed funnel-wide: an invalid funnel graph blocks EVERY page's build.
# ---------------------------------------------------------------------------


_ORPHAN_PLAN_JSON = json.dumps(
    {
        "funnel_strategy": {
            "avatar_summary": "Trabalhador CLT buscando antecipar o FGTS.",
            "tone_voice": "calmo, editorial, factual",
            "total_pages": 5,
        },
        "pages": [
            {
                "page_number": 1,
                "page_type": "LANDING PAGE",
                "h1_title": "Saque FGTS Aniversário: Como Funciona",
                "slug": "saque-fgts",
                "emotional_objective": "clareza e alívio prático",
                "main_content_structure": ["H2: O que é", "H2: Como funciona"],
                "hook_to_next_page": "Ver quem tem direito",
                "next_page_slug": "quem-tem-direito-pr",
                "target_keywords": ["fgts", "saque aniversario"],
            },
            {
                "page_number": 2,
                "page_type": "HUB",
                "h1_title": "Guia Completo do FGTS",
                "slug": "quem-tem-direito-pr",
                "emotional_objective": "organização e confiança",
                "main_content_structure": ["H2: Índice do guia"],
                "hook_to_next_page": "Como consultar o saldo",
                "next_page_slug": "como-consultar-saldo-p1",
                "target_keywords": ["fgts guia"],
            },
            {
                "page_number": 3,
                "page_type": "PRESELL",
                "h1_title": "Outro Guia do FGTS",
                "slug": "outro-guia-pr",
                "emotional_objective": "organização e confiança",
                "main_content_structure": ["H2: Conteúdo"],
                "hook_to_next_page": "Como consultar o saldo",
                "next_page_slug": "como-consultar-saldo-p1",
                "target_keywords": ["fgts guia 2"],
            },
            {
                "page_number": 4,
                "page_type": "SOLUTION",
                "h1_title": "Como Consultar o Saldo do FGTS",
                "slug": "como-consultar-saldo-p1",
                "emotional_objective": "orientação passo a passo",
                "main_content_structure": ["H2: Passo a passo"],
                "hook_to_next_page": "Como sacar o FGTS",
                "next_page_slug": "como-sacar-p2",
                "target_keywords": ["consultar saldo fgts"],
            },
            {
                "page_number": 5,
                "page_type": "SOLUTION",
                "h1_title": "Como Sacar o FGTS Aniversário",
                "slug": "como-sacar-p2",
                "emotional_objective": "orientação passo a passo",
                "main_content_structure": ["H2: Passo a passo"],
                "hook_to_next_page": "",
                "next_page_slug": "",
                "target_keywords": ["sacar fgts"],
            },
        ],
    },
    ensure_ascii=False,
)


def _orphan_responder(model: str, messages: list[dict]) -> str:
    content = messages[-1]["content"]
    if "BRIEFING_DE_ENTRADA" in content:
        return _ORPHAN_PLAN_JSON
    if "Pesquise e retorne SOMENTE um objeto JSON" in content:
        return RESEARCH_JSON
    if "PÁGINA DE POUSO" in content:
        return P1_JSON
    if "PÁGINA INTERNA" in content or "PÁGINA PRÉ-SELL" in content:
        return _page_html_for(content)
    if "JUIZ DE QUALIDADE" in content:
        return JUDGE_JSON
    if "YOAST SEO" in content:
        return SEO_JSON
    if "VISUAL STRATEGIST" in content:
        return IMAGE_PROMPT
    if "Corrija OBRIGATORIAMENTE" in content:
        # Validator-retry corrective prompt (the terminal SOLUTION has no
        # cross-funnel route to write, so pagespec keeps failing): return
        # interior-page HTML again so retries EXHAUST into write_pN FAILED
        # (a real LLM always answers) rather than raising an unscripted-prompt
        # error -- the page must end up cleanly BLOCKED, not page-level errored.
        return _page_html_for(content)
    raise AssertionError(f"unscripted prompt (no responder match): {content[:200]!r}")


def test_run_pipeline_blocks_every_page_when_funnel_graph_failed(
    tmp_path: Path, config_files: Path
) -> None:
    """With no cross-funnel exit configured, the terminal SOLUTION cannot
    recirculate -> `validate_funnel_graph` flags `terminal_no_exit` in
    step_extract -> the whole funnel fails closed and EVERY page's build is
    blocked (none may reach step_build, even ones otherwise fine). This is a
    2-solution plan, so `expand_presell_hubs` also fails closed (<3
    solutions) -- there is no LLM call in the mechanical expansion."""
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    settings.site.cross_funnel_lps = []          # no cross-funnel exit -> terminal_no_exit
    llm = FakeLLM(responses=_orphan_responder)
    runner = Runner(llm=llm, max_retries=settings.run.max_retries, runs_dir=tmp_path / "runs")
    deps = Deps(llm=llm, research=None, image_gen=None, image_proc=None, publisher=None,
                loader=DocxBriefingLoader(), settings=settings, runner=runner)
    briefing = tmp_path / "briefing.txt"
    briefing.write_text("Briefing com funil sem saida cross-funnel.", encoding="utf-8")

    state = run_pipeline(briefing, deps, only=None, publish=False)

    # step_extract's validate_funnel_graph call caught the missing terminal exit.
    graph_res = state.step_status.get("funnel_graph")
    assert graph_res is not None and graph_res.status == StepStatus.FAILED
    assert any(i.code == "terminal_no_exit" for i in graph_res.issues), graph_res.issues

    # fail-closed funnel-wide -- every page's build must be blocked, none of
    # them may reach step_build (even the ones whose write/judge are fine).
    assert state.plan is not None and len(state.plan.pages) == 5
    for page in state.plan.pages:
        blocked = state.step_status.get(f"blocked_p{page.page_number}")
        assert blocked is not None and blocked.status == StepStatus.FAILED, page.slug
        assert f"build_p{page.page_number}" not in state.step_status, page.slug
        assert f"publish_p{page.page_number}" not in state.step_status, page.slug

    run_dir = tmp_path / "runs" / state.run_id
    assert not list(run_dir.glob("*.elementor.json"))
    assert not list(run_dir.glob("*.gutenberg.html"))
