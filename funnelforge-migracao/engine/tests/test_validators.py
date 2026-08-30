from datetime import date, timedelta
from pathlib import Path

from funnelforge.domain.models import PageRole, ResearchFacts, VerifiedFact
from funnelforge.pipeline.validators.checks import (
    run_validators, same_domain, sanitize_widget_block,
)

_GOLDEN_DIR = Path(__file__).parent / "golden"


def test_language_pt_flags_spanish_and_english():
    issues = run_validators(["language_pt"], "Ingreso mínimo in 2026 ¿Cómo?", {})
    codes = {i.code for i in issues}
    assert "language_pt" in codes


def test_language_pt_passes_clean_portuguese():
    assert run_validators(["language_pt"], "Consulte seu saldo do FGTS em 2026.", {}) == []


def test_cta_style_flags_first_person_cta():
    txt = '=== WIDGET: BOTÃO ===\nTexto: Será que eu me encaixo? Quero ver\n'
    issues = run_validators(["cta_style"], txt, {"domain": "https://creditoup.com.br"})
    assert any(i.code == "cta_first_person" for i in issues)


def test_gutenberg_blocks_flags_script_and_unbalanced():
    txt = "<!-- wp:paragraph --><p>x</p><!-- /wp:paragraph --><script>bad()</script>"
    issues = run_validators(["gutenberg_blocks"], txt, {})
    assert any(i.code == "has_script" for i in issues)


def test_gutenberg_blocks_flags_unbalanced():
    txt = "<!-- wp:group --><div>x</div>"  # 1 open, 0 close
    issues = run_validators(["gutenberg_blocks"], txt, {})
    assert any(i.code == "unbalanced" for i in issues)


def test_compliance_flags_when_absent_and_passes_when_present():
    issues = run_validators(["compliance"], "texto qualquer", {})
    assert any(i.code == "no_compliance" for i in issues)
    ok = run_validators(["compliance"], "financiado por Google Adsense", {})
    assert ok == []


def test_length_p1_flags_short_text():
    assert any(i.code == "too_short" for i in run_validators(["length_p1"], "palavra " * 10, {}))
    assert run_validators(["length_p1"], "palavra " * 600, {}) == []


def test_winning_lp_flags_missing_faq_but_not_byline():
    """Byline / rodapé / nav are injected by the WordPress theme now (fixed
    footer), not the page content -- winning_lp must still flag a missing FAQ
    but must NOT flag a missing byline anymore."""
    issues = run_validators(["winning_lp"], "=== WIDGET: TEXTO ===\nsem faq", {})
    codes = {i.code for i in issues}
    assert "no_faq" in codes
    assert "no_byline" not in codes


def test_language_pt_flags_english_leak():
    issues = run_validators(["language_pt"], "veja the guide and you", {})
    assert any(i.code == "language_pt" for i in issues)


# ---------------------------------------------------------------------------
# FIX 1 (smoke): cta_style must be scoped to CTA BUTTON text only -- the
# banned execution/first-person verbs legitimately appear in body prose and
# in the mandatory compliance rodapé ("sem solicitar dados"), which must
# NOT be flagged. See `_cta_texts` in checks.py.
# ---------------------------------------------------------------------------

def test_cta_style_passes_real_smoke_p1_draft():
    """Regression for the real smoke run: a GOOD, compliant P1 draft (calm
    H1, descriptive 3rd-person CTAs, single same-domain destination) was
    WRONGLY BLOCKED because cta_style scanned the whole content -- including
    the rodapé's "sem solicitar dados" and body prose "antes de solicitar" --
    instead of only the CTA button text."""
    draft = (_GOLDEN_DIR / "smoke_p1_draft.txt").read_text(encoding="utf-8")
    issues = run_validators(["cta_style"], draft, {"role": PageRole.LP})
    codes = {i.code for i in issues}
    assert "cta_execution" not in codes
    assert "cta_first_person" not in codes
    assert issues == []


def test_cta_style_flags_execution_verb_in_conjugated_button_text():
    txt = "=== WIDGET: BOTÃO ===\nTexto: Agende agora >>>\nCor: marca\nLink: x\n"
    issues = run_validators(["cta_style"], txt, {"role": PageRole.LP})
    assert any(i.code == "cta_execution" for i in issues)


def test_cta_style_flags_first_person_button_text_on_lp():
    txt = "=== WIDGET: BOTÃO ===\nTexto: Quero ver\nCor: marca\nLink: x\n"
    issues = run_validators(["cta_style"], txt, {"role": PageRole.LP})
    assert any(i.code == "cta_first_person" for i in issues)


def test_cta_style_ignores_banned_words_outside_cta_buttons():
    """"sem solicitar dados" appears ONLY in body/compliance prose (no such
    BOTÃO) -- must NOT be flagged."""
    txt = (
        "=== WIDGET: RODAPE ===\n"
        "Sobre o Site: conteúdo informativo, sem solicitar dados pessoais, "
        "senhas ou qualquer tipo de pagamento.\n"
        "---\n"
        "=== WIDGET: TEXTO ===\n"
        "Veja o que verificar antes de solicitar a antecipação junto ao banco.\n"
    )
    assert run_validators(["cta_style"], txt, {"role": PageRole.LP}) == []


def test_cta_style_flags_execution_verb_in_html_anchor():
    # verbo que CONTINUA banido — 'solicitar' saiu da lista em 17/08/2026
    txt = '<!-- wp:buttons --><a href="https://x.com/rec/y">Agendar agora</a><!-- /wp:buttons -->'
    issues = run_validators(["cta_style"], txt, {"role": PageRole.SOLUTION})
    assert any(i.code == "cta_execution" for i in issues)


def test_interior_min_length_flags_truncated_solution():
    """A near-empty interior page (LLM truncation) must be flagged so it retries
    instead of shipping a blank /rec draft."""
    stub = ('<!-- wp:buttons --><a href="/rec/x">a</a><!-- /wp:buttons -->'
            '<p>Só isso.</p>')
    issues = run_validators(["interior_min_length"], stub, {"role": PageRole.SOLUTION})
    assert any(i.code == "body_too_short" for i in issues)
    # a full-length body passes...
    full = "<p>" + ("palavra " * 450) + "</p>"
    assert run_validators(["interior_min_length"], full, {"role": PageRole.SOLUTION}) == []
    # ...and the LP is out of scope for this interior-only guard
    assert run_validators(["interior_min_length"], stub, {"role": PageRole.LP}) == []


def test_cta_style_allows_demitido_curiosity_cta():
    """Regression: "demitido"/"demitir" contain the substring "emit" (stem of
    the banned "emitir"), but the demission vocabulary is the heart of the
    FGTS saque-rescisão funnel. A calm curiosity CTA about being fired must
    NOT be flagged as a service-execution verb (word-boundary fix)."""
    for label in ("E se eu for demitido? Como fica »",
                  "Regras de demissão e quitação »",
                  "O que muda se te demitirem »"):
        txt = f'<!-- wp:buttons --><a href="https://x.com/rec/y">{label}</a><!-- /wp:buttons -->'
        issues = run_validators(["cta_style"], txt, {"role": PageRole.SOLUTION})
        assert "cta_execution" not in {i.code for i in issues}, label


def test_gutenberg_blocks_allows_self_closing():
    """Self-closing blocks (spacer/separator/post-featured-image) take no
    close comment and must NOT read as an unbalanced open (else the richer
    /rec blocks would fail the write)."""
    content = (
        "<!-- wp:paragraph --><p>x</p><!-- /wp:paragraph -->\n"
        '<!-- wp:separator {"className":"is-style-wide"} /-->\n'
        '<!-- wp:spacer {"height":"5px"} /-->\n'
        "<!-- wp:group --><div>y</div><!-- /wp:group -->"
    )
    issues = run_validators(["gutenberg_blocks"], content, {})
    assert not any(i.code == "unbalanced" for i in issues)


def test_gutenberg_blocks_still_flags_real_imbalance():
    issues = run_validators(["gutenberg_blocks"], "<!-- wp:group --><div>y</div>", {})
    assert any(i.code == "unbalanced" for i in issues)


# ---------------------------------------------------------------------------
# CARD-0003: no_trailing_buttons -- SOLUTION/PRESELL pages must close on a
# textual transition, never on a wp:buttons block.
# ---------------------------------------------------------------------------

def _buttons_block(href="https://creditoup.com.br/rec/outro-destino-p2",
                    texto="Ver o passo seguinte »"):
    return (
        '<!-- wp:buttons --><div class="wp-block-buttons">'
        '<!-- wp:button {"width":100,"style":{"border":{"radius":"10px"},'
        '"color":{"background":"#008353"}}} -->'
        '<div class="wp-block-button has-custom-width wp-block-button__width-100">'
        f'<a class="wp-block-button__link has-background wp-element-button" href="{href}" '
        f'style="border-radius:10px;background-color:#008353"><strong>{texto}</strong></a></div>'
        '<!-- /wp:button --></div><!-- /wp:buttons -->'
    )


_NOTA_PERMANECE_BLOCK = (
    '<!-- wp:paragraph {"align":"center"} --><p class="has-text-align-center">'
    '<small><em>* Você permanece neste mesmo site *</em></small></p><!-- /wp:paragraph -->'
)

