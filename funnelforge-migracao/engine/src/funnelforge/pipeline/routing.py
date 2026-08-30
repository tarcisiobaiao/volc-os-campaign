from __future__ import annotations

import re

from funnelforge.config.settings import Settings
from funnelforge.domain.models import (
    FunnelPlan, Issue, Page, PageRole, Route, effective_role, resolve_route,
)
from funnelforge.pipeline.doctrine import APPROVED_CTA_EXEMPLARS
from funnelforge.pipeline.pagespec import _sig_tokens, pagespec_for

# The trailing `-prN` index of a presell hub slug, used to rotate its fan-out
# order NEUTRALLY (offset=(N-1)%n) so no solution is privileged in the hero.
_PRESELL_INDEX_RE = re.compile(r"-pr(\d+)$")


def presell_rotation_offset(slug: str, n: int) -> int:
    """Neutral rotation offset for a presell hub: (N-1) % n where N is the
    `-prN` suffix index (1-based). A hub with no numeric suffix (the raw
    pre-expansion mapper slug) rotates from 0."""
    if n <= 0:
        return 0
    m = _PRESELL_INDEX_RE.search(slug)
    idx = int(m.group(1)) if m else 1
    return (idx - 1) % n


def _placement(i: int, n: int) -> str:
    if i == 0:
        return "hero"
    if i == n - 1:
        return "footer"
    return "inline"


def _anchor_for(target_h1: str, i: int) -> str:
    """Descriptive 3rd-person anchor congruent with the target H1 (shares a
    significant token so enforce_pagespec's anchor_congruent passes)."""
    base = APPROVED_CTA_EXEMPLARS[i % len(APPROVED_CTA_EXEMPLARS)]
    tok = next(iter(sorted(_sig_tokens(target_h1))), "")
    if not tok:
        return base
    return f"Ver o guia de {tok} >>>"


def is_terminal_solution(page: Page, solutions: list[Page]) -> bool:
    """The terminal SOLUTION is the highest-`ordinal` page in the funnel: it
    stops advancing (no forward funnel edge) and recirculates cross-funnel
    instead. Same rule `validate_funnel_graph` uses for `terminal_no_exit`."""
    if not solutions:
        return False
    return page.ordinal == max(s.ordinal for s in solutions)


