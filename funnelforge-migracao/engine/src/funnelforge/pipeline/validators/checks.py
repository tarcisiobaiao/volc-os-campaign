from __future__ import annotations
from datetime import date
from decimal import Decimal, InvalidOperation
import json
import re
import unicodedata
from collections.abc import Callable
from urllib.parse import urlparse
from funnelforge.domain.models import Issue, PageRole
from funnelforge.pipeline.doctrine import (
    BANNED_CTA_FIRST_PERSON, BANNED_FEAR, BANNED_OFFICIAL, banned_cta_execution_hit,
)
from funnelforge.pipeline.lp_template import validate_lp_content
from funnelforge.pipeline.engajamento import NIVEIS_BINARIOS, canon_engajamento
from funnelforge.pipeline.pagespec import _STOP, pagespec_validator
from funnelforge.pipeline.uniqueness import jaccard, uniqueness_guard

_SPANISH = (
    "ingreso",
    "¿cómo",
    "sisbén",
    "nequi",
    "beneficiario",
    "requisitos, montos",
)
_ENGLISH_LEAK = (" in 20", " the ", " and ", " you ")


def language_pt(content: str, ctx: dict) -> list[Issue]:
    low = content.lower()
    if any(w in low for w in _SPANISH) or any(w in low for w in _ENGLISH_LEAK):
        return [
            Issue(code="language_pt",
                  message="Vazamento de espanhol/inglês na saída.")
        ]
    return []


def _ctx_role(ctx: dict) -> PageRole:
    role = ctx.get("role")
    if isinstance(role, PageRole):
        return role
    if isinstance(role, str) and role:
        try:
            return PageRole(role)
        except ValueError:
            pass
    return PageRole.LP  # fail-closed: strictest ruleset when unknown


_BOTAO_BLOCK_RE = re.compile(
    r"=== WIDGET: BOT[ÃA]O ===\s*\n(.*?)(?=\n---|\Z)", re.S | re.I
)
_MARKER_TEXTO_RE = re.compile(r"^Texto:\s*(.+)$", re.M)
# O destino do botão no formato MARCADOR mora numa linha `Link:` própria (ver
# `adapters/elementor.parse_markers`). Sem ela, `_cta_links` só enxergava o
# HTML/Gutenberg -- e a LANDING PAGE inteira, que só fala marcador, ficava
# imune ao portão de congruência CTA↔destino.
_MARKER_LINK_RE = re.compile(r"^Link:\s*(.+)$", re.M)
_ANCHOR_RE = re.compile(r"<a\b[^>]*>(.*?)</a>", re.S | re.I)
_INNER_TAG_RE = re.compile(r"<[^>]+>")
# A CTA button is an anchor INSIDE a wp:buttons block. Inline <a> links in
# prose (official deep links, recirculation links) are NOT CTAs -- their
# descriptive text legitimately names service pages ("página de cadastro do
# portal Gov.br", "consultar CPF"), which must never be read as a
# service-execution CTA (this false positive blocked a whole SOLUTION write).
_BUTTONS_BLOCK_RE = re.compile(
    r"<!--\s*wp:buttons\b.*?<!--\s*/wp:buttons\s*-->", re.S | re.I
)


_HREF_ATTR_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.I)


def _cta_links(content: str) -> list[tuple[str, str]]:
    """Like `_cta_texts` but keeps the HREF of each CTA BUTTON anchor, as
    (label, href) pairs (label = visible anchor text, tags stripped; href = the
    `href` attribute, "" when absent). Only anchors INSIDE a `wp:buttons` block
    count as CTA buttons (an inline `<a>` in prose is not a CTA). The marker
    draft format carries its href on a separate `Link:` line, so only the
    HTML/Gutenberg wp:buttons anchors yield pairs here -- exactly the rendered
    surface the destination-congruence gate (CARD-0011) runs on. Passing a
    SINGLE block's HTML returns just that block's anchors -- how
    `cta_destination_congruent` pairs each button with its own bridge."""
    pairs: list[tuple[str, str]] = []
    # (a) formato MARCADOR -- `Texto:` + `Link:` dentro de um bloco
    # `=== WIDGET: BOTÃO ===`. Os dois casam por POSIÇÃO dentro do bloco (o
    # bloco real tem um par; a lista tolera bloco torto sem estourar índice).
    for block in _BOTAO_BLOCK_RE.findall(content):
        rotulos = [m.strip() for m in _MARKER_TEXTO_RE.findall(block)]
        hrefs = [m.strip() for m in _MARKER_LINK_RE.findall(block)]
        for i, rotulo in enumerate(rotulos):
            if rotulo:
                pairs.append((rotulo, hrefs[i] if i < len(hrefs) else ""))
    # (b) HTML/Gutenberg -- só âncoras DENTRO de um bloco wp:buttons.
    for block in _BUTTONS_BLOCK_RE.findall(content):
        for m in _ANCHOR_RE.finditer(block):
            label = _INNER_TAG_RE.sub("", m.group(1)).strip()
            if label:
                href_m = _HREF_ATTR_RE.search(m.group(0))
                pairs.append((label, href_m.group(1).strip() if href_m else ""))
    return pairs


def _cta_texts(content: str) -> list[str]:
    """Extract CTA BUTTON label text only.

    The banned CTA-style verbs (execution/first-person) are only forbidden
    IN CTA BUTTON TEXT. They legitimately show up in body prose, the mandatory
    compliance rodapé (e.g. "sem solicitar dados"), and inline OFFICIAL deep
    links (e.g. "página de cadastro do portal Gov.br"), so `cta_style` must
    scan ONLY the visible text of CTA buttons, never inline links or prose.

    Supports both draft formats:
      (a) marker format -- `Texto: ...` lines inside `=== WIDGET: BOTÃO ===`
          blocks;
      (b) HTML/Gutenberg -- only anchors INSIDE a `wp:buttons` block count as
          CTA buttons (an inline `<a>` link in a paragraph is not a CTA).
    """
    texts: list[str] = []
    for block in _BOTAO_BLOCK_RE.findall(content):
        texts.extend(m.strip() for m in _MARKER_TEXTO_RE.findall(block))
    for block in _BUTTONS_BLOCK_RE.findall(content):
        for inner in _ANCHOR_RE.findall(block):
            label = _INNER_TAG_RE.sub("", inner).strip()
            if label:
                texts.append(label)
    return texts


# ⚠️ ANCORAR EM "^" ERA O FURO. A regra antiga só olhava o COMEÇO do rótulo,
# então qualquer prefixo escapava: "Quero consultar no App FGTS" prometia
# executar o serviço e passava batido. Agora o verbo é procurado no rótulo
# INTEIRO -- e o que separa promessa de curiosidade não é a POSIÇÃO, é o
# ENQUADRAMENTO: um interrogativo ("como", "quando", "quem", "se") ANTES do
# verbo transforma execução em explicação, e aí o clique não mente. É por isso
# que "Ver como consultar no App FGTS" continua válido (doutrina do card
# CARD-0011) enquanto "Consultar no App FGTS" não.
_CTA_ACTION_RE = re.compile(
    r"\b(?:acessar|acesse|abrir|abra|autorizar|autorize|baixar|baixe|"
    r"cadastrar|cadastre|conferir|confira|consultar|consulte|contratar|"
    r"contrate|emitir|emita|entrar|instalar|instale|pedir|resgatar|resgate|"
    r"sacar|saque|simular|simule|solicitar|solicite)\b",
    re.I,
)
# O enquadramento explicativo. "se" entra porque "Veja se dá para sacar pelo
# app" é curiosidade legítima; ele só vale quando vem ANTES do verbo.
_CTA_FRAME_RE = re.compile(
    r"\b(?:como|quando|quem|onde|quais|qual|se|por\s*que|porqu[eê])\b",
    re.I,
)
_CTA_EXTERNAL_DEST_RE = re.compile(
    r"\b(?:app|aplicativo|portal|site|canal)\b|\bgov\.br\b|\bcaixa\b",
    re.I,
)


def _promessa_de_execucao(rotulo: str) -> bool:
    """True quando o rótulo PROMETE executar o serviço, e não explicá-lo."""
    acao = _CTA_ACTION_RE.search(rotulo)
    if acao is None:
        return False
    enquadramento = _CTA_FRAME_RE.search(rotulo)
    return not (enquadramento and enquadramento.start() < acao.start())


def cta_style(content: str, ctx: dict) -> list[Issue]:
    joined = "\n".join(_cta_texts(content)).lower()
    issues: list[Issue] = []
    # Word-boundary anchored (doctrine.banned_cta_execution_hit): "Solicite" is
    # still caught, but "demitido" is NOT (the stem "emit" no longer fires
    # mid-word) -- see _cta_execution_regex for why that false positive mattered.
    if banned_cta_execution_hit(joined):
        issues.append(Issue(code="cta_execution",
                            message="CTA com verbo de execução de serviço (proibido)."))
    if _ctx_role(ctx) == PageRole.LP and any(p in joined for p in BANNED_CTA_FIRST_PERSON):
        issues.append(Issue(code="cta_first_person",
                            message="CTA em 1ª pessoa emocional na LP (proibido)."))
    # A label can be literally true and still lie about the click destination.
    # "Consultar modalidade no App FGTS" is an execution promise; when its href
    # is an internal article, the button does not do what it says.  Curiosity
    # framing ("Ver como consultar no App FGTS") remains valid because the
    # click truthfully opens an explanation.
    site = urlparse(ctx.get("domain", "")).netloc.lower()
    for label, href in _cta_links(content):
        parsed = urlparse(href)
        internal = not parsed.netloc or _host_matches(parsed.netloc.lower(), site)
        if internal and _promessa_de_execucao(label) and _CTA_EXTERNAL_DEST_RE.search(label):
            issues.append(Issue(
                code="cta_destination_mismatch",
                message=(f"CTA promete ação em destino externo, mas aponta para página "
                         f"interna: {label!r} -> {href!r}."),
            ))
    return issues


def calm_utility(content: str, ctx: dict) -> list[Issue]:
    low = content.lower()
    issues: list[Issue] = []
    if any(p in low for p in BANNED_FEAR):
        issues.append(Issue(code="fear_language",
                            message="Gatilho de medo/escassez proibido (tom calmo obrigatório)."))
    if any(p in low for p in BANNED_OFFICIAL):
        issues.append(Issue(code="official_impersonation",
                            message="Linguagem de falsa oficialidade proibida."))
    return issues