_AVISO_BLOCK = (
    '<!-- wp:paragraph {"align":"center","style":{"typography":{"fontSize":"12px"}}} -->'
    '<p class="has-text-align-center"><em>Aviso de Utilidade Pública: portal informativo '
    'independente, sem vínculo com os órgãos citados, não realizamos solicitações nem '
    'pedimos dados pessoais ou pagamentos.</em></p><!-- /wp:paragraph -->'
)


def test_no_trailing_buttons_flags_page_ending_in_button_block():
    content = (
        '<!-- wp:paragraph --><p>Texto normal da última seção do artigo.</p>'
        '<!-- /wp:paragraph -->\n'
        + _buttons_block()
    )
    issues = run_validators(["no_trailing_buttons"], content, {"role": PageRole.SOLUTION})
    assert any(i.code == "trailing_buttons" for i in issues)


def test_no_trailing_buttons_passes_when_page_ends_in_transition_paragraph():
    content = (
        _buttons_block()
        + '\n<!-- wp:paragraph --><p>Recapitulando o que foi visto, o próximo passo natural '
          'é conferir o guia completo sobre o tema.</p><!-- /wp:paragraph -->'
    )
    issues = run_validators(["no_trailing_buttons"], content, {"role": PageRole.SOLUTION})
    assert issues == []


def test_no_trailing_buttons_passes_when_buttons_followed_by_text_section():
    content = (
        _buttons_block()
        + '\n<!-- wp:heading --><h2>Mais um detalhe importante</h2><!-- /wp:heading -->'
        + '\n<!-- wp:paragraph --><p>Uma nova seção de texto explicando o assunto em mais '
          'profundidade.</p><!-- /wp:paragraph -->'
        + '\n<!-- wp:paragraph --><p>E o fecho vem aqui, como uma transição textual.</p>'
          '<!-- /wp:paragraph -->'
    )
    issues = run_validators(["no_trailing_buttons"], content, {"role": PageRole.SOLUTION})
    assert issues == []


def test_no_trailing_buttons_still_flags_when_aviso_follows_buttons():
    """The system-appended 'utilidade pública' notice is IGNORED when scanning
    for the real closing block -- buttons immediately underneath it still
    fail, they don't get a free pass just because the aviso comes after."""
    content = _buttons_block() + "\n" + _AVISO_BLOCK
    issues = run_validators(["no_trailing_buttons"], content, {"role": PageRole.SOLUTION})
    assert any(i.code == "trailing_buttons" for i in issues)


def test_no_trailing_buttons_flags_through_trailing_spacer_and_note():
    """Legacy 'FIM: 2 botões + nota' shape: buttons, then a spacer, then the
    '* Você permanece *' note -- both are decorative/ignorable, so the real
    closing block underneath is still the button stack."""
    content = (
        _buttons_block()
        + '\n<!-- wp:spacer {"height":"5px"} --><div style="height:5px" '
          'aria-hidden="true" class="wp-block-spacer"></div><!-- /wp:spacer -->'
        + "\n" + _NOTA_PERMANECE_BLOCK
    )
    issues = run_validators(["no_trailing_buttons"], content, {"role": PageRole.SOLUTION})
    assert any(i.code == "trailing_buttons" for i in issues)


def test_no_trailing_buttons_applies_to_presell_too():
    content = _buttons_block()
    issues = run_validators(["no_trailing_buttons"], content, {"role": PageRole.PRESELL})
    assert any(i.code == "trailing_buttons" for i in issues)


def test_no_trailing_buttons_skips_lp_role():
    """The LP (P1) role is out of scope for this interior-only guard."""
    content = _buttons_block()
    assert run_validators(["no_trailing_buttons"], content, {"role": PageRole.LP}) == []


# ---------------------------------------------------------------------------
# Task 10: no_leading_buttons -- SOLUTION page body (`/rec`) must never open
# on a wp:buttons block (reserves the marco-zero for the Ad Inserter ad); the
# first block underneath the WP-title H1 must be a wp:paragraph.
# ---------------------------------------------------------------------------

def test_no_leading_buttons_flags_page_starting_with_button_block():
    content = (
        _buttons_block()
        + '\n<!-- wp:heading --><h2>Como funciona</h2><!-- /wp:heading -->'
        + '\n<!-- wp:paragraph --><p>Texto explicativo do artigo.</p>'
          '<!-- /wp:paragraph -->'
    )
    issues = run_validators(["no_leading_buttons"], content, {"role": PageRole.SOLUTION})
    assert any(i.code == "leading_buttons" for i in issues)


def test_no_leading_buttons_passes_when_page_starts_with_paragraph():
    content = (
        '<!-- wp:paragraph --><p>Abertura direta do artigo.</p>'
        '<!-- /wp:paragraph -->\n'
        + '<!-- wp:heading --><h2>Como funciona</h2><!-- /wp:heading -->'
    )
    issues = run_validators(["no_leading_buttons"], content, {"role": PageRole.SOLUTION})
    assert issues == []


# ---------------------------------------------------------------------------
# CARD-0004 AC3: apex https://gov.br on allowed_external lets *.gov.br
# subdomains pass same_domain (meu.inss.gov.br, servicos.dataprev.gov.br).
# ---------------------------------------------------------------------------

_GOV_ALLOWED = ["https://gov.br", "https://www.gov.br", "https://www.caixa.gov.br"]


def test_same_domain_allows_gov_br_subdomain_via_apex():
    ctx = {"domain": "https://creditoup.com.br",
           "allowed_external": ["https://gov.br", "https://www.caixa.gov.br"],
           "research_hosts": ["gov.br", "dataprev.gov.br"]}
    ok = ('<a href="https://meu.inss.gov.br/atualizacao-cadastral">a</a>'
          '<a href="https://servicos.dataprev.gov.br/consulta">b</a>')
    assert run_validators(["same_domain"], ok, ctx) == []
    # Static preferences do not authorize anything: removing research hosts
    # rejects both URLs even if allowed_external still lists gov/caixa.
    ctx_no_apex = {**ctx, "research_hosts": []}
    assert any(i.code == "cross_domain"
               for i in run_validators(["same_domain"], ok, ctx_no_apex))


def test_same_domain_allows_verified_platform_host_fix3c():
    """FIX-3c: a commercial platform host that the research surfaced AND a
    chromium visit confirmed (ctx['verified_platforms']) is allowed for THIS
    page -- but the very same host is rejected when it was NOT verified."""
    content = ('<p>No <a href="https://www.jeitto.com.br/emprestimo" '
               'rel="nofollow sponsored">Jeitto</a> voce simula o valor.</p>')
    base = {"domain": "https://creditoup.com.br", "allowed_external": ["https://gov.br"]}
    verified = {**base, "verified_platforms": ["www.jeitto.com.br"]}
    assert run_validators(["same_domain"], content, verified) == []
    # not verified -> the commercial host is still blocked (fail-closed default)
    assert any(i.code == "cross_domain"
               for i in run_validators(["same_domain"], content, base))




# ---------------------------------------------------------------------------
# CARD-0004 AC4: official_link_density -- SOLUTION-only mode-aware minimum.
# ---------------------------------------------------------------------------

_INSS = '<a href="https://meu.inss.gov.br/atualizacao">consulta no Meu INSS</a>'
_CAIXA = '<a href="https://www.caixa.gov.br/fgts">consulta do FGTS na CAIXA</a>'
_SIBLING = '<a href="https://creditoup.com.br/rec/irma-p2">ver o guia irmão</a>'


def test_official_link_density_rich_mode_requires_two_distinct():
    """Research surfaced >=2 official deep links (ctx official_links len >= 2)
    -> the SOLUTION page must carry >=2 DISTINCT official hrefs."""
    ctx = {"role": PageRole.SOLUTION, "allowed_external": _GOV_ALLOWED,
           "official_links": ["https://meu.inss.gov.br/atualizacao",
                              "https://www.caixa.gov.br/fgts"]}
    # only one official href present -> flagged
    assert any(i.code == "official_links_few"
               for i in run_validators(["official_link_density"], _INSS + _SIBLING, ctx))
    # two distinct official hrefs -> passes
    assert run_validators(["official_link_density"], _INSS + _CAIXA + _SIBLING, ctx) == []


def test_official_link_density_rich_mode_requires_intersection_with_verified():
    """Task 8 (B4/I10): rich mode (>=2 VERIFIED deep links) hardens only when the
    body actually weaves in >=2 of THOSE verified links -- two other whitelisted
    hosts (not among official_links) no longer satisfy the minimum. The writer
    was handed the exact deep links, so it must anchor them."""
    ctx = {"role": PageRole.SOLUTION, "allowed_external": _GOV_ALLOWED,
           "official_links": ["https://meu.inss.gov.br/atualizacao",
                              "https://www.caixa.gov.br/fgts"]}
    # two whitelisted hosts, but NEITHER is one of the verified links -> flagged
    other = ('<a href="https://www.gov.br/receitafederal">Receita</a>'
             '<a href="https://outra.gov.br/servico">outro canal</a>')
    assert any(i.code == "official_links_few"
               for i in run_validators(["official_link_density"], other + _SIBLING, ctx))
    # the two VERIFIED deep links present -> passes (intersection >= 2)
    assert run_validators(["official_link_density"], _INSS + _CAIXA + _SIBLING, ctx) == []


