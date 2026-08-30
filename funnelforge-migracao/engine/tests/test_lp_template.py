import json

from funnelforge.pipeline.lp_template import (
    _drop_conflicting_global_typography,
    _fillable,
    _numbered_to_emoji,
    _strip_trailing_arrows,
    _su_accordion,
    load_lp_template,
    render_lp,
    validate_lp_content,
)

_CONTENT = {
    "hero_title": "Saque-Aniversário FGTS",
    "hero_subtitle": "Antecipação e regras em 2026",
    "article_title": "Saque-Aniversário do FGTS em 2026",
    "intro": "<p>Intro.</p>",
    "sections": [
        {"title": "O que é?", "body": "<p>a</p>"},
        {"title": "3 pontos", "body": "<p>b</p>"},
        {"title": "Quem tem direito?", "body": "<p>c</p>"},
        {"title": "Regras 2026", "body": "<p>d</p>"},
    ],
    "faq": [{"q": "Posso?", "a": "Sim."}, {"q": "Quanto?", "a": "Depende."}],
    "transition": "<p>Veja o guia completo.</p>",
    # EXATAMENTE 3: um por destino real da LP. Com presell_hubs=1 +
    # lp_direct_solutions=2 o grafo monta [hub, solução 1, solução 2], e o
    # contrato do redator passou a ser "um texto por destino" em vez de um
    # número fixo herdado do desenho de 3 hubs.
    "cta_texts": ["Como consultar »", "Ver o passo »", "Como aderir »"],
}
_HREF = "https://creditoup.com.br/rec/quem-tem-direito-antecipar-fgts-pr"


def test_render_lp_fills_slots_and_preserves_design():
    tpl = load_lp_template()
    cont, page_settings = render_lp(
        tpl, _CONTENT, funnel_hrefs=[_HREF],
        hero_image_url="https://creditoup.com.br/wp-content/uploads/hero.webp", id_seed="s1")
    blob = json.dumps(cont, ensure_ascii=False)
    # content injected
    assert "Saque-Aniversário FGTS" in blob and "Saque-Aniversário do FGTS em 2026" in blob
    assert "Quem tem direito?" in blob
    assert "[su_accordion]" in blob and "Posso?" in blob
    assert "Como consultar" in blob
    # every button points at the funnel destination (3 buttons; single href
    # supplied -> all 3 reuse it via the fallback-to-last rule)
    assert blob.count(_HREF) == 6   # 6 widgets de botão (2 heróis + corpo)
    # hero image swapped, placeholders gone
    assert "wp-content/uploads/hero.webp" in blob
    assert "{{HERO_IMAGE}}" not in blob and "{{FUNNEL_HREF}}" not in blob
    # DESIGN preserved (palette) but SOURCE content gone
    assert "#F9B200" in blob  # star-divider / button color kept
    assert "Ingreso" not in blob and "colombia.eleicoes" not in blob


def test_render_lp_regenerates_ids():
    tpl = load_lp_template()
    cont_a, _ = render_lp(tpl, _CONTENT, funnel_hrefs=[_HREF], id_seed="seedA")
    cont_b, _ = render_lp(tpl, _CONTENT, funnel_hrefs=[_HREF], id_seed="seedB")
    # original template ids are not shipped verbatim
    assert "76c54f8b" not in json.dumps(cont_a)
    # a different seed yields a different id sequence (no cross-page collision)
    assert json.dumps(cont_a) != json.dumps(cont_b)


def test_strip_trailing_arrows():
    assert _strip_trailing_arrows("Como consultar »") == "Como consultar"
    assert _strip_trailing_arrows("Ver o passo >>>") == "Ver o passo"
    assert _strip_trailing_arrows("Quero ver » ") == "Quero ver"
    assert _strip_trailing_arrows("Sem seta") == "Sem seta"
    # an internal > is not chrome and stays
    assert _strip_trailing_arrows("A > B agora") == "A > B agora"


def test_render_lp_strips_arrows_from_iconed_buttons():
    """Every LP template button already shows a right-arrow icon, so the »/>>
    the writer appends is stripped -- no button label keeps trailing arrows."""
    tpl = load_lp_template()
    cont, _ = render_lp(tpl, _CONTENT, funnel_hrefs=[_HREF], id_seed="s1")
    buttons = [w for w in _fillable(cont) if w.get("widgetType") == "button"]
    assert buttons, "expected LP buttons"
    for b in buttons:
        text = b["settings"].get("text", "")
        assert not text.rstrip().endswith(("»", ">>", ">", "›", "→")), text


