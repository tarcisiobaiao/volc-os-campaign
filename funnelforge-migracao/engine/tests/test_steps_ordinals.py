from funnelforge.domain.models import FunnelPlan, Page, PageRole
from funnelforge.pipeline.steps import assign_solution_ordinals


def test_assign_ordinals_from_slug():
    plan = FunnelPlan(pages=[
        Page(page_number=1, page_type="LP", h1_title="", slug="base"),
        Page(page_number=2, page_type="HUB", h1_title="", slug="base-pr1"),
        Page(page_number=3, page_type="SOLUTION", h1_title="", slug="base-p1"),
        Page(page_number=4, page_type="SOLUTION", h1_title="", slug="base-p2"),
    ])
    assign_solution_ordinals(plan)
    by = {p.slug: p for p in plan.pages}
    assert by["base-p1"].ordinal == 1 and by["base-p2"].ordinal == 2
    assert by["base-p1"].role is PageRole.SOLUTION
    assert by["base-pr1"].role is PageRole.PRESELL
    assert by["base"].role is PageRole.LP
