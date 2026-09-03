from __future__ import annotations

import re

from funnelforge.pipeline.doctrine import COMPLIANCE_NOTICE_TEXT

_FENCE = "```"

# ⚠️ MESMO FURO DO `raw_html_contract`: o comentário de bloco aceita ATRIBUTOS
# (`<!-- wp:html {"lock":{"move":false}} -->`) e a versão antiga desta regex
# exigia o comentário SECO. Resultado: um widget declarado com atributos NÃO era
# reconhecido como HTML cru, e o normalizador entrava nele -- reescrevendo <li>
# como blocos `wp:list-item` e quebrando os <p> internos do widget. O comentário
# "never touch raw html" abaixo dizia a verdade só para metade dos blocos.
_RAW_HTML_BLOCK = (
    r"<!--\s*wp:html(?![\w-])(?:(?!-->)[\s\S])*?-->"
    r"[\s\S]*?"
    r"<!--\s*/wp:html\s*-->"
)
_RAW_HTML_OPEN_RE = re.compile(r"\A<!--\s*wp:html(?![\w-])", re.I)

# A wp:separator (divider) block, opener..closer.
_SEP_BLOCK = r"<!--\s*wp:separator\b[^>]*-->[\s\S]*?<!--\s*/wp:separator\s*-->"


def _strip_separators_around_buttons(content: str) -> str:
    """Drop a wp:separator wedged next to a wp:buttons group. The writer
    sometimes emits "button, divider, buttons" at the end of the article, which
    reads as a rendering bug -- a horizontal rule slicing through the CTA stack.
    Separators BETWEEN prose sections are left untouched."""
    content = re.sub(r"(<!--\s*/wp:buttons\s*-->)\s*" + _SEP_BLOCK, r"\1", content, flags=re.I)
    content = re.sub(_SEP_BLOCK + r"\s*(<!--\s*wp:buttons\b)", r"\1", content, flags=re.I)
    return content


# Canonical compliance footnote: identical text (keeps the `compliance`
# validator's "utilidade pública" anchor), but discreet -- centered, 12px,
# italic, muted -- and always at the END, not a body-font banner up top.
_AVISO_TEXT = COMPLIANCE_NOTICE_TEXT
_AVISO_BLOCK = (
    '<!-- wp:paragraph {"align":"center","style":{"typography":{"fontSize":"12px",'
    '"fontStyle":"italic"},"color":{"text":"#94a3b8"},"spacing":{"margin":{"top":"28px"}}}} -->\n'
    '<p class="has-text-align-center" style="color:#94a3b8;margin-top:28px;font-size:12px;'
    'font-style:italic"><em>' + _AVISO_TEXT + "</em></p>\n"
    "<!-- /wp:paragraph -->"
)
# ONE paragraph block (leaf: no nested paragraph close inside it).
_PARA_BLOCK_RE = re.compile(
    r"<!--\s*wp:paragraph\b[^>]*-->[\s\S]*?<!--\s*/wp:paragraph\s*-->", re.I
)
# A bare <p>...</p> leaf (the writer sometimes emits the aviso WITHOUT the
# wp:paragraph comment wrapper). Non-greedy to its own close -> never spans <p>s.
_P_LEAF_RE = re.compile(r"<p\b[^>]*>[\s\S]*?</p>", re.I)
_UTILIDADE_RE = re.compile(r"utilidade\s+p[úu]blica", re.I)


def _drop_if_aviso(m: re.Match) -> str:
    return "" if _UTILIDADE_RE.search(m.group(0)) else m.group(0)


def finalize_compliance_notice(content: str) -> str:
    """Remove the writer's inline 'Aviso de Utilidade Pública' (wherever it
    landed, wrapped in wp:paragraph OR a bare <p>) and re-append ONE canonical,
    discreet italic/small footnote at the very END. Compliance stays satisfied
    while the notice reads as a footnote, not a banner interrupting the article.

    Each block/paragraph is matched INDIVIDUALLY (leaf, non-greedy to its own
    close) and dropped only if it contains the aviso -- so the removal never
    spans across unrelated blocks and swallows the article body."""
    content = _PARA_BLOCK_RE.sub(_drop_if_aviso, content)   # wrapped aviso
    content = _P_LEAF_RE.sub(_drop_if_aviso, content)       # bare <p> aviso
    return content.rstrip() + "\n" + _AVISO_BLOCK


# Common Portuguese abbreviations whose trailing "." must NOT be treated as a
# sentence boundary (case-insensitive, matched right before the split point).
_ABBREVIATIONS = (
    "sr", "sra", "srta", "dr", "dra", "prof", "profa", "etc", "ex", "vs",
    "pág", "art", "n", "nº", "obs", "min", "máx", "aprox",
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý0-9\"'<])")