def test_official_link_density_sparse_mode_requires_only_one():
    """No researched official URL means fail closed; one URL requires that URL."""
    sparse_ctx = {"role": PageRole.SOLUTION, "allowed_external": _GOV_ALLOWED,
                  "official_links": []}
    assert any(i.code == "official_links_few"
               for i in run_validators(["official_link_density"], _SIBLING, sparse_ctx))
    assert any(i.code == "official_links_few"
               for i in run_validators(["official_link_density"], _INSS + _SIBLING,
                                        sparse_ctx))
    # a SINGLE available official link is still sparse mode (min 1), never >=2
    single_ctx = {**sparse_ctx, "official_links": ["https://meu.inss.gov.br/atualizacao"]}
    assert run_validators(["official_link_density"], _INSS + _SIBLING, single_ctx) == []


def test_official_link_density_exempts_presell_and_lp():
    """Only SOLUTION is in scope; PRESELL/LP are exempt regardless of links."""
    ctx = {"allowed_external": _GOV_ALLOWED,
           "official_links": ["https://meu.inss.gov.br/atualizacao",
                              "https://www.caixa.gov.br/fgts"]}
    for role in (PageRole.PRESELL, PageRole.LP):
        assert run_validators(["official_link_density"], _SIBLING, {**ctx, "role": role}) == []


# ---------------------------------------------------------------------------
# CARD-0006: short_intro -- SOLUTION pages must dive into the first H2 right
# after the top CTA block; the intro may hold at most ONE real paragraph.
# ---------------------------------------------------------------------------

def _intro_p(text="Texto qualquer de introdução sobre o tema da página."):
    return f'<!-- wp:paragraph --><p>{text}</p><!-- /wp:paragraph -->'


_H2_BLOCK = '<!-- wp:heading --><h2>Primeiro passo</h2><!-- /wp:heading -->'


def test_short_intro_flags_solution_with_two_plus_intro_paragraphs():
    content = (
        _buttons_block() + _NOTA_PERMANECE_BLOCK
        + _intro_p("Primeira ideia da introdução.")
        + _intro_p("Segunda ideia que já devia estar depois do H2.")
        + _H2_BLOCK
    )
    issues = run_validators(["short_intro"], content, {"role": PageRole.SOLUTION})
    assert any(i.code == "intro_long" for i in issues)


def test_short_intro_passes_solution_with_one_intro_paragraph():
    content = (
        _buttons_block() + _NOTA_PERMANECE_BLOCK
        + _intro_p("Única ideia de introdução, direta e curta.")
        + _H2_BLOCK
    )
    assert run_validators(["short_intro"], content, {"role": PageRole.SOLUTION}) == []


def test_short_intro_passes_solution_with_zero_intro_paragraphs():
    content = _buttons_block() + _NOTA_PERMANECE_BLOCK + _H2_BLOCK
    assert run_validators(["short_intro"], content, {"role": PageRole.SOLUTION}) == []


def test_short_intro_does_not_count_nota_and_aviso_as_intro_paragraphs():
    """The nota '* Você permanece *' and an aviso placed up top (edge case,
    since the system normally moves it to the end) are NOT real intro prose:
    with both plus a single real paragraph, the count is still 1 (valid)."""
    content = (
        _buttons_block() + _NOTA_PERMANECE_BLOCK + _AVISO_BLOCK
        + _intro_p("Única ideia real de introdução.")
        + _H2_BLOCK
    )
    assert run_validators(["short_intro"], content, {"role": PageRole.SOLUTION}) == []


def test_short_intro_exempts_presell_and_lp():
    content = (
        _buttons_block() + _NOTA_PERMANECE_BLOCK
        + _intro_p("Primeiro parágrafo.") + _intro_p("Segundo parágrafo.")
        + _H2_BLOCK
    )
    for role in (PageRole.PRESELL, PageRole.LP):
        assert run_validators(["short_intro"], content, {"role": role}) == []


def test_short_intro_exempts_draft_without_any_heading():
    """A degenerate draft with no heading at all is left alone by this
    validator -- other checks (e.g. interior_min_length) already catch it."""
    content = (
        _buttons_block() + _NOTA_PERMANECE_BLOCK
        + _intro_p("Primeiro parágrafo.") + _intro_p("Segundo parágrafo.")
    )
    assert run_validators(["short_intro"], content, {"role": PageRole.SOLUTION}) == []


# ---------------------------------------------------------------------------
# CARD-0007: opening_line_unique -- the PRESELL opening CTA line must not
# repeat near-verbatim across DIFFERENT funnels/runs. The intra-run
# `uniqueness` guard can't catch this (same-run drafts only); prior lines are
# pre-loaded cross-run into ctx by steps._write_ctx from the phrase_registry.
# ---------------------------------------------------------------------------

_PRESELL_OPEN = (
    '<!-- wp:paragraph --><p><strong>Toque na opção certa e aprenda como '
    'consultar o saldo do FGTS ✅</strong></p><!-- /wp:paragraph -->'
    '<!-- wp:heading --><h2>Como funciona</h2><!-- /wp:heading -->'
)


def test_opening_line_unique_flags_near_identical_prior_line():
    ctx = {
        "role": PageRole.PRESELL,
        "prior_opening_lines": [
            "Toque na opção certa e aprenda como consultar o saldo do FGTS"],
    }
    issues = run_validators(["opening_line_unique"], _PRESELL_OPEN, ctx)
    assert any(i.code == "boilerplate_opening" for i in issues)


def test_opening_line_unique_passes_genuinely_different_line():
    ctx = {
        "role": PageRole.PRESELL,
        "prior_opening_lines": [
            "Descubra agora o passo a passo pra emitir a segunda via da conta de luz"],
    }
    assert run_validators(["opening_line_unique"], _PRESELL_OPEN, ctx) == []


def test_opening_line_unique_is_presell_only():
    prior = ["Toque na opção certa e aprenda como consultar o saldo do FGTS"]
    for role in (PageRole.LP, PageRole.SOLUTION):
        ctx = {"role": role, "prior_opening_lines": prior}
        assert run_validators(["opening_line_unique"], _PRESELL_OPEN, ctx) == []


def test_opening_line_unique_noop_without_ctx_or_empty_priors():
    assert run_validators(["opening_line_unique"], _PRESELL_OPEN, {}) == []
    empty_ctx = {"role": PageRole.PRESELL, "prior_opening_lines": []}
    assert run_validators(["opening_line_unique"], _PRESELL_OPEN, empty_ctx) == []


def test_opening_line_unique_threshold_is_configurable():
    content = '<!-- wp:paragraph --><p>aaaa bbbb cccc dddd</p><!-- /wp:paragraph -->'
    ctx = {"role": PageRole.PRESELL, "prior_opening_lines": ["aaaa bbbb eeee ffff"]}
    # shared tokens {aaaa, bbbb} over union of 6 -> jaccard 0.333...
    assert run_validators(
        ["opening_line_unique"], content, {**ctx, "opening_line_threshold": 0.3}) != []
    assert run_validators(
        ["opening_line_unique"], content, {**ctx, "opening_line_threshold": 0.5}) == []


def test_funnel_schema_coerces_string_total_pages():
    """The extractor's raw JSON sometimes quotes numbers ("total_pages": "6").
    funnel_schema must coerce, not crash on `len(pages) < "6"` (TypeError)."""
    raw = {"pages": [{}, {}], "funnel_strategy": {"total_pages": "6"}}
    issues = run_validators(["funnel_schema"], "", {"parsed": raw})
    # 2 pages < 6 planned -> a genuine shortfall is still flagged, no crash
    assert {i.code for i in issues} == {"page_count_short"}


def test_funnel_schema_ignores_non_numeric_total_pages():
    """A non-coercible total_pages (list/garbage) must degrade to 'no opinion',
    never abort the whole run with a TypeError."""
    for bad in (["a"], "abc", {"x": 1}):
        raw = {"pages": [{}, {}], "funnel_strategy": {"total_pages": bad}}
        assert run_validators(["funnel_schema"], "", {"parsed": raw}) == []


def test_forward_only_flags_backlink():
    ctx = {"slug": "a-p2", "solution_order": {"a-p1": 1, "a-p2": 2, "a-p3": 3},
           "is_terminal": False,
           "parsed": {"routes": [{"placement": "inline", "kind": "funnel",
                                   "target": "a-p1", "anchor": "x"}]}}
    assert any(i.code == "not_forward" for i in run_validators(["forward_only"], "", ctx))


def test_forward_only_passes_advance():
    ctx = {"slug": "a-p2", "solution_order": {"a-p1": 1, "a-p2": 2, "a-p3": 3},
           "is_terminal": False,
           "parsed": {"routes": [{"placement": "inline", "kind": "funnel",
                                   "target": "a-p3", "anchor": "x"}]}}
    assert run_validators(["forward_only"], "", ctx) == []  # ordinal 3 > 2 = avança


