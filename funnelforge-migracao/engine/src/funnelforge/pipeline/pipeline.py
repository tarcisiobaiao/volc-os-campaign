# funnel-forge/src/funnelforge/pipeline/pipeline.py
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
from funnelforge.pipeline.jornada import (
    contrato_de_medicao,
    revisar_esqueleto,
    revisar_funil_pronto,
    tem_jornada,
)
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
    # Dossiê: hints do operador (URL + afirmação a CONFERIR, nunca fato pronto)
    # e o leitor de documento que registra a proveniência das fontes. None/[]
    # em teste: o escopo da fonte vem do host.
    hints_do_operador: list[dict] = field(default_factory=list)
    ler_documento: Any = None


def editorial_v2_do_run(state: RunState, settings: Settings) -> bool:
    """O run está no RAMO EDITORIAL NOVO?

    Três fontes podem LIGAR (nenhuma desliga a outra): o `run.editorial_v2`
    das settings (config.yaml ou o perfil do funil), o `editorial_v2` da
    arquitetura do card (`FunnelPlan.editorial_v2`) e o próprio estado — um
    run que nasceu no ramo novo continua nele quando é retomado sem o perfil.
    Rebaixar no meio escreveria parte do funil com um contrato e parte com
    outro, e a revisão da B5 não saberia qual régua aplicar."""
    plano = state.plan
    return bool(state.editorial_v2
                or getattr(settings.run, "editorial_v2", False)
                or (plano is not None and plano.editorial_v2))


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
    if deps.sitemap is not None and deps.settings.run.terminal_exit_policy == "cross_funnel":
        try:
            lp = next((p for p in plan.pages if effective_role(p) is PageRole.LP), None)
            theme = lp.h1_title if lp else plan.pages[0].h1_title
            cross_targets = deps.sitemap.cross_funnel_targets(
                theme=theme, exclude_slugs=[p.slug for p in plan.pages])
        except Exception:  # noqa: BLE001 - sitemap is best-effort, never fatal
            cross_targets = None
    try:
        build_funnel_routes(plan, deps.settings, cross_funnel_targets=cross_targets)
        graph_issues = validate_funnel_graph(plan, deps.settings, research_pending=True)
    except ValueError as exc:
        # Página sem rota válida (slug vazio, cross-funnel fora do domínio) é
        # falha de grafo: reprova fechado, como qualquer outro problema de
        # conteúdo -- e nunca aborta o run. O canal oficial NÃO entra nesta
        # conta: ele é ligado depois da pesquisa (bind_official_route).
        graph_issues = [Issue(code="bare_rec", message=str(exc))]
    if graph_issues:
        state.step_status["funnel_graph"] = StepResult(
            step="funnel_graph", status=StepStatus.FAILED, issues=graph_issues)
    if tem_jornada(plan):
        # A prova de que o mapa foi revisado antes do gasto. Os bloqueantes
        # também estão no `funnel_graph` (é ele o portão); aqui o passo fica
        # FAILED quando o esqueleto reprova, com bloqueantes e avisos juntos.
        revisao = revisar_esqueleto(plan)
        state.step_status["revisao_esqueleto"] = StepResult(
            step="revisao_esqueleto",
            status=StepStatus.FAILED if revisao.bloqueantes else StepStatus.OK,
            issues=[*revisao.bloqueantes, *revisao.avisos])


