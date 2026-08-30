"""
VOLC DOCX — Theme tokens (porta fiel do SKILL DOCX VOLC / volc-theme.js).

Referência: INSTITUCIONAL/SKILL DOCX VOLC/DESIGN.md (v1.0, abr/2026).
Stack original: Node + `docx`. Aqui: python-docx (mesmos tokens, mesma medida).

Unidades:
  - cores: hex sem '#'
  - font size: PONTOS (pt) — o DESIGN lista half-points; aqui já em pt
  - spacing de parágrafo: TWIPS (1/20 pt)
  - line spacing: MÚLTIPLO (val_twips / 240, onde 240 = simples)
  - border size: OITAVOS de ponto (padrão OOXML w:sz)
  - char spacing: VINTÉSIMOS de ponto (padrão OOXML w:spacing/@val)
  - página/margem: TWIPS
"""
from __future__ import annotations

# ---- cores -----------------------------------------------------------------
COLORS = {
    "navy": "0B1F3A",
    "navySoft": "1E3A5F",
    "gold": "B8860B",
    "goldSoft": "D4A017",
    "slate": "3D4A5C",
    "slateLight": "6B7280",
    "white": "FFFFFF",
    "bg": "F7F8FA",
    "bgDark": "E8EBF0",
    "bgAccent": "FDF6E3",
    "bgNavy": "EEF2F8",
    "red": "991B1B",
    "green": "166534",
    "border": "D1D5DB",
    "borderDark": "9CA3AF",
}

FONT_FAMILY = "Calibri"

# ---- tamanhos de fonte (pt) ------------------------------------------------
SIZE = {
    "coverTitle": 28,
    "h1": 20,
    "h2": 15,
    "h3": 12,
    "body": 11,
    "insightText": 12,
    "insightLabel": 10,
    "note": 10,
    "footnote": 9,
    "headerFooter": 8,
    "sectionNum": 9,
    "tableHeader": 10,
    "tableBody": 10,
    "coverLogo": 14,
    "coverLogoSub": 9,
}

# ---- character spacing (vintésimos de ponto) -------------------------------
CHAR_SPACING = {
    "logo": 80,
    "logoSubtitle": 60,
    "confidential": 80,
    "sectionNum": 100,
}

# ---- spacing de parágrafo (twips) ------------------------------------------
PARA = {
    "body": {"before": 80, "after": 80, "line": 320},
    "h1": {"before": 480, "after": 240},
    "h2": {"before": 360, "after": 160},
    "h3": {"before": 240, "after": 120},
    "bullet": {"before": 60, "after": 60, "line": 300},
}

SPACER = {"xs": 60, "sm": 120, "md": 200, "lg": 240, "xl": 320, "xxl": 480}

# ---- margens internas de célula (twips) ------------------------------------
CELL = {
    "tableHeader": {"top": 120, "bottom": 120, "left": 140, "right": 140},
    "tableBody": {"top": 100, "bottom": 100, "left": 140, "right": 140},
    "insightBox": {"top": 240, "bottom": 240, "left": 360, "right": 240},
    "noteBox": {"top": 160, "bottom": 160, "left": 300, "right": 200},
}

BULLET_INDENT = {"left": 720, "hanging": 360}

# ---- página (twips) --------------------------------------------------------
PAGE = {
    "width": 12240,   # US Letter 8.5"
    "height": 15840,  # 11"
    "margin": {"top": 1440, "right": 1440, "bottom": 1440, "left": 1440},
    "usableWidth": 9360,  # 6.5"
    "rightEdge": 9360,
    "tocRight": 9000,
}

# ---- bordas (oitavos de ponto) ---------------------------------------------
BORDER = {
    "h1Bottom": 12,
    "insightLeft": 24,
    "noteLeft": 16,
    "tableHeaderCell": 6,
    "tableBodyCell": 4,
    "headerBottom": 4,
    "footerTop": 4,
    "coverLogoBottom": 6,
}
