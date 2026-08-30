from funnelforge.pipeline.doctrine import doctrine_context
from funnelforge.prompts import render


def test_redator_p1_renders_with_context():
    out = render("redator_p1", headline="Saque FGTS", cta_link="/quem-tem-direito",
                 objective="o", skeleton="- H2: a", keywords="fgts", facts="{}", domain="https://creditoup.com.br")
    assert "creditoup.com.br/rec/quem-tem-direito" in out or "/rec{{" not in out
    assert "1ª pessoa" in out.lower() or "descritivo" in out.lower()  # winning CTA rule present


def test_redator_p1_pede_tres_ctas_congruentes_com_os_destinos_reais():
    """FRENTE 4: a LP tem EXATAMENTE 3 posicoes de destino no template
    Elementor, entao o schema pede 3 cta_texts. O que morreu foi a MOLDURA:
    o prompt nao fala mais em "3 HUBS QUALIFICADORES" -- um desenho que a config
    (presell_hubs=1 + lp_direct_solutions=2) nao produz. Os destinos entram por
    DADO (`lp_destinations`), com papel e H1, e cada cta_texts[i] anuncia o seu."""
    destinos = [
        {"h1": "Qual caminho serve para o seu caso", "objective": "qualificar",
         "role": "PRESELL", "role_label": "hub qualificador"},
        {"h1": "Analise sem consulta ao biro", "objective": "entender a analise",
         "role": "SOLUTION", "role_label": "pagina de solucao"},
        {"h1": "Limite garantido por deposito", "objective": "comparar",
         "role": "SOLUTION", "role_label": "pagina de solucao"},
    ]
    out = render("redator_p1", headline="Cartao para negativado", objective="o",
                 skeleton="- H2: a", keywords="k", facts="{}",
                 lp_destinations=destinos)
    low = out.lower()
    # o contrato numerico continua de pe
    assert '3 strings em "cta_texts"' in low
    assert '5 strings em "cta_texts"' not in low
    assert '"cta_texts": ["texto do cta 1' in low
    assert "cta_texts[2]" in low
    assert "3 textos" in low and "distintos" in low
    # os destinos REAIS aparecem, com o papel de cada um
    assert "qual caminho serve para o seu caso" in low
    assert "analise sem consulta ao biro" in low
    assert "limite garantido por deposito" in low
    assert "cta_texts[0]" in low and "cta_texts[1]" in low
    # a moldura obsoleta morreu: nada de contar hubs no texto do prompt
    assert "3 hubs" not in low
    assert "3 pré-sells" not in low and "3 pre-sells" not in low
    # e o subsistema de angulo continua enterrado
    assert "ângulo" not in low and "lidera" not in low


def test_redator_p1_cta_forbids_technical_jargon():
    """Task 2 (refino-copy): the LP cta_texts must be understandable by the
    general public -- technical interest-rate numbers (%, a.m., a.a.) are
    forbidden in a CTA; use curiosity/benefit in plain language instead."""
    out = render("redator_p1", headline="Saque FGTS", cta_link="/quem-tem-direito",
                 objective="o", skeleton="- H2: a", keywords="fgts", facts="{}",
                 domain="https://creditoup.com.br", author_name="Equipe",
                 author_credential="c", cnpj="00.000.000/0001-00",
                 **doctrine_context())
    low = out.lower()
    assert "cta nunca cita taxa/percentual/número técnico" in low
    assert "linguagem simples" in low
    assert "% ao mês" in low


def test_all_prompts_render():
    for name in ["extractor", "redator_p1", "redator_pages", "redator_presell",
                 "judge", "seo", "image_prompt"]:
        assert render(name, headline="h", cta_link="/x", objective="o", skeleton="s",
                      keywords="k", facts="{}", domain="https://creditoup.com.br",
                      briefing="b", content="c", tone="t", avatar="a", role="SOLUTION",
                      routes=[], author_name="Equipe", author_credential="c",
                      cnpj="00.000.000/0001-00", **doctrine_context()) != ""


