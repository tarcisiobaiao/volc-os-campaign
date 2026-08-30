import pytest

from funnelforge.domain.models import (
    AdManifest, AdSlot, EXISTENTIAL_CRITERIA, IndexDecision, Verdict,
    Page, FunnelPlan, RunState, StepResult, StepStatus,
    PageRole, Route, derive_role, effective_role, resolve_route,
    role_matches_slug,
)


def test_funnelplan_roundtrip():
    p = Page(page_number=1, page_type="LANDING PAGE", h1_title="T", slug="t",
             emotional_objective="o", main_content_structure=["H2: a"],
             hook_to_next_page="ir", next_page_slug="p2", target_keywords=["k"])
    plan = FunnelPlan(avatar_summary="a", tone_voice="calmo", total_pages=1, pages=[p])
    st = RunState(run_id="r1", briefing_text="b", plan=plan)
    js = st.to_json()
    back = RunState.from_json(js)
    assert back.plan.pages[0].page_type == "LANDING PAGE"
    assert back.run_id == "r1"


def test_stepresult_status_enum():
    sr = StepResult(step="write_p1", status=StepStatus.OK, model_used="x", attempts=1)
    assert sr.status is StepStatus.OK


def test_derive_role_presell_before_solution():
    assert derive_role("saque-fgts-pr") is PageRole.PRESELL
    assert derive_role("saque-fgts-p1") is PageRole.SOLUTION
    assert derive_role("saque-fgts-p12") is PageRole.SOLUTION
    assert derive_role("saque-fgts") is PageRole.LP
    assert derive_role("saque-fgts-r") is PageRole.LP
    assert derive_role("saque-fgts-p1/") is PageRole.SOLUTION


def test_effective_role_and_match():
    p = Page(page_number=1, page_type="LANDING PAGE", h1_title="t", slug="fgts-pr")
    assert effective_role(p) is PageRole.PRESELL
    assert role_matches_slug(p) is True
    p2 = Page(page_number=1, page_type="x", h1_title="t", slug="fgts-pr",
              role=PageRole.LP)
    assert effective_role(p2) is PageRole.LP
    assert role_matches_slug(p2) is False


def test_resolve_route_funnel_same_domain():
    # Rota interna nao depende de autorizacao externa nenhuma: e slug do proprio
    # dominio. Por isso a chamada nao passa `authorized_external`.
    r = Route(placement="hero", kind="funnel", target="quem-tem-direito", anchor="a")
    assert resolve_route(r, domain="https://creditoup.com.br", post_type="rec") == \
        "https://creditoup.com.br/rec/quem-tem-direito"


def test_resolve_route_external_official_exige_url_da_pesquisa():
    """O lastro e a URL EXATA que a pesquisa daquela pagina trouxe -- nao o host.

    Autorizar por prefixo de host deixava o redator inventar um caminho plausivel
    dentro de um host legitimo. Com a URL inteira, o portal generico
    (https://www.gov.br) NAO carrega a pagina profunda (/inss)."""
    r = Route(placement="inline", kind="external_official",
              target="https://www.gov.br/inss", anchor="a")
    assert resolve_route(r, domain="https://creditoup.com.br", post_type="rec",
                         authorized_external=["https://www.gov.br/inss"]) == \
        "https://www.gov.br/inss"
    with pytest.raises(ValueError):
        resolve_route(r, domain="https://creditoup.com.br", post_type="rec",
                      authorized_external=["https://www.gov.br"])


def test_resolve_route_external_official_nao_e_por_lista_de_instalacao():
    """A autorizacao nao e por tema: um canal oficial NAO governamental (o
    cadastro do entregador do iFood) passa, desde que a pesquisa o tenha
    trazido. Era exatamente isso que a allowlist estatica impedia."""
    r = Route(placement="inline", kind="external_official",
              target="https://entregador.ifood.com.br/cadastro", anchor="a")
    assert resolve_route(
        r, domain="https://creditoup.com.br", post_type="rec",
        authorized_external=["https://entregador.ifood.com.br/cadastro"]) == \
        "https://entregador.ifood.com.br/cadastro"


def test_resolve_route_external_official_rejects_lookalike_domain():
    """Host sosia (gov.br.evil.com) continua reprovado -- agora por nao estar no
    conjunto autorizado, nao por estar fora de uma lista de instalacao."""
    with pytest.raises(ValueError):
        resolve_route(Route(placement="inline", kind="external_official",
                            target="https://www.gov.br.evil.com/x", anchor="a"),
                      domain="https://creditoup.com.br", post_type="rec",
                      authorized_external=["https://www.gov.br/programa"])
    r = Route(placement="inline", kind="external_official",
              target="https://www.gov.br/programa", anchor="a")
    assert resolve_route(r, domain="https://creditoup.com.br", post_type="rec",
                         authorized_external=["https://www.gov.br/programa"]) == \
        "https://www.gov.br/programa"


def test_resolve_route_rejects_bare_rec_offlist_and_unknown():
    with pytest.raises(ValueError):
        resolve_route(Route(placement="hero", kind="funnel", target="", anchor="a"),
                      domain="https://creditoup.com.br", post_type="rec")
    # Portal concorrente: reprova por falta de lastro na pesquisa desta pagina.
    with pytest.raises(ValueError):
        resolve_route(Route(placement="inline", kind="external_official",
                            target="https://portalmundomais.com/x", anchor="a"),
                      domain="https://creditoup.com.br", post_type="rec",
                      authorized_external=["https://www.gov.br/inss"])
    # Sem nenhuma evidencia (a pesquisa nao autorizou nada) tambem reprova:
    # fail-closed por ausencia de prova.
    with pytest.raises(ValueError):
        resolve_route(Route(placement="inline", kind="external_official",
                            target="https://www.gov.br/inss", anchor="a"),
                      domain="https://creditoup.com.br", post_type="rec")
    with pytest.raises(ValueError):
        resolve_route(Route(placement="inline", kind="weird", target="x", anchor="a"),
                      domain="https://creditoup.com.br", post_type="rec")


def test_verdict_blocking_default_false():
    assert Verdict().blocking is False
    assert Verdict(blocking=True).blocking is True


def test_existential_criteria_present():
    assert "compliance" in EXISTENTIAL_CRITERIA
    assert "single_destination" in EXISTENTIAL_CRITERIA
    assert "cta_discipline" in EXISTENTIAL_CRITERIA


def test_proof_and_authority_is_not_existential():
    """Cirurgico/trust-Gemini: proof_and_authority was demoted OUT of the
    fail-closed gate -- weak/thin proof is advisory feedback, never a hard
    block. Keeps the runner from getting stuck on numbers/values."""
    assert "proof_and_authority" not in EXISTENTIAL_CRITERIA


def test_stepresult_telemetry_defaults():
    r = StepResult(step="x", status=StepStatus.OK)
    assert r.prompt_tokens == 0 and r.completion_tokens == 0
    assert r.cost_usd == 0.0 and r.latency_ms == 0


def test_ad_models_defaults():
    slot = AdSlot(slot_id="lp-hero", page_role=PageRole.LP, placement="hero")
    assert slot.min_height_px == 0 and slot.refresh_eligible is False
    m = AdManifest(slots=[slot])
    assert m.vignette.max_per_window == 1 and m.vignette.window_seconds == 600


def test_index_decision_defaults():
    d = IndexDecision()
    assert d.robots == "noindex,follow" and d.canonical is None
