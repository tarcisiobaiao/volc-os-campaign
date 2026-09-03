# funnel-forge/src/funnelforge/pipeline/steps.py
from __future__ import annotations

import json
import re
import time
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError

from funnelforge.adapters import landing_policy_gate as lp_gate
from funnelforge.config.settings import ScreenshotConfig
from funnelforge.pipeline.admanifest import build_ad_manifest, vignette_meta
from funnelforge.pipeline.base_factual import base_para_o_redator
from funnelforge.pipeline.budget import preco_declarado_da_imagem
from funnelforge.pipeline.preflight import preflight_issues
from funnelforge.pipeline.retry_policy import classificar_issues
from funnelforge.pipeline.runner import LLMStepError
from funnelforge.domain.models import (
    EXISTENTIAL_CRITERIA,
    FunnelPlan,
    IndexDecision,
    Issue,
    Page,
    PageDraft,
    PageRole,
    ResearchFacts,
    Route,
    RunState,
    StepResult,
    StepStatus,
    Verdict,
    derive_role,
    effective_role,
    resolve_route,
)
from funnelforge.pipeline.doctrine import doctrine_context
from funnelforge.pipeline.engajamento import canon_engajamento
from funnelforge.pipeline.enhancers.gutenberg import (
    finalize_compliance_notice,
    formatar_moeda_em_estrutura,
    normalize_gutenberg,
)
from funnelforge.pipeline import canal_profundo
from funnelforge.pipeline.lp_template import load_lp_template, render_lp, validate_lp_content
from funnelforge.pipeline.pagespec import pagespec_for
from funnelforge.pipeline.phrase_registry import load_lines, record as record_phrase
from funnelforge.pipeline.routing import (
    bind_official_route,
    build_funnel_routes,
    is_terminal_solution,
    resolve_page_links,
    validate_funnel_graph,
)
from funnelforge.pipeline.taxonomy import contract_advisories
from funnelforge.pipeline.uniqueness import jaccard
from funnelforge.pipeline.validators.checks import (
    SIGNATURE_BLOCK_BY_ENGAGEMENT,
    VISUAL_BLOCKS_BY_ENGAGEMENT,
    host_matches_preference,
    presell_opening_line,
    run_validators,
    sanitize_widget_block,
    tolerant_json_object,
    url_host,
)
from funnelforge.prompts import render
from funnelforge.widgets import WidgetInvalido, chave_por_nome, ler, renderizar

# ---------------------------------------------------------------------------
# Tolerant JSON parsing (shared by extract / research / judge / seo steps).
# ---------------------------------------------------------------------------

def _tolerant_json(text: str) -> dict:
    """Parse a JSON object out of LLM output that may be fenced/decorated.

    A implementação vive em `validators.checks.tolerant_json_object` porque o
    validador `lp_json_contract` também precisa dela e NÃO pode importar deste
    módulo (steps importa checks; o contrário fecharia o ciclo). Aqui fica só a
    delegação, para não existir uma terceira cópia do mesmo parser.
    """
    return tolerant_json_object(text)


def _plan_from_raw(raw: dict) -> FunnelPlan:
    strategy = raw.get("funnel_strategy", {}) or {}
    pages = [Page(**p) for p in (raw.get("pages", []) or [])]
    return FunnelPlan(
        avatar_summary=strategy.get("avatar_summary", ""),
        tone_voice=strategy.get("tone_voice", ""),
        # The pages array is AUTHORITATIVE: total_pages always mirrors it, so a
        # miscounted funnel_strategy.total_pages (the extractor sometimes echoes
        # the "standard" 5 for a richer 6-page / 4-solution funnel) never drifts
        # from the real plan or the report.
        total_pages=len(pages),
        pages=pages,
    )


def parse_funnel_plan(json_text: str) -> FunnelPlan:
    """Tolerant parse of the `extractor` step's output into a FunnelPlan."""
    return _plan_from_raw(_tolerant_json(json_text))


def _word_count(text: str) -> int:
    stripped = re.sub(r"^===.*===$", "", text, flags=re.M)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    return len(stripped.split())


def _cta_link(page: Page) -> str:
    return f"/{page.next_page_slug}" if page.next_page_slug else ""


def _prompt_name_for(page: Page) -> str:
    """Select the redator prompt by the page's EFFECTIVE role (T1D), not its
    raw `page_type`: LP -> the calm P1 doctrine, PRESELL -> the bridge
    prompt, SOLUTION (and anything else) -> the calm interior-page prompt.
    Branching on role (not `page_type`) matches how routing/pagespec already
    decide funnel wiring, so a HUB-typed page whose slug derives PRESELL/
    SOLUTION still gets the matching prompt+links."""
    role = effective_role(page)
    if role is PageRole.LP:
        return "redator_p1"
    if role is PageRole.PRESELL:
        return "redator_presell"
    return "redator_pages"


_SOLUTION_ORDINAL_RE = re.compile(r"-p(\d+)$")


def assign_solution_ordinals(plan: FunnelPlan) -> None:
    """Set `page.role` explicitly (via `derive_role`) on EVERY page -- this
    guards against dedupe_slugs mutating a slug after role would otherwise be
    inferred lazily -- and populate `page.ordinal` for SOLUTION pages from the
    trailing `-pN` in their slug."""
    for page in plan.pages:
        page.role = derive_role(page.slug)
        if page.role is PageRole.SOLUTION:
            m = _SOLUTION_ORDINAL_RE.search(page.slug)
            if m:
                page.ordinal = int(m.group(1))


_PRESELL_SUFFIX_RE = re.compile(r"-pr\d*$")


# Neutral qualifier lenses fixed by hub index (1-based). DETERMINISTIC,
# LLM-free, resume-safe: each `-prN` hub opens the qualifier with a DIFFERENT
# neutral question and derives a materially-distinct h1 variant from its lens
# tag, so the 3 hubs are observably distinct by index WITHOUT any angle bias.
# Tuple entries are (opening_lens_question, h1_variant_tag).
_HUB_LENSES: tuple[tuple[str, str], ...] = (
    ("qual é a sua situação hoje?", "por onde começar"),
    ("o que você quer resolver primeiro?", "resolver o seu caso"),
    ("em que etapa você está?", "ir direto à sua etapa"),
)

_PRESELL_INDEX_RE = re.compile(r"-pr(\d+)$")


def _hub_index(slug: str) -> int:
    """1-based `-prN` index of a presell hub slug (defaults to 1 when the slug
    carries no numeric suffix -- e.g. the raw pre-expansion mapper slug)."""
    m = _PRESELL_INDEX_RE.search(slug)
    return int(m.group(1)) if m else 1


def _hub_lens(slug: str) -> tuple[str, str]:
    return _HUB_LENSES[(_hub_index(slug) - 1) % len(_HUB_LENSES)]


def _hub_h1_variant(base_h1: str, index: int) -> str:
    """A materially-distinct, NEUTRAL h1 for hub `index` (1-based), derived
    from that hub's qualifier lens tag -- never 3 identical H1s (anti-doorway),
    never an angle/pitch."""
    tag = _HUB_LENSES[(index - 1) % len(_HUB_LENSES)][1]
    base = (base_h1 or "").strip()
    return f"{base}: {tag}" if base else tag.capitalize()


def _qualifier_questions_for(page: Page, plan: FunnelPlan) -> list[dict[str, str]]:
    """Derive this hub's qualifier questions from the plan's SOLUTIONS, ordered
    to match the hub's rotated funnel routes (`page.routes`). Each solution's
    `emotional_objective` (or its h1) becomes a neutral 'caso -> caminho'
    criterion, so the qualifier block's SET/ORDER is distinct per hub index
    (lens + rotation) without reintroducing any per-angle bias."""
    by_slug = {p.slug: p for p in plan.pages
               if effective_role(p) is PageRole.SOLUTION}
    questions: list[dict[str, str]] = []
    for r in page.routes:
        if r.kind != "funnel":
            continue
        sol = by_slug.get(r.target)
        if sol is None:
            continue
        questions.append({"caso": (sol.emotional_objective or sol.h1_title),
                          "solucao": sol.h1_title})
    return questions


def expand_presell_hubs(state: RunState, deps: Any) -> None:
    """Mechanically expand the single mapped PRESELL into 3 NEUTRAL qualifier
    hubs (`-pr1/-pr2/-pr3`). Runs right after the FAITHFUL mapper
    `step_extract` and before dedupe/routing, replacing the removed creative
    angle-synthesis step (CARD-0009 / Opção A -- the presell must be a neutral
    rotating/qualifying hub, never an angle-biased pitch).

    DETERMINISTIC by construction: no LLM, no randomness. Each clone gets a
    fixed neutral qualifier LENS by index plus a materially-distinct h1 variant
    derived from that lens, so the step is fully resumable. The neutral fan-out
    ROTATION itself is applied later by `build_funnel_routes` (offset=(N-1)%n
    by the `-prN` index).

    Fail-closed: a funnel with fewer than 3 solutions raises `ValueError` (the
    honest multi-route hub graph is impossible). Ends by calling
    `assign_solution_ordinals` so ordinals/roles are populated on real data.

    HUB ÚNICO (`run.presell_hubs <= 1`, o padrão): NÃO clona nada. Normaliza o
    slug da única pré-sell mapeada para terminar em `-pr` e devolve o plano
    como veio. A expansão existia para dar 3 destinos à LP; com a LP mandando
    o primeiro botão ao hub e os demais direto às soluções, os clones perderam
    a função — e eram, por construção, três páginas com a MESMA
    `main_content_structure`. Neste modo bastam 2 soluções (uma para avançar,
    uma terminal), então a trava de >=3 só vale para o modo de 3 hubs."""
    plan = state.plan or FunnelPlan()
    solutions = [p for p in plan.pages if effective_role(p) is PageRole.SOLUTION]
    n_hubs = deps.settings.run.presell_hubs

    if n_hubs <= 1:
        if len(solutions) < 2:
            raise ValueError("funil precisa de >=2 soluções")
        for p in plan.pages:
            if effective_role(p) is PageRole.PRESELL:
                p.slug = _PRESELL_SUFFIX_RE.sub("", p.slug) + "-pr"
        for i, page in enumerate(plan.pages, start=1):
            page.page_number = i
        plan.total_pages = len(plan.pages)
        assign_solution_ordinals(plan)
        return

    if len(solutions) < 3:
        raise ValueError("funil precisa de >=3 soluções")

    presells = [p for p in plan.pages if effective_role(p) is PageRole.PRESELL]
    base_presell = presells[0] if presells else None
    if base_presell is not None:
        base_slug = _PRESELL_SUFFIX_RE.sub("", base_presell.slug)
        presell_type = base_presell.page_type
        base_h1 = base_presell.h1_title
        base_obj = base_presell.emotional_objective
        base_struct = list(base_presell.main_content_structure)
        base_kw = list(base_presell.target_keywords)
    else:
        base_slug = plan.pages[0].slug if plan.pages else ""
        presell_type = "HUB"
        base_h1 = plan.pages[0].h1_title if plan.pages else ""
        base_obj = ""
        base_struct = []
        base_kw = []

    new_presells = [
        Page(
            page_number=0,  # renumbered below
            page_type=presell_type,
            h1_title=_hub_h1_variant(base_h1, i),
            slug=f"{base_slug}-pr{i}",
            role=PageRole.PRESELL,
            emotional_objective=base_obj,
            main_content_structure=base_struct,
            target_keywords=base_kw,
        )
        for i in range(1, 4)
    ]
    # Rebuild the page list: LP first, then the 3 neutral hubs, then the
    # (unchanged) solutions and any other pages -- in their original order.
    lp_pages = [p for p in plan.pages if effective_role(p) is PageRole.LP]
    rest = [p for p in plan.pages
            if effective_role(p) not in (PageRole.LP, PageRole.PRESELL)]
    plan.pages = lp_pages + new_presells + rest
    for i, page in enumerate(plan.pages, start=1):
        page.page_number = i
    plan.total_pages = len(plan.pages)
    assign_solution_ordinals(plan)


def dedupe_slugs(plan: FunnelPlan | None) -> None:
    """De-collide duplicate slugs in-place: the 2nd+ occurrence of a slug
    gets a `-2`, `-3`, ... suffix. Reruns of the extractor step can echo the
    same slug for two pages; publishing both unmodified would create a
    duplicate-URL fingerprint (SCALED-CONTENT signal) and a WordPress
    slug collision."""
    if plan is None:
        return
    seen: dict[str, int] = {}
    for p in plan.pages:
        base = p.slug
        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            p.slug = f"{base}-{seen[base]}"


def index_decision_for(settings: Any, page: Page) -> IndexDecision:
    """Compute the `noindex,follow` + self-canonical decision for a page,
    from `settings.index[role]` (falls back to `noindex,follow` if the role
    has no explicit policy)."""
    pol = settings.index.get(effective_role(page).value)
    robots = pol.robots if pol is not None else "noindex,follow"
    canonical = f"{settings.site.domain}/{settings.site.post_type}/{page.slug}"
    return IndexDecision(robots=robots, canonical=canonical)


def uniqueness_state_guard(state: RunState, page: Page, deps: Any) -> None:
    """Funnel-level content-uniqueness state hook (T0E). Compares this
    page's draft against every other already-written draft in the same run
    via `pipeline.uniqueness.jaccard` (the SAME boilerplate-aware
    Jaccard/tokenizer the T1C `uniqueness` validator uses -- see below); if
    any pair meets/exceeds `settings.uniqueness.jaccard_threshold`, fails
    this page's `write_p{n}` step (fail-closed -- build/publish are gated on
    write status) so near-duplicate pages never ship as distinct URLs.

    NOTE: this is the run-time *state hook*, invoked per-page right after
    `step_write` inside `run_pipeline`. `pipeline/uniqueness.py`'s
    `uniqueness_guard(content, ctx)` is a separate, later static content
    validator run inside `run_validators`/`checks.py`, registered on the
    `write_page` step only (interior HUB/SOLUTION pages) -- `write_p1`
    (the Landing Page) never runs it. This state hook stays because it is
    the ONLY uniqueness guard that also covers the Landing Page draft; both
    now share `pipeline.uniqueness.jaccard` as their single algorithm so
    they can never disagree on an overlapping pair."""
    draft = state.drafts.get(page.page_number)
    if draft is None:
        return
    base = deps.settings.uniqueness.jaccard_threshold
    hub = deps.settings.uniqueness.hub_distinction_threshold
    plan = state.plan or FunnelPlan()
    role_by_num = {p.page_number: effective_role(p) for p in plan.pages}
    cur_is_hub = role_by_num.get(page.page_number, effective_role(page)) is PageRole.PRESELL
    for other_n, other in state.drafts.items():
        if other_n == page.page_number:
            continue
        # PRESELL-vs-PRESELL: neutral hubs legitimately share solution vocabulary
        # -> use the lenient hub threshold (see UniquenessConfig). Every other
        # pair (solution/LP) stays at the strict jaccard_threshold.
        threshold = hub if (cur_is_hub and role_by_num.get(other_n) is PageRole.PRESELL) else base
        if jaccard(draft.content, other.content) >= threshold:
            res = state.step_status.get(f"write_p{page.page_number}")
            if res is not None:
                res.status = StepStatus.FAILED
                res.issues = list(res.issues) + [Issue(
                    code="duplicate_content",
                    message=f"Conteúdo quase idêntico à página {other_n} (Jaccard>={threshold}).")]
            return


def _presell_opening_solution(content: str, solution_slugs: set[str]) -> str | None:
    """The SOLUTION whose slug appears FIRST in the draft (i.e. the solution
    that opens the hub's choice block), or None when none is present. Slugs are
    matched NOT-followed-by-a-digit so `a-p1` never matches inside `a-p12`."""
    best_slug, best_pos = None, len(content) + 1
    for slug in solution_slugs:
        m = re.search(re.escape(slug) + r"(?![0-9])", content)
        if m is not None and m.start() < best_pos:
            best_slug, best_pos = slug, m.start()
    return best_slug


def _fail_hub(state: RunState, page: Page, code: str, message: str) -> None:
    res = state.step_status.get(f"write_p{page.page_number}")
    if res is not None:
        res.status = StepStatus.FAILED
        res.issues = list(res.issues) + [Issue(code=code, message=message)]


def presell_hub_distinction_guard(state: RunState, page: Page, deps: Any) -> None:
    """Funnel-level STRUCTURAL-distinction state hook for the presell hubs
    (CARD-0009 / OVERRIDE-2). Invoked per-page right after `step_write` (next
    to `uniqueness_state_guard`); it compares this hub's draft against the
    other presell drafts already written in the SAME run and fails this page's
    `write_p{n}` step (fail-closed) when either:

      (1) two hubs are MATERIALLY IDENTICAL in their qualifier+preview body --
          the WHOLE draft is compared (not just the opening CTA line), so a hub
          that copies the substantive body but varies only line 1 is still
          caught; OR
      (2) the SAME solution opens the choice block of EVERY hub (hero not
          neutral) -- checked once all presell hubs have a draft.

    `uniqueness_state_guard` (whole-run duplicate content) and
    `opening_line_unique` (cross-run first line) stay active ON TOP of this;
    this guard adds the hub-specific hero-neutrality net that a per-page
    validator cannot see (the comparison is across the presell drafts of the
    same run) plus a clearer presell-scoped distinctness error."""
    if effective_role(page) is not PageRole.PRESELL:
        return
    current = state.drafts.get(page.page_number)
    if current is None:
        return
    plan = state.plan or FunnelPlan()
    presells = [p for p in plan.pages if effective_role(p) is PageRole.PRESELL]
    others = [(p, state.drafts.get(p.page_number)) for p in presells
              if p.page_number != page.page_number]
    others = [(p, d) for p, d in others if d is not None]
    if not others:
        return
    # Hub-vs-hub uses the LENIENT hub_distinction_threshold: the 3 neutral hubs
    # preview the SAME solutions, so they share that vocabulary by design -- only
    # a near-identical (copy-paste) hub is a real doorway. Hero-neutrality (2) is
    # the separate anti-bias net and is UNAFFECTED by this threshold.
    threshold = deps.settings.uniqueness.hub_distinction_threshold
    # (1) material equality of the qualifier+preview body between two hubs
    # (whole draft compared, so copying the body while varying only line 1 is
    # still caught -- "não apenas a 1ª linha").
    for other_page, other in others:
        if jaccard(current.content, other.content) >= threshold:
            _fail_hub(state, page, "hub_not_distinct",
                      f"Hub '{page.slug}' materialmente igual ao hub "
                      f"'{other_page.slug}' (bloco qualificador + previews).")
            return
    # (2) hero neutrality -- only once EVERY hub is written: fail if the same
    # solution opens the choice block of all of them.
    if len(others) + 1 == len(presells):
        solution_slugs = {p.slug for p in plan.pages
                          if effective_role(p) is PageRole.SOLUTION}
        openers = [_presell_opening_solution(d.content, solution_slugs)
                   for _, d in others]
        openers.append(_presell_opening_solution(current.content, solution_slugs))
        determinate = [o for o in openers if o]
        if len(determinate) == len(openers) and len(set(determinate)) == 1:
            _fail_hub(state, page, "hub_hero_not_neutral",
                      f"Todos os hubs abrem a escolha com a mesma solução "
                      f"'{determinate[0]}' (hero não neutro).")


