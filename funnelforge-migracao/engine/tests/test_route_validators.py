from funnelforge.pipeline.validators.checks import run_validators

CTX = {"domain": "https://creditoup.com.br", "post_type": "rec", "slug": "saque-fgts",
       "allowed_external": ["https://www.gov.br", "https://www.caixa.gov.br"],
       "research_hosts": ["gov.br", "caixa.gov.br"]}


def test_same_domain_rejects_foreign_host():
    txt = '<a href="https://portalmundomais.com/x">ver</a>'
    assert any(i.code == "cross_domain" for i in run_validators(["same_domain"], txt, CTX))


def test_same_domain_allows_site_and_research_host():
    txt = ('<a href="https://creditoup.com.br/rec/quem-tem-direito">a</a>'
           '<a href="https://www.gov.br/inss">b</a><a href="/rec/outra">c</a>')
    assert run_validators(["same_domain"], txt, CTX) == []


def test_same_domain_rejects_foreign_script_src():
    txt = '<script src="https://joinads.me/a.js"></script>'
    assert any(i.code == "cross_domain" for i in run_validators(["same_domain"], txt, CTX))


def test_same_domain_flags_bare_text_url():
    txt = "Para saber mais, acesse portalmundomais.com/oferta e confira as condições."
    assert any(i.code == "cross_domain" for i in run_validators(["same_domain"], txt, CTX))


def test_same_domain_flags_markdown_link():
    txt = "Veja mais detalhes em [Saiba mais](https://portalmundomais.com) sobre o tema."
    assert any(i.code == "cross_domain" for i in run_validators(["same_domain"], txt, CTX))


def test_same_domain_flags_bare_scheme_url():
    txt = "Script de terceiros carregado de https://joinads.me sem tag <script>."
    assert any(i.code == "cross_domain" for i in run_validators(["same_domain"], txt, CTX))


def test_same_domain_flags_bare_url_inside_p1_marker_block():
    txt = (
        "=== WIDGET: TEXTO ===\n"
        "Você também pode visitar portalmundomais.com para mais informações "
        "sobre o assunto.\n"
        "---\n"
        "=== WIDGET: BOTÃO ===\n"
        "Texto: Ver o passo a passo\n"
        "Link: https://creditoup.com.br/rec/saque-fgts\n"
    )
    assert any(i.code == "cross_domain" for i in run_validators(["same_domain"], txt, CTX))


def test_same_domain_allows_own_domain_prose_and_researched_link():
    txt = (
        "O creditoup.com.br é um portal informativo independente. "
        'Saiba mais nos canais oficiais em <a href="https://www.gov.br/inss">aqui</a>.'
    )
    assert run_validators(["same_domain"], txt, CTX) == []


def test_same_domain_no_false_positive_on_ordinary_prose():
    txt = ("Explicamos o passo a passo com calma, sem pressa, etc. "
           "Não há nenhum link nesta frase, apenas texto corrido normal.")
    assert run_validators(["same_domain"], txt, CTX) == []


def test_same_domain_allows_apex_prose_of_researched_www_host():
    # T0B false-positive fix: allow-listed "www.gov.br" / "www.caixa.gov.br"
    # must also cover bare apex mentions like "gov.br" / "caixa.gov.br" in
    # ordinary prose (exactly what redator_pages.jinja instructs the model
    # to write), not just the literal "www." host.
    txt = "O portal gov.br e a caixa.gov.br informam sobre o benefício."
    assert run_validators(["same_domain"], txt, CTX) == []


def test_same_domain_allows_bare_apex_path():
    txt = "Consulte o programa em gov.br/programa para mais detalhes."
    assert run_validators(["same_domain"], txt, CTX) == []


def test_same_domain_still_rejects_lookalike_apex_hosts():
    # Regression guard: apex-acceptance must NOT open the door to lookalike
    # domains that merely contain an allow-listed apex as a prefix/suffix
    # label chain -- "gov.br.evil.com" is not "gov.br", not a subdomain of
    # it, and not "www.gov.br"'s apex, so it must still be flagged.
    txt = "Cuidado com o site falso gov.br.evil.com que imita o portal oficial."
    issues = run_validators(["same_domain"], txt, CTX)
    assert any(i.code == "cross_domain" for i in issues)


def test_same_domain_still_rejects_lookalike_site_apex_host():
    # Same lookalike guard, this time targeting the site domain itself
    # (not an allow entry) -- "creditoup.com.br.evil.com" is not the site
    # and not the site's apex.
    txt = 'Phishing em <a href="https://creditoup.com.br.evil.com/fake">aqui</a>.'
    issues = run_validators(["same_domain"], txt, CTX)
    assert any(i.code == "cross_domain" for i in issues)


def test_no_bare_rec_flags_dead_rec():
    assert any(i.code == "bare_rec" for i in run_validators(
        ["no_bare_rec"], '<a href="https://creditoup.com.br/rec">morto</a>', CTX))
    assert run_validators(
        ["no_bare_rec"], '<a href="https://creditoup.com.br/rec/quem-tem-direito">v</a>',
        CTX) == []


def test_no_self_loop_flags_own_slug():
    txt = '<a href="https://creditoup.com.br/rec/saque-fgts">eu</a>'
    assert any(i.code == "self_loop" for i in run_validators(["no_self_loop"], txt, CTX))