def test_redator_pages_is_calm_not_legacy():
    out = render("redator_pages", role="SOLUTION", headline="Saque FGTS",
                 objective="o", skeleton="- H2: a", keywords="fgts", facts="{}",
                 domain="https://creditoup.com.br", author_name="Equipe Credito Up",
                 author_credential="Redacao", cnpj="00.000.000/0001-00",
                 routes=[{"anchor": "Ver a lista completa >>>",
                          "href": "https://creditoup.com.br/rec/saque-fgts-p2"}],
                 **doctrine_context())
    low = out.lower()
    assert "portal mundo mais" not in low            # legacy identity gone
    assert "semantic_monetization_layer" not in low  # legacy module gone
    assert "regra absoluta de primeira pessoa" not in low
    assert "7 em cada 10" not in out                 # fabricated scarcity gone
    assert "utilidade publica" in low or "utilidade pública" in low
    assert "Ver a lista completa" in out             # uses resolved route anchor
    assert "creditoup.com.br/rec/saque-fgts-p2" in out


def test_redator_pages_mid_advances_and_terminal_only_recirculates():
    """A4/A7 (forward-only routing): the miolo SOLUTION no longer meshes with
    sibling solutions -- `build_funnel_routes` now gives it exactly 1
    `funnel` (forward) edge + 1 `external_official` edge, so the writer
    prompt must say the page ADVANCES + cites the OFFICIAL channel, never the
    old sibling rodízio/mesh language. The terminal SOLUTION only recirculates
    (`cross_funnel`, no forward, no official channel). Both open the body in
    a paragraph, never a leading button (no_leading_buttons, Task 10)."""
    routes_mid = [
        {"kind": "funnel", "anchor": "Ver o guia da próxima etapa",
         "href": "https://creditoup.com.br/rec/bancos-p2"},
        {"kind": "external_official", "anchor": "Canal oficial",
         "href": "https://www.gov.br"},
    ]
    routes_terminal = [
        {"kind": "cross_funnel", "anchor": "Ver outro guia",
         "href": "https://creditoup.com.br/pis-pasep-esquecido/"},
    ]
    common = dict(role="SOLUTION", headline="h", objective="o", skeleton="s",
                  keywords="k", facts="{}", domain="https://creditoup.com.br",
                  author_name="E", author_credential="R", cnpj="00",
                  **doctrine_context())

    mid = render("redator_pages", is_terminal=False, routes=routes_mid, **common).lower()
    assert "avança" in mid and "oficial" in mid
    assert "só recircula" not in mid
    assert "rodízio" not in mid  # legacy sibling-mesh instruction is gone
    assert "a página sempre abre em texto" in mid  # opens the body in a paragraph

    terminal = render("redator_pages", is_terminal=True, routes=routes_terminal, **common).lower()
    assert "só recircula" in terminal and "cross_funnel" in terminal
    assert "a página sempre abre em texto" in terminal
    # the legacy single-destination instruction (non-SOLUTION fallback) is
    # NOT emitted for SOLUTION pages of either kind
    legacy = "o destino principal do funil (o 1º da lista acima) é o cta recorrente"
    assert legacy not in mid and legacy not in terminal


def test_redator_presell_is_neutral_hub_not_angle_biased():
    """CARD-0009 (AC3): the presell is a NEUTRAL rotating/qualifying HUB. The
    prompt no longer LEADS with any solution or carries an angle bias; instead
    `step_write` passes `qualifier_lens` + `qualifier_questions`. Proven on the
    RENDER of the template with a fake context (never on LLM output): neutral
    payoff present, no LIDERA/own-angle/lead-solution language, opens in a
    paragraph, a qualifier block is instructed, and the hrefs are used in the
    GIVEN (already-rotated) order."""
    out = render("redator_presell", role="PRESELL", headline="Ponte", objective="o",
                 skeleton="- H2: a", keywords="fgts", facts="{}",
                 domain="https://creditoup.com.br", author_name="Equipe",
                 author_credential="c", cnpj="00.000.000/0001-00",
                 qualifier_lens="qual é a sua situação hoje?",
                 qualifier_questions=[
                     {"caso": "quer consultar o saldo", "solucao": "Consulta de saldo"},
                     {"caso": "quer receber mais rápido", "solucao": "Bancos e prazos"}],
                 routes=[{"anchor": "Ver o passo a passo >>>",
                          "href": "https://creditoup.com.br/rec/saque-fgts-p1"}],
                 **doctrine_context())
    low = out.lower()
    # neutral payoff, opens in a paragraph, never a button
    assert "toque na opção certa" in low
    assert "nunca um botão primeiro" in low
    # NO angle/lead bias anywhere in the rendered prompt
    assert "lidera" not in low
    assert "ângulo próprio" not in low
    assert "solução líder" not in low
    assert "lead_solution" not in low
    # neutral qualifier lens + qualifier block instructed and rendered
    assert "qual é a sua situação hoje?" in low
    assert "bloco qualificador" in low
    # the qualifier questions (caso -> caminho) render in the GIVEN order
    assert "quer consultar o saldo" in low
    assert low.index("quer consultar o saldo") < low.index("quer receber mais rápido")
    # hrefs used in the GIVEN (already-rotated) order, never "lead first"
    assert "na ordem" in low


