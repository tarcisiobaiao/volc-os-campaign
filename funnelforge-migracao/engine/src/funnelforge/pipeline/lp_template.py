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
from html import escape
from importlib import resources

from funnelforge.domain.models import Issue
from funnelforge.pipeline.editorial_safety import (
    href_externo,
    html_issues,
    links_no_texto_da_lp,
    notice_html,
    valid_web_url,
)
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

# Entrega própria da LP NÃO é decidida aqui. Contar frases ou palavras não diz
# se a página responde à dúvida de quem clicou: uma LP curta pode responder e
# uma longa pode só encaminhar. Quem decide é o revisor contextual, que lê a
# pergunta, a promessa do anúncio e o texto (`revisor.jinja`, página sem valor
# próprio = congruencia_destino bloqueante). Aqui fica só o contrato do
# template: campos, tipos, 4 seções, 3 CTAs, HTML válido.


def validate_lp_content(content: dict, *, technical_only: bool = False,
                        sem_links_no_texto: bool = False) -> list[Issue]:
    """Validate the redator_p1 JSON that feeds the LP template.

    Checks the slot schema (all fields present, 4 sections, >=3 CTAs), the
    LP-specific shape rules (intro is a single paragraph) AND the compliance guards on the
    copy: no service-execution verbs in the CTAs, no false-officiality, no
    fabricated scarcity anywhere. Grounding (a real number/authority fact) is
    instructed in the prompt but not machine-verified here.
    """
    issues: list[Issue] = []
    if not isinstance(content, dict):
        return [Issue(code="lp_schema", message="A LP deve ser um objeto JSON.")]
    for name in _REQUIRED_LP_SLOTS:
        if not content.get(name):
            issues.append(Issue(code="lp_missing_slot", message=f"Campo obrigatório ausente: {name}"))
    for name in ("hero_title", "hero_subtitle", "article_title", "intro", "transition"):
        if not isinstance(content.get(name), str):
            issues.append(Issue(code="lp_schema", message=f"{name} deve ser texto."))
    for name, fields in (("sections", ("title", "body")), ("faq", ("q", "a"))):
        items = content.get(name)
        if not isinstance(items, list) or any(
            not isinstance(item, dict) or any(not isinstance(item.get(k), str) for k in fields)
            for item in items
        ):
            issues.append(Issue(code="lp_schema", message=f"Estrutura inválida: {name}"))
    ctas = content.get("cta_texts")
    if not isinstance(ctas, list) or any(not isinstance(c, str) for c in ctas):
        issues.append(Issue(code="lp_schema", message="cta_texts deve ser uma lista de textos."))
    if issues:
        return issues
    for value in (content["intro"], content["transition"],
                  *(s["body"] for s in content["sections"])):
        issues.extend(html_issues(value, rich_only=True))
    for k in _REQUIRED_LP_SLOTS:
        if not content.get(k):
            issues.append(Issue(code="lp_missing_slot",
                                message=f"Campo obrigatório ausente/vazio: {k}"))
    secs = content.get("sections") or []
    if len(secs) != 4:
        issues.append(Issue(code="lp_sections",
                            message=f"Esperado 4 seções no template, veio {len(secs)}."))
    # LP V2 (`sem_links_no_texto`): os únicos links são os botões do template
    # (renderer); âncora no texto gerado, interna ou externa, é erro estrutural
    # (15/10/2026). Quem chega aqui já passou pelo saneador do runner, que tira
    # essas âncoras com o mesmo parser. A LP V1 continua com as regras com que
    # foi escrita: o prompt V1 pede a fonte linkada na frase do fato
    # (`redator_p1.jinja`), e LP V1 histórica não pode reprovar por regra nova.
    if sem_links_no_texto:
        issues.extend(links_no_texto_da_lp([
            content["intro"], content["transition"], content["hero_title"],
            content["hero_subtitle"], content["article_title"],
            *(s["body"] for s in content["sections"]),
            *(s["title"] for s in content["sections"]),
            *(f["q"] for f in content["faq"]), *(f["a"] for f in content["faq"]),
            *(c for c in content["cta_texts"])]))
    ctas = content.get("cta_texts") or []
    # EXATAMENTE 3, não ">= 3": o template tem 3 posições de destino
    # (`_BUTTON_HREF`: 7 widgets de botão para 3 destinos) e o pagespec da LP é
    # cta_min=cta_max=3. Com ">= 3", um modelo que devolvia 5 CTAs passava e os
    # dois excedentes sumiam sem aviso -- ninguém nunca soube que não eram
    # renderizados.
    if len(ctas) != 3:
        issues.append(Issue(code="lp_ctas",
                            message=f"Esperado EXATAMENTE 3 CTAs (o template tem 3 "
                                    f"posições de destino), veio {len(ctas)}."))

    if technical_only:
        return issues  # Copy, extensão da intro e promessa: revisão contextual.

    intro = content.get("intro") or ""
    if intro.count("<p>") > 1:
        issues.append(Issue(code="lp_intro_long",
                            message="Intro deve ter EXATAMENTE 1 parágrafo (<p>); veio "
                                    "mais de um -- remova o parágrafo de roadmap."))

    cta_text = " ".join(str(c) for c in ctas)
    hit = next((hit for c in ctas if (hit := banned_cta_execution_hit(c))), None)
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
# a button pulls content["cta_texts"][int].
#
# O template tem DOIS HERÓIS, um por breakpoint. Os dois carregam o MESMO
# título, os MESMOS três rótulos e os MESMOS três destinos, na mesma ordem:
# pré-sell, solução 1, solução 2. 98% do tráfego é mobile (operador,
# 15/10/2026): até então o herói mobile tinha só 2 botões e o terceiro caminho
# aparecia apenas no corpo, abaixo da dobra.
#
# O herói mobile é compacto (sem altura mínima de tela cheia, conteúdo no topo,
# sem divisor, sem ícone nos botões) porque divide a primeira dobra com o
# cabeçalho do tema e com a folha de consentimento (volc-consent-manager), que
# no celular ocupa de y=387 até o fim em 360x800. O 100vh com `flex-end` de
# 78c13d94 jogava título e botões para baixo da folha. Medido no Elementor 4.3.5
# (WordPress descartável, cabeçalho de 85 px, 15/10/2026): com título de 40,
# subtítulo de 80 + "Toque abaixo!" e rótulos de 60 caracteres, o 3º botão termina
# 6 px acima da folha; com rótulos de ~37, 60 px. `scripts/prova_dobra_lp.py`
# refaz a medição; qualquer mudança no herói mobile exige rodá-la de novo.
#
# Custo consciente do desenho: título e subtítulo existem DUAS VEZES no DOM,
# já que `hide_*` do Elementor é `display:none`, não remoção. Por isso só o
# herói MOBILE carrega o `h1` -- a indexação do Google é mobile-first, e dois
# h1 no documento seria pior que um h1 escondido no desktop.
_SLOT_MAP: dict[int, tuple[str, object]] = {
    # --- herói MOBILE (hide_desktop + hide_tablet) ---
    0: ("heading", "hero_title"),          # o ÚNICO h1 da página
    1: ("heading", "hero_subtitle_mobile"),   # composto em `_subtitulos_do_heroi`
    2: ("button", 0),
    3: ("button", 1),
    4: ("button", 2),
    # --- herói DESKTOP (hide_tablet + hide_mobile) ---
    5: ("heading", "hero_title"),
    6: ("heading", "hero_subtitle_desktop"),  # idem: nunca leva a chamada de toque
    7: ("button", 0),
    8: ("button", 1),
    9: ("button", 2),
    # --- corpo (ambos os breakpoints) ---
    10: ("heading", "article_title"),
    11: ("text", "intro"),
    12: ("heading", ("sections", 0, "title")),
    13: ("text", ("sections", 0, "body")),
    14: ("heading", ("sections", 1, "title")),
    15: ("text", ("sections", 1, "body")),
    16: ("button", 2),                      # repetição contextual, não a única aparição
    17: ("heading", ("sections", 2, "title")),
    18: ("text", ("sections", 2, "body")),
    19: ("heading", ("sections", 3, "title")),
    20: ("text", ("sections", 3, "body")),
    21: ("heading", "faq_title"),
    22: ("faq", "faq"),
    23: ("text", "transition"),
}