def test_forward_only_terminal_noop():
    ctx = {"slug": "a-p3", "solution_order": {"a-p1": 1, "a-p2": 2, "a-p3": 3},
           "is_terminal": True,
           "parsed": {"routes": [{"placement": "footer", "kind": "cross_funnel",
                                   "target": "https://creditoup.com.br/x", "anchor": "z"}]}}
    assert run_validators(["forward_only"], "", ctx) == []


# ---------------------------------------------------------------------------
# Final-review fixes: /rec marco-zero covers PRESELL too, and the terminal
# solution (cross-funnel only) is exempt from the official deep-link density.
# ---------------------------------------------------------------------------

def test_no_leading_buttons_covers_presell():
    """/rec = SOLUTION and PRESELL; a PRESELL opening on a wp:buttons block
    must be flagged too (the Ad Inserter marco-zero rule applies to both
    interior roles); opening on a paragraph passes."""
    lead_btn = ('<!-- wp:buttons --><div class="wp-block-buttons"></div>'
                '<!-- /wp:buttons -->\n<p>x</p>')
    assert any(i.code == "leading_buttons"
               for i in run_validators(["no_leading_buttons"], lead_btn,
                                       {"role": PageRole.PRESELL}))
    ok = '<!-- wp:paragraph --><p>Toque na opção certa ✅</p><!-- /wp:paragraph -->'
    assert run_validators(["no_leading_buttons"], ok, {"role": PageRole.PRESELL}) == []


def test_official_link_density_exempts_terminal_solution():
    """The terminal solution recirculates via cross_funnel only (no official
    link), so it is exempt from the deep-link density -- while a MID solution
    with no official link is still flagged."""
    body = "<!-- wp:paragraph --><p>corpo sem link oficial</p><!-- /wp:paragraph -->"
    base = {"role": PageRole.SOLUTION, "allowed_external": ["https://gov.br"],
            "official_links": ["https://gov.br"]}
    assert run_validators(["official_link_density"], body,
                          {**base, "is_terminal": True}) == []
    assert run_validators(["official_link_density"], body,
                          {**base, "is_terminal": False}) != []


def test_cta_style_ignores_execution_verb_in_inline_official_link():
    """Regression (real run): the required inline OFFICIAL deep link describes a
    gov.br page and its anchor text legitimately contains service words like
    'cadastro' -- it is NOT a CTA button and must not trip cta_execution (this
    false positive blocked the whole consultar-cpf SOLUTION write). Execution
    verbs INSIDE a wp:buttons block are still caught."""
    body = (
        '<!-- wp:paragraph --><p>Veja mais na '
        '<a href="https://www.gov.br/x">página de cadastro do portal Gov.br</a>.</p>'
        '<!-- /wp:paragraph -->\n'
        '<!-- wp:buttons --><div class="wp-block-buttons">'
        '<a class="wp-block-button__link" href="https://x.com/rec/y">'
        'Como conferir se é verdadeiro »</a></div><!-- /wp:buttons -->'
    )
    assert run_validators(["cta_style"], body, {"role": PageRole.SOLUTION}) == []
    btn = ('<!-- wp:buttons --><div class="wp-block-buttons">'
           '<a class="wp-block-button__link" href="https://x.com/rec/y">Agende agora »</a>'
           '</div><!-- /wp:buttons -->')
    assert any(i.code == "cta_execution"
               for i in run_validators(["cta_style"], btn, {"role": PageRole.SOLUTION}))


# ---------------------------------------------------------------------------
# CARD-0011 REQ-2: cta_destination_congruent -- the HARD GATE that makes every
# advance button tell the truth about where it goes. For each funnel button the
# LABEL and/or the bridge paragraph immediately before its block must carry a
# DISTINCTIVE token of the destination H1 (a sig token NOT shared by the sibling
# solutions), so the common funnel theme (e.g. "FGTS") can never false-pass.
# ---------------------------------------------------------------------------

# Distinctive-per-destination H1s (all share "fgts"; p2 uniquely owns
# rescisao/demissao, p3 uniquely owns aniversario/antecipado, p1 saldo/aplicativo).
_H1S = {
    "fgts-p1": "Consultar saldo FGTS pelo aplicativo",
    "fgts-p2": "Saque rescisao FGTS apos demissao",
    "fgts-p3": "Saque aniversario FGTS antecipado",
}


def _cong_ctx(**over):
    ctx = {"role": PageRole.SOLUTION, "post_type": "rec",
           "h1_by_slug": dict(_H1S), "sibling_h1s": dict(_H1S)}
    ctx.update(over)
    return ctx


def _p2_button(texto):
    return _buttons_block(href="https://creditoup.com.br/rec/fgts-p2", texto=texto)


def test_cta_destination_congruent_passes_distinctive_token_in_label():
    content = _p2_button("Ver o guia de saque-rescisao »")
    assert run_validators(["cta_destination_congruent"], content, _cong_ctx()) == []


def test_cta_destination_congruent_passes_distinctive_token_only_in_bridge():
    content = (_intro_p("O proximo guia trata da rescisao do FGTS apos a demissao.")
               + _p2_button("Toque para ver o proximo passo »"))
    assert run_validators(["cta_destination_congruent"], content, _cong_ctx()) == []


def test_cta_destination_congruent_fails_generic_open_loop_zero_overlap():
    content = _p2_button("Ver o passo que quase todo mundo pula »")
    issues = run_validators(["cta_destination_congruent"], content, _cong_ctx())
    assert any(i.code == "cta_incongruent" for i in issues)


def test_cta_destination_congruent_fails_when_label_shares_only_common_theme_token():
    # "FGTS" is shared by ALL sibling H1s -> NOT distinctive -> must not pass.
    content = _p2_button("Ver o guia de FGTS »")
    issues = run_validators(["cta_destination_congruent"], content, _cong_ctx())
    assert any(i.code == "cta_incongruent" for i in issues)


def test_cta_destination_congruent_fail_open_on_unknown_destination_h1():
    # Destination slug absent from h1_by_slug -> unknown H1 -> fail-open (never
    # block a good page for missing context; lesson from _anchor_congruent).
    content = _buttons_block(href="https://creditoup.com.br/rec/fgts-p9",
                             texto="Ver o passo seguinte »")
    assert run_validators(["cta_destination_congruent"], content, _cong_ctx()) == []


def test_cta_destination_congruent_exempts_official_and_cross_funnel():
    ctx = _cong_ctx()
    official = _buttons_block(href="https://www.gov.br/receitafederal",
                             texto="Ver o passo que todo mundo pula »")
    cross = _buttons_block(href="https://creditoup.com.br/r/emprestimo-consignado",
                          texto="Ver outro guia completo »")
    assert run_validators(["cta_destination_congruent"], official, ctx) == []
    assert run_validators(["cta_destination_congruent"], cross, ctx) == []


_H2_RESCISAO = "<!-- wp:heading --><h2>Rescisao do FGTS</h2><!-- /wp:heading -->"


def test_cta_destination_congruent_lp_exempt_and_presell_hero_exempt():
    # LP is always out of scope. A PRESELL whose only button is the hero fan-out
    # (before any H2) is exempt -- the hero is congruent via its resolved anchors
    # and an H2-less presell has no mid-text button to check.
    content = _p2_button("Ver o passo que quase todo mundo pula »")
    assert run_validators(["cta_destination_congruent"], content,
                          _cong_ctx(role=PageRole.LP)) == []
    assert run_validators(["cta_destination_congruent"], content,
                          _cong_ctx(role=PageRole.PRESELL)) == []


def test_cta_destination_congruent_presell_hero_before_h2_exempt():
    # Even when an H2 exists, a generic hero button BEFORE the first H2 is exempt.
    content = (_p2_button("Ver o passo que todo mundo pula »")
               + _H2_RESCISAO + _intro_p("Prosa do bloco."))
    assert run_validators(["cta_destination_congruent"], content,
                          _cong_ctx(role=PageRole.PRESELL)) == []


def test_cta_destination_congruent_flags_incongruent_presell_mid_button():
    # CARD-0016 FIX-2: a PRESELL mid-text button (AFTER an H2) with a generic
    # open-loop label that never names the destination is flagged, exactly like a
    # SOLUTION button -- the presell mid-text CTAs must announce their solution.
    content = _H2_RESCISAO + _p2_button("Ver o passo que quase todo mundo pula »")
    issues = run_validators(["cta_destination_congruent"], content,
                            _cong_ctx(role=PageRole.PRESELL))
    assert any(i.code == "cta_incongruent" for i in issues)


def test_cta_destination_congruent_passes_congruent_presell_mid_button():
    content = _H2_RESCISAO + _p2_button("Ver o guia de saque-rescisao apos demissao »")
    assert run_validators(["cta_destination_congruent"], content,
                          _cong_ctx(role=PageRole.PRESELL)) == []


# Regression (v4 outage): 'pix'/'clt'/'cpf' are <4 chars, so the old
# _sig_tokens dropped them -> a legit "via Pix" presell button to the PIX
# solution was false-flagged, blocking EVERY presell (fan-out reaches PIX).
# The destination SLUG segments recover 'pix' as a distinctive token.
_PIX_H1S = {
    "emprestimo-na-hora-via-pix-p1": "Empréstimo na Hora via PIX para negativados",
    "emprestimo-garantia-celular-online-p2": "Empréstimo com garantia de celular",
    "emprestimo-clt-negativado-fgts-p3": "Empréstimo CLT para negativado e FGTS",
}


