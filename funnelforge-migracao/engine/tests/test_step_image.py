# funnel-forge/tests/test_step_image.py
"""FIX (final review, carried finding (j)): `step_image` must not spend a
real gpt-image call generating a hero image that will never be used.
`build_elementor` only emits the image widget when `hero=True`
(`run.hero_image` in config) -- see adapters/elementor.py -- so generating
+ converting an image while `hero_image` is False is pure wasted COGS on a
real run. The creative-prompt LLM call still runs either way (dry runs must
still exercise that step)."""
from pathlib import Path

from funnelforge.config.settings import RunConfig, Secrets, Settings, SiteConfig, StepConfig
from funnelforge.domain.models import Page, RunState, StepStatus
from funnelforge.pipeline import steps as st
from funnelforge.pipeline.pipeline import Deps
from funnelforge.pipeline.runner import Runner
from tests.fakes import FakeLLM


class _CountingImageGen:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt: str, size: str = "1536x1024") -> bytes:
        self.calls += 1
        return b"fake-image-bytes"


class _CountingImageProc:
    def __init__(self) -> None:
        self.calls = 0

    def to_webp(self, data: bytes, out_path: Path, quality: int = 80) -> Path:
        self.calls += 1
        out_path.write_bytes(data)
        return out_path


def _settings(hero_image: bool) -> Settings:
    return Settings(
        secrets=Secrets(), run=RunConfig(hero_image=hero_image),
        site=SiteConfig(domain="https://creditoup.com.br"),
        steps={"image": StepConfig(model="gpt-image-2")},
    )


def _page() -> Page:
    return Page(page_number=1, page_type="LANDING PAGE", h1_title="Saque FGTS",
               slug="saque-fgts", emotional_objective="clareza")


def test_step_image_skips_generation_when_hero_image_off(tmp_path: Path) -> None:
    settings = _settings(hero_image=False)
    runner = Runner(llm=FakeLLM(responses=["a photo prompt"]), max_retries=0,
                    runs_dir=tmp_path / "runs")
    image_gen, image_proc = _CountingImageGen(), _CountingImageProc()
    deps = Deps(llm=runner.llm, research=None, image_gen=image_gen, image_proc=image_proc,
                publisher=None, loader=None, settings=settings, runner=runner)
    state = RunState(run_id="saque-fgts-20260715-101010")

    st.step_image(state, _page(), deps)

    # the creative-prompt LLM step still ran (dry runs stay auditable)...
    assert "image_p1" in state.step_status
    assert state.step_status["image_p1"].status.value == "OK"
    # ...but the real image generation/conversion calls (the gpt-image spend
    # and the webp conversion) must NOT have fired, and no image is recorded.
    assert image_gen.calls == 0
    assert image_proc.calls == 0
    assert 1 not in state.images


class _CapturingImageGen:
    def __init__(self) -> None:
        self.sizes: list[str] = []

    def generate(self, prompt: str, size: str = "1536x1024") -> bytes:
        self.sizes.append(size)
        return b"fake-image-bytes"


def test_lp_uses_vertical_size_interior_uses_landscape(tmp_path: Path) -> None:
    """The LP hero is generated VERTICAL (run.image_size_lp) with the LP-only
    prompt; an interior /rec featured image is generated LANDSCAPE
    (run.image_size_post)."""
    settings = _settings(hero_image=True)
    settings.run.featured_image = True  # so the interior page also generates
    runner = Runner(llm=FakeLLM(responses=["lp prompt", "post prompt"]), max_retries=0,
                    runs_dir=tmp_path / "runs")
    gen = _CapturingImageGen()
    deps = Deps(llm=runner.llm, research=None, image_gen=gen, image_proc=_CountingImageProc(),
                publisher=None, loader=None, settings=settings, runner=runner)
    state = RunState(run_id="saque-fgts-20260715-101010")

    st.step_image(state, _page(), deps)  # LANDING PAGE
    interior = Page(page_number=3, page_type="SOLUTION", h1_title="Consultar FGTS",
                    slug="consultar-fgts-p1", emotional_objective="clareza")
    st.step_image(state, interior, deps)

    assert gen.sizes == [settings.run.image_size_lp, settings.run.image_size_post]
    assert settings.run.image_size_lp != settings.run.image_size_post


