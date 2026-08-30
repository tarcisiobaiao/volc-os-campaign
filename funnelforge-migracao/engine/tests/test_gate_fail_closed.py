import json
from pathlib import Path

from funnelforge.adapters.briefing_docx import DocxBriefingLoader
from funnelforge.config.settings import load_settings
from funnelforge.domain.models import StepStatus
from funnelforge.pipeline.pipeline import Deps, run_pipeline
from funnelforge.pipeline.runner import Runner
from tests.fakes import FakeLLM
from tests.test_smoke_e2e import (
    ANGLES_JSON,
    IMAGE_PROMPT,
    P1_JSON,
    PLAN_JSON,
    RESEARCH_JSON,
    SEO_JSON,
    _page_html_for,
)

# 1-page plan so `only="p1"` exercises just the LP fail-closed path.
LP_PLAN = ('{"funnel_strategy":{"avatar_summary":"a","tone_voice":"t","total_pages":1},'
           '"pages":[{"page_number":1,"page_type":"LANDING PAGE","h1_title":"Saque FGTS",'
           '"slug":"saque-fgts","main_content_structure":["H2: a"],'
           '"hook_to_next_page":"ver","next_page_slug":"quem-tem-direito",'
           '"target_keywords":["fgts"]}]}')
SEO = '{"seotitle":"t","metadescription":"d","keywordfocus":"k","slug":"s"}'


# ---------------------------------------------------------------------------
# LP fail-closed gate. The LP is STRUCTURED JSON filling the Elementor template
# -- it is NOT judged by the marker/HTML judge; its gate is validate_lp_content
# (schema + middle-ground compliance) inside step_write. LP LLM call order:
# extract, research, write_p1, seo, image (NO judge).
# ---------------------------------------------------------------------------


def _run_lp(tmp_path: Path, config_files, p1_response: str):
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    def _responder(model: str, messages: list[dict]) -> str:
        """Responde por CASAMENTO DE PROMPT, não por posição na lista.

        A LP passou a ter validadores no runner: uma reprovação vira mensagem
        de correção e NOVA tentativa. Com lista posicional, a segunda tentativa
        consumia a resposta do passo seguinte e o roteiro inteiro saía do
        lugar — o teste falharia pelo motivo errado. Casar por prompt mantém o
        roteiro estável com ou sem retry.
        """
        content = messages[-1]["content"]
        if "Corrija OBRIGATORIAMENTE" in content or "PÁGINA DE POUSO" in content:
            return p1_response
        if "BRIEFING_DE_ENTRADA" in content:
            return LP_PLAN
        if "Pesquise e retorne SOMENTE um objeto JSON" in content:
            return '{"resumo":"r","fontes":["https://x"]}'
        if "YOAST SEO" in content:
            return SEO
        return "img"

    llm = FakeLLM(responses=_responder)
    runner = Runner(llm=llm, max_retries=1, runs_dir=tmp_path / "runs")
    deps = Deps(llm=llm, research=None, image_gen=None, image_proc=None, publisher=None,
                loader=DocxBriefingLoader(), settings=settings, runner=runner)
    b = tmp_path / "b.txt"
    b.write_text("Briefing FGTS")
    return run_pipeline(b, deps, only="p1", publish=False, timestamp="20260715-101010")


def test_valid_lp_json_builds(tmp_path: Path, config_files):
    state = _run_lp(tmp_path, config_files, P1_JSON)
    assert state.step_status["write_p1"].status is not StepStatus.FAILED
    assert "blocked_p1" not in state.step_status
    assert (tmp_path / "runs" / state.run_id / "p1.elementor.json").exists()


def test_non_json_lp_blocks(tmp_path: Path, config_files):
    state = _run_lp(tmp_path, config_files, "not json at all, sorry -- §§ garbled")
    assert state.step_status["write_p1"].status is StepStatus.FAILED
    assert "blocked_p1" in state.step_status
    assert not (tmp_path / "runs" / state.run_id / "p1.elementor.json").exists()


def test_lp_missing_slots_blocks(tmp_path: Path, config_files):
    bad = json.dumps({"hero_title": "x", "cta_texts": ["a", "b", "c"]})  # most slots missing
    state = _run_lp(tmp_path, config_files, bad)
    assert state.step_status["write_p1"].status is StepStatus.FAILED
    assert "lp_missing_slot" in {i.code for i in state.step_status["write_p1"].issues}
    assert "blocked_p1" in state.step_status
    assert not (tmp_path / "runs" / state.run_id / "p1.elementor.json").exists()


