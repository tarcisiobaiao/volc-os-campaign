from __future__ import annotations

import re

from funnelforge.config.settings import Settings
from funnelforge.domain.models import (
    FunnelPlan, Issue, Page, PageRole, Route, effective_role, resolve_route,
)
from funnelforge.pipeline.doctrine import APPROVED_CTA_EXEMPLARS
from funnelforge.pipeline.pagespec import _STOP, _sig_tokens, pagespec_for


def _placement(i: int, n: int) -> str:
    if i == 0:
        return "hero"
    if i == n - 1:
        return "footer"
    return "inline"


# Sufixo POSICIONAL do slug (`-pr`, `-pr2`, `-p3`): ele diz onde a página está
# no funil, não do que ela trata. Entrar na âncora só encompridaria o botão com
# uma informação que o leitor não usa.
_SUFIXO_POSICIONAL_RE = re.compile(r"^pr?\d*$")


def _termos_do_slug(slug: str) -> list[str]:
    """As palavras do slug, na ordem em que ele as escreve.

    O slug é legível por construção (`quem-tem-direito-pr` -> "quem tem
    direito"), então ele serve como FRASE, e não só como conjunto de tokens.
    """
    partes = [t for t in re.split(r"[^0-9a-zà-ü]+", slug.lower()) if t]
    return [t for t in partes if not _SUFIXO_POSICIONAL_RE.match(t) and not t.isdigit()]


def _token_do_h1(target_h1: str) -> str:
    """O termo do H1 que a âncora cita: o ÚLTIMO significativo.

    Manchete em português costuma terminar no substantivo do assunto ("Guia
    Completo do FGTS" -> `fgts`; "Saque-rescisão após demissão" -> `demissao`).
    A regra anterior pegava o PRIMEIRO em ordem alfabética — "completo",
    "aniversário" —, um critério sem nenhuma relação com o que a página trata.
    """
    tokens = [t for t in re.findall(r"[a-z0-9à-ü]{4,}", (target_h1 or "").lower())
              if t not in _STOP]
    return tokens[-1] if tokens else ""


def _anchor_for(target_h1: str, i: int, target_slug: str = "") -> str:
    """Âncora descritiva do destino — derivada do H1 E do CAMINHO dele.

    ⚠️ O TOKEN ERA O PRIMEIRO EM ORDEM ALFABÉTICA do H1, o que não tem relação
    nenhuma com o destino. Medido nos funis de teste deste repositório: o H1
    "Guia Completo do FGTS" produzia `Ver o guia de completo >>>` apontando para
    `/rec/quem-tem-direito-pr`, e "Como Sacar o FGTS Aniversário" produzia
    `Ver o guia de aniversário >>>` apontando para `/rec/como-sacar-p2`. As duas
    prometem um assunto que o caminho do destino não contém — que é literalmente
    o achado `ANCORA_INCONGRUENTE_COM_DESTINO` da política do destino pago.

    Duas réguas medem esta mesma âncora e elas olham lados diferentes: o
    `pagespec` do motor compara com o H1 do destino, e a política do destino
    pago compara com o CAMINHO da URL. Quando H1 e slug divergem — e divergem:
    "Guia Completo do FGTS" mora em `/rec/quem-tem-direito-pr` —, um token só não
    satisfaz as duas. Por isso:

      * com termo em comum, ele sozinho basta e é o mais LONGO (mais
        distintivo: "aniversario" diz mais que "fgts", que o funil inteiro
        compartilha);
      * sem termo em comum, a âncora nomeia os DOIS — a frase do caminho e, entre
        parênteses, o termo da manchete. É mais comprida, e é honesta: ela
        descreve para onde vai e o que o leitor vai encontrar lá.
    """
    base = APPROVED_CTA_EXEMPLARS[i % len(APPROVED_CTA_EXEMPLARS)]
    do_h1 = _sig_tokens(target_h1)
    termos_do_slug = _termos_do_slug(target_slug)
    do_slug = _sig_tokens(" ".join(termos_do_slug))
    comuns = do_h1 & do_slug
    if comuns:
        # `-len` primeiro e o token depois: desempate estável, nunca dependente
        # da ordem de iteração de um set.
        return f"Ver o guia de {sorted(comuns, key=lambda t: (-len(t), t))[0]} >>>"
    frase = " ".join(termos_do_slug)
    do_h1_token = _token_do_h1(target_h1)
    if frase and do_h1_token:
        return f"Ver o guia de {frase} ({do_h1_token}) >>>"
    if frase:
        return f"Ver o guia de {frase} >>>"
    if do_h1_token:
        return f"Ver o guia de {do_h1_token} >>>"
    return base


