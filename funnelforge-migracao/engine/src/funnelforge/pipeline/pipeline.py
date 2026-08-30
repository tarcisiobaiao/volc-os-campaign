# funnel-forge/src/funnelforge/pipeline/pipeline.py
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from funnelforge.config.settings import Settings
from funnelforge.domain.models import (
    FunnelPlan,
    Issue,
    Page,
    PageRole,
    RunState,
    StepResult,
    StepStatus,
    effective_role,
)
from funnelforge.pipeline import steps as st
from funnelforge.pipeline.budget import OrcamentoEstourado
from funnelforge.pipeline.routing import (
    build_funnel_routes,
    reachable_slugs,
    validate_funnel_graph,
)
from funnelforge.pipeline.runner import LLMStepError, Runner
from funnelforge.ports.llm import LLMClient
from funnelforge.ports.services import (
    BriefingLoader,
    ImageGenerator,
    ImageProcessor,
    Publisher,
    ResearchProvider,
    ScreenshotProvider,
    SitemapProvider,
    UrlVerifier,
)


@dataclass
class Deps:
    """Bundles every injected port the pipeline needs. Any of `research`,
    `image_gen`, `image_proc`, `publisher` may be None -- the corresponding
    steps then no-op the network-bound parts (see steps.py docstrings) so a
    dry run works with only `llm`, `loader`, `settings` and `runner`."""

    llm: LLMClient
    research: ResearchProvider | None
    image_gen: ImageGenerator | None
    image_proc: ImageProcessor | None
    publisher: Publisher | None
    loader: BriefingLoader
    settings: Settings
    runner: Runner
    sitemap: SitemapProvider | None = None
    # Optional Playwright/Chromium adapter for official-page screenshots
    # (CARD-0005). None when the feature flag is off OR playwright isn't
    # installed (see cli.build_deps) -- step_screenshot then no-ops.
    #
    # ESCOPO: só screenshot. A verificação "essa URL existe?" saiu daqui e virou
    # `url_verifier` -- era o que fazia `official_screenshots`, uma flag
    # cosmética, decidir se uma página com fato numérico passava ou não.
    screenshot: ScreenshotProvider | None = None
    # Verificador de URL ao vivo (`UrlVerifier`): HTTP puro, sem browser, SEMPRE
    # ligado em `cli.build_deps`. É quem sustenta o gate factual
    # (`_gate_research`) e os links de plataforma (`_write_ctx`). None só em
    # teste/dry-run -- e aí o gate factual reprova fato crítico por falta de
    # verificador, que é o fail-closed desejado.
    url_verifier: UrlVerifier | None = None
    # Termos que identificam ESTA pauta, vindos do perfil do run
    # (`config/perfil.py`). Entram no tema que o sitemap usa para decidir o que
    # é "a mesma pauta com outro título" na hora de escolher a saída
    # cross-funnel. Vazio é o normal: o motor então usa só o H1 da LP e as
    # keywords que a ponte trouxe do card.
    tema_termos: list[str] = field(default_factory=list)


def _falhou(state: RunState, key: str) -> bool:
    """O passo existe e terminou em FAILED. Ausente NÃO conta como falha —
    um passo que ainda não rodou é pendente, não condenado."""
    r = state.step_status.get(key)
    return r is not None and r.status is StepStatus.FAILED


def _select_pages(state: RunState, only: str | None) -> list[Page]:
    pages = state.plan.pages if state.plan else []
    if not only:
        return list(pages)
    if only == "p1":
        return [p for p in pages if p.page_type == "LANDING PAGE" or p.page_number == 1]
    # Single page by SLUG or by "pN" page-number label (e.g. regenerate one
    # SOLUTION in place, keeping its slug so the rest of the funnel's links to it
    # stay intact). No match -> empty (process nothing), never a silent full run.
    return [p for p in pages if p.slug == only or f"p{p.page_number}" == only]


def _checkpoint(state: RunState, deps: Deps) -> None:
    deps.runner.checkpoint(state.run_id, state.to_json())