def _split_sentences(text: str) -> list[str]:
    """Split plain text into sentences on '. '/'! '/'? ' boundaries, without
    breaking common abbreviations (Sr., Dr., etc.) or splitting inside an
    unclosed inline tag (e.g. never break between '<a' and its own '>')."""
    raw_parts = _SENTENCE_SPLIT_RE.split(text)
    sentences: list[str] = []
    for part in raw_parts:
        if sentences:
            prev = sentences[-1]
            last_word = re.split(r"[\s>]", prev.rstrip(".!?").rstrip())[-1].lower()
            open_a = prev.count("<a") - prev.count("</a")
            if last_word in _ABBREVIATIONS or open_a > 0:
                sentences[-1] = prev + " " + part
                continue
        sentences.append(part)
    return [s for s in sentences if s.strip()]


def _split_long_paragraphs(content: str) -> str:
    """Break a single `wp:paragraph` block whose text has >=3 sentences OR is
    long (>~300 chars) into multiple short `wp:paragraph` blocks (1-2
    sentences each). Preserves inline `<strong>/<em>/<a>` markup. Never
    touches `wp:html` blocks, lists, tables, headings or buttons -- those are
    not `wp:paragraph` blocks and this function only matches that one block
    type."""

    def _split_one(m: re.Match) -> str:
        block = m.group(0)
        inner = re.search(r"<p\b([^>]*)>([\s\S]*?)</p>", block, re.I)
        if not inner:
            return block
        attrs, text = inner.group(1), inner.group(2)
        sentences = _split_sentences(text.strip())
        if len(sentences) < 3 and len(text) <= 300:
            return block
        if len(sentences) < 2:
            return block
        blocks = [
            f"<!-- wp:paragraph -->\n<p{attrs}>{chunk}</p>\n<!-- /wp:paragraph -->"
            for chunk in sentences
        ]
        return "\n".join(blocks)

    return _PARA_BLOCK_RE.sub(_split_one, content)


_LEADING_WP_BLOCK_RE = re.compile(r"\A\s*<!--\s*wp:", re.I)


def _wrap_leading_bare_line(content: str) -> str:
    """Wrap a BARE leading line in a wp:paragraph block.

    The presell opening hook (e.g. `<strong>Toque na opção certa ... ✅</strong>`)
    sometimes arrives as a bare inline line rather than a proper block. A bare
    leading line is not a valid top-level Gutenberg block and leaves the /rec
    body opening on non-block markup (so the Ad Inserter marco-zero slot and
    `no_leading_buttons` can't see a clean first paragraph). If the content does
    NOT already open on a `<!-- wp:` block, wrap its first line as a paragraph.
    """
    stripped = content.lstrip()
    if not stripped or _LEADING_WP_BLOCK_RE.match(stripped):
        return content
    first, sep, rest = stripped.partition("\n")
    first = first.strip()
    if not first:
        return content
    inner = first if first.lower().startswith("<p") else f"<p>{first}</p>"
    wrapped = f"<!-- wp:paragraph -->{inner}<!-- /wp:paragraph -->"
    # The split pass ran BEFORE this wrapper (see normalize_gutenberg), so it
    # never saw this bare intro as a wp:paragraph block. Split the freshly
    # wrapped block now, or a long bare intro ships as one wall of text.
    wrapped = _split_long_paragraphs(wrapped)
    return f"{wrapped}\n{rest}" if sep else wrapped


# --- Ad-anchor-zone flattening (COMPLIANCE) --------------------------------
# The site's Ad Inserter injects an ad BEFORE <p> #1 and AFTER <p> #3 (it
# counts <p> tags in document order). If one of those opening paragraphs sits
# inside a `wp-block-group has-background` / pullquote (a highlight box), the
# injected ad lands INSIDE that box -- an ad wrapped in a fraud-looking
# highlighted element reads as click inducement (AdSense policy risk). So the
# opening paragraphs must be PLAIN top-level blocks: we unwrap any leading box
# until enough plain top-level paragraphs precede everything else. Boxes deeper
# in the article are legitimate and left untouched.
_WP_TOKEN = re.compile(r"<!--\s*(/?)wp:([a-z0-9-]+)((?:(?!-->)[\s\S])*?)(/?)-->", re.I)
_LEADING_FLAT_PARAS = 4  # opening paragraphs that must be plain/top-level
_BOX_BLOCKS = ("group", "pullquote", "media-text")


