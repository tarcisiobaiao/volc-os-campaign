import json
from pathlib import Path

from funnelforge.config.settings import (
    AdsConfig, AdSlotConfig, RunConfig, Secrets, Settings, SiteConfig, VignetteConfig,
)
from funnelforge.domain.models import (
    AdManifest, AdSlot, Page, PageDraft, PageRole, RunState, VignetteCap,
)
from funnelforge.pipeline import steps as st
from funnelforge.pipeline.admanifest import (
    build_ad_manifest, inject_ad_slots, slot_hint_html, vignette_meta,
)
from funnelforge.pipeline.pipeline import Deps
from funnelforge.pipeline.runner import Runner
from tests.fakes import FakeLLM


def _settings_with_ads() -> Settings:
    return Settings(
        secrets=Secrets(), run=RunConfig(),
        site=SiteConfig(domain="https://creditoup.com.br", post_type="rec"),
        steps={},
        ads=AdsConfig(vignette=VignetteConfig(), slots={"LP": [
            AdSlotConfig(slot_id="lp-hero", placement="hero",
                         sizes=["fluid", "336x280"], min_height_px=280),
            AdSlotConfig(slot_id="lp-footer", placement="footer",
                         sizes=["fluid"], min_height_px=250),
        ]}),
    )


def _deps(settings: Settings, runner: Runner) -> Deps:
    return Deps(llm=FakeLLM(responses=[]), research=None, image_gen=None,
                image_proc=None, publisher=None, loader=None,
                settings=settings, runner=runner)


def test_build_ad_manifest_lp_slots_from_config():
    m = build_ad_manifest(_settings_with_ads(), PageRole.LP)
    assert [s.slot_id for s in m.slots] == ["lp-hero", "lp-footer"]
    assert all(s.page_role is PageRole.LP for s in m.slots)
    assert m.slots[0].min_height_px == 280  # reserved height -> no CLS


def test_build_ad_manifest_missing_role_is_graceful():
    m = build_ad_manifest(_settings_with_ads(), PageRole.SOLUTION)
    assert m.slots == []  # no config slots for role -> no ads, no crash


def test_slot_hint_html_reserves_height_and_has_no_script():
    slot = AdSlot(slot_id="lp-hero", page_role=PageRole.LP, placement="hero",
                  sizes=["fluid", "336x280"], min_height_px=280)
    html = slot_hint_html(slot)
    assert 'data-ad-slot="lp-hero"' in html
    assert 'data-ad-sizes="fluid,336x280"' in html
    assert "min-height:280px" in html
    assert "<script" not in html.lower()


def test_inject_ad_slots_appends_reserved_containers():
    elementor = [{"id": "00000001", "elType": "container", "elements": []}]
    m = AdManifest(slots=[AdSlot(slot_id="lp-hero", page_role=PageRole.LP,
                                 placement="hero", min_height_px=280)])
    out = inject_ad_slots(elementor, m)
    assert out is elementor
    w = elementor[0]["elements"]
    assert len(w) == 1 and w[0]["widgetType"] == "text-editor"
    assert 'data-ad-slot="lp-hero"' in w[0]["settings"]["editor"]


def test_step_build_writes_admanifest_for_lp(tmp_path: Path):
    settings = _settings_with_ads()
    runner = Runner(llm=FakeLLM(responses=[]), max_retries=0, runs_dir=tmp_path / "runs")
    deps = _deps(settings, runner)
    page = Page(page_number=1, page_type="LANDING PAGE", h1_title="H",
                slug="saque-fgts", next_page_slug="quem-tem-direito-pr")
    state = RunState(run_id="saque-fgts-20260715-101010")
    # LP draft is STRUCTURED JSON now (fills the Elementor template).
    state.drafts[1] = PageDraft(page_number=1, page_type="LANDING PAGE",
                               format="lp_json",
                               content='{"hero_title":"H","cta_texts":["Ver o passo »"]}',
                               word_count=1)
    st.step_build(state, page, deps)
    run_dir = tmp_path / "runs" / state.run_id
    manifest = json.loads((run_dir / "p1.admanifest.json").read_text(encoding="utf-8"))
    assert [s["slot_id"] for s in manifest["slots"]] == ["lp-hero", "lp-footer"]
    # The LP is built from the designer-owned Elementor TEMPLATE -- ad slots
    # are NOT injected into it (inject_ad_slots has its own unit test above).
    assert (run_dir / "p1.elementor.json").exists()


def test_slot_hint_refresh_and_kv_only_when_eligible():
    elig = AdSlot(slot_id="sol-inline-1", page_role=PageRole.SOLUTION,
                  placement="inline", min_height_px=250,
                  refresh_eligible=True, source_key="gam-123")
    inelig = AdSlot(slot_id="sol-footer", page_role=PageRole.SOLUTION,
                    placement="footer", min_height_px=250,
                    refresh_eligible=False, source_key="")
    e = slot_hint_html(elig)
    i = slot_hint_html(inelig)
    assert 'data-ad-refresh="true"' in e
    assert 'data-ad-kv="src=gam-123"' in e
    assert "data-ad-refresh" not in i   # not eligible -> no refresh
    assert "data-ad-kv" not in i        # empty source_key -> never invented


def test_build_ad_manifest_solution_marks_refresh_eligible():
    settings = Settings(
        secrets=Secrets(), run=RunConfig(),
        site=SiteConfig(domain="https://creditoup.com.br"), steps={},
        ads=AdsConfig(slots={"SOLUTION": [
            AdSlotConfig(slot_id="sol-inline-1", placement="inline",
                         sizes=["fluid", "300x250"], min_height_px=250,
                         refresh_eligible=True),
            AdSlotConfig(slot_id="sol-footer", placement="footer",
                         sizes=["fluid"], min_height_px=250),
        ]}),
    )
    m = build_ad_manifest(settings, PageRole.SOLUTION)
    inline = next(s for s in m.slots if s.slot_id == "sol-inline-1")
    footer = next(s for s in m.slots if s.slot_id == "sol-footer")
    assert inline.refresh_eligible is True
    assert footer.refresh_eligible is False


def test_vignette_meta_declares_cap():
    meta = vignette_meta(VignetteCap(enabled=True, max_per_window=1, window_seconds=600))
    assert 'name="ff-ad-vignette"' in meta
    assert "max_per_window=1" in meta and "window_seconds=600" in meta
    assert "<script" not in meta.lower()


def test_vignette_meta_disabled():
    assert vignette_meta(VignetteCap(enabled=False)) == (
        '<meta name="ff-ad-vignette" content="enabled=false">'
    )


def test_step_build_writes_vignette_head(tmp_path):
    settings = _settings_with_ads()
    runner = Runner(llm=FakeLLM(responses=[]), max_retries=0, runs_dir=tmp_path / "runs")
    deps = _deps(settings, runner)
    page = Page(page_number=1, page_type="LANDING PAGE", h1_title="H",
                slug="saque-fgts", next_page_slug="quem-tem-direito-pr")
    state = RunState(run_id="saque-fgts-20260715-101010")
    state.drafts[1] = PageDraft(page_number=1, page_type="LANDING PAGE",
                               format="markers",
                               content="=== WIDGET: TÍTULO (H1) ===\nH\n", word_count=1)
    st.step_build(state, page, deps)
    run_dir = tmp_path / "runs" / state.run_id
    head = (run_dir / "p1.head.html").read_text(encoding="utf-8")
    assert "max_per_window=1" in head and "window_seconds=600" in head
    preview = (run_dir / "p1.preview.html").read_text(encoding="utf-8")
    assert 'name="ff-ad-vignette"' in preview
