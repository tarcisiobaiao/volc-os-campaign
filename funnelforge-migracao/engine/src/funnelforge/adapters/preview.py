"""Preview local do payload final: árvore, estilos e breakpoints do Elementor.

Não executa PHP/WordPress. Gutenberg usa CSS editorial local e o hardening
versionado; o recibo sempre registra essa limitação de fidelidade ao tema.
"""
from __future__ import annotations

import re
from html import escape

CSS = """
*{box-sizing:border-box}body{margin:0;color:#242424;background:#fff;font:18px/1.6 Arial,sans-serif}
main{max-width:760px;margin:auto;padding:24px}h1{font-size:clamp(28px,4vw,40px);line-height:1.2}
h2{font-size:26px;line-height:1.3}h3{font-size:22px;line-height:1.3}p{margin:0 0 18px}
a{color:#005e43;text-decoration:underline;overflow-wrap:anywhere}img{max-width:100%;height:auto}
.e-container{display:flex;flex-direction:column;gap:20px;width:100%;min-width:0}
.e-widget{width:100%;min-width:0}.e-widget h1,.e-widget h2,.e-widget h3{margin:0}
.elementor-button,.wp-block-button__link{display:inline-flex;align-items:center;justify-content:center;
 min-width:44px;min-height:44px;padding:14px 20px;border-radius:8px;background:#006b45;color:white;
 font-weight:700;line-height:1.4;text-decoration:none;max-width:100%;text-align:center}
.wp-block-buttons{display:flex;flex-wrap:wrap;gap:12px;margin:24px 0}
a:hover{ text-decoration:underline;text-decoration-thickness:2px}
a:focus-visible,summary:focus-visible,button:focus-visible,input:focus-visible{
outline:3px solid #162e51;outline-offset:3px}
.elementor-button:hover,.wp-block-button__link:hover{filter:brightness(.85)}
figure{margin:24px 0}.wp-block-table{overflow-x:auto}table{border-collapse:collapse;width:100%}
td,th{padding:12px;border:1px solid #cbd5e1;text-align:left;vertical-align:top;overflow-wrap:anywhere}
.wp-block-columns{display:flex;gap:24px}.wp-block-column{flex:1;min-width:0}
details{border:1px solid #cbd5e1;border-radius:6px;padding:12px;margin:12px 0}
summary{cursor:pointer;min-height:44px;font-weight:700}details p{margin-top:12px}
footer{padding:24px;max-width:100%;background:#f5f5f5;font-size:14px;color:#333}
@media(max-width:767px){main{padding:20px}.wp-block-columns{flex-direction:column}}
"""


def _size(value):
    if not isinstance(value, dict) or value.get("size") in (None, ""):
        return ""
    return str(value['size']) + (value.get('unit', 'px') if value.get('unit') != 'custom' else '')


def _style(s: dict, suffix: str = "", *, widget: bool = False) -> str:
    rules = []
    def put(prop, key, convert=str):
        value = s.get(key + suffix)
        if value is not None and value != "":
            converted = convert(value)
            if converted:
                rules.append(f"{prop}:{converted}")
    for prop, key in [('background-color','background_color'),('color','title_color'),
                      ('text-align','align'),('flex-direction','flex_direction'),
                      ('justify-content','flex_justify_content'),('align-items','flex_align_items'),
                      ('font-weight','typography_font_weight')]:
        put(prop, key)
    for prop, key in [('min-height','min_height'),('font-size','typography_font_size'),
                      ('line-height','typography_line_height'),('gap','flex_gap')]:
        put(prop, key, _size)
    for key in ['padding', 'margin', '_margin']:
        v = s.get(key + suffix)
        if isinstance(v, dict):
            unit = v.get('unit','px')
            rules.append(f"{key.lstrip('_')}:" + ' '.join(
                str(v.get(side) or 0) + unit for side in ['top','right','bottom','left']))
    bg = s.get('background_image' + suffix)
    if isinstance(bg, dict) and bg.get('url'):
        rules += [f"background-image:url('{bg['url']}')", 'background-size:cover',
                  'background-position:top center']
    if s.get('hide' + suffix) == 'hidden' + suffix.replace('_', '-'):
        rules.append('display:none')
    return ';'.join(rules)


def _accordion(text: str) -> str:
    text = re.sub(r'\[su_spoiler title="(.*?)" open="(yes|no)"[^\]]*\](.*?)\[/su_spoiler\]',
                  lambda m: f'<details{" open" if m[2] == "yes" else ""}>'
                  f'<summary>{m[1]}</summary><p>{m[3]}</p></details>', text, flags=re.S)
    return text.replace('[su_accordion]', '').replace('[/su_accordion]', '')


def elementor_body(nodes: list) -> tuple[str, str]:
    styles = []
    def render(node):
        ident = 'el-' + node['id']
        s = node.get('settings') or {}
        for suffix, media in [('', ''),('_desktop','(min-width:1025px)'),
                              ('_tablet','(min-width:768px) and (max-width:1024px)'),
                              ('_mobile','(max-width:767px)')]:
            rule = f'#{ident}{{{_style(s, suffix)}}}'
            styles.append(f'@media{media}{{{rule}}}' if media else rule)
        children = ''.join(render(c) for c in node.get('elements', []))
        w = node.get('widgetType')
        if w == 'heading':
            tag = s.get('header_size', 'h2')
            if s.get('typography_font_size'):
                styles.append(f'#{ident}>{tag}{{font-size:inherit;line-height:inherit;font-weight:inherit}}')
            children = f'<{tag}>{s.get("title", "")}</{tag}>'
        elif w == 'text-editor':
            children = _accordion(s.get('editor',''))
        elif w == 'html':
            children = s.get('html','')
        elif w == 'image':
            children = (f'<img src="{escape(s.get("image",{}).get("url",""),quote=True)}" '
                        f'alt="{escape(s.get("image",{}).get("alt",""),quote=True)}">')
        elif w == 'button':
            button_style = (f'background:{s.get("background_color", "#006b45")};'
                            f'color:{s.get("button_text_color", "#fff")};')
            if s.get('align') == 'justify':
                button_style += 'width:100%;'
            children = (f'<a class="elementor-button" style="{button_style}" '
                        f'href="{escape(s.get("link",{}).get("url",""),quote=True)}">'
                        f'{s.get("text", "")}</a>')
        elif w == 'divider':
            children = f'<hr style="border:0;border-top:3px solid {s.get("color", "#ddd")};width:25%">'
        return f'<div id="{ident}" class="e-{"widget" if w else "container"}">{children}</div>'
    return ''.join(render(n) for n in nodes), '\n'.join(styles)


def document(title: str, body: str, *, css: str = "", head: str = "", footer: str = "",
             body_class: str = "") -> str:
    classe = f' class="{escape(body_class)}"' if body_class else ""
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{escape(title)}</title>{head}<style>{CSS}\n{css}</style></head>'
            f'<body{classe}><main>{body}</main>{"<footer>" + escape(footer) + "</footer>" if footer else ""}'
            '</body></html>')
