from funnelforge.pipeline.steps import _plan_from_raw
from funnelforge.pipeline.validators.checks import funnel_schema


def test_funnel_schema_allows_richer_funnel_but_flags_truncation():
    # MORE pages than the self-declared count -> VALID (a richer 4-solution funnel)
    raw_more = {"funnel_strategy": {"total_pages": 5},
                "pages": [{"page_number": i} for i in range(6)]}
    assert funnel_schema("", {"parsed": raw_more}) == []
    # FEWER pages than planned -> truncated/incomplete extraction -> flagged
    raw_short = {"funnel_strategy": {"total_pages": 5},
                 "pages": [{"page_number": i} for i in range(3)]}
    assert "page_count_short" in {i.code for i in funnel_schema("", {"parsed": raw_short})}


def test_plan_from_raw_total_pages_mirrors_pages_array():
    raw = {"funnel_strategy": {"total_pages": 5},
           "pages": [{"page_number": i + 1, "page_type": "SOLUTION",
                      "h1_title": "h", "slug": f"tema-p{i + 1}"} for i in range(6)]}
    plan = _plan_from_raw(raw)
    assert plan.total_pages == 6 == len(plan.pages)