def _pix_ctx():
    return {"role": PageRole.PRESELL, "post_type": "rec",
            "h1_by_slug": dict(_PIX_H1S), "sibling_h1s": dict(_PIX_H1S)}


def _pix_button(texto):
    return _buttons_block(
        href="https://creditoup.com.br/rec/emprestimo-na-hora-via-pix-p1", texto=texto)


def test_cta_destination_congruent_passes_short_pix_token_regression():
    h2 = "<!-- wp:heading --><h2>Crédito rápido</h2><!-- /wp:heading -->"
    ok = h2 + _pix_button("Preciso de dinheiro rápido via Pix »")
    assert run_validators(["cta_destination_congruent"], ok, _pix_ctx()) == []
    # a generic open-loop to the SAME pix destination is still flagged
    bad = h2 + _pix_button("Ver o passo que quase todo mundo pula »")
    assert any(i.code == "cta_incongruent"
               for i in run_validators(["cta_destination_congruent"], bad, _pix_ctx()))


def _h2_block(title):
    return f"<!-- wp:heading --><h2>{title}</h2><!-- /wp:heading -->"


def test_min_headings_requires_three_content_h2_on_solution():
    """Blindagem (p2/celular defect): a SOLUTION with <3 content H2 shipped as a
    headingless wall + the widget dumped at the tail. min_headings forces a retry
    until the article has >=3 H2 sections."""
    para = "<!-- wp:paragraph --><p>x</p><!-- /wp:paragraph -->"
    ctx = {"role": PageRole.SOLUTION}
    assert any(i.code == "too_few_headings"
               for i in run_validators(["min_headings"], para, ctx))            # 0 H2
    two = _h2_block("Um") + para + _h2_block("Dois") + para
    assert any(i.code == "too_few_headings"
               for i in run_validators(["min_headings"], two, ctx))             # 2 H2
    three = _h2_block("Um") + _h2_block("Dois") + _h2_block("Tres") + para
    assert run_validators(["min_headings"], three, ctx) == []                   # 3 H2 OK


def test_min_headings_faq_excluded_and_presell_lp_exempt():
    # a FAQ heading does NOT count toward the 3 (mirrors the widget injector)
    two_plus_faq = (_h2_block("Um") + _h2_block("Dois")
                    + _h2_block("Perguntas Frequentes"))
    assert any(i.code == "too_few_headings" for i in
               run_validators(["min_headings"], two_plus_faq, {"role": PageRole.SOLUTION}))
    # PRESELL / LP are out of scope
    assert run_validators(["min_headings"], "", {"role": PageRole.PRESELL}) == []
    assert run_validators(["min_headings"], "", {"role": PageRole.LP}) == []


def test_cta_destination_congruent_fail_open_when_siblings_share_all_tokens():
    """When the destination shares EVERY sig token with its siblings there is no
    distinctive token to demand -> fail-open, never block (the canonical
    'saque-fgts-pN' funnel, whose H1s are near-identical, must not be gated)."""
    same = {"a-p1": "Saque FGTS", "a-p2": "Saque FGTS", "a-p3": "Saque FGTS"}
    ctx = {"role": PageRole.SOLUTION, "post_type": "rec",
           "h1_by_slug": dict(same), "sibling_h1s": dict(same)}
    content = _buttons_block(href="https://creditoup.com.br/rec/a-p2",
                             texto="Ver o passo seguinte »")
    assert run_validators(["cta_destination_congruent"], content, ctx) == []


def _p3_button(texto):
    return _buttons_block(href="https://creditoup.com.br/rec/fgts-p3", texto=texto)


def test_cta_destination_congruent_fan_out_two_destinations_rejects_swap():
    """CARD-0015 end-to-end coverage: a SOLUTION draft that fans out to TWO
    destinations (CARD-0011's forward fan-out, e.g. p1 -> {p2, p3}) in a SINGLE
    piece of content. Each button's label must announce ITS OWN destination;
    swapping the two labels -- p2's button wearing p3's distinctive word and
    vice-versa -- is the original CARD-0011 bug (a button that lies about where
    it goes) and BOTH buttons must be flagged, not just one."""
    correct = (_p2_button("Ver o guia de saque-rescisao »")
               + _p3_button("Ver o guia do saque-aniversario »"))
    assert run_validators(["cta_destination_congruent"], correct, _cong_ctx()) == []

    swapped = (_p2_button("Ver o guia do saque-aniversario »")   # p3's word on p2's button
               + _p3_button("Ver o guia de saque-rescisao »"))    # p2's word on p3's button
    issues = run_validators(["cta_destination_congruent"], swapped, _cong_ctx())
    assert [i.code for i in issues] == ["cta_incongruent", "cta_incongruent"]


# ---------------------------------------------------------------------------
# CARD-0011 REQ-2: bridge_before_cta -- STRUCTURAL only. Every NON-hero
# wp:buttons block must be immediately preceded by a REAL wp:paragraph (not a
# heading, not the '* Voce permanece *' nota, not another button, not a spacer).
# The hero button (first buttons block) is exempt: its bridge is the intro.
# ---------------------------------------------------------------------------

_SPACER_BLOCK = ('<!-- wp:spacer {"height":"5px"} --><div style="height:5px" '
                 'aria-hidden="true" class="wp-block-spacer"></div><!-- /wp:spacer -->')


def test_bridge_before_cta_passes_real_paragraph_before_nonhero_button():
    content = (
        _intro_p("Introducao direta que enquadra o primeiro avanco.")
        + _buttons_block(texto="Ver o guia do saldo »")               # hero (exempt)
        + _H2_BLOCK
        + _intro_p("Ponte real que enquadra o proximo destino do funil.")
        + _buttons_block(texto="Ver o guia da rescisao »")            # non-hero, bridged
    )
    assert run_validators(["bridge_before_cta"], content, {"role": PageRole.SOLUTION}) == []


def test_bridge_before_cta_flags_heading_before_nonhero_button():
    content = (
        _intro_p("Introducao.")
        + _buttons_block(texto="hero »")
        + _H2_BLOCK                                          # heading right before...
        + _buttons_block(texto="avanco »")                  # ...this non-hero button
    )
    issues = run_validators(["bridge_before_cta"], content, {"role": PageRole.SOLUTION})
    assert any(i.code == "missing_bridge" for i in issues)


def test_bridge_before_cta_flags_nota_before_nonhero_button():
    content = (
        _intro_p("Introducao.")
        + _buttons_block(texto="hero »")
        + _NOTA_PERMANECE_BLOCK                              # the '* Voce permanece *' nota
        + _buttons_block(texto="avanco »")
    )
    issues = run_validators(["bridge_before_cta"], content, {"role": PageRole.SOLUTION})
    assert any(i.code == "missing_bridge" for i in issues)


def test_bridge_before_cta_flags_button_before_nonhero_button():
    content = (
        _intro_p("Introducao.")
        + _buttons_block(texto="hero »")
        + _buttons_block(texto="segundo colado »")          # buttons back-to-back
    )
    issues = run_validators(["bridge_before_cta"], content, {"role": PageRole.SOLUTION})
    assert any(i.code == "missing_bridge" for i in issues)


def test_bridge_before_cta_flags_spacer_before_nonhero_button():
    content = (
        _intro_p("Introducao.")
        + _buttons_block(texto="hero »")
        + _intro_p("Ponte real, mas seguida de um spacer.")
        + _SPACER_BLOCK                                     # spacer immediately before button
        + _buttons_block(texto="avanco »")
    )
    issues = run_validators(["bridge_before_cta"], content, {"role": PageRole.SOLUTION})
    assert any(i.code == "missing_bridge" for i in issues)


def test_bridge_before_cta_exempts_hero_button():
    # First buttons block preceded by a heading is fine for THIS validator: the
    # hero's bridge is the intro and it is out of scope (no_leading_buttons
    # covers opening-on-buttons separately).
    content = _H2_BLOCK + _buttons_block(texto="hero »")
    assert run_validators(["bridge_before_cta"], content, {"role": PageRole.SOLUTION}) == []


def test_bridge_before_cta_is_solution_only():
    content = (_intro_p("Intro.") + _buttons_block(texto="hero »")
               + _H2_BLOCK + _buttons_block(texto="avanco »"))
    for role in (PageRole.PRESELL, PageRole.LP):
        assert run_validators(["bridge_before_cta"], content, {"role": role}) == []


# ---------------------------------------------------------------------------
# CARD-0013: sanitize_widget_block -- the hard Python battery (allowlist +
# blockers, NO real JS parse) that decides whether a generated wp:html widget
# is injected or rejected. Pure function: `sanitize_widget_block(block) ->
# list[Issue]`. ANY issue -> the step publishes the article WITHOUT the widget.
# Each OVERRIDE-4 label gets a positive (fires) AND a negative (a clean widget
# never fires it) case; the `_VALID_WIDGET` master is the all-labels negative.
# ---------------------------------------------------------------------------