def test_redator_presell_cta_is_congruent_bridge_with_short_paragraphs():
    """Task 3 (refino-copy): every fan-out CTA to another track must (a)
    describe the destination (congruence) AND (b) bridge from THIS presell's
    angle -- never a CTA that ignores where the reader is standing. Short
    paragraphs (1-2 sentences) must also stay explicit in the prompt."""
    out = render("redator_presell", role="PRESELL", headline="Ponte", objective="o",
                 skeleton="- H2: a", keywords="fgts", facts="{}",
                 domain="https://creditoup.com.br", author_name="Equipe",
                 author_credential="c", cnpj="00.000.000/0001-00",
                 routes=[{"anchor": "Ver o passo a passo >>>",
                          "href": "https://creditoup.com.br/rec/saque-fgts-p1"}],
                 **doctrine_context())
    low = out.lower()
    # FIX-2 (CARD-0016): fan-out CTAs -- hero AND mid-text -- must NAME a
    # distinctive term of the destination solution, never a generic open loop.
    assert "nomear um termo distintivo da solução de destino" in low
    assert "reconhece o contexto do leitor e nomeia o destino" in low
    assert "nunca um cta solto que ignora onde o leitor está" in low
    assert "parágrafos curtos" in low


def test_image_prompt_not_vertical_9_16():
    from funnelforge.prompts import render
    out = render("image_prompt", headline="h", objective="o")
    assert "9:16" not in out


def test_redator_p1_and_pages_require_grounded_numeric_proof():
    """FIX 2 (smoke): the judge blocked a good P1 draft for citing entities
    but no number/data/source. The prompts must instruct the redator to
    ground at least one concrete figure/date/value in the research facts
    (never invented), with a qualitative-authority-fact fallback when facts
    are sparse -- without ever emitting a literal BANNED phrase (calm
    doctrine must stay intact)."""
    p1 = render("redator_p1", headline="Saque FGTS", cta_link="/quem-tem-direito",
               objective="o", skeleton="- H2: a", keywords="fgts", facts="{}",
               domain="https://creditoup.com.br", author_name="Equipe",
               author_credential="c", cnpj="00.000.000/0001-00", **doctrine_context())
    pages = render("redator_pages", role="SOLUTION", headline="Saque FGTS",
                   objective="o", skeleton="- H2: a", keywords="fgts", facts="{}",
                   domain="https://creditoup.com.br", author_name="Equipe",
                   author_credential="c", cnpj="00.000.000/0001-00",
                   routes=[{"anchor": "Ver a lista completa >>>",
                            "href": "https://creditoup.com.br/rec/saque-fgts-p2"}],
                   **doctrine_context())
    # calm-doctrine guard: the NEW grounding sentence itself must not
    # introduce a fresh literal BANNED phrase (the templates already,
    # legitimately, quote banned phrases ELSEWHERE as forbidden examples --
    # see test_doctrine_validators.py / doctrine.py -- so this checks only
    # the new sentence text, not the whole rendered prompt).
    banned = ("não perca o prazo", "muitos perdem", "quero ver",
             "será que eu", "solicitar", "agendar")
    for out in (p1, pages):
        low = out.lower()
        # O VOCABULÁRIO MUDOU, a garantia não. Antes o prompt descrevia a
        # estrutura do JSON (`fatos_verificados`, `fonte_primaria`,
        # `dados_validados`) porque o redator recebia `facts.model_dump_json()`
        # inteiro. Ele passou a receber a base já PODADA
        # (`pipeline/base_factual.py`): número não verificado não chega mais até
        # ele, e o que chega vem formatado com o link a citar.
        #
        # O que continua obrigatório é o CONTRATO, e é isso que se afirma aqui:
        assert "fatos verificados" in low            # a única origem de cifra
        assert "e de mais nada" in low               # exclusividade explícita
        assert "na mesma frase" in low               # o link junto da afirmação
        assert "não verificado — não use" in low     # o que fazer com o podado
        assert "não o reconstitua de memória" in low  # a alucinação, nomeada
        assert "sem cifra alguma" in low             # o caminho quando não há fato
        for b in banned:
            # The templates quote banned examples elsewhere; the factual
            # contract itself must not require one of them.
            assert b not in low.split("toda credibilidade precisa de prova", 1)[1].split("\n", 1)[0]