def _populate_routes(state: RunState, deps: Deps) -> None:
    """Recompute `page.routes` on the FINAL plan (post-expansion/dedupe) via
    the existing deterministic `build_funnel_routes` builder.

    `step_extract` already ran the SAME builder once, on the faithfully
    mapped (pre-expansion) plan -- but `expand_presell_hubs` REPLACES the
    single mapped PRESELL with 3 brand-new NEUTRAL hub `Page` objects
    (`-pr1/2/3`), which start with empty `.routes`. Without this, their write
    step's `pagespec` validator fails closed on every retry (`cta_too_few` --
    genuinely no CTAs to write), and re-running the redator prompt with
    corrective feedback can never fix an EMPTY routes list. Re-running the
    builder here gives every page (including the new hubs) real, resolvable
    routes again -- and applies the NEUTRAL fan-out rotation per `-prN` index.

    RE-VALIDATES the FINAL graph: `step_extract` validated the throwaway
    1-presell plan, but the LP now fans out to all 3 hubs
    (`build_funnel_routes`'s LP branch), so a good funnel passes here. A
    broken FINAL graph (an orphan solution, a terminal with no cross-funnel
    exit) is caught NOW and fails `funnel_graph` closed on the graph that
    actually ships -- delivering the fail-closed guarantee on the real plan,
    not the pre-expansion stand-in."""
    plan = state.plan
    if plan is None or not plan.pages:
        return
    cross_targets = None
    if deps.sitemap is not None:
        try:
            lp = next((p for p in plan.pages if effective_role(p) is PageRole.LP), None)
            theme = lp.h1_title if lp else plan.pages[0].h1_title
            cross_targets = deps.sitemap.cross_funnel_targets(
                theme=theme, exclude_slugs=[p.slug for p in plan.pages])
        except Exception:  # noqa: BLE001 - sitemap is best-effort, never fatal
            cross_targets = None
    try:
        build_funnel_routes(plan, deps.settings, cross_funnel_targets=cross_targets)
        graph_issues = validate_funnel_graph(plan, deps.settings)
    except ValueError as exc:
        # Página sem rota válida (slug vazio, cross-funnel fora do domínio) é
        # falha de grafo: reprova fechado, como qualquer outro problema de
        # conteúdo -- e nunca aborta o run. O canal oficial NÃO entra nesta
        # conta: ele é ligado depois da pesquisa (bind_official_route).
        graph_issues = [Issue(code="bare_rec", message=str(exc))]
    if graph_issues:
        state.step_status["funnel_graph"] = StepResult(
            step="funnel_graph", status=StepStatus.FAILED, issues=graph_issues)