def run_pipeline(
    briefing_path: Path | None,
    deps: Deps,
    only: str | None = None,
    publish: bool = False,
    resume_state: RunState | None = None,
    timestamp: str = "",
    plan: FunnelPlan | None = None,
    ate_o_dossie: bool = False,
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
        # O GRAFO ANTES DA PRIMEIRA CHAMADA PAGA. O roteamento não depende do
        # `engajamento`; o classificador abaixo é uma chamada de LLM, e um
        # funil estruturalmente quebrado (grafo ou jornada) não deve pagar nem
        # ela — o portão logo adiante aborta o run de qualquer jeito.
        _populate_routes(state, deps)
        # Classifica a FORMA DA PERGUNTA de cada solução -> `page.engajamento`,
        # que decide qual ferramenta interativa a página recebe. Roda aqui
        # porque precisa do plano já expandido e com slugs finais, e antes do
        # checkpoint, para que um resume não reclassifique. 100% fail-safe:
        # qualquer problema usa inferência semântica sobre H1/estrutura.
        if not _falhou(state, "funnel_graph"):
            st.declarar_engajamento(state, deps)

    # RAMO EDITORIAL NOVO: decidido UMA vez por execução e gravado no estado
    # (pegajoso: um run que nasceu no ramo novo continua nele). Desligado, o
    # laço abaixo é o de sempre, passo a passo e prompt a prompt.
    v2 = editorial_v2_do_run(state, deps.settings) and not st.perfil_rapido(deps)
    state.editorial_v2 = v2


    if state.run_id.startswith("_pending") and state.plan and state.plan.pages:
        old = state.run_id
        state.run_id = f"{state.plan.pages[0].slug}-{timestamp}"
        deps.runner.finalize_run_id(old, state.run_id)
    _checkpoint(state, deps)
    # DOSSIÊ FACTUAL antes de qualquer briefing/redação: pesquisa única do
    # funil, portão de cobertura, fatos congelados. Página sem lastro fica
    # bloqueada aqui e o laço abaixo não gasta nada com ela.
    dossie_vivo = None
    if (getattr(deps.settings.run, "dossie_factual", False) and tem_jornada(state.plan)
            and not _falhou(state, "funnel_graph")):
        dossie_vivo = _preparar_dossie(state, deps)
        _checkpoint(state, deps)
    if ate_o_dossie:
        # Só esqueleto -> pesquisa -> dossiê -> verificação -> cobertura.
        # Nenhum briefing, redação, SEO, widget, revisão, imagem ou build.
        _write_report(state, deps)
        _checkpoint(state, deps)
        return state

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
    # Com JORNADA a publicação espera a revisão global do funil pronto: nada
    # vai ao rascunho do WordPress antes de o funil inteiro ser conferido.
    com_jornada = tem_jornada(state.plan)
    a_publicar: list[Page] = []

    laco = _Laco(v2=v2, publish=publish, com_jornada=com_jornada,
                 orcamento=orcamento, a_publicar=a_publicar, dossie_vivo=dossie_vivo)
    if dossie_vivo is not None and st.perfil_rapido(deps):
        _complementar_lote_rapido(state, pages, deps, dossie_vivo)
        _checkpoint(state, deps)
    workers = int(getattr(deps.settings.run, "page_workers", 1) or 1)
    if workers > 1 and len(pages) > 1:
        _paginas_em_paralelo(state, pages, deps, laco, workers)
    else:
        for page in pages:
            if _processar_pagina(state, page, deps, laco) == "break":
                break
    if dossie_vivo is not None:
        _consolidar_dossie(state, deps, dossie_vivo)

    # REVISÃO GLOBAL do funil pronto (só com jornada), ANTES de qualquer
    # publicação e só sobre páginas estruturalmente aprovadas. Uma passada
    # determinística, sem chamada e sem reescrita. Prova estrutural (CTA para
    # dúvida resolvida em todo caminho, loop real, saída oficial fora de
    # lugar, beco) bloqueia a página; proxy de termo é aviso para a pessoa.
    if com_jornada:
        revisao = revisar_funil_pronto(state, deps.settings)
        if revisao:
            state.revisao_global = revisao
            bloqueio = bool(revisao["paginas_bloqueadas"])
            state.step_status["revisao_global"] = StepResult(
                step="revisao_global",
                status=StepStatus.FAILED if bloqueio else StepStatus.OK,
                issues=[Issue(code=a["regra"],
                              message=(f"[p{a['pagina']} {a['duvida_id']}] "
                                       f"({a['severidade']}) {a['localizador']}: "
                                       f"{a['evidencia']} → {a['proposta']}"))
                        for a in revisao["achados"]])
            for n in revisao["paginas_bloqueadas"]:
                state.step_status[f"blocked_p{n}"] = StepResult(
                    step=f"blocked_p{n}", status=StepStatus.FAILED,
                    issues=[Issue(code="revisao_global",
                                  message="revisão global do funil pronto achou prova "
                                          "estrutural nesta página; publish pulado")])
            _checkpoint(state, deps)
        if st.perfil_rapido(deps):
            _revisao_e_pacotes_rapidos(state, deps)
        for page in a_publicar:
            if f"blocked_p{page.page_number}" in state.step_status:
                continue
            try:
                st.step_publish(state, page, deps)
            except Exception as exc:  # noqa: BLE001 - uma página não derruba as outras
                state.step_status[f"page_{page.page_number}"] = StepResult(
                    step=f"page_{page.page_number}", status=StepStatus.FAILED,
                    issues=[Issue(code="exception", message=str(exc))])
            _checkpoint(state, deps)

    _write_report(state, deps)
    _checkpoint(state, deps)
    return state



@dataclass
class _Laco:
    """O que o laço de páginas compartilha entre uma página e a próxima."""
    v2: bool
    publish: bool
    com_jornada: bool
    orcamento: Any
    a_publicar: list
    # "tudo" (serial) | "redacao" (para depois do portão de página condenada)
    # | "acabamento" (retoma do SEO; a redação já está consolidada)
    fase: str = "tudo"
    # O dossiê como CACHE compartilhado (`CompiladorDeDossie`): a página com
    # lacuna pesquisa sob demanda antes de escrever. None = sem dossiê.
    dossie_vivo: Any = None


def _paginas_em_paralelo(state: RunState, pages: list[Page], deps: Deps, laco: _Laco,
                         workers: int) -> None:
    """As páginas em até `workers` (máx. 3) workers isolados, depois do dossiê
    congelado, em DUAS fases com consolidação serial entre elas:

    A. portão, briefing e redação em paralelo; os rascunhos entram no estado em
       ordem de página e a unicidade entre eles é conferida como no serial
       (cada página contra as anteriores) — a repetida falha ANTES de gastar
       com SEO, revisão ou imagem;
    B. do SEO ao build em paralelo, cada revisor já vendo os rascunhos das
       páginas de origem (o rótulo que o botão de lá prometeu).

    Logs e prompts das páginas entram no run no fim, em ordem de página — a
    mesma ordem do serial. Ver `pipeline/paralelo.py`."""
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace

    from funnelforge.pipeline import paralelo as par

    if not state.dossie_sha256:
        # Sem dossiê congelado a pesquisa ainda está por fazer, e ela é o
        # gasto faturado: não roda em paralelo. Fica registrado, não é silêncio.
        state.step_status["paginas_paralelas"] = StepResult(
            step="paginas_paralelas", status=StepStatus.SKIPPED,
            issues=[Issue(code="sem_dossie", message="page_workers>1 sem dossiê congelado: "
                          "páginas processadas em série")])
        for page in pages:
            if _processar_pagina(state, page, deps, laco) == "break":
                break
        return

    workers = min(workers, par.MAX_PAGE_WORKERS)
    contador = par.ContadorDeChamadas(deps.llm)
    trava = threading.Lock()
    screenshot = par.Serializado(deps.screenshot, trava) if deps.screenshot is not None else None
    sitemap = par.Serializado(deps.sitemap, trava) if deps.sitemap is not None else None
    parar = threading.Event()
    # O orçamento da página vale para as duas fases (o teto por página não
    # dobra porque a página foi processada em duas vezes).
    orcamentos = {p.page_number: (laco.orcamento.para_pagina(f"p{p.page_number}")
                                  if laco.orcamento is not None else None) for p in pages}
    duracao: dict[int, float] = {}

    def fase(nome: str, alvo: list[Page]) -> list[par.DeltaDaPagina]:
        copias = {p.page_number: state.model_copy(deep=True) for p in alvo}

        def worker(page: Page) -> par.DeltaDaPagina:
            n = page.page_number
            if parar.is_set():
                return par.DeltaDaPagina(page_number=n, rodou=False)
            copia = copias[n]
            pagina = next(p for p in copia.plan.pages if p.page_number == n)
            orc = orcamentos[n]
            if orc is not None and nome == "redacao":
                orc.entrar_na_pagina(f"p{n}")
            runner = par.RunnerDaPagina(deps.runner, n, contador, orc)
            deps_pg = replace(deps, llm=contador, runner=runner, screenshot=screenshot,
                              sitemap=sitemap)
            local = _Laco(v2=laco.v2, publish=laco.publish, com_jornada=laco.com_jornada,
                          orcamento=orc, a_publicar=[], fase=nome,
                          dossie_vivo=laco.dossie_vivo)
            inicio = time.monotonic()
            try:
                sinal = _processar_pagina(copia, pagina, deps_pg, local)
            except Exception as exc:  # noqa: BLE001 - um worker não derruba os outros
                sinal = None
                copia.step_status[f"page_{n}"] = StepResult(
                    step=f"page_{n}", status=StepStatus.FAILED,
                    issues=[Issue(code="exception",
                                  message=f"{type(exc).__name__}: {exc}"[:400])])
            if sinal == "break":
                parar.set()
            gasto = round(time.monotonic() - inicio, 3)
            return par.extrair_delta(state, copia, pagina, sinal=sinal,
                                     publicar=bool(local.a_publicar), duracao_s=gasto)

        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pagina") as pool:
            deltas = list(pool.map(worker, alvo))
        aplicados = []
        for delta in sorted(deltas, key=lambda d: d.page_number):
            if not delta.rodou:
                continue
            n = delta.page_number
            duracao[n] = duracao.get(n, 0.0) + delta.duracao_s
            if delta.violacoes:
                state.step_status[f"page_{n}"] = StepResult(
                    step=f"page_{n}", status=StepStatus.FAILED,
                    issues=[Issue(code="delta_fora_da_pagina",
                                  message="worker mudou estado de fora da página (não "
                                          "aplicado): " + ", ".join(delta.violacoes[:10]))])
                state.step_status[f"blocked_p{n}"] = StepResult(
                    step=f"blocked_p{n}", status=StepStatus.FAILED,
                    issues=[Issue(code="fail_closed", message="delta fora da página")])
                continue
            par.aplicar_delta(state, delta)
            aplicados.append(delta)
        return aplicados

    antes = list(state.step_status)
    inicio = time.monotonic()
    redigidas = [d for d in fase("redacao", pages) if d.sinal == "redigida"]

    # UNICIDADE ENTRE AS PÁGINAS DO LOTE — a mesma regra do serial: cada página
    # contra as escritas antes dela. A repetida tem `write_pN` reprovado e a
    # fase B a trata como página condenada (blocked, sem gasto).
    lote = sorted(d.page_number for d in redigidas)
    todos = dict(state.drafts)
    for n in lote:
        page = next(p for p in state.plan.pages if p.page_number == n)
        state.drafts = {k: v for k, v in todos.items() if k not in lote or k <= n}
        try:
            st.uniqueness_state_guard(state, page, deps)
            st.presell_hub_distinction_guard(state, page, deps)
        finally:
            state.drafts = todos
    _checkpoint(state, deps)

    por_numero = {p.page_number: p for p in state.plan.pages}
    acabadas = fase("acabamento", [por_numero[n] for n in lote]) if not parar.is_set() else []
    for delta in acabadas:
        if delta.publicar:
            laco.a_publicar.append(por_numero[delta.page_number] if delta.pagina is None
                                   else next(p for p in state.plan.pages
                                             if p.page_number == delta.page_number))
    parede_s = round(time.monotonic() - inicio, 3)
    for page in pages:
        par.fundir_artefatos(deps.runner.runs_dir, state.run_id, page.page_number)
    # Os passos novos na ordem do serial (página a página), não na das fases:
    # o estado e o relatório de um run paralelo leem como os de um serial.
    state.step_status = par.ordem_serial(state.step_status, antes)

    state.step_status["paginas_paralelas"] = StepResult(
        step="paginas_paralelas", status=StepStatus.OK, latency_ms=int(parede_s * 1000),
        issues=[Issue(code="paralelo", message=(
            f"workers={workers}; páginas={len(duracao)}; redigidas={len(lote)}; "
            f"acabadas={len(acabadas)}; chamadas={contador.total}; "
            f"pico_de_chamadas_em_voo={contador.pico}; parede_s={parede_s}; "
            f"soma_das_paginas_s={round(sum(duracao.values()), 3)}; "
            f"teto_do_run={'atingido' if parar.is_set() else 'não'}; "
            f"dossie={state.dossie_sha256[:12]}"))])
    _checkpoint(state, deps)

def _processar_pagina(state: RunState, page: Page, deps: Deps, laco: "_Laco") -> str | None:
    """Uma página do laço, do portão do dossiê ao publish (ou ao adiamento do
    publish). Devolve "break" quando o teto do RUN acabou — o chamador para de
    abrir páginas novas; qualquer outra falha fica na própria página."""
    v2, publish, com_jornada = laco.v2, laco.publish, laco.com_jornada
    orcamento, a_publicar = laco.orcamento, laco.a_publicar
    if (laco.dossie_vivo is not None and not st.perfil_rapido(deps)
            and laco.fase != "acabamento"
            and not _done(state, f"write_p{page.page_number}")):
        _complementar_pagina(state, page, deps, laco.dossie_vivo)
    if _falhou(state, f"dossie_p{page.page_number}"):
        return None          # conflito na promessa central: só ESTA página para
    # Zera o contador da PÁGINA: o teto por página existe para que uma
    # página patológica não coma o orçamento das outras.
    if orcamento is not None and laco.fase != "acabamento":
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

        # RAMO NOVO: o briefing-v1 desta página, entre a pesquisa e a
        # redação — só para página ainda não escrita (num run antigo
        # retomado com a flag, o que já foi escrito não ganha briefing).
        # Falhou -> `step_write` recusa sem gastar (briefing_indisponivel).
        if (v2 and not _done(state, f"write_p{page.page_number}")
                and (not _done(state, f"briefing_p{page.page_number}")
                     or page.page_number not in state.briefings)):
            st.step_briefing(state, page, deps)
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
        if (_falhou(state, f"write_p{page.page_number}")
                or _falhou(state, f"judge_p{page.page_number}")):
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
                    message="write/judge FAILED — seo/imagem/build/publish pulados "
                            "para não gastar em página condenada")])
            _checkpoint(state, deps)
            return None

        if laco.fase == "redacao":
            return "redigida"     # a consolidação decide se a página segue

        if not _done(state, f"seo_p{page.page_number}"):
            st.step_seo(state, page, deps)
            _checkpoint(state, deps)

        # RAMO NOVO (B5): o REVISOR CONTEXTUAL vem DEPOIS do SEO e do
        # widget — o título SEO é o H1 visível das internas e o texto do
        # widget vai ao ar; os dois são revisados e cobertos pelo recibo.
        # TODA página escrita a partir de briefing passa por aqui (LP sem
        # contrato editorial inclusive). A escrita antiga (página sem
        # briefing num run retomado) já foi julgada dentro do `step_write`.
        if v2 and page.page_number in state.briefings:
            # O widget roda UMA vez, antes da revisão: se ele fosse gerado
            # depois, entraria no ar texto que ninguém revisou (V12).
            if (getattr(deps.settings.run, "widgets_enabled", False)
                    and f"widget_p{page.page_number}" not in state.step_status):
                st.step_widget(state, page, deps)
                _checkpoint(state, deps)
            # O próprio revisor decide se roda: decisão humana gravada
            # manda, e página já aprovada ou em revisão humana com o MESMO
            # conteúdo não é revisada de novo (o resume não re-rola).
            st.revisar_pagina_v2(state, page, deps)
            _checkpoint(state, deps)
            if not st.revisao_liberada(state, page):
                state.step_status[f"blocked_p{page.page_number}"] = StepResult(
                    step=f"blocked_p{page.page_number}", status=StepStatus.FAILED,
                    issues=[Issue(
                        code="fail_closed",
                        message="revisão sem aprovação (revisão humana pendente, "
                                "rejeitada ou conteúdo mudado depois da decisão) — "
                                "imagem/build/publish pulados; ver revisor_p"
                                f"{page.page_number} e `funnelforge decidir`")])
                _checkpoint(state, deps)
                return None

        # LP always crafts its hero prompt (generation still gated on
        # run.hero_image inside step_image); interior /rec posts run the
        # image step only when run.featured_image is on. `image_wanted`
        # inside step_image is the single source of the generate/skip
        # decision, so the two never disagree.
        _wants_image = (page.page_type == "LANDING PAGE" or getattr(
            deps.settings.run, "featured_image", False)) and getattr(
            deps.settings.run, "imagens_habilitadas", True)
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
            return None

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
        ) and not (v2 and page.page_number in state.briefings):
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
            return None

        # ⚠️ A condenação ANTIGA tem de sair do estado quando a página passa.
        #
        # `blocked_pN` só era escrito, nunca apagado. Depois da retomada de
        # 19/08/2026 a p3 estava com `widget_p3: OK` e `content_gate_p3: OK`
        # — e ainda carregava `blocked_p3: FAILED` da rodada anterior. O
        # relatório lê o estado e diria "bloqueada" sobre uma página pronta
        # para publicar. Estado que guarda veredito vencido mente para quem
        # o lê depois, e é a partir dele que o operador decide.
        state.step_status.pop(f"blocked_p{page.page_number}", None)
        _registrar_metadados(state, page, deps)

        # No perfil rápido só o `block` da revisão GLOBAL vai a humano; lacuna de
        # evidência já foi degradada no texto e é aviso para o revisor global.
        revisao = "" if st.perfil_rapido(deps) else _revisao_por_evidencia(state, page)
        if revisao:
            state.step_status[f"evidencia_p{page.page_number}"] = StepResult(
                step=f"evidencia_p{page.page_number}", status=StepStatus.SKIPPED,
                issues=[Issue(code="revisao_humana_por_evidencia", message=revisao)])
        if publish and deps.publisher is not None and not revisao and not _done(
            state, f"publish_p{page.page_number}"
        ):
            if com_jornada:
                a_publicar.append(page)
            else:
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
            return "break"
        return None
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
        return None
    except Exception as exc:  # noqa: BLE001 - one page's failure must not abort the rest
        key = f"page_{page.page_number}"
        state.step_status[key] = StepResult(
            step=key,
            status=StepStatus.FAILED,
            issues=[Issue(code="exception", message=str(exc))],
        )
        _checkpoint(state, deps)
        return None
    return None