def test_judge_single_destination_is_role_aware():
    """Criterion 6 (`single_destination`) must branch on `page_type`: a
    SOLUTION page's multi-destination routing (sibling solutions + 1
    external_official + 1 cross_funnel exit, same domain) is CORRECT by the
    winning graph -- the judge prompt must say so and must NOT render the
    LP/HUB single-destination-only rule for SOLUTION. LANDING PAGE (and,
    symmetrically, HUB) must keep the single-destination rule and must NOT
    render the SOLUTION multi-destination text."""
    common = dict(content="c", domain="https://creditoup.com.br", cta_link="/x",
                  keywords="k", facts="{}")

    solution_out = render("judge", page_type="SOLUTION", **common, **doctrine_context())
    lp_out = render("judge", page_type="LANDING PAGE", **common, **doctrine_context())
    hub_out = render("judge", page_type="HUB", **common, **doctrine_context())

    # SOLUTION branch text present only for SOLUTION.
    assert "Esta é uma página SOLUTION" in solution_out
    assert "MÚLTIPLOS destinos tipados" in solution_out
    assert "NÃO penalize" in solution_out and "múltiplos destinos" in solution_out.lower()
    assert "Esta é uma página SOLUTION" not in lp_out
    assert "Esta é uma página SOLUTION" not in hub_out

    # single-destination-only rule text present for LANDING PAGE ONLY; HUB
    # (presell) now FANS OUT to the 3 solutions, SOLUTION has its own mesh.
    single_dest_rule = "TODOS os botões da página apontam para EXATAMENTE o mesmo destino"
    assert single_dest_rule in lp_out
    assert single_dest_rule not in hub_out
    assert single_dest_rule not in solution_out
    # HUB (presell) gets the fan-out branch, not single-destination.
    assert "Esta é uma página PRÉ-SELL (HUB)" in hub_out
    assert "FAN-OUT" in hub_out


def test_redator_presell_renders_calm_single_destination():
    out = render("redator_presell", role="PRESELL", headline="Ponte", objective="o",
                 skeleton="- H2: a", keywords="fgts", facts="{}",
                 domain="https://creditoup.com.br", author_name="Equipe",
                 author_credential="c", cnpj="00.000.000/0001-00",
                 routes=[{"anchor": "Ver o passo a passo >>>",
                          "href": "https://creditoup.com.br/rec/saque-fgts-p1"}],
                 **doctrine_context())
    assert "creditoup.com.br/rec/saque-fgts-p1" in out
    assert "regra absoluta de primeira pessoa" not in out.lower()


