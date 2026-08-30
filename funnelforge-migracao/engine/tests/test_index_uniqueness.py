from funnelforge.adapters.elementor import build_elementor
from funnelforge.domain.models import FunnelPlan, Page
from funnelforge.pipeline.steps import dedupe_slugs

MARK = "=== WIDGET: TÍTULO (H1) ===\nOi\n"


def test_dedupe_slugs_decollides():
    plan = FunnelPlan(pages=[
        Page(page_number=1, page_type="LANDING PAGE", h1_title="a", slug="guia"),
        Page(page_number=2, page_type="HUB", h1_title="b", slug="guia")])
    dedupe_slugs(plan)
    assert [p.slug for p in plan.pages] == ["guia", "guia-2"]


def test_elementor_ids_run_scoped_but_deterministic():
    a = build_elementor(
        MARK, href="https://creditoup.com.br/rec/x", image_url=None, id_seed="runA")
    b = build_elementor(
        MARK, href="https://creditoup.com.br/rec/x", image_url=None, id_seed="runB")
    a2 = build_elementor(
        MARK, href="https://creditoup.com.br/rec/x", image_url=None, id_seed="runA")
    assert a[0]["id"] != b[0]["id"]
    assert a[0]["id"] == a2[0]["id"]
    default = build_elementor(MARK, href="https://creditoup.com.br/rec/x", image_url=None)
    assert default[0]["id"] == "00000001"


def test_index_decision_noindex_and_self_canonical(config_files):
    from funnelforge.config.settings import load_settings
    from funnelforge.pipeline.steps import index_decision_for
    s = load_settings(config_files / ".env", config_files / "config.yaml")
    page = Page(page_number=1, page_type="LANDING PAGE", h1_title="t", slug="saque-fgts")
    d = index_decision_for(s, page)
    assert d.robots == "noindex,follow"
    assert d.canonical == "https://creditoup.com.br/rec/saque-fgts"
