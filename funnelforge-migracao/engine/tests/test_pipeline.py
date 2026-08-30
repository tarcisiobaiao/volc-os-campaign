# funnel-forge/tests/test_pipeline.py
from pathlib import Path
from funnelforge.pipeline.pipeline import run_pipeline, Deps, _profit_ledger, _pv_per_session
from funnelforge.pipeline.runner import Runner
from funnelforge.config.settings import load_settings
from funnelforge.adapters.briefing_docx import DocxBriefingLoader
from funnelforge.domain.models import (
    FunnelPlan,
    Page as _Page,
    PageRole as _PageRole,
    Route as _Route,
    RunState as _RunState,
    StepResult,
    StepStatus,
)
from tests.fakes import FakeLLM

PLAN_JSON = (
    '{"funnel_strategy":{"avatar_summary":"a","tone_voice":"calmo","total_pages":1},'
    '"pages":[{"page_number":1,"page_type":"LANDING PAGE","h1_title":"Saque FGTS",'
    '"slug":"saque-fgts","emotional_objective":"o",'
    '"main_content_structure":["H2: Como funciona"],"hook_to_next_page":"ver",'
    '"next_page_slug":"quem-tem-direito","target_keywords":["fgts"]}]}'
)
P1_MARKERS = (
    "=== WIDGET: TÍTULO (H1) ===\nSaque FGTS\n---\n"
    "=== WIDGET: FAQ ===\n1. Pode? Sim.\n---\n"
    "=== WIDGET: BYLINE ===\nNome: Equipe\nCredencial: Redação\n---\n"
    "=== WIDGET: RODAPE ===\nSobre o Site. Google Adsense. Utilidade pública. "
    + "palavra " * 500
)


def test_dry_run_produces_plan_and_p1_draft(tmp_path: Path, config_files):
    # config_files fixture writes .env + config.yaml into tmp_path (see conftest)
    from tests.test_smoke_e2e import P1_JSON
    settings = load_settings(tmp_path / ".env", tmp_path / "config.yaml")
    # LP LLM call order: extract, research, write_p1, seo, image prompt (NO
    # judge -- the LP is JSON validated by validate_lp_content, not judged).
    llm = FakeLLM(responses=[PLAN_JSON, '{"resumo":"r","fontes":["https://x"]}', P1_JSON,
                             '{"seotitle":"t","metadescription":"d","keywordfocus":"fgts",'
                             '"slug":"s"}',
                             "a photo prompt"])
    runner = Runner(llm=llm, max_retries=1, runs_dir=tmp_path / "runs")
    deps = Deps(llm=llm, research=None, image_gen=None, image_proc=None, publisher=None,
                loader=DocxBriefingLoader(), settings=settings, runner=runner)
    briefing = tmp_path / "b.txt"
    briefing.write_text("Briefing FGTS Saque-Aniversário")
    state = run_pipeline(briefing, deps, only="p1", publish=False)
    assert state.plan.pages[0].slug == "saque-fgts"
    assert 1 in state.drafts and state.drafts[1].format == "lp_json"
    assert "hero_title" in state.drafts[1].content
    assert (tmp_path / "runs" / state.run_id / "state.json").exists()

    run_dir = tmp_path / "runs" / state.run_id
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "## Custos e telemetria (COGS)" in report
    assert "Páginas por sessão" in report
    snap = (run_dir / "config_snapshot.json").read_text(encoding="utf-8")
    assert "creditoup.com.br" in snap
    assert "sk-test" not in snap  # secrets excluded from snapshot
    assert (run_dir / "prompts" / "extract.txt").read_text(encoding="utf-8")


