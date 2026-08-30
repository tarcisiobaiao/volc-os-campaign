"""Deterministic Elementor-template injector for the Landing Page.

Clones a fixed, designer-built Elementor template (`templates/lp.json`,
adapted from the winning funnel's LP) and repopulates ONLY the content
(headings/texts/FAQ/button labels), the hero background image and the funnel
hrefs -- preserving every `settings` block (colors, typography, dividers,
button styles) EXACTLY. This is the "clone-and-repopulate" approach from the
n8n flow, made deterministic (no LLM re-serializing 30KB of JSON).

The template's fillable widgets (heading / text-editor / button, in document
order) map to content slots by INDEX -- see `_SLOT_MAP`. The map is specific
to the current `lp.json`; when the template is improved in the Elementor
editor, keep the widget order (or update this map).
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from importlib import resources

from funnelforge.domain.models import Issue
from funnelforge.pipeline.doctrine import (
    BANNED_CTA_FIRST_PERSON,
    BANNED_FEAR,
    BANNED_OFFICIAL,
    banned_cta_execution_hit,
)

_REQUIRED_LP_SLOTS = (
    "hero_title", "hero_subtitle", "article_title", "intro",
    "sections", "faq", "transition", "cta_texts",
)

# Tactile mobile-first invite ("toque abaixo e veja como...") the gravata
# (hero_subtitle) must close with, congruent with the hero CTAs right below it.
_GRAVATA_TACTILE_RE = re.compile(r"toque", re.IGNORECASE)


def validate_lp_content(content: dict) -> list[Issue]:
    """Validate the redator_p1 JSON that feeds the LP template.

    Checks the slot schema (all fields present, 4 sections, >=3 CTAs), the
    LP-specific shape rules (intro is a single paragraph, the gravata closes
    with a tactile CTA invite) AND the middle-ground compliance guards on the
    copy: no service-execution verbs in the CTAs, no false-officiality, no
    fabricated scarcity anywhere. Grounding (a real number/authority fact) is
    instructed in the prompt but not machine-verified here.
    """
    issues: list[Issue] = []
    for k in _REQUIRED_LP_SLOTS:
        if not content.get(k):
            issues.append(Issue(code="lp_missing_slot",
                                message=f"Campo obrigatório ausente/vazio: {k}"))
    secs = content.get("sections") or []
    if len(secs) != 4:
        issues.append(Issue(code="lp_sections",
                            message=f"Esperado 4 seções no template, veio {len(secs)}."))
    ctas = content.get("cta_texts") or []
    # EXATAMENTE 3, não ">= 3": o template tem 3 posições de destino
    # (`_BUTTON_HREF`: 6 widgets de botão para 3 destinos) e o pagespec da LP é
    # cta_min=cta_max=3. Com ">= 3", um modelo que devolvia 5 CTAs passava e os
    # dois excedentes sumiam sem aviso -- ninguém nunca soube que não eram
    # renderizados.
    if len(ctas) != 3:
        issues.append(Issue(code="lp_ctas",
                            message=f"Esperado EXATAMENTE 3 CTAs (o template tem 3 "
                                    f"posições de destino), veio {len(ctas)}."))

    intro = content.get("intro") or ""
    if intro.count("<p>") > 1:
        issues.append(Issue(code="lp_intro_long",
                            message="Intro deve ter EXATAMENTE 1 parágrafo (<p>); veio "
                                    "mais de um -- remova o parágrafo de roadmap."))
    subtitle = content.get("hero_subtitle") or ""
    if not _GRAVATA_TACTILE_RE.search(subtitle):
        issues.append(Issue(code="lp_gravata_no_cta",
                            message="Gravata (hero_subtitle) sem convite tátil "
                                    "('toque...') congruente com os cta_texts."))

    cta_text = " ".join(str(c) for c in ctas)
    hit = banned_cta_execution_hit(cta_text)
    if hit:
        issues.append(Issue(code="cta_execution",
                            message=f"CTA com verbo de execução de serviço: '{hit}'."))
    # 1ª pessoa emocional é proibida NA LP (regra exclusiva desta página, ver
    # doctrine.banned_for_role). O validador `cta_style` já aplica isso às
    # páginas interiores lendo os blocos wp:buttons; a LP não tem blocos --
    # tem `cta_texts` --, e por isso a única página em que a regra é
    # existencial era justamente a única sem quem a conferisse.
    low_ctas = cta_text.lower()
    for phrase in BANNED_CTA_FIRST_PERSON:
        if phrase in low_ctas:
            issues.append(Issue(
                code="cta_first_person",
                message=f"CTA em 1ª pessoa emocional na LP (proibido): '{phrase}'."))
            break
    flat = json.dumps(content, ensure_ascii=False).lower()
    for p in BANNED_OFFICIAL:
        if p in flat:
            issues.append(Issue(code="official_impersonation",
                                message=f"Falsa oficialidade no conteúdo: '{p}'."))
            break
    for p in BANNED_FEAR:
        if p in flat:
            issues.append(Issue(code="fear_language",
                                message=f"Escassez/medo fabricado no conteúdo: '{p}'."))
            break
    return issues

# Fillable-widget index (heading/text-editor/button in document order) -> slot.
# ("sections", i, "title"|"body") pulls content["sections"][i][...]; an int on
# a button pulls content["cta_texts"][int]; a LIST is a fallback chain.
#
# O template tem DOIS HERÓIS, um por breakpoint -- antes o desktop não tinha
# herói nenhum e a página abria direto no corpo. Os dois carregam o MESMO
# título e os MESMOS destinos; muda a quantidade de botões acima da dobra
# (2 no mobile, 3 no desktop) e o subtítulo, porque "toque abaixo" só faz
# sentido em tela de toque.
#
# Custo consciente do desenho: título e subtítulo existem DUAS VEZES no DOM,
# já que `hide_*` do Elementor é `display:none`, não remoção. Por isso só o
# herói MOBILE carrega o `h1` -- a indexação do Google é mobile-first, e dois
# h1 no documento seria pior que um h1 escondido no desktop.
_SLOT_MAP: dict[int, tuple[str, object]] = {
    # --- herói MOBILE (hide_desktop + hide_tablet) ---
    0: ("heading", "hero_title"),          # o ÚNICO h1 da página
    1: ("heading", "hero_subtitle"),
    2: ("button", 0),
    3: ("button", 1),
    # --- herói DESKTOP (hide_tablet + hide_mobile) ---
    4: ("heading", "hero_title"),
    5: ("heading", ["hero_subtitle_desktop", "hero_subtitle"]),
    6: ("button", 0),
    7: ("button", 1),
    8: ("button", 2),
    # --- corpo (ambos os breakpoints) ---
    9: ("heading", "article_title"),
    10: ("text", "intro"),
    11: ("heading", ("sections", 0, "title")),
    12: ("text", ("sections", 0, "body")),
    13: ("heading", ("sections", 1, "title")),
    14: ("text", ("sections", 1, "body")),
    15: ("button", 2),
    16: ("heading", ("sections", 2, "title")),
    17: ("text", ("sections", 2, "body")),
    18: ("heading", ("sections", 3, "title")),
    19: ("text", ("sections", 3, "body")),
    20: ("heading", "faq_title"),
    21: ("faq", "faq"),
    22: ("text", "transition"),
}

# Botão (ordinal em ordem de documento) -> índice do destino em `funnel_hrefs`.
# São 6 widgets de botão para 3 destinos, porque os dois heróis repetem os
# mesmos caminhos. Antes o href era POSICIONAL (`funnel_hrefs[n]`), o que com 6
# botões mandaria três deles para o último destino -- o mapa explícito é o que
# mantém a promessa "cada botão leva ao SEU destino" com heróis duplicados.
_BUTTON_HREF: dict[int, int] = {
    0: 0, 1: 1,           # mobile:  hub, solução 1
    2: 0, 3: 1, 4: 2,     # desktop: hub, solução 1, solução 2
    5: 2,                 # corpo:   solução 2
}


_ARROW_TOKENS = (">>>", ">>", ">", "»", "›", "→")


def _has_arrow_icon(settings: dict) -> bool:
    """True if the button widget already renders a right-arrow icon."""
    ic = settings.get("selected_icon")
    val = ic.get("value") if isinstance(ic, dict) else ic
    return bool(val) and "arrow" in str(val).lower()


def _strip_trailing_arrows(text: str) -> str:
    """Drop trailing arrow chrome (»/>>/→ ...) the writer appends -- redundant
    when the button widget itself shows an arrow icon."""
    t = text.rstrip()
    changed = True
    while changed:
        changed = False
        for tok in _ARROW_TOKENS:
            if t.endswith(tok):
                t = t[: -len(tok)].rstrip()
                changed = True
    return t


# number-keycap emojis (1..9). Each is "N" + U+FE0F + U+20E3 -- all BMP (<=3
# bytes in UTF-8), so they survive the astral-char strip on _elementor_data.
_KEYCAPS = {str(d): f"{d}️⃣" for d in range(1, 10)}
_NUMBERED_P_RE = re.compile(r"(<p>)\s*([1-9])\)\s*")


def _numbered_to_emoji(html: str) -> str:
    """Swap a leading "N)" enumeration inside a paragraph for a number-keycap
    emoji (1️⃣ 2️⃣ 3️⃣ ...), for a bit more visual layer in the LP body -- e.g.
    "<p>1) texto" -> "<p>1️⃣ texto". No-op when there's no such enumeration."""
    return _NUMBERED_P_RE.sub(lambda m: f"{m.group(1)}{_KEYCAPS[m.group(2)]} ", html)