def test_redator_prompts_never_use_clique_verb():
    """CARD-0008: mobile-first tactile-register audit. Invitations that name
    the physical action on a button/element must say 'toque'/'tocar', never
    the desktop-mouse verb 'clique'/'clicar'. Permanent guard against
    regressions in the 3 redator prompts (LP, presell, interior pages)."""
    routes = [{"anchor": "Ver o passo a passo >>>",
               "href": "https://creditoup.com.br/rec/saque-fgts-p2"}]
    common = dict(headline="h", cta_link="/x", objective="o", skeleton="s",
                  keywords="k", facts="{}", domain="https://creditoup.com.br",
                  author_name="Equipe", author_credential="c",
                  cnpj="00.000.000/0001-00", routes=routes, role="SOLUTION",
                  is_terminal=False, **doctrine_context())
    for name in ("redator_p1", "redator_presell", "redator_pages"):
        out = render(name, **common).lower()
        assert "clique" not in out, f"{name}.jinja ainda contém 'clique'"
        assert "clicar" not in out, f"{name}.jinja ainda contém 'clicar'"


def test_redator_widget_never_uses_clique_verb():
    """CARD-0015 coverage: the same mobile-first tactile-register guard
    (CARD-0008) extended to `redator_widget` -- the 4th prompt that can name a
    physical action on a widget button/element must also say 'toque'/'tocar',
    never the desktop-mouse verb 'clique'/'clicar'."""
    out = render("redator_widget", country="Brasil", year=2026, title="Saque FGTS",
                 article="<p>corpo</p>", arquetipo="roteador", facts="").lower()
    assert "clique" not in out, "redator_widget.jinja contém 'clique'"
    assert "clicar" not in out, "redator_widget.jinja contém 'clicar'"


def test_redator_presell_opens_with_cta_line_then_fanout_and_ends_textual():
    """CARD-0002: the presell (-pr) must open with a bold CTA line ('Toque na
    opção certa...') immediately followed by the fan-out 'escolha seu
    caminho' block, then a max-1-paragraph intro -- and the old generic top
    button pair / end button pair are gone, so the page never closes on a
    wp:buttons block anymore (the close is textual)."""
    out = render("redator_presell", role="PRESELL", headline="Ponte", objective="o",
                 skeleton="- H2: a", keywords="fgts", facts="{}",
                 domain="https://creditoup.com.br", author_name="Equipe",
                 author_credential="c", cnpj="00.000.000/0001-00",
                 routes=[{"anchor": "Ver o passo a passo >>>",
                          "href": "https://creditoup.com.br/rec/saque-fgts-p1"}],
                 **doctrine_context())
    low = out.lower()
    # opening CTA line instruction, ahead of the fan-out choice block
    assert "toque na opção certa" in low
    assert low.index("toque na opção certa") < low.index('escolha seu caminho')
    # intro capped at 1 paragraph
    assert "máximo 1 parágrafo" in low
    # no more generic top pair / end pair of buttons
    assert "topo: 2 botões" not in low
    assert "fim: 2 botões" not in low
    # the close is textual, never a button block
    assert "nunca feche a página com um bloco de botões" in low


def test_redator_pages_delivers_real_step_by_step_with_real_links():
    """Task 4 (refino-copy): the SOLUTION page must deliver a REAL numbered
    step-by-step (not generic filler text), anchoring the resolved
    official_links inline in the exact step, with short mobile-first
    paragraphs -- never a generic/paredão paragraph."""
    out = render("redator_pages", role="SOLUTION", headline="Saque FGTS",
                 objective="o", skeleton="- H2: a", keywords="fgts", facts="{}",
                 domain="https://creditoup.com.br", author_name="Equipe",
                 author_credential="c", cnpj="00.000.000/0001-00",
                 routes=[{"kind": "external_official", "anchor": "Canal oficial",
                          "href": "https://www.gov.br"}],
                 official_links=["https://www.gov.br/fgts"],
                 **doctrine_context())
    low = out.lower()
    assert "passo a passo numerado" in low
    assert "hyperlinks reais" in low
    assert "parágrafos curtos" in low


