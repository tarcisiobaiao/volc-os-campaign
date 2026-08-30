"""
Page Factory — faithful port of n8n-funnel-builder.json node
"Code in JavaScript" (🏭 PAGE FACTORY V4 — LINKS NATIVOS). Turns the Funnel
Architect JSON ({funnel_strategy, pages}) into `writingJobs` (one briefing per
page) + meta. Also maps the architect pages to the canonical FunnelPage shape
used by the existing UI/DB (position/page_title/avatar/stage/...).
"""
from __future__ import annotations

from typing import Any, Dict, List

_STAGE_BY_TYPE = {
    "LANDING PAGE": "tofu",
    "HUB": "mofu",
    "PRÉ-SELL": "mofu",
    "PRE-SELL": "mofu",
    "SOLUÇÃO": "bofu",
    "SOLUCAO": "bofu",
}
_DEFAULT_STAGE_BY_POS = {1: "tofu", 2: "tofu", 3: "mofu", 4: "mofu", 5: "bofu"}


def page_factory(ai_output: Dict[str, Any]) -> Dict[str, Any]:
    """Port of the PAGE FACTORY Code node. `ai_output` is the parsed architect JSON."""
    pages = ai_output.get("pages") or []
    global_strategy = ai_output.get("funnel_strategy") or {}

    if not pages:
        return {"writingJobs": [], "meta": {"total_pages": 0, "funnel_strategy": global_strategy}}

    writing_jobs: List[Dict[str, Any]] = []
    total = len(pages)
    for index, page in enumerate(pages):
        structure = page.get("main_content_structure")
        if isinstance(structure, list):
            structure_text = "\n- ".join(str(s) for s in structure)
        else:
            structure_text = structure

        target_keywords = page.get("target_keywords")
        if isinstance(target_keywords, list):
            keywords_text = ", ".join(str(k) for k in target_keywords)
        else:
            keywords_text = "Keywords do tema principal"

        next_slug = page.get("next_page_slug")
        if next_slug:
            next_link = f"/{next_slug}"
        elif index + 1 < total:
            next_link = f"/pagina-{index + 2}"
        else:
            next_link = "/inicio"

        writing_jobs.append(
            {
                "job_id": f"write_p{page.get('page_number')}",
                "page_type": page.get("page_type"),
                "writer_briefing": {
                    "avatar_context": global_strategy.get("avatar_summary") or "Público geral",
                    "tone": global_strategy.get("tone_voice") or "Informativo",
                    "page_num": page.get("page_number"),
                    "total_pages": total,
                    "headline": page.get("h1_title"),
                    "objective": page.get("emotional_objective"),
                    "current_url": page.get("slug") or f"pagina-{page.get('page_number')}",
                    "cta_text": page.get("hook_to_next_page") or "Avançar",
                    "cta_link": next_link,
                    "skeleton": f"- {structure_text}",
                    "keywords": keywords_text,
                    # R4: intro/fechamento (Task 6) propagados para o briefing do
                    # writer. Default "" p/ compat com páginas mock/fallback que
                    # ainda não têm esses campos.
                    "intro_section": page.get("intro_section") or "",
                    "closing_section": page.get("closing_section") or "",
                },
            }
        )

    return {
        "writingJobs": writing_jobs,
        "meta": {"total_pages": total, "funnel_strategy": global_strategy},
    }


def architect_pages_to_funnel_pages(ai_output: Dict[str, Any], persona_fallback: str = "") -> List[Dict[str, Any]]:
    """Map architect `pages` -> canonical FunnelPage rows (for DB + existing drawer)."""
    pages = ai_output.get("pages") or []
    strategy = ai_output.get("funnel_strategy") or {}
    avatar = strategy.get("avatar_summary") or persona_fallback or None
    out: List[Dict[str, Any]] = []
    for idx, p in enumerate(pages):
        position = int(p.get("page_number") or (idx + 1))
        ptype = str(p.get("page_type") or "").upper()
        stage = _STAGE_BY_TYPE.get(ptype) or _DEFAULT_STAGE_BY_POS.get(position, "tofu")
        structure = p.get("main_content_structure") or []
        subtitles = [str(s) for s in structure] if isinstance(structure, list) else [str(structure)]
        links: List[str] = []
        if p.get("hook_to_next_page"):
            slug = p.get("next_page_slug")
            links.append(f"{p['hook_to_next_page']} → /{slug}" if slug else str(p["hook_to_next_page"]))
        out.append(
            {
                "position": position,
                "page_title": p.get("h1_title") or f"Página {position}",
                "avatar": avatar,
                "stage": stage,
                "emotional_goal": p.get("emotional_objective") or "",
                "subtitles": subtitles,
                "internal_links": links,
                # R4: intro/fechamento (Task 6) propagados para a FunnelPage
                # canônica. Default "" p/ compat com páginas mock/fallback que
                # ainda não têm esses campos.
                "intro_section": p.get("intro_section") or "",
                "closing_section": p.get("closing_section") or "",
            }
        )
    out.sort(key=lambda x: x["position"])
    return out