def load_lp_template() -> dict:
    """Load the packaged, adapted LP Elementor template."""
    raw = resources.files("funnelforge").joinpath("templates/lp.json").read_text(encoding="utf-8")
    return json.loads(raw)


def _fillable(content: list) -> list[dict]:
    """Heading / text-editor / button widgets, in document order."""
    out: list[dict] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("widgetType") in ("heading", "text-editor", "button"):
                out.append(node)
            for child in node.get("elements", []) or []:
                walk(child)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    walk(content)
    return out


def _slot_value(content: dict, spec: object) -> str:
    # Lista = cadeia de fallback: o primeiro valor não-vazio vence. Serve ao
    # subtítulo do herói DESKTOP, que idealmente tem texto próprio (o mobile
    # diz "toque abaixo", que no desktop é errado) mas cai no subtítulo comum
    # quando o redator não produziu a variante -- nunca deixa o herói vazio.
    if isinstance(spec, list):
        for alt in spec:
            valor = _slot_value(content, alt)
            if valor:
                return valor
        return ""
    if isinstance(spec, tuple):
        key, idx, sub = spec
        arr = content.get(key) or []
        return arr[idx].get(sub, "") if idx < len(arr) else ""
    return content.get(spec, "")


def _su_accordion(faq: list) -> str:
    parts = []
    for i, item in enumerate(faq or []):
        op = "yes" if i == 0 else "no"
        q, a = item.get("q", ""), item.get("a", "")
        parts.append(
            f'[su_spoiler title="{q}" open="{op}" style="fancy" icon="plus"]{a}[/su_spoiler]'
        )
    return "[su_accordion]" + "".join(parts) + "[/su_accordion]"