def test_malformed_extract_degrades_gracefully(tmp_path: Path, config_files):
    # extractor returns a page missing required fields -> must NOT crash the run.
    settings = load_settings(tmp_path / ".env", tmp_path / "config.yaml")
    bad_plan = (
        '{"funnel_strategy":{"avatar_summary":"a","tone_voice":"t","total_pages":1},'
        '"pages":[{"foo":"bar"}]}'
    )
    llm = FakeLLM(responses=[bad_plan])
    runner = Runner(llm=llm, max_retries=0, runs_dir=tmp_path / "runs")
    deps = Deps(llm=llm, research=None, image_gen=None, image_proc=None, publisher=None,
                loader=DocxBriefingLoader(), settings=settings, runner=runner)
    briefing = tmp_path / "b.txt"
    briefing.write_text("Briefing FGTS")

    state = run_pipeline(briefing, deps, only="p1", publish=False)  # must not raise

    assert state.step_status["extract"].status.value == "FAILED"
    assert state.plan is not None and state.plan.pages == []
    run_dir = tmp_path / "runs" / state.run_id
    assert (run_dir / "state.json").exists()
    assert (run_dir / "report.md").exists()


def test_image_crafting_failure_does_not_block_a_good_page(tmp_path: Path, config_files):
    """FIX B (smoke-run finding): `steps.image.model` pointed at an
    image-only model used to send image_prompt.jinja's chat instruction to
    it, raise, and propagate out of step_image -- the pipeline's per-page
    try/except then caught it, recorded a `page_1` failure, and skipped
    step_build entirely even though write/judge/seo had all passed. Script
    a responder that raises ONLY for the image-crafting prompt (matched by
    "VISUAL STRATEGIST", the marker `image_prompt.jinja` opens with) and
    assert the page still builds."""
    settings = load_settings(tmp_path / ".env", tmp_path / "config.yaml")

    def _responder(model: str, messages: list[dict]) -> str:
        content = messages[-1]["content"]
        if "BRIEFING_DE_ENTRADA" in content:
            return PLAN_JSON
        if "Pesquise e retorne SOMENTE" in content:
            return '{"resumo":"r","fontes":["https://x"]}'
        if "VISUAL STRATEGIST" in content:
            raise RuntimeError("OpenAIException: InternalServerError (image-only model)")
        if "PÁGINA DE POUSO" in content:
            from tests.test_smoke_e2e import P1_JSON
            return P1_JSON
        if "JUIZ DE QUALIDADE" in content:
            return (
                '{"approved":true,"blocking":false,"scores":{"single_destination":9,'
                '"proof_and_authority":8,"compliance":9,"cta_discipline":8},"feedback":[]}'
            )
        if "YOAST SEO" in content:
            return '{"seotitle":"t","metadescription":"d","keywordfocus":"fgts","slug":"s"}'
        raise AssertionError(f"unscripted prompt (no responder match): {content[:200]!r}")

    llm = FakeLLM(responses=_responder)
    runner = Runner(llm=llm, max_retries=0, runs_dir=tmp_path / "runs")
    deps = Deps(llm=llm, research=None, image_gen=None, image_proc=None, publisher=None,
                loader=DocxBriefingLoader(), settings=settings, runner=runner)
    briefing = tmp_path / "b.txt"
    briefing.write_text("Briefing FGTS Saque-Aniversário")

    state = run_pipeline(briefing, deps, only="p1", publish=False)  # must not raise

    assert "page_1" not in state.step_status, (
        "image failure must not surface as a page-level exception")
    assert state.step_status["write_p1"].status != StepStatus.FAILED
    # LP has no judge step now (JSON template path); its gate is validate_lp_content
    assert state.step_status["image_p1"].status == StepStatus.SKIPPED
    assert state.step_status["image_p1"].status != StepStatus.FAILED
    assert "build_p1" in state.step_status
    assert state.step_status["build_p1"].status == StepStatus.OK
    run_dir = tmp_path / "runs" / state.run_id
    assert (run_dir / "p1.elementor.json").exists()