def run_pipeline(
    briefing_path: Path | None,
    deps: Deps,
    only: str | None = None,
    publish: bool = False,
    resume_state: RunState | None = None,
    timestamp: str = "",
    plan: FunnelPlan | None = None,
) -> RunState:
    """Run the funnel pipeline end to end: load briefing -> extract plan ->
    per page (research -> write -> judge -> seo -> [image for P1] -> build
    -> [publish]) -> report.md.

    `only="p1"` restricts processing to the landing page. A failure on one
    page is caught and recorded as FAILED in step_status; it does not abort
    the other pages.

    `resume_state`, when given, is reused as the starting RunState (Task 13
    resume support): steps already OK/RETRIED/FALLBACK in its step_status
    are skipped and their prior outputs (plan/drafts/seo/facts/images) are
    kept as-is. `briefing_path` may then be `None` -- the briefing text was
    already captured on `resume_state.briefing_text` by the original run, so
    it is not re-read from disk (the CLI's `resume` command has no briefing
    path at hand, only a `run_id`).

    `plan`, quando dado, é um FunnelPlan JÁ PRONTO — a PONTE VOLC: o
    `funnel_architecture` do card do Pautador convertido por
    `adapters/briefing_volc.py`. Ele entra no lugar do `step_extract` (que
    no-opa sozinho, porque `state.plan` deixa de ser None) e por isso o run
    não gasta nenhuma chamada de LLM para reconstruir de texto um objeto que
    o sistema já tem inteiro. `briefing_path` é `None` neste caminho: não
    existe briefing em texto.

    IMPORTANTE, e é a diferença que este parâmetro existe para marcar: um
    plano injetado é NOVO, não é um plano retomado. Ele PRECISA passar pelos
    quatro passos de normalização abaixo. Um `resume_state`, ao contrário,
    traz um plano que JÁ foi normalizado no run original e não pode ser
    normalizado de novo. Os dois casos chegam aqui com `state.plan`
    preenchido — só este parâmetro os distingue.
    """
    state = resume_state if resume_state is not None else RunState(
        run_id=f"_pending-{timestamp}")
    if briefing_path is not None:
        state.briefing_text = deps.loader.load(Path(briefing_path))

    # PLANO INJETADO (ponte VOLC). Só entra num state que ainda NÃO tem plano,
    # para que um `resume` jamais seja sobrescrito por engano.
    _plano_injetado = plan is not None and state.plan is None
    if _plano_injetado:
        state.plan = plan

    # `step_extract` no-ops when `state.plan` is already populated (the resume
    # path -- see its docstring): the plan was already expanded/routed on the
    # original run, so expand_presell_hubs/dedupe/route-repopulation must NOT
    # run again on a resumed, hand-built (often minimal, LP-less) test/prod
    # RunState. Guard on the SAME condition step_extract itself checks.
    #
    # ARMADILHA — a razão do `or _plano_injetado`: `_fresh_extract` é avaliado
    # ANTES de `step_extract`, então um plano pré-populado cairia no ramo do
    # resume e PULARIA os quatro passos. Sem `_populate_routes`, toda página
    # fica com `routes=[]`; o validador `pagespec` reprova toda tentativa de
    # escrita com `cta_too_few` (não há CTA a escrever, e nenhum retorno com
    # feedback corretivo conserta uma lista VAZIA de rotas); e o grafo do
    # funil não é validado nenhuma vez.
    _fresh_extract = state.plan is None or _plano_injetado
    st.step_extract(state, deps)
    if _fresh_extract:
        try:
            st.expand_presell_hubs(state, deps)
        except ValueError as exc:
            # Fail-closed (<3 solutions -> the honest multi-route hub graph is
            # impossible). The mechanical expansion makes NO LLM call, so there
            # is no paid telemetry to preserve -- just record the failure.
            state.step_status["expand_presell_hubs"] = StepResult(
                step="expand_presell_hubs", status=StepStatus.FAILED,
                issues=[Issue(code="expand_error", message=str(exc))])
        st.dedupe_slugs(state.plan)
        # Classifica a FORMA DA PERGUNTA de cada solução -> `page.engajamento`,
        # que decide qual ferramenta interativa a página recebe. Roda aqui
        # porque precisa do plano já expandido e com slugs finais, e antes do
        # checkpoint, para que um resume não reclassifique. 100% fail-safe:
        # qualquer problema usa inferência semântica sobre H1/estrutura.
        st.declarar_engajamento(state, deps)
        _populate_routes(state, deps)

    if state.run_id.startswith("_pending") and state.plan and state.plan.pages:
        old = state.run_id
        state.run_id = f"{state.plan.pages[0].slug}-{timestamp}"
        deps.runner.finalize_run_id(old, state.run_id)
    _checkpoint(state, deps)

    pages = _select_pages(state, only)

    # PORTÃO DE GRAFO ANTES DE QUALQUER GASTO (Frente 3).
    # `_page_blocked` já bloqueia build/publish quando `funnel_graph` falhou —
    # mas só era consultado DEPOIS de pesquisa + redação + juiz + seo + imagem
    # de TODAS as páginas. Num funil de 5 páginas isso é o funil inteiro
    # (~US$ 2,10 medidos) pago para produzir zero URL publicada. O grafo é
    # determinístico e já está decidido aqui: marca tudo como bloqueado,
    # escreve o relatório com o motivo e para. Nada de "descobrir no fim".
    graph_res = state.step_status.get("funnel_graph")
    if graph_res is not None and graph_res.status is StepStatus.FAILED:
        for page in pages:
            state.step_status[f"blocked_p{page.page_number}"] = StepResult(
                step=f"blocked_p{page.page_number}", status=StepStatus.FAILED,
                issues=[Issue(
                    code="fail_closed",
                    message="funnel_graph FAILED — funil abortado ANTES de "
                            "pesquisa/redação: nenhuma página seria publicada.")])
        _write_report(state, deps)
        _checkpoint(state, deps)
        return state

    orcamento = getattr(deps.runner, "budget", None)

    for page in pages:
        # Zera o contador da PÁGINA: o teto por página existe para que uma
        # página patológica não coma o orçamento das outras.
        if orcamento is not None:
            orcamento.entrar_na_pagina(f"p{page.page_number}")
        try:
            if not _done(state, f"research_p{page.page_number}"):
                st.step_research(state, page, deps)
                # Escolhe, UMA VEZ e com browser, quais URLs externas esta
                # página pode usar (proveniência + verificação ao vivo + sonda
                # anti-anúncio) -> state.official_links. Redator, gate final e
                # screenshot leem daí, então os três nunca discordam do canal.
                st.registrar_canais_oficiais(state, page, deps)
                _checkpoint(state, deps)

            if not _done(state, f"write_p{page.page_number}"):
                st.step_write(state, page, deps)
                st.uniqueness_state_guard(state, page, deps)
                # CARD-0009: structural-distinction net across the 3 presell
                # hubs (materially-identical body or non-neutral hero -> write
                # fails). No-op for non-presell pages.
                st.presell_hub_distinction_guard(state, page, deps)
                _checkpoint(state, deps)

            # ── PÁGINA CONDENADA NÃO GASTA MAIS ───────────────────────
            #
            # Se a redação falhou, esta página não vai existir: o gate final e
            # o `_page_blocked` já garantem que build e publish são pulados.
            # Mas SEO, prompt de imagem e a geração da imagem continuavam
            # rodando e cobrando por um artigo que ninguém vai ler.
            #
            # Medido no primeiro run real (17/08/2026): a p1 morreu no
            # `research_p1` e mesmo assim gastou US$ 0,0018 de seo + US$ 0,0028
            # de prompt de imagem + US$ 0,0422 de geração — US$ 0,047 numa
            # página já condenada, 2,3% do custo de um funil.
            #
            # `continue` e não `break`: as outras páginas seguem normalmente.
            # Uma página morta não derruba o funil — isso é desenho antigo e
            # continua valendo.
            if _falhou(state, f"write_p{page.page_number}"):
                # ⚠️ MARCA ANTES DE SAIR. A primeira versão deste atalho só
                # dava `continue`, e a página ficava condenada SEM o
                # `blocked_pN` — que é o marcador que o gate, o relatório e a
                # tela usam para saber que ela não existe. Pular o gasto e
                # perder a marcação seria trocar um defeito de US$ 0,047 por
                # um defeito de estado, que é bem pior.
                state.step_status[f"blocked_p{page.page_number}"] = StepResult(
                    step=f"blocked_p{page.page_number}", status=StepStatus.FAILED,
                    issues=[Issue(
                        code="fail_closed",
                        message="write FAILED — seo/imagem/build/publish pulados "
                                "para não gastar em página condenada")])
                _checkpoint(state, deps)
                continue

            if not _done(state, f"seo_p{page.page_number}"):
                st.step_seo(state, page, deps)
                _checkpoint(state, deps)

            # LP always crafts its hero prompt (generation still gated on
            # run.hero_image inside step_image); interior /rec posts run the
            # image step only when run.featured_image is on. `image_wanted`
            # inside step_image is the single source of the generate/skip
            # decision, so the two never disagree.
            _wants_image = page.page_type == "LANDING PAGE" or getattr(
                deps.settings.run, "featured_image", False)
            if _wants_image and not _done(state, f"image_p{page.page_number}"):
                st.step_image(state, page, deps)
                _checkpoint(state, deps)

            # Official-page screenshots (CARD-0005): only when a provider is
            # wired (flag on + playwright installed). NON-blocking -- like
            # step_image, any failure is swallowed inside step_screenshot and
            # `_page_blocked` deliberately ignores it, so a good page always
            # builds/publishes.
            if deps.screenshot is not None and not _done(
                state, f"screenshot_p{page.page_number}"
            ):
                st.step_screenshot(state, page, deps)
                _checkpoint(state, deps)

            if _page_blocked(state, page, antes_do_build=True):
                state.step_status[f"blocked_p{page.page_number}"] = StepResult(
                    step=f"blocked_p{page.page_number}", status=StepStatus.FAILED,
                    issues=[Issue(
                        code="fail_closed",
                        message="write/judge FAILED or funnel_graph FAILED — "
                                "build & publish skipped")])
                _checkpoint(state, deps)
                continue

            if not _done(state, f"build_p{page.page_number}"):
                st.step_build(state, page, deps)
                _checkpoint(state, deps)

            # Interactive SOLUTION widget (CARD-0013): AFTER build (final,
            # normalized draft), BEFORE publish. Gated on run.widgets_enabled so
            # the step is never even called when off -> flag-off runs are
            # byte-for-byte the current pipeline. A falha fica SKIPPED no passo,
            # mas o content_gate abaixo bloqueia a publicação quando a página
            # semanticamente exige um widget.
            if getattr(deps.settings.run, "widgets_enabled", False) and not _done(
                state, f"widget_p{page.page_number}"
            ):
                st.step_widget(state, page, deps)
                _checkpoint(state, deps)

            # Validate the exact post-normalize/post-widget draft.  This gate is
            # deterministic and cannot be disabled by an empty step validator
            # list; if it fails, REST publication is skipped.
            if not _done(state, f"content_gate_p{page.page_number}"):
                st.step_content_gate(state, page, deps)
                _checkpoint(state, deps)

            if _page_blocked(state, page):
                state.step_status[f"blocked_p{page.page_number}"] = StepResult(
                    step=f"blocked_p{page.page_number}", status=StepStatus.FAILED,
                    issues=[Issue(
                        code="fail_closed",
                        message="Gate factual/editorial final FAILED — publish pulado")])
                _checkpoint(state, deps)
                continue

            # ⚠️ A condenação ANTIGA tem de sair do estado quando a página passa.
            #
            # `blocked_pN` só era escrito, nunca apagado. Depois da retomada de
            # 19/08/2026 a p3 estava com `widget_p3: OK` e `content_gate_p3: OK`
            # — e ainda carregava `blocked_p3: FAILED` da rodada anterior. O
            # relatório lê o estado e diria "bloqueada" sobre uma página pronta
            # para publicar. Estado que guarda veredito vencido mente para quem
            # o lê depois, e é a partir dele que o operador decide.
            state.step_status.pop(f"blocked_p{page.page_number}", None)

            if publish and deps.publisher is not None and not _done(
                state, f"publish_p{page.page_number}"
            ):
                st.step_publish(state, page, deps)
                _checkpoint(state, deps)
        except OrcamentoEstourado as exc:
            # Teto de custo. Aborta com mensagem clara em vez de continuar
            # gastando: se o teto do RUN acabou, as próximas páginas gastariam
            # para bater na mesma parede -> encerra o laço e escreve o relatório.
            key = f"budget_p{page.page_number}"
            state.step_status[key] = StepResult(
                step=key, status=StepStatus.FAILED,
                issues=[Issue(code="orcamento_estourado", message=str(exc))])
            _checkpoint(state, deps)
            if exc.escopo == "run":
                break
            continue
        except LLMStepError as exc:
            # Falha definitiva de um passo de LLM. O custo das tentativas que
            # morreram viaja na exceção e é PRESERVADO no ledger -- antes ele
            # sumia junto com o traceback e o relatório mentia para menos.
            key = f"page_{page.page_number}"
            pago = exc.step_result
            state.step_status[key] = StepResult(
                step=key,
                status=StepStatus.FAILED,
                attempts=pago.attempts,
                issues=[Issue(code="exception", message=str(exc))],
                prompt_tokens=pago.prompt_tokens,
                completion_tokens=pago.completion_tokens,
                cost_usd=pago.cost_usd,
                latency_ms=pago.latency_ms,
            )
            _checkpoint(state, deps)
            continue
        except Exception as exc:  # noqa: BLE001 - one page's failure must not abort the rest
            key = f"page_{page.page_number}"
            state.step_status[key] = StepResult(
                step=key,
                status=StepStatus.FAILED,
                issues=[Issue(code="exception", message=str(exc))],
            )
            _checkpoint(state, deps)
            continue

    _write_report(state, deps)
    _checkpoint(state, deps)
    return state


