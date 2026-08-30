"""
Task 11 (Pautador Pro / R4): o briefing DOCX do funil deve renderizar
`intro_section` (antes da lista de H2 da página) e `closing_section`
(depois dela). Formato de entrada: shape CANÔNICA da FunnelPage
(`page_title`, `subtitles`, `intro_section`, `closing_section`, ...),
que é a mesma que chega ao composer via `routers/entities.py`
(`funnel_architecture.pages` persistido por `architect_pages_to_funnel_pages`).

Pautador Pro (refactor pt-BR + diretrizes em bullets): `intro_section` e
`closing_section` agora são ARRAYS de bullets em pt-BR (diretrizes para o
redator, não prosa pronta) sob os rótulos "Introdução (diretrizes)" e
"Fechamento (diretrizes)". Um funil já gerado ANTES dessa mudança ainda pode
ter esses campos como string simples (legado) — o DOCX precisa continuar
renderizando esse caso sem quebrar.
"""
from __future__ import annotations

import io

from docx import Document

from app.docx import build_funnel_briefing

INTRO_MARKER = "INTRO_MARKER_TEXT"
CLOSING_MARKER = "CLOSING_MARKER_TEXT"
INTRO_BULLET_1 = "Abrir com o gancho provocativo INTRO_MARKER_TEXT"
INTRO_BULLET_2 = "Prometer esclarecer o próximo passo"
CLOSING_BULLET_1 = "Recapitular o valor entregue CLOSING_MARKER_TEXT"
CLOSING_BULLET_2 = "Reforçar a utilidade desta página"


def _card():
    return {
        "entity": {
            "canonical_name": "Entidade Teste",
            "full_name": "Entidade Teste Completa",
            "country": "Brasil",
        },
        "country_code": "BR",
        "insights": "",
    }


def _funnel(*, intro_closing=None) -> dict:
    page = {
        "position": 1,
        "page_title": "Página Um",
        "role_label": "Landing Page",
        "emotional_goal": "Capturar atenção inicial.",
        "subtitles": ["Primeiro H2 da página", "Segundo H2 da página"],
        "internal_links": [],
    }
    if intro_closing is not None:
        intro, closing = intro_closing
        page["intro_section"] = intro
        page["closing_section"] = closing
    return {
        "funnel_strategy": {"avatar_summary": "Avatar teste", "tone_voice": "Direto"},
        "pages": [page],
        "writing_jobs": [],
        "funnel_hypotheses": [{"title": "Funil Teste"}],
    }


def _paragraph_texts(docx_bytes: bytes) -> list[str]:
    doc = Document(io.BytesIO(docx_bytes))
    return [p.text for p in doc.paragraphs]


def test_intro_and_closing_bullets_render_around_h2_list():
    """Caso NOVO: intro_section/closing_section são listas de bullets pt-BR —
    cada bullet deve renderizar como seu próprio parágrafo, sob os novos
    rótulos, intro ANTES do bloco de H2 e closing DEPOIS."""
    docx_bytes = build_funnel_briefing(
        _card(),
        _funnel(intro_closing=([INTRO_BULLET_1, INTRO_BULLET_2], [CLOSING_BULLET_1, CLOSING_BULLET_2])),
    )
    texts = _paragraph_texts(docx_bytes)

    assert any(t.strip() == "Introdução (diretrizes)" for t in texts)
    assert any(t.strip() == "Fechamento (diretrizes)" for t in texts)

    intro_bullet_1_idx = next(i for i, t in enumerate(texts) if INTRO_BULLET_1 in t)
    intro_bullet_2_idx = next(i for i, t in enumerate(texts) if INTRO_BULLET_2 in t)
    closing_bullet_1_idx = next(i for i, t in enumerate(texts) if CLOSING_BULLET_1 in t)
    closing_bullet_2_idx = next(i for i, t in enumerate(texts) if CLOSING_BULLET_2 in t)

    # cada bullet é seu PRÓPRIO parágrafo (não um único parágrafo concatenado)
    assert intro_bullet_1_idx != intro_bullet_2_idx
    assert closing_bullet_1_idx != closing_bullet_2_idx

    h2_indices = [i for i, t in enumerate(texts) if "Primeiro H2 da página" in t or "Segundo H2 da página" in t]
    assert h2_indices, "esperava encontrar os H2 (subtitles) da página no documento"
    first_h2_idx = min(h2_indices)
    last_h2_idx = max(h2_indices)

    assert max(intro_bullet_1_idx, intro_bullet_2_idx) < first_h2_idx, "intro_section deve aparecer ANTES do primeiro H2"
    assert min(closing_bullet_1_idx, closing_bullet_2_idx) > last_h2_idx, "closing_section deve aparecer DEPOIS do último H2"


def test_legacy_string_intro_and_closing_still_renders():
    """Caso LEGADO: funil já gerado antes da mudança, com intro_section/
    closing_section como string simples — precisa continuar renderizando
    (como um único parágrafo), sem quebrar."""
    docx_bytes = build_funnel_briefing(
        _card(),
        _funnel(intro_closing=(INTRO_MARKER, CLOSING_MARKER)),
    )
    texts = _paragraph_texts(docx_bytes)

    assert any(t.strip() == "Introdução (diretrizes)" for t in texts)
    assert any(t.strip() == "Fechamento (diretrizes)" for t in texts)
    assert any(INTRO_MARKER in t for t in texts)
    assert any(CLOSING_MARKER in t for t in texts)


def test_backward_compatible_without_intro_closing():
    """Páginas sem intro_section/closing_section renderizam exatamente como antes
    (sem quebrar, sem rótulos 'Introdução (diretrizes)'/'Fechamento (diretrizes)' soltos)."""
    docx_bytes = build_funnel_briefing(_card(), _funnel(intro_closing=None))
    texts = _paragraph_texts(docx_bytes)

    assert not any(INTRO_MARKER in t for t in texts)
    assert not any(CLOSING_MARKER in t for t in texts)
    assert not any(t.strip() == "Introdução (diretrizes)" for t in texts)
    assert not any(t.strip() == "Fechamento (diretrizes)" for t in texts)
    assert any("Primeiro H2 da página" in t for t in texts)