# A fully compliant widget: single wp:html block, CSS in one <style>, exactly ONE
# inline vanilla IIFE, addEventListener bound per id (never the global document
# click), no `&`, no unsafe API, only allowlisted tags/attrs.
#
# CLS ZERO: os cenários são PRÉ-RENDERIZADOS e EMPILHADOS na mesma célula do
# grid (`grid-area:1 / 1`), e a troca é `style.visibility` -- nunca
# `style.display`, que tiraria o bloco do fluxo e empurraria o anúncio abaixo.
# O container tem sempre a altura do maior cenário, então a interação do leitor
# não move um pixel da página.
_VALID_WIDGET = (
    "<!-- wp:html -->\n"
    '<div id="wg-elig" class="wg-card">\n'
    "<style>.wg-card{background:#ffffff;border:1px solid #e2e8f0;border-radius:16px;"
    "padding:24px;margin:32px 0}.wg-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}"
    "@media (max-width:600px){.wg-grid{grid-template-columns:1fr}}"
    ".wg-out{display:grid}.wg-out > .wg-cen{grid-area:1 / 1;visibility:hidden}</style>\n"
    '<div class="wg-grid">\n'
    '<label for="wg-idade">Idade</label>\n'
    '<input id="wg-idade" type="number" placeholder="Ex.: 40">\n'
    '<label for="wg-tempo">Tempo de contribuicao</label>\n'
    '<input id="wg-tempo" type="number" placeholder="Ex.: 15">\n'
    "</div>\n"
    '<button id="wg-btn" type="button">Ver resultado indicativo</button>\n'
    '<div class="wg-out" aria-live="polite">\n'
    '<section id="wg-ok" class="wg-cen"><div><strong>Resultado indicativo:</strong> '
    "confira os demais requisitos no canal oficial.</div></section>\n"
    '<section id="wg-no" class="wg-cen"><div>Resultado indicativo: verifique os demais '
    "requisitos no canal oficial.</div></section>\n"
    "</div>\n"
    "<script>\n"
    "(function(){\n"
    "var b=document.getElementById('wg-btn');\n"
    "if(b){b.addEventListener('click',function(){\n"
    "var idade=document.getElementById('wg-idade');\n"
    "var ok=document.getElementById('wg-ok');\n"
    "var no=document.getElementById('wg-no');\n"
    "var v=idade?parseInt(idade.value,10):0;\n"
    "window.dataLayer=window.dataLayer||[];\n"
    "window.dataLayer.push({event:'wg', arq:'roteador', passo:1});\n"
    "if(v>=60){if(ok){ok.style.visibility='visible';}if(no){no.style.visibility='hidden';}}"
    "else{if(no){no.style.visibility='visible';}if(ok){ok.style.visibility='hidden';}}\n"
    "});}\n"
    "})();\n"
    "</script>\n"
    "</div>\n"
    "<!-- /wp:html -->"
)


def _codes(block: str) -> set[str]:
    return {i.code for i in sanitize_widget_block(block)}


def _swap_script(new_script: str) -> str:
    """`_VALID_WIDGET` with its inline <script>...</script> body replaced -- used
    to isolate the JS-body checks (ampersand / unsafe API / storage / dynamic
    HTML / global click) with everything else held valid."""
    import re
    return re.sub(r"<script>.*?</script>",
                  "<script>\n" + new_script + "\n</script>", _VALID_WIDGET, flags=re.S)


def test_sanitize_valid_widget_passes_clean():
    """The master negative: a fully compliant widget raises ZERO issues (so the
    step would inject it). If this ever fails, every per-label negative is moot."""
    assert sanitize_widget_block(_VALID_WIDGET) == []


def test_sanitize_flags_iframe_as_unsafe_external_code():
    bad = _VALID_WIDGET.replace(
        '<div class="wg-grid">',
        '<div class="wg-grid"><iframe src="https://x.com"></iframe>', 1)
    assert "unsafe_external_code" in _codes(bad)


def test_sanitize_flags_javascript_uri_as_unsafe_external_code():
    bad = _VALID_WIDGET.replace(
        '<button id="wg-btn" type="button">Ver resultado indicativo</button>',
        '<button id="wg-btn" type="button" data-x="javascript:void(0)">Ver</button>', 1)
    assert "unsafe_external_code" in _codes(bad)


def test_sanitize_flags_inline_event_handler():
    bad = _VALID_WIDGET.replace(
        '<button id="wg-btn" type="button">',
        '<button id="wg-btn" type="button" onclick="go()">', 1)
    assert "inline_event_handler" in _codes(bad)
    assert "inline_event_handler" not in _codes(_VALID_WIDGET)  # negative


def test_sanitize_flags_form_not_allowed():
    bad = _VALID_WIDGET.replace('<div class="wg-grid">',
                                '<form><div class="wg-grid">', 1).replace(
        "</div>\n<button", "</div></form>\n<button", 1)
    assert "form_not_allowed" in _codes(bad)
    assert "form_not_allowed" not in _codes(_VALID_WIDGET)  # negative


def test_sanitize_flags_missing_inline_script():
    import re
    bad = re.sub(r"<script>.*?</script>", "", _VALID_WIDGET, flags=re.S)
    assert "missing_inline_script" in _codes(bad)


def test_sanitize_flags_multiple_scripts():
    bad = _VALID_WIDGET.replace("</div>\n<!-- /wp:html -->",
                                "<script>var x=1;</script></div>\n<!-- /wp:html -->", 1)
    assert "multiple_scripts" in _codes(bad)


def test_sanitize_flags_external_script():
    bad = _swap_script("").replace(
        "<script>\n\n</script>", '<script src="https://cdn.x/app.js"></script>', 1)
    codes = _codes(bad)
    assert "external_script" in codes
    # a src-less inline script never trips external_script
    assert "external_script" not in _codes(_VALID_WIDGET)


def test_sanitize_flags_ampersand_in_script_all_forms():
    # raw `&&`, a bare `&`, and the three HTML-entity encodings WP would mangle
    for js in ("if(a && b){}", "var x = a & b;", "if(a &amp;&amp; b){}",
               "var y = 1 &#38; 2;", "var z = 3 &#x26; 4;"):
        assert "ampersand_in_script" in _codes(_swap_script(js)), js
    # the valid widget (nested ifs, no &) never trips it
    assert "ampersand_in_script" not in _codes(_VALID_WIDGET)


def test_sanitize_flags_unsafe_js_api():
    for js in ("fetch('/x');", "new XMLHttpRequest();", "var w=new WebSocket('x');",
               "eval('1');", "alert('x');", "prompt('x');", "confirm('x');",
               "var f=new Function('return 1');"):
        assert "unsafe_js_api" in _codes(_swap_script(js)), js
    # look-alikes in the valid widget (parseInt/getElementById/function()) do NOT fire
    assert "unsafe_js_api" not in _codes(_VALID_WIDGET)


def test_sanitize_flags_storage_or_cookie():
    for js in ("localStorage.setItem('a','b');", "sessionStorage.getItem('a');",
               "document.cookie='a=b';"):
        assert "storage_or_cookie_not_allowed" in _codes(_swap_script(js)), js
    assert "storage_or_cookie_not_allowed" not in _codes(_VALID_WIDGET)


def test_sanitize_flags_dynamic_html():
    for js in ("el.innerHTML='x';", "el.outerHTML='x';", "el.insertAdjacentHTML('x','y');",
               "document.write('x');", "var n=document.createElement('div');"):
        assert "dynamic_html_not_allowed" in _codes(_swap_script(js)), js
    assert "dynamic_html_not_allowed" not in _codes(_VALID_WIDGET)


def test_sanitize_flags_global_click_listener():
    bad = _swap_script("document.addEventListener('click',function(){});")
    assert "global_click_listener_not_allowed" in _codes(bad)
    # per-element addEventListener('click') in the valid widget is fine
    assert "global_click_listener_not_allowed" not in _codes(_VALID_WIDGET)


def test_sanitize_flags_disallowed_tag():
    bad = _VALID_WIDGET.replace(
        '<button id="wg-btn" type="button">Ver resultado indicativo</button>',
        '<a href="https://x.com">ir</a>'
        '<button id="wg-btn" type="button">Ver resultado indicativo</button>', 1)
    assert "tag_not_allowed" in _codes(bad)
    assert "tag_not_allowed" not in _codes(_VALID_WIDGET)  # negative


def test_sanitize_flags_disallowed_attribute():
    bad = _VALID_WIDGET.replace(
        '<input id="wg-idade" type="number" placeholder="Ex.: 40">',
        '<input id="wg-idade" type="number" name="cpf" placeholder="Ex.: 40">', 1)
    assert "attribute_not_allowed" in _codes(bad)
    assert "attribute_not_allowed" not in _codes(_VALID_WIDGET)  # negative


def test_sanitize_flags_unbalanced_html():
    bad = _VALID_WIDGET.replace("</div>\n<!-- /wp:html -->", "\n<!-- /wp:html -->", 1)
    assert "unbalanced_html" in _codes(bad)
    assert "unbalanced_html" not in _codes(_VALID_WIDGET)  # negative


def test_sanitize_any_issue_means_reject():
    """The step's contract: a non-empty issue list == reject (publish without the
    widget). A clean widget returns [] == inject."""
    assert sanitize_widget_block(_VALID_WIDGET) == []
    assert sanitize_widget_block(
        _VALID_WIDGET.replace("<button", "<marquee></marquee><button", 1)) != []


