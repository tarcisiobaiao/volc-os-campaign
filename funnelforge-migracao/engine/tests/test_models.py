from funnelforge.domain.models import FunnelPlan, Page, PageRole, RunState, derive_role


def test_derive_role_numbered_presell():
    for s in ("a-pr", "a-pr1", "a-pr2", "a-pr3"):
        assert derive_role(s) is PageRole.PRESELL, s
    for s in ("a-p1", "a-p12"):
        assert derive_role(s) is PageRole.SOLUTION, s
    assert derive_role("a") is PageRole.LP


def test_page_no_longer_has_angle_or_lead_solution_fields():
    """CARD-0009 (Opção A): the angle subsystem is removed -- Page must no
    longer declare `angle`/`lead_solution_slug`. The presell is a NEUTRAL hub,
    so no page carries a per-angle bias or a privileged lead solution."""
    assert "angle" not in Page.model_fields
    assert "lead_solution_slug" not in Page.model_fields


def test_rehydrate_legacy_page_with_angle_and_lead_solution_keys_is_tolerant():
    """OVERRIDE-5: a legacy state.json carries `angle`/`lead_solution_slug` on
    its pages. Re-hydrating a Page from such a dict must NOT raise (pydantic v2
    ignores unknown keys); the removed keys simply vanish, never surface as
    attributes."""
    legacy = {"page_number": 2, "page_type": "HUB", "h1_title": "x", "slug": "a-pr1",
              "angle": "consultar cpf", "lead_solution_slug": "a-p1"}
    p = Page(**legacy)
    assert p.slug == "a-pr1"
    assert not hasattr(p, "angle")
    assert not hasattr(p, "lead_solution_slug")


def test_rehydrate_legacy_runstate_json_with_angle_keys_is_tolerant():
    """OVERRIDE-5: a whole legacy RunState.json (plan pages carrying the two
    removed keys) must re-hydrate cleanly via RunState.from_json, so a resumed
    run started before this card never crashes on the old checkpoint."""
    legacy_plan = FunnelPlan(total_pages=2, pages=[
        Page(page_number=1, page_type="LANDING PAGE", h1_title="LP", slug="a"),
        Page(page_number=2, page_type="HUB", h1_title="Hub", slug="a-pr1"),
    ])
    raw = legacy_plan.model_dump()
    # inject the legacy keys onto the presell page dict, mimicking an old dump
    raw["pages"][1]["angle"] = "consultar cpf"
    raw["pages"][1]["lead_solution_slug"] = "a-p1"
    state = RunState(run_id="a-20260720-101010", plan=FunnelPlan(**raw))
    rehydrated = RunState.from_json(state.to_json())
    assert rehydrated.plan is not None
    pr = rehydrated.plan.pages[1]
    assert pr.slug == "a-pr1"
    assert not hasattr(pr, "angle")


def test_rehydrate_complete_legacy_state_with_all_three_old_presells_is_tolerant():
    """CARD-0015 coverage: a COMPLETE legacy state.json -- not just one page --
    from a run started before CARD-0009, carrying the old -pr1/-pr2/-pr3 presell
    trio (each with `angle`/`lead_solution_slug`, the angle-biased design this
    cycle removed) alongside the 3 SOLUTION pages. The whole plan must
    re-hydrate through RunState.from_json without error, and NONE of the 3
    legacy presells may surface the removed fields afterwards."""
    legacy_plan = FunnelPlan(total_pages=7, pages=[
        Page(page_number=1, page_type="LANDING PAGE", h1_title="LP", slug="a"),
        Page(page_number=2, page_type="HUB", h1_title="Hub 1", slug="a-pr1"),
        Page(page_number=3, page_type="HUB", h1_title="Hub 2", slug="a-pr2"),
        Page(page_number=4, page_type="HUB", h1_title="Hub 3", slug="a-pr3"),
        Page(page_number=5, page_type="SOLUTION", h1_title="Passo 1", slug="a-p1", ordinal=1),
        Page(page_number=6, page_type="SOLUTION", h1_title="Passo 2", slug="a-p2", ordinal=2),
        Page(page_number=7, page_type="SOLUTION", h1_title="Passo 3", slug="a-p3", ordinal=3),
    ])
    raw = legacy_plan.model_dump()
    # every OLD -prN presell carried its own angle + a (possibly distinct)
    # privileged lead solution -- mimic a real pre-CARD-0009 dump.
    legacy_leads = {1: "a-p1", 2: "a-p2", 3: "a-p3"}
    for i, lead in legacy_leads.items():
        raw["pages"][i]["angle"] = f"angle-{lead}"
        raw["pages"][i]["lead_solution_slug"] = lead
    state = RunState(run_id="a-20260720-101010", plan=FunnelPlan(**raw))

    rehydrated = RunState.from_json(state.to_json())

    assert rehydrated.plan is not None
    presells = [p for p in rehydrated.plan.pages if p.slug in ("a-pr1", "a-pr2", "a-pr3")]
    assert [p.slug for p in presells] == ["a-pr1", "a-pr2", "a-pr3"]
    for p in presells:
        assert not hasattr(p, "angle")
        assert not hasattr(p, "lead_solution_slug")
    # the rest of the legacy plan survives the round-trip untouched
    solutions = [p for p in rehydrated.plan.pages if p.slug in ("a-p1", "a-p2", "a-p3")]
    assert [p.slug for p in solutions] == ["a-p1", "a-p2", "a-p3"]