def gutenberg_blocks(content: str, ctx: dict) -> list[Issue]:
    issues: list[Issue] = []
    if re.search(r"<script\b", content, re.I) and not ctx.get("allow_sanitized_widget_script"):
        issues.append(
            Issue(code="has_script",
                  message="Contém <script> (proibido).")
        )
    # Count block OPENS, excluding SELF-CLOSING blocks (`<!-- wp:x ... /-->`,
    # e.g. spacer/separator/post-featured-image) which never take a matching
    # close comment -- otherwise a legit self-closing block reads as an
    # unbalanced open and fails the write.
    all_opens = re.findall(
        r"<!--\s*wp:(?!list-item\b)[a-z0-9-]+[^>]*?-->", content, re.I
    )
    opens = sum(1 for m in all_opens if not m.rstrip().endswith("/-->"))
    closes = len(
        re.findall(
            r"<!--\s*/wp:(?!list-item\b)[a-z0-9-]+",
            content,
            re.I
        )
    )
    if opens != closes:
        issues.append(
            Issue(
                code="unbalanced",
                message=f"Blocos desbalanceados {opens} vs {closes}."
            )
        )
    return issues


def compliance(content: str, ctx: dict) -> list[Issue]:
    if (
        "adsense" not in content.lower()
        and "utilidade pública" not in content.lower()
    ):
        return [
            Issue(
                code="no_compliance",
                message="Falta bloco de compliance/aviso."
            )
        ]
    return []


def length_p1(content: str, ctx: dict) -> list[Issue]:
    n = len(re.sub(r"<[^>]+>", " ", content).split())
    if n < 500:
        return [Issue(code="too_short", message=f"Curto demais: {n} palavras.")]
    return []


def interior_min_length(content: str, ctx: dict) -> list[Issue]:
    """Interior funnel pages (PRESELL/SOLUTION) must carry a real article, not a
    truncated stub. Without this, an LLM that returns near-empty output (a couple
    of buttons + the aviso) still passes every STRUCTURAL check and ships as a
    blank /rec draft. 400 words is a safe floor -- real pages run 900-1200."""
    if _ctx_role(ctx) not in (PageRole.PRESELL, PageRole.SOLUTION):
        return []
    text = re.sub(r"<[^>]+>", " ", re.sub(r"<!--.*?-->", " ", content, flags=re.S))
    n = len(text.split())
    if n < 400:
        return [Issue(code="body_too_short",
                      message=f"Corpo curto demais: {n} palavras (mínimo 400).")]
    return []


_TRAILING_WS_RE = re.compile(r"\s+\Z")
_TRAILING_SPACER_RE = re.compile(
    r"(?:<!--\s*wp:spacer\b[^>]*?/-->"
    r"|<!--\s*wp:spacer\b[^>]*?-->[\s\S]*?<!--\s*/wp:spacer\s*-->)\s*\Z",
    re.I,
)
_TRAILING_SEPARATOR_RE = re.compile(
    r"(?:<!--\s*wp:separator\b[^>]*?/-->"
    r"|<!--\s*wp:separator\b[^>]*?-->[\s\S]*?<!--\s*/wp:separator\s*-->)\s*\Z",
    re.I,
)
_TRAILING_PARAGRAPH_RE = re.compile(
    r"(?:<!--\s*wp:paragraph\b[^>]*?-->([\s\S]*?)<!--\s*/wp:paragraph\s*-->"
    r"|(<p\b[^>]*>[\s\S]*?</p>))\s*\Z",
    re.I,
)
_TRAILING_BUTTONS_RE = re.compile(r"<!--\s*/wp:buttons\s*-->\s*\Z", re.I)
_AVISO_UTILIDADE_RE = re.compile(r"utilidade\s+p[úu]blica", re.I)
_NOTA_PERMANECE_RE = re.compile(r"voc[êe]\s+permanece", re.I)


def _strip_trailing_ignorables(content: str) -> str:
    """Peel whitespace, trailing wp:spacer/wp:separator blocks, and a trailing
    'aviso de utilidade pública' or '* Você permanece *' note paragraph off the
    END of the draft, so `no_trailing_buttons` can see what the article
    ACTUALLY closes on underneath the decorative/compliance tail."""
    text = content
    for _ in range(200):
        no_ws = _TRAILING_WS_RE.sub("", text)
        if no_ws != text:
            text = no_ws
            continue
        m = _TRAILING_SPACER_RE.search(text)
        if m:
            text = text[: m.start()]
            continue
        m = _TRAILING_SEPARATOR_RE.search(text)
        if m:
            text = text[: m.start()]
            continue
        m = _TRAILING_PARAGRAPH_RE.search(text)
        if m:
            inner = m.group(1) if m.group(1) is not None else m.group(2)
            if _AVISO_UTILIDADE_RE.search(inner) or _NOTA_PERMANECE_RE.search(inner):
                text = text[: m.start()]
                continue
        break
    return text


def no_trailing_buttons(content: str, ctx: dict) -> list[Issue]:
    """PRESELL/SOLUTION pages must close on a textual transition, never on a
    button stack -- see redator_pages.jinja's saturacao_de_cta. Ignore the
    trailing aviso/nota/spacer/separator (decorative or system-appended) to see
    what the article ACTUALLY ends on; flag only when THAT is a wp:buttons
    block. A page ending in FAQ/pullquote/prose is fine; buttons mid-body are
    fine; only a trailing button stack is not."""
    if _ctx_role(ctx) not in (PageRole.PRESELL, PageRole.SOLUTION):
        return []
    tail = _strip_trailing_ignorables(content.rstrip())
    if _TRAILING_BUTTONS_RE.search(tail):
        return [
            Issue(
                code="trailing_buttons",
                message="A página termina em bloco de botões; o fecho deve ser "
                        "um parágrafo de transição textual, sem botão.",
            )
        ]
    return []


_LEADING_BLOCK_RE = re.compile(r"\A\s*<!--\s*wp:(\S+?)\b", re.I)


def no_leading_buttons(content: str, ctx: dict) -> list[Issue]:
    """SOLUTION/PRESELL page body (`/rec`) must never open on a wp:buttons
    block -- the H1 is the WP post title and doesn't live in the body, so the
    first block of the body is what the reader (and the Ad Inserter marco-zero
    ad slot) sees first. It must be a wp:paragraph, not a button stack. Both
    interior /rec roles (SOLUTION and PRESELL) are in scope."""
    if _ctx_role(ctx) not in (PageRole.SOLUTION, PageRole.PRESELL):
        return []
    match = _LEADING_BLOCK_RE.match(content)
    if match and match.group(1).lower() == "buttons":
        return [
            Issue(
                code="leading_buttons",
                message="A página abre em bloco de botões; o primeiro bloco do "
                        "corpo deve ser um parágrafo (reserva o marco-zero do ad).",
            )
        ]
    return []


_FIRST_HEADING_RE = re.compile(r"<!--\s*wp:heading\b", re.I)
_PARAGRAPH_BLOCK_RE = re.compile(
    r"<!--\s*wp:paragraph\b[^>]*?-->([\s\S]*?)<!--\s*/wp:paragraph\s*-->",
    re.I,
)
# Heading-count guard (min_headings). One heading block scoped to its own
# open..close, its <h2> tag, and the FAQ heading text -- so we count only
# CONTENT H2 sections (the FAQ is excluded, mirroring the widget injector's
# `_widget_h2_positions`, so a `2 content H2 + FAQ` page is still too few).
_HEADING_BLOCK_RE = re.compile(
    r"<!--\s*wp:heading\b.*?<!--\s*/wp:heading\s*-->", re.S | re.I)
_H2_TAG_RE = re.compile(r"<h2\b", re.I)
_FAQ_HEADING_RE = re.compile(r"perguntas\s+frequentes", re.I)


def min_headings(content: str, ctx: dict) -> list[Issue]:
    """SOLUTION pages must have >=3 CONTENT H2 sections (redator_pages
    <estrutura_h2>). Without this guard a model that ignores the instruction
    ships a headingless WALL -- and the widget injector, which targets 'before
    the 3rd content H2', then dumps the widget at the very END, decontextualized
    (the p2/celular defect: 0 H2 -> confusing wall + widget dumped at the tail +
    a floating FAQ dropdown). SOLUTION-only; the FAQ heading does not count."""
    if _ctx_role(ctx) is not PageRole.SOLUTION:
        return []
    content_h2 = [
        m for m in _HEADING_BLOCK_RE.finditer(content)
        if _H2_TAG_RE.search(m.group(0)) and not _FAQ_HEADING_RE.search(m.group(0))
    ]
    if len(content_h2) < 3:
        return [
            Issue(
                code="too_few_headings",
                message=(
                    f"Página de solução precisa de >=3 seções H2 de conteúdo "
                    f"(a estrutura em blocos); achei {len(content_h2)}."
                ),
            )
        ]
    return []


def short_intro(content: str, ctx: dict) -> list[Issue]:
    """SOLUTION pages must dive into the first H2 right after the top CTA
    block -- see redator_pages.jinja's <introducao_direta>. The INTRO is
    whatever sits before the first wp:heading; it may hold at most ONE real
    wp:paragraph. The nota "* Você permanece *" and an aviso de utilidade
    pública, when either lands up top, are NOT intro prose and don't count.
    A draft with no heading at all (degenerate) and an intro with zero real
    paragraphs are both left alone -- other validators already catch a
    headingless draft, and an empty intro is trivially within the max of 1.
    PRESELL is OUT OF SCOPE: its opening CTA-line + nota (CARD-0002) would
    false-positive against this same-shaped check; its intro cap is
    prompt-only for now.
    """
    if _ctx_role(ctx) is not PageRole.SOLUTION:
        return []
    heading = _FIRST_HEADING_RE.search(content)
    if not heading:
        return []
    prefix = content[: heading.start()]
    real_paragraphs = [
        block for block in _PARAGRAPH_BLOCK_RE.findall(prefix)
        if not _NOTA_PERMANECE_RE.search(block)
        and not _AVISO_UTILIDADE_RE.search(block)
    ]
    if len(real_paragraphs) > 1:
        return [
            Issue(
                code="intro_long",
                message=(
                    f"Introdução com {len(real_paragraphs)} parágrafo(s) antes "
                    "do 1º H2; o máximo permitido é 1."
                ),
            )
        ]
    return []


def presell_opening_line(content: str) -> str:
    """The PRESELL page's opening CTA line -- plain text of the first
    `wp:paragraph` block in the draft (redator_presell.jinja always opens
    directly on this bolded "Toque na opção certa e ..." line -- see its
    <formato_de_saida>). If some other block precedes it, fall back to the
    first paragraph appearing before the first heading; "" when the draft
    has none at all (a degenerate draft other validators already catch).
    Shared between `opening_line_unique` below and `steps.py`'s
    `step_publish`, so the validator and the cross-run recorder can never
    disagree on what "the opening line" is."""
    heading = _FIRST_HEADING_RE.search(content)
    prefix = content[: heading.start()] if heading else content
    match = _PARAGRAPH_BLOCK_RE.search(prefix)
    if not match:
        return ""
    return _INNER_TAG_RE.sub("", match.group(1)).strip()