def test_run_id_is_slug_timestamp_and_staging_renamed(tmp_path, config_files):
    from funnelforge.adapters.briefing_docx import DocxBriefingLoader
    from funnelforge.config.settings import load_settings
    from funnelforge.pipeline.pipeline import Deps, run_pipeline
    from funnelforge.pipeline.runner import Runner
    from tests.fakes import FakeLLM
    PLAN = ('{"funnel_strategy":{"total_pages":1},"pages":[{"page_number":1,'
            '"page_type":"LANDING PAGE","h1_title":"H","slug":"saque-fgts",'
            '"main_content_structure":["H2: a"],"next_page_slug":"quem-tem-direito",'
            '"target_keywords":["fgts"]}]}')
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    llm = FakeLLM(responses=[PLAN, '{"resumo":"r","fontes":["https://x"]}',
                             "=== WIDGET: TÍTULO (H1) ===\nH\n", '{"approved":true}',
                             '{"seotitle":"t","metadescription":"d","keywordfocus":"k","slug":"s"}',
                             "img"])
    runner = Runner(llm=llm, max_retries=1, runs_dir=tmp_path / "runs")
    deps = Deps(llm=llm, research=None, image_gen=None, image_proc=None, publisher=None,
                loader=DocxBriefingLoader(), settings=settings, runner=runner)
    b = tmp_path / "b.txt"
    b.write_text("Briefing")
    state = run_pipeline(b, deps, only="p1", timestamp="20260715-101010")
    assert state.run_id == "saque-fgts-20260715-101010"
    assert not (tmp_path / "runs" / "_pending-20260715-101010").exists()
    assert (tmp_path / "runs" / state.run_id / "state.json").exists()


def test_pv_per_session_counts_pages_reachable_via_routes_graph():
    """T2H fix: pv/session now walks the SAME `page.routes` funnel graph
    `build_funnel_routes`/`validate_funnel_graph` use (via
    `routing.reachable_slugs`), not a separate `next_page_slug` chain."""
    pages = [
        _Page(page_number=1, page_type="LANDING PAGE", h1_title="a", slug="lp",
              role=_PageRole.LP,
              routes=[_Route(placement="hero", kind="funnel", target="pr")]),
        _Page(page_number=2, page_type="PRESELL", h1_title="b", slug="pr",
              role=_PageRole.PRESELL,
              routes=[_Route(placement="hero", kind="funnel", target="p1")]),
        _Page(page_number=3, page_type="SOLUTION", h1_title="c", slug="p1",
              role=_PageRole.SOLUTION, routes=[]),
    ]
    assert _pv_per_session(FunnelPlan(pages=pages, total_pages=3)) == 3
    assert _pv_per_session(None) == 0


def test_pv_per_session_is_cycle_safe():
    pages = [
        _Page(page_number=1, page_type="LANDING PAGE", h1_title="a", slug="lp",
              role=_PageRole.LP,
              routes=[_Route(placement="hero", kind="funnel", target="pr")]),
        _Page(page_number=2, page_type="PRESELL", h1_title="b", slug="pr",
              role=_PageRole.PRESELL,
              routes=[_Route(placement="hero", kind="funnel", target="lp")]),  # loops back
    ]
    assert _pv_per_session(FunnelPlan(pages=pages, total_pages=2)) == 2


def test_pv_per_session_ignores_stale_next_page_slug_and_counts_full_routes_graph():
    """Regression for the bug this fix closes: a page whose `next_page_slug`
    is stale/empty (e.g. left over from a plan edit, or a SOLUTION page that
    fans out to several siblings instead of a single forward hop) must still
    be counted correctly, because pv/session is derived from `page.routes`,
    never from `next_page_slug`."""
    pages = [
        _Page(page_number=1, page_type="LANDING PAGE", h1_title="a", slug="lp",
              role=_PageRole.LP, next_page_slug="this-slug-does-not-exist",
              routes=[_Route(placement="hero", kind="funnel", target="pr")]),
        _Page(page_number=2, page_type="PRESELL", h1_title="b", slug="pr",
              role=_PageRole.PRESELL, next_page_slug="",
              routes=[_Route(placement="hero", kind="funnel", target="s1"),
                      _Route(placement="hero", kind="funnel", target="s2")]),
        _Page(page_number=3, page_type="SOLUTION", h1_title="c", slug="s1",
              role=_PageRole.SOLUTION, routes=[]),
        _Page(page_number=4, page_type="SOLUTION", h1_title="d", slug="s2",
              role=_PageRole.SOLUTION, routes=[]),
    ]
    assert _pv_per_session(FunnelPlan(pages=pages, total_pages=4)) == 4