def test_step_image_generates_when_hero_image_on(tmp_path: Path) -> None:
    settings = _settings(hero_image=True)
    runner = Runner(llm=FakeLLM(responses=["a photo prompt"]), max_retries=0,
                    runs_dir=tmp_path / "runs")
    image_gen, image_proc = _CountingImageGen(), _CountingImageProc()
    deps = Deps(llm=runner.llm, research=None, image_gen=image_gen, image_proc=image_proc,
                publisher=None, loader=None, settings=settings, runner=runner)
    state = RunState(run_id="saque-fgts-20260715-101010")

    st.step_image(state, _page(), deps)

    assert image_gen.calls == 1
    assert image_proc.calls == 1
    assert 1 in state.images


def test_step_image_noops_generation_when_ports_missing_dry_run(tmp_path: Path) -> None:
    """Pre-existing dry-run behavior (image_gen/image_proc None) must stay
    intact regardless of hero_image."""
    settings = _settings(hero_image=True)
    runner = Runner(llm=FakeLLM(responses=["a photo prompt"]), max_retries=0,
                    runs_dir=tmp_path / "runs")
    deps = Deps(llm=runner.llm, research=None, image_gen=None, image_proc=None,
                publisher=None, loader=None, settings=settings, runner=runner)
    state = RunState(run_id="saque-fgts-20260715-101010")

    st.step_image(state, _page(), deps)

    assert "image_p1" in state.step_status
    assert 1 not in state.images


def _raising_responder(model: str, messages: list[dict]) -> str:
    """Simulates the real smoke-run bug: `steps.image.model` pointed at an
    image-only model (e.g. gpt-image-2) so the chat-completion call for the
    prompt-crafting step raises (OpenAIException InternalServerError in
    production)."""
    raise RuntimeError("OpenAIException: InternalServerError (not a chat model)")


def test_step_image_crafting_llm_raises_is_not_fatal(tmp_path: Path) -> None:
    """FIX B: if the prompt-crafting LLM call raises (e.g. `steps.image.model`
    is misconfigured to an image-only model), step_image must swallow the
    exception, record `image_p1` as SKIPPED (never FAILED), and NEVER
    propagate -- so a page whose write/judge/seo already passed can still
    reach step_build in the pipeline's per-page loop."""
    settings = _settings(hero_image=True)
    runner = Runner(llm=FakeLLM(responses=_raising_responder), max_retries=0,
                    runs_dir=tmp_path / "runs")
    image_gen, image_proc = _CountingImageGen(), _CountingImageProc()
    deps = Deps(llm=runner.llm, research=None, image_gen=image_gen, image_proc=image_proc,
                publisher=None, loader=None, settings=settings, runner=runner)
    state = RunState(run_id="saque-fgts-20260715-101010")

    st.step_image(state, _page(), deps)  # must not raise

    assert "image_p1" in state.step_status
    result = state.step_status["image_p1"]
    assert result.status is StepStatus.SKIPPED
    assert result.status is not StepStatus.FAILED
    assert any(i.code == "image_skipped" for i in result.issues)
    # generation was never reached since crafting itself blew up
    assert image_gen.calls == 0
    assert image_proc.calls == 0
    assert 1 not in state.images


def test_step_image_generation_failure_is_not_fatal(tmp_path: Path) -> None:
    """Same guarantee when the crafting call succeeds but image
    generation/webp conversion blows up (e.g. a real image-provider 5xx)."""
    class _RaisingImageGen:
        def generate(self, prompt: str, size: str = "1536x1024") -> bytes:
            raise RuntimeError("image provider 500")

    settings = _settings(hero_image=True)
    runner = Runner(llm=FakeLLM(responses=["a photo prompt"]), max_retries=0,
                    runs_dir=tmp_path / "runs")
    deps = Deps(llm=runner.llm, research=None, image_gen=_RaisingImageGen(),
                image_proc=_CountingImageProc(), publisher=None, loader=None,
                settings=settings, runner=runner)
    state = RunState(run_id="saque-fgts-20260715-101010")

    st.step_image(state, _page(), deps)  # must not raise

    result = state.step_status["image_p1"]
    assert result.status is StepStatus.SKIPPED
    assert 1 not in state.images