def test_lp_banned_cta_execution_blocks(tmp_path: Path, config_files):
    bad = json.loads(P1_JSON)
    # 3 CTAs: com 5, a LP reprovaria por `lp_ctas` (quantidade) e o teste
    # passaria pelo motivo ERRADO, sem nunca exercitar o `cta_execution`.
    bad["cta_texts"] = ["Agendar meu saque »", "Solicitar agora »", "Ver »"]
    state = _run_lp(tmp_path, config_files, json.dumps(bad, ensure_ascii=False))
    assert state.step_status["write_p1"].status is StepStatus.FAILED
    assert "cta_execution" in {i.code for i in state.step_status["write_p1"].issues}
    assert not (tmp_path / "runs" / state.run_id / "p1.elementor.json").exists()


# ---------------------------------------------------------------------------
# Interior (HUB/SOLUTION) fail-closed JUDGE gate -- still the marker/HTML judge.
# ---------------------------------------------------------------------------


def _run_funnel(tmp_path: Path, config_files, judge_fn):
    def _responder(model: str, messages: list[dict]) -> str:
        content = messages[-1]["content"]
        if "BRIEFING_DE_ENTRADA" in content:
            return PLAN_JSON
        if "ESTRATEGISTA-CHEFE" in content:
            return ANGLES_JSON
        if "Pesquise e retorne SOMENTE um objeto JSON" in content:
            return RESEARCH_JSON
        if "PÁGINA DE POUSO" in content:
            return P1_JSON
        if "PÁGINA INTERNA" in content or "PÁGINA PRÉ-SELL" in content:
            return _page_html_for(content)
        if "JUIZ DE QUALIDADE" in content:
            return judge_fn(content)
        if "YOAST SEO" in content:
            return SEO_JSON
        if "VISUAL STRATEGIST" in content:
            return IMAGE_PROMPT
        raise AssertionError(f"unscripted prompt: {content[:120]!r}")

    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    llm = FakeLLM(responses=_responder)
    runner = Runner(llm=llm, max_retries=settings.run.max_retries, runs_dir=tmp_path / "runs")
    deps = Deps(llm=llm, research=None, image_gen=None, image_proc=None, publisher=None,
                loader=DocxBriefingLoader(), settings=settings, runner=runner)
    b = tmp_path / "b.txt"
    b.write_text("Briefing FGTS")
    return run_pipeline(b, deps, only=None, publish=False)


def test_blocking_judge_skips_interior_build(tmp_path: Path, config_files):
    """A blocking judge verdict on the interior pages -> those pages FAIL and
    are not built (fail-closed on write_pN/judge_pN)."""
    blocking = '{"approved":false,"blocking":true,"scores":{"compliance":3},"feedback":["x"]}'
    state = _run_funnel(tmp_path, config_files, lambda c: blocking)
    run_dir = tmp_path / "runs" / state.run_id
    for p in state.plan.pages:
        if p.page_type == "LANDING PAGE":
            continue
        n = p.page_number
        assert state.step_status[f"judge_p{n}"].status is StepStatus.FAILED
        assert f"blocked_p{n}" in state.step_status
    assert not list(run_dir.glob("p2.*.gutenberg.html"))


def test_solution_multi_destination_not_blocked(tmp_path: Path, config_files):
    """A SOLUTION page's low single_destination score must NOT block (its
    multi-destination routing is pagespec's job); LP/HUB stay passing."""
    passing = ('{"approved":true,"blocking":false,"scores":{"single_destination":9,'
               '"proof_and_authority":8,"compliance":9,"cta_discipline":8},"feedback":[]}')
    low_sd = ('{"approved":false,"blocking":false,"scores":{"single_destination":3,'
              '"proof_and_authority":8,"compliance":9,"cta_discipline":8},"feedback":["multi"]}')
    state = _run_funnel(
        tmp_path, config_files,
        lambda c: low_sd if "Esta é uma página SOLUTION" in c else passing)
    run_dir = tmp_path / "runs" / state.run_id
    sols = [p for p in state.plan.pages if p.page_type == "SOLUTION"]
    assert len(sols) == 3
    for p in sols:
        assert state.step_status[f"judge_p{p.page_number}"].status is not StepStatus.FAILED
        assert f"blocked_p{p.page_number}" not in state.step_status
        assert list(run_dir.glob(f"p{p.page_number}.*.gutenberg.html"))
