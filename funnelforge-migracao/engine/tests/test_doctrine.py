from funnelforge.domain.models import PageRole
from funnelforge.pipeline.doctrine import (
    APPROVED_CTA_EXEMPLARS, BANNED_CTA_EXECUTION, BANNED_CTA_FIRST_PERSON,
    BANNED_FEAR, BANNED_OFFICIAL, REQUIRED_COMPLIANCE_ANCHORS,
    banned_cta_execution_hit, banned_for_role, doctrine_context,
)


def test_banned_for_role_lp_includes_first_person():
    lp = banned_for_role(PageRole.LP)
    assert "quero ver" in lp and "não perca o prazo" in lp and "agendar" in lp


def test_banned_for_role_interior_excludes_first_person():
    sol = banned_for_role(PageRole.SOLUTION)
    assert "quero ver" not in sol
    assert "liberado pelo governo" in sol and "agendar" in sol


def test_doctrine_context_keys_are_nonempty_lists():
    ctx = doctrine_context()
    for key in ("banned_fear", "banned_official", "banned_cta_first_person",
                "banned_cta_execution", "required_compliance_anchors",
                "approved_cta_exemplars"):
        assert isinstance(ctx[key], list) and ctx[key]


def test_required_and_exemplars_present():
    assert "google adsense" in REQUIRED_COMPLIANCE_ANCHORS
    assert any("passo a passo" in c.lower() for c in APPROVED_CTA_EXEMPLARS)
    assert "sistema oficial" in BANNED_OFFICIAL
    assert "não perca o prazo" in BANNED_FEAR
    assert "quero ver" in BANNED_CTA_FIRST_PERSON
    assert "agendar" in BANNED_CTA_EXECUTION


def test_banned_cta_execution_hit_is_word_boundary_anchored():
    # genuine execution verbs (incl. conjugated/imperative) are caught...
    assert banned_cta_execution_hit("Agende agora")        # stem de "agendar"
    assert banned_cta_execution_hit("Agende sua vaga")     # stem of "agendar"
    assert banned_cta_execution_hit("Emita o documento")   # stem of "emitir"
    assert banned_cta_execution_hit("Cadastre-se")         # stem of "cadastrar"
    assert banned_cta_execution_hit("consultar meu CPF")   # multi-word idiom
    # ...but a banned stem never fires MID-word (the "emit" in "demitido"):
    assert banned_cta_execution_hit("E se eu for demitido?") is None
    assert banned_cta_execution_hit("Regras de demissão") is None
    assert banned_cta_execution_hit("O que muda se te demitirem") is None
    assert banned_cta_execution_hit("") is None


def test_compliance_anchor_matches_real_aviso_copy():
    # Guards against anchors drifting from the actual accented copy in
    # redator_p1.jinja's AVISO body: "Não temos vínculo com os órgãos...".
    real_aviso = "não temos vínculo com os órgãos".lower()
    assert any(anchor.lower() in real_aviso for anchor in REQUIRED_COMPLIANCE_ANCHORS)


def test_doctrine_context_expoe_o_texto_do_aviso():
    """A frase exata do aviso estava copiada a mao em redator_pages.jinja e
    redator_presell.jinja, enquanto o enhancer que reposiciona o aviso e o guard
    de unicidade liam a constante. Bastava ajustar a redacao de um lado para o
    sistema deixar de reconhecer o aviso que o proprio redator escreveu."""
    from funnelforge.pipeline.doctrine import COMPLIANCE_NOTICE_TEXT, doctrine_context
    ctx = doctrine_context()
    assert ctx["compliance_notice_text"] == COMPLIANCE_NOTICE_TEXT
    assert isinstance(ctx["compliance_notice_text"], str) and ctx["compliance_notice_text"]


def test_prompts_nao_repetem_a_frase_do_aviso_a_mao():
    """Guarda permanente: a frase entra por interpolacao, nunca digitada."""
    from importlib import resources
    from funnelforge.pipeline.doctrine import COMPLIANCE_NOTICE_TEXT
    for nome in ("redator_pages.jinja", "redator_presell.jinja", "judge.jinja"):
        fonte = resources.files("funnelforge.prompts").joinpath(nome).read_text("utf-8")
        assert COMPLIANCE_NOTICE_TEXT not in fonte, f"{nome} repete o aviso a mao"
        assert "compliance_notice_text" in fonte, f"{nome} nao interpola o aviso"
