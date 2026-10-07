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
    assert "3 rótulos claros" in low
    assert "3 textos DISTINTOS" not in out
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


def test_redator_pages_uses_supplied_links_without_forcing_recirculation():
    routes = [{"kind": "funnel", "anchor": "Ver requisitos",
               "href": "https://site.example/rec/requisitos-pr", "reason": "Conferir elegibilidade"}]
    out = render("redator_pages", routes=routes, headline="Cursos", objective="Escolher",
                 skeleton="Etapas", keywords="curso", facts="").lower()
    assert "conferir elegibilidade" in out
    assert "https://site.example/rec/requisitos-pr" in out
    assert "sem obrigar uma" in out
    assert "só recircula" not in out


def test_presell_prioritizes_reader_intent_instead_of_rotation():
    out = render("redator_presell", headline="Cursos", objective="Escolher",
                 skeleton="Etapas", keywords="curso", facts="",
                 qualifier_lens="Onde encontrar a oferta?").lower()
    assert "onde encontrar a oferta?" in out
    assert "pode priorizar" in out
    assert "não rotacione soluções" in out
    assert "rotacionada" not in out


def test_presell_cta_describes_delivery_without_keyword_overlap_rule():
    out = render("redator_presell", headline="Cursos", objective="Escolher",
                 skeleton="Etapas", keywords="curso", facts="").lower()
    assert "a página de destino precisa entregar o prometido" in out
    assert "parágrafos curtos" in out
    assert "termo distintivo" not in out


def test_image_prompt_not_vertical_9_16():
    from funnelforge.prompts import render
    out = render("image_prompt", headline="h", objective="o")
    assert "9:16" not in out


def test_writers_keep_factual_grounding_without_authority_quotas():
    for name in ("redator_p1", "redator_presell", "redator_pages"):
        out = render(name, headline="Cursos", objective="Escolher", skeleton="Etapas",
                     keywords="curso", facts="FATOS VERIFICADOS: NENHUM.").lower()
        assert "fatos verificados" in out
        assert "na mesma frase" in out
        assert "não" in out and "memória" in out
        assert "3 a 5 órgãos" not in out
        assert "não há cota de órgãos" in out


def test_judge_accepts_relevant_multiple_destinations_for_every_role():
    for role in ("SOLUTION", "HUB", "LANDING PAGE"):
        out = render("judge", page_type=role, content="ARTIGO_UNICO", facts="",
                     domain="https://site.example").lower()
        assert "múltiplos links pertinentes são válidos" in out
        assert "não destino único" in out
        assert out.count("artigo_unico") == 1


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


def test_writers_do_not_require_a_device_specific_invitation():
    for name in ("redator_p1", "redator_presell", "redator_pages"):
        out = render(name, headline="Cursos", objective="Escolher", skeleton="Etapas",
                     keywords="curso", facts="").lower()
        assert "entrega útil" in out
        assert "cta" in out
    lp = render("redator_p1", headline="Cursos", objective="Escolher", skeleton="Etapas",
                keywords="curso", facts="").lower()
    assert 'não há palavra "toque" obrigatória' in lp


def test_redator_widget_never_uses_clique_verb():
    """CARD-0015 coverage: the same mobile-first tactile-register guard
    (CARD-0008) extended to `redator_widget` -- the 4th prompt that can name a
    physical action on a widget button/element must also say 'toque'/'tocar',
    never the desktop-mouse verb 'clique'/'clicar'."""
    out = render("redator_widget", country="Brasil", year=2026, title="Saque FGTS",
                 article="<p>corpo</p>", arquetipo="roteador", facts="").lower()
    assert "clique" not in out, "redator_widget.jinja contém 'clique'"
    assert "clicar" not in out, "redator_widget.jinja contém 'clicar'"


def test_presell_delivers_value_before_navigation_without_button_quotas():
    out = render("redator_presell", headline="Cursos", objective="Escolher",
                 skeleton="Etapas", keywords="curso", facts="").lower()
    assert "resposta útil antes" in out
    assert "não retenha uma resposta" in out
    assert "não coloque botão após todo h2 por obrigação" in out
    assert "3+3 = 6" not in out


def test_solution_puts_verified_channel_in_the_relevant_step():
    url = "https://oficial.example/catalogo"
    out = render("redator_pages", headline="Cursos", objective="Escolher", skeleton="Etapas",
                 keywords="curso", facts="", official_links=[url]).lower()
    assert url in out
    assert "ponha o hyperlink real nessa etapa" in out
    assert "parágrafos curtos" in out


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


def test_visual_presentation_depends_on_the_question_not_page_number():
    common = dict(headline="Cursos", objective="Escolher", skeleton="Etapas",
                  keywords="curso", facts="")
    first = render("redator_pages", page_num=2, **common)
    second = render("redator_pages", page_num=5, **common)
    assert first == second
    assert "tabela só para comparação real" in first
    assert "sem cotas de blocos" in first


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
