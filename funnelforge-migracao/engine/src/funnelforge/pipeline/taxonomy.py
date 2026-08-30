"""Funnel taxonomy + interlink CONTRACT (reference spec + advisory checks).

Documents the winning-funnel rules the pipeline already implements
deterministically -- `domain.models.derive_role` (page-type by slug suffix) and
`pipeline.routing.build_funnel_routes` (the CTA interlink graph). This module is
the SPEC/reference; the code above is the authoritative implementation.
`contract_advisories` cross-checks a BUILT plan against the rules and returns
NON-BLOCKING notes (surfaced in the report, never fail-closed).
"""
from __future__ import annotations

import json
from importlib import resources

from funnelforge.domain.models import FunnelPlan, PageRole, effective_role

# page_type by slug suffix (mirrors domain.models.derive_role)
SUFFIX_TO_ROLE = {"<no suffix>": "LP", "-prN": "PRESELL", "-p<N>": "SOLUTION"}

# CTA interlink graph per role (the winning, non-looping, forward-only typed graph)
INTERLINK_RULES = {
    "LP": ("HUB ÚNICO (run.presell_hubs=1): botão 1 -> a PRESELL (-pr); botões "
           "seguintes -> as `lp_direct_solutions` primeiras SOLUÇÕES, direto. "
           ">80% dos cliques ficam no primeiro botão, então ele leva ao "
           "qualificador; os demais cortam caminho. Com presell_hubs=3 volta a "
           "ser 1 CTA por hub (-pr1/-pr2/-pr3)."),
    "PRESELL": ("fan-out NEUTRO: 1 CTA por SOLUÇÃO, sem solução privilegiada no hero; "
                "hub qualificador; cada H2 é o preview de uma solução. É ele que "
                "garante alcançabilidade das soluções sem botão direto na LP."),
    "SOLUTION": ("FORWARD-ONLY: fan-out para TODAS as soluções seguintes "
                 "(p_i -> {p_i+1..p_n}, OVERRIDE-1) + 1 saída OFICIAL externa; "
                 "sem aresta para trás, sem cross-funnel no miolo. A terminal "
                 "(maior ordinal) para de avançar e recircula CROSS-FUNNEL apenas "
                 "(URL real do sitemap, relacionado-mas-diverso)."),
}


def load_contract() -> dict:
    """Load the packaged funnel contract JSON (reference/fixture)."""
    raw = resources.files("funnelforge").joinpath(
        "templates/funnel_contract.json").read_text(encoding="utf-8")
    return json.loads(raw)


def contract_advisories(plan: FunnelPlan) -> list[str]:
    """ADVISORY (non-blocking) checks of a built plan against the interlink
    contract: EVERY presell must FAN OUT to every solution; the terminal solution
    must have a cross-funnel exit; no page may route to itself."""
    notes: list[str] = []
    if plan is None or not plan.pages:
        return notes
    solutions = sorted((p for p in plan.pages if effective_role(p) is PageRole.SOLUTION),
                       key=lambda p: p.ordinal)
    presells = [p for p in plan.pages if effective_role(p) is PageRole.PRESELL]
    if presells and solutions:
        for presell in presells:
            targets = {r.target for r in presell.routes if r.kind == "funnel"}
            missing = [s.slug for s in solutions if s.slug not in targets]
            if missing:
                notes.append(f"presell '{presell.slug}' não faz fan-out para todas "
                            f"as soluções; faltam: {missing}")
    if solutions and not any(r.kind == "cross_funnel" for r in solutions[-1].routes):
        notes.append(f"solução terminal '{solutions[-1].slug}' sem saída cross-funnel.")
    for p in plan.pages:
        if any(r.kind == "funnel" and r.target == p.slug for r in p.routes):
            notes.append(f"página '{p.slug}' tem CTA para si mesma (self-loop).")
    return notes
