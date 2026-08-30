from __future__ import annotations

import hashlib
import re

# Deterministic marker -> Elementor page builder. PURE PYTHON, stdlib only.
# Turns "=== WIDGET: TYPE ===" blocks (Portuguese) emitted by the redactor
# into an Elementor `content` array. Never clones a foreign template.

_HEADER_RE = re.compile(r"^===\s*WIDGET:\s*(.+?)\s*===\s*$")
_FAQ_LINE_RE = re.compile(r"^\d+[.)]\s*(.+?\?)\s*(.*)$")


def parse_markers(text: str) -> list[dict]:
    """Split redactor output into widget blocks on `\\n---\\n`.

    Each block's first line is `=== WIDGET: TYPE ===`. For BOTÃO, the body
    lines `Texto:`/`Cor:`/`Link:` are parsed into `data["texto"]`,
    `data["cor"]`, `data["link"]`. For every other type the remaining body
    lines are kept verbatim in `data["body"]`.
    """
    widgets: list[dict] = []
    for raw_block in text.strip("\n").split("\n---\n"):
        block = raw_block.strip("\n")
        if not block.strip():
            continue
        header, *rest = block.split("\n")
        match = _HEADER_RE.match(header.strip())
        if not match:
            continue
        widget_type = match.group(1).strip()
        body_lines = list(rest)
        while body_lines and not body_lines[-1].strip():
            body_lines.pop()
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)
        if widget_type == "BOTÃO":
            data = _parse_botao_fields(body_lines)
        else:
            data = {"body": body_lines}
        widgets.append({"type": widget_type, "data": data})
    return widgets


def _parse_botao_fields(lines: list[str]) -> dict:
    data = {"texto": "", "cor": "", "link": ""}
    for line in lines:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "texto":
            data["texto"] = value
        elif key == "cor":
            data["cor"] = value
        elif key == "link":
            data["link"] = value
    return data


class _IdCounter:
    """Deterministic 8-hex-digit id generator, starting at 1 per build.

    `start` offsets the sequence so IDs are run-scoped instead of resetting
    to the same `00000001...` sequence on every build (a machine
    fingerprint that flags the output as scaled/templated content)."""

    def __init__(self, start: int = 0) -> None:
        self._n = start

    def next(self) -> str:
        self._n += 1
        return f"{self._n:08x}"


def _widget(ids: _IdCounter, widget_type: str, settings: dict) -> dict:
    return {
        "id": ids.next(),
        "elType": "widget",
        "widgetType": widget_type,
        "settings": settings,
        "elements": [],
    }


def _text_editor(ids: _IdCounter, html: str) -> dict:
    return _widget(ids, "text-editor", {"editor": html})


def _heading(ids: _IdCounter, text: str, header_size: str) -> dict:
    return _widget(ids, "heading", {"title": text, "header_size": header_size})


def _body_text(data: dict) -> str:
    return "\n".join(data.get("body", [])).strip()


def _build_image(ids: _IdCounter, image_url: str) -> dict:
    return _widget(ids, "image", {"image": {"url": image_url}})


def _build_nav(ids: _IdCounter, data: dict, brand_color: str) -> dict:
    text = _body_text(data)
    html = f'<p style="font-size:13px;color:{brand_color};">{text}</p>'
    return _text_editor(ids, html)


def _build_titulo(ids: _IdCounter, data: dict, header_size: str) -> dict:
    return _heading(ids, _body_text(data), header_size)


def _build_texto(ids: _IdCounter, data: dict) -> dict:
    return _text_editor(ids, f"<p>{_body_text(data)}</p>")


def _build_lista(ids: _IdCounter, data: dict) -> dict:
    items = "".join(f"<li>{line.strip()}</li>" for line in data.get("body", []) if line.strip())
    return _text_editor(ids, f"<ul>{items}</ul>")


def _build_aviso(ids: _IdCounter, data: dict) -> dict:
    style = (
        "background-color:#fff9c4;border:1px solid #333;"
        "border-radius:8px;padding:15px;font-size:13px"
    )
    html = f'<div style="{style}">{_body_text(data)}</div>'
    return _text_editor(ids, html)