def test_multi_page_prompt_snapshots_are_distinct_per_page(tmp_path: Path, config_files):
    """Regression (T2C review fix): `run_llm_step` used to be called with the
    bare step-TYPE name ("write_page"/"judge"/"seo"/"research") for every
    non-LP page. Since `Runner.snapshot_prompt` writes to
    `runs/<run_id>/prompts/<name>.txt`, every page's rendered prompt for a
    given step type overwrote the previous page's file -- for any funnel
    with >1 non-LP page, only the LAST page's prompt survived on disk,
    defeating the reproducible-A/B goal. The `name` passed to `run_llm_step`
    must be page-qualified (e.g. `f"judge_p{page.page_number}"`), matching
    the page-qualified key already used for `state.step_status`. This runs
    the smoke-test's funnel (LP + 3x PRESELL + 3x SOLUTION, since Task 5
    wires `step_synthesize_angles` -- see test_smoke_e2e.py) end to end and
    asserts the per-page snapshot files for research/write/judge/seo all
    exist for >=2 non-LP pages with genuinely different content. The funnel is
    LP + 3x PRESELL + 3x SOLUTION because `expand_presell_hubs` mechanically
    expands the single mapped presell into 3 neutral hubs (see test_smoke_e2e).
    """
    from tests.test_smoke_e2e import _responder

    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    llm = FakeLLM(responses=_responder)
    runner = Runner(llm=llm, max_retries=settings.run.max_retries, runs_dir=tmp_path / "runs")
    deps = Deps(llm=llm, research=None, image_gen=None, image_proc=None, publisher=None,
                loader=DocxBriefingLoader(), settings=settings, runner=runner)
    briefing = tmp_path / "briefing.txt"
    briefing.write_text("Briefing completo do funil FGTS Saque-Aniversário.", encoding="utf-8")

    state = run_pipeline(briefing, deps, only=None, publish=False)
    assert len(state.plan.pages) == 5  # LP + 1x PRESELL + 3x SOLUTION (hub único)

    prompts_dir = tmp_path / "runs" / state.run_id / "prompts"

    for step in ("research", "write", "judge", "seo"):
        p2 = (prompts_dir / f"{step}_p2.txt").read_text(encoding="utf-8")
        p3 = (prompts_dir / f"{step}_p3.txt").read_text(encoding="utf-8")
        assert p2 != p3, f"{step}_p2.txt and {step}_p3.txt are identical -- overwrite bug"

    # the old bare, non-page-qualified snapshot files must no longer be written
    for bare in ("research.txt", "write_page.txt", "judge.txt", "seo.txt"):
        assert not (prompts_dir / bare).exists(), f"unqualified snapshot {bare} still written"


def test_profit_ledger_sums_cost_and_tokens():
    state = _RunState(run_id="x")
    state.step_status["write_p1"] = StepResult(
        step="write_p1", status=StepStatus.OK, prompt_tokens=100,
        completion_tokens=200, cost_usd=0.05, latency_ms=1200)
    state.step_status["judge_p1"] = StepResult(
        step="judge_p1", status=StepStatus.OK, prompt_tokens=50,
        completion_tokens=10, cost_usd=0.01, latency_ms=300)
    led = _profit_ledger(state)
    assert led["cost_usd"] == 0.06
    assert led["prompt_tokens"] == 150 and led["completion_tokens"] == 210
    assert len(led["per_step"]) == 2