# ---------------------------------------------------------------------------
# step_extract
# ---------------------------------------------------------------------------


def step_extract(state: RunState, deps: Any) -> None:
    """Extract the FunnelPlan from the briefing text via the `extract` step.

    No-op if `state.plan` is already populated (resume path).
    """
    if state.plan is not None:
        return
    prompt = render("extractor", briefing=state.briefing_text)
    cfg = deps.settings.steps["extract"]
    text, res = deps.runner.run_llm_step(
        "extract", cfg, [{"role": "user", "content": prompt}], ctx={},
        run_id=state.run_id,
    )
    try:
        raw = _tolerant_json(text)
        plan = _plan_from_raw(raw)
    except (ValueError, json.JSONDecodeError, ValidationError) as exc:
        res.status = StepStatus.FAILED
        res.issues = list(res.issues) + [Issue(code="parse_error", message=str(exc))]
        state.plan = FunnelPlan()
        state.step_status["extract"] = res
        return
    extra = run_validators(cfg.validators, text, {"parsed": raw})
    if extra:
        res.issues = list(res.issues) + extra
        res.status = StepStatus.FAILED
    state.plan = plan
    # Pull REAL cross-funnel exit URLs from the site sitemap (a diverse-but-
    # related guide for the terminal SOLUTION). None-safe + best-effort.
    cross_targets = None
    if getattr(deps, "sitemap", None) is not None:
        try:
            lp = next((p for p in plan.pages if effective_role(p) is PageRole.LP), None)
            # O TEMA, para o sitemap decidir o que é redundante, é o funil
            # inteiro — não três palavras do H1. As keywords de todas as
            # páginas já vieram do card pela ponte, e o perfil do run pode
            # acrescentar os apelidos da entidade.
            partes = [lp.h1_title if lp else (plan.pages[0].h1_title if plan.pages else "")]
            partes += [k for pg in plan.pages for k in pg.target_keywords]
            partes += list(getattr(deps, "tema_termos", None) or [])
            theme = " ".join(x for x in partes if x)
            cross_targets = deps.sitemap.cross_funnel_targets(
                theme=theme, exclude_slugs=[p.slug for p in plan.pages])
        except Exception:  # noqa: BLE001 - sitemap is best-effort, never fatal
            cross_targets = None
    try:
        build_funnel_routes(state.plan, deps.settings, cross_funnel_targets=cross_targets)
        graph_issues = validate_funnel_graph(state.plan, deps.settings)
    except ValueError as exc:
        graph_issues = [Issue(code="bare_rec", message=str(exc))]
    if graph_issues:
        state.step_status["funnel_graph"] = StepResult(
            step="funnel_graph", status=StepStatus.FAILED, issues=graph_issues)
    # Advisory (non-blocking): cross-check the built graph against the funnel
    # taxonomy contract (presell fan-out, terminal cross-funnel, no self-loop).
    advisories = contract_advisories(state.plan)
    if advisories:
        state.step_status["contract_advisory"] = StepResult(
            step="contract_advisory", status=StepStatus.OK,
            issues=[Issue(code="contract_advisory", message=m) for m in advisories])
    state.step_status["extract"] = res


# ---------------------------------------------------------------------------
# step_research
# ---------------------------------------------------------------------------


def _uma_pesquisa(state: RunState, page: Page, deps: Any, key: str,
                  fontes_reprovadas: list[str] | None = None
                  ) -> tuple[ResearchFacts, StepResult]:
    """UMA tentativa de pesquisa, já com o gate factual aplicado.

    Não decide nada sobre retentar — quem decide é `step_research`. Separado do
    laço justamente para que as duas rotas (provedor dedicado e fallback pelo
    LLM) sejam retentadas pela MESMA política.
    """
    structure = "\n".join(page.main_content_structure)
    if deps.research is not None:
        # A rota do provedor não passa pelo `Runner`, então o teto de custo tem
        # de ser conferido AQUI — senão a pesquisa seria a única despesa sem
        # freio do pipeline.
        orcamento = getattr(deps.runner, "budget", None)
        if orcamento is not None:
            orcamento.exigir_saldo(key)
        # O feedback só é passado quando o provedor sabe recebê-lo: um fake de
        # teste com assinatura antiga continua funcionando.
        try:
            facts = deps.research.research(topic=page.h1_title, structure=structure,
                                           fontes_reprovadas=fontes_reprovadas or [])
        except TypeError:
            facts = deps.research.research(topic=page.h1_title, structure=structure)
        # FIX 5 (smoke): research goes through `deps.research` (not
        # `run_llm_step`), so its cost/tokens used to show as 0 in
        # report.md. Copy the adapter's last-call telemetry (if it exposes
        # any -- `getattr` keeps this safe for any ResearchProvider
        # implementation that doesn't) into this step's StepResult.
        res = StepResult(
            step=key, status=StepStatus.OK, model_used="external-research", attempts=1,
            prompt_tokens=getattr(deps.research, "last_prompt_tokens", 0),
            completion_tokens=getattr(deps.research, "last_completion_tokens", 0),
            cost_usd=getattr(deps.research, "last_cost_usd", 0.0),
            latency_ms=getattr(deps.research, "last_latency_ms", 0),
        )
        if orcamento is not None:
            orcamento.registrar(key, res.cost_usd)
        _gate_research(facts, res, deps)
        return facts, res

    prompt = (
        "Pesquise e retorne SOMENTE um objeto JSON (UTF-8, sem markdown) com fatos "
        "verificáveis para o tema abaixo, no schema:\n"
        '{"resumo": "...", "dados_validados": [], "fatos_verificados": ['
        '{"valor":"...","unidade":"...","fonte_primaria":"https://...",'
        '"dispositivo":"... ou não se aplica","vigente_desde":"AAAA-MM-DD",'
        '"verificado_em":"AAAA-MM-DD"}], "passo_a_passo": [], "fontes": []}\n\n'
        f"Tema: {page.h1_title}\n"
        f"Estrutura: {structure}\n"
        f"Keywords: {', '.join(page.target_keywords)}\n\n"
        "URL EXATA (nunca o portal genérico): quando um passo acontece numa página "
        "oficial de serviço/consulta, retorne em 'fontes' a URL EXATA daquela página "
        "de serviço (ex.: a consulta de situação cadastral do CPF, não o gov.br/"
        "receitafederal genérico). PLATAFORMAS: para cada plataforma/app/fintech "
        "citada, inclua a URL EXATA do site oficial dela em 'fontes'."
    )
    cfg = deps.settings.steps["research"]
    text, res = deps.runner.run_llm_step(
        key, cfg, [{"role": "user", "content": prompt}], ctx={},
        run_id=state.run_id,
    )
    try:
        raw = _tolerant_json(text)
        facts = ResearchFacts(**raw)
    except (ValueError, json.JSONDecodeError, TypeError):
        facts = ResearchFacts(sparse=True)
    _gate_research(facts, res, deps)
    return facts, res


def step_research(state: RunState, page: Page, deps: Any) -> None:
    """Populate `state.facts[page.page_number]` -- agora COM retentativa.

    Se `deps.research` (um ResearchProvider dedicado) está configurado, chama
    direto; senão pede ao LLM primário um JSON de fatos best-effort, para que
    um dry run sem provedor ainda tenha alguma ancoragem.

    O QUE MUDOU (Frente 3): a pesquisa não tinha retentativa nenhuma. Um 429 do
    provedor virava `sparse=True`, o gate factual reprovava e a página morria —
    com o briefing e o extract já pagos e a redação nunca tentada. Agora são até
    `run.research_max_attempts` tentativas com espera exponencial
    (`run.research_backoff_s`, dobrando, limitada por `research_backoff_max_s`),
    e a telemetria de TODAS elas é somada no `research_p{n}` (tentativa que
    falhou também custou dinheiro e passa a aparecer no relatório).

    QUANDO DESISTIR: só retenta o que uma nova busca pode mudar — falta de
    fontes, contrato factual furado, fonte que não resolveu, erro transitório do
    provedor. `fact_source_verifier_missing` é terminal (é fiação: nenhuma
    pesquisa nova liga o Chromium), e um erro TERMINAL do provedor (401, janela
    de contexto, schema recusado) também para na hora — ver `retry_policy`.
    """
    key = f"research_p{page.page_number}"
    tentativas = max(1, int(getattr(deps.settings.run, "research_max_attempts", 3)))
    base = float(getattr(deps.settings.run, "research_backoff_s", 4.0))
    teto_espera = float(getattr(deps.settings.run, "research_backoff_max_s", 60.0))
    dormir = getattr(deps.runner, "sleep", time.sleep)

    # Acumulador: a conta do passo é a SOMA das tentativas, não a da última.
    acumulado = StepResult(step=key, status=StepStatus.FAILED, attempts=0)
    facts = ResearchFacts(sparse=True)

    # As URLs que a verificação ao vivo já reprovou. Alimentam a tentativa
    # seguinte — sem isto, cada retentativa refazia a MESMA busca com o MESMO
    # prompt e devolvia as MESMAS alucinações. Medido no primeiro run real:
    # 3 tentativas, US$ 0,3945, as três fontes idênticas nas três.
    reprovadas: list[str] = []
    # As URLs que reprovaram na tentativa ANTERIOR. Se a atual reprovar pelas
    # mesmas, a busca não trocou de fonte e retentar é gasto sem chance de
    # desfecho diferente — ver a checagem no fim do laço.
    fatais_anteriores: frozenset[str] = frozenset()

    for n in range(1, tentativas + 1):
        try:
            facts, res = _uma_pesquisa(state, page, deps, key, reprovadas)
            terminal_de_provedor = False
        except LLMStepError as exc:
            # O passo de LLM morreu, mas o que já foi pago vem junto na exceção.
            res = exc.step_result
            facts = ResearchFacts(sparse=True)
            terminal_de_provedor = exc.classe == "terminal"
            res.issues = list(res.issues) + [
                Issue(code="research_provider_error", message=str(exc))]

        acumulado.attempts = n
        acumulado.status = res.status
        acumulado.issues = list(res.issues)
        acumulado.model_used = res.model_used or acumulado.model_used
        acumulado.prompt_tokens += res.prompt_tokens
        acumulado.completion_tokens += res.completion_tokens
        acumulado.cost_usd += res.cost_usd
        acumulado.latency_ms += res.latency_ms

        # Colhe as URLs que não resolveram, para a próxima tentativa saber.
        # As BLOQUEADAS entram junto: elas não reprovam o passo, mas citar
        # outra fonte para o mesmo fato é melhor que citar uma que ninguém
        # consegue conferir.
        for issue in res.issues:
            if issue.code in ("fact_source_unreachable", "fact_source_unverifiable"):
                url = str(issue.message).rsplit(": ", 1)[-1].rstrip(".").strip()
                if url.startswith("http") and url not in reprovadas:
                    reprovadas.append(url)

        # ── TELEMETRIA POR TENTATIVA ──────────────────────────────────────
        #
        # O laço de retentativa mais caro do pipeline era o ÚNICO sem log: as
        # outras 18 etapas do run #6 aparecem em `log.jsonl` e `research_p*`
        # não aparece em nenhuma linha. Foi por isso que "quatro tentativas,
        # US$ 0,4556" nunca teve diagnóstico — não havia o que ler.
        registrar = getattr(deps.runner, "log", None)
        if callable(registrar):
            registrar(state.run_id, {
                "step": key, "attempt": n,
                "status": res.status.value if hasattr(res.status, "value") else str(res.status),
                "cost_usd": res.cost_usd, "latency_ms": res.latency_ms,
                "model": res.model_used,
                "n_issues": len(res.issues),
                "codes": sorted({i.code for i in res.issues}),
                "urls_reprovadas": list(reprovadas),
            })

        if res.status is not StepStatus.FAILED:
            break
        if terminal_de_provedor or not classificar_issues(res.issues, {}).retentar:
            break

        # ── NÃO RETENTAR O QUE NÃO PODE MUDAR ─────────────────────────────
        #
        # Se esta tentativa reprovou pelas MESMAS URLs da anterior, a busca não
        # trocou de fonte — e a próxima vai bater no mesmo verificador, no mesmo
        # site, com o mesmo resultado. Medido no run #6: quatro tentativas
        # contra `bancobmg.com.br`, US$ 0,4556, o mesmo veredito nas quatro.
        #
        # A comparação é do conjunto de URLs FATAIS, não das issues inteiras:
        # duas tentativas podem ter contagens diferentes de fato e ainda assim
        # esbarrarem exatamente na mesma fonte.
        fatais_agora = frozenset(
            str(i.message).rsplit(": ", 1)[-1].rstrip(".").strip()
            for i in res.issues if i.code == "fact_source_unreachable")
        if fatais_agora and fatais_agora == fatais_anteriores:
            acumulado.issues = list(acumulado.issues) + [Issue(
                code="research_retry_sem_efeito",
                message=(f"Tentativa {n} reprovou exatamente pelas mesmas fontes da "
                         f"anterior ({', '.join(sorted(fatais_agora))}). Parei aqui: "
                         f"repetir a busca com o mesmo prompt daria o mesmo veredito, "
                         f"e cada tentativa custa dinheiro."),
            )]
            break
        fatais_anteriores = fatais_agora

        if n < tentativas:
            dormir(min(base * (2 ** (n - 1)), teto_espera))

    state.facts[page.page_number] = facts
    state.step_status[key] = acumulado


def _gate_research(facts: ResearchFacts, res: StepResult, deps: Any) -> None:
    """Single fail-closed gate shared by provider and LLM fallback research."""
    validator_names = list(dict.fromkeys([
        *(getattr(deps.settings.steps.get("research"), "validators", []) or []),
        "has_sources",
        "research_facts_contract",
    ]))
    # ⚠️ FATO COM VIGÊNCIA NO FUTURO É PODADO, NÃO É SENTENÇA DE MORTE.
    #
    # `research_facts_contract` reprova `vigente_desde > hoje`, e com razão: uma
    # regra que ainda não entrou em vigor não sustenta afirmação no presente.
    # Mas a reprovação derrubava o PASSO, e com ele a página inteira — nem a
    # redação começava.
    #
    # Medido em 19/08/2026, run 9, p2: oito fatos verificados, UM com
    # `vigente_desde='2026-11-01'`. Os outros quatro da mesma fonte diziam
    # `2025-11-01` — um dígito trocado. Esse dígito custou a página inteira, e
    # foi a SEGUNDA morte da p2 (a primeira, `fact_source_not_listed`, tinha
    # outra causa).
    #
    # Podar é a resposta certa e já é a doutrina desta função: logo abaixo,
    # fonte que não pôde ser verificada tira o fato de `fontes_resolvidas` e a
    # página sobrevive. O que não pode chegar ao texto é a cifra do fato ruim —
    # e podá-lo aqui garante isso melhor do que matar a página garantia.
    hoje = date.today()
    futuros = [f for f in (facts.fatos_verificados or [])
               if isinstance(getattr(f, "vigente_desde", None), date)
               and f.vigente_desde > hoje]
    if futuros:
        facts.fatos_verificados = [f for f in (facts.fatos_verificados or [])
                                   if f not in futuros]
        # Podou TUDO: a pesquisa rodou e não sobrou fato utilizável. `sparse` é
        # o estado que o motor já usa para isso, e dizê-lo aqui é o que faz o
        # redator escrever de forma qualitativa em vez de achar que tem base.
        # Não é reprovação: quem impede número sem lastro é o
        # `critical_fact_grounding` no gate final, e ele continua de pé.
        if not facts.fatos_verificados:
            facts.sparse = True
        for f in futuros:
            # AVISO, não reprovação: aparece no relatório e alimenta o feedback
            # da retentativa, mas não entra em `extra`, que é o que derruba.
            res.issues = list(res.issues) + [Issue(
                code="fato_vigencia_futura_podado",
                message=(f"Fato descartado: vigência em {f.vigente_desde} ainda não "
                         f"começou (hoje é {hoje}). Fonte: {f.fonte_primaria}. A "
                         f"página segue com os demais fatos; nenhuma cifra deste "
                         f"pode ser publicada."),
            )]

    extra = run_validators(validator_names, "", {
        "parsed": facts,
        "today": hoje,
        "max_age_days": getattr(deps.settings.run, "research_max_age_days", 45),
    })

    # Fato publicável precisa de fonte que RESPONDE ao vivo. Quem responde isso
    # é o port `UrlVerifier` (`deps.url_verifier`), sempre ligado -- não mais o
    # provider de screenshot. Antes isto era
    # `getattr(deps.screenshot, "verify_url")`: um método fora de qualquer
    # Protocol, num provider que só existe quando `run.official_screenshots`
    # está ON. Desligar os prints -- flag que se anuncia cosmética -- reprovava
    # TODA página com fato numérico. Fontes qualitativas seguem passando só
    # pelo gate de URL/schema.
    #
    # O `getattr` abaixo é no BUNDLE, não no provider: `deps` aqui é tipado
    # `Any` e há chamadores com um deps duck-typed. O que importa é que o
    # MÉTODO chamado (`verify_url`) está declarado no Protocol `UrlVerifier` --
    # nada mais é descoberto por reflexão.
    strict_sources = list(dict.fromkeys(
        fact.fonte_primaria for fact in (facts.fatos_verificados or [])))
    if strict_sources:
        verifier = getattr(deps, "url_verifier", None)
        if verifier is None:
            extra.append(Issue(
                code="fact_source_verifier_missing",
                message="Há fatos críticos, mas nenhum verificador ao vivo de fonte foi ligado.",
            ))
        else:
            resolved: list[str] = []
            # ⚠️ DUAS CLASSES DE FALHA, E SÓ UMA MATA A PÁGINA.
            #
            # Antes, qualquer fonte que não resolvesse virava
            # `fact_source_unreachable` e reprovava a pesquisa inteira. Medido no
            # run #6: a página 4 morreu porque `bancobmg.com.br` — um banco de
            # verdade — responde 403 a qualquer User-Agent declarado. É um WAF,
            # não uma URL morta. A página tinha outros fatos com fonte boa e foi
            # perdida junto, depois de quatro tentativas contra o mesmo bloqueio.
            #
            # Agora:
            #   RECUSADA (404, não-https, HTML de erro) -> a URL não serve.
            #     Continua fatal e continua retentável: uma busca nova pode
            #     achar outra fonte.
            #   BLOQUEADA (403/429/timeout) -> não deu para saber. O fato sai de
            #     `fontes_resolvidas`, então nenhuma cifra dele chega ao texto
            #     (`base_factual` poda o que o gate reprovaria) — mas a PÁGINA
            #     sobrevive e é escrita com o que restou.
            #
            # A rigidez que se mantém é a que importa: número publicado continua
            # exigindo fonte que respondeu ao vivo. O que se afrouxa é a
            # consequência de não conseguir checar — que virava perda de página.
            bloqueadas: list[str] = []
            for source in strict_sources:
                try:
                    ok = bool(verifier.verify_url(source))
                except Exception:  # noqa: BLE001 - resolution failure is a gate result
                    ok = False
                if ok:
                    resolved.append(source)
                    continue
                pergunta = getattr(verifier, "bloqueada", None)
                if callable(pergunta) and pergunta(source):
                    bloqueadas.append(source)
                    continue
                extra.append(Issue(
                    code="fact_source_unreachable",
                    message=f"Fonte primária não resolveu no verificador: {source}",
                ))
            facts.fontes_resolvidas = resolved
            for source in bloqueadas:
                porque = ""
                ler = getattr(verifier, "motivo", None)
                if callable(ler):
                    porque = ler(source) or ""
                # AVISO, não reprovação: entra em `res.issues` para aparecer no
                # relatório e alimentar o feedback da retentativa, mas NÃO entra
                # em `extra`, que é o que derruba o passo.
                res.issues = list(res.issues) + [Issue(
                    code="fact_source_unverifiable",
                    message=(f"Fonte não pôde ser verificada ({porque or 'bloqueio'}): "
                             f"{source}. O fato foi mantido na pesquisa, mas nenhuma "
                             f"cifra dele pode ser publicada."),
                )]
    if extra:
        res.issues = list(res.issues) + extra
        res.status = StepStatus.FAILED