def _build_faq(ids: _IdCounter, data: dict) -> dict:
    spoilers = []
    for i, line in enumerate(data.get("body", [])):
        line = line.strip()
        if not line:
            continue
        match = _FAQ_LINE_RE.match(line)
        if match:
            question, answer = match.group(1).strip(), match.group(2).strip()
        else:
            question, answer = line, ""
        open_attr = ' open="yes"' if i == 0 else ""
        spoilers.append(f'[su_spoiler title="{question}"{open_attr}]{answer}[/su_spoiler]')
    html = "[su_accordion]" + "".join(spoilers) + "[/su_accordion]"
    return _text_editor(ids, html)


def _build_byline(ids: _IdCounter, data: dict) -> list[dict]:
    body = data.get("body", [])
    name = body[0].strip() if body else ""
    credential = "\n".join(body[1:]).strip() if len(body) > 1 else ""
    return [_heading(ids, name, "h3"), _text_editor(ids, f"<p>{credential}</p>")]


def _build_rodape(ids: _IdCounter, data: dict) -> dict:
    html = f'<p style="font-size:12px;">{_body_text(data)}</p>'
    return _text_editor(ids, html)


def _build_botao(
    ids: _IdCounter, data: dict, href: str, brand_color: str, green: str, green_used: list[bool]
) -> dict:
    color = brand_color
    if data.get("cor") == "verde" and not green_used[0]:
        color = green
        green_used[0] = True
    text = data.get("texto", "")
    settings = {
        "text": text,
        "link": {"url": href, "is_external": "", "nofollow": ""},
        "align": "justify",
        "background_background": "classic",
        "background_color": color,
        "button_text_color": "#ffffff",
        "border_radius": {
            "unit": "px", "top": "10", "right": "10",
            "bottom": "10", "left": "10", "isLinked": True,
        },
    }
    return _widget(ids, "button", settings)


def build_elementor(
    markers: str,
    href: str,
    image_url: str | None,
    brand_color: str = "#c8102e",
    green: str = "#008456",
    id_seed: str = "",
    hero: bool = False,
) -> list:
    """Turn redactor marker text into an Elementor `content` array.

    Returns `[container]`, a single boxed container holding one widget per
    marker (BYLINE expands to two). Every BOTÃO link is forced to `href`;
    at most one button may use `green`, all others fall back to
    `brand_color`. Generated entirely from the markers -- no template
    cloning, Portuguese only.

    `id_seed` (typically the run id) run-scopes the generated widget IDs so
    they don't reset to the same `00000001...` sequence on every build --
    left at the default `""`, IDs remain the legacy deterministic sequence
    starting at 1 (so existing goldens/callers are unaffected).

    `hero` (default `False`) gates the 9:16 hero image. The winning LPs lead
    with the H1 as the LCP element -- a heavy hero image inserted before it
    is an LCP/CLS bomb, so by default no image widget is emitted at all
    (text-H1 is the LCP). Only when `hero=True` (via `run.hero_image` in
    config) is the image inserted first, ahead of the markers.
    """
    start = int(hashlib.sha1(id_seed.encode()).hexdigest(), 16) % 0x00FFFFFF if id_seed else 0
    ids = _IdCounter(start)
    container = {
        "id": ids.next(),
        "elType": "container",
        "settings": {"content_width": "boxed"},
        "elements": [],
    }

    if image_url and hero:
        container["elements"].append(_build_image(ids, image_url))

    green_used = [False]
    for w in parse_markers(markers):
        wtype, data = w["type"], w["data"]
        if wtype == "NAV":
            container["elements"].append(_build_nav(ids, data, brand_color))
        elif wtype == "TÍTULO (H1)":
            container["elements"].append(_build_titulo(ids, data, "h1"))
        elif wtype == "TÍTULO (H2)":
            container["elements"].append(_build_titulo(ids, data, "h2"))
        elif wtype == "TEXTO":
            container["elements"].append(_build_texto(ids, data))
        elif wtype == "LISTA":
            container["elements"].append(_build_lista(ids, data))
        elif wtype == "AVISO":
            container["elements"].append(_build_aviso(ids, data))
        elif wtype == "FAQ":
            container["elements"].append(_build_faq(ids, data))
        elif wtype == "BYLINE":
            container["elements"].extend(_build_byline(ids, data))
        elif wtype == "RODAPE":
            container["elements"].append(_build_rodape(ids, data))
        elif wtype == "BOTÃO":
            container["elements"].append(
                _build_botao(ids, data, href, brand_color, green, green_used)
            )
        # unknown widget types are ignored (defensive; redactor is contracted
        # to only emit the types listed above)

    return [container]