def _base_do_modelo(nome: str) -> str:
    return re.sub(r"-\d{4}-\d{2}-\d{2}$", "", (nome or "").split("/")[-1].lower())


def _preco_da_consulta_de_busca(modelo: str) -> float:
    """Preço de tabela de UMA consulta de grounding (LiteLLM). 0 = desconhecido."""
    try:
        from litellm import model_cost
    except Exception:  # noqa: BLE001
        return 0.0
    preco = (model_cost.get(modelo) or {}).get("search_context_cost_per_query") or {}
    return float(preco.get("search_context_size_medium") or 0.0) if isinstance(preco, dict) else 0.0


def _preparar_dossie(state: RunState, deps: Deps) -> None:
    """Compila (ou, num resume, REAPROVEITA) o dossiê e aplica o portão."""
    from funnelforge.adapters.research_perplexity import pesquisar_funil
    from funnelforge.domain.dossie import DossieDoFunil
    from funnelforge.pipeline.dossie import aplicar_portao, compilar_dossie, hash_do_dossie

    paginas = [p for p in state.plan.pages if p.jornada is not None]

    def bloquear_tudo(motivo: str, base: StepResult) -> None:
        state.step_status["dossie"] = base
        for p in paginas:
            state.step_status[f"dossie_p{p.page_number}"] = StepResult(
                step=f"dossie_p{p.page_number}", status=StepStatus.FAILED,
                issues=[Issue(code="dossie_indisponivel", message=motivo)])
            state.step_status[f"blocked_p{p.page_number}"] = StepResult(
                step=f"blocked_p{p.page_number}", status=StepStatus.FAILED,
                issues=[Issue(code="fail_closed", message=motivo)])

    if state.dossie:
        dossie = DossieDoFunil.model_validate(state.dossie)
        if hash_do_dossie(dossie) != state.dossie_sha256:
            bloquear_tudo("dossiê do estado não confere com o hash congelado: nada é escrito",
                          StepResult(step="dossie", status=StepStatus.FAILED))
            return
        aplicar_portao(state, dossie)
        return
    cfg = deps.settings.steps.get("dossie")
    if cfg is None:
        bloquear_tudo("run.dossie_factual ligado sem steps.dossie na config",
                      StepResult(step="dossie", status=StepStatus.FAILED))
        return
    orcamento = getattr(deps.runner, "budget", None)
    respostas = []

    preco_da_busca = _preco_da_consulta_de_busca(cfg.model)
    buscas: list[float] = []

    def pesquisar(assunto, spec, faltantes):
        if orcamento is not None:
            orcamento.exigir_saldo("dossie")
        resp = pesquisar_funil(deps.llm, cfg, assunto, spec, faltantes)
        # O grounding cobra por consulta e `completion_cost` pode não somar
        # isso: o orçamento debita tokens + consultas × preço de tabela (teto
        # conservador; se o LiteLLM já incluiu, superestima — nunca o contrário).
        buscas.append(round(resp.consultas_de_busca * preco_da_busca, 6))
        if orcamento is not None:
            orcamento.registrar_fora_de_pagina("dossie", resp.custo_usd + buscas[-1])
        respostas.append(resp)
        if _base_do_modelo(resp.modelo_servido) != _base_do_modelo(cfg.model):
            raise RuntimeError(f"pesquisa do dossiê pediu {cfg.model} e recebeu "
                               f"{resp.modelo_servido}: troca de modelo não é aceita")
        return resp

    def telemetria(status: StepStatus, issues: list[Issue]) -> StepResult:
        ultima = respostas[-1] if respostas else None
        return StepResult(
            step="dossie", status=status, model_requested=cfg.model,
            model_used=ultima.modelo_servido if ultima else "",
            auth_mode=ultima.auth_mode if ultima else "",
            attempts=sum(max(1, len(r.metadados)) for r in respostas),
            prompt_tokens=sum(r.prompt_tokens for r in respostas),
            completion_tokens=sum(r.completion_tokens for r in respostas),
            cost_usd=round(sum(r.custo_usd for r in respostas) + sum(buscas), 6),
            latency_ms=sum(r.latencia_ms for r in respostas), issues=issues)

    pasta = deps.runner.runs_dir / state.run_id

    def gravar_chamadas() -> None:
        # O recibo de CADA chamada ao provedor, com sucesso ou não: o canário
        # de 07/10 voltou vazio e não deixou como saber por quê.
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "pesquisa_dossie.json").write_text(json.dumps([
            {"rodada": i, "modelo_pedido": r.modelo_pedido, "modelo_servido": r.modelo_servido,
             "auth_mode": r.auth_mode, "defeito": r.defeito, "citacoes": len(r.citacoes),
             "fatos": len((r.dados or {}).get("fatos") or []),
             "custo_tokens_usd": r.custo_usd if r.custo_informado else None,
             "busca_estimada_usd": buscas[i - 1] if i <= len(buscas) else 0.0,
             "chamadas": r.metadados}
            for i, r in enumerate(respostas, 1)], ensure_ascii=False, indent=2),
            encoding="utf-8")

    from funnelforge.pipeline.dossie import CompiladorDeDossie
    vivo = CompiladorDeDossie(state, deps, pesquisar,
                              registrar_canais=st.registrar_canais_oficiais,
                              ler_documento=getattr(deps, "ler_documento", None))
    vivo.respostas, vivo.gravar_chamadas, vivo.telemetria_do_passo = (
        respostas, gravar_chamadas, telemetria)
    try:
        # Só a pesquisa GLOBAL aqui: a complementação é por lacuna, sob demanda,
        # no worker de cada página (`_complementar_pagina`).
        dossie = vivo.compilar(hints=list(getattr(deps, "hints_do_operador", []) or []),
                               complementos=0)
    except Exception as exc:  # noqa: BLE001 - defeito do motor, não da fonte
        motivo = f"pesquisa do dossiê falhou: {type(exc).__name__}: {str(exc)[:300]}"
        bloquear_tudo(motivo, telemetria(StepStatus.FAILED,
                                         [Issue(code="dossie_falhou", message=motivo)]))
        gravar_chamadas()
        return None
    gravar_chamadas()
    state.dossie = dossie.model_dump(mode="json")
    state.dossie_sha256 = dossie.sha256
    (pasta / "dossie_factual.json").write_text(dossie.model_dump_json(indent=2),
                                               encoding="utf-8")
    resultado = aplicar_portao(state, dossie)
    state.step_status["dossie"] = telemetria(StepStatus.OK, [
        Issue(code="dossie_portao", message=f"{len(resultado.prontas)} página(s) liberada(s), "
              f"{len(resultado.bloqueadas)} bloqueada(s); {len(dossie.fatos)} fato(s), "
              f"{len(dossie.pesquisa)} rodada(s), "
              f"{sum(t.consultas_de_busca for t in dossie.pesquisa)} consulta(s) de busca do "
              f"grounding; " + (
                  f"custo = tokens US$ {sum(r.custo_usd for r in respostas):.4f} + "
                  f"busca estimada US$ {sum(buscas):.4f} (US$ {preco_da_busca}/consulta)"
                  if all(r.custo_informado for r in respostas) else
                  f"auth_mode {respostas[-1].auth_mode if respostas else '?'}: custo NÃO "
                  "informado pelo servidor (quota do plano)") +
              f"; sha256 {dossie.sha256[:12]}")])
    return vivo