def _top_level_blocks(content: str) -> list[tuple[int, int, str]]:
    """Return `(start, end, name)` for each TOP-LEVEL Gutenberg block, in
    document order. Depth-aware: a `wp:group` wrapping N inner blocks is ONE
    top-level block spanning its opener..closer, not N. Self-closing void
    blocks (`<!-- wp:spacer /-->`) count as their own block."""
    blocks: list[tuple[int, int, str]] = []
    depth = 0
    start: int | None = None
    name: str | None = None
    for m in _WP_TOKEN.finditer(content):
        is_close = m.group(1) == "/"
        self_close = m.group(4) == "/"
        if is_close:
            depth -= 1
            if depth <= 0:
                if start is not None:
                    blocks.append((start, m.end(), name or ""))
                depth = 0
                start = None
        elif self_close:
            if depth == 0:
                blocks.append((m.start(), m.end(), m.group(2).lower()))
        else:
            if depth == 0:
                start = m.start()
                name = m.group(2).lower()
            depth += 1
    return blocks


def _unwrap_box(block: str, name: str) -> str:
    """Drop a box wrapper, promoting its inner blocks to top-level PLAIN blocks.
    For `wp:group`/`media-text` we strip the block comments + the outer `<div>`
    and keep the inner wp:* blocks. For `wp:pullquote` we reduce it to a plain
    `wp:paragraph` carrying its text. Idempotent-safe: returns the inner markup
    with no residual group/pullquote wrapper or `has-background` class."""
    if name == "pullquote":
        text = re.sub(r"<[^>]+>", " ", block)
        text = re.sub(r"\s+", " ", text).strip()
        return f"<!-- wp:paragraph -->\n<p>{text}</p>\n<!-- /wp:paragraph -->" if text else ""
    inner = re.sub(r"\A\s*<!--\s*wp:[a-z0-9-]+\b(?:(?!-->)[\s\S])*?-->\s*", "", block, flags=re.I)
    inner = re.sub(r"<!--\s*/wp:[a-z0-9-]+\s*-->\s*\Z", "", inner, flags=re.I)
    # Peel the wrapping <div> layers (a group renders as an OUTER
    # `wp-block-group` div and, in some serializations, an inner
    # `__inner-container` div). Stop as soon as the content no longer opens on a
    # bare <div> -- the inner wp:paragraph/heading blocks (comment- or <p>-led)
    # end the peel, so nested content is never over-stripped. Capped at 3 layers.
    for _ in range(3):
        if re.match(r"\s*<div\b[^>]*>", inner, re.I) and re.search(r"</div>\s*\Z", inner, re.I):
            inner = re.sub(r"\A\s*<div\b[^>]*>", "", inner, flags=re.I)
            inner = re.sub(r"</div>\s*\Z", "", inner, flags=re.I)
        else:
            break
    return inner.strip()


def _flatten_leading_boxes(content: str, min_flat_paras: int = _LEADING_FLAT_PARAS) -> str:
    """Unwrap any box block (`wp:group`/`pullquote`/`media-text`) found in the
    opening until `min_flat_paras` plain top-level paragraphs precede the rest
    of the body -- so the Ad Inserter's anchors never land inside a highlight
    box. Boxes past that opening window are left intact."""
    to_unwrap: list[tuple[int, int, str]] = []
    p_seen = 0
    for start, end, name in _top_level_blocks(content):
        block = content[start:end]
        n_p = len(re.findall(r"<p[\s>]", block, re.I))
        if name in _BOX_BLOCKS and p_seen < min_flat_paras:
            to_unwrap.append((start, end, name))
        p_seen += n_p
        if p_seen >= min_flat_paras:
            break
    for start, end, name in reversed(to_unwrap):  # right-to-left keeps offsets valid
        content = content[:start] + _unwrap_box(content[start:end], name) + content[end:]
    return content


# ---------------------------------------------------------------------------
# MOEDA E PERCENTUAL EM pt-BR — corrigidos na GERAÇÃO
#
# A evidência preservada de `/r/fgts-saque-aniversario/` traz, no corpo que foi
# ao ar: "A Caixa aplica uma alíquota de 5 % a 50 % e soma uma parcela fixa de
# até 2900.00 R$". São duas formas erradas na mesma frase — o símbolo no FIM com
# ponto decimal inglês, e o espaço antes do sinal de porcentagem — e as duas
# viram `VALOR_MONETARIO_MALFORMADO` no portão do destino pago.
#
# Corrigir aqui, na geração, e não depois: uma correção pós-publicação é uma
# edição manual por página, e a próxima página nasce com o mesmo defeito.
#
# ⚠️ Só formas com `R$` ou `número %` são tocadas. Um "2900.00" solto pode ser
# versão, medida ou identificador; reescrevê-lo por conta própria seria inventar
# uma interpretação que o texto não sustenta.
# ---------------------------------------------------------------------------
_MOEDA_POSFIXADA_RE = re.compile(r"(?<![\w.,])(\d[\d.,]*)\s*R\$")
_MOEDA_PREFIXADA_RE = re.compile(r"R\$\s*(\d[\d.,]*)")
# Espaço (comum ou NBSP) entre o número e o `%`.
_PERCENTUAL_SOLTO_RE = re.compile(r"(\d)[\s\u00a0]+%")