def build_funnel_routes(plan: FunnelPlan, settings: Settings,
                        cross_funnel_targets: list[str] | None = None) -> None:
    """Deterministically assign page.routes for the HONEST winning graph.
    resolve_route is the SOLE href former; any invalid route raises ValueError
    (fail-closed).

    The graph (Plano A): LP -> exactly the N distinct PRESELL hubs; each
    PRESELL is a NEUTRAL qualifier hub that fans out to every SOLUTION with a
    per-hub NEUTRAL ROTATION (offset=(N-1)%n by its `-prN` index) -- no
    privileged lead solution in the hero; each mid SOLUTION FANS OUT forward
    (OVERRIDE-1) to EVERY subsequent solution (p_i -> {p_{i+1}..p_n}, each
    anchor congruent to its destination) plus one official external link --
    forward-only + acyclic by construction; the terminal SOLUTION (max ordinal)
    stops advancing and recirculates cross-funnel only.

    `cross_funnel_targets` are REAL absolute same-domain URLs (from the site
    sitemap) for the SOLUTION cross-funnel exit -- a related-but-diverse guide,
    never an invented slug. Fallback: config `cross_funnel_lps` slugs, built as
    absolute URLs under `lp_post_type` (so they too resolve as real URLs)."""
    pages = plan.pages
    presells = sorted((p for p in pages if effective_role(p) is PageRole.PRESELL),
                      key=lambda p: (p.ordinal, p.slug))
    solutions = sorted((p for p in pages if effective_role(p) is PageRole.SOLUTION),
                       key=lambda p: p.ordinal)
    cross = list(cross_funnel_targets or [])
    if not cross:
        base = settings.site.domain.rstrip("/")
        pt = settings.site.lp_post_type
        cross = [f"{base}/{pt}/{s.strip('/')}" for s in settings.site.cross_funnel_lps]
    for page in pages:
        role = effective_role(page)
        spec = pagespec_for(settings, role)
        routes: list[Route] = []
        if role is PageRole.LP:
            # LP -> os HUBS primeiro, depois as N primeiras SOLUÇÕES direto.
            #
            # `lp_direct_solutions=0` reproduz o grafo antigo (LP -> só hubs).
            # Com 1 hub e 2 diretas sai [hub, p1, p2]: o primeiro botão leva ao
            # qualificador (medido em campo: >80% dos cliques) e os demais
            # cortam caminho para a solução, sem custar uma página de hub que
            # quase ninguém abriria.
            #
            # Nenhuma solução fica ilhada: o hub faz fan-out para TODAS, e o
            # encadeamento forward entre soluções (p_i -> {p_i+1..p_n}) cobre o
            # resto. Uma solução com botão direto NA LP continua recebendo
            # aresta do hub -- dois caminhos de entrada, nunca um ciclo, porque
            # nenhuma aresta aponta para a LP.
            diretas = solutions[:max(0, settings.run.lp_direct_solutions)]
            alvos = [*presells, *diretas][:spec.cta_max]
            if alvos:
                routes = [Route(placement=_placement(i, len(alvos)), kind="funnel",
                                target=t.slug, anchor=_anchor_for(t.h1_title, i))
                          for i, t in enumerate(alvos)]
            else:
                routes = [Route(placement="hero", kind="funnel",
                                target=page.next_page_slug, anchor=_anchor_for("", 0))]
        elif role is PageRole.PRESELL:
            # FAN-OUT (NEUTRAL): the presell is a qualifier hub that opens EVERY
            # solution. Order is a NEUTRAL ROTATION keyed on the `-prN` index
            # (offset=(N-1)%n), NOT a privileged lead -- so no solution is
            # always first across the 3 hubs. Cap (I8) to spec.cta_max by
            # walking the SOLUTION ring from the offset; because different hubs
            # start at different offsets, every solution keeps an inbound edge
            # so reachability survives the cap regardless of how many solutions.
            if solutions:
                n = len(solutions)
                offset = presell_rotation_offset(page.slug, n)
                ordered = [solutions[(offset + k) % n] for k in range(n)]
                if len(ordered) > spec.cta_max:
                    ordered = ordered[:spec.cta_max]
                routes = [Route(placement=_placement(i, len(ordered)), kind="funnel",
                                target=s.slug, anchor=_anchor_for(s.h1_title, i))
                          for i, s in enumerate(ordered)]
            else:
                routes = [Route(placement="hero", kind="funnel",
                                target=page.next_page_slug, anchor=_anchor_for("", 0))]
        else:  # SOLUTION
            if is_terminal_solution(page, solutions):
                # Terminal: stop advancing, recirculate cross-funnel ONLY.
                if cross:
                    routes = [Route(placement="footer", kind="cross_funnel",
                                    target=cross[page.ordinal % len(cross)],
                                    anchor="Ver outro guia completo >>>")]
                else:
                    routes = []
            else:
                # Mid: FAN-OUT forward (OVERRIDE-1). Emit ONE funnel edge to
                # EVERY subsequent solution (p_i -> {p_{i+1}..p_n}), each with an
                # anchor congruent to ITS OWN destination h1, + ONE official
                # external link. Forward-only + acyclic are preserved BY
                # CONSTRUCTION: every edge targets a strictly-higher ordinal
                # (solutions is ordinal-sorted, so `forward` is exactly the
                # higher-ordinal tail) -- no mesh backward, no cross-funnel here.
                idx = next(i for i, s in enumerate(solutions) if s.slug == page.slug)
                forward = solutions[idx + 1:]
                routes = [Route(placement="inline", kind="funnel", target=s.slug,
                                anchor=_anchor_for(s.h1_title, i))
                          for i, s in enumerate(forward)]
                # O CANAL OFICIAL NÃO É DECIDIDO AQUI.
                # Este builder roda ANTES da pesquisa (pipeline._populate_routes),
                # então qualquer URL escolhida agora seria chute de configuração --
                # foi assim que um funil de entregador do iFood ganhou um botão
                # "Consultar no canal oficial" apontando para https://www.gov.br.
                # A aresta `external_official` é ligada DEPOIS, por
                # `bind_official_route`, com a URL que a pesquisa DESTA página
                # trouxe e o Chromium confirmou.
        for r in routes:            # LEI DO MESMO DOMÍNIO, aplicada uma vez
            # Só existem rotas `funnel`/`cross_funnel` aqui: a `external_official`
            # nasce depois, já com a URL da pesquisa (ver bind_official_route).
            resolve_route(r, domain=settings.site.domain,
                          post_type=settings.site.post_type)
        page.routes = routes


ANCORA_CANAL_OFICIAL = "Consultar no canal oficial >>>"