def _complementar_pagina(state: RunState, page: Page, deps: Deps, vivo: Any) -> None:
    """A página com lacuna pesquisa sob demanda (uma busca por lacuna,
    deduplicada entre páginas), registra no cache, e é reavaliada — o snapshot
    do dossiê do worker passa a ter a própria página atualizada."""
    from funnelforge.pipeline.dossie import aplicar_portao
    n = page.page_number
    if n not in vivo.coberturas or not vivo.lacunas(n):
        return
    resumo = vivo.complementar_pagina(page, state)
    with vivo.trava:
        parcial = vivo.montar(state)
    state.dossie = parcial.model_dump(mode="json")
    state.dossie_sha256 = parcial.sha256
    pagina = parcial.pagina(n)
    if pagina is not None:
        aplicar_portao(state, parcial.model_copy(update={"paginas": [pagina]}))
    state.step_status[f"dossie_complemento_p{n}"] = StepResult(
        step=f"dossie_complemento_p{n}", status=StepStatus.OK,
        issues=[Issue(code="complemento_sob_demanda", message=json.dumps(
            resumo, ensure_ascii=False)[:600])])


def _complementar_lote_rapido(state: RunState, pages: list[Page], deps: Deps, vivo: Any) -> None:
    """No perfil rápido, fecha todas as lacunas em uma rodada consolidada.

    A saída continua sendo o mesmo dossiê tipado e o mesmo portão por página;
    só muda a granularidade da pesquisa. Falha de fonte degrada o requisito e
    as páginas seguem para a revisão global, conforme o contrato já existente.
    """
    from funnelforge.pipeline.dossie import aplicar_portao
    resumo = vivo.complementar_lote(pages, state)
    with vivo.trava:
        parcial = vivo.montar(state)
    state.dossie = parcial.model_dump(mode="json")
    state.dossie_sha256 = parcial.sha256
    aplicar_portao(state, parcial)
    state.step_status["dossie_complemento_lote"] = StepResult(
        step="dossie_complemento_lote", status=StepStatus.OK,
        issues=[Issue(code="complemento_em_lote", message=json.dumps(
            resumo, ensure_ascii=False)[:600])])