def _numero_ptbr(bruto: str) -> str:
    """`2900.00` -> `2.900,00`; `2900,00` -> `2.900,00`; `2900` -> `2.900`.

    A ambiguidade real é o ponto sozinho: `2.900` é milhar em pt-BR e `2900.00` é
    decimal em inglês. A regra de desempate é a quantidade de casas depois do
    ÚLTIMO separador — duas casas é centavo, três é milhar. Fora disso, devolve o
    original: adivinhar mais que isso seria inventar um valor.
    """
    texto = bruto.strip().rstrip(".,")
    if not texto or not texto[0].isdigit():
        return bruto
    if "," in texto and "." in texto:
        inteiro, _, decimal = texto.rpartition(",")
        inteiro = inteiro.replace(".", "").replace(",", "")
    elif "," in texto:
        inteiro, _, decimal = texto.rpartition(",")
    elif "." in texto:
        inteiro, _, decimal = texto.rpartition(".")
        if len(decimal) != 2:          # `2.900` é milhar, não centavo
            inteiro, decimal = texto.replace(".", ""), ""
    else:
        inteiro, decimal = texto, ""
    if not inteiro.isdigit() or (decimal and not decimal.isdigit()):
        return bruto
    milhar = f"{int(inteiro):,}".replace(",", ".")
    return f"{milhar},{decimal}" if decimal else milhar


def formatar_moeda_ptbr(texto: str) -> str:
    """Normaliza valor monetário e percentual para a forma pt-BR."""
    saida = _MOEDA_POSFIXADA_RE.sub(lambda m: f"R$ {_numero_ptbr(m.group(1))}", texto)
    saida = _MOEDA_PREFIXADA_RE.sub(lambda m: f"R$ {_numero_ptbr(m.group(1))}", saida)
    return _PERCENTUAL_SOLTO_RE.sub(r"\1%", saida)


def formatar_moeda_em_estrutura(obj: object) -> object:
    """`formatar_moeda_ptbr` aplicada às FOLHAS de texto de uma estrutura.

    A LP não é HTML: é JSON estruturado que preenche o template Elementor, e
    `normalize_gutenberg` nunca a toca. Como o valor malformado medido em campo
    (`2900.00 R$`, `5 %`) estava justamente no corpo da LP, a mesma correção
    precisa alcançá-la — e alcançar folha a folha, não pelo JSON serializado,
    para nunca reescrever chave, aspa ou escape.
    """
    if isinstance(obj, str):
        return formatar_moeda_ptbr(obj)
    if isinstance(obj, list):
        return [formatar_moeda_em_estrutura(x) for x in obj]
    if isinstance(obj, dict):
        return {k: formatar_moeda_em_estrutura(v) for k, v in obj.items()}
    return obj


def normalize_gutenberg(html: str, *, ad_paragraph_anchors: list[int] | None = None) -> str:
    content = html.replace("﻿", "").replace(_FENCE + "html", "").replace(
        _FENCE, ""
    ).strip()
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    parts = re.split("(" + _RAW_HTML_BLOCK + ")", content, flags=re.I)
    out = []
    for part in parts:
        if _RAW_HTML_OPEN_RE.match(part):
            out.append(part)  # never touch raw html blocks
            continue
        p = re.sub(r"<!--\s*/?wp:list-item\s*-->", "", part, flags=re.I)
        p = re.sub(
            r"<li\b([^>]*)>([\s\S]*?)</li>",
            r"<!-- wp:list-item -->\n<li\1>\2</li>\n<!-- /wp:list-item -->",
            p,
            flags=re.I,
        )
        p = _split_long_paragraphs(p)
        # Moeda/percentual FORA do `wp:html`: o bloco cru é território do widget
        # (código executável), e reescrever markup por causa de um cifrão é como
        # um widget quebra em silêncio.
        p = formatar_moeda_ptbr(p)
        out.append(p)
    result = re.sub(r"\n{3,}", "\n\n", "".join(out)).strip()
    result = _wrap_leading_bare_line(result)
    # Keep one plain paragraph beyond the last configured ad anchor.  The
    # historical default remains four (live anchors 1/3), but the placement is
    # now an explicit project input rather than a hidden enhancer constant.
    min_flat = (max(ad_paragraph_anchors) + 1) if ad_paragraph_anchors else _LEADING_FLAT_PARAS
    result = _flatten_leading_boxes(result, min_flat)  # ad-anchor zone must be plain
    return _strip_separators_around_buttons(result)