# ---------------------------------------------------------------------------
# step_write (+ judge)
# ---------------------------------------------------------------------------


def _existential_criteria_for(role: PageRole) -> tuple[str, ...]:
    """Role-aware existential-criteria set for the judge's fail-closed gate.

    A SOLUTION page's multi-destination routing (sibling solutions + 1
    external_official link + 1 cross_funnel exit, same domain) is the
    WINNING routing graph by design and is already validated
    deterministically by `pagespec`/`run_validators` at write time (see
    `_write_ctx` -> ctx["pagespec"], enforced via the `pagespec` validator
    on `write_page`). The judge's `single_destination` rubric is an
    LP/HUB-only rule (see judge.jinja criterion 6); it must not be allowed
    to double-gate routing that pagespec already passed. So for SOLUTION,
    `single_destination` is EXCLUDED from the criteria that can flip
    `blocked` for SOLUTION -- compliance/cta_discipline still gate every
    role, and `verdict.blocking` is still honored for every role via the
    `or` below. (proof_and_authority was demoted OUT of EXISTENTIAL_CRITERIA
    entirely -- "cirurgico"/trust-Gemini decision -- so weak proof is
    advisory, never a gate, for every role.) LANDING PAGE and PRESELL/HUB
    keep the full non-proof existential set."""
    if role in (PageRole.SOLUTION, PageRole.PRESELL):
        # SOLUTION (mesh + exits) and PRESELL (fan-out to the 3 solutions) are
        # BOTH correctly multi-destination -- single_destination is an LP-only
        # existential rule (pagespec already validates their routing).
        return tuple(c for c in EXISTENTIAL_CRITERIA if c != "single_destination")
    return EXISTENTIAL_CRITERIA


def _judge_page(state: RunState, page: Page, content: str, deps: Any) -> None:
    """Run the `judge` step. MUST pass page_type so the LANDING-PAGE-only
    1st-person-CTA rule in the judge prompt applies correctly (an undefined
    page_type disables that rule, per Task 11)."""
    facts = state.facts.get(page.page_number, ResearchFacts(sparse=True))
    prompt = render(
        "judge",
        content=content,
        page_type=page.page_type,
        domain=deps.settings.site.domain,
        cta_link=_cta_link(page),
        keywords=", ".join(page.target_keywords),
        facts=base_para_o_redator(facts),
        **doctrine_context(),
    )
    cfg = deps.settings.steps["judge"]
    text, res = deps.runner.run_llm_step(
        f"judge_p{page.page_number}", cfg, [{"role": "user", "content": prompt}], ctx={},
        run_id=state.run_id,
    )
    try:
        verdict = Verdict(**_tolerant_json(text))
    except (ValueError, json.JSONDecodeError, TypeError):
        verdict = Verdict(approved=False, blocking=True,
                          feedback=["judge output could not be parsed"])
    if not verdict.approved:
        res.issues = list(res.issues) + [
            Issue(code="judge_rejected", message=fb) for fb in verdict.feedback if fb]
    # Fail-closed gate (Task 8/T0C, role-aware per T1E): don't trust the
    # LLM's self-reported `blocking` flag alone -- a valid verdict can omit
    # it (pydantic default False) or set it inconsistently with its own
    # scores. Cross-check every role-appropriate existential criterion score
    # against the pass bar; a missing score counts as 0 (fail-closed
    # default) rather than being silently ignored.
    criteria = _existential_criteria_for(effective_role(page))
    blocked = verdict.blocking or any(
        verdict.scores.get(criterion, 0) < 7 for criterion in criteria)
    if blocked:
        res.status = StepStatus.FAILED
        res.issues = list(res.issues) + [
            Issue(code="judge_blocking",
                  message="Veredito bloqueante: critério existencial reprovado.")]
    state.step_status[f"judge_p{page.page_number}"] = res


def candidatas_da_pesquisa(facts: ResearchFacts) -> list[str]:
    """As URLs que a PESQUISA desta página devolveu, da evidência mais forte
    para a mais fraca: fonte primária de fato verificado que RESOLVEU no
    verificador, depois as demais `fontes`, depois as fontes de
    `dados_validados`. Deduplicado, ordem preservada."""
    resolvidas = set(facts.fontes_resolvidas or [])
    ordem: list[str] = [f.fonte_primaria for f in (facts.fatos_verificados or [])
                        if f.fonte_primaria in resolvidas]
    ordem += list(facts.fontes or [])
    ordem += [dv.get("fonte", "") for dv in (facts.dados_validados or [])
              if isinstance(dv, dict)]
    vistas: set[str] = set()
    saida: list[str] = []
    for bruto in ordem:
        url = (bruto or "").strip()
        if url and url not in vistas:
            vistas.add(url)
            saida.append(url)
    return saida


def _confirmada_ao_vivo(verify: Any, url: str) -> bool:
    """O Chromium viu uma página viva e válida? Erro conta como NÃO
    (fail-closed): link que não dá para confirmar não é publicado."""
    try:
        return bool(verify(url))
    except Exception:  # noqa: BLE001 - verificação é gate; falhar = reprovar
        return False


def _vive_de_anuncio(ad_probe: Any, url: str) -> bool:
    """A página de destino se sustenta em anúncio display?

    Se sim, ela não é canal oficial: é um portal que disputa a MESMA sessão que
    você acabou de comprar no Google Ads -- exatamente os 3 links para portal
    concorrente que o inventário do funil antigo encontrou. Este é o
    discriminador que substitui a allowlist sem virar outra lista: canal oficial
    (gov.br, cadastro do iFood, Serasa) não monetiza a sua sessão com display,
    portal concorrente monetiza.

    `None` (não sei) e qualquer erro NÃO reprovam: a sonda é camada extra, e um
    falso positivo dela não pode derrubar a única URL oficial da página.
    """
    try:
        return ad_probe(url) is True
    except Exception:  # noqa: BLE001 - sonda é best-effort, nunca fatal
        return False


def build_official_links(
    facts: ResearchFacts, site: Any, *,
    verify: Any = None, ad_probe: Any = None, cap: int = 4,
) -> list[str]:
    """As URLs externas que ESTA página pode usar. A autorização é a PESQUISA.

    Não existe mais allowlist de domínio. A lista antiga
    ([gov.br, caixa.gov.br]) só servia ao funil de FGTS: num funil de entregador
    do iFood o canal oficial É o cadastro do iFood, num de Serasa Limpa Nome é o
    Serasa -- e a lista transformava isso em reprovação silenciosa (zero deep
    link oficial, CTA do grafo apontando para gov.br, print recusado).

    O que autoriza, em três camadas:

    1. PROVENIÊNCIA (sempre): só entra URL que a busca desta página devolveu.
       É o que impede o redator de inventar `emprestimo-aprovado-rapido.com`.
    2. VERIFICAÇÃO AO VIVO (quando há browser): o Chromium precisa ter visto uma
       página válida. Fail-closed -- URL que não confirma não entra.
    3. ANTI-CONCORRENTE (quando há sonda): destino que vive de anúncio display
       não é canal oficial, é quem rouba o clique comprado.

    `site.official_preference` só ORDENA (o `official_source` da entidade sobe o
    canal dela na fila); `site.blocked_hosts` é denylist opcional. Nenhum dos
    dois autoriza coisa alguma -- sem evidência, a lista sai vazia e a página
    falha fechada no gate de densidade, por ausência de prova.

    SEM browser (dry run / playwright ausente) valem só a camada 1 e a denylist:
    é modo DEGRADADO, consciente, igual ao que o motor já fazia.
    """
    site_host = urlparse(getattr(site, "domain", "") or "").netloc.lower()
    preferencias = list(getattr(site, "official_preference", []) or [])
    bloqueados = {(url_host(h) or h.lower()).removeprefix("www.")
                  for h in (getattr(site, "blocked_hosts", []) or []) if h}
    aprovadas: list[tuple[bool, str]] = []
    for url in candidatas_da_pesquisa(facts):
        if not url.startswith("https://"):
            continue                       # canal oficial é sempre https
        host = url_host(url)
        if not host or "." not in host:
            continue                       # sem TLD não é destino de verdade
        if site_host and (host == site_host or host.endswith("." + site_host)):
            continue                       # recirculação própria, não é externo
        if any(host == b or host.endswith("." + b) for b in bloqueados):
            continue                       # denylist explícita do operador
        if verify is not None and not _confirmada_ao_vivo(verify, url):
            continue                       # fail-closed: página não confirmada
        if ad_probe is not None and _vive_de_anuncio(ad_probe, url):
            continue                       # portal de anúncio = concorrente
        aprovadas.append((host_matches_preference(host, preferencias), url))
    ordenadas = ([u for pref, u in aprovadas if pref]
                 + [u for pref, u in aprovadas if not pref])
    return ordenadas[:cap]


def build_platform_links(
    facts: ResearchFacts, official_links: list[str], site_domain: str,
    *, verify: Any = None, cap: int = 4,
) -> list[dict]:
    """Deep links COMERCIAIS de plataforma/serviço de uma página SOLUTION
    (FIX-3c): as `fontes` + `dados_validados[].fonte` da pesquisa cujo host não
    é o do próprio site nem o de um canal já escolhido como OFICIAL -- as
    fintechs/serviços que o passo a passo nomeia (Jeitto, SuperSim, Velotax...).
    Deduplicado por host, limitado a `cap`.

    Antes a separação "oficial x plataforma" era feita pela allowlist; agora é
    feita por `official_links`, que é a escolha desta página. Sem lista: um
    funil de iFood tem o cadastro do iFood como oficial e as demais plataformas
    como comerciais, sem ninguém cadastrar domínio antes.

    Com `verify` (checagem `url -> bool` no Chromium), o candidato só fica se
    confirmar como página viva -- fail-CLOSED. Sem verificador NADA é emitido.
    Devolve `[{"url", "host"}]`."""
    site_host = urlparse(site_domain).netloc.lower()
    hosts_oficiais = {url_host(u) for u in (official_links or [])}
    hosts_oficiais.discard("")
    sources = list(facts.fontes or [])
    sources += [dv.get("fonte", "") for dv in (facts.dados_validados or [])
                if isinstance(dv, dict)]
    out: list[dict] = []
    seen: set[str] = set()
    for src in sources:
        url = (src or "").strip()
        if not url:
            continue
        host = urlparse(url if "://" in url else "http://" + url).netloc.lower()
        if not host or host in seen:
            continue
        if any(host == o or host.endswith("." + o) for o in hosts_oficiais):
            continue  # já é canal oficial desta página -- build_official_links cuida
        if host == site_host or (site_host and host.endswith("." + site_host)):
            continue  # the site's own recirculation, never a "platform" link
        if verify is None or not verify(url):
            continue  # fail-closed: only chromium-confirmed live pages get linked
        seen.add(host)
        out.append({"url": url, "host": host})
        if len(out) >= cap:
            break
    return out


def _verificadores(deps: Any) -> tuple[Any, Any]:
    """(verify_url, is_ad_monetized) — de DUAS fontes diferentes, de propósito.

    "Essa URL existe?" é pergunta de HTTP, e virou o port `UrlVerifier`: sempre
    ligado, com cache por run, sem browser. Era isto que estava errado antes —
    a verificação morava no provider de screenshot, então desligar
    `official_screenshots` (uma flag de IMAGEM, anunciada como cosmética e
    best-effort) fazia toda página com fato numérico reprovar na pesquisa. A
    flag volta a ser cosmética.

    A sonda anti-anúncio continua no provider de browser porque ela precisa de
    DOM e de rede para decidir se a página é um portal de anúncio. Ela é
    OPCIONAL: sem Playwright vem None e a camada 3 simplesmente não roda.

    Duck-typing nos dois: um fake de teste não precisa ter os dois métodos."""
    verificador = getattr(deps, "url_verifier", None)
    verify = getattr(verificador, "verify_url", None)
    sonda = getattr(getattr(deps, "screenshot", None), "is_ad_monetized", None)
    return (verify if callable(verify) else None,
            sonda if callable(sonda) else None)


def registrar_canais_oficiais(state: RunState, page: Page, deps: Any) -> None:
    """Decide, UMA VEZ por página e logo depois da pesquisa, quais URLs externas
    aquela página pode usar -- e guarda em `state.official_links`.

    Por que aqui e não no redator: a escolha do canal é um FATO DA PESQUISA
    (precisa de browser para confirmar que a página existe e que não é um portal
    de anúncio), e browser é caro -- `_write_ctx` roda duas vezes por página e o
    screenshot uma terceira. Guardando no RunState, prompt, gate final e print
    falam do MESMO canal e o Chromium abre uma vez só; o checkpoint carrega a
    decisão para o resume.

    Best-effort: qualquer falha deixa a lista vazia (a página é reprovada depois
    pelo gate de densidade) e NUNCA derruba a etapa de pesquisa."""
    if effective_role(page) is not PageRole.SOLUTION:
        return
    facts = state.facts.get(page.page_number)
    if facts is None:
        return
    verify, ad_probe = _verificadores(deps)
    try:
        escolhidos = build_official_links(
            facts, deps.settings.site, verify=verify, ad_probe=ad_probe)
    except Exception:  # noqa: BLE001 - escolha de canal nunca derruba a pesquisa
        state.official_links[page.page_number] = []
        return

    # ── DOMÍNIO-RAIZ NÃO É CANAL, É MARCA ─────────────────────────────────
    #
    # Medido em 19/08/2026 no funil FGTS publicado: 22 de 23 links externos
    # eram raiz. "página de download na Google Play Store" levava a
    # `play.google.com`; "tabela de limites da Caixa" levava a `caixa.gov.br`.
    # O leitor caía na home e tinha de procurar sozinho — o trabalho que o
    # artigo prometeu poupar.
    #
    # A causa era a PESQUISA: nas três páginas de solução, `fonte_primaria` e
    # `fontes` só tinham raízes. E o prompt da pesquisa já pedia o contrário,
    # com todas as letras e com exemplo ("URL EXATA (nunca o portal
    # generico)") — o modelo ignorou nas três. Instrução não sustenta
    # invariante; por isso a descoberta agora é mecânica.
    termos = canal_profundo.termos_uteis(
        page.h1_title, " ".join(page.main_content_structure or []),
        " ".join(getattr(page, "target_keywords", []) or []))
    state.official_links[page.page_number] = [
        canal_profundo.aprofundar(u, termos, verificar=verify) if canal_profundo.e_raiz(u)
        else u
        for u in escolhidos
    ]


def _phrase_registry_path(deps: Any) -> Path:
    """Cross-run registry file location (CARD-0007): directly under
    `runs_dir`, NOT a per-run subfolder, so every funnel run reads/appends
    the SAME file -- see `phrase_registry` module docstring for why this
    needs to survive past a single run."""
    return deps.runner.runs_dir / "_phrase_registry.json"


def research_hosts(facts: ResearchFacts) -> list[str]:
    """Os hosts que a PESQUISA desta página trouxe — a autorização de link
    externo, no lugar de qualquer allowlist estática.

    O princípio: **o que a busca devolveu é autorizado; o que ela não devolveu
    não existe.** Uma página sobre milhas no PicPay cita `picpay.com` porque a
    pesquisa achou, uma sobre entregador Shopee cita `shopee.com.br` pelo mesmo
    motivo, e ninguém precisa prever esses domínios um a um.

    O que isso NÃO afrouxa: o modelo continua sem poder inventar URL. Um host
    que a busca não trouxe é recusado — que é a única trava que realmente
    protege, porque é assim que uma página sobre crédito acabaria linkando um
    domínio de golpe com a sua assinatura embaixo.
    """
    fontes = list(facts.fontes or [])
    fontes += [dv.get("fonte", "") for dv in (facts.dados_validados or [])
               if isinstance(dv, dict)]
    hosts: dict[str, None] = {}
    for src in fontes:
        url = (src or "").strip()
        if not url:
            continue
        host = urlparse(url if "://" in url else "http://" + url).netloc.lower()
        if host:
            hosts[host.removeprefix("www.")] = None
    return list(hosts)