# Botão (ordinal em ordem de documento) -> índice do destino em `funnel_hrefs`.
# São 7 widgets de botão para 3 destinos: cada herói mostra os três caminhos e
# o corpo repete o terceiro depois da explicação. Antes o href era POSICIONAL
# (`funnel_hrefs[n]`), o que mandaria vários botões para o último destino -- o
# mapa explícito é o que mantém "cada botão leva ao SEU destino". O índice do
# rótulo em `_SLOT_MAP` e o do destino aqui são o MESMO em todo botão: rótulo e
# href nunca se trocam entre breakpoints.
_BUTTON_HREF: dict[int, int] = {
    0: 0, 1: 1, 2: 2,     # mobile:  pré-sell, solução 1, solução 2
    3: 0, 4: 1, 5: 2,     # desktop: pré-sell, solução 1, solução 2
    6: 2,                 # corpo:   solução 2 (repetição contextual)
}


_ARROW_TOKENS = (">>>", ">>", ">", "»", "›", "→")


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


# Chamada curta para os botões, SÓ no herói mobile da LP V2 (operador,
# 15/10/2026). Quem acrescenta é o render, não o redator: o prompt pede o
# subtítulo sem descrever navegação, e o desktop (botões ao lado, sem toque)
# nunca recebe a chamada. Rascunho antigo que já trazia a chamada no fim não a
# duplica no celular nem a leva para o desktop.
CHAMADA_DO_HEROI_MOBILE = "Toque abaixo!"
_CHAMADA_FINAL_RE = re.compile(r"[\s,;.\u2013\u2014-]*(?:👇\s*)?toque abaixo\s*[!.]?\s*(?:👇)?\s*$",
                               re.I)


