from funnelforge.pipeline.enhancers.gutenberg import (
    _flatten_leading_boxes,
    _split_long_paragraphs,
    _top_level_blocks,
    finalize_compliance_notice,
    normalize_gutenberg,
)


def test_strips_code_fences_and_repairs_list_items():
    raw = (
        "```html\n<!-- wp:list -->\n<ul class=\"wp-block-list\">"
        "<li>a</li></ul>\n<!-- /wp:list -->\n```"
    )
    out = normalize_gutenberg(raw)
    assert "```" not in out
    assert "<!-- wp:list-item -->" in out


def test_leaves_wp_html_blocks_untouched():
    raw = "<!-- wp:html -->\n<ul><li>keep</li></ul>\n<!-- /wp:html -->"
    out = normalize_gutenberg(raw)
    assert "<!-- wp:list-item -->" not in out


_BTN = ('<!-- wp:buttons --><div class="wp-block-buttons"><!-- wp:button -->'
        '<div class="wp-block-button"><a href="/rec/x">t</a></div>'
        '<!-- /wp:button --></div><!-- /wp:buttons -->')
_SEP = ('<!-- wp:separator {"className":"is-style-wide"} -->'
        '<hr class="wp-block-separator"/><!-- /wp:separator -->')


def test_strips_divider_wedged_between_buttons():
    raw = _BTN + _SEP + _BTN
    out = normalize_gutenberg(raw)
    assert "wp:separator" not in out
    assert out.count("wp:buttons") == 4  # both button groups survive (2 open + 2 close)


def test_keeps_separator_between_text_sections():
    raw = "<!-- wp:paragraph --><p>a</p><!-- /wp:paragraph -->" + _SEP + \
        "<!-- wp:paragraph --><p>b</p><!-- /wp:paragraph -->"
    out = normalize_gutenberg(raw)
    assert "wp:separator" in out  # a real section divider is left alone


def test_finalize_compliance_notice_moves_and_styles_aviso():
    body = ('<!-- wp:paragraph --><p>Aviso de Utilidade Pública: portal informativo '
            'independente...</p><!-- /wp:paragraph -->\n'
            '<!-- wp:heading --><h2>Conteúdo</h2><!-- /wp:heading -->')
    out = finalize_compliance_notice(body)
    # the inline (top) aviso paragraph is removed (only the canonical one remains)
    assert out.count("Utilidade Pública") == 1
    # ...and the canonical discreet footnote is the LAST block, italic + small
    assert out.rstrip().endswith("<!-- /wp:paragraph -->")
    last_para = out[out.rindex("<!-- wp:paragraph"):]
    assert "Utilidade Pública" in last_para
    assert "font-style:italic" in last_para and "12px" in last_para
    # compliance anchor still present for the validator
    assert "utilidade pública" in out.lower()


def test_finalize_compliance_notice_adds_when_missing():
    out = finalize_compliance_notice("<!-- wp:paragraph --><p>x</p><!-- /wp:paragraph -->")
    assert "utilidade pública" in out.lower()


def test_finalize_compliance_notice_removes_bare_p_aviso():
    """The writer sometimes emits the aviso as a BARE <p> (no wp:paragraph
    wrapper). It must still be removed -- no duplicate with the canonical one."""
    body = ('<!-- wp:heading --><h2>Conteúdo real</h2><!-- /wp:heading -->\n'
            '<p class="has-text-align-center"><small><em>Aviso de Utilidade Pública: '
            'portal informativo independente.</em></small></p>')
    out = finalize_compliance_notice(body)
    assert "Conteúdo real" in out
    assert out.count("Utilidade Pública") == 1
    assert out.rstrip().endswith("<!-- /wp:paragraph -->")


def test_finalize_compliance_notice_preserves_body_when_aviso_not_first():
    """Regression: the aviso can appear AFTER paragraphs of real copy. Removing
    it must NOT swallow the body between the first paragraph and the aviso."""
    p = "<!-- wp:paragraph --><p>{}</p><!-- /wp:paragraph -->"
    body = "\n".join([
        p.format("Parágrafo um do artigo, conteúdo real."),
        p.format("Parágrafo dois, mais conteúdo importante."),
        p.format("Aviso de Utilidade Pública: portal informativo."),
    ])
    out = finalize_compliance_notice(body)
    assert "Parágrafo um do artigo" in out
    assert "Parágrafo dois" in out
    assert out.count("Utilidade Pública") == 1  # only the canonical footnote remains


def test_wraps_bare_leading_strong_hook_in_paragraph():
    """The presell opening hook can arrive as a bare `<strong>...</strong>` line;
    normalize_gutenberg must wrap it in a wp:paragraph block so the /rec body
    opens on a clean first paragraph (never bare inline markup) -- keeps the Ad
    Inserter marco-zero slot and no_leading_buttons sane."""
    raw = ('<strong>Toque na opção certa e blinde seu bolso ✅</strong>\n\n'
           '<!-- wp:buttons --><div class="wp-block-buttons"></div><!-- /wp:buttons -->')
    out = normalize_gutenberg(raw)
    assert out.lstrip().startswith("<!-- wp:paragraph -->")
    assert "<strong>Toque na opção certa" in out
    # content already opening on a wp: block is left untouched
    already = '<!-- wp:heading --><h2>x</h2><!-- /wp:heading -->'
    assert normalize_gutenberg(already).lstrip().startswith("<!-- wp:heading -->")