def _write_ctx(state: RunState, page: Page, deps: Any) -> dict:
    """Validator ctx for `step_write`: same-domain/identity fields (T0B/T0D)
    plus the T1A pagespec + h1_by_slug the `pagespec` validator needs to
    enforce the winning funnel graph (`page.routes`, populated by
    `build_funnel_routes` in `step_extract`) against `settings.routing`."""
    plan = state.plan or FunnelPlan()
    role = effective_role(page)
    facts = state.facts.get(page.page_number, ResearchFacts(sparse=True))
    # Forward-only routing context (Task 8): `solution_order` maps every
    # SOLUTION slug to its ordinal, and `is_terminal` marks the last solution
    # (highest ordinal) -- both feed the forward_only validator and the
    # interior writer so a mid page only advances and the terminal recirculates.
    solutions = [p for p in plan.pages if effective_role(p) is PageRole.SOLUTION]
    solution_order = {p.slug: p.ordinal for p in solutions}
    is_terminal = is_terminal_solution(page, solutions) if role is PageRole.SOLUTION else False
    try:
        prior_opening_lines = load_lines(_phrase_registry_path(deps), "presell_opening")
    except Exception:  # noqa: BLE001 - registry is best-effort, must never block a write
        prior_opening_lines = []
    # OS CANAIS EXTERNOS DESTA PÁGINA (a autorização, e ela é POR PÁGINA).
    # `state.official_links` é a escolha feita logo depois da pesquisa, com
    # browser (ver registrar_canais_oficiais). O fallback recalcula OFFLINE --
    # só proveniência, sem confirmação ao vivo -- para estado montado à mão em
    # teste ou checkpoint antigo: é modo degradado, não o caminho normal.
    #
    # ⚠️ A CHAVE, NÃO O VALOR. `[]` aqui tem DOIS significados e confundi-los
    # reabre o buraco que esta frente veio fechar:
    #   chave AUSENTE  -> ninguém decidiu ainda (checkpoint antigo, estado
    #                     montado à mão em teste) -> o fallback offline é o certo
    #   chave PRESENTE
    #   com lista []   -> o browser RODOU e REPROVOU todos os candidatos
    #                     (URL morta, ou portal de anúncio pego pela sonda)
    #
    # Testar `or []` trata os dois igual e recalcula por proveniência pura,
    # ressuscitando exatamente a URL que a verificação ao vivo acabou de
    # rejeitar — ela volta ao prompt do redator, vira alvo do CTA oficial, entra
    # no conjunto autorizado e ainda gera o print embutido no artigo. Era assim
    # que um portal concorrente levava o clique comprado embora.
    if page.page_number in state.official_links:
        official_links = list(state.official_links[page.page_number])
    else:
        official_links = build_official_links(facts, deps.settings.site)
    # A aresta `external_official` do grafo nasce AQUI, tarde, já com a URL que
    # a pesquisa trouxe -- efeito colateral deliberado, porque o `pagespec`
    # montado logo abaixo precisa enxergar a rota final. Idempotente: chamar de
    # novo no gate de conteúdo recoloca exatamente a MESMA rota.
    bind_official_route(page, official_links, role=role, is_terminal=is_terminal)
    # FIX-3c: commercial PLATFORM deep links for SOLUTION pages -- the fintechs/
    # services the path names, from the research, each confirmed LIVE by a
    # chromium visit (fail-closed). Feeds the writer prompt AND same_domain
    # (verified_platforms whitelists exactly these hosts for THIS page). Skipped
    # unless a screenshot/verify provider is wired -- then platform_links stays
    # empty and the page renders exactly as before.
    platform_links: list[dict] = []
    verifier, _ = _verificadores(deps)
    if role is PageRole.SOLUTION and verifier is not None:
        try:
            platform_links = build_platform_links(
                facts, official_links, deps.settings.site.domain, verify=verifier)
        except Exception:  # noqa: BLE001 - platform links are best-effort, never block
            platform_links = []
    verified_platforms = [p["host"] for p in platform_links]
    # Só SOLUTION carrega forma de pergunta: LP e PRESELL não têm contrato
    # visual nem widget, e inventar rótulo para elas mudaria o prompt à toa.
    engajamento = engajamento_declarado(page) if role is PageRole.SOLUTION else ""
    return {
        "parsed": {"role": role.value, "slug": page.slug,
                   "next_page_slug": page.next_page_slug,
                   "routes": [r.model_dump() for r in page.routes]},
        "role": role,
        "domain": deps.settings.site.domain,
        "post_type": deps.settings.site.post_type,
        # A AUTORIZAÇÃO DE LINK EXTERNO: os hosts que a PESQUISA desta página
        # trouxe. É o que substitui a allowlist estática -- uma página sobre
        # milhas no PicPay cita `picpay.com` porque a busca devolveu, não
        # porque alguém cadastrou o domínio antes. Ver `same_domain`.
        "research_hosts": research_hosts(facts),
        "slug": page.slug,
        "cnpj": deps.settings.site.cnpj,
        # OS CAMPOS DO PLANO — o que a página promete ANTES de ter corpo.
        # `plano_de_destino_pago` (validador e pré-voo) lê daqui: a alegação que
        # derrubou a conta entrou pelo H1 do plano, e um ctx que só carrega o
        # corpo não tem como reprovar o que não está no corpo.
        "h1": page.h1_title,
        "page_type": page.page_type,
        "subtitulos": list(page.main_content_structure),
        "lp_post_type": deps.settings.site.lp_post_type,
        # A identidade/divulgação que o TEMA renderiza. Declaração, não
        # observação — ver `SiteConfig.rodape_institucional`.
        "rodape_institucional": deps.settings.site.rodape_institucional,
        "facts": facts,
        # O rótulo DECLARADO, canonizado e com a escala binária já traduzida
        # (ver `engajamento_declarado`). Passar `page.engajamento` cru era o que
        # fazia `visual_contract` desligar em silêncio diante de `sustenta` ou
        # de um acento.
        "engajamento": engajamento,
        "visual_required_blocks": list(
            VISUAL_BLOCKS_BY_ENGAGEMENT.get(engajamento, ())),
        "ad_paragraph_anchors": deps.settings.ads.paragraph_anchors,
        "pagespec": pagespec_for(deps.settings, role, terminal=is_terminal).model_dump(),
        "solution_order": solution_order,
        "is_terminal": is_terminal,
        "h1_by_slug": {p.slug: p.h1_title for p in plan.pages},
        # CARD-0011 REQ-2: H1 of ALL solutions of the funnel, so
        # `cta_destination_congruent` can compute each destination's DISTINCTIVE
        # token by subtracting the sibling solutions' tokens (kills the false
        # pass by the shared funnel-theme token, e.g. "FGTS").
        "sibling_h1s": {p.slug: p.h1_title for p in solutions},
        "prior_drafts": [d.content for n, d in state.drafts.items()
                         if n != page.page_number],
        # The `uniqueness` validator compares this draft to every prior draft at
        # this threshold. A PRESELL only realistically collides with the OTHER
        # neutral hubs (they preview the SAME solutions -> shared vocabulary by
        # design), so it gets the lenient hub_distinction_threshold -- the same
        # bar the presell_hub_distinction_guard uses, so the two can't disagree.
        # PRESELL-vs-SOLUTION is naturally distinct, so the higher bar is safe.
        # SOLUTION/LP keep the strict jaccard_threshold.
        "jaccard_threshold": (deps.settings.uniqueness.hub_distinction_threshold
                              if role is PageRole.PRESELL
                              else deps.settings.uniqueness.jaccard_threshold),
        # Cross-run anti-boilerplate (CARD-0007): prior PRESELL opening CTA
        # lines from EVERY past run (not just this one), so opening_line_unique
        # can catch a repeat across different funnels/days -- see the
        # phrase_registry module docstring.
        "prior_opening_lines": prior_opening_lines,
        "opening_line_threshold": deps.settings.uniqueness.opening_line_threshold,
        # SOLUTION deep official links surfaced from the research (with the
        # current generic-graph fallback). Feeds BOTH the writer prompt and the
        # official_link_density validator so the density minimum reflects the
        # real official material the research provided. See build_official_links.
        "official_links": official_links,
        # FIX-3c: chromium-verified commercial platform links + their hosts. The
        # hosts whitelist same_domain for THIS page (per-page, research-derived),
        # so the writer may link exactly the platforms it names -- nothing else.
        "platform_links": platform_links,
        "verified_platforms": verified_platforms,
    }


def step_write(state: RunState, page: Page, deps: Any) -> None:
    """Write the page draft, branching by the page's EFFECTIVE role (T1D).

    LP -> `redator_p1` prompt, marker-format output (later turned into
    Elementor by step_build). PRESELL -> `redator_presell` (single forward
    destination into the SOLUTION band). SOLUTION (and anything else) ->
    `redator_pages`, the calm interior-page doctrine. Both interior prompts
    render Gutenberg HTML (normalized via `normalize_gutenberg`) and receive
    the page's TYPED, already-resolved routes (`resolve_page_links`) instead
    of a raw `{domain}/rec{cta_link}` string, so multi-destination SOLUTION
    pages (siblings + external_official + cross_funnel) render every button
    from the winning routing graph, never a bare/invented href.
    """
    facts = state.facts.get(page.page_number, ResearchFacts(sparse=True))
    research_result = state.step_status.get(f"research_p{page.page_number}")
    if research_result is not None and research_result.status is StepStatus.FAILED:
        state.step_status[f"write_p{page.page_number}"] = StepResult(
            step=f"write_p{page.page_number}", status=StepStatus.FAILED,
            issues=[Issue(
                code="research_dependency_failed",
                message="Redação não iniciada: a pesquisa factual não passou pelo gate.",
            )],
        )
        return
    domain = deps.settings.site.domain
    route_ctx = _write_ctx(state, page, deps)
    plan = state.plan or FunnelPlan()

    # PRÉ-VOO (Frente 3): as reprovações que já estavam decididas antes da
    # primeira palavra. `pagespec` valida `page.routes` — dado determinístico
    # que o redator não escreve — e `official_link_density` é impossível de
    # satisfazer quando a pesquisa não trouxe link oficial nenhum. Rodar isso
    # DEPOIS de escrever custava, na medição, até 3 redações + juiz por uma
    # reprovação que não dependia do texto. Aqui não sai nenhuma chamada paga:
    # a página falha fechada com o motivo real e o dinheiro fica no bolso.
    # Só é pré-checado o que ESTÁ na lista de validadores DESTE passo, então a
    # LP (`write_p1`, validators: []) segue sem pré-voo, exatamente como hoje.
    cfg_write = deps.settings.steps.get(
        "write_p1" if page.page_type == "LANDING PAGE" else "write_page")
    reprovas_de_insumo = preflight_issues(
        list(getattr(cfg_write, "validators", []) or []), route_ctx)
    if reprovas_de_insumo:
        state.step_status[f"write_p{page.page_number}"] = StepResult(
            step=f"write_p{page.page_number}", status=StepStatus.FAILED,
            attempts=0, issues=reprovas_de_insumo)
        return

    if page.page_type == "LANDING PAGE":
        # Destinos REAIS dos botões da LP, na ORDEM em que build_funnel_routes
        # os montou. Com presell_hubs=1 + lp_direct_solutions=2 isso é
        # [hub, solução 1, solução 2] -- e não os "3 hubs qualificadores" que o
        # prompt descrevia. Passando papel + H1 de cada destino, o redator
        # escreve cada cta_texts[i] para o destino i e o prompt para de
        # carregar um número fixo de páginas que a config pode mudar amanhã.
        _page_by_slug = {p.slug: p for p in plan.pages}
        lp_destinations: list[dict] = []
        for route in page.routes:
            if route.kind != "funnel":
                continue
            alvo = _page_by_slug.get(route.target)
            if alvo is None:
                continue
            papel = effective_role(alvo)
            lp_destinations.append({
                "slug": alvo.slug,
                "h1": alvo.h1_title,
                "objective": alvo.emotional_objective,
                "role": papel.value,
                "role_label": (
                    "hub qualificador (pré-sell neutra: ajuda o leitor a achar "
                    "o caminho do próprio caso)"
                    if papel is PageRole.PRESELL
                    else "página de solução (entrega o passo a passo de UM caminho)"
                ),
            })
        prompt = render(
            "redator_p1",
            headline=page.h1_title,
            objective=page.emotional_objective,
            skeleton="\n".join(page.main_content_structure),
            keywords=", ".join(page.target_keywords),
            cta_text=page.hook_to_next_page,
            # A LP é o destino que recebe o clique COMPRADO: a fonte da pesquisa
            # chega ao redator como NOME para citar em prosa, nunca como URL
            # para embutir. Ver `base_factual` para o achado que essa instrução
            # produziu na página que foi ao ar.
            facts=base_para_o_redator(facts, destino_pago=True),
            lp_destinations=lp_destinations,
            today=date.today().strftime("%d/%m/%Y"),
        )
        cfg = deps.settings.steps["write_p1"]
        text, res = deps.runner.run_llm_step(
            f"write_p{page.page_number}", cfg, [{"role": "user", "content": prompt}],
            ctx=route_ctx, run_id=state.run_id,
        )
        # The LP output is STRUCTURED JSON that fills the fixed Elementor
        # template (lp_template.render_lp) in step_build -- not markers, and
        # not judged by the marker/HTML judge. Its gate is the JSON schema +
        # middle-ground compliance guards (validate_lp_content) below, plus the
        # template's own design.
        try:
            content_obj = _tolerant_json(text)
        except (ValueError, json.JSONDecodeError, TypeError) as exc:
            res.status = StepStatus.FAILED
            res.issues = list(res.issues) + [
                Issue(code="parse_error", message=f"LP JSON inválido: {exc}")]
            content_obj = {}
        # MOEDA pt-BR na LP. `normalize_gutenberg` nunca toca a LP (ela é JSON,
        # não Gutenberg), e foi exatamente no corpo da LP que os valores
        # malformados foram medidos: "de 5 % a 50 %" e "até 2900.00 R$".
        content_obj = formatar_moeda_em_estrutura(content_obj)
        content = json.dumps(content_obj, ensure_ascii=False)
        # O contrato da LP roda DENTRO do runner quando `lp_json_contract` está
        # em write_p1.validators: lá ele ganha retry com feedback e o modelo tem
        # chance de consertar, em vez de morrer no primeiro tiro. Aqui sobra só
        # o caso em que o gate NÃO foi configurado -- assim o contrato nunca
        # fica sem dono, e também nunca aparece duplicado na lista de issues.
        configurados = list(cfg.validators or [])
        lp_issues: list[Issue] = []
        if "lp_json_contract" not in configurados:
            lp_issues = validate_lp_content(content_obj)
        if "critical_fact_grounding" not in configurados:
            lp_issues.extend(run_validators(
                ["critical_fact_grounding"], content, route_ctx))
        if lp_issues:
            res.issues = list(res.issues) + lp_issues
            res.status = StepStatus.FAILED
        state.step_status[f"write_p{page.page_number}"] = res
        state.drafts[page.page_number] = PageDraft(
            page_number=page.page_number, page_type=page.page_type,
            format="lp_json", content=content, word_count=_word_count(content))
        return

    # `plan` já foi resolvido acima (o ramo da LP também precisa dele).
    # Terminal = the last SOLUTION by ordinal (same rule validate_funnel_graph
    # uses). The terminal page has no "next" solution, so its writer favours the
    # cross_funnel exit (recirculate the reader into other site content) instead
    # of looping back into the funnel band.
    _solutions = sorted((p for p in plan.pages if effective_role(p) is PageRole.SOLUTION),
                        key=lambda p: p.ordinal)
    is_terminal = bool(_solutions) and page.slug == _solutions[-1].slug
    # NEUTRAL hub qualifier context (CARD-0009): the presell writer receives a
    # fixed-by-index neutral qualifier LENS + the plan's solutions as
    # 'caso -> caminho' criteria in the hub's rotated route order -- NEVER an
    # angle or a privileged lead solution. Empty for non-presell prompts.
    if effective_role(page) is PageRole.PRESELL:
        qualifier_lens = _hub_lens(page.slug)[0]
        qualifier_questions = _qualifier_questions_for(page, plan)
    else:
        qualifier_lens = ""
        qualifier_questions = []
    # CARD-0011 REQ-2: hand the SOLUTION writer the H1/theme + objective of EACH
    # forward destination (mid) so every advance button can ANNOUNCE where it
    # goes, and the cross_funnel LABEL (terminal) so its bridge frames the
    # diverse recirculation guide honestly. `next_solutions` follows the SAME
    # forward funnel routes build_funnel_routes assigned (ordinal order) -- never
    # an invented destination. Empty/"" for non-SOLUTION and where not applicable.
    if effective_role(page) is PageRole.SOLUTION and not is_terminal:
        _sol_by_slug = {p.slug: p for p in _solutions}
        next_solutions = [
            {"slug": r.target, "h1": _sol_by_slug[r.target].h1_title,
             "objective": _sol_by_slug[r.target].emotional_objective}
            for r in page.routes
            if r.kind == "funnel" and r.target in _sol_by_slug
        ]
    else:
        next_solutions = []
    cross_funnel_label = ""
    if is_terminal:
        cross_funnel_label = next(
            (r.anchor for r in page.routes if r.kind == "cross_funnel"), "")
    prompt = render(
        _prompt_name_for(page),
        role=effective_role(page).value,
        page_num=page.page_number,
        total_pages=plan.total_pages,
        is_terminal=is_terminal,
        qualifier_lens=qualifier_lens,
        qualifier_questions=qualifier_questions,
        next_solutions=next_solutions,
        cross_funnel_label=cross_funnel_label,
        headline=page.h1_title,
        objective=page.emotional_objective,
        skeleton="\n".join(page.main_content_structure),
        keywords=", ".join(page.target_keywords),
        facts=base_para_o_redator(facts),
        domain=domain,
        routes=resolve_page_links(page, deps.settings,
                                  authorized_external=route_ctx["official_links"]),
        official_links=route_ctx["official_links"],
        platform_links=route_ctx.get("platform_links", []),
        engajamento=page.engajamento,
        # O bloco visual obrigatório sai da FORMA DA PERGUNTA já classificada,
        # não de `page_num % 3`. Renumerar a página (o step_extract renumera)
        # trocava o contrato visual sem que uma vírgula do conteúdo mudasse.
        signature_block=SIGNATURE_BLOCK_BY_ENGAGEMENT.get(page.engajamento, ""),
        visual_required_blocks=route_ctx["visual_required_blocks"],
        author_name=deps.settings.site.author_name,
        author_credential=deps.settings.site.author_credential,
        cnpj=deps.settings.site.cnpj,
        today=date.today().strftime("%d/%m/%Y"),
        **doctrine_context(),
    )
    cfg = deps.settings.steps["write_page"]
    text, res = deps.runner.run_llm_step(
        f"write_p{page.page_number}", cfg, [{"role": "user", "content": prompt}],
        ctx=route_ctx, run_id=state.run_id,
    )
    content = normalize_gutenberg(
        text, ad_paragraph_anchors=deps.settings.ads.paragraph_anchors)

    state.step_status[f"write_p{page.page_number}"] = res
    state.drafts[page.page_number] = PageDraft(
        page_number=page.page_number,
        page_type=page.page_type,
        format="gutenberg",
        content=content,
        word_count=_word_count(content),
    )

    _judge_page(state, page, content, deps)


# ---------------------------------------------------------------------------
# step_seo
# ---------------------------------------------------------------------------


def step_seo(state: RunState, page: Page, deps: Any) -> None:
    draft = state.drafts.get(page.page_number)
    content = draft.content if draft else ""
    prompt = render("seo", content=content, today=date.today().strftime("%d/%m/%Y"))
    cfg = deps.settings.steps["seo"]
    text, res = deps.runner.run_llm_step(
        f"seo_p{page.page_number}", cfg, [{"role": "user", "content": prompt}], ctx={},
        run_id=state.run_id,
    )
    try:
        parsed = _tolerant_json(text)
    except (ValueError, json.JSONDecodeError):
        parsed = {}
    extra = run_validators(cfg.validators, text, {"parsed": parsed})
    if extra:
        res.issues = list(res.issues) + extra
        res.status = StepStatus.FAILED
    state.seo[page.page_number] = parsed
    state.step_status[f"seo_p{page.page_number}"] = res


# ---------------------------------------------------------------------------
# step_image
# ---------------------------------------------------------------------------