def test_render_lp_subtitle_has_explicit_font_size():
    """The hero subtitle (2nd fillable heading) must carry an explicit
    typography size (it used to render at the theme default)."""
    tpl = load_lp_template()
    cont, _ = render_lp(tpl, _CONTENT, funnel_hrefs=[_HREF], id_seed="s1")
    headings = [w for w in _fillable(cont) if w.get("widgetType") == "heading"]
    subtitle = headings[1]  # index 1 == hero_subtitle per _SLOT_MAP
    s = subtitle["settings"]
    assert s.get("typography_typography") == "custom"
    assert s.get("typography_font_size", {}).get("size")


def test_drop_conflicting_global_typography():
    # a widget with BOTH a custom size and a global typography link -> link dropped
    node = {"elements": [{"widgetType": "heading", "settings": {
        "typography_font_size": {"unit": "px", "size": 18},
        "__globals__": {"typography_typography": "globals/typography?id=text"}}}]}
    _drop_conflicting_global_typography(node)
    s = node["elements"][0]["settings"]
    assert "typography_typography" not in (s.get("__globals__") or {})
    # a widget WITHOUT a custom size keeps its global link untouched
    link = {"typography_typography": "globals/typography?id=text"}
    node2 = {"widgetType": "heading", "settings": {"__globals__": dict(link)}}
    _drop_conflicting_global_typography(node2)
    assert node2["settings"]["__globals__"] == link


def test_render_lp_subtitle_size_wins_no_global_link():
    """Regression: the subtitle shipped a global typography link that beat its
    custom 18px (un-editable in Elementor). render_lp must leave no widget with
    both a custom size and a conflicting global typography link."""
    tpl = load_lp_template()
    cont, _ = render_lp(tpl, _CONTENT, funnel_hrefs=[_HREF], id_seed="s1")

    def conflicts(n: object) -> bool:
        if isinstance(n, dict):
            s = n.get("settings", {})
            g = s.get("__globals__") or {}
            if s.get("typography_font_size") and "typography_typography" in g:
                return True
            return any(conflicts(c) for c in n.get("elements", []) or [])
        if isinstance(n, list):
            return any(conflicts(x) for x in n)
        return False

    assert not conflicts(cont)


def test_lp_hero_background_is_cover_desktop_and_mobile():
    """The hero image is set as background_image_mobile, so the container needs
    an explicit cover display size on BOTH breakpoints."""
    tpl = load_lp_template()
    # o herói MOBILE é o container escondido no desktop -- localizado pela
    # propriedade, não por um id que muda a cada export do Elementor
    hero = next((n for n in _walk_containers(tpl["content"])
                 if (n.get("settings") or {}).get("hide_desktop")), None)
    assert hero is not None, "herói mobile (hide_desktop) não encontrado"
    s = hero["settings"]
    assert s.get("background_size") == "cover"
    assert s.get("background_size_mobile") == "cover"


def _walk_containers(node: object) -> list:
    out = []
    if isinstance(node, dict):
        if node.get("elType") == "container":
            out.append(node)
        for c in node.get("elements", []) or []:
            out.extend(_walk_containers(c))
    elif isinstance(node, list):
        for x in node:
            out.extend(_walk_containers(x))
    return out


def test_numbered_to_emoji():
    body = "<p>1) Um</p><p>2) Dois</p><p>3) Três</p>"
    out = _numbered_to_emoji(body)
    assert "<p>1️⃣ Um</p>" in out and "<p>2️⃣ Dois</p>" in out and "<p>3️⃣ Três</p>" in out
    assert "1)" not in out
    # no enumeration -> untouched
    assert _numbered_to_emoji("<p>Texto normal (com parênteses) 1) inline</p>") \
        == "<p>Texto normal (com parênteses) 1) inline</p>"


def test_render_lp_header_buttons_full_width_and_headings_bold():
    tpl = load_lp_template()
    cont, _ = render_lp(tpl, _CONTENT, funnel_hrefs=[_HREF], id_seed="s1")
    fill = _fillable(cont)
    buttons = [w for w in fill if w.get("widgetType") == "button"]
    # the 2 hero/header buttons are full width (Elementor Advanced > Width 100%)
    assert buttons[0]["settings"].get("_element_width") == "inherit"
    assert buttons[1]["settings"].get("_element_width") == "inherit"
    # article/section headings are bold (700); the hero title/subtitle keep theirs
    # títulos do CORPO em negrito; os 4 primeiros são os dois heróis
    headings = [w for w in fill if w.get("widgetType") == "heading"]
    for h in headings[4:]:
        assert h["settings"].get("typography_font_weight") in ("600", "700")