# ---------------------------------------------------------------------------
# CARD-0013 isolation regression: widgets carry a SANITIZED <script> through the
# separate wp:html path, but the ARTICLE BODY itself must still never contain a
# raw <script> -- the write-time gutenberg_blocks/has_script gate stays intact.
# ---------------------------------------------------------------------------

def test_has_script_regression_article_body_script_still_forbidden():
    body = ('<!-- wp:paragraph --><p>corpo do artigo</p><!-- /wp:paragraph -->'
            "<script>alert(1)</script>")
    assert any(i.code == "has_script"
               for i in run_validators(["gutenberg_blocks"], body, {}))
    clean = '<!-- wp:paragraph --><p>corpo do artigo</p><!-- /wp:paragraph -->'
    assert not any(i.code == "has_script"
                   for i in run_validators(["gutenberg_blocks"], clean, {}))


# ===========================================================================
# CLS ZERO POR CONSTRUÇÃO
#
# Alternar cenário com `style.display` tira o bloco do fluxo e muda a altura do
# container. Com 15 unidades de anúncio na página, cada interação empurra o
# anúncio para baixo -- layout shift E viewability perdida, e é o leitor
# ENGAJADO (o que mais interage) quem mais sofre.
#
# Os dois lados do invariante são exigidos: `grid-area` no markup (os cenários
# ocupam a mesma célula, então o container tem sempre a altura do maior) e
# `visibility` no script (não reflui). Um sem o outro não entrega nada.
# ===========================================================================


def test_display_toggle_e_rejeitado_por_causar_cls() -> None:
    ruim = _VALID_WIDGET.replace("ok.style.visibility='visible'",
                                 "ok.style.display='block'")
    codes = {i.code for i in sanitize_widget_block(ruim)}
    assert "display_toggle_causes_cls" in codes


def test_sem_grid_area_e_rejeitado() -> None:
    ruim = _VALID_WIDGET.replace("grid-area:1 / 1;", "")
    codes = {i.code for i in sanitize_widget_block(ruim)}
    assert "missing_grid_stack" in codes


def test_o_widget_valido_empilha_e_alterna_visibility() -> None:
    """O fixture-mestre é a especificação executável do padrão novo."""
    assert "grid-area:1 / 1" in _VALID_WIDGET
    assert ".style.visibility=" in _VALID_WIDGET
    assert ".style.display=" not in _VALID_WIDGET
    assert not sanitize_widget_block(_VALID_WIDGET)


def test_datalayer_push_e_permitido() -> None:
    """A medição não pode ser barrada pelas regras de segurança: `push` num
    array não é rede, não é storage, não monta HTML e não tem `&`."""
    assert "dataLayer.push" in _VALID_WIDGET
    assert not sanitize_widget_block(_VALID_WIDGET)


# ===========================================================================
# AUTORIZAÇÃO DE LINK EXTERNO VEM DA BUSCA, NÃO DE UMA LISTA
#
# A allowlist estática travava a operação sem proteger: bloqueava o canal
# oficial de que a página precisava (picpay.com numa página sobre milhas,
# shopee.com.br numa sobre entregador) e deixava passar o que entrava pela
# prosa. Agora: o que a pesquisa daquela página trouxe é autorizado.
#
# A trava que FICA é a que importa -- o modelo não inventa URL.
# ===========================================================================

def _pagina(host: str) -> str:
    return f'<p>Veja no canal oficial: <a href="https://{host}/ajuda">site</a>.</p>'


def _ctx(research: list[str] | None = None) -> dict:
    return {"domain": "https://creditoup.com.br",
            "allowed_external": [],            # sem lista nenhuma
            "research_hosts": research or []}


def test_host_que_a_busca_trouxe_e_autorizado() -> None:
    """O caso PicPay: ninguém cadastrou o domínio, a busca achou."""
    assert same_domain(_pagina("picpay.com"), _ctx(["picpay.com"])) == []
    assert same_domain(_pagina("shopee.com.br"), _ctx(["shopee.com.br"])) == []


def test_host_que_a_busca_nao_trouxe_e_recusado() -> None:
    """A trava que sobra: URL inventada pelo modelo não passa."""
    issues = same_domain(_pagina("emprestimo-aprovado-rapido.com"), _ctx(["picpay.com"]))
    assert [i.code for i in issues] == ["cross_domain"]


def test_sem_pesquisa_nenhum_host_externo_passa() -> None:
    """Pesquisa vazia -> nada externo. Fail-closed, sem lista de resgate."""
    assert same_domain(_pagina("picpay.com"), _ctx([]))


def test_o_proprio_dominio_sempre_passa() -> None:
    conteudo = '<a href="https://creditoup.com.br/rec/outra-p2">interlink</a>'
    assert same_domain(conteudo, _ctx([])) == []


def test_www_nao_atrapalha() -> None:
    """A busca costuma devolver com e sem `www`; os dois têm de casar."""
    assert same_domain(_pagina("www.picpay.com"), _ctx(["picpay.com"])) == []
    assert same_domain(_pagina("picpay.com"), _ctx(["www.picpay.com"])) == []


# ===========================================================================
# CONTRATOS FACTUAIS, CTA/DESTINO, RAW HTML, ANÚNCIO E VOCABULÁRIO VISUAL
# ===========================================================================

def _fact(*, source: str = "https://www.gov.br/fato",
          value: str = "R$ 500,00") -> VerifiedFact:
    return VerifiedFact(
        valor=value, unidade="reais", fonte_primaria=source,
        dispositivo="não se aplica", vigente_desde=date.today() - timedelta(days=30),
        verificado_em=date.today(),
    )


def test_sparse_research_is_a_hard_source_failure() -> None:
    facts = ResearchFacts(sparse=True, fontes=[])
    issues = run_validators(["has_sources"], "", {"parsed": facts})
    assert {i.code for i in issues} == {"no_sources"}


def test_verified_fact_requires_fresh_listed_primary_source() -> None:
    source = "https://www.gov.br/fato"
    stale = _fact(source=source).model_copy(
        update={"verificado_em": date.today() - timedelta(days=90)})
    facts = ResearchFacts(fontes=[source], fatos_verificados=[stale])
    issues = run_validators(["research_facts_contract"], "", {
        "parsed": facts, "today": date.today(), "max_age_days": 45})
    assert "stale_fact" in {i.code for i in issues}


def test_cta_that_promises_external_action_but_links_internal_is_rejected() -> None:
    body = ('<!-- wp:buttons --><div class="wp-block-buttons"><a '
            'href="https://creditoup.com.br/rec/modalidade-p2">'
            'Consultar modalidade no App FGTS</a></div><!-- /wp:buttons -->')
    issues = run_validators(["cta_style"], body, {
        "role": PageRole.SOLUTION, "domain": "https://creditoup.com.br"})
    assert "cta_destination_mismatch" in {i.code for i in issues}


def test_curiosity_cta_about_external_action_can_link_internal() -> None:
    body = ('<!-- wp:buttons --><div class="wp-block-buttons"><a '
            'href="https://creditoup.com.br/rec/modalidade-p2">'
            'Ver como consultar no App FGTS</a></div><!-- /wp:buttons -->')
    assert run_validators(["cta_style"], body, {
        "role": PageRole.SOLUTION, "domain": "https://creditoup.com.br"}) == []


def test_raw_html_rejects_paragraph_even_with_attributes_and_whitespace() -> None:
    body = '<!-- wp:html --><div><p class="erro"> </p></div><!-- /wp:html -->'
    issues = run_validators(["raw_html_contract"], body, {})
    assert "paragraph_in_raw_html" in {i.code for i in issues}


def test_adjacent_groups_need_explicit_margin() -> None:
    body = ('<!-- wp:group {} --><div></div><!-- /wp:group -->'
            '<!-- wp:group {} --><div></div><!-- /wp:group -->')
    codes = {i.code for i in run_validators(["raw_html_contract"], body, {})}
    assert "adjacent_groups_without_margin" in codes


def test_outline_and_consecutive_button_groups_are_not_publishable() -> None:
    body = ('<!-- wp:buttons --><div class="is-style-outline"></div><!-- /wp:buttons -->'
            '<!-- wp:buttons --><div></div><!-- /wp:buttons -->')
    codes = {i.code for i in run_validators(["raw_html_contract"], body, {})}
    assert {"outline_button", "adjacent_button_groups"} <= codes


def test_critical_claim_requires_resolved_typed_fact_and_citation() -> None:
    source = "https://www.gov.br/fato"
    body = '<p>O limite informado é R$ 500,00.</p>'
    untrusted = ResearchFacts(fontes=[source], fatos_verificados=[_fact(source=source)])
    issues = run_validators(["critical_fact_grounding"], body, {"facts": untrusted})
    assert "ungrounded_critical_claim" in {i.code for i in issues}

    trusted = untrusted.model_copy(update={"fontes_resolvidas": [source]})
    cited = f'<p>O limite informado é R$ 500,00. <a href="{source}">Fonte</a>.</p>'
    assert run_validators(["critical_fact_grounding"], cited, {"facts": trusted}) == []