def _consolidar_dossie(state: RunState, deps: Deps, vivo: Any) -> None:
    """Depois das páginas: o dossiê do run é o cache consolidado (fatos por
    fact_id, coberturas como cada página as viu), com SHA novo."""
    with vivo.trava:
        final = vivo.montar(state)
    state.dossie = final.model_dump(mode="json")
    state.dossie_sha256 = final.sha256
    pasta = deps.runner.runs_dir / state.run_id
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "dossie_factual.json").write_text(final.model_dump_json(indent=2), encoding="utf-8")
    vivo.gravar_chamadas()
    estados = {}
    for p in final.paginas:
        estados[p.cobertura.estado] = estados.get(p.cobertura.estado, 0) + 1
    base = vivo.telemetria_do_passo(StepStatus.OK, [])
    base.issues = [Issue(code="dossie_consolidado", message=(
        f"páginas {estados}; {len(final.fatos)} fato(s); "
        f"{sum(1 for t in final.pesquisa if t.pagina)} complementação(ões) sob demanda; "
        f"{vivo.deduplicadas} lacuna(s) deduplicada(s); {vivo.reaproveitadas} reaproveitada(s) "
        f"do cache; {len(final.conflitos)} conflito(s); sha256 {final.sha256[:12]}"))]
    state.step_status["dossie"] = base
    _checkpoint(state, deps)


