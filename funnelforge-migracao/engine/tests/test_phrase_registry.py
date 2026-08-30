# funnel-forge/tests/test_phrase_registry.py
"""CARD-0007 wiring tests: steps._write_ctx injects prior PRESELL opening
lines + threshold from the phrase_registry, and step_publish records the
opening line only after a successful publish (with fakes, no network)."""
from types import SimpleNamespace

import pytest

from funnelforge.config.settings import load_settings
from funnelforge.domain.models import Page, PageDraft, RunState
from funnelforge.pipeline import phrase_registry
from funnelforge.pipeline.steps import _phrase_registry_path, _write_ctx, step_publish


def _deps(tmp_path, config_files, publisher=None):
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    runner = SimpleNamespace(runs_dir=tmp_path / "runs")
    return SimpleNamespace(settings=settings, runner=runner, publisher=publisher)


# ---------------------------------------------------------------------------
# (d) _write_ctx injects prior_opening_lines / opening_line_threshold
# ---------------------------------------------------------------------------


def test_write_ctx_injects_prior_opening_lines_and_threshold(tmp_path, config_files):
    deps = _deps(tmp_path, config_files)
    phrase_registry.record(
        _phrase_registry_path(deps), "presell_opening",
        "Toque na opção certa e aprenda como consultar o saldo do FGTS",
        "outro-funil-pr", "run-antigo")

    state = RunState(run_id="run-novo")
    page = Page(page_number=2, page_type="PRESELL", h1_title="T", slug="tema-pr")
    ctx = _write_ctx(state, page, deps)

    assert ctx["prior_opening_lines"] == [
        "Toque na opção certa e aprenda como consultar o saldo do FGTS"]
    assert ctx["opening_line_threshold"] == 0.6


def test_write_ctx_prior_opening_lines_empty_when_registry_absent(tmp_path, config_files):
    """First-ever run: no registry file exists yet -> empty list, never fatal
    (AC4: registry absent must behave identically to today)."""
    deps = _deps(tmp_path, config_files)
    state = RunState(run_id="run-1")
    page = Page(page_number=2, page_type="PRESELL", h1_title="T", slug="tema-pr")
    ctx = _write_ctx(state, page, deps)
    assert ctx["prior_opening_lines"] == []
    assert not _phrase_registry_path(deps).exists()


def test_write_ctx_tolerates_corrupted_registry(tmp_path, config_files):
    deps = _deps(tmp_path, config_files)
    path = _phrase_registry_path(deps)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")

    state = RunState(run_id="run-1")
    page = Page(page_number=2, page_type="PRESELL", h1_title="T", slug="tema-pr")
    ctx = _write_ctx(state, page, deps)  # must not raise

    assert ctx["prior_opening_lines"] == []


def test_write_ctx_tolerates_deps_without_runner(config_files, tmp_path):
    """Belt-and-suspenders: even if the registry lookup itself blows up (e.g.
    a minimal/fake deps missing `.runner`), _write_ctx must still return a
    usable ctx instead of raising."""
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    deps = SimpleNamespace(settings=settings)  # no .runner at all
    state = RunState(run_id="run-1")
    page = Page(page_number=2, page_type="PRESELL", h1_title="T", slug="tema-pr")

    ctx = _write_ctx(state, page, deps)  # must not raise

    assert ctx["prior_opening_lines"] == []
    assert ctx["opening_line_threshold"] == 0.6


# ---------------------------------------------------------------------------
# (e) step_publish records the PRESELL opening line, best-effort, only after
# a successful publish.
# ---------------------------------------------------------------------------


class _FakePublisher:
    def __init__(self):
        self.post_call = None

    def create_post(self, title, content, slug, status, post_type, featured_media=None):
        self.post_call = {"content": content, "status": status}
        return {"id": 5}

    def set_yoast(self, post_id, post_type, fields, status=None):
        return {}

    def set_status(self, post_id, post_type, status):
        return {}


class _BoomPublisher:
    def create_post(self, *args, **kwargs):
        raise RuntimeError("WP 500")


_OPENING_CONTENT = (
    '<!-- wp:paragraph --><p><strong>Toque na opção certa e aprenda como '
    'consultar o saldo do FGTS ✅</strong></p><!-- /wp:paragraph -->'
    '<!-- wp:heading --><h2>Como funciona</h2><!-- /wp:heading -->'
)


def test_step_publish_records_presell_opening_line_after_success(tmp_path, config_files):
    deps = _deps(tmp_path, config_files, publisher=_FakePublisher())
    state = RunState(run_id="run-1")
    state.drafts[2] = PageDraft(page_number=2, page_type="PRESELL",
                                format="gutenberg", content=_OPENING_CONTENT)
    page = Page(page_number=2, page_type="PRESELL", h1_title="T", slug="tema-pr")

    step_publish(state, page, deps)

    lines = phrase_registry.load_lines(_phrase_registry_path(deps), "presell_opening")
    assert lines == ["Toque na opção certa e aprenda como consultar o saldo do FGTS ✅"]


def test_step_publish_does_not_record_when_publish_fails(tmp_path, config_files):
    deps = _deps(tmp_path, config_files, publisher=_BoomPublisher())
    state = RunState(run_id="run-1")
    state.drafts[2] = PageDraft(page_number=2, page_type="PRESELL",
                                format="gutenberg", content=_OPENING_CONTENT)
    page = Page(page_number=2, page_type="PRESELL", h1_title="T", slug="tema-pr")

    with pytest.raises(RuntimeError):
        step_publish(state, page, deps)

    assert not _phrase_registry_path(deps).exists()


def test_step_publish_does_not_record_for_non_presell_role(tmp_path, config_files):
    deps = _deps(tmp_path, config_files, publisher=_FakePublisher())
    state = RunState(run_id="run-1")
    state.drafts[3] = PageDraft(page_number=3, page_type="SOLUTION",
                                format="gutenberg", content=_OPENING_CONTENT)
    page = Page(page_number=3, page_type="SOLUTION", h1_title="T", slug="tema-p1")

    step_publish(state, page, deps)

    assert phrase_registry.load_lines(_phrase_registry_path(deps), "presell_opening") == []


def test_step_publish_registry_write_failure_never_fails_publish(
        tmp_path, config_files, monkeypatch):
    """Best-effort: if recording itself raises, publish must still succeed."""
    import funnelforge.pipeline.steps as steps_mod

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(steps_mod, "record_phrase", _boom)
    deps = _deps(tmp_path, config_files, publisher=_FakePublisher())
    state = RunState(run_id="run-1")
    state.drafts[2] = PageDraft(page_number=2, page_type="PRESELL",
                                format="gutenberg", content=_OPENING_CONTENT)
    page = Page(page_number=2, page_type="PRESELL", h1_title="T", slug="tema-pr")

    step_publish(state, page, deps)  # must not raise

    assert deps.publisher.post_call is not None
    assert "publish_p2" in state.step_status