def _done(state: RunState, key: str) -> bool:
    res = state.step_status.get(key)
    return res is not None and res.status in (
        StepStatus.OK,
        StepStatus.RETRIED,
        StepStatus.FALLBACK,
    )


def _page_blocked(state: RunState, page: Page, *, antes_do_build: bool = False) -> bool:
    """True if the page's existential steps FAILED, OR the funnel's routing
    graph itself is structurally broken -> no build/publish.

    ⚠️ `antes_do_build=True` TIRA o `content_gate` da conta, e sem isso a
    retomada de uma página condenada é IMPOSSÍVEL.

    Medido em 19/08/2026, run 9, páginas 3 e 4: o `content_gate` reprovou por
    `required_widget_missing`. Na retomada, esta função era consultada ANTES do
    build, via um `content_gate` reprovado que ainda estava no estado — dava
    True, o laço fazia `continue`, e o widget (o passo que apagaria justamente
    aquela reprovação) nunca rodava. O comando saía com status 0 e não escrevia
    nada: `state.json` ficava byte a byte igual.

    Era um nó cego. A reprovação do portão trancava a porta do conserto do que
    o portão reprovou, e duas páginas prontas — 10.922 e 13.201 caracteres de
    artigo pesquisado, escrito, julgado, com SEO e imagem — ficavam presas sem
    caminho de volta.

    O `content_gate` continua valendo na segunda consulta, logo depois de ele
    ter rodado de novo (é lá que ele decide publicação). O que não pode é ele
    julgar antes de existir na rodada atual.

    Task 12/T1B fail-closed gate: `step_extract` writes
    `state.step_status["funnel_graph"] = FAILED` when `validate_funnel_graph`
    finds an unreachable page or a terminal SOLUTION with no cross-funnel
    exit (see steps.py/routing.py). That check used to be purely advisory --
    recorded in the report but never enforced -- so a structurally broken
    funnel would still build and publish every page. `funnel_graph` is a
    run-level (not per-page) status, so when it is FAILED this returns True
    for every page, which makes the existing gate below skip build+publish
    funnel-wide (the report still records `funnel_graph: FAILED` with its
    issues as the reason, since that step_status entry is untouched)."""
    graph_res = state.step_status.get("funnel_graph")
    if graph_res is not None and graph_res.status is StepStatus.FAILED:
        return True
    chaves = [
        f"research_p{page.page_number}",
        f"write_p{page.page_number}",
        f"judge_p{page.page_number}",
    ]
    if not antes_do_build:
        chaves.append(f"content_gate_p{page.page_number}")
    for key in chaves:
        res = state.step_status.get(key)
        if res is not None and res.status is StepStatus.FAILED:
            return True
    return False