def test_legal_force_without_resolved_device_is_rejected() -> None:
    body = "<p>O trabalhador tem direito ao saque nesta situação.</p>"
    issues = run_validators(["critical_fact_grounding"], body,
                            {"facts": ResearchFacts(fontes=[])})
    assert "ungrounded_legal_claim" in {i.code for i in issues}


def test_legal_force_with_resolved_device_and_citation_passes() -> None:
    source = "https://www.gov.br/lei-fgts"
    fact = VerifiedFact(
        valor="O trabalhador tem direito ao saque nesta situação",
        unidade="regra", fonte_primaria=source, dispositivo="Lei 8.036/1990",
        vigente_desde=date.today() - timedelta(days=30), verificado_em=date.today())
    facts = ResearchFacts(fontes=[source], fontes_resolvidas=[source],
                          fatos_verificados=[fact])
    body = (f'<p>O trabalhador tem direito ao saque nesta situação. '
            f'<a href="{source}">Fonte</a>.</p>')
    assert run_validators(["critical_fact_grounding"], body, {"facts": facts}) == []


def test_directional_copy_outside_widget_is_ad_unsafe() -> None:
    body = ('<!-- wp:paragraph --><p>Responda abaixo para ver o resultado.</p>'
            '<!-- /wp:paragraph -->')
    issues = run_validators(["ad_interaction"], body, {"ad_paragraph_anchors": [1, 3]})
    assert "directional_copy_outside_widget" in {i.code for i in issues}


def test_visual_contract_maps_comparison_to_native_blocks() -> None:
    ctx = {"role": PageRole.SOLUTION, "engajamento": "comparativo"}
    incomplete = '<!-- wp:details --><details></details><!-- /wp:details -->'
    codes = {i.code for i in run_validators(["visual_contract"], incomplete, ctx)}
    assert codes == {"missing_semantic_block"}
    complete = (incomplete + '<!-- wp:table --><figure></figure><!-- /wp:table -->'
                '<!-- wp:columns --><div></div><!-- /wp:columns -->')
    assert run_validators(["visual_contract"], complete, ctx) == []


def test_porcentagem_colada_na_tabela_ancora_no_fato_tipado() -> None:
    """⚠️ O ESPAÇO ANTES DO `%` CONDENAVA A PÁGINA COMPARATIVA INTEIRA.

    `VerifiedFact` guarda valor e unidade SEPARADOS, e o portão monta a agulha
    com `" ".join((valor, unidade, dispositivo))` — vira `"0,57 % ..."`. O texto
    escreve das duas formas: `<a>0,57 %</a>` na prosa e `<td>0,57%</td>` na
    tabela. Antes do conserto, o mesmo número, ancorado no MESMO fato, recebia
    dois vereditos por causa de um espaço.

    Medido em 18/08/2026, run `maquininha-de-cartao-...-112043`, página 4: nove
    `ungrounded_critical_claim`, todos porcentagem, todos com fato tipado e
    fonte resolvida. Nove dos dez fatos daquela página tinham `unidade="%"` — e
    uma página comparativa é feita de tabela, então ela condenava a si mesma.
    """
    source = "https://www.ton.com.br"
    fato = VerifiedFact(
        valor="0,57", unidade="%", fonte_primaria=source,
        dispositivo="Regulamento do Plano Ton Mega+",
        vigente_desde=date.today() - timedelta(days=19), verificado_em=date.today())
    facts = ResearchFacts(fontes=[source], fontes_resolvidas=[source],
                          fatos_verificados=[fato])

    # Colado, como sai numa célula de tabela.
    tabela = (f'<table><tr><td>Ton (Plano Mega+)</td><td>0,57%</td></tr></table>'
              f'<p><a href="{source}">Fonte</a></p>')
    assert run_validators(["critical_fact_grounding"], tabela, {"facts": facts}) == []

    # Com espaço, como sai na prosa. Os dois têm de valer igual.
    prosa = f'<p>A taxa é de <a href="{source}">0,57 %</a>.</p>'
    assert run_validators(["critical_fact_grounding"], prosa, {"facts": facts}) == []


def test_porcentagem_sem_fato_continua_reprovando() -> None:
    """O conserto do espaço NÃO pode ter afrouxado o portão.

    Um número que não está em `fatos_verificados` segue reprovando — é a metade
    da mudança que importa, porque a outra metade destrava página.
    """
    source = "https://www.ton.com.br"
    fato = VerifiedFact(
        valor="0,57", unidade="%", fonte_primaria=source,
        dispositivo="Regulamento do Plano Ton Mega+",
        vigente_desde=date.today() - timedelta(days=19), verificado_em=date.today())
    facts = ResearchFacts(fontes=[source], fontes_resolvidas=[source],
                          fatos_verificados=[fato])

    inventado = (f'<table><tr><td>Outra</td><td>9,99%</td></tr></table>'
                 f'<p><a href="{source}">Fonte</a></p>')
    codes = {i.code for i in run_validators(["critical_fact_grounding"], inventado,
                                            {"facts": facts})}
    assert "ungrounded_critical_claim" in codes


def test_unidade_por_extenso_e_ponto_decimal_ainda_ancoram() -> None:
    """⚠️ A MESMA GRANDEZA, DUAS GRAFIAS, NO MESMO RUN.

    Medido em 18/08/2026, run `maquininha-de-cartao-...-112043`: a página 4
    gravou `valor="0,57"` `unidade="%"`; a página 6 gravou `valor="0.57"`
    `unidade="Percentual (%)"`. A agulha antiga era
    `" ".join((valor, unidade, dispositivo))` procurada por substring, então
    nenhuma das duas casava com o `0,57%`/`0.57%` do texto — e as duas páginas
    caíam por escolha de redação do próprio motor.
    """
    source = "https://www.ton.com.br"
    fato = VerifiedFact(
        valor="0.57", unidade="Percentual (%)", fonte_primaria=source,
        dispositivo="Tabela de taxas", vigente_desde=date.today() - timedelta(days=5),
        verificado_em=date.today())
    facts = ResearchFacts(fontes=[source], fontes_resolvidas=[source],
                          fatos_verificados=[fato])

    for grafia in ("0.57%", "0,57%", "0.57 %"):
        corpo = f'<p>A taxa é de {grafia}. <a href="{source}">Fonte</a>.</p>'
        assert run_validators(["critical_fact_grounding"], corpo, {"facts": facts}) == [], \
            f"grafia {grafia!r} deixou de ancorar"


def test_quantia_por_prefixo_nao_ancora_mais() -> None:
    """⚠️ O CASAMENTO POR SUBSTRING APROVAVA NÚMERO ERRADO.

    `"r$ 500" in "r$ 5000,00 reais ..."` é True: um fato de cinco mil ancorava
    uma afirmação de quinhentos. Comparar número canonizado fecha o buraco — a
    mudança é mais permissiva com GRAFIA e mais estrita com VALOR.
    """
    source = "https://www.gov.br/fato"
    fato = VerifiedFact(
        valor="R$ 5000,00", unidade="reais", fonte_primaria=source,
        dispositivo="não se aplica", vigente_desde=date.today() - timedelta(days=30),
        verificado_em=date.today())
    facts = ResearchFacts(fontes=[source], fontes_resolvidas=[source],
                          fatos_verificados=[fato])

    corpo = f'<p>O limite é de R$ 500,00. <a href="{source}">Fonte</a>.</p>'
    codes = {i.code for i in run_validators(["critical_fact_grounding"], corpo,
                                            {"facts": facts})}
    assert "ungrounded_critical_claim" in codes


def test_separador_de_milhar_nao_vira_decimal() -> None:
    """Em pt-BR `1.000` é mil e `1,000` é um.

    Trocar `.` por `,` às cegas faria um fato de "1,000" ancorar uma afirmação
    de "1.000" — errando por mil vezes numa página que fala de dinheiro.
    """
    source = "https://www.gov.br/fato"
    fato = VerifiedFact(
        valor="1,000", unidade="reais", fonte_primaria=source,
        dispositivo="não se aplica", vigente_desde=date.today() - timedelta(days=30),
        verificado_em=date.today())
    facts = ResearchFacts(fontes=[source], fontes_resolvidas=[source],
                          fatos_verificados=[fato])

    corpo = f'<p>São R$ 1.000 no total. <a href="{source}">Fonte</a>.</p>'
    codes = {i.code for i in run_validators(["critical_fact_grounding"], corpo,
                                            {"facts": facts})}
    assert "ungrounded_critical_claim" in codes


def test_unidade_incompativel_nao_ancora() -> None:
    """Número certo, grandeza errada: 0,57% não se ancora num fato em reais."""
    source = "https://www.ton.com.br"
    fato = VerifiedFact(
        valor="0,57", unidade="Reais (BRL)", fonte_primaria=source,
        dispositivo="Tabela", vigente_desde=date.today() - timedelta(days=5),
        verificado_em=date.today())
    facts = ResearchFacts(fontes=[source], fontes_resolvidas=[source],
                          fatos_verificados=[fato])

    corpo = f'<p>A taxa é de 0,57%. <a href="{source}">Fonte</a>.</p>'
    codes = {i.code for i in run_validators(["critical_fact_grounding"], corpo,
                                            {"facts": facts})}
    assert "ungrounded_critical_claim" in codes
