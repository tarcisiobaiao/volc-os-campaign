from typer.testing import CliRunner
from funnelforge.cli import app
from funnelforge.domain.models import FunnelPlan, Page, RunState, StepResult, StepStatus

runner = CliRunner()


def test_models_command_prints_map(tmp_path, monkeypatch, config_files):
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["models"])
    assert res.exit_code == 0
    assert "write_p1" in res.stdout


def _all_ok_state(run_id: str) -> RunState:
    page = Page(page_number=1, page_type="LANDING PAGE", h1_title="Saque FGTS",
                slug="saque-fgts", emotional_objective="o",
                main_content_structure=["H2: a"], hook_to_next_page="ir",
                next_page_slug="p2", target_keywords=["fgts"])
    plan = FunnelPlan(avatar_summary="a", tone_voice="calmo", total_pages=1, pages=[page])
    state = RunState(run_id=run_id, briefing_text="Briefing FGTS", plan=plan)
    for key in ("research_p1", "write_p1", "seo_p1", "image_p1", "build_p1"):
        state.step_status[key] = StepResult(step=key, status=StepStatus.OK, attempts=1)
    return state


def test_resume_command_loads_state_and_completes_without_briefing(
    tmp_path, monkeypatch, config_files
):
    monkeypatch.chdir(tmp_path)
    run_id = "saque-fgts"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    state = _all_ok_state(run_id)
    (run_dir / "state.json").write_text(state.to_json(), encoding="utf-8")

    res = runner.invoke(app, ["resume", run_id])

    assert res.exit_code == 0, res.output
    assert (run_dir / "report.md").exists()


def test_resume_missing_run_id_fails_cleanly(tmp_path, monkeypatch, config_files):
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["resume", "does-not-exist"])
    assert res.exit_code != 0


def test_export_secrets_populates_environ(monkeypatch):
    from funnelforge.cli import _export_secrets
    from funnelforge.config.settings import Secrets
    for k in ["OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "PERPLEXITY_API_KEY"]:
        monkeypatch.delenv(k, raising=False)
    _export_secrets(Secrets(openai_api_key="sk-x", perplexity_api_key="pk-y"))
    import os
    assert os.environ["OPENAI_API_KEY"] == "sk-x"
    assert os.environ["PERPLEXITY_API_KEY"] == "pk-y"
    assert "GEMINI_API_KEY" not in os.environ  # None secrets are not exported