def opening_line_unique(content: str, ctx: dict) -> list[Issue]:
    """CARD-0007: the PRESELL opening CTA line must not repeat near-verbatim
    across DIFFERENT funnels/runs -- the intra-run `uniqueness` guard can't
    catch this (it only compares drafts written in the SAME run).
    `ctx['prior_opening_lines']` is pre-loaded by `steps._write_ctx` from the
    persistent `phrase_registry`, so this validator stays PURE (no I/O). A
    no-op when the role isn't PRESELL, there are no prior lines to compare
    against, or this draft has no extractable opening line."""
    if _ctx_role(ctx) is not PageRole.PRESELL:
        return []
    priors = ctx.get("prior_opening_lines") or []
    if not priors:
        return []
    line = presell_opening_line(content)
    if not line:
        return []
    threshold = float(ctx.get("opening_line_threshold", 0.6))
    worst, worst_prior = 0.0, ""
    for prior in priors:
        score = jaccard(line, prior)
        if score > worst:
            worst, worst_prior = score, prior
    if worst >= threshold:
        return [
            Issue(
                code="boilerplate_opening",
                message=(
                    f"Linha de abertura quase idêntica (Jaccard {worst:.2f} >= "
                    f"{threshold:.2f}) à de outro funil já publicado: \"{worst_prior}\"."
                ),
            )
        ]
    return []


def winning_lp(content: str, ctx: dict) -> list[Issue]:
    # Byline / nav / institutional "Sobre o Site" footer are NO LONGER part
    # of the generated page content -- the WordPress theme injects author,
    # navigation and the compliance footer (with CNPJ) globally on a fixed
    # template. winning_lp therefore only enforces the on-page funnel
    # essentials: a real FAQ block + calm CTA discipline.
    issues: list[Issue] = []
    if "=== WIDGET: FAQ ===" not in content:
        issues.append(Issue(code="no_faq", message="Falta o bloco FAQ."))
    issues += cta_style(content, ctx)
    return issues