def _pv_per_session(plan: FunnelPlan | None) -> int:
    """Expected page views per session = number of pages reachable from the
    LP entry via the SAME `page.routes` funnel graph `build_funnel_routes`
    assigns and `validate_funnel_graph` walks (see `routing.reachable_slugs`).

    T2H fix: this used to walk `next_page_slug` -- a separate, LLM-authored
    field that only encodes a single forward hop and can drift from the
    actual routed graph (e.g. a SOLUTION ring where every page also links to
    its neighbours) -- which could undercount pv/session relative to the
    funnel that actually ships. Deterministic: same BFS, no randomness."""
    if not plan or not plan.pages:
        return 0
    return len(reachable_slugs(plan))


_PAGE_SUFFIX_RE = re.compile(r"_p(\d+)$")


def _step_kind_and_page(key: str) -> tuple[str, int | None]:
    """Quebra `write_p3` em ("write", 3); `extract` em ("extract", None).

    É o que permite ler o custo por TIPO de passo e por PÁGINA sem inventar
    nomenclatura nova: as chaves do `step_status` já carregam as duas
    informações desde sempre."""
    match = _PAGE_SUFFIX_RE.search(key)
    if not match:
        return key, None
    return key[: match.start()], int(match.group(1))


def _profit_ledger(state: RunState, orcamento=None) -> dict:
    """Aggregate F5 per-step telemetry into a COGS ledger + pv-per-session.

    Além do total, entrega o que o operador de arbitragem precisa LER: quanto
    por página, quanto por TIPO de passo (é aqui que a geração de imagem
    finalmente aparece, como `image_gen`), e quanto foi para páginas
    REPROVADAS -- dinheiro que já saiu e não vira sessão nenhuma. "Reprovada"
    é a definição que o próprio pipeline grava: existe `blocked_p{n}` no
    `step_status`."""
    per_step = []
    cost = 0.0
    pt = ct = 0
    per_page: dict[int, dict] = {}
    per_kind: dict[str, dict] = {}
    for key, res in state.step_status.items():
        cost += res.cost_usd
        pt += res.prompt_tokens
        ct += res.completion_tokens
        per_step.append((key, res.prompt_tokens, res.completion_tokens,
                         res.cost_usd, res.latency_ms))
        kind, page_number = _step_kind_and_page(key)
        bucket = per_kind.setdefault(kind, {"cost_usd": 0.0, "prompt_tokens": 0,
                                            "completion_tokens": 0, "calls": 0})
        bucket["cost_usd"] += res.cost_usd
        bucket["prompt_tokens"] += res.prompt_tokens
        bucket["completion_tokens"] += res.completion_tokens
        bucket["calls"] += 1
        if page_number is None:
            continue
        page_bucket = per_page.setdefault(
            page_number, {"cost_usd": 0.0, "prompt_tokens": 0,
                          "completion_tokens": 0, "blocked": False,
                          "published": False})
        page_bucket["cost_usd"] += res.cost_usd
        page_bucket["prompt_tokens"] += res.prompt_tokens
        page_bucket["completion_tokens"] += res.completion_tokens
        if kind == "blocked":
            page_bucket["blocked"] = True
        if kind == "publish" and res.status in (
                StepStatus.OK, StepStatus.RETRIED, StepStatus.FALLBACK):
            page_bucket["published"] = True

    # Arredonda cada balde ANTES de somar: sem isso, 0.10 + 0.05 vira
    # 0.15000000000000002 no relatório -- ruído de float que só atrapalha quem
    # lê.
    for bucket in (*per_page.values(), *per_kind.values()):
        bucket["cost_usd"] = round(bucket["cost_usd"], 6)

    wasted = sum(b["cost_usd"] for b in per_page.values() if b["blocked"])
    uteis = sum(1 for b in per_page.values() if not b["blocked"])
    return {"cost_usd": round(cost, 6), "prompt_tokens": pt,
            "completion_tokens": ct, "pv_per_session": _pv_per_session(state.plan),
            # O gasto que o TETO contabilizou, para poder ser confrontado com a
            # soma dos passos. Duas contagens independentes que precisam bater:
            # se divergirem, alguma chamada paga está fora do ledger — que foi
            # exatamente o defeito da imagem.
            "budget": orcamento.relatorio() if orcamento is not None else None,
            "per_step": per_step,
            "per_page": per_page,
            "per_kind": per_kind,
            "desperdicio_usd": round(wasted, 6),
            "custo_por_pagina_util": round((cost - wasted) / uteis, 6) if uteis else 0.0}