def test_redator_p1_nao_oferece_cta_em_primeira_pessoa():
    """O prompt antigo ENSINAVA, como registro permitido, "Será que eu tenho
    direito? Quero ver" -- duas frases que sao literais de
    BANNED_CTA_FIRST_PERSON. O prompt mandava escrever o que o validador bane.
    Agora a lista aparece SO como proibicao, e o registro oferecido e o
    APPROVED_CTA_EXEMPLARS."""
    from funnelforge.pipeline.doctrine import (
        APPROVED_CTA_EXEMPLARS, BANNED_CTA_FIRST_PERSON,
    )
    out = render("redator_p1", headline="h", objective="o", skeleton="s",
                 keywords="k", facts="{}")
    low = out.lower()
    # cada frase banida aparece, e aparece DEPOIS do cabecalho de proibicao
    cabecalho = low.index("1ª pessoa emocional no botão — proibido")
    for frase in BANNED_CTA_FIRST_PERSON:
        assert frase in low, frase
        assert low.index(frase) > cabecalho, f"'{frase}' aparece fora da lista de proibicao"
    # o registro OFERECIDO e o aprovado pela doutrina
    for exemplo in APPROVED_CTA_EXEMPLARS:
        assert exemplo in out, exemplo


def test_prompts_de_redacao_nao_prescrevem_tema():
    """O prompt nao pode carregar o tema do funil anterior. O SCHEMA da LP
    mandava, literalmente, a primeira secao citar a "Caixa Econômica Federal
    (CAIXA)" -- num funil de cartao para negativado, a LP saia citando a Caixa.
    O tema entra por {{ headline }} e pela BASE FACTUAL, nunca pelo texto fixo."""
    proibidos = ("fgts", "inss", "caixa econ", "consignado", "prestamista",
                 "saque-rescis", "saque-anivers", "jeitto", "supersim",
                 "velotax", "carteira de trabalho", "ctps", "pis/cidad")
    comum = dict(headline="h", objective="o", skeleton="s", keywords="k",
                 facts="{}", domain="https://creditoup.com.br", cta_link="/x",
                 author_name="E", author_credential="c", cnpj="00.000.000/0001-00",
                 role="SOLUTION", is_terminal=False,
                 routes=[{"kind": "funnel", "anchor": "Ver o guia",
                          "href": "https://creditoup.com.br/rec/tema-p2"}],
                 official_links=["https://gov.br/tema"],
                 platform_links=[{"host": "exemplo.com.br",
                                  "url": "https://exemplo.com.br/x"}])
    for nome in ("redator_p1", "redator_presell", "redator_pages"):
        low = render(nome, **comum).lower()
        for termo in proibidos:
            assert termo not in low, f"{nome}.jinja prescreve o tema '{termo}'"
    # os prompts de imagem tambem: a hero da LP e a primeira coisa que o
    # clique pago ve, e ela vinha com CTPS e cartao da Caixa em qualquer funil
    for nome in ("image_prompt", "image_prompt_lp"):
        low = render(nome, headline="h", objective="o").lower()
        for termo in ("carteira de trabalho", "ctps", "caixa econ", "pis card",
                      "pis/cidad"):
            assert termo not in low, f"{nome}.jinja prescreve o prop '{termo}'"


def test_render_injeta_a_doutrina_mesmo_sem_o_chamador_passar():
    """A duplicacao nasceu de um esquecimento: step_write renderizava o
    redator_p1 SEM doctrine_context, e o `| default([])` do template engolia a
    falta em silencio -- o prompt seguia com as proibicoes escritas a mao. Agora
    a doutrina entra dentro de render(), para os 4 prompts que a falam, e VENCE
    o que o chamador mandar (ninguem apaga a lista por acidente)."""
    from funnelforge.pipeline.doctrine import (
        BANNED_CTA_EXECUTION, BANNED_CTA_FIRST_PERSON, BANNED_FEAR,
    )
    lp = render("redator_p1", headline="h", objective="o", skeleton="s",
                keywords="k", facts="{}")
    assert BANNED_FEAR[0] in lp
    assert BANNED_CTA_FIRST_PERSON[0] in lp
    assert BANNED_CTA_EXECUTION[0] in lp
    # nem um chamador distraido consegue esvaziar a lista
    forcado = render("redator_pages", role="SOLUTION", headline="h", objective="o",
                     skeleton="s", keywords="k", facts="{}", routes=[],
                     banned_fear=[], banned_cta_execution=[])
    assert BANNED_FEAR[0] in forcado
    assert BANNED_CTA_EXECUTION[0] in forcado