def _field(obj, key: str, default=None):
    """Read `key` from a dict or a pydantic model/object alike."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def seo_limits(content: str, ctx: dict) -> list[Issue]:
    parsed = ctx.get("parsed")
    if parsed is None:
        return []
    metadescription = _field(parsed, "metadescription", "") or ""
    if len(metadescription) > 160:
        return [
            Issue(
                code="seo_meta_too_long",
                message=f"Metadescription com {len(metadescription)} caracteres (max 160).",
            )
        ]
    return []


def has_sources(content: str, ctx: dict) -> list[Issue]:
    parsed = ctx.get("parsed")
    if parsed is None:
        return []
    sparse = bool(_field(parsed, "sparse", False))
    fontes = _field(parsed, "fontes", []) or []
    if sparse or not fontes:
        return [Issue(code="no_sources", message="Pesquisa esparsa ou sem fontes citadas.")]
    invalid = [u for u in fontes if not _valid_https_url(str(u))]
    if invalid:
        return [Issue(code="invalid_source_url",
                      message=f"Fonte não é URL HTTPS absoluta: {invalid[0]!r}.")]
    return []


def _valid_https_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme == "https" and bool(parsed.netloc)


def research_facts_contract(content: str, ctx: dict) -> list[Issue]:
    """Validate freshness and provenance of publication-grade facts."""
    parsed = ctx.get("parsed")
    if parsed is None:
        return []
    sources = set(_field(parsed, "fontes", []) or [])
    facts = _field(parsed, "fatos_verificados", []) or []
    today = ctx.get("today") or date.today()
    max_age = int(ctx.get("max_age_days") or 45)
    issues: list[Issue] = []
    for index, fact in enumerate(facts, start=1):
        source = str(_field(fact, "fonte_primaria", "") or "")
        verified = _field(fact, "verificado_em", None)
        active = _field(fact, "vigente_desde", None)
        if source not in sources:
            issues.append(Issue(
                code="fact_source_not_listed",
                message=f"Fato {index}: fonte_primaria não aparece em fontes.",
            ))
        if not _valid_https_url(source):
            issues.append(Issue(code="invalid_primary_source",
                                message=f"Fato {index}: fonte primária inválida."))
        if isinstance(active, date) and active > today:
            issues.append(Issue(code="fact_not_yet_effective",
                                message=f"Fato {index}: vigência começa no futuro."))
        if not isinstance(verified, date):
            issues.append(Issue(code="fact_without_verification_date",
                                message=f"Fato {index}: verificado_em inválido."))
        elif verified > today or (today - verified).days > max_age:
            issues.append(Issue(
                code="stale_fact",
                message=(f"Fato {index}: verificação fora da janela de {max_age} dias "
                         f"({verified.isoformat()})."),
            ))
    return issues


def funnel_schema(content: str, ctx: dict) -> list[Issue]:
    parsed = ctx.get("parsed")
    if parsed is None:
        return []
    pages = _field(parsed, "pages", None)
    if not pages or not isinstance(pages, list):
        return [Issue(code="no_pages", message="JSON extraído sem lista 'pages'.")]
    strategy = _field(parsed, "funnel_strategy", {}) or {}
    # The raw extractor JSON is untyped: total_pages may arrive quoted ("6") or
    # as garbage (a list). Coerce to int; a non-numeric value means "no declared
    # count", never a crash of the whole run on `len(pages) < <str|list>`.
    try:
        total_pages = int(_field(strategy, "total_pages", None))
    except (TypeError, ValueError):
        total_pages = None
    # The pages array is authoritative; a richer funnel (more solutions than the
    # extractor's self-declared count) is VALID, so only a SHORTFALL -- fewer
    # pages than planned, i.e. a truncated/incomplete extraction -- is a defect.
    if total_pages and len(pages) < total_pages:
        return [
            Issue(
                code="page_count_short",
                message=f"Extração incompleta: {len(pages)} páginas, o plano previa {total_pages}.",
            )
        ]
    return []


_HREF_SRC_RE = re.compile(r'(?:href|src)\s*=\s*["\']([^"\']+)["\']', re.I)
# Markdown link targets: [texto](URL) -- grab everything up to ')' or whitespace.
_MD_LINK_RE = re.compile(r'\]\(\s*([^)\s]+)')
# Any scheme-qualified URL loose in the text (not inside an attribute/markdown).
_SCHEME_URL_RE = re.compile(r'https?://[^\s<>"\'()\]]+', re.I)
# Bare "host.tld" tokens with no scheme, e.g. "portalmundomais.com" or
# "joinads.me" mentioned in plain prose. Only fires on a real-looking TLD so
# ordinary words/abbreviations ("etc.") and sentence-ending periods don't match.
_BARE_HOST_TLDS = (
    "com", "org", "net", "info", "biz", "gov", "edu", "mil", "adv",
    "io", "me", "co", "app", "dev", "shop", "store", "online", "site",
    "tech", "blog", "news", "club", "xyz", "ai", "br", "us", "uk",
)
_BARE_HOST_RE = re.compile(
    r"(?<![\w.@/-])"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"(?:" + "|".join(_BARE_HOST_TLDS) + r")"
    r"(?![a-z0-9-])"
    r"(?:/[^\s\"'<>()\]]*)?",
    re.I,
)


def _host_matches(host: str, entry: str) -> bool:
    """One host-vs-allow-entry rule, shared by every host check: `host` is
    accepted for `entry` when it is exactly `entry`, a subdomain of it, or its
    "www."-prefixed apex (entry "www.gov.br" also permits bare "gov.br"). A
    lookalike like "gov.br.evil.com" satisfies none of the three and is
    rejected. An empty `entry` matches nothing (a real host is never "", never
    ends in ".", and is never "www." of the empty string)."""
    return host == entry or host.endswith("." + entry) or entry == "www." + host


def _host_ok(host: str, site: str, allowed: set[str]) -> bool:
    # Accept the registrable apex of a "www."-prefixed site/allow entry too:
    # if the entry is exactly "www." + host, `host` is that entry's apex
    # domain (e.g. site/allow "www.gov.br" also permits bare "gov.br" prose).
    # This does NOT relax subdomain matching: a lookalike like
    # "gov.br.evil.com" is neither equal to nor "www."-apex-of any entry,
    # nor a subdomain of one, so it is still rejected.
    return _host_matches(host, site) or any(_host_matches(host, a) for a in allowed)


def url_host(url: str) -> str:
    """Host de uma URL, em minúsculas ("" quando não dá para extrair).

    Substitui `url_host_on_allowlist`, que era o motor da allowlist: a mesma
    função decidia quem podia sair da página E quais fontes da pesquisa viravam
    link oficial, então uma lista pensada para o funil de FGTS reprovava o canal
    oficial de qualquer outro tema. Autorização agora é evidência de pesquisa,
    URL a URL (ver steps.build_official_links); aqui sobrou só o utilitário."""
    return _url_host(url)


def host_matches_preference(host: str, preferences: list[str] | None) -> bool:
    """A PREFERÊNCIA casou com este host? Isso NUNCA autoriza nada.

    Aceita domínio ("caixa.gov.br") ou NOME de órgão/empresa como o campo
    `official_source` da entidade no VOLC O.S. entrega ("iFood", "DIAN", "Caixa
    Econômica Federal") -- aquele campo é um nome, não uma URL, e por isso não
    poderia ser trava nem se quiséssemos. Casa por token sem acento: "iFood"
    bate em `entregador.ifood.com.br`, "Caixa Econômica" bate em
    `www.caixa.gov.br`.

    Único efeito: o candidato sobe na fila dos links oficiais. Não casar não
    reprova nada, e uma preferência vazia é o caso normal."""
    if not preferences or not host:
        return False
    host_plano = _sem_acento(host)
    for bruto in preferences:
        pref = (bruto or "").strip()
        if not pref:
            continue
        if "." in pref and " " not in pref:          # veio como domínio
            alvo = (_url_host(pref) or pref.lower()).removeprefix("www.")
            if alvo and _host_matches(host, alvo):
                return True
            continue
        for token in re.split(r"[^0-9a-z]+", _sem_acento(pref)):
            if len(token) >= 4 and token in host_plano:
                return True
    return False


def _sem_acento(texto: str) -> str:
    """minúsculas e sem acento, para comparar nome de canal com host."""
    plano = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in plano if not unicodedata.combining(c)).lower()


def _url_host(raw: str) -> str:
    """Best-effort host extraction from an attribute value, markdown target,
    scheme-qualified URL, or bare domain-like token (no scheme)."""
    raw = raw.strip().strip(").,;!?”’\"'")
    if not raw:
        return ""
    candidate = raw if ("://" in raw or raw.startswith("//")) else "http://" + raw
    return urlparse(candidate).netloc.lower()


def _extract_hosts(content: str) -> list[str]:
    """Pull every plausible external host out of `content`: HTML href/src
    attributes, markdown link targets, scheme-qualified URLs loose in the
    text, and bare domain-like tokens (e.g. "portalmundomais.com/oferta")."""
    hosts: dict[str, None] = {}
    for pattern in (_HREF_SRC_RE, _MD_LINK_RE, _SCHEME_URL_RE, _BARE_HOST_RE):
        for m in pattern.finditer(content):
            raw = m.group(1) if pattern.groups else m.group(0)
            host = _url_host(raw)
            if host:
                hosts[host] = None
    return list(hosts)


def same_domain(content: str, ctx: dict) -> list[Issue]:
    """A AUTORIZAÇÃO VEM DA BUSCA, não de uma lista.

    Um host externo é aceito quando a PESQUISA daquela página o trouxe. Nada de
    allowlist estática: uma página sobre milhas no PicPay precisa citar
    `picpay.com`, uma sobre entregador Shopee precisa citar `shopee.com.br`, e
    prever esses domínios um a um numa lista trava a operação sem proteger nada
    — a lista bloqueava o canal oficial de que a página precisa e deixava passar
    o que entrava pela prosa.

    A trava que FICA, e é a única que importa: **o modelo não inventa URL.** Só
    entra host que a busca devolveu de verdade. Sem isso, uma página sobre
    crédito linka `emprestimo-aprovado-rapido.com` e você publica um caminho
    para golpe com a sua assinatura embaixo.

    `official_preference` pode continuar desempatando QUAL canal vira o CTA,
    mas não participa desta autorização. Um domínio preferido que a pesquisa não
    trouxe continua bloqueado — preferência não é permissão.
    """
    site = urlparse(ctx.get("domain", "")).netloc.lower()
    # Hosts que a pesquisa desta página trouxe -- a autorização de verdade.
    da_busca = {h.lower() for h in (ctx.get("research_hosts") or []) if h}
    # Compat: plataformas confirmadas ao vivo, quando há verificador ligado.
    verificados = {h.lower() for h in (ctx.get("verified_platforms") or []) if h}
    autorizados = da_busca | verificados
    for host in _extract_hosts(content):
        if _host_ok(host, site, set()):
            continue
        if any(_host_matches(host, v) for v in autorizados):
            continue
        return [Issue(code="cross_domain",
                      message=f"Host externo que a pesquisa não trouxe: {host}. "
                              f"Só entra link que a busca devolveu (nunca inventado).")]
    return []


def official_link_density(content: str, ctx: dict) -> list[Issue]:
    """Require research-derived official links, never allow-list membership.

    Only role SOLUTION is in scope; PRESELL/LP are exempt. The minimum is
    MODE-AWARE and read from `ctx['official_links']` -- the deep links
    step_write surfaced from the research (its fallback always yields at least
    the one generic graph link, so the list is a faithful signal of how much
    official material the research actually provided):
      - research gave >= 2 official deep links  -> require >= 2 distinct hrefs;
      - sparse research (0/1 link, or ctx absent) -> require only >= 1 (the
        graph link), a controlled fail-open so a page is never blocked for
        lacking deep links the research never surfaced.
    """
    # The TERMINAL solution recirculates via cross_funnel only -- it has no
    # external_official route and its writer branch is told not to cite an
    # official channel, so it is exempt from the deep-link density requirement.
    if _ctx_role(ctx) is not PageRole.SOLUTION or ctx.get("is_terminal"):
        return []
    verified = set(ctx.get("official_links") or [])
    linked = {m.group(1) for m in _HREF_SRC_RE.finditer(content)}
    official = linked & verified
    if len(verified) >= 2:
        # Rich mode -- the research surfaced >=2 VERIFIED deep links (a
        # single-link curated/graph fallback never reaches here). Harden by
        # requiring the body to actually weave in >=2 of THOSE verified links
        # (intersection), not just any two whitelisted hosts: the writer was
        # handed the exact deep links, so it must anchor them (Task 8 / B4).
        have = len(official)
        minimum = 2
    else:
        # Sparse/fallback mode (0/1 verified link): a controlled fail-open, only
        # the single graph/curated official link is required -- never block a
        # page for lacking deep links the research never surfaced.
        have = len(official)
        minimum = 1
    if have < minimum:
        return [
            Issue(
                code="official_links_few",
                message=(
                    f"Apenas {have} link(s) oficial(is) distinto(s) no corpo "
                    f"(fonte devolvida pela pesquisa); o mínimo desta página é {minimum}."
                ),
            )
        ]
    return []


# Um bloco wp:buttons inteiro (é dentro dele que mora o clique comprado).
_BOTOES_BLOCO_RE = re.compile(r"<!--\s*wp:buttons\b.*?<!--\s*/wp:buttons\s*-->", re.S | re.I)


def external_cta_authorized(content: str, ctx: dict) -> list[Issue]:
    """O CLIQUE COMPRADO NÃO VAZA POR BOTÃO.

    Link em prosa é CITAÇÃO e já responde ao `same_domain` (só passa host que a
    pesquisa daquela página trouxe). BOTÃO é outra coisa: é para onde a página
    empurra a sessão que você pagou no Google Ads. Então botão só pode apontar
    para o próprio site (recirculação) ou para o canal externo que o motor
    ESCOLHEU com evidência -- `official_links` e as plataformas verificadas.

    É esta a regra que substitui a allowlist no ponto que importava: o
    inventário do funil antigo achou 8 links de saída, 3 deles para um portal
    concorrente. Um concorrente citado pela pesquisa continua podendo ser
    CITADO; ele não pode ganhar o botão.
    """
    site = urlparse(ctx.get("domain", "")).netloc.lower()
    autorizados = {_url_host(u) for u in (ctx.get("official_links") or [])}
    autorizados |= {h.lower() for h in (ctx.get("verified_platforms") or []) if h}
    autorizados.discard("")
    for bloco in _BOTOES_BLOCO_RE.finditer(content):
        for m in _HREF_SRC_RE.finditer(bloco.group(0)):
            host = _url_host(m.group(1))
            if not host:
                continue                      # href relativo = mesmo site
            if site and _host_matches(host, site):
                continue
            if any(_host_matches(host, a) for a in autorizados):
                continue
            return [Issue(
                code="external_cta_nao_autorizado",
                message=(f"Botão manda o clique comprado para {host}, que não é o "
                         "canal escolhido pela pesquisa desta página. Destino "
                         "externo não escolhido pode ser citado no texto, "
                         "nunca virar botão."))]
    return []


def no_bare_rec(content: str, ctx: dict) -> list[Issue]:
    post_type = ctx.get("post_type", "rec")
    for m in _HREF_SRC_RE.finditer(content):
        if urlparse(m.group(1)).path.rstrip("/").endswith("/" + post_type):
            return [Issue(code="bare_rec",
                          message=f"Link morto para /{post_type} sem destino de funil.")]
    return []


def no_self_loop(content: str, ctx: dict) -> list[Issue]:
    slug = (ctx.get("slug") or "").strip().strip("/")
    post_type = ctx.get("post_type", "rec")
    if not slug:
        return []
    for m in _HREF_SRC_RE.finditer(content):
        if urlparse(m.group(1)).path.strip("/") == f"{post_type}/{slug}":
            return [Issue(code="self_loop", message="Botão aponta para a própria página (loop).")]
    return []


_CNPJ_RE = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")


def identity(content: str, ctx: dict) -> list[Issue]:
    issues: list[Issue] = []
    expected = (ctx.get("cnpj") or "").strip()
    low = content.lower()
    for m in _CNPJ_RE.finditer(content):
        if expected and m.group(0) != expected:
            issues.append(Issue(code="wrong_cnpj",
                                message=f"CNPJ {m.group(0)} diverge do CNPJ do site."))
            break
    if "[razão social" in low or "[razao social" in low:
        issues.append(Issue(code="placeholder_cnpj",
                            message="Placeholder '[Razão Social' não substituído."))
    if "licenciado pelo sated" in low:
        issues.append(Issue(code="fake_credential",
                            message="Credencial fabricada 'licenciado pelo SATED' (proibido)."))
    return issues


def forward_only(content: str, ctx: dict) -> list[Issue]:
    """SOLUTION pages route forward-only: a `funnel` route may only advance to a
    SOLUTION of STRICTLY HIGHER ordinal (see routing.py's build_funnel_routes).
    A terminal SOLUTION (last ordinal) has no forward routes at all -- it only
    recirculates cross-funnel -- so it is always a no-op here. `ctx['parsed']`
    holds the already-extracted `routes` (kind/target pairs); `solution_order`
    maps slug -> ordinal, as `_write_ctx` builds it."""
    if ctx.get("is_terminal"):
        return []
    order = ctx.get("solution_order") or {}
    own = order.get(ctx.get("slug"), 0)
    parsed = ctx.get("parsed") or {}
    routes = _field(parsed, "routes", []) or []
    issues: list[Issue] = []
    for route in routes:
        if _field(route, "kind") != "funnel":
            continue
        target = _field(route, "target")
        if order.get(target, 0) <= own:
            issues.append(
                Issue(
                    code="not_forward",
                    message=(
                        f"Rota funnel para '{target}' não avança o funil "
                        f"(ordinal {order.get(target, 0)} <= {own})."
                    ),
                )
            )
    return issues


# A wp:paragraph block whose CLOSE sits at the very end of the scanned prefix
# -- i.e. the block IMMEDIATELY before whatever follows. The tempered inner
# `(?:(?!...).)*?` never crosses another paragraph close, so it captures ONLY
# that last paragraph (never spans an earlier one, which would let a distant
# mention false-pass the bridge check).
_END_PARAGRAPH_RE = re.compile(
    r"<!--\s*wp:paragraph\b[^>]*?-->"
    r"((?:(?!<!--\s*/wp:paragraph).)*?)"
    r"<!--\s*/wp:paragraph\s*-->\s*\Z",
    re.I | re.S,
)


def _preceding_paragraph_text(content: str, pos: int) -> str | None:
    """Visible text of the wp:paragraph block IMMEDIATELY before `pos` (a
    wp:buttons block start), or None when the block right before it is NOT a
    real bridge paragraph -- a heading, another buttons block, a spacer/
    separator, or the '* Voce permanece *' nota / 'utilidade publica' aviso
    (system/compliance prose, never a bridge) all return None. Shared by
    `bridge_before_cta` (structure) and `cta_destination_congruent` (the bridge
    half of the congruence check)."""
    prefix = content[:pos].rstrip()
    m = _END_PARAGRAPH_RE.search(prefix)
    if not m:
        return None
    inner = m.group(1)
    if _NOTA_PERMANECE_RE.search(inner) or _AVISO_UTILIDADE_RE.search(inner):
        return None
    return _INNER_TAG_RE.sub("", inner).strip()


def _dest_slug(href: str) -> str:
    """Destination slug the card keys congruence on: the last non-empty path
    segment of the href. '' when the href carries no path."""
    path = urlparse(href).path.rstrip("/")
    return path.rsplit("/", 1)[-1] if path else ""


_CTA_TOKEN_RE = re.compile(r"[a-z0-9à-ü]{3,}")
# Short (3-char) fillers that are NOT destination-salient -- excluded so they
# never count as a "distinctive" term. `pix`, `clt`, `cpf`, `inss`, `fgts` are
# deliberately NOT here: they are exactly the salient short terms `_sig_tokens`
# (>=4 chars) drops, and the reason a good "via Pix" button was false-flagged.
_CTA_STOP3 = {"via", "com", "sem", "por", "dos", "das", "uma", "aos", "nao",
              "voce", "meu", "sua", "seu", "que", "isso", "essa", "esse", "tem",
              "ate", "mais", "rec", "http", "www"}


def _cta_tokens(text: str) -> set[str]:
    """>=3-char tokens for CTA↔destination congruence, so SALIENT short terms
    (pix, clt, cpf, inss) count -- `_sig_tokens` (>=4) drops them, which
    false-flagged legitimate PIX buttons. Minus the shared stopword sets."""
    return {t for t in _CTA_TOKEN_RE.findall(text.lower())
            if t not in _STOP and t not in _CTA_STOP3}


def _slug_tokens(slug: str) -> set[str]:
    """Distinctive-worthy segments of a destination slug (e.g.
    'emprestimo-na-hora-via-pix-p1' -> {emprestimo, hora, pix}). The ordinal
    tail 'pN' and short fillers are dropped. This is what makes 'pix'/'clt'
    recoverable as distinctive terms."""
    return {t for t in _cta_tokens(slug.replace("-", " "))
            if not re.fullmatch(r"p\d+", t)}


def _distinctive_tokens(dest_h1: str, dest_slug: str, sibling_h1s: dict) -> set[str]:
    """Tokens (H1 + slug segments, >=3 chars) that identify the destination and
    NO sibling solution shares -- the destination's own theme minus the common
    funnel theme (kills the false pass by the shared theme token, e.g. 'FGTS').
    Including the SLUG segments recovers salient short terms like 'pix'/'clt'
    that the >=4-char H1 tokenizer drops. Empty when the destination shares every
    token with its siblings (nothing distinctive to demand -> fail-open)."""
    own = _cta_tokens(dest_h1) | _slug_tokens(dest_slug)
    shared: set[str] = set()
    for slug, h1 in (sibling_h1s or {}).items():
        if slug == dest_slug:
            continue
        shared |= _cta_tokens(h1) | _slug_tokens(slug)
    return own - shared


def cta_destination_congruent(content: str, ctx: dict) -> list[Issue]:
    """HARD GATE (CARD-0011 REQ-2 / OVERRIDE-4): every funnel advance BUTTON must
    tell the truth about where it goes. For each wp:buttons anchor whose
    destination slug (last path segment of its href) is a known funnel page, the
    button LABEL and/or the bridge paragraph immediately BEFORE its block must
    contain >=1 DISTINCTIVE token of the destination H1 -- a sig token the
    sibling solutions do NOT share -- so the common funnel theme (e.g. 'FGTS')
    can never false-pass.

    SOLUTION-only. external_official and cross_funnel anchors are EXEMPT: their
    destination slug is not among this funnel's `h1_by_slug`, so the lookup
    misses and the button is skipped (cross_funnel needs only the structural
    bridge). Two FAIL-OPENs mirror `_anchor_congruent`'s lesson -- never block a
    good page for missing context: (a) an unknown destination H1, and (b) a
    destination that shares every token with its siblings (no distinctive token
    to demand).

    PRESELL is ALSO in scope, but only for the MID-TEXT buttons (one after each
    H2): the hero "escolha seu caminho" fan-out (the 3 buttons before the first
    H2) is already congruent via its resolved anchors, so it is exempt -- the
    scan starts at the first wp:heading. A presell with no H2 has no mid-text
    button to check."""
    role = _ctx_role(ctx)
    if role not in (PageRole.SOLUTION, PageRole.PRESELL):
        return []
    scan_from = 0
    if role is PageRole.PRESELL:
        heading = _FIRST_HEADING_RE.search(content)
        scan_from = heading.start() if heading else len(content)
    h1_by_slug = ctx.get("h1_by_slug") or {}
    sibling_h1s = ctx.get("sibling_h1s") or {}
    issues: list[Issue] = []
    for block in _BUTTONS_BLOCK_RE.finditer(content):
        if block.start() < scan_from:
            continue  # PRESELL hero fan-out (pre-H2) is exempt
        bridge = _preceding_paragraph_text(content, block.start()) or ""
        bridge_tokens = _cta_tokens(bridge)
        for label, href in _cta_links(block.group(0)):
            dest_h1 = h1_by_slug.get(_dest_slug(href))
            if not dest_h1:
                continue  # fail-open: external/cross/unknown destination
            distinctive = _distinctive_tokens(dest_h1, _dest_slug(href), sibling_h1s)
            if not distinctive:
                continue  # fail-open: nothing distinguishes this destination
            if not ((_cta_tokens(label) | bridge_tokens) & distinctive):
                issues.append(
                    Issue(
                        code="cta_incongruent",
                        message=(
                            f"Botao de avanco para '{_dest_slug(href)}' nao anuncia o "
                            f"destino: nem o texto nem a ponte citam um termo distintivo "
                            f'de "{dest_h1}".'
                        ),
                    )
                )
    return issues


def bridge_before_cta(content: str, ctx: dict) -> list[Issue]:
    """STRUCTURAL gate (CARD-0011 REQ-2 / OVERRIDE-4 -- structure ONLY, semantic
    congruence is prompt + judge + `cta_destination_congruent`): every NON-hero
    wp:buttons block must be IMMEDIATELY preceded by a real wp:paragraph -- the
    pre-CTA bridge. A heading, the '* Voce permanece *' nota, an 'utilidade
    publica' aviso, another buttons block, or a spacer/separator right before a
    button is NOT a bridge. The HERO button (the FIRST buttons block) is exempt:
    its bridge is the intro paragraph (an extra pre-H2 bridge would trip
    `short_intro`). SOLUTION-only."""
    if _ctx_role(ctx) is not PageRole.SOLUTION:
        return []
    issues: list[Issue] = []
    for i, block in enumerate(_BUTTONS_BLOCK_RE.finditer(content)):
        if i == 0:
            continue  # hero button -- its bridge is the intro paragraph
        if _preceding_paragraph_text(content, block.start()) is None:
            issues.append(
                Issue(
                    code="missing_bridge",
                    message=(
                        "Botao de avanco sem ponte: todo bloco de botoes que nao seja o "
                        "hero precisa de um paragrafo de prosa imediatamente antes, "
                        "enquadrando o destino."
                    ),
                )
            )
    return issues


# ---------------------------------------------------------------------------
# Publication contracts.  These run once during generation and again against
# the final post-widget draft, so normalizers/injectors cannot invalidate a
# page after its only validation pass.
# ---------------------------------------------------------------------------

# ⚠️ O comentário de bloco do Gutenberg ACEITA ATRIBUTOS
# (`<!-- wp:html {"lock":{"move":false}} -->`), e a versão antiga exigia o
# comentário SECO. Um bloco de HTML cru declarado com atributos escapava dos
# DOIS lados da mesma regex: `raw_html_contract` nunca via o <p> dentro dele, e
# o "never touch raw html" do enhancer não o reconhecia -- então o normalizador
# reescrevia <li> e quebrava parágrafos DENTRO do widget.
_RAW_HTML_BLOCK_RE = re.compile(
    r"<!--\s*wp:html(?![\w-])(?:(?!-->)[\s\S])*?-->"
    r"([\s\S]*?)"
    r"<!--\s*/wp:html\s*-->",
    re.I,
)
_ANY_RAW_PARAGRAPH_RE = re.compile(r"<p\b", re.I)
_AD_DIRECTION_RE = re.compile(
    r"\b(?:clique|escolha|marque|preencha|responda|selecione|toque|use|veja)\b"
    r"[^.!?]{0,80}\b(?:abaixo|acima|a seguir|logo depois|na próxima)\b",
    re.I,
)


# Blocos DECORATIVOS não separam nada: dois grupos de botões com um spacer ou
# um separator no meio continuam sendo dois grupos de botões colados. A regra
# antiga exigia adjacência literal, então UM separador a desligava.
_DECORATIVO_ENTRE = (
    r"(?:\s*(?:"
    r"<!--\s*wp:(?:spacer|separator)(?![\w-])(?:(?!-->)[\s\S])*?/-->"
    r"|<!--\s*wp:(?:spacer|separator)(?![\w-])(?:(?!-->)[\s\S])*?-->"
    r"[\s\S]*?<!--\s*/wp:(?:spacer|separator)\s*-->"
    r"))*\s*"
)
_ADJACENT_BUTTONS_RE = re.compile(
    r"<!--\s*/wp:buttons\s*-->" + _DECORATIVO_ENTRE + r"<!--\s*wp:buttons(?![\w-])",
    re.I,
)
_ADJACENT_GROUPS_RE = re.compile(
    r"<!--\s*/wp:group\s*-->\s*<!--\s*wp:group(?![\w-])((?:(?!-->)[\s\S])*?)-->",
    re.I,
)
# A margem tem de EXISTIR e ser DIFERENTE DE ZERO. O teste antigo era de
# SUBSTRING (`'"margin"' not in attrs`), então `{"margin":{"top":"0px"}}`
# continha a palavra, separava nada, e passava -- os dois grupos seguiam
# colados na tela, que é exatamente o defeito que a regra existe para pegar.
_MARGIN_OBJ_RE = re.compile(r'"margin"\s*:\s*\{((?:[^{}]|\{[^{}]*\})*)\}')
_MARGIN_SHORTHAND_RE = re.compile(r'"margin"\s*:\s*"([^"]*)"')
_MARGIN_SIDE_RE = re.compile(r'"(top|bottom)"\s*:\s*"([^"]*)"', re.I)
_ZERO_LENGTH_RE = re.compile(
    r"\A0+(?:[.,]0+)?\s*(?:px|rem|em|%|pt|vh|vw|ch|ex)?\Z", re.I)


def _margem_vertical_real(attrs: str) -> bool:
    """True quando os atributos do bloco declaram margem SUPERIOR ou INFERIOR
    com valor não-nulo. Só `top`/`bottom` contam: margem lateral não separa
    dois irmãos empilhados. Um preset (`var:preset|spacing|30`) conta como
    margem real -- o valor é resolvido pelo tema, e não é zero."""
    valores: list[str] = []
    for obj in _MARGIN_OBJ_RE.findall(attrs):
        valores.extend(valor for _lado, valor in _MARGIN_SIDE_RE.findall(obj))
    valores.extend(_MARGIN_SHORTHAND_RE.findall(attrs))
    return any(v.strip() and not _ZERO_LENGTH_RE.match(v.strip()) for v in valores)


def raw_html_contract(content: str, ctx: dict) -> list[Issue]:
    issues: list[Issue] = []
    for block in _RAW_HTML_BLOCK_RE.findall(content):
        # Deliberately ``<p\b`` rather than ``<p>``: attributes and empty
        # variants are equally unsafe to paragraph-counting themes/plugins.
        if _ANY_RAW_PARAGRAPH_RE.search(block):
            issues.append(Issue(
                code="paragraph_in_raw_html",
                message=("Bloco wp:html contém <p>; use div/span para ficar fora "
                         "do contador de anúncios."),
            ))
            break
    if re.search(r"\bis-style-outline\b", content, re.I):
        issues.append(Issue(code="outline_button",
                            message="Botão outline não é permitido no artefato publicável."))
    if _ADJACENT_BUTTONS_RE.search(content):
        issues.append(Issue(
            code="adjacent_button_groups",
            message=("Grupos wp:buttons consecutivos -- inclusive quando só um "
                     "spacer/separator os separa -- precisam ser um único grupo "
                     "ou ter prosa entre eles."),
        ))
    for match in _ADJACENT_GROUPS_RE.finditer(content):
        if not _margem_vertical_real(match.group(1)):
            issues.append(Issue(
                code="adjacent_groups_without_margin",
                message=("Grupos wp:group irmãos exigem margem vertical explícita e "
                         "NÃO-NULA no segundo bloco (margem zero não separa nada)."),
            ))
            break
    return issues


def ad_interaction(content: str, ctx: dict) -> list[Issue]:
    """Keep editorial direction and widgets independent from ad insertion."""
    without_raw = _RAW_HTML_BLOCK_RE.sub("", content)
    issues: list[Issue] = []
    paragraph_re = re.compile(
        r"<!--\s*wp:paragraph\b[^>]*-->\s*<p\b[^>]*>(.*?)</p>\s*"
        r"<!--\s*/wp:paragraph\s*-->", re.S | re.I)
    for index, match in enumerate(paragraph_re.finditer(without_raw), start=1):
        text = _INNER_TAG_RE.sub(" ", match.group(1))
        if _AD_DIRECTION_RE.search(text):
            anchors = set(int(n) for n in (ctx.get("ad_paragraph_anchors") or []) if int(n) > 0)
            zone = " (na zona de anúncio)" if index in anchors or index - 1 in anchors else ""
            issues.append(Issue(
                code="directional_copy_outside_widget",
                message=(f"Parágrafo editorial {index}{zone} orienta por posição; "
                         "a instrução deve viver dentro do componente interativo."),
            ))
    return issues


VISUAL_BLOCKS_BY_ENGAGEMENT: dict[str, tuple[str, ...]] = {
    "condicional": ("details", "columns"),
    "sequencial": ("details", "list"),
    "comparativo": ("details", "table", "columns"),
    "diagnostico": ("details", "columns"),
    "dado_unico": ("details", "table"),
}
# O BLOCO-ASSINATURA de cada forma de pergunta -- o bloco visual que a página
# é OBRIGADA a usar pelo menos uma vez.
#
# Antes o prompt escolhia esse bloco por `[...][(page_num) % 3]`: um sorteio
# posicional. A mesma página, renumerada (e o step_extract renumera), mudava de
# contrato visual sem que uma vírgula do conteúdo mudasse -- e o bloco sorteado
# não tinha relação nenhuma com os blocos que o `visual_contract` fiscaliza.
# Eram dois contratos discordando sobre a mesma página.
#
# Agora a escolha vem da FORMA DA PERGUNTA já classificada (Page.engajamento),
# a MESMA chave do VISUAL_BLOCKS_BY_ENGAGEMENT acima -- a forma visual passa a
# ser consequência do conteúdo. Não é portão novo: para comparativo/dado_unico
# e condicional/diagnostico o visual_contract JÁ exige table/columns.
SIGNATURE_BLOCK_BY_ENGAGEMENT: dict[str, str] = {
    "comparativo": "TABELA COMPARATIVA (wp:table)",   # compara opções lado a lado
    "dado_unico": "TABELA COMPARATIVA (wp:table)",    # um número só precisa de contexto ao lado
    "condicional": "DUAS COLUNAS (wp:columns)",       # "se A / se B" é layout de duas colunas
    "diagnostico": "DUAS COLUNAS (wp:columns)",       # sintoma de um lado, conduta do outro
    "sequencial": "PULLQUOTE (wp:pullquote)",         # o passo a passo já é lista; falta o respiro
}


def visual_contract(content: str, ctx: dict) -> list[Issue]:
    """Map the declared question shape to deterministic native block types.

    ⚠️ O SILÊNCIO ACABOU -- E A ASSIMETRIA COM O WIDGET FICOU DECLARADA.

    Antes, QUALQUER rótulo fora do mapa fazia a função devolver `[]`, isto é,
    "aprovado": um `sustenta` (a escala binária nova do motor de pautas), um
    `Dado Único` com acento ou um erro de digitação apagavam o portão inteiro
    sem uma linha de log -- enquanto `widget_archetype_for`, lendo o MESMO
    campo, aplicava `infer_engajamento` e seguia trabalhando. Um lado inferia, o
    outro desistia calado, e ninguém tinha declarado isso.

    Agora são DOIS casos, e a diferença entre eles é o ponto:

    - NADA DECLARADO ("") -> fail-open EXPLÍCITO. `Page.engajamento` vazio é um
      estado legítimo (`declarar_engajamento` nem roda sem `steps.engajamento`
      na config). BLOQUEAR aqui exigiria inferir, e inferir para bloquear é o
      que este portão não pode fazer: `infer_engajamento` é heurística de
      palavra-chave, e reprovar uma página porque o H1 dela tinha "como" seria
      o portão inventando um requisito que ninguém declarou. Escolher ferramenta
      por inferência é seguro; reprovar publicação por inferência não é.
    - RÓTULO DECLARADO QUE NÃO RESOLVE -> Issue, alto e claro. Aqui alguém
      declarou algo e o portão não conseguiu honrar: isso é defeito, não
      ausência. Quem canoniza e traduz a escala binária antes do ctx é
      `steps.engajamento_declarado`.
    """
    if _ctx_role(ctx) is not PageRole.SOLUTION:
        return []
    bruto = str(ctx.get("engajamento") or "").strip()
    engagement = canon_engajamento(bruto)
    if not engagement:
        return []  # fail-open declarado: a página não declarou forma nenhuma
    requirements = VISUAL_BLOCKS_BY_ENGAGEMENT.get(engagement)
    if requirements is None:
        motivo = (
            "é NÍVEL da escala binária do motor de pautas, não forma de pergunta"
            if engagement in NIVEIS_BINARIOS
            else "não está no vocabulário de formas de pergunta"
        )
        return [Issue(
            code="engajamento_nao_resolvido",
            message=(
                f"Contrato visual desligado por rótulo inutilizável: {bruto!r} {motivo} "
                f"({', '.join(sorted(VISUAL_BLOCKS_BY_ENGAGEMENT))}). "
                "Traduza com `steps.engajamento_declarado` antes de montar o ctx."
            ),
        )]
    issues: list[Issue] = []
    for block in requirements:
        if not re.search(rf"<!--\s*wp:{re.escape(block)}\b", content, re.I):
            issues.append(Issue(
                code="missing_semantic_block",
                message=f"Engajamento {engagement!r} exige bloco wp:{block}.",
            ))
    return issues

_JSON_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n?|```\s*$")


def tolerant_json_object(text: str) -> dict:
    """Extrai um objeto JSON de uma saída de LLM que pode vir cercada/decorada.

    Tira as cercas ```json, pega do primeiro `{` ao último `}` e faz o parse.
    Levanta ValueError quando não há objeto JSON algum. Esta é a ÚNICA cópia
    viva do parser: `steps._tolerant_json` delega para cá (o validador da LP
    precisa dele e não pode importar de `steps`, que importa este módulo).
    """
    stripped = _JSON_FENCE_RE.sub("", (text or "").strip()).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("nenhum objeto JSON encontrado na saída do modelo")
    return json.loads(stripped[start:end + 1])


def lp_json_contract(content: str, ctx: dict) -> list[Issue]:
    """O contrato da LANDING PAGE, dentro do runner -- com retry.

    A LP não é HTML: é o JSON que preenche o template Elementor. Os validadores
    de página interior não servem aqui e, pior, MENTEM: `_cta_texts` só enxerga
    marcadores `=== WIDGET: BOTÃO ===` ou blocos `wp:buttons`, então `cta_style`
    sobre o JSON da LP devolve lista vazia -- seria um portão que sempre passa,
    exatamente a pior espécie de portão.

    Este aqui fala a língua da LP: parseia o JSON e delega ao
    `validate_lp_content`, o MESMO contrato que o `step_write` aplica (schema,
    intro de 1 parágrafo, gravata tátil, 3 CTAs, doutrina de copy). Registrá-lo
    como VALIDADOR é o que transforma a reprovação em FEEDBACK e nova tentativa,
    em vez de morte no primeiro tiro.
    """
    try:
        parsed = tolerant_json_object(content)
    except ValueError as exc:  # json.JSONDecodeError herda de ValueError
        return [Issue(code="parse_error",
                      message=f"Saída da LP não é um JSON válido: {exc}")]
    if not isinstance(parsed, dict):
        return [Issue(code="parse_error",
                      message="Saída da LP não é um objeto JSON.")]
    return validate_lp_content(parsed)


def _normalized_claim(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = re.sub(r"\s+", " ", folded).strip().lower()
    # ⚠️ O ESPAÇO ANTES DO `%` CONDENAVA PÁGINA COMPARATIVA INTEIRA.
    #
    # `critical_fact_grounding` monta a agulha com `" ".join((valor, unidade,
    # dispositivo))`, e o `VerifiedFact` guarda valor e unidade SEPARADOS:
    # `valor="0,57"`, `unidade="%"` vira `"0,57 % regulamento..."`. O texto,
    # porém, escreve das duas formas — `<a>0,57 %</a>` na prosa e `<td>0,57%</td>`
    # na tabela. Sem esta linha, `"0,57%" in "0,57 % regulamento..."` é False, e
    # o mesmo número, ancorado no mesmo fato, recebia dois vereditos diferentes
    # por causa de um espaço.
    #
    # Medido em 18/08/2026, run `maquininha-de-cartao-...-112043`, página 4:
    # NOVE `ungrounded_critical_claim`, todos porcentagem, todos com fato tipado
    # em `fatos_verificados` e `fonte_primaria` dentro de `fontes_resolvidas`.
    # 9 dos 10 fatos daquela página tinham `unidade="%"` — e uma página
    # comparativa é feita de tabela, então ela condenava a si mesma.
    #
    # Isto NÃO afrouxa o portão: continua sendo exigido fato tipado com fonte
    # resolvida. Só faz `0,57%` e `0,57 %` serem o mesmo token dos dois lados.
    return re.sub(r"(\d)\s+%", r"\1%", folded)


# Uma afirmação que é PURA QUANTIDADE: opcional `R$`, dígitos com separadores,
# opcional `%`. Só estas seguem o caminho numérico; referência legal ("Lei
# 8.036/1990") e prazo ("60 dias") continuam no caminho de substring, porque
# neles o número não é o que se compara.
_QUANTIA_RE = re.compile(r"^(?:r\$\s*)?\d[\d.,]*\s*%?$")
_NUM_RE = re.compile(r"\d[\d.,]*\d|\d")


def _canon_numero(texto: str) -> str | None:
    """`0,57` · `0.57` · `1.234,56` · `R$ 500,00` → `0.57` · `0.57` · `1234.56` · `500`.

    ⚠️ O SEPARADOR DECIMAL NÃO PODE SER ADIVINHADO POR TROCA CEGA.

    Em pt-BR `1.000` é mil e `1,000` é um. Trocar `.` por `,` sem olhar faria
    um fato de "1,000" ancorar uma afirmação de "1.000" — errando por mil vezes
    numa página que fala de dinheiro. A regra usada aqui é a padrão: com os dois
    separadores, o ÚLTIMO é o decimal; com um só, ele é decimal apenas quando
    sobram 1 ou 2 dígitos depois dele (grupo de milhar tem exatamente 3).
    """
    m = _NUM_RE.search(texto)
    if m is None:
        return None
    bruto = m.group(0)

    tem_ponto, tem_virgula = "." in bruto, "," in bruto
    if tem_ponto and tem_virgula:
        decimal = "," if bruto.rfind(",") > bruto.rfind(".") else "."
    elif tem_ponto or tem_virgula:
        sep = "." if tem_ponto else ","
        cauda = bruto.rsplit(sep, 1)[1]
        # 3 dígitos depois do separador = grupo de milhar, não decimal.
        decimal = sep if (len(cauda) in (1, 2) and bruto.count(sep) == 1) else ""
    else:
        decimal = ""

    limpo = []
    for ch in bruto:
        if ch.isdigit():
            limpo.append(ch)
        elif decimal and ch == decimal:
            limpo.append(".")
    texto_limpo = "".join(limpo)
    if not texto_limpo or texto_limpo == ".":
        return None
    try:
        return format(Decimal(texto_limpo).normalize(), "f")
    except InvalidOperation:
        return None


def _unidade_compativel(afirmacao: str, unidade: str) -> bool:
    """A unidade da afirmação bate com a que o fato declara?

    ⚠️ A pesquisa escreve a unidade como quiser: medido em 18/08/2026 no mesmo
    run, a página 4 gravou `unidade="%"` e a página 6 gravou
    `unidade="Percentual (%)"` para a MESMA grandeza. Exigir string igual
    reprovaria metade das páginas por escolha de redação do próprio motor.
    """
    u = _normalized_claim(unidade)
    if "%" in afirmacao:
        return "%" in u or "percent" in u
    if "r$" in afirmacao.lower():
        return "r$" in u or "reais" in u or "real" in u or "brl" in u
    # Quantidade sem símbolo: a unidade não desempata, e exigir que ela
    # desempate rejeitaria fato legítimo com `unidade` vazia.
    return True


def _visible_fact_text(content: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", content, flags=re.S | re.I)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    return _INNER_TAG_RE.sub(" ", text)


_CRITICAL_CLAIM_RE = re.compile(
    r"R\$\s*\d[\d.]*?(?:,\d{1,2})?\b"
    r"|\b\d+(?:[.,]\d+)?\s*%"
    r"|\b\d+\s*(?:dias?|meses?|anos?)\b"
    r"|\b(?:lei|resolu[cç][aã]o|decreto|portaria|instru[cç][aã]o\s+normativa|circular)"
    r"(?:\s+[A-ZÀ-Ü]{2,8})?(?:\s+n[ºo.]*)?\s*[\d.]+(?:/\d{2,4})?",
    re.I,
)
_LEGAL_FORCE_RE = re.compile(
    r"\b(?:a\s+lei|a\s+legisla[cç][aã]o|a\s+norma|a\s+resolu[cç][aã]o|"
    r"[ée]\s+obrigat[oó]ri[oa]|[ée]\s+proibid[oa]|n[aã]o\s+tem\s+direito|"
    r"tem\s+direito|direito\s+garantido|o\s+sistema\s+exige)\b",
    re.I,
)
_CLAIM_STOPWORDS = frozenset({
    "para", "como", "pela", "pelo", "essa", "esse", "esta", "este",
    "direito", "sistema", "regra", "norma", "obrigatorio", "obrigatoria",
})


def _claim_terms(value: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{4,}", _normalized_claim(value))
            if w not in _CLAIM_STOPWORDS}


def critical_fact_grounding(content: str, ctx: dict) -> list[Issue]:
    """Every critical numeric/legal claim must map to a resolved typed fact.

    ⚠️ SEM `facts` NO CONTEXTO, ISTO ERA UM NO-OP SILENCIOSO.

    O `return []` de antes fazia o portão APROVAR qualquer coisa quando o
    chamador esquecia de passar os fatos — e aprovar em silêncio é o pior
    desfecho possível para um portão: quem lê o resultado não distingue "não
    havia nada a reprovar" de "eu não fui capaz de olhar".

    Medido no run #6: `widget_p3` gravou OK, o widget com "30 a 60 dias" foi
    injetado, e o `content_gate` reprovou a página inteira pelo mesmo texto —
    com pesquisa, redação, juiz, SEO, imagem e widget já pagos. Rodando o
    validador à mão no mesmo bloco com os mesmos fatos, ele ACUSA as duas
    afirmações. Ou seja: no run, ele não recebeu os fatos.

    Agora, faltando o contexto, o portão diz que não conseguiu olhar. Se houver
    afirmação crítica no texto, isso é uma reprovação — o passo retenta ou a
    página cai, mas ninguém publica número não conferido achando que conferiu.
    """
    facts_obj = ctx.get("facts")
    if facts_obj is None:
        if not _CRITICAL_CLAIM_RE.search(_visible_fact_text(content)):
            return []      # nada de crítico no texto: não há o que ancorar
        return [Issue(
            code="fact_grounding_sem_contexto",
            message=("Há afirmação crítica no texto, mas os fatos da pesquisa não "
                     "chegaram a este portão — não deu para conferir nada. "
                     "Fiação quebrada no chamador, não conteúdo ruim."),
        )]
    strict = _field(facts_obj, "fatos_verificados", []) or []
    resolved = set(_field(facts_obj, "fontes_resolvidas", []) or [])
    trusted = [f for f in strict if str(_field(f, "fonte_primaria", "")) in resolved]
    visible = _visible_fact_text(content)
    issues: list[Issue] = []
    seen: set[str] = set()
    for match in _CRITICAL_CLAIM_RE.finditer(visible):
        raw = re.sub(r"\s+", " ", match.group(0)).strip()
        claim = _normalized_claim(raw)
        if claim in seen:
            continue
        seen.add(claim)
        # ⚠️ QUANTIDADE CASA POR NÚMERO, NÃO POR SUBSTRING.
        #
        # A agulha antiga era `" ".join((valor, unidade, dispositivo))` e a
        # afirmação era procurada dentro dela. Isso falhava dos dois lados:
        #
        #   erra reprovando — medido em 18/08/2026, mesmo run:
        #     p4  `valor="0,57"` `unidade="%"`              texto `0,57%`
        #     p6  `valor="0.57"` `unidade="Percentual (%)"` texto `0.57%`
        #     Nenhuma das duas casava: separador decimal e grafia da unidade
        #     são escolha livre da pesquisa, e o texto cola o símbolo no número.
        #
        #   erra aprovando — `"r$ 500" in "r$ 5000,00 ..."` é True. Um fato de
        #     cinco mil ancorava uma afirmação de quinhentos, por prefixo.
        #
        # Comparar o número canonizado e conferir a unidade conserta os dois: é
        # mais permissivo com grafia e mais ESTRITO com valor.
        quantia = bool(_QUANTIA_RE.match(claim))
        numero = _canon_numero(claim) if quantia else None

        grounding = None
        for fact in trusted:
            valor = str(_field(fact, "valor", ""))
            unidade = str(_field(fact, "unidade", ""))
            if numero is not None:
                if (_canon_numero(valor) == numero
                        and _unidade_compativel(claim, unidade)):
                    grounding = fact
                    break
                continue
            haystack = _normalized_claim(" ".join((
                valor, unidade, str(_field(fact, "dispositivo", "")),
            )))
            if claim in haystack:
                grounding = fact
                break
        if grounding is None:
            issues.append(Issue(
                code="ungrounded_critical_claim",
                message=f"Afirmação crítica sem fato tipado e fonte resolvida: {raw!r}.",
            ))
            continue
        source = str(_field(grounding, "fonte_primaria", ""))
        if source not in content:
            issues.append(Issue(
                code="critical_claim_without_citation",
                message=f"Afirmação crítica {raw!r} não cita sua fonte primária no conteúdo.",
            ))

    # Consequential legal assertions can be false even without a number or an
    # explicit statute identifier ("tem direito", "é obrigatório"). Require a
    # resolved fact with an actual legal device and lexical connection to the
    # sentence, plus the same source-citation rule.
    for sentence in re.split(r"(?<=[.!?])\s+", visible):
        if not _LEGAL_FORCE_RE.search(sentence):
            continue
        sentence_norm = _normalized_claim(sentence)
        if sentence.strip().endswith("?") or re.search(
            r"\b(?:quem|ver quem|descobrir quem|como saber quem) tem direito\b",
            sentence_norm,
        ):
            continue  # question/FAQ heading is not a factual assertion
        terms = _claim_terms(sentence)
        grounding = None
        for fact in trusted:
            device = str(_field(fact, "dispositivo", "") or "")
            if _normalized_claim(device) in {"", "nao se aplica", "n/a"}:
                continue
            fact_terms = _claim_terms(
                f"{_field(fact, 'valor', '')} {device}")
            if len(terms & fact_terms) >= 2:
                grounding = fact
                break
        raw_sentence = re.sub(r"\s+", " ", sentence).strip()
        if grounding is None:
            issues.append(Issue(
                code="ungrounded_legal_claim",
                message=f"Afirmação de força legal sem dispositivo verificável: {raw_sentence!r}.",
            ))
        else:
            source = str(_field(grounding, "fonte_primaria", ""))
            if source not in content:
                issues.append(Issue(
                    code="critical_claim_without_citation",
                    message=f"Afirmação legal não cita sua fonte primária: {raw_sentence!r}.",
                ))
    return issues


VALIDATORS: dict[str, Callable[[str, dict], list[Issue]]] = {
    "language_pt": language_pt,
    "cta_style": cta_style,
    "pagespec": pagespec_validator,
    "calm_utility": calm_utility,
    "gutenberg_blocks": gutenberg_blocks,
    "compliance": compliance,
    "length_p1": length_p1,
    "interior_min_length": interior_min_length,
    "no_trailing_buttons": no_trailing_buttons,
    "no_leading_buttons": no_leading_buttons,
    "short_intro": short_intro,
    "min_headings": min_headings,
    "winning_lp": winning_lp,
    "seo_limits": seo_limits,
    "has_sources": has_sources,
    "research_facts_contract": research_facts_contract,
    "funnel_schema": funnel_schema,
    "same_domain": same_domain,
    "official_link_density": official_link_density,
    "external_cta_authorized": external_cta_authorized,
    "no_bare_rec": no_bare_rec,
    "no_self_loop": no_self_loop,
    "identity": identity,
    "uniqueness": uniqueness_guard,
    "opening_line_unique": opening_line_unique,
    "forward_only": forward_only,
    "cta_destination_congruent": cta_destination_congruent,
    "bridge_before_cta": bridge_before_cta,
    "critical_fact_grounding": critical_fact_grounding,
    "raw_html_contract": raw_html_contract,
    "ad_interaction": ad_interaction,
    "visual_contract": visual_contract,
    "lp_json_contract": lp_json_contract,
}


def run_validators(
    names: list[str],
    content: str,
    ctx: dict
) -> list[Issue]:
    out: list[Issue] = []
    for name in names:
        out.extend(VALIDATORS[name](content, ctx))
    return out


# ---------------------------------------------------------------------------
# CARD-0013: widget sanitization battery (OVERRIDE-4, decisão FECHADA).
#
# `sanitize_widget_block(block)` is a PURE function (NOT a `(content, ctx)`
# validator, so it is deliberately NOT registered in VALIDATORS): the widget
# subsystem consumes it DIRECTLY by import from `step_widget`, because the real
# execution point is POST-write/POST-build -- registering it in write_page
# validators (briefing §4.5) would be a no-op there. It is a HARD ALLOWLIST +
# BLOCKER battery, NOT a JS parser: there is NO `new Function`/eval of the
# widget code here (the removed `script_syntax_error` gate). Any Issue it
# returns == reject the widget (the article publishes intact, no widget).
#
# The widget is the ONLY place a <script> may reach a published page, and even
# then only after passing every check below; the ARTICLE BODY stays script-free
# via the separate write-time `gutenberg_blocks`/`has_script` gate.
# ---------------------------------------------------------------------------

# Structural HTML allowlist mirrored VERBATIM in prompts/redator_widget.jinja so
# the generator only ever emits what survives here. `<script>`/`<style>` are the
# CSS/JS carriers and are handled by dedicated checks, so their ELEMENTS are
# stripped before the tag scan -- they are never in this content-tag set.
_WIDGET_ALLOWED_TAGS = frozenset({
    "div", "span", "strong", "em", "ul", "li", "h3", "h4",
    "button", "input", "label", "select", "option", "section",
})
# Void elements take no closing tag -> excluded from the balance heuristic.
_WIDGET_VOID_TAGS = frozenset({"input"})
# Attribute allowlist (card OVERRIDE-4). `data-*`/`aria-*` (safe, a11y) pass by
# prefix; everything else -- href/src/name/on*=/... -- is rejected.
_WIDGET_ALLOWED_ATTRS = frozenset({
    "style", "id", "class", "type", "value", "placeholder", "for",
})

_SCRIPT_EL_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.S | re.I)
_STYLE_EL_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.S | re.I)
_SCRIPT_INNER_RE = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S | re.I)
_SCRIPT_OPEN_RE = re.compile(r"<script\b[^>]*>", re.I)
_SCRIPT_SRC_RE = re.compile(r"<script\b[^>]*\bsrc\s*=", re.I)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_INLINE_ON_RE = re.compile(r"<[^>]*\son[a-z]+\s*=", re.I)
_TAG_RE = re.compile(r"<\s*(/?)\s*([a-zA-Z][a-zA-Z0-9-]*)([^>]*?)(/?)\s*>")
_ATTR_NAME_RE = re.compile(r"([a-zA-Z_:][-a-zA-Z0-9_:]*)\s*=")
_ATTR_VALUE_RE = re.compile(r"\"[^\"]*\"|'[^']*'")
# Script-body blockers (checked against the concatenated inline <script> bodies).
_UNSAFE_JS_API_RE = re.compile(
    r"\b(?:fetch|XMLHttpRequest|WebSocket|eval|alert|prompt|confirm)\s*\("
    r"|\bnew\s+Function\b|\bFunction\s*\(")
_STORAGE_RE = re.compile(r"localStorage|sessionStorage|document\.cookie")
_DYNAMIC_HTML_RE = re.compile(
    r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|createElement")
_GLOBAL_CLICK_RE = re.compile(
    r"""document\.addEventListener\s*\(\s*['"]click['"]""")

# --- CLS ZERO POR CONSTRUÇÃO -------------------------------------------------
# Alternar cenário com `style.display` tira o bloco do fluxo e MUDA A ALTURA do
# container. Com 15 unidades de anúncio na página, cada interação do leitor
# empurra o anúncio para baixo: isso é Cumulative Layout Shift E viewability
# perdida, ao mesmo tempo. E é o leitor engajado — o que mais interage — quem
# mais sofre.
#
# O conserto não é uma meta de performance, é geometria: todos os cenários
# ocupam A MESMA célula de um grid (`grid-area:1/1`), então o container tem
# sempre a altura do MAIOR deles, e a troca é `visibility`, que não reflui.
# Nada se move porque não há para onde mover.
#
# Por isso `.style.display` é bloqueado no script e `grid-area` é exigido no
# markup: um sem o outro não entrega o invariante.
_DISPLAY_TOGGLE_RE = re.compile(r"\.style\.display\b")
_GRID_STACK_RE = re.compile(r"grid-area\s*:", re.I)


def _widget_html_issues(html_only: str) -> list[Issue]:
    """Tag/attribute allowlist + a heuristic tag-balance check over the STRUCTURAL
    HTML (script/style elements and comments already stripped). Each distinct
    offending tag/attribute is reported once."""
    issues: list[Issue] = []
    counts: dict[str, int] = {}
    seen_tag: set[str] = set()
    seen_attr: set[str] = set()
    for m in _TAG_RE.finditer(html_only):
        closing, name, attrs, selfclose = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        if name not in _WIDGET_ALLOWED_TAGS:
            if name not in seen_tag:
                seen_tag.add(name)
                issues.append(Issue(code="tag_not_allowed",
                                    message=f"Tag fora da allowlist: <{name}>."))
            continue
        if closing:
            counts[name] = counts.get(name, 0) - 1
            continue
        # opening tag: allowlist its attributes (values stripped so `=` inside a
        # value never reads as a bogus attribute name), then count for balance.
        for am in _ATTR_NAME_RE.finditer(_ATTR_VALUE_RE.sub("", attrs)):
            attr = am.group(1).lower()
            if attr.startswith(("data-", "aria-")) or attr in _WIDGET_ALLOWED_ATTRS:
                continue
            if attr not in seen_attr:
                seen_attr.add(attr)
                issues.append(Issue(code="attribute_not_allowed",
                                    message=f"Atributo fora da allowlist: {attr}."))
        if name not in _WIDGET_VOID_TAGS and not selfclose:
            counts[name] = counts.get(name, 0) + 1
    if any(v != 0 for v in counts.values()):
        issues.append(Issue(code="unbalanced_html",
                            message="Tags HTML desbalanceadas (heurística)."))
    return issues


def sanitize_widget_block(block: str) -> list[Issue]:
    """HARD sanitization of a candidate wp:html widget block. Returns the list of
    violations found; an EMPTY list means the widget is safe to inject. Every
    check is a string/regex rule (no code execution) -- see the module banner.

    HTML-structural checks run over `html_only` (the block with <script>/<style>
    ELEMENTS and HTML comments removed) so JS operators like `i<n` never read as
    tags; the JS-behaviour checks run over the concatenated inline <script>
    bodies. Labels are exactly the OVERRIDE-4 battery."""
    issues: list[Issue] = []

    script_bodies = _SCRIPT_INNER_RE.findall(block)
    n_scripts = len(_SCRIPT_OPEN_RE.findall(block))
    script_body = "\n".join(script_bodies)

    html_only = _SCRIPT_EL_RE.sub("", block)
    html_only = _STYLE_EL_RE.sub("", html_only)
    html_only = _HTML_COMMENT_RE.sub("", html_only)
    low_html = html_only.lower()

    if _ANY_RAW_PARAGRAPH_RE.search(html_only):
        issues.append(Issue(
            code="paragraph_in_raw_html",
            message="Widget contém <p>; use div/span para não entrar no contador de anúncios.",
        ))

    # --- external / injected code ------------------------------------------
    if "<iframe" in low_html or "javascript:" in low_html or _SCRIPT_SRC_RE.search(block):
        issues.append(Issue(code="unsafe_external_code",
                            message="iframe, <script src> ou javascript: (código externo)."))
    if _INLINE_ON_RE.search(html_only):
        issues.append(Issue(code="inline_event_handler",
                            message="Handler de evento inline (on*=) proibido."))
    if "<form" in low_html:
        issues.append(Issue(code="form_not_allowed",
                            message="<form> não permitido (use inputs soltos)."))

    # --- exactly ONE inline script -----------------------------------------
    if n_scripts == 0:
        issues.append(Issue(code="missing_inline_script",
                            message="Nenhum <script> inline (exatamente 1 exigido)."))
    elif n_scripts > 1:
        issues.append(Issue(code="multiple_scripts",
                            message=f"{n_scripts} <script> (exatamente 1 exigido)."))
    if _SCRIPT_SRC_RE.search(block):
        issues.append(Issue(code="external_script",
                            message="<script src=...> proibido (o script deve ser inline)."))

    # --- inline-script BODY blockers ---------------------------------------
    if "&" in script_body:  # covers `&`, `&&`, `&amp;`, `&#38;`, `&#x26;`
        issues.append(Issue(code="ampersand_in_script",
                            message="'&' no corpo do script (WP escaparia e quebraria)."))
    if _UNSAFE_JS_API_RE.search(script_body):
        issues.append(Issue(code="unsafe_js_api",
                            message="API JS proibida (fetch/XHR/WebSocket/eval/alert/"
                                    "prompt/confirm/Function)."))
    if _STORAGE_RE.search(script_body):
        issues.append(Issue(code="storage_or_cookie_not_allowed",
                            message="localStorage/sessionStorage/cookie não permitido."))
    if _DYNAMIC_HTML_RE.search(script_body):
        issues.append(Issue(code="dynamic_html_not_allowed",
                            message="Construção dinâmica de HTML não permitida (pré-renderize)."))
    if _GLOBAL_CLICK_RE.search(script_body):
        issues.append(Issue(code="global_click_listener_not_allowed",
                            message="Listener global de clique proibido (use por id)."))

    # --- CLS zero: os dois lados do invariante ------------------------------
    if _DISPLAY_TOGGLE_RE.search(script_body):
        issues.append(Issue(
            code="display_toggle_causes_cls",
            message="`style.display` muda a altura do container e empurra o "
                    "anúncio abaixo (CLS). Empilhe os cenários em `grid-area:1/1` "
                    "e alterne `style.visibility`."))
    if not _GRID_STACK_RE.search(block):
        issues.append(Issue(
            code="missing_grid_stack",
            message="Cenários não empilhados: falta `grid-area:1/1` no container "
                    "de resultado. Sem isso a troca de cenário reflui a página."))

    # --- tag/attribute allowlist + balance ---------------------------------
    issues.extend(_widget_html_issues(html_only))
    return issues