def bind_official_route(page: Page, official_links: list[str], *,
                        role: PageRole, is_terminal: bool) -> None:
    """Liga (tarde) a aresta `external_official` desta página, com a URL que a
    PESQUISA dela trouxe.

    Por que tarde: `build_funnel_routes` roda antes da pesquisa, então lá o
    canal oficial só podia sair de configuração -- e configuração de canal
    oficial é o que fazia um funil de entregador do iFood apontar para gov.br.
    Aqui já existe evidência: `official_links[0]` é a melhor URL que a busca
    daquela página devolveu, verificada.

    IDEMPOTENTE de propósito: remove qualquer `external_official` anterior antes
    de recolocar, porque `_write_ctx` roda duas vezes por página (redação e
    gate final) e não pode acumular rota.

    Sem `official_links` a página fica SEM canal oficial e o `pagespec` reprova
    com `target_missing` -- fail-closed por ausência de prova, que é o
    comportamento correto: publicar uma solução que manda o leitor a lugar
    nenhum é pior do que não publicar."""
    page.routes = [r for r in page.routes if r.kind != "external_official"]
    if role is not PageRole.SOLUTION or is_terminal:
        return  # a terminal só recircula cross-funnel; LP/PRESELL nunca citam canal
    if not official_links:
        return
    page.routes = [*page.routes,
                   Route(placement="inline", kind="external_official",
                         target=official_links[0], anchor=ANCORA_CANAL_OFICIAL)]


def resolve_page_links(page: Page, settings: Settings, *,
                       authorized_external: list[str] | None = None) -> list[dict[str, str]]:
    # `kind` is carried through so the interior-page writer can DISTRIBUTE CTAs
    # across the recirculation set (funnel siblings + cross_funnel) instead of
    # clustering every button on the first funnel target -- and so the terminal
    # page can favour the cross_funnel exit. See redator_pages.jinja.
    #
    # `authorized_external` são as URLs externas que a pesquisa DESTA página
    # autorizou (normalmente as mesmas de `bind_official_route`). Sem elas, uma
    # rota `external_official` não resolve -- e é assim que deve ser.
    return [{"kind": r.kind,
             "anchor": r.anchor,
             "href": resolve_route(r, domain=settings.site.domain,
                                   post_type=settings.site.post_type,
                                   authorized_external=authorized_external)}
            for r in page.routes]


def reachable_slugs(plan: FunnelPlan) -> set[str]:
    """BFS the `funnel`-kind edges of `page.routes` (the winning graph
    `build_funnel_routes` assigns) from every LP entry page. This is THE
    graph reachability walk -- `validate_funnel_graph` uses it to flag
    orphan pages, and `pipeline._pv_per_session` reuses it verbatim so the
    two can never disagree about what counts as "reachable" (T2H fix: pv/
    session used to walk `next_page_slug`, a separate chain that can drift
    from the actual routed funnel)."""
    pages = plan.pages
    if not pages:
        return set()
    slugs = {p.slug for p in pages}
    adj = {p.slug: [r.target for r in p.routes
                    if r.kind == "funnel" and r.target in slugs] for p in pages}
    reached: set[str] = set()
    stack = [p.slug for p in pages if effective_role(p) is PageRole.LP]
    while stack:
        s = stack.pop()
        if s in reached:
            continue
        reached.add(s)
        stack.extend(adj.get(s, []))
    return reached


def validate_funnel_graph(plan: FunnelPlan, settings: Settings) -> list[Issue]:
    issues: list[Issue] = []
    pages = plan.pages
    if not pages:
        return issues
    reached = reachable_slugs(plan)
    for p in pages:
        if p.slug not in reached:
            issues.append(Issue(code="unreachable_page",
                                message=f"Pagina '{p.slug}' nao alcancavel a partir da LP."))
    solutions = sorted((p for p in pages if effective_role(p) is PageRole.SOLUTION),
                       key=lambda p: p.ordinal)
    if solutions and not any(r.kind == "cross_funnel" for r in solutions[-1].routes):
        issues.append(Issue(
            code="terminal_no_exit",
            message=f"Pagina terminal '{solutions[-1].slug}' sem saida cross-funnel."))
    # NOTE: the old I9 checks (lead_not_distinct / lead_unresolved) were removed
    # with the angle subsystem (CARD-0009). Presell hubs no longer carry a
    # privileged lead field; neutral rotation by -prN index + fan-out
    # completeness are enforced by build_funnel_routes and contract_advisories.
    return issues