def test_split_long_paragraphs_breaks_three_sentences_into_three_blocks():
    raw = (
        '<!-- wp:paragraph --><p>Primeira frase aqui. Segunda frase aqui. '
        'Terceira frase aqui.</p><!-- /wp:paragraph -->'
    )
    out = _split_long_paragraphs(raw)
    assert out.count("<!-- wp:paragraph -->") == 3
    assert out.count("<!-- /wp:paragraph -->") == 3
    assert "Primeira frase aqui." in out
    assert "Segunda frase aqui." in out
    assert "Terceira frase aqui." in out


def test_split_long_paragraphs_leaves_short_paragraph_intact():
    raw = '<!-- wp:paragraph --><p>Uma frase curta só.</p><!-- /wp:paragraph -->'
    out = _split_long_paragraphs(raw)
    assert out == raw


def test_split_long_paragraphs_preserves_inline_strong():
    raw = (
        '<!-- wp:paragraph --><p>Primeira frase com <strong>destaque</strong> aqui. '
        'Segunda frase aqui também. Terceira frase final aqui.</p>'
        '<!-- /wp:paragraph -->'
    )
    out = _split_long_paragraphs(raw)
    assert "<strong>destaque</strong>" in out
    assert out.count("<!-- wp:paragraph -->") == 3


def test_split_long_paragraphs_ignores_wp_html_blocks():
    raw = (
        '<!-- wp:html --><p>Frase um aqui. Frase dois aqui. Frase tres aqui.</p>'
        '<!-- /wp:html -->'
    )
    out = _split_long_paragraphs(raw)
    assert out == raw


def test_normalize_gutenberg_splits_long_paragraphs():
    raw = (
        '<!-- wp:paragraph --><p>Primeira frase aqui. Segunda frase aqui. '
        'Terceira frase aqui.</p><!-- /wp:paragraph -->'
    )
    out = normalize_gutenberg(raw)
    assert out.count("<!-- wp:paragraph -->") == 3


def test_normalize_gutenberg_splits_long_BARE_leading_intro():
    """Regression: a LONG bare leading intro (no wp:paragraph wrapper) must be
    both wrapped AND split. The split pass runs before the leading-line wrapper,
    so without splitting the freshly-wrapped block the intro shipped as one
    ~380-char wall (the exact p6 defect). The wrapper must break it too."""
    raw = (
        'Conseguir crédito rápido estando negativado costuma ser um desafio '
        'burocrático, mas a modalidade de empréstimo com garantia de celular surge '
        'como uma alternativa viável em 2026 para liberar recursos sem complicações. '
        'Este guia detalha o funcionamento dessa linha de crédito, explicando como '
        'usar o aparelho para reduzir os juros sem abrir mão do uso do smartphone.\n'
        '<!-- wp:paragraph --><p>Bloco curto seguinte.</p><!-- /wp:paragraph -->'
    )
    out = normalize_gutenberg(raw)
    # opens on a clean wp:paragraph block (wrapper still applied)
    assert out.lstrip().startswith("<!-- wp:paragraph -->")
    # and the 2-sentence intro was broken -- no paragraph over 300 chars survives
    import re as _re
    paras = [
        _re.sub(r"<[^>]+>", "", m).strip()
        for m in _re.findall(r"<p\b[^>]*>(.*?)</p>", out, _re.S | _re.I)
    ]
    assert paras and all(len(p) <= 300 for p in paras), \
        f"long bare intro not split: {[len(p) for p in paras]}"


def test_top_level_blocks_is_depth_aware():
    """A wp:group wrapping two paragraphs is ONE top-level block, not three."""
    raw = (
        '<!-- wp:paragraph --><p>Um.</p><!-- /wp:paragraph -->\n'
        '<!-- wp:group --><div class="wp-block-group">'
        '<!-- wp:paragraph --><p>Dois.</p><!-- /wp:paragraph -->'
        '<!-- wp:paragraph --><p>Tres.</p><!-- /wp:paragraph -->'
        '</div><!-- /wp:group -->'
    )
    blocks = _top_level_blocks(raw)
    names = [b[2] for b in blocks]
    assert names == ["paragraph", "group"], names


