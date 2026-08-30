import json
from pathlib import Path
from funnelforge.adapters.elementor import parse_markers, build_elementor

MARKERS = """=== WIDGET: NAV ===
Home | Benefícios | Crédito e FGTS
---
=== WIDGET: TÍTULO (H1) ===
Saque-Aniversário do FGTS: entenda como funciona
---
=== WIDGET: BOTÃO ===
Texto: Ver o passo a passo
Cor: verde
Link: https://creditoup.com.br/rec/quem-tem-direito-pr
---
=== WIDGET: AVISO ===
Aviso de Utilidade Pública: Somos um portal informativo independente.
---
=== WIDGET: FAQ ===
1. Quem tem nome negativado pode antecipar? Sim. Usa o saldo do FGTS como garantia.
"""


def test_parse_markers_splits_widgets():
    ws = parse_markers(MARKERS)
    types = [w["type"] for w in ws]
    assert types[:3] == ["NAV", "TÍTULO (H1)", "BOTÃO"]
    assert ws[2]["data"]["link"] == "https://creditoup.com.br/rec/quem-tem-direito-pr"


def test_build_elementor_all_buttons_use_href_and_no_spanish():
    content = build_elementor(MARKERS, href="https://creditoup.com.br/rec/quem-tem-direito-pr",
                              image_url=None)
    blob = json.dumps(content, ensure_ascii=False)
    assert "colombia.eleicoes.org" not in blob
    assert "Ingreso" not in blob and "¿Cómo" not in blob
    # every button link is the single destination
    assert blob.count("https://creditoup.com.br/rec/quem-tem-direito-pr") >= 1


def test_golden_stability(tmp_path: Path):
    content = build_elementor(MARKERS, href="https://creditoup.com.br/rec/x", image_url=None)
    golden = Path("tests/golden/p1_elementor.json")
    if not golden.exists():
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    assert json.loads(golden.read_text(encoding="utf-8")) == content


def test_button_uses_valid_elementor_controls():
    content = build_elementor(
        "=== WIDGET: BOTÃO ===\nTexto: Ver o passo a passo\nCor: verde\nLink: x\n",
        href="https://creditoup.com.br/rec/x", image_url=None)
    btn = next(e for c in content for e in c["elements"]
               if e["widgetType"] == "button")
    s = btn["settings"]
    assert s["align"] == "justify"               # full-width, not scalar width:100
    assert s["background_background"] == "classic"  # bg group control
    assert isinstance(s["border_radius"], dict)     # dimensions control
    assert s["border_radius"]["unit"] == "px"
    assert s["link"]["url"] == "https://creditoup.com.br/rec/x"
    assert "width" not in s                          # invalid scalar removed


def test_preview_renders_dict_border_radius():
    from funnelforge.pipeline.steps import _preview_html
    from funnelforge.domain.models import Page
    page = Page(page_number=1, page_type="LANDING PAGE", h1_title="H", slug="s")
    content = build_elementor(
        "=== WIDGET: BOTÃO ===\nTexto: Ir\nLink: x\n",
        href="https://creditoup.com.br/rec/x", image_url=None)
    html = _preview_html(page, content)
    assert "border-radius:10px" in html   # not the dict repr
    assert "{'unit'" not in html


def test_no_hero_image_by_default():
    content = build_elementor(
        "=== WIDGET: TÍTULO (H1) ===\nSaque FGTS\n",
        href="https://creditoup.com.br/rec/x", image_url="https://img/x.webp")
    types = [e["widgetType"] for c in content for e in c["elements"]]
    assert "image" not in types                       # 9:16 hero retired
    assert content[0]["elements"][0]["widgetType"] == "heading"  # H1 is LCP


def test_hero_image_only_behind_flag():
    content = build_elementor(
        "=== WIDGET: TÍTULO (H1) ===\nSaque FGTS\n",
        href="https://creditoup.com.br/rec/x", image_url="https://img/x.webp",
        hero=True)
    assert content[0]["elements"][0]["widgetType"] == "image"
