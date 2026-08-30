import pytest

from funnelforge.config.settings import load_settings
from funnelforge.domain.models import PageRole, PageTypeSpec, Route
from funnelforge.pipeline.pagespec import enforce_pagespec, pagespec_for

LP_SPEC = PageTypeSpec(role=PageRole.LP, allowed_targets=["funnel"],
    required_targets=["funnel"],
    forbidden_targets=["self","bare_rec","external_official","cross_funnel"],
    cta_min=5, cta_max=8, distinct_targets=False, anchor_congruent=True)

def _lp_routes(n, target="fgts-pr"):
    return [Route(placement="inline", kind="funnel", target=target,
                  anchor="Ver o passo a passo do saque >>>") for _ in range(n)]

def test_lp_ok_single_destination():
    issues = enforce_pagespec(_lp_routes(5), LP_SPEC, slug="fgts",
                              h1_by_slug={"fgts-pr": "Saque do FGTS: passo a passo"})
    assert issues == []

def test_lp_too_few_ctas():
    codes = {i.code for i in enforce_pagespec(_lp_routes(3), LP_SPEC, slug="fgts", h1_by_slug={})}
    assert "cta_too_few" in codes

def test_lp_flags_second_destination():
    routes = _lp_routes(4) + [Route(placement="footer", kind="funnel", target="outra", anchor="x")]
    codes = {i.code for i in enforce_pagespec(routes, LP_SPEC, slug="fgts", h1_by_slug={})}
    assert "not_single_destination" in codes

def test_lp_flags_self_loop_and_forbidden_kind():
    routes = _lp_routes(5) + [
        Route(placement="footer", kind="funnel", target="fgts", anchor="y"),
        Route(placement="footer", kind="external_official", target="https://gov.br", anchor="z")]
    codes = {i.code for i in enforce_pagespec(routes, LP_SPEC, slug="fgts", h1_by_slug={})}
    assert "self_loop" in codes and "target_not_allowed" in codes

def test_solution_requires_external_and_cross_and_distinct():
    spec = PageTypeSpec(role=PageRole.SOLUTION,
        allowed_targets=["funnel","external_official","cross_funnel"],
        required_targets=["external_official","cross_funnel"],
        forbidden_targets=["self","bare_rec"],
        cta_min=2, cta_max=5, distinct_targets=True, anchor_congruent=True)
    routes = [Route(placement="inline", kind="funnel", target="fgts-p2",
                    anchor="Ver o guia do saldo >>>"),
              Route(placement="inline", kind="funnel", target="fgts-p2", anchor="dup")]
    codes = {i.code for i in enforce_pagespec(routes, spec, slug="fgts-p1",
             h1_by_slug={"fgts-p2":"Saldo do FGTS"})}
    assert "target_missing" in codes and "targets_not_distinct" in codes

def test_anchor_incongruent_flagged():
    issues = enforce_pagespec(
        [Route(placement="hero", kind="funnel", target="fgts-pr", anchor="clique aqui")]*5,
        LP_SPEC, slug="fgts", h1_by_slug={"fgts-pr":"Antecipacao do Saque Aniversario"})
    assert any(i.code == "anchor_incongruent" for i in issues)


# ---------------------------------------------------------------------------
# CARD-0015: the REAL production LP contract (Section-2 briefing invariant +
# test_routing.py's _settings()) is cta_min=cta_max=3, distinct_targets=True --
# distinct from the generic LP_SPEC (5/8) exercised above. Pinning the actual
# numbers here means a config regression away from "exactly 3 distinct" is
# caught, not just the generic too-few/not-distinct mechanism.
# ---------------------------------------------------------------------------
_REAL_LP_SPEC = PageTypeSpec(role=PageRole.LP, allowed_targets=["funnel"],
    required_targets=["funnel"],
    forbidden_targets=["self", "bare_rec", "external_official", "cross_funnel"],
    cta_min=3, cta_max=3, distinct_targets=True, anchor_congruent=True)


def _distinct_routes(*targets):
    return [Route(placement="inline", kind="funnel", target=t, anchor=f"Ver o guia {t} >>>")
            for t in targets]


def test_lp_real_contract_exactly_three_distinct_ctas_required():
    three = _distinct_routes("fgts-pr1", "fgts-pr2", "fgts-pr3")
    assert enforce_pagespec(three, _REAL_LP_SPEC, slug="fgts", h1_by_slug={}) == []

    two_codes = {i.code for i in
                 enforce_pagespec(three[:2], _REAL_LP_SPEC, slug="fgts", h1_by_slug={})}
    assert "cta_too_few" in two_codes

    four = three + _distinct_routes("fgts-pr4")
    four_codes = {i.code for i in
                  enforce_pagespec(four, _REAL_LP_SPEC, slug="fgts", h1_by_slug={})}
    assert "cta_too_many" in four_codes

    duplicate = three[:2] + [three[0]]
    dup_codes = {i.code for i in
                 enforce_pagespec(duplicate, _REAL_LP_SPEC, slug="fgts", h1_by_slug={})}
    assert "targets_not_distinct" in dup_codes


@pytest.fixture
def settings(config_files):
    # config_files (conftest.py) fixture provides .env + config.yaml; the
    # honest-graph routing keys (SOLUTION miolo vs SOLUTION_TERMINAL) are
    # applied here so this test doesn't depend on other tasks' migration of
    # the shared fixture's routing block.
    s = load_settings(config_files / ".env", config_files / "config.yaml")
    s.routing["SOLUTION"] = s.routing["SOLUTION"].model_copy(update={
        "allowed_targets": ["funnel", "external_official"],
        "required_targets": ["funnel", "external_official"],
        "forbidden_targets": ["self", "bare_rec", "cross_funnel"],
        "cta_min": 1, "cta_max": 1, "distinct_targets": True,
    })
    s.routing["SOLUTION_TERMINAL"] = s.routing["SOLUTION"].model_copy(update={
        "allowed_targets": ["cross_funnel"],
        "required_targets": ["cross_funnel"],
        "forbidden_targets": ["self", "funnel", "external_official", "bare_rec"],
        "cta_min": 1, "cta_max": 1, "distinct_targets": False,
    })
    return s


def test_pagespec_terminal_key(settings):  # settings da fixture config_files
    mid = pagespec_for(settings, PageRole.SOLUTION)
    term = pagespec_for(settings, PageRole.SOLUTION, terminal=True)
    assert "cross_funnel" in term.required_targets       # terminal EXIGE cross
    assert "cross_funnel" not in term.forbidden_targets  # ...logo não o proíbe
    assert "funnel" in term.forbidden_targets            # terminal proíbe forward
    assert "cross_funnel" in mid.forbidden_targets       # miolo proíbe cross
    assert "external_official" in mid.required_targets