def _regen_ids(node: object, counter: list[int]) -> None:
    if isinstance(node, dict):
        if "id" in node:
            counter[0] += 1
            node["id"] = f"{counter[0]:08x}"
        for child in node.get("elements", []) or []:
            _regen_ids(child, counter)
    elif isinstance(node, list):
        for x in node:
            _regen_ids(x, counter)


def _drop_conflicting_global_typography(node: object) -> None:
    """Remove a lingering `__globals__.typography_typography` link on any widget
    that ALSO ships a custom `typography_font_size`.

    In Elementor a GLOBAL font link beats the custom typography_* keys, so
    leaving both makes the custom size silently ineffective (and the size field
    un-editable until the global is unlinked). Whenever this template ships a
    custom size, the custom size must win -- so drop the conflicting link."""
    if isinstance(node, dict):
        s = node.get("settings")
        if isinstance(s, dict) and s.get("typography_font_size"):
            g = s.get("__globals__")
            if isinstance(g, dict) and "typography_typography" in g:
                g.pop("typography_typography", None)
                if not g:
                    s.pop("__globals__", None)
        for child in node.get("elements", []) or []:
            _drop_conflicting_global_typography(child)
    elif isinstance(node, list):
        for x in node:
            _drop_conflicting_global_typography(x)