def test_render_lp_applies_number_emojis_to_body():
    content = dict(_CONTENT)
    content["sections"] = [
        {"title": "3 pontos", "body": "<p>1) A</p><p>2) B</p><p>3) C</p>"},
        *_CONTENT["sections"][1:],
    ]
    cont, _ = render_lp(load_lp_template(), content, funnel_hrefs=[_HREF], id_seed="s1")
    blob = json.dumps(cont, ensure_ascii=False)
    assert "1️⃣ A" in blob and "2️⃣ B" in blob and "3️⃣ C" in blob


def test_su_accordion_first_open():
    out = _su_accordion([{"q": "P1", "a": "R1"}, {"q": "P2", "a": "R2"}])
    assert out.startswith("[su_accordion]") and out.endswith("[/su_accordion]")
    assert 'title="P1" open="yes"' in out and 'title="P2" open="no"' in out


def _lp_content(**overrides):
    """A schema-complete LP content dict already compliant with the intro
    (1 paragraph) and gravata (tactile CTA invite) rules, so each test below
    can flip exactly one axis without tripping unrelated issues."""
    content = dict(_CONTENT)
    content["hero_subtitle"] = ("Antecipação e valores em 2026 -- toque abaixo e veja "
                                 "como consultar o saldo")
    content["intro"] = "<p>Dor prática factual. Promessa direta do que a página entrega.</p>"
    content.update(overrides)
    return content


def test_validate_lp_content_flags_multi_paragraph_intro():
    content = _lp_content(intro="<p>Dor prática.</p><p>Solução e fonte.</p><p>Roadmap.</p>")
    codes = {i.code for i in validate_lp_content(content)}
    assert "lp_intro_long" in codes


def test_validate_lp_content_accepts_single_paragraph_intro():
    content = _lp_content()
    codes = {i.code for i in validate_lp_content(content)}
    assert "lp_intro_long" not in codes


def test_validate_lp_content_flags_gravata_without_tactile_cta():
    content = _lp_content(hero_subtitle="Antecipação e regras em 2026")
    codes = {i.code for i in validate_lp_content(content)}
    assert "lp_gravata_no_cta" in codes


def test_validate_lp_content_accepts_gravata_with_tactile_cta():
    content = _lp_content()
    codes = {i.code for i in validate_lp_content(content)}
    assert "lp_gravata_no_cta" not in codes
    # case-insensitive
    content = _lp_content(hero_subtitle="Antecipação -- TOQUE abaixo e veja como consultar")
    codes = {i.code for i in validate_lp_content(content)}
    assert "lp_gravata_no_cta" not in codes


# ---------------------------------------------------------------------------
# Task 11 -- LP render multi-href (one destination per button) + 3 button slots.
# The honest funnel's LP offers 3 CONGRUENT CTAs, one per pre-sell angle, so the
# 3 template buttons must each carry a DISTINCT funnel href (not all the same).
# ---------------------------------------------------------------------------

_HREFS3 = [
    "https://creditoup.com.br/rec/saque-fgts-pr1",
    "https://creditoup.com.br/rec/saque-fgts-pr2",
    "https://creditoup.com.br/rec/saque-fgts-pr3",
]


def test_lp_template_has_six_button_slots_for_three_destinations():
    """Dois heróis (mobile 2 botões, desktop 3) + 1 no corpo = 6 widgets para
    3 destinos. A repetição é o preço de ter herói nos dois breakpoints."""
    tpl = load_lp_template()
    buttons = [w for w in _fillable(tpl["content"]) if w.get("widgetType") == "button"]
    assert len(buttons) == 6


def test_render_lp_applies_distinct_href_per_button():
    tpl = load_lp_template()
    cont, _ = render_lp(tpl, _CONTENT, funnel_hrefs=_HREFS3, id_seed="s1")
    buttons = [w for w in _fillable(cont) if w.get("widgetType") == "button"]
    assert len(buttons) == 6
    hrefs = [b["settings"]["link"]["url"] for b in buttons]
    a, b, c = _HREFS3
    # mobile: hub + solução 1 · desktop: hub + s1 + s2 · corpo: solução 2
    assert hrefs == [a, b, a, b, c, c]
    assert len(set(hrefs)) == 3      # os 3 destinos, todos alcançados


def test_render_lp_fewer_hrefs_falls_back_to_last():
    """When fewer hrefs than buttons are supplied, remaining buttons reuse the
    LAST href (never leave a raw {{FUNNEL_HREF}} placeholder)."""
    tpl = load_lp_template()
    cont, _ = render_lp(tpl, _CONTENT, funnel_hrefs=[_HREF], id_seed="s1")
    buttons = [w for w in _fillable(cont) if w.get("widgetType") == "button"]
    hrefs = [b["settings"]["link"]["url"] for b in buttons]
    assert hrefs == [_HREF] * 6
    assert "{{FUNNEL_HREF}}" not in json.dumps(cont)