def test_judge_julga_pela_doutrina_e_nao_por_uma_copia():
    """O judge RECEBIA doctrine_context() (steps.py) e nao usava NENHUMA
    variavel: julgava por uma lista parafraseada a mao, ja mais curta que a
    real. Agora as proibicoes e o texto do aviso vem da fonte unica."""
    from funnelforge.pipeline.doctrine import (
        BANNED_CTA_FIRST_PERSON, BANNED_FEAR, BANNED_OFFICIAL,
        COMPLIANCE_NOTICE_TEXT,
    )
    comum = dict(content="c", domain="https://creditoup.com.br", cta_link="/x",
                 keywords="k", facts="{}")
    lp = render("judge", page_type="LANDING PAGE", **comum)
    for frase in BANNED_FEAR:
        assert frase in lp, frase
    for frase in BANNED_OFFICIAL:
        assert frase in lp, frase
    for frase in BANNED_CTA_FIRST_PERSON:
        assert frase in lp, frase
    assert COMPLIANCE_NOTICE_TEXT in lp
    # a proibicao de 1a pessoa e EXCLUSIVA da LP: nao vaza para o ramo interior
    sol = render("judge", page_type="SOLUTION", **comum)
    assert BANNED_CTA_FIRST_PERSON[0] not in sol
    assert BANNED_FEAR[0] in sol


def test_bloco_visual_obrigatorio_vem_da_forma_da_pergunta_nao_do_numero_da_pagina():
    """`(page_num % 3)` era sorteio: renumerar a pagina (e o step_extract
    renumera) trocava o contrato visual sem que uma virgula do conteudo mudasse
    -- e o bloco sorteado nem era um dos que o `visual_contract` fiscaliza.
    Agora o bloco-assinatura sai da FORMA DA PERGUNTA ja classificada."""
    from funnelforge.pipeline.validators.checks import SIGNATURE_BLOCK_BY_ENGAGEMENT
    comum = dict(role="SOLUTION", headline="h", objective="o", skeleton="s",
                 keywords="k", facts="{}", domain="https://creditoup.com.br",
                 author_name="E", author_credential="c", cnpj="00", routes=[])
    # mesma forma de pergunta, numeros de pagina diferentes -> MESMO bloco
    a = render("redator_pages", page_num=2, engajamento="comparativo",
               signature_block=SIGNATURE_BLOCK_BY_ENGAGEMENT["comparativo"], **comum)
    b = render("redator_pages", page_num=5, engajamento="comparativo",
               signature_block=SIGNATURE_BLOCK_BY_ENGAGEMENT["comparativo"], **comum)
    assert "TABELA COMPARATIVA (wp:table)" in a.split("BLOCO-ASSINATURA")[1][:200]
    assert "TABELA COMPARATIVA (wp:table)" in b.split("BLOCO-ASSINATURA")[1][:200]
    # forma diferente -> bloco diferente, na mesma posicao do funil
    c = render("redator_pages", page_num=2, engajamento="sequencial",
               signature_block=SIGNATURE_BLOCK_BY_ENGAGEMENT["sequencial"], **comum)
    assert "PULLQUOTE (wp:pullquote)" in c.split("BLOCO-ASSINATURA")[1][:200]
    # sem classificacao, o prompt entrega o CRITERIO -- nunca um sorteio
    d = render("redator_pages", page_num=2, **comum)
    assert "que a FORMA do conteúdo pedir" in d


def test_bloco_assinatura_nao_contradiz_o_validador_visual():
    """O bloco exigido pelo prompt tem de ser um dos que o `visual_contract`
    fiscaliza para aquela mesma forma de pergunta -- eram dois contratos
    discordando sobre a mesma pagina."""
    from funnelforge.pipeline.validators.checks import (
        SIGNATURE_BLOCK_BY_ENGAGEMENT, VISUAL_BLOCKS_BY_ENGAGEMENT,
    )
    for forma, assinatura in SIGNATURE_BLOCK_BY_ENGAGEMENT.items():
        exigidos = VISUAL_BLOCKS_BY_ENGAGEMENT.get(forma, ())
        if "pullquote" in assinatura:
            continue  # pullquote e cota de variedade do prompt, nao do validador
        assert any(bloco in assinatura for bloco in exigidos), (forma, assinatura)
