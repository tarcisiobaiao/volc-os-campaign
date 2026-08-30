# funnel-forge/tests/test_step_research.py
"""FIX 5 (smoke): research goes through `deps.research` (a `ResearchProvider`
adapter), not `Runner.run_llm_step`, so its cost/tokens used to show as 0 in
report.md -- `PerplexityResearch` never surfaced its LLM call's telemetry.
`step_research` must copy the adapter's last-call telemetry into the
`research_p{n}` StepResult it stores."""
from datetime import date
from pathlib import Path

from funnelforge.config.settings import RunConfig, Secrets, Settings, SiteConfig, StepConfig
from funnelforge.domain.models import Page, ResearchFacts, RunState, VerifiedFact
from funnelforge.pipeline import steps as st
from funnelforge.pipeline.pipeline import Deps
from funnelforge.pipeline.runner import Runner
from tests.fakes import FakeLLM


class _TelemetryResearchProvider:
    """Stand-in for `PerplexityResearch` exposing the FIX 5 telemetry
    attributes with non-zero values."""

    def __init__(self) -> None:
        self.last_prompt_tokens = 250
        self.last_completion_tokens = 610
        self.last_cost_usd = 0.045
        self.last_latency_ms = 1500

    def research(self, topic: str, structure: str) -> ResearchFacts:
        return ResearchFacts(resumo="r", fontes=["https://gov.br/fgts"])


class _NoTelemetryResearchProvider:
    """A ResearchProvider that does NOT expose telemetry attrs at all --
    `step_research` must stay safe (default to 0) instead of raising."""

    def research(self, topic: str, structure: str) -> ResearchFacts:
        return ResearchFacts(resumo="r", fontes=["https://gov.br/fgts"])


class _SparseResearchProvider:
    def research(self, topic: str, structure: str) -> ResearchFacts:
        return ResearchFacts(sparse=True)


class _StrictResearchProvider:
    def research(self, topic: str, structure: str) -> ResearchFacts:
        source = "https://www.gov.br/fgts"
        return ResearchFacts(
            fontes=[source],
            fatos_verificados=[VerifiedFact(
                valor="10%", unidade="percentual", fonte_primaria=source,
                dispositivo="não se aplica", vigente_desde=date.today(),
                verificado_em=date.today())],
        )


class _LiveVerifier:
    """Implementação do port `UrlVerifier` (ports/services.py). Antes este
    stand-in era passado como `screenshot=`, porque o gate ia buscar
    `verify_url` dentro do provider de screenshot — o acoplamento que a
    Frente 6 desfez."""

    def verify_url(self, url: str) -> bool:
        return url == "https://www.gov.br/fgts"


def _settings() -> Settings:
    return Settings(
        secrets=Secrets(), run=RunConfig(),
        site=SiteConfig(domain="https://creditoup.com.br"),
        steps={"research": StepConfig(model="perplexity/sonar-deep-research")},
    )


def _page() -> Page:
    return Page(page_number=1, page_type="LANDING PAGE", h1_title="Saque FGTS",
               slug="saque-fgts", main_content_structure=["H2: Como funciona"])


def test_step_research_copies_adapter_telemetry_into_step_result(tmp_path: Path) -> None:
    settings = _settings()
    runner = Runner(llm=FakeLLM(responses=[]), max_retries=0, runs_dir=tmp_path / "runs")
    research = _TelemetryResearchProvider()
    deps = Deps(llm=runner.llm, research=research, image_gen=None, image_proc=None,
                publisher=None, loader=None, settings=settings, runner=runner)
    state = RunState(run_id="saque-fgts-20260715-101010")

    st.step_research(state, _page(), deps)

    res = state.step_status["research_p1"]
    assert res.prompt_tokens == 250
    assert res.completion_tokens == 610
    assert res.cost_usd == 0.045
    assert res.latency_ms == 1500


def test_step_research_defaults_telemetry_to_zero_when_provider_lacks_it(
    tmp_path: Path,
) -> None:
    settings = _settings()
    runner = Runner(llm=FakeLLM(responses=[]), max_retries=0, runs_dir=tmp_path / "runs")
    deps = Deps(llm=runner.llm, research=_NoTelemetryResearchProvider(), image_gen=None,
                image_proc=None, publisher=None, loader=None, settings=settings,
                runner=runner)
    state = RunState(run_id="saque-fgts-20260715-101010")

    st.step_research(state, _page(), deps)  # must not raise

    res = state.step_status["research_p1"]
    assert res.prompt_tokens == 0
    assert res.cost_usd == 0.0


def test_sparse_provider_research_blocks_writer_before_any_write_call(tmp_path: Path) -> None:
    settings = _settings()
    runner = Runner(llm=FakeLLM(responses=[]), max_retries=0, runs_dir=tmp_path / "runs")
    deps = Deps(llm=runner.llm, research=_SparseResearchProvider(), image_gen=None,
                image_proc=None, publisher=None, loader=None, settings=settings, runner=runner)
    state = RunState(run_id="saque-fgts-20260811-101010")
    page = _page()

    st.step_research(state, page, deps)
    st.step_write(state, page, deps)

    assert state.step_status["research_p1"].status is st.StepStatus.FAILED
    assert state.step_status["write_p1"].status is st.StepStatus.FAILED
    assert runner.llm.calls == []


def test_strict_fact_is_trusted_only_after_live_source_verification(tmp_path: Path) -> None:
    settings = _settings()
    runner = Runner(llm=FakeLLM(responses=[]), max_retries=0, runs_dir=tmp_path / "runs")
    deps = Deps(llm=runner.llm, research=_StrictResearchProvider(), image_gen=None,
                image_proc=None, publisher=None, loader=None, settings=settings, runner=runner,
                url_verifier=_LiveVerifier())
    state = RunState(run_id="saque-fgts-20260811-101010")

    st.step_research(state, _page(), deps)

    assert state.step_status["research_p1"].status is st.StepStatus.OK
    assert state.facts[1].fontes_resolvidas == ["https://www.gov.br/fgts"]
