# funnel-forge/tests/conftest.py
from __future__ import annotations
from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def _sem_espera_de_verdade(monkeypatch):
    """Nenhum teste dorme de verdade. Nunca.

    A retentativa da pesquisa espera com backoff exponencial
    (`run.research_backoff_s`, dobrando). Num teste que exercita o caminho de
    falha, isso vira sono real: `test_sparse_provider_research_blocks_writer_
    before_any_write_call` sozinho passou a levar 12 s dos 16 s da suíte
    inteira. Suíte lenta é suíte que se deixa de rodar.

    Fica `autouse` de propósito, e não como conserto pontual naquele teste: o
    próximo caminho de retentativa que alguém escrever herda a proteção sem
    precisar lembrar dela. O código de produção continua dormindo — só o teste
    é que não.
    """
    import time as _time

    from funnelforge.pipeline import steps as _steps

    monkeypatch.setattr(_steps.time, "sleep", lambda _s: None, raising=False)
    monkeypatch.setattr(_time, "sleep", lambda _s: None)


@pytest.fixture
def config_files(tmp_path: Path) -> Path:
    """Write a minimal .env + config.yaml (mirrors Task 1's test values) into tmp_path.

    Includes every `steps:` entry from the project's real config.yaml so
    `load_settings(tmp_path / ".env", tmp_path / "config.yaml")` yields a
    Settings object with all step configs the pipeline needs (extract,
    research, write_p1, write_page, judge, seo, image).
    """
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-test\n"
        "GEMINI_API_KEY=gm-test\n"
        "ANTHROPIC_API_KEY=an-test\n"
        "PERPLEXITY_API_KEY=px-test\n"
        "WP_URL=https://creditoup.com.br\n"
        "WP_USER=admin\n"
        "WP_APP_TOKEN=abc\n",
        encoding="utf-8",
    )
    (tmp_path / "config.yaml").write_text(
        "run:\n"
        "  max_retries: 1\n"
        "  publish: false\n"
        "site:\n"
        "  domain: https://creditoup.com.br\n"
        "  post_type: rec\n"
        '  cnpj: "42.724.548/0001-24"\n'
        "  author: {name: Equipe Credito Up, credential: Redacao de jornalismo de servico.}\n"
        "  authors:\n"
        "    - {name: Equipe Credito Up, credential: Redacao, profile_slug: equipe}\n"
        "  official_preference: []\n"
        "  cross_funnel_lps: [emprestimo-consignado]\n"
        "routing:\n"
        "  LP:       {allowed_targets: [funnel], required_targets: [funnel],\n"
        "             forbidden_targets: [self, bare_rec, external_official, cross_funnel],\n"
        "             cta_min: 5, cta_max: 8, distinct_targets: false, anchor_congruent: true}\n"
        "  PRESELL:  {allowed_targets: [funnel], required_targets: [funnel],\n"
        "             forbidden_targets: [self, bare_rec],\n"
        "             cta_min: 2, cta_max: 6, distinct_targets: true, anchor_congruent: true}\n"
        # Honest-graph (Plano A): the winning graph is forward-only -- a mid
        # SOLUTION carries [funnel, external_official]; the terminal carries
        # [cross_funnel] only, validated against SOLUTION_TERMINAL, which
        # step_write now selects via pagespec_for(..., terminal=is_terminal).
        # This fixture mirrors the STRICT production config.yaml so the smoke/
        # gate tests actually exercise the real routing enforcement.
        # CARD-0011 (OVERRIDE-1 fan-out): a mid SOLUTION now advances to EVERY
        # subsequent solution (p_i -> {p_{i+1}..p_n}), so cta_max must accommodate
        # (n-ordinal) forward funnel edges -- mirrors production config.yaml's
        # SOLUTION cta_max 5 (was 1 under the old forward-single graph). cta_min
        # stays 1 (the terminal/last mid still carries a single forward edge).
        "  SOLUTION: {allowed_targets: [funnel, external_official],\n"
        "             required_targets: [funnel, external_official],\n"
        "             forbidden_targets: [self, bare_rec, cross_funnel], cta_min: 1, cta_max: 5,\n"
        "             distinct_targets: true, anchor_congruent: true}\n"
        "  SOLUTION_TERMINAL: {allowed_targets: [cross_funnel], required_targets: [cross_funnel],\n"
        "             forbidden_targets: [self, funnel, external_official, bare_rec],\n"
        "             cta_min: 1, cta_max: 1, distinct_targets: false, anchor_congruent: true}\n"
        "ads:\n"
        "  vignette: {enabled: true, max_per_window: 1, window_seconds: 600}\n"
        "  slots:\n"
        "    LP:\n"
        "      - {slot_id: lp-hero, placement: hero, sizes: [fluid, 336x280],\n"
        "         min_height_px: 280, refresh_eligible: false, source_key: ''}\n"
        "      - {slot_id: lp-footer, placement: footer, sizes: [fluid],\n"
        "         min_height_px: 250, refresh_eligible: false, source_key: ''}\n"
        "    PRESELL:\n"
        "      - {slot_id: pr-inline, placement: inline, sizes: [fluid, 300x250],\n"
        "         min_height_px: 250, refresh_eligible: false, source_key: ''}\n"
        "    SOLUTION:\n"
        "      - {slot_id: sol-inline-1, placement: inline, sizes: [fluid, 300x250],\n"
        "         min_height_px: 250, refresh_eligible: true, source_key: ''}\n"
        "      - {slot_id: sol-footer, placement: footer, sizes: [fluid],\n"
        "         min_height_px: 250, refresh_eligible: false, source_key: ''}\n"
        "index:\n"
        "  LP:       {robots: 'noindex,follow'}\n"
        "  PRESELL:  {robots: 'noindex,follow'}\n"
        "  SOLUTION: {robots: 'noindex,follow'}\n"
        "uniqueness:\n"
        "  jaccard_threshold: 0.35\n"
        "steps:\n"
        "  extract:    {model: gpt-5.2, fallbacks: [], temperature: 0.2,\n"
        "               validators: [funnel_schema]}\n"
        "  synthesize_angles: {model: gemini/gemini-3.5-flash, fallbacks: [gpt-4.1],\n"
        "               temperature: 0.8, validators: []}\n"
        "  research:   {model: perplexity/sonar-deep-research, fallbacks: [], temperature: 0.2,\n"
        "               validators: [has_sources]}\n"
        "  write_p1:   {model: claude-opus-4-8, fallbacks: [], temperature: 0.7,\n"
        "               validators: [lp_json_contract, calm_utility, language_pt,\n"
        "                            critical_fact_grounding]}\n"
        "  write_page: {model: claude-opus-4-8, fallbacks: [], temperature: 0.7,\n"
        "               validators: [gutenberg_blocks, cta_style, pagespec, calm_utility,"
        " compliance, language_pt, same_domain, no_bare_rec, no_self_loop, identity,"
        " uniqueness]}\n"
        "  judge:      {model: gemini/gemini-2.5-pro, fallbacks: [], temperature: 0.0,\n"
        "               validators: []}\n"
        "  seo:        {model: gpt-4o, fallbacks: [], temperature: 0.4,\n"
        "               validators: [seo_limits]}\n"
        "  image:      {model: gpt-image-2, fallbacks: [], temperature: 1.0,\n"
        "               validators: []}\n",
        encoding="utf-8",
    )
    return tmp_path
