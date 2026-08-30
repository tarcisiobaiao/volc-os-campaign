from pathlib import Path
from funnelforge.pipeline.runner import Runner
from funnelforge.config.settings import StepConfig
from funnelforge.domain.models import StepStatus
from funnelforge.ports.llm import LLMResult
from tests.fakes import FakeLLM


def test_retries_with_feedback_then_passes(tmp_path: Path):
    # first output leaks spanish (fails language_pt), second is clean
    llm = FakeLLM(responses=["Ingreso in 2026", "Consulte seu saldo em 2026"])
    r = Runner(llm=llm, max_retries=2, runs_dir=tmp_path)
    cfg = StepConfig(model="m", fallbacks=[], temperature=0.0, validators=["language_pt"])
    text, res = r.run_llm_step("write", cfg, [{"role": "user", "content": "go"}], ctx={},
                               run_id="test-run")
    assert "saldo" in text
    assert res.status in (StepStatus.OK, StepStatus.RETRIED)
    assert res.attempts == 2
    # feedback was injected on the retry
    assert any("language_pt" in str(c["messages"]) for c in llm.calls[1:])


def test_failed_when_never_valid(tmp_path: Path):
    llm = FakeLLM(responses=["Ingreso", "Ingreso", "Ingreso"])
    r = Runner(llm=llm, max_retries=1, runs_dir=tmp_path)
    cfg = StepConfig(model="m", fallbacks=[], temperature=0.0, validators=["language_pt"])
    _, res = r.run_llm_step("write", cfg, [{"role": "user", "content": "go"}], ctx={},
                            run_id="test-run")
    assert res.status is StepStatus.FAILED


def test_fallback_status_when_primary_fails(tmp_path):
    def responder(model, messages):
        if model == "primary":
            raise RuntimeError("primary down")
        return "Consulte seu saldo do FGTS em 2026"  # clean PT
    llm = FakeLLM(responses=responder)
    r = Runner(llm=llm, max_retries=1, runs_dir=tmp_path)
    cfg = StepConfig(model="primary", fallbacks=["backup"], temperature=0.0,
                     validators=["language_pt"])
    _, res = r.run_llm_step("w", cfg, [{"role": "user", "content": "go"}], ctx={},
                            run_id="test-run")
    assert res.status is StepStatus.FALLBACK
    assert res.model_used == "backup"


class _VersionedLLM:
    """Returns a fixed `model_used` regardless of the requested model, to
    simulate a provider echoing back a versioned/dated or prefix-stripped
    variant of the configured model name."""

    def __init__(self, text: str, used_model: str):
        self._text = text
        self._used_model = used_model

    def complete(self, model, fallbacks, messages, temperature, response_schema=None,
                 web_search=False):
        return LLMResult(text=self._text, model_used=self._used_model)


def test_fallback_not_flagged_for_dated_model_variant(tmp_path):
    """FIX 4 (smoke): primary `gpt-4.1` (config) vs `gpt-4.1-2025-04-14`
    (returned) is the SAME model, not a fallback."""
    llm = _VersionedLLM("Consulte seu saldo do FGTS em 2026", "gpt-4.1-2025-04-14")
    r = Runner(llm=llm, max_retries=0, runs_dir=tmp_path)
    cfg = StepConfig(model="gpt-4.1", fallbacks=[], temperature=0.0,
                     validators=["language_pt"])
    _, res = r.run_llm_step("w", cfg, [{"role": "user", "content": "go"}], ctx={},
                            run_id="test-run")
    assert res.status is StepStatus.OK
    assert res.model_used == "gpt-4.1-2025-04-14"


def test_fallback_not_flagged_for_provider_prefix_mismatch(tmp_path):
    """primary `gemini/gemini-2.5-pro` (config) vs `gemini-2.5-pro`
    (returned, no provider prefix) is the SAME model, not a fallback."""
    llm = _VersionedLLM("Consulte seu saldo do FGTS em 2026", "gemini-2.5-pro")
    r = Runner(llm=llm, max_retries=0, runs_dir=tmp_path)
    cfg = StepConfig(model="gemini/gemini-2.5-pro", fallbacks=[], temperature=0.0,
                     validators=["language_pt"])
    _, res = r.run_llm_step("w", cfg, [{"role": "user", "content": "go"}], ctx={},
                            run_id="test-run")
    assert res.status is StepStatus.OK