def test_flatten_leading_has_background_box_for_ad_anchor_zone():
    """COMPLIANCE/AdSense: the Ad Inserter anchors before <p> #1 and after <p>
    #3. A `wp-block-group has-background` in the opening puts an anchored <p>
    INSIDE a highlight box -> the ad renders inside a fraud-looking box (click
    inducement). normalize_gutenberg must FLATTEN leading boxes so the opening
    paragraphs are plain top-level blocks; a box further down must survive."""
    raw = (
        '<!-- wp:paragraph --><p>Intro plana um.</p><!-- /wp:paragraph -->\n'
        '<!-- wp:group {"style":{"color":{"background":"#f1f5f9"}}} -->\n'
        '<div class="wp-block-group has-background" style="background:#f1f5f9">\n'
        '<!-- wp:paragraph --><p>Dentro da caixa dois.</p><!-- /wp:paragraph -->\n'
        '<!-- wp:paragraph --><p>Dentro da caixa tres.</p><!-- /wp:paragraph -->\n'
        '</div>\n<!-- /wp:group -->\n'
        '<!-- wp:paragraph --><p>Paragrafo quatro plano.</p><!-- /wp:paragraph -->\n'
        '<!-- wp:paragraph --><p>Paragrafo cinco.</p><!-- /wp:paragraph -->\n'
        '<!-- wp:group --><div class="wp-block-group has-background">'
        '<!-- wp:paragraph --><p>Caixa legitima la embaixo.</p><!-- /wp:paragraph -->'
        '</div><!-- /wp:group -->'
    )
    out = normalize_gutenberg(raw)
    # opening (up to the 4th paragraph) has NO box wrapper
    head = out[: out.find("Paragrafo quatro")]
    assert "wp:group" not in head and "has-background" not in head, head
    # the boxed paragraphs survive as plain content
    assert "Dentro da caixa dois." in out and "Dentro da caixa tres." in out
    # the far-down legitimate box is preserved (still a group with background)
    assert "Caixa legitima la embaixo." in out
    assert "has-background" in out  # the far box kept its styling


def test_flatten_leading_boxes_noop_when_opening_is_plain():
    """No leading box -> content is unchanged by the flattener."""
    raw = (
        '<!-- wp:paragraph --><p>Um.</p><!-- /wp:paragraph -->\n'
        '<!-- wp:paragraph --><p>Dois.</p><!-- /wp:paragraph -->'
    )
    assert _flatten_leading_boxes(raw) == raw


def test_flatten_leading_boxes_never_touches_buttons():
    """Regression (v4 outage): a wp:buttons block carries `has-background` on the
    button LINK class (`wp-block-button__link has-background`) -- that is NOT a
    highlight box. The flattener is NAME-based (only group/pullquote/media-text),
    so a leading 'escolha seu caminho' button stack is left 100% untouched."""
    raw = (
        '<!-- wp:paragraph --><strong>Toque na opção certa ✅</strong><!-- /wp:paragraph -->\n'
        '<!-- wp:buttons --><div class="wp-block-buttons"><!-- wp:button -->'
        '<div class="wp-block-button"><a class="wp-block-button__link has-background '
        'wp-element-button" href="https://x/rec/a-p1">Opção A »</a></div>'
        '<!-- /wp:button --></div><!-- /wp:buttons -->'
    )
    assert _flatten_leading_boxes(raw) == raw


# ---------------------------------------------------------------------------
# MOEDA pt-BR na GERAÇÃO (Fase D, item 6 do LIVE-REMEDIATION-PLAN)
# ---------------------------------------------------------------------------


def test_moeda_malformada_e_corrigida_na_geracao():
    """`VALOR_MONETARIO_MALFORMADO`, fechado na origem.

    Os valores estão na captura preservada de `/r/fgts-saque-aniversario/`:
    "uma alíquota de 5 % a 50 % e soma uma parcela fixa de até 2900.00 R$".
    `2900.00 R$` é forma inglesa com o símbolo no fim; `5 %` tem espaço antes do
    sinal. A correção acontece na geração porque corrigir depois de publicado
    custa uma edição manual por página.
    """
    from funnelforge.pipeline.enhancers.gutenberg import formatar_moeda_ptbr

    assert formatar_moeda_ptbr("até 2900.00 R$ por mês") == "até R$ 2.900,00 por mês"
    assert formatar_moeda_ptbr("R$ 2900.00") == "R$ 2.900,00"
    assert formatar_moeda_ptbr("de 5 % a 50 %") == "de 5% a 50%"
    assert formatar_moeda_ptbr("R$ 1.234,50") == "R$ 1.234,50"     # já correto: no-op
    assert formatar_moeda_ptbr("R$ 2.900") == "R$ 2.900"           # inteiro: no-op


def test_moeda_ptbr_nao_toca_bloco_de_html_cru():
    """`wp:html` é território do widget: o normalizador não entra nele, e a
    formatação de moeda segue a mesma regra — reescrever markup executável por
    causa de um cifrão é como um widget quebra em silêncio."""
    from funnelforge.pipeline.enhancers.gutenberg import normalize_gutenberg

    bloco = ('<!-- wp:html -->\n<div>const teto = "2900.00 R$";</div>\n'
             '<!-- /wp:html -->\n'
             '<!-- wp:paragraph -->\n<p>o teto é 2900.00 R$</p>\n<!-- /wp:paragraph -->')
    out = normalize_gutenberg(bloco)
    assert 'const teto = "2900.00 R$"' in out
    assert "<p>o teto é R$ 2.900,00</p>" in out