def test_lp_tem_exatamente_um_h1_e_ele_esta_no_heroi_mobile():
    """As LPs no ar não tinham H1 NENHUM (medido em 10/08/2026 em
    /r/antecipacao-saque-aniversario-fgts e /r/emprestimo-consignado-inss-guia:
    0 h1, 4 e 2 h2). Comprava-se tráfego para uma página cujo título principal,
    para o buscador, não existia.

    Com dois heróis no DOM (o `hide_*` do Elementor é `display:none`, não
    remoção), o h1 tem de ficar em UM só. Fica no MOBILE: a indexação do Google
    é mobile-first, então é a variante que renderiza no viewport que ele usa."""
    tpl = load_lp_template()
    headings = [w for w in _fillable(tpl["content"]) if w.get("widgetType") == "heading"]
    niveis = [h["settings"].get("header_size") for h in headings]
    assert niveis.count("h1") == 1, niveis
    assert niveis[0] == "h1", "o h1 tem de ser o título do herói MOBILE"
    assert niveis[2] == "h2", "o título do herói desktop duplica o texto: nunca h1"


def test_render_lp_preenche_os_dois_herois_com_o_mesmo_titulo():
    """Os dois heróis carregam o mesmo título — é a mesma página, vista em
    telas diferentes. Se divergirem, o leitor vê promessas diferentes conforme
    o aparelho."""
    tpl = load_lp_template()
    cont, _ = render_lp(tpl, _CONTENT, funnel_hrefs=_HREFS3, id_seed="s1")
    headings = [w for w in _fillable(cont) if w.get("widgetType") == "heading"]
    assert headings[0]["settings"]["title"] == headings[2]["settings"]["title"]


def test_subtitulo_do_desktop_cai_no_comum_quando_nao_ha_variante():
    """`hero_subtitle_desktop` é opcional: sem ele, o desktop usa o subtítulo
    comum em vez de ficar vazio."""
    tpl = load_lp_template()
    cont, _ = render_lp(tpl, _CONTENT, funnel_hrefs=_HREFS3, id_seed="s1")
    headings = [w for w in _fillable(cont) if w.get("widgetType") == "heading"]
    assert headings[3]["settings"]["title"] == _CONTENT["hero_subtitle"]

    com_variante = dict(_CONTENT, hero_subtitle_desktop="Veja abaixo as opções")
    cont2, _ = render_lp(tpl, com_variante, funnel_hrefs=_HREFS3, id_seed="s1")
    h2 = [w for w in _fillable(cont2) if w.get("widgetType") == "heading"]
    assert h2[3]["settings"]["title"] == "Veja abaixo as opções"
    assert h2[1]["settings"]["title"] == _CONTENT["hero_subtitle"]   # mobile intacto


def test_validate_lp_content_exige_exatamente_tres_ctas():
    """O template tem 3 posicoes de destino (_BUTTON_HREF: 6 widgets de botao
    para 3 destinos). Com `>= 3`, um modelo que devolvia 5 CTAs passava e os
    dois excedentes sumiam sem aviso -- o fixture do smoke tinha 5, e ninguem
    nunca soube que dois nunca foram renderizados."""
    codes = {i.code for i in validate_lp_content(_lp_content(
        cta_texts=["Um »", "Dois »", "Tres »", "Quatro »", "Cinco »"]))}
    assert "lp_ctas" in codes
    codes = {i.code for i in validate_lp_content(_lp_content(
        cta_texts=["Um »", "Dois »"]))}
    assert "lp_ctas" in codes
    codes = {i.code for i in validate_lp_content(_lp_content(
        cta_texts=["Um »", "Dois »", "Tres »"]))}
    assert "lp_ctas" not in codes


def test_validate_lp_content_reprova_cta_em_primeira_pessoa_na_lp():
    """1a pessoa emocional e proibida NA LP (doctrine.banned_for_role). O
    `cta_style` aplica isso lendo blocos wp:buttons -- que a LP nao tem. A unica
    pagina onde a regra e existencial era a unica sem quem a conferisse."""
    from funnelforge.pipeline.doctrine import BANNED_CTA_FIRST_PERSON
    for frase in BANNED_CTA_FIRST_PERSON:
        content = _lp_content(cta_texts=[f"{frase.capitalize()} tenho direito? »",
                                         "Ver o passo a passo »",
                                         "Como funciona a analise »"])
        codes = {i.code for i in validate_lp_content(content)}
        assert "cta_first_person" in codes, frase
    limpo = _lp_content(cta_texts=["Ver o passo a passo »", "Como funciona »",
                                   "Ver a lista completa »"])
    assert "cta_first_person" not in {i.code for i in validate_lp_content(limpo)}