def _sem_chamada_final(texto: str) -> str:
    return _CHAMADA_FINAL_RE.sub("", texto or "").rstrip()


def _subtitulos_do_heroi(content: dict, *, copy_rapida: bool) -> dict:
    """`hero_subtitle_mobile` e `hero_subtitle_desktop` que o template usa.

    V1 (`copy_rapida=False`) fica como sempre foi: mobile = `hero_subtitle`;
    desktop = `hero_subtitle_desktop` do redator V1, ou o mesmo subtítulo."""
    base = str(content.get("hero_subtitle") or "")
    desktop = str(content.get("hero_subtitle_desktop") or "")
    if not copy_rapida:
        return {"hero_subtitle_mobile": base, "hero_subtitle_desktop": desktop or base}
    limpo = _sem_chamada_final(base)
    mobile = f"{limpo} {CHAMADA_DO_HEROI_MOBILE}".strip() if limpo else ""
    return {"hero_subtitle_mobile": mobile,
            "hero_subtitle_desktop": _sem_chamada_final(desktop) or limpo}


def assinatura_do_template() -> str:
    """sha256 do que decide o Elementor da LP: o `lp.json` e este renderer.

    O build grava a assinatura ao lado do artefato (`p1.template.json`); o portão
    final compara. Artefato montado com outro template/render não é adulteração
    nem é aceito em silêncio: vira `lp_template_desatualizado`, com o comando de
    rebuild explícito (`funnelforge reconstruir-lp`)."""
    pacote = resources.files("funnelforge")
    h = hashlib.sha256()
    for parte in ("templates/lp.json", "pipeline/lp_template.py"):
        h.update(parte.encode())
        h.update(pacote.joinpath(parte).read_bytes())
    return h.hexdigest()


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
    if isinstance(spec, tuple):
        key, idx, sub = spec
        arr = content.get(key) or []
        return arr[idx].get(sub, "") if idx < len(arr) else ""
    return content.get(spec, "")


def _su_accordion(faq: list) -> str:
    parts = []
    for i, item in enumerate(faq or []):
        op = "yes" if i == 0 else "no"
        # Questions/answers are text, not a way to inject HTML or WP shortcodes.
        q, a = (escape(item.get(k, "")).replace("[", "&#91;").replace("]", "&#93;")
                for k in ("q", "a"))
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

    O mapa existe porque os dois heróis REPETEM os mesmos caminhos: são 7
    widgets de botão (3 + 3 + 1 no corpo) para 3 destinos. Uma regra posicional (`funnel_hrefs[n]`)
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


def _container_por_breakpoint(content: list, chave: str, valor: str) -> dict | None:
    """Localiza o heroi por semantica responsiva, nunca por posicao ou id exportado."""
    encontrado = None

    def walk(node: object) -> None:
        nonlocal encontrado
        if encontrado is not None:
            return
        if isinstance(node, dict):
            if node.get("elType") == "container" and (node.get("settings") or {}).get(chave) == valor:
                encontrado = node
                return
            for child in node.get("elements", []) or []:
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(content)
    return encontrado