def _revisao_e_pacotes_rapidos(state: RunState, deps: Deps) -> None:
    """Perfil rápido: UMA revisão global do funil pronto (patch mínimo de block
    aplicado uma vez) e o pacote de cada página, gravados no run."""
    from funnelforge.pipeline.revisao_rapida import pacote_da_pagina, revisar_funil_rapido
    pasta = deps.runner.runs_dir / state.run_id
    pasta.mkdir(parents=True, exist_ok=True)
    try:
        revisao = revisar_funil_rapido(state, deps)
    except Exception as exc:  # noqa: BLE001 - revisão que falha vira bloqueio visível
        revisao = {"versao": "revisao-global-rapida-v1", "erro": f"{type(exc).__name__}: {exc}"[:400],
                   "paginas": [], "revisao_humana": [{"page_number": "funil",
                                                      "motivo": "revisão global falhou"}]}
        state.step_status["revisao_global_rapida"] = StepResult(
            step="revisao_global_rapida", status=StepStatus.FAILED,
            issues=[Issue(code="revisao_global_rapida_falhou", message=revisao["erro"])])
    (pasta / "revisao_global_rapida.json").write_text(
        json.dumps(revisao, ensure_ascii=False, indent=2), encoding="utf-8")
    pacotes = [pacote_da_pagina(state, p) for p in state.plan.pages]
    (pasta / "pacotes.json").write_text(json.dumps(pacotes, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    _checkpoint(state, deps)


def _revisao_por_evidencia(state: RunState, page: Page) -> str:
    """Página escrita com a promessa central sem evidência não publica sem
    decisão humana."""
    r = state.step_status.get(f"dossie_p{page.page_number}")
    if r is None:
        return ""
    return next((i.message for i in r.issues if i.code == "revisao_humana_por_evidencia"), "")


def _registrar_metadados(state: RunState, page: Page, deps: Deps) -> None:
    """Metadados e JSON-LD da página aprovada: determinístico, sem chamada.
    Nunca derruba a página — falha vira registro, não exceção."""
    from datetime import date as _data

    from funnelforge.pipeline.metadados import metadados_da_pagina
    try:
        meta = metadados_da_pagina(
            state, page, deps.settings, hoje=_data.today(),
            robots=st.index_decision_for(deps.settings, page).robots)
        state.metadados[page.page_number] = meta.model_dump()
        pasta = deps.runner.runs_dir / state.run_id
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / f"metadados_p{page.page_number}.json").write_text(
            meta.model_dump_json(indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - metadado não pode matar página aprovada
        state.metadados[page.page_number] = {"erro": f"{type(exc).__name__}: {exc}"[:300]}


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
        # B5: revisor contextual do ramo novo (ausente no ramo antigo).
        f"revisor_p{page.page_number}",
    ]
    if not antes_do_build:
        chaves.append(f"content_gate_p{page.page_number}")
    for key in chaves:
        res = state.step_status.get(key)
        if res is not None and res.status is StepStatus.FAILED:
            return True
    return False


def _reachable_page_count(plan: FunnelPlan | None) -> int:
    """Structural reachability, not observed or predicted session page views."""
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
            "completion_tokens": ct, "reachable_pages": _reachable_page_count(state.plan),
            "pv_per_session": None, "measurement_status": "not_collected",
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
        pedido = (f", pedido={res.model_requested}"
                  if res.model_requested and res.status is StepStatus.FALLBACK else "")
        lines.append(f"- `{key}`: {res.status.value} (tentativas={res.attempts}, "
                     f"modelo={res.model_used or 'n/a'}{pedido})")
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
    lines.append(f"- Páginas alcançáveis no grafo: {led['reachable_pages']}")
    lines.append("- Páginas por sessão: não medidas (nenhum evento de sessão neste relatório).")
    do_plano = [k for k, r in state.step_status.items() if r.auth_mode == "chatgpt_plan"]
    if do_plano:
        lines.append(f"- Passos no plano ChatGPT (uso do plano, sem custo de API): "
                     f"{len(do_plano)} — o custo em USD acima é só o faturado por API.")
    lines.extend(_cost_summary_lines(led, state, deps))
    lines.append("")
    lines.append("| Passo | Prompt tok | Completion tok | Custo USD | Latência ms |")
    lines.append("|---|---|---|---|---|")
    for key, ptok, ctok, cst, lat in led["per_step"]:
        lines.append(f"| {key} | {ptok} | {ctok} | {cst:.6f} | {lat} |")

    lines.extend(_jornada_no_relatorio(state, run_dir))
    (run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _jornada_no_relatorio(state: RunState, run_dir: Path) -> list[str]:
    """Artefatos da jornada: `revisao_global.json` e `medicao.json`.

    O contrato de medição só sai de um mapa que passou no portão: medir um
    funil estruturalmente quebrado seria medir o que não vai existir. Nenhum
    tracking é implantado — o arquivo diz o que medir, de onde, e com que
    natureza (hipótese, simulação, observação real)."""
    plan = state.plan
    if not tem_jornada(plan) or _falhou(state, "funnel_graph"):
        return []
    assert plan is not None
    achados = list((state.revisao_global or {}).get("achados") or [])
    contrato = contrato_de_medicao(plan, state.run_id, achados=achados)
    (run_dir / "medicao.json").write_text(contrato.model_dump_json(indent=2), encoding="utf-8")
    if state.revisao_global:
        (run_dir / "revisao_global.json").write_text(
            json.dumps(state.revisao_global, ensure_ascii=False, indent=2), encoding="utf-8")
    avisos = state.step_status.get("revisao_esqueleto")
    materiais = [a for a in achados if a.get("severidade") == "material"]
    linhas = ["", "## Jornada do leitor", "",
              f"- Revisão do esqueleto (antes do gasto): aprovada, "
              f"{len(avisos.issues) if avisos else 0} aviso(s).",
              f"- Revisão global do funil pronto: "
              f"{(state.revisao_global or {}).get('decisao', 'não rodou')} — "
              f"{len(materiais)} achado(s) material(is), {len(achados) - len(materiais)} aviso(s). "
              "Nenhum texto alterado.",
              f"- Saídas oficiais: " + ", ".join(
                  f"{k}={v}" for k, v in contrato.saidas_oficiais.items()),
              f"- Contrato de medição: medicao.json ({len(contrato.sinais)} sinais previstos, "
              f"{len(contrato.observadas())} observação(ões) real(is)). Proposta de nova "
              "versão exige aprovação humana; nada é publicado ou reescrito por código."]
    return linhas


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