def _contextual_routes(plan: FunnelPlan, settings: Settings) -> bool:
    if not any(p.editorial is not None for p in plan.pages):
        return False
    by_slug = {p.slug: p for p in plan.pages}
    if len(by_slug) != len(plan.pages):
        raise ValueError("contextual plan has duplicate slugs")
    pending: dict[str, list[Route]] = {}
    for page in plan.pages:
        contract = page.editorial
        if contract is None:
            raise ValueError(f"missing editorial contract: {page.slug}")
        if not all(s.strip() for s in (
                contract.reader_question, contract.useful_delivery, contract.cta_label)):
            raise ValueError(f"empty editorial contract: {page.slug}")
        if effective_role(page) is PageRole.LP and not 1 <= len(contract.links) <= 3:
            raise ValueError("current LP template supports one to three destinations")
        routes: list[Route] = []
        targets: set[str] = set()
        for link in contract.links:
            target = by_slug.get(link.target)
            if (target is None or target.editorial is None or target is page
                    or link.target in targets or not link.reason.strip()):
                raise ValueError(f"invalid contextual link: {page.slug} -> {link.target}")
            # Funnel URLs currently resolve under the interior post type, not /r/.
            if effective_role(target) is PageRole.LP:
                raise ValueError("contextual links to LP require a typed LP URL resolver")
            targets.add(link.target)
            routes.append(Route(
                placement=_placement(len(routes), len(contract.links)), kind="funnel",
                target=target.slug, anchor=target.editorial.cta_label, reason=link.reason))
        for route in routes:
            resolve_route(route, domain=settings.site.domain, post_type=settings.site.post_type)
        pending[page.slug] = routes
    for page in plan.pages:
        page.routes = pending[page.slug]
    return True


def is_terminal_solution(page: Page, solutions: list[Page]) -> bool:
    """The terminal SOLUTION is the highest-`ordinal` page in the funnel: it
    stops advancing (no forward funnel edge); its exit follows the run policy.
    Same rule `validate_funnel_graph` uses for `terminal_no_exit`."""
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
    if _contextual_routes(plan, settings):
        return
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
                                target=t.slug, anchor=_anchor_for(t.h1_title, i, t.slug))
                          for i, t in enumerate(alvos)]
            else:
                routes = [Route(placement="hero", kind="funnel",
                                target=page.next_page_slug,
                            anchor=_anchor_for("", 0, page.next_page_slug))]
        elif role is PageRole.PRESELL:
            # FAN-OUT (NEUTRAL): the presell is a qualifier hub that opens EVERY
            # solution. Order is a NEUTRAL ROTATION keyed on the `-prN` index
            # (offset=(N-1)%n), NOT a privileged lead -- so no solution is
            # always first across the 3 hubs. Cap (I8) to spec.cta_max by
            # walking the SOLUTION ring from the offset; because different hubs
            # start at different offsets, every solution keeps an inbound edge
            # so reachability survives the cap regardless of how many solutions.
            if solutions:
                ordered = list(solutions)
                if len(ordered) > spec.cta_max:
                    ordered = ordered[:spec.cta_max]
                routes = [Route(placement=_placement(i, len(ordered)), kind="funnel",
                                target=s.slug, anchor=_anchor_for(s.h1_title, i, s.slug))
                          for i, s in enumerate(ordered)]
            else:
                routes = [Route(placement="hero", kind="funnel",
                                target=page.next_page_slug,
                            anchor=_anchor_for("", 0, page.next_page_slug))]
        else:  # SOLUTION
            if is_terminal_solution(page, solutions):
                # Official mode waits for research; legacy mode recirculates.
                if cross and settings.run.terminal_exit_policy == "cross_funnel":
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
                                anchor=_anchor_for(s.h1_title, i, s.slug))
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
                        role: PageRole, is_terminal: bool,
                        terminal_official: bool = False) -> None:
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
    if role is not PageRole.SOLUTION or (is_terminal and not terminal_official):
        return  # LP/PRESELL and legacy terminals never bind an official route.
    if is_terminal and terminal_official:
        # A resumed legacy plan must not retain its old cross-funnel exit.
        page.routes = [r for r in page.routes if r.kind != "cross_funnel"]
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
             "reason": r.reason,
             "href": resolve_route(r, domain=settings.site.domain,
                                   post_type=settings.site.post_type,
                                   authorized_external=authorized_external)}
            for r in page.routes]


def reachable_slugs(plan: FunnelPlan) -> set[str]:
    """BFS the `funnel`-kind edges of `page.routes` (the winning graph
    `build_funnel_routes` assigns) from every LP entry page. This is THE
    graph reachability walk -- `validate_funnel_graph` uses it to flag
    orphan pages; `pipeline._reachable_page_count` reports the same structural
    measure. Reachability is not observed pages per session."""
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


def validate_funnel_graph(plan: FunnelPlan, settings: Settings, *,
                          research_pending: bool = False) -> list[Issue]:
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
    exit_kind = ("external_official" if (any(p.editorial for p in pages)
                 or settings.run.terminal_exit_policy == "official")
                 else "cross_funnel")
    # Before research there is deliberately no guessed official URL.
    pending_official = research_pending and exit_kind == "external_official"
    if solutions and not pending_official and not any(
            r.kind == exit_kind for r in solutions[-1].routes):
        issues.append(Issue(
            code="terminal_no_exit",
            message=f"Pagina terminal '{solutions[-1].slug}' sem saida {exit_kind}."))
    # Destination priority belongs to the editorial contract, not hub rotation.
    return issues