def _aplicar_visual_rapido(content: list, *, hero_image_url: str) -> None:
    """Corrige defeitos medidos sem depender dos ids ou indices do Elementor.

    O template possui dois herois mutuamente exclusivos por breakpoint. Cada
    viewport precisa de um H1 visivel; por isso os dois titulos recebem H1, mas
    nunca aparecem juntos. Se a estrutura responsiva mudar, falhamos em vez de
    estilizar silenciosamente o container errado.
    """
    mobile = _container_por_breakpoint(content, "hide_desktop", "hidden-desktop")
    desktop = _container_por_breakpoint(content, "hide_mobile", "hidden-mobile")
    if mobile is None or desktop is None:
        raise ValueError("Template LP sem os herois responsivos esperados")

    for widget in _fillable(content):
        settings = widget.setdefault("settings", {})
        if widget.get("widgetType") == "heading":
            settings["header_size"] = "h2"
        if widget.get("widgetType") == "button" and settings.get("background_color") in (
                "#F9B200", "#3BD404", "#48952C"):
            settings["button_text_color"] = "#171717"

    for hero in (mobile, desktop):
        headings = [w for w in _fillable([hero]) if w.get("widgetType") == "heading"]
        if len(headings) < 2:
            raise ValueError("Hero LP sem titulo e subtitulo esperados")
        headings[0].setdefault("settings", {})["header_size"] = "h1"
        headings[1].setdefault("settings", {})["header_size"] = "p"

        # Um funil linear tem um único próximo destino. O template possui 3
        # botões em cada herói para funis em leque (pré-sell + 2 soluções);
        # reaproveitá-los por fallback produzia dois ou três botões idênticos
        # acima da dobra. Preserve somente a primeira ocorrência de cada URL
        # dentro de cada herói. O CTA do corpo fica intacto e pode avançar a
        # mensagem depois que o leitor consumiu a explicação.
        vistos: set[str] = set()

        def remover_repetidos(elementos: list[dict]) -> list[dict]:
            filtrados: list[dict] = []
            for elemento in elementos:
                if elemento.get("widgetType") == "button":
                    href = str(
                        (((elemento.get("settings") or {}).get("link") or {}).get("url"))
                        or ""
                    )
                    if href and href in vistos:
                        continue
                    if href:
                        vistos.add(href)
                filhos = elemento.get("elements")
                if isinstance(filhos, list):
                    elemento["elements"] = remover_repetidos(filhos)
                filtrados.append(elemento)
            return filtrados

        hero["elements"] = remover_repetidos(hero.get("elements", []) or [])

    mobile["settings"]["background_color"] = "#C9003B"
    if not hero_image_url:
        mobile["settings"]["min_height_mobile"] = {"unit": "px", "size": 0}
        mobile["settings"]["flex_justify_content_mobile"] = "flex-start"
        mobile["settings"]["padding_mobile"] = {
            "unit": "px", "top": "24", "right": "16", "bottom": "24", "left": "16"}
        for node in [mobile, *mobile.get("elements", []), *_fillable([mobile])]:
            for key in ("margin_mobile", "_margin_mobile"):
                if key in node.get("settings", {}):
                    node["settings"][key] = {
                        "unit": "px", "top": "0", "right": "0", "bottom": "0", "left": "0"}