def image_wanted(settings: Any, page: Page) -> bool:
    """Whether an image should actually be GENERATED for this page.

    The LP gates on `run.hero_image` (rendered into the Elementor hero); an
    interior /rec post (SOLUTION/PRESELL) gates on `run.featured_image` (WP
    thumbnail + mid-content wp:image). Used both by the pipeline (whether to
    call step_image at all) and by step_image's own generation guard, so the
    two never disagree."""
    if page.page_type == "LANDING PAGE":
        return bool(settings.run.hero_image)
    return bool(getattr(settings.run, "featured_image", False))


def step_image(state: RunState, page: Page, deps: Any) -> None:
    """Craft the hero-image prompt via a TEXT chat model (`steps.image.model`
    -- `image_prompt.jinja` is a CHAT INSTRUCTION asking the model to WRITE
    an English image-generation prompt, it does not generate an image
    itself), then (if both image ports are configured AND the hero image is
    actually enabled) generate the image with the dedicated IMAGE model
    (`settings.run.image_model` / `run.image_quality`, wired into
    `OpenAIImageGenerator` in cli.py's `build_deps` -- see RunConfig in
    config/settings.py) and convert it to webp. Generation is skipped -- but
    the creative prompt is still produced -- when `deps.image_gen`/
    `deps.image_proc` is None (dry runs still exercise the LLM step), OR
    when `image_wanted(settings, page)` is False (LP -> `run.hero_image`;
    interior /rec post -> `run.featured_image`): for the LP,
    `build_elementor` never emits the image widget unless `hero=True` (see
    steps.py's step_build / adapters/elementor.py), and for an interior post
    the featured/mid-content image is only wired at publish when
    `featured_image` is on -- so a generated image is otherwise never used,
    and paying for a real gpt-image call for a discarded asset wastes COGS.

    Image is NON-ESSENTIAL (smoke-test finding): pointing `steps.image.model`
    at an image-only model previously sent a chat-completion call to it,
    raised, and propagated all the way out of this function -- the
    pipeline's per-page `try/except` then caught it, recorded a `page_{n}`
    FAILURE, and `continue`d PAST step_build, discarding an otherwise-good
    page whose write/judge/seo had already passed. The ENTIRE body below is
    now wrapped in one try/except: any exception (prompt-crafting call OR
    generation/webp conversion) is swallowed here, recorded as a SKIPPED
    (never FAILED) `image_p{n}` StepResult, and NEVER re-raised, so control
    always returns normally to the pipeline loop, which reaches step_build
    regardless. (`_page_blocked` in pipeline.py already only gates on
    write_p{n}/judge_p{n}/funnel_graph, never image_p{n} -- this fix's job is
    only to stop the exception from escaping this function.)"""
    key = f"image_p{page.page_number}"
    is_lp = page.page_type == "LANDING PAGE"
    try:
        # LP hero -> VERTICAL 9:16 briefing (subject up top, black-gradient
        # bottom for the title/buttons overlay); interior /rec -> LANDSCAPE
        # editorial featured image. Different prompt AND different size.
        prompt_name = "image_prompt_lp" if is_lp else "image_prompt"
        img_size = (deps.settings.run.image_size_lp if is_lp
                    else deps.settings.run.image_size_post)
        prompt_text = render(
            prompt_name, headline=page.h1_title, objective=page.emotional_objective
        )
        cfg = deps.settings.steps["image"]
        text, res = deps.runner.run_llm_step(
            key, cfg, [{"role": "user", "content": prompt_text}], ctx={},
            run_id=state.run_id,
        )
        state.step_status[key] = res

        if deps.image_gen is None or deps.image_proc is None or not image_wanted(
                deps.settings, page):
            return

        # A imagem era a ÚNICA despesa invisível do ledger: sai por httpx cru
        # (`adapters/image_openai.py`), não passa pelo LiteLLM, e a API de
        # imagens não devolve custo junto com a resposta.
        #
        # As duas frentes se encaixam aqui, cada uma no seu papel:
        #   ANTES de gerar  -> o TETO confere saldo com o preço DECLARADO no
        #                      config. É estimativa, e tem que ser: não dá para
        #                      pedir autorização depois de gastar.
        #   DEPOIS de gerar -> a TELEMETRIA lança o preço MEDIDO pela tabela do
        #                      litellm, que é o que vai para o relatório.
        # Medido vence declarado no ledger; declarado é só o que o teto usa para
        # decidir se pode gerar.
        orcamento = getattr(deps.runner, "budget", None)
        if orcamento is not None:
            orcamento.exigir_saldo(f"image_gen_p{page.page_number}",
                                   estimativa_usd=preco_declarado_da_imagem(deps.settings))
        data = deps.image_gen.generate(text, size=img_size)
        _record_image_generation(state, page, deps, img_size)
        if orcamento is not None:
            # o que ENTRA no orçamento é o custo medido que a telemetria acabou
            # de gravar; cair para o declarado só quando a medição não veio.
            medido = getattr(state.step_status.get(f"image_gen_p{page.page_number}"),
                             "cost_usd", None)
            orcamento.registrar(f"image_gen_p{page.page_number}",
                                medido if medido else preco_declarado_da_imagem(deps.settings))
        run_dir = deps.runner.runs_dir / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        out_path = run_dir / f"p{page.page_number}.webp"
        saved = deps.image_proc.to_webp(data, out_path)
        state.images[page.page_number] = str(saved)
    except Exception as exc:  # noqa: BLE001 - image is non-essential; must never fail a good page
        # PRESERVA a telemetria já paga: o SKIPPED antes SOBRESCREVIA o
        # StepResult da chamada de texto que escreveu o prompt, apagando do
        # relatório um custo que a fatura ia cobrar de qualquer jeito.
        prev = state.step_status.get(key)
        state.step_status[key] = StepResult(
            step=key, status=StepStatus.SKIPPED,
            model_used=prev.model_used if prev else "",
            attempts=prev.attempts if prev else 0,
            prompt_tokens=prev.prompt_tokens if prev else 0,
            completion_tokens=prev.completion_tokens if prev else 0,
            cost_usd=prev.cost_usd if prev else 0.0,
            latency_ms=prev.latency_ms if prev else 0,
            issues=[Issue(
                code="image_skipped",
                message=f"Etapa de imagem ignorada após falha (não bloqueante): {exc}")])


def _record_image_generation(state: RunState, page: Page, deps: Any, size: str) -> None:
    """Lança a GERAÇÃO DA IMAGEM no ledger, como passo próprio `image_gen_pN`.

    Por que passo separado de `image_pN`: `image_pN` é a chamada de TEXTO que
    escreve o prompt (centavos); `image_gen_pN` é a imagem de verdade
    (~US$ 0,05, ~12% do custo do funil) -- que até aqui não existia em
    telemetria alguma, porque saía por um `httpx.post` cru fora do
    `run_llm_step`. Somar as duas na mesma linha esconderia justamente a que
    pesa.

    A telemetria vem de `deps.image_gen.last_usage` (contrato OPCIONAL do port
    `ImageGenerator`, mesmo padrão do `ResearchProvider` no `step_research`):
    um gerador que não a expõe entra no ledger com custo desconhecido E um
    aviso -- nunca como zero silencioso. Nada aqui levanta: o chamador já está
    dentro do try/except que torna a imagem não-essencial, mas isto é só
    contabilidade e não deve chegar perto de derrubar a página."""
    key = f"image_gen_p{page.page_number}"
    usage = getattr(deps.image_gen, "last_usage", None)
    if usage is None:
        state.step_status[key] = StepResult(
            step=key, status=StepStatus.OK, attempts=1,
            model_used=str(getattr(deps.settings.run, "image_model", "") or ""),
            issues=[Issue(
                code="image_cost_unknown",
                message="Imagem gerada, mas o gerador não reportou custo "
                        "(port sem `last_usage`): COGS subestimado neste run.")])
        return
    issues: list[Issue] = []
    if getattr(usage, "cost_source", "desconhecido") == "desconhecido":
        issues.append(Issue(
            code="image_cost_unknown",
            message=f"Preço de {getattr(usage, 'model', '?')} não está na tabela do "
                    "litellm e a API não devolveu `usage`: custo lançado como 0,00 "
                    "(atualize o litellm em vez de estimar o número na mão)."))
    state.step_status[key] = StepResult(
        step=key, status=StepStatus.OK, attempts=1,
        model_used=f"{getattr(usage, 'model', '')} {getattr(usage, 'quality', '')} "
                   f"{size}".strip(),
        prompt_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        completion_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        cost_usd=float(getattr(usage, "cost_usd", 0.0) or 0.0),
        latency_ms=int(getattr(usage, "latency_ms", 0) or 0),
        issues=issues)


# ---------------------------------------------------------------------------
# step_screenshot
# ---------------------------------------------------------------------------

# Blank/under-render guard thresholds (Parte B / B3). A capture is rejected when
# either a large share of horizontal bands are near-flat OR there is one big
# CONTIGUOUS flat run (the tell-tale empty box of a spinner / lazy-load). Pure
# Pillow (per-band grayscale std-dev), no OCR/ML -- see scratchpad/validate_shot.
# These module defaults mirror ScreenshotConfig's fields; step_screenshot reads
# the live limiares/retry settle from `settings.screenshot` (Task 9 / B5). The
# larger blank-retry settle (paired with scroll=True to kick lazy-loaders, B3
# "Retry 1x (scroll + settle maior)") now lives in ScreenshotConfig.retry_settle_ms.
_BLANK_BANDS = 25
_BLANK_STD = 8.0
_BLANK_FRAC_MAX = 0.18
_BLANK_CONTIG_MAX = 0.15