def _write_report(state: RunState, deps: Deps) -> None:
    run_dir = deps.runner.runs_dir / state.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    if state.plan is not None:
        (run_dir / "funnel_plan.json").write_text(
            state.plan.model_dump_json(indent=2), encoding="utf-8"
        )

    (run_dir / "config_snapshot.json").write_text(
        deps.settings.model_dump_json(indent=2, exclude={"secrets"}), encoding="utf-8"
    )

    lines = [f"# Relatório de execução -- {state.run_id}", ""]
    lines.append(f"Total de páginas no plano: {state.plan.total_pages if state.plan else 0}")
    lines.append("")
    lines.append("| Página | Tipo | Slug | Palavras | Status | Modelo |")
    lines.append("|---|---|---|---|---|---|")
    pages = state.plan.pages if state.plan else []
    for page in pages:
        draft = state.drafts.get(page.page_number)
        write_res = state.step_status.get(f"write_p{page.page_number}")
        status = write_res.status.value if write_res else "SKIPPED"
        model = write_res.model_used if write_res else ""
        words = draft.word_count if draft else 0
        lines.append(
            f"| {page.page_number} | {page.page_type} | {page.slug} | {words} | "
            f"{status} | {model} |"
        )

    lines.append("")
    lines.append("## Detalhe dos passos")
    for key, res in state.step_status.items():
        lines.append(f"- `{key}`: {res.status.value} (tentativas={res.attempts}, "
                     f"modelo={res.model_used or 'n/a'})")
        for issue in res.issues:
            lines.append(f"  - [{issue.code}] {issue.message}")

    led = _profit_ledger(state, getattr(deps.runner, "budget", None))
    lines.append("")
    lines.append("## Custos e telemetria (COGS)")
    lines.append(f"- Custo total (USD): {led['cost_usd']:.6f}")
    if led.get("budget"):
        orc = led["budget"]
        lines.append(f"- Teto por run/página (USD): {orc['teto_run_usd']:.2f} / "
                     f"{orc['teto_pagina_usd']:.2f}")
        lines.append(f"- Gasto debitado do teto (USD): {orc['gasto_run_usd']:.6f}")
        if orc["gasto_por_pagina"]:
            por_pagina = ", ".join(f"{k}={v:.4f}"
                                   for k, v in orc["gasto_por_pagina"].items())
            lines.append(f"- Gasto por página (USD): {por_pagina}")
    lines.append(
        f"- Tokens prompt/completion: {led['prompt_tokens']}/{led['completion_tokens']}"
    )
    lines.append(f"- Páginas por sessão (funil): {led['pv_per_session']}")
    lines.extend(_cost_summary_lines(led, state, deps))
    lines.append("")
    lines.append("| Passo | Prompt tok | Completion tok | Custo USD | Latência ms |")
    lines.append("|---|---|---|---|---|")
    for key, ptok, ctok, cst, lat in led["per_step"]:
        lines.append(f"| {key} | {ptok} | {ctok} | {cst:.6f} | {lat} |")

    (run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _cost_summary_lines(led: dict, state: RunState, deps: Deps) -> list[str]:
    """O resumo de custo que o operador consegue LER.

    Três perguntas, três blocos: quanto custou cada PÁGINA (e ela publicou ou
    foi barrada), quanto custou cada TIPO de passo (a imagem aparece como
    `image_gen`), e quanto do dinheiro foi para página reprovada -- o
    desperdício, que é o número que decide se vale mexer nos gates ou no
    prompt. Mais o placar do verificador de URL, que é a prova de que a visita
    dupla morreu."""
    total = led["cost_usd"] or 0.0
    slug_by_number = {p.page_number: p.slug for p in (state.plan.pages if state.plan else [])}
    out: list[str] = ["", "### Custo por página", "",
                      "| Página | Slug | Custo USD | % do run | Tokens | Situação |",
                      "|---|---|---|---|---|---|"]
    for number in sorted(led["per_page"]):
        bucket = led["per_page"][number]
        share = (bucket["cost_usd"] / total * 100) if total else 0.0
        if bucket["blocked"]:
            situacao = "REPROVADA (não publicou)"
        elif bucket["published"]:
            situacao = "publicada"
        else:
            situacao = "gerada (sem publish)"
        tokens = bucket["prompt_tokens"] + bucket["completion_tokens"]
        out.append(f"| p{number} | {slug_by_number.get(number, '?')} | "
                   f"{bucket['cost_usd']:.6f} | {share:.1f}% | {tokens} | {situacao} |")

    out += ["", "### Custo por tipo de passo", "",
            "| Tipo | Chamadas | Custo USD | % do run |", "|---|---|---|---|"]
    for kind, bucket in sorted(led["per_kind"].items(), key=lambda kv: -kv[1]["cost_usd"]):
        share = (bucket["cost_usd"] / total * 100) if total else 0.0
        out.append(f"| {kind} | {bucket['calls']} | {bucket['cost_usd']:.6f} | {share:.1f}% |")

    wasted = led["desperdicio_usd"]
    wasted_share = (wasted / total * 100) if total else 0.0
    blocked = [f"p{n}" for n, b in sorted(led["per_page"].items()) if b["blocked"]]
    out += ["", "### Desperdício e custo por página útil", "",
            f"- Gasto em páginas REPROVADAS: US$ {wasted:.6f} ({wasted_share:.1f}% do run)"
            + (f" — {', '.join(blocked)}" if blocked else " — nenhuma"),
            f"- Custo médio por página que sobreviveu: US$ "
            f"{led['custo_por_pagina_util']:.6f}"]

    stats = getattr(getattr(deps, "url_verifier", None), "stats", None)
    if stats is not None:
        # `cache_hits` é a prova de que a visita dupla morreu: são as idas à
        # rede que o cache do run evitou (write -> content_gate -> publish
        # pedem as MESMAS URLs).
        out += ["", "### Verificação de URL (ao vivo)", "",
                f"- URLs visitadas: {getattr(stats, 'checked', 0)} · "
                f"visitas evitadas pelo cache: {getattr(stats, 'cache_hits', 0)}",
                f"- Verificadas OK: {getattr(stats, 'ok', 0)} · "
                f"recusadas: {getattr(stats, 'refused', 0)} · "
                f"inconclusivas (bloqueio/timeout): {getattr(stats, 'inconclusive', 0)}"]
        for url, reason in list(getattr(stats, "reasons", {}).items())[:10]:
            out.append(f"  - {url} — {reason}")
    return out
