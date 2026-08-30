from funnelforge.domain.models import FunnelPlan, Page, PageRole, Route
from funnelforge.pipeline.taxonomy import (
    contract_advisories,
    load_contract,
)


def _sol(n: int, routes: list[Route]) -> Page:
    return Page(page_number=n + 2, page_type="SOLUTION", h1_title=f"Solucao {n}",
                slug=f"tema-p{n}", role=PageRole.SOLUTION, ordinal=n, routes=routes)


def _presell(routes: list[Route], slug: str = "tema-pr", page_number: int = 2) -> Page:
    return Page(page_number=page_number, page_type="PRESELL", h1_title="Presell", slug=slug,
                role=PageRole.PRESELL, ordinal=0, routes=routes)


def _funnel(target: str) -> Route:
    return Route(placement="body", kind="funnel", target=target)


def _cross() -> Route:
    return Route(placement="footer", kind="cross_funnel",
                 target="https://creditoup.com.br/pis-pasep-esquecido/")


def _good_plan() -> FunnelPlan:
    """Presell fans out to all 3 solutions; terminal p3 has a cross-funnel exit."""
    presell = _presell([_funnel("tema-p1"), _funnel("tema-p2"), _funnel("tema-p3")])
    p1 = _sol(1, [_funnel("tema-p2"), _funnel("tema-p3")])
    p2 = _sol(2, [_funnel("tema-p1"), _funnel("tema-p3")])
    p3 = _sol(3, [_funnel("tema-p1"), _funnel("tema-p2"), _cross()])
    return FunnelPlan(total_pages=4, pages=[presell, p1, p2, p3])


def test_good_plan_has_no_advisories():
    assert contract_advisories(_good_plan()) == []


def test_flags_presell_that_does_not_fan_out():
    presell = _presell([_funnel("tema-p1")])  # only p1 -- the routing bug
    p1 = _sol(1, [_funnel("tema-p2"), _funnel("tema-p3")])
    p2 = _sol(2, [_funnel("tema-p1"), _funnel("tema-p3")])
    p3 = _sol(3, [_funnel("tema-p1"), _funnel("tema-p2"), _cross()])
    notes = contract_advisories(FunnelPlan(total_pages=4, pages=[presell, p1, p2, p3]))
    assert any("fan-out" in n for n in notes)
    assert any("tema-p2" in n and "tema-p3" in n for n in notes)


def test_flags_any_presell_that_does_not_fan_out_not_just_first():
    """Task 13 (M1): contract_advisories must iterate ALL pre-sells, not just
    the first one -- a 2nd/3rd pre-sell that fails to fan out must also be
    flagged (the honest funnel has 3 pre-sells, each fanning out to every
    solution)."""
    p1 = _sol(1, [_funnel("tema-p2"), _funnel("tema-p3")])
    p2 = _sol(2, [_funnel("tema-p1"), _funnel("tema-p3")])
    p3 = _sol(3, [_funnel("tema-p1"), _funnel("tema-p2"), _cross()])
    pr1 = _presell([_funnel("tema-p1"), _funnel("tema-p2"), _funnel("tema-p3")],
                   slug="tema-pr1", page_number=2)
    pr2 = _presell([_funnel("tema-p2")], slug="tema-pr2", page_number=3)  # missing fan-out
    pr3 = _presell([_funnel("tema-p1"), _funnel("tema-p2"), _funnel("tema-p3")],
                   slug="tema-pr3", page_number=4)
    notes = contract_advisories(
        FunnelPlan(total_pages=6, pages=[pr1, pr2, pr3, p1, p2, p3]))
    assert any("tema-pr2" in n and "fan-out" in n for n in notes)
    assert not any("tema-pr1" in n and "fan-out" in n for n in notes)
    assert not any("tema-pr3" in n and "fan-out" in n for n in notes)


def test_flags_terminal_without_cross_funnel():
    presell = _presell([_funnel("tema-p1"), _funnel("tema-p2")])
    p1 = _sol(1, [_funnel("tema-p2")])
    p2 = _sol(2, [_funnel("tema-p1")])  # terminal, no cross_funnel exit
    notes = contract_advisories(FunnelPlan(total_pages=3, pages=[presell, p1, p2]))
    assert any("cross-funnel" in n and "tema-p2" in n for n in notes)


def test_flags_self_loop():
    p1 = _sol(1, [_funnel("tema-p1")])  # CTA to itself
    notes = contract_advisories(FunnelPlan(total_pages=1, pages=[p1]))
    assert any("self-loop" in n and "tema-p1" in n for n in notes)


def test_empty_plan_is_silent():
    assert contract_advisories(None) == []
    assert contract_advisories(FunnelPlan(total_pages=0, pages=[])) == []


def test_contract_asset_loads_and_matches_taxonomy():
    c = load_contract()
    assert c["taxonomy"]["page_type_by_slug_suffix"]["presell"].endswith("-pr")
    # the packaged contract enumerates LP + presell + 3 solutions
    roles = [p["page_type"] for p in c["pages"]]
    assert roles.count("solution") == 3
    assert "LP" in roles and "presell" in roles
