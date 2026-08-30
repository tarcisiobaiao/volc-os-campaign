from funnelforge.adapters.research_perplexity import PerplexityResearch
from funnelforge.config.settings import StepConfig
from funnelforge.ports.llm import LLMResult
from tests.fakes import FakeLLM

CFG = StepConfig(model="perplexity/sonar-deep-research", fallbacks=[], temperature=0.2,
                  validators=["has_sources"])


class _TelemetryLLM:
    """Fake LLM that returns a fixed LLMResult carrying non-zero telemetry,
    to verify the adapter records it (FIX 5, smoke)."""

    def __init__(self, text: str):
        self._text = text
        self.calls: list[dict] = []

    def complete(self, model, fallbacks, messages, temperature, response_schema=None,
                 web_search=False):
        self.calls.append({"model": model})
        return LLMResult(text=self._text, model_used=model, prompt_tokens=120,
                         completion_tokens=340, cost_usd=0.0123, latency_ms=987)


def test_research_with_sources_is_not_sparse():
    llm = FakeLLM(responses=[
        '{"resumo": "r", "dados_validados": [], "passo_a_passo": [], '
        '"fontes": ["https://gov.br/fgts"]}'
    ])
    facts = PerplexityResearch(llm, CFG).research(topic="Saque FGTS", structure="H2: Como")
    assert facts.sparse is False
    assert facts.fontes == ["https://gov.br/fgts"]


def test_research_with_empty_fontes_is_marked_sparse():
    """Reconciles the Task 12 seam: the pipeline does NOT run the
    `has_sources` validator when a ResearchProvider is injected, so the
    adapter itself must flag "no sources" via `sparse=True`."""
    llm = FakeLLM(responses=['{"resumo": "r", "fontes": []}'])
    facts = PerplexityResearch(llm, CFG).research(topic="Saque FGTS", structure="H2: Como")
    assert facts.sparse is True


def test_research_on_unparseable_llm_output_returns_sparse_facts():
    llm = FakeLLM(responses=["not json at all"])
    facts = PerplexityResearch(llm, CFG).research(topic="Saque FGTS", structure="H2: Como")
    assert facts.sparse is True


def test_research_never_raises_on_llm_error():
    def boom(model, messages):
        raise RuntimeError("provider down")

    llm = FakeLLM(responses=boom)
    facts = PerplexityResearch(llm, CFG).research(topic="Saque FGTS", structure="H2: Como")
    assert facts.sparse is True


def test_research_without_step_cfg_returns_sparse_without_calling_llm():
    llm = FakeLLM(responses=[])
    facts = PerplexityResearch(llm, None).research(topic="Saque FGTS", structure="H2: Como")
    assert facts.sparse is True
    assert llm.calls == []


def test_research_records_last_call_telemetry():
    """FIX 5 (smoke): research goes through this adapter, not
    `run_llm_step`, so cost/tokens used to show as 0 in report.md. The
    adapter must record the LAST call's telemetry as attributes."""
    llm = _TelemetryLLM(
        '{"resumo": "r", "dados_validados": [], "passo_a_passo": [], '
        '"fontes": ["https://gov.br/fgts"]}'
    )
    provider = PerplexityResearch(llm, CFG)
    assert provider.last_prompt_tokens == 0 and provider.last_cost_usd == 0.0
    provider.research(topic="Saque FGTS", structure="H2: Como")
    assert provider.last_prompt_tokens == 120
    assert provider.last_completion_tokens == 340
    assert provider.last_cost_usd == 0.0123
    assert provider.last_latency_ms == 987