def test_fallback_flagged_when_used_model_matches_configured_fallback_base(tmp_path):
    """A used model equal to a configured FALLBACK base (not the primary)
    must still be reported as FALLBACK."""
    def responder(model, messages):
        if model == "gpt-4.1":
            raise RuntimeError("primary down")
        return "Consulte seu saldo do FGTS em 2026"
    llm = FakeLLM(responses=responder)
    r = Runner(llm=llm, max_retries=1, runs_dir=tmp_path)
    cfg = StepConfig(model="gpt-4.1", fallbacks=["gemini/gemini-2.5-pro"], temperature=0.0,
                     validators=["language_pt"])
    _, res = r.run_llm_step("w", cfg, [{"role": "user", "content": "go"}], ctx={},
                            run_id="test-run")
    assert res.status is StepStatus.FALLBACK
    assert res.model_used == "gemini/gemini-2.5-pro"


def test_checkpoint_writes_state_atomically(tmp_path):
    r = Runner(llm=FakeLLM(responses=[]), max_retries=0, runs_dir=tmp_path)
    r.checkpoint("run1", '{"x": 1}')
    assert (tmp_path / "run1" / "state.json").read_text(encoding="utf-8") == '{"x": 1}'
    assert not (tmp_path / "run1" / "state.json.tmp").exists()


def test_log_appends_jsonl(tmp_path):
    r = Runner(llm=FakeLLM(responses=[]), max_retries=0, runs_dir=tmp_path)
    r.log("run1", {"a": 1})
    r.log("run1", {"a": 2})
    lines = (tmp_path / "run1" / "log.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


class _EchoLLM:
    def __init__(self, texts):
        self._texts = list(texts)
        self.seen = []

    def complete(self, model, fallbacks, messages, temperature, response_schema=None,
                 web_search=False):
        self.seen.append([dict(m) for m in messages])
        return LLMResult(text=self._texts.pop(0), model_used=model,
                         prompt_tokens=10, completion_tokens=5, cost_usd=0.001,
                         latency_ms=42)


def test_run_llm_step_sums_telemetry_and_logs_each_attempt(tmp_path: Path):
    llm = _EchoLLM(["contains ingreso spanish", "texto limpo em portugues"])
    cfg = StepConfig(model="m", validators=["language_pt"])
    r = Runner(llm=llm, max_retries=2, runs_dir=tmp_path)
    text, res = r.run_llm_step("extract", cfg, [{"role": "user", "content": "x"}],
                               ctx={}, run_id="saque-fgts-20260715-101010")
    assert res.prompt_tokens == 20 and res.completion_tokens == 10
    assert abs(res.cost_usd - 0.002) < 1e-9 and res.latency_ms == 84
    log = (tmp_path / "saque-fgts-20260715-101010" / "log.jsonl").read_text("utf-8")
    assert log.strip().count("\n") == 1  # two attempts -> two lines
    assert '"ts": "20260715-101010"' in log


def test_retry_echoes_prior_assistant_turn(tmp_path: Path):
    llm = _EchoLLM(["ingreso spanish leak", "portugues limpo"])
    cfg = StepConfig(model="m", validators=["language_pt"])
    r = Runner(llm=llm, max_retries=2, runs_dir=tmp_path)
    r.run_llm_step("s", cfg, [{"role": "user", "content": "orig"}], ctx={}, run_id="r-1")
    second = llm.seen[1]
    assert any(m["role"] == "assistant" and m["content"] == "ingreso spanish leak"
               for m in second)


def test_finalize_run_id_renames_and_is_noop_when_equal(tmp_path: Path):
    r = Runner(llm=_EchoLLM([]), max_retries=0, runs_dir=tmp_path)
    (tmp_path / "_pending-20260715-101010").mkdir()
    (tmp_path / "_pending-20260715-101010" / "log.jsonl").write_text("x", "utf-8")
    r.finalize_run_id("_pending-20260715-101010", "saque-fgts-20260715-101010")
    assert (tmp_path / "saque-fgts-20260715-101010" / "log.jsonl").exists()
    assert not (tmp_path / "_pending-20260715-101010").exists()
    r.finalize_run_id("saque-fgts-20260715-101010", "saque-fgts-20260715-101010")


def test_snapshot_prompt_writes_rendered_prompt(tmp_path):
    r = Runner(llm=FakeLLM(responses=[]), max_retries=0, runs_dir=tmp_path)
    r.snapshot_prompt("run1", "extract", [{"role": "user", "content": "BRIEFING X"}])
    txt = (tmp_path / "run1" / "prompts" / "extract.txt").read_text(encoding="utf-8")
    assert "BRIEFING X" in txt