def _screenshot_blank_metrics(
    png: bytes, bands: int = _BLANK_BANDS, blank_std: float = _BLANK_STD,
) -> tuple[float, float]:
    """Return (blank_frac, max_contig_blank) in [0,1]: the fraction of horizontal
    bands whose grayscale std-dev is below `blank_std`, and the largest contiguous
    run of such bands (normalised). A well-rendered page scores low on both."""
    import io

    from PIL import Image, ImageStat

    img = Image.open(io.BytesIO(png)).convert("L")
    w, h = img.size
    bands = max(1, min(bands, h))
    step = max(1, h // bands)
    flags: list[bool] = []
    for i in range(bands):
        top = i * step
        if top >= h:
            break
        bottom = h if i == bands - 1 else min(h, top + step)
        if bottom <= top:
            break
        flags.append(ImageStat.Stat(img.crop((0, top, w, bottom))).stddev[0] < blank_std)
    if not flags:
        return 0.0, 0.0
    run = mx = 0
    for f in flags:
        run = run + 1 if f else 0
        mx = max(mx, run)
    n = len(flags)
    return sum(flags) / n, mx / n


def _screenshot_is_blank(png: bytes, frac_max: float = _BLANK_FRAC_MAX,
                         contig_max: float = _BLANK_CONTIG_MAX) -> bool:
    """True when a capture looks blank/under-rendered by the B3 thresholds
    (defaults mirror config; step_screenshot passes the config limiares)."""
    frac, contig = _screenshot_blank_metrics(png)
    return frac >= frac_max or contig >= contig_max


def _screenshot_rejected_by_status(result: Any) -> bool:
    """True when a CaptureResult is an error page or a non-200 navigation."""
    status = getattr(result, "status", None)
    return bool(getattr(result, "is_error_page", False)) or (
        status is not None and status != 200)


def step_screenshot(state: RunState, page: Page, deps: Any) -> None:
    """Capture STATIC screenshots of a SOLUTION page's OFFICIAL destination
    links and save them as compressed webp assets in the run dir, for
    step_publish to embed right after the matching link.

    As URLs são EXATAMENTE as que o redator recebeu: a decisão que
    `registrar_canais_oficiais` gravou em `state.official_links` logo depois da
    pesquisa, com browser -- proveniência, visita real e sonda anti-anúncio. Ler
    do estado (e não recalcular) é o que faz prompt, gate e print falarem do
    MESMO canal e o Chromium abrir uma vez só.

    ⚠️ O recálculo por `build_official_links` aqui é FALLBACK degradado, para
    checkpoint anterior a esta mudança ou estado montado à mão em teste -- e só
    roda quando a CHAVE está ausente. Página com chave presente e lista vazia
    significa "a verificação reprovou todos os candidatos", e isso é respeitado:
    recalcular ali ressuscitaria a URL que a sonda acabou de rejeitar.

    O adapter NÃO tem mais fronteira de host: com o fim da allowlist ele exige
    https e mais nada. Se a pesquisa trouxe o cadastro do iFood, é de lá que sai
    o print.

    GATED: runs only for role SOLUTION, only when `run.official_screenshots` is
    on, and only when a provider is wired (`deps.screenshot`; cli.build_deps
    leaves it None when the flag is off OR playwright is not installed). Capped
    at `run.screenshots_max_per_page`.

    100% BEST-EFFORT, mirroring step_image's contract: the ENTIRE body is
    wrapped in one try/except. ANY failure -- provider error, a single URL
    timing out, webp conversion blowing up -- is swallowed, recorded as a
    SKIPPED (never FAILED) `screenshot_p{n}` StepResult, and NEVER re-raised, so
    a page whose write/judge/seo already passed always proceeds to build/
    publish. `_page_blocked` deliberately ignores this step; screenshots are
    non-essential and must never take down a good page."""
    key = f"screenshot_p{page.page_number}"
    try:
        # Gates -> silent no-op (no status recorded), so a run with the feature
        # off looks exactly like today. Any of these short-circuits.
        if deps.screenshot is None or not getattr(
                deps.settings.run, "official_screenshots", False):
            return
        if effective_role(page) is not PageRole.SOLUTION:
            return

        facts = state.facts.get(page.page_number, ResearchFacts(sparse=True))
        # Config-driven wiring (Task 9 / B5): capture mode, crop profile and the
        # blank-guard limiares/retry settle all come from `settings.screenshot`
        # (desktop by default) instead of hardcoded constants.
        sc = getattr(deps.settings, "screenshot", None) or ScreenshotConfig()
        # OS MESMOS canais que o redator recebeu -- escolhidos na pesquisa, com
        # browser. Sem lista de domínios: se a pesquisa trouxe o cadastro do
        # iFood, é dele que sai o print (antes o guard do adapter recusava).
        # Fallback offline para checkpoint antigo/estado montado à mão.
        # Mesma regra do `_write_ctx`: a CHAVE distingue "ninguém decidiu ainda"
        # de "decidiu-se que nenhum candidato presta". Testar a lista vazia
        # trataria os dois igual e o print sairia justamente da URL que a sonda
        # anti-anúncio acabou de reprovar.
        if page.page_number in state.official_links:
            links = list(state.official_links[page.page_number])
        else:
            links = build_official_links(facts, deps.settings.site)
        cap = getattr(deps.settings.run, "screenshots_max_per_page", 2)
        run_dir = deps.runner.runs_dir / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        shots: list[dict] = []
        for k, url in enumerate(links[:cap], start=1):
            result = deps.screenshot.capture(url, mode=sc.mode)
            # Guard 1 (status/error): drop non-200 or error/404 pages outright.
            if _screenshot_rejected_by_status(result):
                continue
            png = result.png
            # Guard 2 (blank/under-render): retry ONCE with a materially
            # different capture -- scroll the page to KICK lazy-loaders +
            # wait a LARGER settle (B3 "Retry 1x (scroll + settle maior)"),
            # deliberately attacking the cause of the blank rather than
            # re-shooting an identical frame. If the retry is still bad, give
            # up on this URL (fail-open -- skip the print, keep the page).
            if _screenshot_is_blank(png, sc.blank_frac_max, sc.blank_contig_max):
                result = deps.screenshot.capture(
                    url, mode=sc.mode, scroll=True, settle_ms=sc.retry_settle_ms)
                if _screenshot_rejected_by_status(result) or _screenshot_is_blank(
                        result.png, sc.blank_frac_max, sc.blank_contig_max):
                    continue
                png = result.png
            host = urlparse(url).netloc.lower()
            host_slug = host.replace(".", "")
            out_path = run_dir / f"p{page.page_number}-oficial-{host_slug}-{k}.webp"
            saved = deps.image_proc.screenshot_to_webp(png, out_path, profile=sc.crop_profile)
            shots.append({"url": url, "path": str(saved)})
        if shots:
            state.screenshots[page.page_number] = shots
        state.step_status[key] = StepResult(step=key, status=StepStatus.OK, attempts=1)
    except Exception as exc:  # noqa: BLE001 - screenshots are non-essential; must never fail a good page
        state.step_status[key] = StepResult(
            step=key, status=StepStatus.SKIPPED,
            issues=[Issue(
                code="screenshot_skipped",
                message=f"Etapa de screenshot ignorada após falha (não bloqueante): {exc}")])


# ---------------------------------------------------------------------------
# step_build
# ---------------------------------------------------------------------------


def _iter_widgets(nodes: list) -> list:
    """Flatten every widget in an Elementor tree in document order, recursing
    through nested containers (the LP TEMPLATE nests widgets inside inner
    containers, unlike the flat marker-built LP)."""
    out: list = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("widgetType"):
            out.append(node)
        out.extend(_iter_widgets(node.get("elements", []) or []))
    return out


def _preview_html(
    page: Page, elementor: list, decision: IndexDecision | None = None,
    head_extra: str = "",
) -> str:
    """Minimal HTML wrapper rendering the Elementor content for local
    visual review (not a pixel-accurate Elementor render, just enough to
    eyeball headings/text/buttons/image in order).

    When `decision` is given, injects `<meta name="robots">` +
    `<link rel="canonical">` so the local preview reflects the same index
    hygiene the real publish step will emit (noindex,follow + self-canonical
    -- see IndexDecision/index_decision_for). `head_extra` is appended
    verbatim after that (e.g. the vignette frequency-cap declaration)."""
    parts: list[str] = []
    for container in [{"elements": _iter_widgets(elementor)}]:
        for el in container.get("elements", []):
            wtype = el.get("widgetType")
            s = el.get("settings", {})
            if wtype == "heading":
                size = s.get("header_size", "h2")
                parts.append(f"<{size}>{s.get('title', '')}</{size}>")
            elif wtype == "text-editor":
                parts.append(s.get("editor", ""))
            elif wtype == "image":
                url = s.get("image", {}).get("url", "")
                if url:
                    parts.append(f'<img src="{url}" style="max-width:100%">')
            elif wtype == "button":
                link = s.get("link", {}).get("url", "#")
                bg = s.get("background_color", "#c8102e")
                rd = s.get("border_radius")
                radius = rd.get("top", 10) if isinstance(rd, dict) else (rd or 10)
                parts.append(
                    f'<p><a href="{link}" style="background:{bg};color:#fff;'
                    f"padding:10px 16px;border-radius:{radius}px;text-decoration:none;"
                    f'display:inline-block">{s.get("text", "")}</a></p>'
                )
    body = "\n".join(parts)
    index_head = ""
    if decision is not None:
        index_head = (
            f'<meta name="robots" content="{decision.robots}">'
            f'<link rel="canonical" href="{decision.canonical}">'
        )
    return (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        f"<title>{page.h1_title}</title>{index_head}{head_extra}</head>"
        '<body style="max-width:720px;margin:40px auto;font-family:sans-serif;'
        f'line-height:1.5">\n{body}\n</body></html>'
    )


def step_build(state: RunState, page: Page, deps: Any) -> None:
    """Turn the approved draft into its final publishable artifact.

    LANDING PAGE -> build_elementor(markers) -> writes p1.elementor.json +
    p1.preview.html. HUB/SOLUTION -> content is already normalized
    Gutenberg HTML (done in step_write); just persist the draft file.
    """
    draft = state.drafts.get(page.page_number)
    if draft is None:
        return
    run_dir = deps.runner.runs_dir / state.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    decision = index_decision_for(deps.settings, page)

    manifest = build_ad_manifest(deps.settings, effective_role(page))
    (run_dir / f"p{page.page_number}.admanifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )

    if page.page_type == "LANDING PAGE":
        # T2G fix: prefer the winning-graph routes (ALL of `page.routes`, the
        # SAME data pagespec/reachability already validated -- see
        # build_funnel_routes) over a separately-derived next_page_slug -- one
        # funnel href per LP button, so resolve_route stays the SOLE href former
        # for the LP too. Only fall back to the next_page_slug-derived Route when
        # routing never ran (page.routes empty), e.g. a step_build call made
        # directly on a bare Page in a unit test.
        if page.routes:
            routes = page.routes
            # Fail-closed: an HONEST funnel (built by expand_presell_hubs with 3
            # neutral hubs) must reach 3 DISTINCT pre-sell destinations from the
            # LP -- one congruent CTA per hub. If the plan carries the 3 hubs
            # but the LP collapsed to fewer distinct targets, the graph is broken
            # -> fail the page instead of shipping a degenerate single-CTA LP.
            plan_presells = sum(
                1 for p in (state.plan.pages if state.plan else [])
                if effective_role(p) is PageRole.PRESELL)
            distinct = len({r.target for r in routes})
            if plan_presells >= 3 and distinct < 3:
                state.step_status[f"build_p{page.page_number}"] = StepResult(
                    step=f"build_p{page.page_number}", status=StepStatus.FAILED,
                    issues=[Issue(code="lp_destinos",
                                  message="LP precisa de 3 destinos (pré-sells) distintos; "
                                          f"veio {distinct}.")])
                return
        else:
            routes = [Route(placement="hero", kind="funnel",
                            target=page.next_page_slug, anchor=page.hook_to_next_page)]
        try:
            hrefs = [
                resolve_route(
                    route, domain=deps.settings.site.domain,
                    post_type=deps.settings.site.post_type)
                for route in routes
            ]
        except ValueError as exc:
            state.step_status[f"build_p{page.page_number}"] = StepResult(
                step=f"build_p{page.page_number}", status=StepStatus.FAILED,
                issues=[Issue(code="bare_rec", message=str(exc))])
            return
        image_url = state.images.get(page.page_number) or ""
        try:
            content_obj = json.loads(draft.content)
        except (ValueError, json.JSONDecodeError):
            content_obj = {}
        # Clone the fixed, designer-built Elementor TEMPLATE and repopulate
        # ONLY the content + hero image + funnel hrefs (design preserved).
        # Replaces the old marker -> build_elementor path for the LP.
        elementor, page_settings = render_lp(
            load_lp_template(), content_obj, funnel_hrefs=hrefs,
            hero_image_url=image_url, id_seed=state.run_id)
        (run_dir / "p1.elementor.json").write_text(
            json.dumps(elementor, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (run_dir / "p1.page_settings.json").write_text(
            json.dumps(page_settings, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        head = vignette_meta(manifest.vignette)
        (run_dir / "p1.head.html").write_text(head, encoding="utf-8")
        (run_dir / "p1.preview.html").write_text(
            _preview_html(page, elementor, decision=decision, head_extra=head),
            encoding="utf-8",
        )
        (run_dir / f"p{page.page_number}.{page.slug}.lp_content.json").write_text(
            draft.content, encoding="utf-8"
        )
    else:
        (run_dir / f"p{page.page_number}.{page.slug}.gutenberg.html").write_text(
            draft.content, encoding="utf-8"
        )

    (run_dir / f"p{page.page_number}.meta.json").write_text(
        decision.model_dump_json(indent=2), encoding="utf-8")

    state.step_status[f"build_p{page.page_number}"] = StepResult(
        step=f"build_p{page.page_number}", status=StepStatus.OK, attempts=1
    )


# ---------------------------------------------------------------------------
# step_widget (CARD-0013): interactive SOLUTION widgets -- gated + 100% fail-safe
# ---------------------------------------------------------------------------

_WIDGET_BLOCK_RE = re.compile(r"<!--\s*wp:html\s*-->.*?<!--\s*/wp:html\s*-->", re.S | re.I)
# One heading block, scoped to its OWN open..close (non-greedy) so a later FAQ
# heading never bleeds into an earlier heading's window.
_WIDGET_HEADING_BLOCK_RE = re.compile(
    r"<!--\s*wp:heading\b.*?<!--\s*/wp:heading\s*-->", re.S | re.I)
_WIDGET_H2_RE = re.compile(r"<h2\b", re.I)
_WIDGET_FAQ_RE = re.compile(r"perguntas\s+frequentes", re.I)


def _widget_h2_positions(content: str) -> list[int]:
    """Start indices of every `<!-- wp:heading -->` block that renders an <h2>,
    EXCLUDING a 'Perguntas Frequentes' (FAQ) heading -- the FAQ is reserved for
    its own fallback anchor and never counts toward the 3-H2 threshold, so a
    `2 content H2 + FAQ` article takes the FAQ branch, not the 3rd-H2 branch."""
    out: list[int] = []
    for m in _WIDGET_HEADING_BLOCK_RE.finditer(content):
        block = m.group(0)
        if not _WIDGET_H2_RE.search(block):
            continue
        if _WIDGET_FAQ_RE.search(block):
            continue
        out.append(m.start())
    return out


def _widget_faq_position(content: str) -> int | None:
    """Start index of a heading block whose text is 'Perguntas Frequentes' (any
    level), else None."""
    for m in _WIDGET_HEADING_BLOCK_RE.finditer(content):
        if _WIDGET_FAQ_RE.search(m.group(0)):
            return m.start()
    return None


def _widget_insert_at(content: str, pos: int, block: str) -> str:
    return content[:pos].rstrip() + "\n\n" + block + "\n\n" + content[pos:]


def inject_widget(content: str, block: str) -> str:
    """Insert `block` into the article content, fenced by blank lines. Anchor:
    BEFORE the 3rd content H2 when there are >=3; else BEFORE the 'Perguntas
    Frequentes' heading; else appended at the end. Pure function (no placeholder,
    no state) -- the injection point the injector tests pin."""
    b = block.strip()
    positions = _widget_h2_positions(content)
    if len(positions) >= 3:
        return _widget_insert_at(content, positions[2], b)
    faq = _widget_faq_position(content)
    if faq is not None:
        return _widget_insert_at(content, faq, b)
    # Defense in depth (the `min_headings` validator makes <3 H2 SOLUTION pages
    # fail before here): with 1-2 content H2, anchor BEFORE the last one so the
    # widget lands inside the article, never dumped at the decontextualized tail.
    if positions:
        return _widget_insert_at(content, positions[-1], b)
    return content.rstrip() + "\n\n" + b + "\n"


def _widget_skip(page: Page, *issues: Issue, pago: StepResult | None = None) -> StepResult:
    """A SKIPPED widget result: the article remains intact (no widget).

    The final content gate decides whether that absence is allowed: it blocks
    publication when widgets are enabled and the page's semantic archetype is
    not ``None``. The leading `widget_rejected` issue marks the rejection; the
    remaining issue code(s) are the machine-readable `widget_error` label(s)
    (a sanitization label, or widget_none / widget_empty / widget_no_block /
    widget_llm_error / widget_exception / widget_no_config).
    ⚠️ `pago` é a telemetria da chamada que JÁ ACONTECEU. Sem ela, um widget
    rejeitado ia para o ledger com custo, tokens, tentativas e latência ZERADOS
    — trabalho pago aparecendo como grátis. Medido no run de referência:
    `widget_p5` está gravado com `cost_usd: 0.0` e duas issues, mas o modelo
    tinha rodado e cobrado. O relatório dizia US$ 2,547 e a fatura era maior.

    Rejeição não é ausência de gasto: é gasto que não virou entrega — que é
    exatamente o número que o operador precisa ver."""
    return StepResult(
        step=f"widget_p{page.page_number}",
        status=StepStatus.SKIPPED,
        issues=[Issue(code="widget_rejected",
                      message="Widget não injetado; o gate final decidirá a publicação.")]
        + list(issues),
        model_used=pago.model_used if pago else "",
        attempts=pago.attempts if pago else 0,
        prompt_tokens=pago.prompt_tokens if pago else 0,
        completion_tokens=pago.completion_tokens if pago else 0,
        cost_usd=pago.cost_usd if pago else 0.0,
        latency_ms=pago.latency_ms if pago else 0,
    )


def _extract_widget_block(text: str) -> str | None:
    """The SINGLE `<!-- wp:html -->…<!-- /wp:html -->` block in the LLM output
    (tolerating surrounding prose / code fences), or None if there isn't exactly
    one -- the generator's contract is exactly one self-contained block."""
    matches = _WIDGET_BLOCK_RE.findall(text)
    if len(matches) != 1:
        return None
    return matches[0].strip()


# CARD-0014: the 8-archetype creative taxonomy (REQ-4 / Seção 4.3), ORDERED.
# The draw indexes into THIS tuple; the order is the CONTRACT shared with
# redator_widget.jinja's catalog (same 8 names, same spelling). None of these is
# a "calculadora" -- diversity by construction is the fix for the Insight-4 bias
# ("evitar o erro de ter só calculadora").
WIDGET_ARCHETYPES: tuple[str, ...] = (
    "Roteador de Elegibilidade",
    "Termômetro de Prontidão",
    "Detector de Sinais de Golpe",
    "Comparador de Rotas",
    "Navegador de Jornada",
    "Quiz Mito ou Verdade",
    "Tradutor de Termos",
    "Priorizador de Próximos Passos",
    # 9º: cobre a forma de pergunta `diagnostico` -- "por que não funcionou
    # COMIGO". É a de maior IGNORÂNCIA, e ignorância foi o eixo que mais
    # correlacionou com desfecho no motor de pautas (+0,194, contra +0,017 da
    # hipótese de persistência que caiu). Quem chega com problema não está
    # pesquisando: está travado, e lê tudo até destravar.
    "Diagnóstico de Recusa",
)

# --- A PONTE: a forma da PERGUNTA escolhe a FERRAMENTA -----------------------
# O eixo `engajamento` do motor de pautas (google_ads_forge/motor_pautas) mede
# quanto tempo de atenção a resposta EXIGE, classificando a forma da pergunta.
# É um dos três PORTÕES do motor -- ele já decide se o tema vale a pena. A
# mesma classificação diz qual ferramenta a página pede.
#
# Sem isto, o arquétipo saía de `sha1(run_id) % 8`: determinístico e diverso,
# mas ARBITRÁRIO em relação ao conteúdo -- uma página sobre "quais bancos
# antecipam FGTS" podia receber um Detector de Sinais de Golpe, e uma sobre
# "como identificar boleto falso" um Comparador de Rotas. Trocados.
#
# `dado_unico` mapeia para None DE PROPÓSITO: se a resposta da página é um
# número, um widget interativo é enfeite -- e enfeite ao lado de anúncio é
# ruído que custa viewability. Melhor não construir.
ENGAJAMENTO_PARA_ARQUETIPO: dict[str, str | None] = {
    "condicional":  "Roteador de Elegibilidade",     # "depende de A, B, C"
    "sequencial":   "Navegador de Jornada",          # "passo 1 ao 7"
    "comparativo":  "Comparador de Rotas",           # "qual das opções"
    "diagnostico":  "Diagnóstico de Recusa",         # "por que não funcionou"
    "dado_unico":   None,                            # a resposta é um número
}


def infer_engajamento(page: Page) -> str:
    """Deterministic semantic fallback from the page's own question/outline."""
    raw = " ".join((page.h1_title, page.emotional_objective,
                    " ".join(page.main_content_structure))).lower()
    raw = unicodedata.normalize("NFKD", raw)
    text = "".join(ch for ch in raw if not unicodedata.combining(ch))
    rules = (
        ("comparativo", ("compar", " versus ", " vs ", "qual opcao", "melhor opcao")),
        ("condicional", ("quem tem direito", "elegib", "requisit", "se eu", "depende")),
        ("diagnostico", ("por que", "recus", "negad", "erro", "problema", "nao consigo")),
        ("dado_unico", ("quanto", "valor", "limite", "taxa", "percentual", "prazo")),
        ("sequencial", ("como ", "passo", "etapa", "consultar", "solicitar", "fazer")),
    )
    for label, signals in rules:
        if any(signal in text for signal in signals):
            return label
    # A service article with no diagnostic/comparison signal is operational by
    # default.  This is a stable semantic default, not a run-id lottery.
    return "sequencial"


def engajamento_declarado(page: Page) -> str:
    """A forma de pergunta que a página DECLARA, canonizada e com a escala
    binária do motor de pautas já traduzida. `""` = a página não declarou nada.

    Três casos:

    1. Uma das cinco FORMAS, em qualquer grafia (`Dado Único`, `diagnóstico`)
       -> ela mesma, canonizada. Antes, `.strip().lower()` deixava `Dado Único`
       cair no fallback -- e o fallback podia devolver widget numa página que o
       motor mandou NÃO ter widget.
    2. `sustenta`, o nível da escala BINÁRIA nova (`motor_pautas/espaco.py`) ->
       ele afirma "há o que ler", mas não diz QUAL forma; refina por inferência
       semântica sobre H1/objetivo/estrutura. Nunca devolve `dado_unico` aqui:
       isso contradiria o que o card afirmou.
    3. Qualquer outra coisa -> sai INTACTA (canonizada), de propósito. É um
       rótulo torto, e quem o recebe -- `visual_contract` -- precisa poder
       RECLAMAR dele. Trocar por "" aqui devolveria o silêncio ao portão.
    """
    rotulo = canon_engajamento(page.engajamento)
    if rotulo == "sustenta":
        forma = infer_engajamento(page)
        return "sequencial" if forma == "dado_unico" else forma
    return rotulo


def engajamento_efetivo(page: Page) -> str:
    """A forma usada para ESCOLHER (nunca para bloquear): a declarada quando
    utilizável, senão a inferência determinística. É o que `widget_archetype_for`
    consome.

    ⚠️ A ASSIMETRIA COM `visual_contract` É PROPOSITAL E AGORA ESTÁ DECLARADA.
    Escolher ferramenta por inferência é sempre seguro -- toda escolha é válida,
    e a alternativa seria sorteio. BLOQUEAR publicação por inferência não é: o
    `infer_engajamento` é heurística de palavra-chave ("como " -> sequencial), e
    reprovar uma página porque o H1 dela tinha "como" seria o portão inventando
    um requisito que ninguém declarou. Por isso o portão exige rótulo DECLARADO
    e reclama alto do rótulo torto, em vez de inferir.
    """
    forma = engajamento_declarado(page)
    return forma if forma in ENGAJAMENTO_PARA_ARQUETIPO else infer_engajamento(page)


def widget_archetype_for(state: RunState, page: Page) -> str | None:
    """O arquétipo de widget desta SOLUÇÃO, sempre derivado do conteúdo.

    1. DERIVADO -- `page.engajamento` (a forma da pergunta, vinda do motor de
       pautas) mapeado por `ENGAJAMENTO_PARA_ARQUETIPO`. É a fonte CERTA: a
       ferramenta passa a responder ao que a página é, não a um sorteio.
       Devolve `None` quando o eixo diz `dado_unico` -- a resposta é um número,
       e widget ali é enfeite ao lado de anúncio. `step_widget` trata o None
       como "não gere".

    Se o declarador não trouxe um rótulo válido, ``engajamento_efetivo`` cai na
    inferência semântica sobre H1, objetivo e estrutura da própria página.  Não
    existe fallback por run_id, posição da página ou sorteio."""
    return ENGAJAMENTO_PARA_ARQUETIPO[engajamento_efetivo(page)]


def step_widget(state: RunState, page: Page, deps: Any) -> None:
    """Generate + sanitize + inject an interactive wp:html widget for a SOLUTION
    page. GATED and isolated from the article body:

    - Gates -> SILENT no-op (no status recorded), so a run with the feature OFF
      looks EXACTLY like today: `run.widgets_enabled` off, role != SOLUTION, or
      no draft content to inject into.
    - The ENTIRE body is wrapped in one try/except. ANY problem -- a NONE reply,
      empty / non-single-block output, sanitization rejection, an LLM FAILED
      result, or a raised exception -- leaves the article INTACT and records a
      SKIPPED `widget_p{n}` (widget_rejected + a widget_error label). The final
      content gate then blocks publication when this page requires the widget.
      The sanitized widget block is the ONLY sanctioned
      path for a <script> onto a page; the article body itself stays script-free
      (write-time gutenberg_blocks / has_script gate is untouched).

    Runs AFTER step_build and BEFORE step_publish (see pipeline.py): it mutates
    the FINAL draft content (post-normalize) that step_publish reads, so the
    published SOLUTION post carries the widget."""
    # Gates -> silent no-op (nothing recorded), so flag-off is byte-for-byte the
    # current pipeline. Each short-circuits before any LLM call.
    if not getattr(deps.settings.run, "widgets_enabled", False):
        return
    if effective_role(page) is not PageRole.SOLUTION:
        return
    draft = state.drafts.get(page.page_number)
    if draft is None or not draft.content.strip():
        return
    # O eixo `engajamento` pode dizer que esta página NÃO comporta widget
    # (`dado_unico`: a resposta é um número, a interação não agrega e o enfeite
    # ao lado do anúncio custa viewability). Silêncio, sem chamada de LLM.
    archetype = widget_archetype_for(state, page)
    if archetype is None:
        return

    key = f"widget_p{page.page_number}"
    try:
        cfg = deps.settings.steps.get("widget")
        if cfg is None:
            state.step_status[key] = _widget_skip(
                page, Issue(code="widget_no_config", message="steps.widget ausente na config."))
            return
        # ── O MODELO NÃO ESCREVE MAIS CÓDIGO ──────────────────────────────
        #
        # Ele devolve JSON de conteúdo; `funnelforge/widgets/render.py` imprime
        # o HTML. O que antes era instrução torcendo para ser obedecida —
        # allowlist de tags, `grid-area`, ausência de `&` no script,
        # `visibility` em vez de `display`, acessibilidade — virou propriedade
        # do gabarito, provada em `tests/test_widgets.py`.
        #
        # O que sobra de falível é só o CONTEÚDO, e é exatamente aí que a
        # retentativa funciona: `WidgetInvalido.motivos` nomeia o que faltou
        # (qual combinação de respostas ficou sem cenário, qual cenário veio
        # vazio) e isso volta para o modelo como lista.
        #
        # Duas tentativas, não mais: se o modelo repetir o mesmo erro com o
        # erro apontado, o problema não é de instrução.
        chave_arq = chave_por_nome(archetype)
        if chave_arq is None:
            state.step_status[key] = _widget_skip(
                page, Issue(code="widget_arquetipo_desconhecido",
                            message=f"Arquétipo sem gabarito: {archetype}."))
            return

        tentativas_widget = 2
        correcao = ""
        text = ""
        res = None
        block = None
        issues: list[Issue] = []

        for tentativa in range(1, tentativas_widget + 1):
            prompt = render(
                "redator_widget", country="Brasil", year=date.today().year,
                title=page.h1_title, article=draft.content,
                arquetipo=chave_arq,
                # A MESMA base podada que o redator recebeu. Sem isto o gerador
                # de widget era o único componente que escrevia texto publicado
                # sem saber quais números são permitidos — e o gate final, que
                # valida o conteúdo COM o widget injetado, matava a página
                # depois de o widget ter sido pago. Medido no run #6
                # (17/08/2026): a p3 passou em tudo e caiu por um "30 a 60 dias"
                # que o widget inventou.
                facts=base_para_o_redator(state.facts.get(page.page_number)),
            ) + correcao
            text, res = deps.runner.run_llm_step(
                key, cfg, [{"role": "user", "content": prompt}], ctx={},
                run_id=state.run_id)
            if res.status is StepStatus.FAILED:
                break
            raw_t = (text or "").strip()
            if not raw_t or raw_t.upper() == "NONE":
                break

            try:
                widget = ler(raw_t)
            except WidgetInvalido as invalido:
                issues = [Issue(code="widget_conteudo_invalido", message=m)
                          for m in invalido.motivos]
                block = None
                if tentativa < tentativas_widget:
                    correcao = (
                        "\n\n=== A TENTATIVA ANTERIOR FOI RECUSADA ===\n"
                        + "\n".join(f"  - {m}" for m in invalido.motivos[:8])
                        + "\nDevolva o JSON INTEIRO de novo, corrigindo exatamente "
                          "isso. Não mude o que estava certo.\n"
                    )
                continue

            block = renderizar(widget)
            # ⚠️ O sanitizador roda sobre markup NOSSO. Se ele recusar aqui, é
            # defeito de gabarito e não do modelo — e nesse caso retentar é
            # inútil, porque a segunda renderização sai idêntica. Mantemos a
            # chamada porque ela é a última linha de defesa antes de publicar;
            # quem deve pegar isso antes é `test_todo_arquetipo_passa_no_sanitizador`.
            issues = sanitize_widget_block(block)
            # O gate factual também vale para o widget. Rodá-lo AQUI, e não só
            # no `content_gate`, é o que permite RETENTAR: no gate final já é
            # tarde, e a página inteira morre por uma frase do widget.
            #
            # ⚠️ `ResearchFacts(sparse=True)` NÃO é detalhe. Esta linha passava
            # `state.facts.get(...)` puro, que é `None` quando a página não tem
            # fatos — e com `None` o validador devolve lista vazia e aprova
            # tudo. O `content_gate` usa `_write_ctx`, que preenche o mesmo
            # buraco com `ResearchFacts(sparse=True)` e reprova.
            #
            # O resultado era um widget que PASSAVA na própria checagem e morria
            # no portão seguinte — quando já não havia retentativa, e a página
            # inteira caía junto. É preciso julgar aqui com a MESMA régua de lá.
            issues += run_validators(
                ["critical_fact_grounding"], block,
                {"facts": state.facts.get(page.page_number, ResearchFacts(sparse=True))})
            if not issues:
                break
            if tentativa < tentativas_widget:
                detalhes = "\n".join(f"  - [{i.code}] {i.message}" for i in issues[:6])
                correcao = (
                    "\n\n=== A TENTATIVA ANTERIOR FOI RECUSADA ===\n"
                    f"{detalhes}\n"
                    "Se o motivo for ancoragem factual: todo número, prazo ou "
                    "regra do seu JSON tem de estar na lista de FATOS "
                    "AUTORIZADOS. Reescreva a frase SEM o número — orientação "
                    "correta sem cifra é útil, cifra inventada derruba a página.\n"
                )
                block = None

        if res is not None and res.status is StepStatus.FAILED:
            state.step_status[key] = _widget_skip(
                page, Issue(code="widget_llm_error",
                            message="Geração do widget falhou; publicação será reavaliada."))
            return
        raw = (text or "").strip()
        if not raw:
            state.step_status[key] = _widget_skip(
                page, Issue(code="widget_empty", message="Gerador retornou vazio."))
            return
        if raw.upper() == "NONE":
            state.step_status[key] = _widget_skip(
                page, Issue(code="widget_none",
                            message="Gerador decidiu que nenhum widget agrega (NONE)."))
            return
        if block is None:
            state.step_status[key] = _widget_skip(
                page, *(issues or [Issue(code="widget_conteudo_invalido",
                                         message="O JSON do widget não descreve uma peça publicável.")]),
                pago=res)
            return
        if issues:
            # Rejected: publish the article WITHOUT the widget. Surface every
            # sanitization label as the widget_error(s).
            state.step_status[key] = _widget_skip(page, *issues, pago=res)
            return
        draft.content = inject_widget(draft.content, block)
        state.step_status[key] = StepResult(
            step=key, status=StepStatus.OK, model_used=res.model_used, attempts=res.attempts,
            prompt_tokens=res.prompt_tokens, completion_tokens=res.completion_tokens,
            cost_usd=res.cost_usd, latency_ms=res.latency_ms)
    except Exception as exc:  # noqa: BLE001 - turn exception into a deterministic gate result
        state.step_status[key] = _widget_skip(
            page, Issue(code="widget_exception",
                        message=f"Exceção no widget: {exc}"))


_FINAL_CONTENT_VALIDATORS: tuple[str, ...] = (
    # Only contracts that can be invalidated by normalization/widget injection
    # or that must be impossible to bypass by editing the LLM validator list.
    "gutenberg_blocks", "cta_style", "calm_utility", "same_domain", "identity",
    "critical_fact_grounding", "raw_html_contract", "ad_interaction", "visual_contract",
    # O clique comprado não vaza por botão: destino externo só no canal que a
    # pesquisa desta página escolheu (citação em prosa continua livre).
    "external_cta_authorized",
)


def _final_content_issues(state: RunState, page: Page, deps: Any, content: str) -> list[Issue]:
    ctx = _write_ctx(state, page, deps)
    ctx["allow_sanitized_widget_script"] = True
    issues = run_validators(list(_FINAL_CONTENT_VALIDATORS), content, ctx)

    # ⚠️ O WIDGET DEIXOU DE SER CONDIÇÃO DE PUBLICAÇÃO.
    #
    # Até 19/08/2026 a ausência do widget virava `required_widget_missing`, que
    # é uma issue, e uma issue reprova o gate — então a página inteira caía.
    # Medido na run 9: p3 e p4 morreram assim. Duas delas com o artigo pronto
    # no disco (11.080 e 13.415 bytes), pesquisado, escrito, julgado, com SEO,
    # imagem e build feitos. A p4 caiu por um teto de custo estourado em
    # US$ 0,0022 — dois décimos de centavo.
    #
    # A troca era ruim nos dois sentidos. Um artigo de utilidade pública COM
    # widget é melhor que sem; um artigo sem widget é infinitamente melhor que
    # artigo nenhum. Trocar o segundo pelo primeiro nunca foi a intenção — é
    # efeito colateral de um enriquecimento ter virado requisito.
    #
    # Agora o widget é registrado como AUSENTE e a página segue. Quem quiser o
    # widget depois roda o passo de novo; quem não rodar, publicou mesmo assim.
    # A rejeição continua visível em `widget_p{n}` (SKIPPED, com o motivo e o
    # custo já pago), que é onde o operador precisa vê-la.
    expected_widget = (
        getattr(deps.settings.run, "widgets_enabled", False)
        and effective_role(page) is PageRole.SOLUTION
        and widget_archetype_for(state, page) is not None
    )
    if expected_widget:
        widget = state.step_status.get(f"widget_p{page.page_number}")
        if widget is None or widget.status is not StepStatus.OK:
            state.step_status[f"widget_ausente_p{page.page_number}"] = StepResult(
                step=f"widget_ausente_p{page.page_number}",
                status=StepStatus.SKIPPED,
                attempts=0,
                issues=[Issue(
                    code="widget_ausente_publicado_assim_mesmo",
                    message="A página comportava widget e ele não saiu. Publicada sem "
                            "ele: um artigo sem widget vale mais que artigo nenhum.")],
            )
    return issues


# ---------------------------------------------------------------------------
# O PORTÃO DO DESTINO PAGO — a barreira que a LP não tinha
#
# Até aqui `step_content_gate` abria com um `if page.page_type == "LANDING PAGE":
# ... return`: a LP, que é o destino do clique COMPRADO, era a única página do
# sistema isenta do portão de conteúdo. Ela era marcada OK sem que validador
# nenhum rodasse, e `step_publish` completava o buraco — o ramo Elementor nunca
# chamava `_final_content_issues`.
#
# O portão que entra no lugar não é uma regra nova escrita aqui: é o contrato de
# `backend/app/landing_policy`, consumido pela ponte
# `adapters/landing_policy_gate`. Duas regras para o mesmo fato divergem no
# primeiro mês; uma só não tem como discordar de si mesma.
# ---------------------------------------------------------------------------


def _lp_hrefs(page: Page, deps: Any) -> list[str]:
    """Os destinos REAIS dos botões da LP, formados por `resolve_route`.

    Mesma fonte que `step_build` usa para renderizar o Elementor, então o portão
    avalia o mesmo destino que o leitor vai clicar. Rota que não resolve NÃO vira
    href vazio silencioso: ela some da lista e o CTA correspondente chega ao
    portão sem destino, que é o que `bare_rec`/incongruência descrevem.
    """
    hrefs: list[str] = []
    for route in page.routes:
        if route.kind != "funnel":
            continue
        try:
            hrefs.append(resolve_route(route, domain=deps.settings.site.domain,
                                       post_type=deps.settings.site.post_type))
        except ValueError:
            hrefs.append("")
    return hrefs


def _portao_da_lp(state: RunState, page: Page, deps: Any, *,
                  carimbo_epoch: float | None = None,
                  carimbo: str | None = None) -> lp_gate.ResultadoDoPortao:
    """Avalia o ARTEFATO da LP no ponto de portão de geração.

    O papel sai de `papel_do_servidor` dentro do contrato: `e_destino_de_campanha`
    é apurado do TIPO da página (a LP é a URL para onde o anúncio aponta) e
    `coleta_dado_do_visitante` é apurado do artefato (existe campo de
    formulário?). Nenhum dos dois vem de campo do chamador — é a diferença entre
    um portão e uma configuração.
    """
    draft = state.drafts.get(page.page_number)
    if draft is None or not draft.content.strip():
        return lp_gate.ResultadoDoPortao(
            pronto=False,
            issues=[Issue(code="missing_final_draft", message="Rascunho final ausente.")],
        )
    try:
        conteudo = json.loads(draft.content)
    except (ValueError, json.JSONDecodeError, TypeError) as exc:
        # JSON ilegível não é página limpa: sem artefato não há o que avaliar, e
        # "não deu para ler" reprova pelo mesmo motivo que uma varredura que
        # explode reprova dentro do contrato.
        return lp_gate.ResultadoDoPortao(
            pronto=False,
            issues=[Issue(code="lp_json_ilegivel",
                          message=f"O artefato da LP não é JSON legível: {exc}")],
        )
    if not isinstance(conteudo, dict):
        return lp_gate.ResultadoDoPortao(
            pronto=False,
            issues=[Issue(code="lp_json_ilegivel",
                          message="O artefato da LP não é um objeto JSON.")],
        )
    # O Elementor já renderizado entra na apuração de campo de formulário: o
    # template é fixo e desenhado à mão hoje, mas um widget de formulário
    # acrescentado nele amanhã tem de subir o papel sozinho.
    elementor_bruto = ""
    run_dir = getattr(getattr(deps, "runner", None), "runs_dir", None)
    if run_dir is not None:
        caminho = Path(run_dir) / state.run_id / "p1.elementor.json"
        if caminho.exists():
            elementor_bruto = caminho.read_text(encoding="utf-8")
    try:
        plano = lp_gate.plano_da_landing_page(
            conteudo=conteudo,
            settings=deps.settings,
            slug=page.slug,
            papel_do_motor=effective_role(page).value,
            hrefs=_lp_hrefs(page, deps),
            fontes_de_pesquisa=state.official_links.get(page.page_number, []),
            elementor_bruto=elementor_bruto,
        )
        return lp_gate.avaliar_plano_de_destino(
            plano,
            settings=deps.settings,
            e_destino_de_campanha=page.page_type == "LANDING PAGE",
            papel_declarado=effective_role(page).value,
            carimbo_epoch=carimbo_epoch,
            carimbo=carimbo,
        )
    except lp_gate.PortaoIndisponivel as exc:
        return lp_gate.indisponivel(exc)


def step_content_gate(state: RunState, page: Page, deps: Any) -> None:
    """Validate the exact Gutenberg draft that may be handed to WordPress.

    This is intentionally after normalization, build and widget injection.
    Validators configured on the LLM runner only see the model's pre-normalized
    response; this second, non-optional gate closes that transformation gap.

    A LANDING PAGE não é mais isenta: ela passa pelo portão do destino pago, que
    lê o JSON estruturado como PLANO (título, H1, subtítulos, CTAs e destinos são
    campos, não corpo — e um portão que só recebe corpo não reprova o que não
    está no corpo).
    """
    key = f"content_gate_p{page.page_number}"
    if page.page_type == "LANDING PAGE":
        resultado = _portao_da_lp(state, page, deps)
        state.step_status[key] = StepResult(
            step=key,
            # ⚠️ O predicado é `paid_destination_ready`, nunca `if bloqueios`.
            # Testar só bloqueios ignora DESCONHECIDO (verificação exigida que
            # não pôde ser concluída) e transforma varredura quebrada em página
            # limpa.
            status=StepStatus.OK if resultado.pronto else StepStatus.FAILED,
            attempts=1,
            issues=resultado.issues,
        )
        return
    draft = state.drafts.get(page.page_number)
    if draft is None or not draft.content.strip():
        state.step_status[key] = StepResult(
            step=key, status=StepStatus.FAILED,
            issues=[Issue(code="missing_final_draft", message="Rascunho final ausente.")],
        )
        return

    issues = _final_content_issues(state, page, deps, draft.content)

    state.step_status[key] = StepResult(
        step=key,
        status=StepStatus.FAILED if issues else StepStatus.OK,
        attempts=1,
        issues=issues,
    )


# ---------------------------------------------------------------------------
# step_publish
# ---------------------------------------------------------------------------


def _upload_hero_and_rewrite(state: RunState, page: Page, deps: Any, elementor: list) -> None:
    """Upload the local hero .webp to WordPress media and rewrite the Elementor
    image widget's URL to the returned media URL, IN PLACE.

    The build step points the hero at a LOCAL run path (`runs/<id>/pN.webp`),
    which is meaningless inside WordPress -- either as an image WIDGET
    (marker LP) or as a container's `background_image_mobile` (TEMPLATE LP).
    So upload the bytes and rewrite BOTH: every image-widget url, and every
    `url` field still equal to the local path. Best-effort and NON-FATAL: any
    failure leaves the Elementor untouched so the draft still publishes."""
    local = state.images.get(page.page_number)
    if not local or not hasattr(deps.publisher, "upload_media"):
        return
    try:
        data = Path(local).read_bytes()
        media = deps.publisher.upload_media(
            data, filename=f"p{page.page_number}.webp", mime="image/webp")
        url = media.get("source_url") or media.get("guid", {}).get("rendered")
        if not url:
            return

        def _rewrite(node: object) -> None:
            if isinstance(node, dict):
                if node.get("widgetType") == "image":
                    node.setdefault("settings", {}).setdefault("image", {})["url"] = url
                for k, v in node.items():
                    if k == "url" and v == local:
                        node[k] = url
                    else:
                        _rewrite(v)
            elif isinstance(node, list):
                for x in node:
                    _rewrite(x)

        _rewrite(elementor)
    except Exception:  # noqa: BLE001 - hero upload is non-essential; never fail publish
        return


def _upload_featured(state: RunState, page: Page, deps: Any, alt: str) -> tuple[int | None, str]:
    """Upload the interior post's generated .webp to WP media and return
    `(media_id, hosted_url)` so the caller can set it as `featured_media` (the
    post thumbnail) and drop a mid-content copy. Best-effort / NON-FATAL:
    returns `(None, "")` when no image was generated, the publisher can't
    upload, or anything raises -- publish must never fail over a featured
    image."""
    local = state.images.get(page.page_number)
    if not local or not hasattr(deps.publisher, "upload_media"):
        return None, ""
    try:
        data = Path(local).read_bytes()
        media = deps.publisher.upload_media(
            data, filename=f"p{page.page_number}.webp", mime="image/webp", alt=alt)
        mid = media.get("id")
        url = media.get("source_url") or media.get("guid", {}).get("rendered") or ""
        return (mid if isinstance(mid, int) else None), url
    except Exception:  # noqa: BLE001 - featured image is non-essential; never fail publish
        return None, ""


def _insert_midcontent_image(html: str, url: str, alt: str) -> str:
    """Insert a Gutenberg wp:image block right after the FIRST heading block so
    the interior post opens with a visual (the old n8n flow's mid-content
    image). No-op when there is no heading to anchor to or no URL."""
    marker = "<!-- /wp:heading -->"
    idx = html.find(marker)
    if idx == -1 or not url:
        return html
    cut = idx + len(marker)
    # Breathing room above AND below the image: never let it sit flush against a
    # heading or a CTA stack (looks broken, and keeping visual distance between
    # images and buttons is good AdSense hygiene -- no "accidental click" layout).
    spacer = ('<!-- wp:spacer {"height":"24px"} --><div style="height:24px" '
              'aria-hidden="true" class="wp-block-spacer"></div><!-- /wp:spacer -->')
    block = (
        f"\n\n{spacer}\n"
        '<!-- wp:image {"sizeSlug":"large","linkDestination":"none"} -->\n'
        f'<figure class="wp-block-image size-large"><img src="{url}" alt="{alt}"/></figure>\n'
        "<!-- /wp:image -->\n"
        f"{spacer}"
    )
    return html[:cut] + block + html[cut:]


# --- Official-page screenshots inserted after the matching link (CARD-0005) ---

# The spacer reused above/below every screenshot: never let it sit flush against
# a paragraph or a CTA stack (AdSense-safe distance from buttons), mirroring
# _insert_midcontent_image's hygiene.
_SCREENSHOT_SPACER = (
    '<!-- wp:spacer {"height":"24px"} --><div style="height:24px" '
    'aria-hidden="true" class="wp-block-spacer"></div><!-- /wp:spacer -->'
)
_BLOCK_CLOSE_RE = re.compile(r"<!--\s*/wp:[^>]*-->")


def _anchor_after_href(html: str, href: str) -> int | None:
    """Index just past the Gutenberg block that CONTAINS `href` (the official
    link a screenshot depicts), or None if the href isn't in the HTML. Anchors
    on the next block-close comment (`<!-- /wp:... -->`) after the href so the
    image lands right after the whole paragraph/buttons block, never mid-block."""
    if not href:
        return None
    pos = html.find(href)
    if pos == -1:
        return None
    m = _BLOCK_CLOSE_RE.search(html, pos)
    if m is None:
        return None
    return m.end()


def _anchor_after_second_heading(html: str) -> int | None:
    """Index just past the SECOND `<!-- /wp:heading -->` -- the fallback anchor
    used when the official href isn't found in the body. None if there aren't
    two headings (the insertion is then skipped; screenshots are best-effort)."""
    marker = "<!-- /wp:heading -->"
    first = html.find(marker)
    if first == -1:
        return None
    second = html.find(marker, first + len(marker))
    if second == -1:
        return None
    return second + len(marker)


def _link_theme(url: str) -> str:
    """Human-ish label for an official link, used in the screenshot alt text:
    its last non-empty path segment with separators turned into spaces (e.g.
    .../atualizacao-cadastral -> 'atualizacao cadastral'); the host when the URL
    carries no path."""
    parsed = urlparse(url)
    segments = [s for s in parsed.path.split("/") if s]
    if segments:
        return segments[-1].replace("-", " ").replace("_", " ")
    return parsed.netloc.lower()


def _insert_official_screenshot(html: str, image_url: str, href: str, host: str,
                                alt: str) -> str:
    """Insert a Gutenberg wp:image (with a 'Reprodução: site oficial (host)'
    figcaption) right after the block that contains `href`; fallback anchor is
    after the SECOND heading. No-op when there's no image URL or neither anchor
    is found. Spacers above/below keep AdSense-safe distance from headings and
    CTA stacks, mirroring _insert_midcontent_image."""
    if not image_url:
        return html
    cut = _anchor_after_href(html, href)
    if cut is None:
        cut = _anchor_after_second_heading(html)
    if cut is None:
        return html
    block = (
        f"\n\n{_SCREENSHOT_SPACER}\n"
        '<!-- wp:image {"sizeSlug":"large","linkDestination":"none"} -->\n'
        f'<figure class="wp-block-image size-large"><img src="{image_url}" alt="{alt}"/>'
        f'<figcaption class="wp-element-caption">Reprodução: site oficial ({host})'
        "</figcaption></figure>\n"
        "<!-- /wp:image -->\n"
        f"{_SCREENSHOT_SPACER}"
    )
    return html[:cut] + block + html[cut:]


def _embed_official_screenshots(state: RunState, page: Page, deps: Any, html: str) -> str:
    """Upload each captured official screenshot to WP media and embed it after
    the block linking to that official URL (fallback: after the 2nd heading).

    Best-effort / NON-FATAL, exactly like the featured image: a failed upload or
    insert for one shot is swallowed and never fails the publish. Returns the
    (possibly unchanged) HTML."""
    shots = state.screenshots.get(page.page_number) or []
    if not shots or not hasattr(deps.publisher, "upload_media"):
        return html
    for shot in shots:
        try:
            local = shot.get("path") or ""
            href = shot.get("url") or ""
            if not local or not Path(local).exists():
                continue
            host = urlparse(href).netloc.lower()
            alt = f"Reprodução: {host} — tela oficial de {_link_theme(href)}"
            data = Path(local).read_bytes()
            media = deps.publisher.upload_media(
                data, filename=Path(local).name, mime="image/webp", alt=alt)
            url = media.get("source_url") or media.get("guid", {}).get("rendered") or ""
            if not url:
                continue
            html = _insert_official_screenshot(html, url, href, host, alt)
        except Exception:  # noqa: BLE001 - official screenshot embed is non-essential; never fail publish
            continue
    return html


def _portao_de_publicacao(state: RunState, page: Page,
                          deps: Any) -> lp_gate.ResultadoDoPortao:
    """O portão da BARREIRA 2, rodado ANTES de qualquer upload.

    LANDING PAGE -> o portão do destino pago sobre o artefato, com carimbo REAL
    (a hora aqui é evidência de frescor, não ruído: é ela que `varrer_recibo`
    compara contra a janela).

    Páginas interiores -> `_final_content_issues` sobre o corpo já com o aviso
    reposicionado. Ele roda DE NOVO depois das decorações de mídia (é o artefato
    exato entregue ao REST); esta passagem é a que impede que uma reprovação
    determinística deixe imagem e print órfãos no site antes de ser descoberta.
    """
    if page.page_type == "LANDING PAGE":
        return _portao_da_lp(
            state, page, deps,
            carimbo_epoch=time.time(),
            carimbo=datetime.now(timezone.utc).isoformat(),
        )
    draft = state.drafts.get(page.page_number)
    conteudo = finalize_compliance_notice(draft.content) if draft else ""
    issues = _final_content_issues(state, page, deps, conteudo)
    return lp_gate.ResultadoDoPortao(pronto=not issues, issues=issues)


def _registrar_recusa_de_publicacao(state: RunState, page: Page, deps: Any,
                                    portao: lp_gate.ResultadoDoPortao) -> None:
    """Marca a recusa nos dois passos e grava o recibo em disco.

    Sem publicação não há linha de `paginas_publicadas` onde pendurar o recibo —
    e uma recusa sem rastro é indistinguível de uma publicação que ninguém
    tentou, que é justamente a dúvida que o recibo existe para não deixar
    sobrar.
    """
    numero = page.page_number
    state.step_status[f"content_gate_p{numero}"] = StepResult(
        step=f"content_gate_p{numero}", status=StepStatus.FAILED,
        attempts=1, issues=portao.issues)
    state.step_status[f"publish_p{numero}"] = StepResult(
        step=f"publish_p{numero}", status=StepStatus.FAILED, attempts=1,
        issues=[Issue(code="final_artifact_rejected",
                      message="Portão do destino pago REPROVOU o artefato final: "
                              "nada foi escrito no WordPress.")] + portao.issues)
    run_dir = getattr(getattr(deps, "runner", None), "runs_dir", None)
    if portao.recibo is None or run_dir is None:
        # Sem recibo (portão indisponível) ou sem pasta de run não há onde
        # gravar. A recusa continua registrada em `step_status`, que é o que o
        # relatório e o `_page_blocked` leem — nada fica aprovado por omissão.
        return
    lp_gate.gravar_recibo_de_recusa(Path(run_dir) / state.run_id, numero, portao.recibo)


def step_publish(state: RunState, page: Page, deps: Any) -> None:
    """Publish the page via `deps.publisher`. No-op if publisher is None --
    callers should only invoke this when `publish=True` AND a publisher was
    injected.

    Status comes from `settings.run.publish_status` (default "draft"), so the
    funnel lands in WordPress as reviewable drafts unless explicitly set to
    "publish"."""
    if deps.publisher is None:
        return
    draft = state.drafts.get(page.page_number)
    if draft is None:
        return

    # ── O PORTÃO, ACIMA DE QUALQUER ESCRITA NO SITE ───────────────────────
    #
    # Ele é a PRIMEIRA instrução do passo, antes de `_upload_hero_and_rewrite`,
    # `_upload_featured` e `_embed_official_screenshots`. Até aqui
    # `_final_content_issues` rodava DEPOIS de três `upload_media`: uma página
    # recusada já tinha deixado mídia órfã no site ao vivo, e "zero publicação
    # parcial" é incompatível com isso.
    portao = _portao_de_publicacao(state, page, deps)
    if not portao.pronto:
        _registrar_recusa_de_publicacao(state, page, deps, portao)
        return

    seo = state.seo.get(page.page_number, {})
    status = deps.settings.run.publish_status

    # WP title uses the CALM copy, never the raw briefing h1 (which can carry
    # fear/officialidade like "Liberado pelo Governo"): the LP uses its own
    # article_title; interior posts use the SEO title.
    if page.page_type == "LANDING PAGE":
        run_dir = deps.runner.runs_dir / state.run_id
        elementor = json.loads((run_dir / "p1.elementor.json").read_text(encoding="utf-8"))
        _upload_hero_and_rewrite(state, page, deps, elementor)
        page_settings = {}
        ps_path = run_dir / "p1.page_settings.json"
        if ps_path.exists():
            try:
                page_settings = json.loads(ps_path.read_text(encoding="utf-8"))
            except (ValueError, json.JSONDecodeError):
                page_settings = {}
        try:
            lp_title = json.loads(draft.content).get("article_title") or page.h1_title
        except (ValueError, json.JSONDecodeError, TypeError):
            lp_title = page.h1_title
        result = deps.publisher.create_elementor_page(
            title=lp_title, slug=page.slug, elementor=elementor, status=status,
            post_type=deps.settings.site.lp_post_type,
            page_settings=page_settings,
        )
    else:
        # Featured image for interior /rec posts (n8n-style): upload the
        # generated webp, set it as the thumbnail (featured_media) AND drop a
        # mid-content copy after the first heading. All best-effort: alt reuses
        # the SEO fields already computed (no extra LLM call), and a missing
        # image just leaves the post text-only.
        alt = seo.get("keywordfocus") or seo.get("seotitle") or page.h1_title
        featured_media, media_url = _upload_featured(state, page, deps, alt)
        # Publish-time decorations (not in the draft that uniqueness compares):
        # move the compliance aviso to a discreet footnote at the end, then drop
        # the mid-content image after the first heading.
        content = finalize_compliance_notice(draft.content)
        content = _insert_midcontent_image(content, media_url, alt)
        # Official-page screenshots (CARD-0005): upload each capture and embed
        # it after the paragraph that links to that official URL. Best-effort/
        # non-fatal -- a missing or failed screenshot just leaves the text as-is.
        content = _embed_official_screenshots(state, page, deps, content)
        # Re-run against the EXACT artifact handed to REST.  Publish-time image,
        # screenshot and compliance transforms occur after step_content_gate;
        # none of them gets an unvalidated path to WordPress.
        final_issues = _final_content_issues(state, page, deps, content)
        if final_issues:
            state.step_status[f"content_gate_p{page.page_number}"] = StepResult(
                step=f"content_gate_p{page.page_number}", status=StepStatus.FAILED,
                attempts=1, issues=final_issues)
            state.step_status[f"publish_p{page.page_number}"] = StepResult(
                step=f"publish_p{page.page_number}", status=StepStatus.FAILED,
                attempts=1,
                issues=[Issue(code="final_artifact_rejected",
                              message="Artefato final pós-decorações reprovado.")]
                       + final_issues)
            return
        result = deps.publisher.create_post(
            title=seo.get("seotitle") or page.h1_title,
            content=content,
            slug=page.slug,
            status=status,
            post_type=deps.settings.site.post_type,
            featured_media=featured_media,
        )

    # Yoast SEO title / meta description / focus keyword. Interior posts use
    # `post_type` (rec); the Elementor LP uses `lp_post_type` (r) -- both have
    # the Yoast meta registered for REST (see docs/yoast-rest-meta.php), without
    # which the write is a SILENT no-op. set_yoast skips empty fields.
    post_id = result.get("id") or result.get("post_id")
    # O ELO COM A CAMPANHA nasce aqui. Guarda o que o WordPress DEVOLVEU, não o
    # que a gente supunha: `slug` e `link` verbatim. Ver `RunState.published`
    # para por que remontar a URL a partir do slug é errado.
    state.published[page.page_number] = {
        "page_number": page.page_number,
        "role": effective_role(page).value,
        "post_type": (deps.settings.site.lp_post_type
                      if page.page_type == "LANDING PAGE"
                      else deps.settings.site.post_type),
        "post_id": post_id,
        "slug": result.get("slug") or page.slug,
        "url_wp": result.get("link") or "",
        "status_wp": status,
        "publicado_em": datetime.now(timezone.utc).isoformat(),
    }
    # ── O RECIBO DA APROVAÇÃO, DENTRO DO REGISTRO DA PUBLICAÇÃO ───────────
    #
    # É o lado esquerdo que não existia da comparação de deriva: `sha256_aprovado`
    # não era gravado por nada fora dos testes, então `DERIVA_AO_VIVO` saiu
    # `unavailable` nos cinco recibos preservados. Sem migration e sem tabela
    # nova: `worker.resumo_do_estado` leva `state.published` verbatim para
    # `pautador_funnel_runs.paginas_publicadas`, que já existe.
    #
    # ⚠️ A impressão gravada é a do ARTEFATO que este motor produziu (o corpo),
    # não a do HTML que o tema renderiza em volta dele. Quem ligar o portão 3
    # precisa saber disso antes de usá-la como `impressao_aprovada` de uma
    # leitura ao vivo — comparar as duas formas acusaria deriva em toda página.
    # O recibo diz de qual ponto de portão ele veio (`gate_point`), que é o que
    # torna essa diferença auditável em vez de silenciosa.
    if portao.recibo is not None:
        state.published[page.page_number] = lp_gate.anexar_recibo(
            state.published[page.page_number], portao.recibo)
    yoast_pt = (deps.settings.site.lp_post_type
                if page.page_type == "LANDING PAGE"
                else deps.settings.site.post_type)
    if post_id and seo:
        deps.publisher.set_yoast(
            post_id=post_id,
            post_type=yoast_pt,
            fields={
                "title": seo.get("seotitle", ""),
                "metadesc": seo.get("metadescription", ""),
                "focuskw": seo.get("keywordfocus", ""),
            },
            status=status,
        )
    # FINAL status pin (last write wins): registered-meta writes above
    # (Elementor / Yoast) can flip a draft to publish on this site, so assert
    # the intended status explicitly at the very end -- guarantees the funnel
    # lands as drafts regardless of any meta side effect.
    if post_id and hasattr(deps.publisher, "set_status"):
        deps.publisher.set_status(post_id=post_id, post_type=yoast_pt, status=status)

    # Cross-run anti-boilerplate (CARD-0007): record the PRESELL opening CTA
    # line only NOW -- after publish has actually succeeded -- so a retried or
    # discarded draft never pollutes the registry other funnels compare
    # against. Best-effort: a registry write failure must never fail publish.
    if effective_role(page) is PageRole.PRESELL:
        try:
            opening_line = presell_opening_line(draft.content)
            if opening_line:
                record_phrase(_phrase_registry_path(deps), "presell_opening",
                              opening_line, page.slug, state.run_id)
        except Exception:  # noqa: BLE001 - registry write is best-effort, never fails publish
            pass

    state.step_status[f"publish_p{page.page_number}"] = StepResult(
        step=f"publish_p{page.page_number}", status=StepStatus.OK, attempts=1
    )


# ===========================================================================
# O PASSO DECLARADOR — quem preenche `Page.engajamento`
#
# O `extractor` é um MAPEADOR FIEL de propósito: ele transcreve campos do
# briefing ("o valor do campo Slug", "o texto após Objetivo da página"). Pôr
# um julgamento ali quebraria a única propriedade que o torna confiável. Por
# isso a declaração tem passo próprio, logo depois do extract -- o mesmo lugar
# de `expand_presell_hubs`.
#
# PRECEDÊNCIA: quem já veio preenchido do briefing VENCE. O passo só completa
# lacunas, nunca sobrescreve uma declaração humana.
#
# FAIL-SAFE: qualquer problema -- LLM falhou, JSON inválido, rótulo fora do
# vocabulário -- usa a inferência semântica determinística de H1/objetivo/
# estrutura. O classificador nunca derruba o funil e nunca cai em sorteio.
# ===========================================================================

ENGAJAMENTO_VOCABULARIO: frozenset[str] = frozenset(ENGAJAMENTO_PARA_ARQUETIPO)


def declarar_engajamento(state: RunState, deps: Any) -> None:
    """Classifica a FORMA DA PERGUNTA de cada SOLUÇÃO, preenchendo
    `page.engajamento`. Ver `ENGAJAMENTO_PARA_ARQUETIPO` para o efeito."""
    plan = state.plan
    if plan is None:
        return
    alvo = [p for p in plan.pages
            if effective_role(p) is PageRole.SOLUTION and not (p.engajamento or "").strip()]
    if not alvo:
        return                       # tudo já declarado no briefing: nada a fazer
    cfg = deps.settings.steps.get("engajamento")
    if cfg is None:
        return                       # widget usa infer_engajamento quando precisar

    key = "engajamento"
    try:
        prompt = render("declarador_engajamento", country="Brasil", pages=alvo)
        text, res = deps.runner.run_llm_step(
            key, cfg, [{"role": "user", "content": prompt}], ctx={}, run_id=state.run_id)
        if res.status is StepStatus.FAILED or not (text or "").strip():
            for p in alvo:
                p.engajamento = infer_engajamento(p)
            state.step_status[key] = StepResult(
                step=key, status=StepStatus.FALLBACK,
                issues=[Issue(code="engajamento_llm_error",
                              message="Declaração falhou; aplicada inferência semântica.")],
                model_used=res.model_used, attempts=res.attempts,
                prompt_tokens=res.prompt_tokens, completion_tokens=res.completion_tokens,
                cost_usd=res.cost_usd, latency_ms=res.latency_ms)
            return

        dados = _tolerant_json(text)
        por_slug = {str(d.get("slug", "")): d for d in (dados.get("paginas") or [])}
        aplicados, recusados = 0, []
        for p in alvo:
            d = por_slug.get(p.slug) or {}
            # Canonizado: o declarador escrever `Dado Único` ou `diagnóstico`
            # é grafia, não rótulo inválido -- e recusar por causa de um til
            # jogava fora justamente o rótulo que manda NÃO gerar widget.
            rotulo = canon_engajamento(d.get("engajamento", ""))
            if rotulo in ENGAJAMENTO_VOCABULARIO:
                p.engajamento = rotulo
                aplicados += 1
            else:
                p.engajamento = infer_engajamento(p)
                aplicados += 1
                if rotulo:
                    recusados.append(f"{p.slug}:{rotulo}")

        issues = [Issue(code="engajamento_fora_do_vocabulario",
                        message=f"Rótulos recusados: {', '.join(recusados)}.")] if recusados else []
        # A telemetria vem do `res` — este passo chama o LLM como qualquer
        # outro e sempre gravou zero, some do ledger e da régua de custo.
        state.step_status[key] = StepResult(
            step=key,
            status=StepStatus.OK if aplicados else StepStatus.SKIPPED,
            issues=issues,
            model_used=res.model_used, attempts=res.attempts,
            prompt_tokens=res.prompt_tokens, completion_tokens=res.completion_tokens,
            cost_usd=res.cost_usd, latency_ms=res.latency_ms)
    except Exception as exc:                                  # noqa: BLE001
        for p in alvo:
            p.engajamento = infer_engajamento(p)
        state.step_status[key] = StepResult(
            step=key, status=StepStatus.FALLBACK,
            issues=[Issue(code="engajamento_error", message=str(exc)[:200])])
