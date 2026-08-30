"""
Papéis das páginas do funil + sufixos de slug — determinístico por POSIÇÃO.

Regra (resgatada do conceito do arquiteto):
  P1  -> Landing Page (Pouso)   | slug INTACTA
  P2  -> Pre-sell               | slug + "-pr"
  P3+ -> Página Solução N       | slug + "-p{N}"  (N = posição - 2)

Aplicado UMA vez na saída do arquiteto (backend), reescrevendo também as
referências cruzadas (CTAs, links internos, H2s que citam "/slug"), pra os links
apontarem para a slug nova. Front e DOCX só renderizam `role_label`.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


def role_for_position(pos: int) -> Tuple[str, str, str]:
    """Retorna (role, label, slug_suffix) para a posição da página (1-based)."""
    if pos <= 1:
        return ("landing", "Landing Page (Pouso)", "")
    if pos == 2:
        return ("presell", "Pre-sell", "-pr")
    n = pos - 2
    return ("solution", f"Página Solução {n}", f"-p{n}")


def _apply_suffix(slug: str, suffix: str) -> str:
    slug = (slug or "").strip().lstrip("/")
    if not slug or not suffix:
        return slug
    return slug if slug.endswith(suffix) else slug + suffix


def apply_roles_and_slugs(
    pages: List[Dict[str, Any]], writing_jobs: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Anota role/role_label nas páginas e writing_jobs e reescreve as slugs
    (própria + todas as referências) conforme a regra por posição. Idempotente."""
    pages = pages or []
    writing_jobs = writing_jobs or []

    # slug "própria" de cada página vem do writer_briefing.current_url
    wj_by_pos: Dict[int, Dict[str, Any]] = {}
    for j in writing_jobs:
        wb = j.get("writer_briefing") or {}
        try:
            wj_by_pos[int(wb.get("page_num"))] = j
        except (TypeError, ValueError):
            continue

    # mapa old_slug -> new_slug
    slug_map: Dict[str, str] = {}
    for pos, j in wj_by_pos.items():
        wb = j.get("writer_briefing") or {}
        old = (wb.get("current_url") or "").strip().lstrip("/")
        if not old:
            continue
        _, _, suffix = role_for_position(pos)
        slug_map[old] = _apply_suffix(old, suffix)

    # regex de reescrita: "/oldslug" (com fronteira) -> "/newslug"; longest-first
    changed = [o for o in slug_map if slug_map[o] != o]
    olds = sorted(changed, key=len, reverse=True)
    pat = re.compile(r"/(" + "|".join(re.escape(o) for o in olds) + r")(?![\w-])") if olds else None

    def rw(text: Any) -> Any:
        if not isinstance(text, str) or pat is None:
            return text
        return pat.sub(lambda m: "/" + slug_map[m.group(1)], text)

    # páginas: role/label + reescreve refs em H2s (subtitles) e links internos
    for p in pages:
        try:
            role, label, _ = role_for_position(int(p.get("position")))
            p["role"], p["role_label"] = role, label
        except (TypeError, ValueError):
            pass
        p["subtitles"] = [rw(s) for s in (p.get("subtitles") or [])]
        p["internal_links"] = [rw(l) for l in (p.get("internal_links") or [])]

    # writing_jobs: slug própria + cta_link/skeleton + role/label
    for j in writing_jobs:
        wb = j.get("writer_briefing") or {}
        old = (wb.get("current_url") or "").strip().lstrip("/")
        if old in slug_map:
            wb["current_url"] = slug_map[old]
        if wb.get("cta_link"):
            wb["cta_link"] = rw(wb["cta_link"])
        if wb.get("skeleton"):
            wb["skeleton"] = rw(wb["skeleton"])
        try:
            role, label, _ = role_for_position(int(wb.get("page_num")))
            j["role"], j["role_label"] = role, label
        except (TypeError, ValueError):
            pass

    return pages, writing_jobs