def _fix_image_and_hrefs(node: object, hero_image_url: str) -> None:
    """Swap the hero background-image placeholder for the real URL.

    Button hrefs are assigned per-slot in `render_lp` (one funnel destination
    per button), so this pass only handles the `{{HERO_IMAGE}}` placeholder."""
    if isinstance(node, dict):
        s = node.get("settings")
        if isinstance(s, dict):
            for v in s.values():
                if isinstance(v, dict) and v.get("url") == "{{HERO_IMAGE}}":
                    v["url"] = hero_image_url
        for child in node.get("elements", []) or []:
            _fix_image_and_hrefs(child, hero_image_url)
    elif isinstance(node, list):
        for x in node:
            _fix_image_and_hrefs(x, hero_image_url)


def _href_for_button(funnel_hrefs: list[str], button_ordinal: int) -> str:
    """Destino do N-ésimo botão (0-based, ordem de documento), via `_BUTTON_HREF`.

    O mapa existe porque os dois heróis REPETEM os mesmos caminhos: são 6
    widgets de botão para 3 destinos. Uma regra posicional (`funnel_hrefs[n]`)
    mandaria metade dos botões para o último destino e quebraria em silêncio a
    promessa de que cada botão leva ao seu.

    Nunca devolve o placeholder cru: fora do mapa, ou com menos destinos que o
    esperado, cai no último href disponível."""
    if not funnel_hrefs:
        return ""
    alvo = _BUTTON_HREF.get(button_ordinal, button_ordinal)
    if alvo < len(funnel_hrefs):
        return funnel_hrefs[alvo]
    return funnel_hrefs[-1]


def render_lp(
    template: dict, content: dict, funnel_hrefs: list[str],
    hero_image_url: str = "", id_seed: str = "",
) -> tuple[list, dict]:
    """Return `(elementor_content_array, page_settings)` for the LP.

    Clones `template`, regenerates all widget ids (run-scoped via `id_seed`),
    fills each fillable widget from `content` per `_SLOT_MAP`, points each button
    at its OWN funnel destination -- `funnel_hrefs[i]` for the i-th button in
    document order, one pre-sell per button (honest 3-CTA LP) -- and swaps the
    hero background image for `hero_image_url`. Preserves all styling.
    """
    tpl = copy.deepcopy(template)
    cont = tpl["content"]
    start = int(hashlib.sha1(id_seed.encode()).hexdigest(), 16) % 0x00FFFFFF if id_seed else 0
    _regen_ids(cont, [start])

    button_ordinal = 0
    for i, w in enumerate(_fillable(cont)):
        spec = _SLOT_MAP.get(i)
        if spec is None:
            continue
        kind, ref = spec
        s = w.setdefault("settings", {})
        if kind == "heading":
            s["title"] = _slot_value(content, ref)
        elif kind == "text":
            s["editor"] = _numbered_to_emoji(_slot_value(content, ref))
        elif kind == "faq":
            s["editor"] = _su_accordion(content.get("faq") or [])
        elif kind == "button":
            texts = content.get("cta_texts") or []
            if isinstance(ref, int) and texts:
                # cycle if fewer CTAs than buttons, so no TEMPLATE (source
                # locale) button label ever survives.
                label = texts[ref % len(texts)]
                # LP template buttons already render a right-arrow icon, so the
                # trailing »/>> the writer appends is redundant -- strip it.
                if _has_arrow_icon(s):
                    label = _strip_trailing_arrows(label)
                s["text"] = label
            s.setdefault("link", {})["url"] = _href_for_button(funnel_hrefs, button_ordinal)
            button_ordinal += 1

    _fix_image_and_hrefs(cont, hero_image_url)
    _drop_conflicting_global_typography(cont)
    return cont, tpl.get("page_settings", {})