def render_lp(
    template: dict, content: dict, funnel_hrefs: list[str],
    hero_image_url: str = "", id_seed: str = "", site_domain: str = "",
    copy_rapida: bool = False, footer_disclosure: bool = False,
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

    slots = {**content, **_subtitulos_do_heroi(content, copy_rapida=copy_rapida)}
    button_ordinal = 0
    for i, w in enumerate(_fillable(cont)):
        spec = _SLOT_MAP.get(i)
        if spec is None:
            continue
        kind, ref = spec
        s = w.setdefault("settings", {})
        if kind == "heading":
            s["title"] = escape(_slot_value(slots, ref))
        elif kind == "text":
            value = _slot_value(content, ref)
            if html_issues(value, rich_only=True):
                raise ValueError("HTML inseguro no texto da LP")
            s["editor"] = _numbered_to_emoji(value)
        elif kind == "faq":
            s["editor"] = _su_accordion(content.get("faq") or [])
        elif kind == "button":
            texts = content.get("cta_texts") or []
            if isinstance(ref, int) and texts:
                # cycle if fewer CTAs than buttons, so no TEMPLATE (source
                # locale) button label ever survives.
                label = texts[ref % len(texts)]
                # A seta final que o redator acrescenta (»/>>) sai de TODO botão
                # da LP: os botões do desktop e do corpo já desenham o ícone, e
                # os do herói mobile ficaram sem ícone (15/10/2026) para o rótulo
                # caber numa linha. Mesmo rótulo nos dois heróis, sempre.
                label = _strip_trailing_arrows(label)
                s["text"] = escape(label)
            href = _href_for_button(funnel_hrefs, button_ordinal)
            if not valid_web_url(href):
                raise ValueError("Destino inválido no botão da LP")
            if site_domain and href_externo(href, site_domain):
                raise ValueError("Botão da LP para outro site: a LP só leva a páginas do funil")
            s.setdefault("link", {})["url"] = href
            button_ordinal += 1

    _fix_image_and_hrefs(cont, hero_image_url)
    _drop_conflicting_global_typography(cont)
    if copy_rapida:
        _aplicar_visual_rapido(cont, hero_image_url=hero_image_url)
    # Canvas can omit theme chrome. A identidade editorial fica na página, mas no
    # FIM (operador, 15/10/2026): no topo ela empurrava o herói para fora da
    # primeira dobra do celular. No site, o aviso global do MU-plugin também vai
    # para o rodapé; o volc-editorial-notice-owner retira este no fim da resposta,
    # só depois de o global ter sido impresso (INSTALACAO-HARDENING.md).
    if copy_rapida:
        from funnelforge.pipeline.copy_contract import short_notice_html
        identity_html = "" if footer_disclosure else short_notice_html(site_domain)
    else:
        identity_html = notice_html(site_domain)
    if identity_html:
        cont.append({
            "id": "editorial", "elType": "container",
            "settings": {"content_width": "full", "background_background": "classic",
                     "background_color": "#ffffff"},
            "elements": [{"id": "notice", "elType": "widget", "widgetType": "html",
                      "settings": {"html": identity_html}, "elements": []}],
        })
    _regen_ids(cont, [start])
    return cont, tpl.get("page_settings", {})


def transformacoes_do_template(content: dict, template: dict | None = None, *,
                               copy_rapida: bool = True,
                               footer_disclosure: bool = False) -> list[dict]:
    """O que `render_lp` faz com o texto APROVADO ao montar o Elementor, para o
    registro no state.json (ramo editorial novo, B5). Não muda o render: repete
    o mesmo percurso por `_SLOT_MAP` e só anota o que muda — escape de HTML nos
    títulos, enumeração "1)" virando emoji, seta final tirada do rótulo do
    botão, FAQ virando shortcode escapado, slot do template sem texto, a
    chamada de toque do herói mobile e ONDE o aviso de identidade ficou (os
    mesmos parâmetros do `render_lp`: o registro diz o que o render fez)."""
    tpl = template if template is not None else load_lp_template()
    saida: list[dict] = []
    vistos: set[tuple[str, str]] = set()

    def anota(tipo: str, campo: str, **extra: object) -> None:
        if (tipo, campo) not in vistos:
            vistos.add((tipo, campo))
            saida.append({"tipo": tipo, "campo": campo, **extra})

    def nome(ref: object) -> str:
        if isinstance(ref, tuple):
            return f"{ref[0]}[{ref[1]}].{ref[2]}"
        return str(ref)

    subtitulos = _subtitulos_do_heroi(content, copy_rapida=copy_rapida)
    slots = {**content, **subtitulos}
    if copy_rapida and subtitulos["hero_subtitle_mobile"] != str(
            content.get("hero_subtitle") or ""):
        anota("chamada_de_toque_no_heroi_mobile", "hero_subtitle",
              depois=subtitulos["hero_subtitle_mobile"][:200])
    textos = content.get("cta_texts") or []
    for i, w in enumerate(_fillable(copy.deepcopy(tpl).get("content", []))):
        spec = _SLOT_MAP.get(i)
        if spec is None:
            continue
        kind, ref = spec
        s = w.get("settings", {}) or {}
        if kind == "heading":
            valor = _slot_value(slots, ref)
            if not valor:
                anota("slot_vazio", nome(ref))
            elif escape(valor) != valor:
                anota("escape_html", nome(ref))
        elif kind == "text":
            valor = _slot_value(content, ref)
            if _numbered_to_emoji(valor) != valor:
                anota("enumeracao_para_emoji", nome(ref), antes=valor[:200],
                      depois=_numbered_to_emoji(valor)[:200])
        elif kind == "faq":
            anota("faq_em_shortcode", "faq", itens=len(content.get("faq") or []))
        elif kind == "button" and isinstance(ref, int) and textos:
            idx = ref % len(textos)
            rotulo = str(textos[idx])
            if _strip_trailing_arrows(rotulo) != rotulo:
                anota("seta_final_removida", f"cta_texts[{idx}]", antes=rotulo,
                      depois=_strip_trailing_arrows(rotulo))
            if escape(rotulo) != rotulo:
                anota("escape_html", f"cta_texts[{idx}]")
    if copy_rapida and footer_disclosure:
        # O aviso curto do motor não entra: o rodapé institucional do tema já
        # traz a identidade (`render_lp`, `identity_html = ""`).
        anota("aviso_identidade_no_rodape_do_tema", "template")
    else:
        anota("aviso_identidade_no_fim", "template")
    return saida
