from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import typer

from funnelforge.config.settings import Secrets, Settings, load_settings
from funnelforge.pipeline.pipeline import Deps, run_pipeline
from funnelforge.pipeline.runner import Runner

app = typer.Typer(add_completion=False)


def _export_secrets(secrets: Secrets) -> None:
    """Populate os.environ from the parsed `.env` secrets so LiteLLM (which
    reads provider credentials straight from the environment) can
    authenticate. `setdefault` is used so a var already exported in the
    caller's shell wins over `.env`."""
    env_map = {
        "OPENAI_API_KEY": secrets.openai_api_key,
        "GEMINI_API_KEY": secrets.gemini_api_key,
        "ANTHROPIC_API_KEY": secrets.anthropic_api_key,
        "PERPLEXITY_API_KEY": secrets.perplexity_api_key,
    }
    for name, value in env_map.items():
        if value:
            os.environ.setdefault(name, value)


def build_deps(settings: Settings) -> Deps:
    """Composition root: the only place (besides this module) that imports
    the concrete network adapters. Imports are lazy (inside this function)
    so importing `funnelforge.cli` never requires network libs to be
    configured -- only invoking a command that actually needs them does.

    `publisher` and `image_gen` are left `None` when the corresponding
    secrets are absent, so `run`/`resume` still work as a dry run (writing
    drafts/report.md locally) without WordPress or OpenAI image credentials.

    The interactive-widget subsystem (CARD-0013, `run.widgets_enabled`) needs
    NO new port here: its generator calls the SAME injected `runner`/`llm` via
    `steps.widget`, and the on/off decision + step config flow entirely through
    `settings` (RunConfig.widgets_enabled + steps["widget"]). So `build_deps`
    wires nothing extra for it -- the pipeline reads the flag off `deps.settings`
    and no-ops when it is off (default).
    """
    _export_secrets(settings.secrets)

    from funnelforge.adapters.briefing_docx import DocxBriefingLoader
    from funnelforge.adapters.image_openai import OpenAIImageGenerator
    from funnelforge.adapters.images_pillow import PillowImageProcessor
    from funnelforge.adapters.litellm_client import LiteLLMClient
    from funnelforge.adapters.research_perplexity import PerplexityResearch
    from funnelforge.adapters.sitemap_http import HttpSitemapProvider
    from funnelforge.adapters.url_verifier_http import HttpUrlVerifier
    from funnelforge.adapters.wordpress import WordPressPublisher

    from funnelforge.pipeline.budget import Orcamento

    llm = LiteLLMClient()
    # Freio de gasto (Frente 3): o teto vem do `config.yaml` e é conferido ANTES
    # de cada chamada paga. Só a execução REAL ganha orçamento -- um Runner
    # montado à mão em teste continua sem teto (budget=None), como antes.
    runner = Runner(
        llm=llm, max_retries=settings.run.max_retries, runs_dir=Path("runs"),
        budget=Orcamento(teto_run_usd=settings.budget.max_usd_per_run,
                         teto_pagina_usd=settings.budget.max_usd_per_page),
    )

    publisher = None
    if settings.secrets.wp_url and settings.secrets.wp_app_token:
        publisher = WordPressPublisher(
            settings.secrets.wp_url, settings.secrets.wp_user or "", settings.secrets.wp_app_token
        )

    image_gen = None
    if settings.secrets.openai_api_key:
        # IMAGE-GENERATION model/quality come from `run.image_model` /
        # `run.image_quality` -- NOT `steps["image"].model`, which is the
        # TEXT model that crafts the English image prompt (see
        # steps.py's step_image / RunConfig in config/settings.py).
        image_gen = OpenAIImageGenerator(
            settings.secrets.openai_api_key,
            model=settings.run.image_model,
            quality=settings.run.image_quality,
        )

    research = PerplexityResearch(llm, settings.steps.get("research"))

    # Official-page screenshots (CARD-0005 / Task 9 B5): only wire the Playwright
    # adapter when the feature flag is ON *and* playwright is importable. If the
    # optional `screenshots` extra isn't installed, leave screenshot=None so
    # step_screenshot no-ops -- an environment without playwright must never
    # break the pipeline. The capture MODE + crop PROFILE (desktop by default)
    # come from `settings.screenshot` and are applied per-capture inside
    # step_screenshot. O provider não recebe lista de domínio nenhuma: quem
    # autoriza é a pesquisa de cada página (steps.build_official_links), e é o
    # MESMO provider que confirma a URL ao vivo (verify_url) e sonda se o
    # destino vive de anúncio (is_ad_monetized).
    screenshot = None
    if settings.run.official_screenshots:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401 - availability probe

            from funnelforge.adapters.screenshot_playwright import (
                PlaywrightScreenshotProvider,
            )

            screenshot = PlaywrightScreenshotProvider()
        except ImportError:
            screenshot = None

    # Verificador de URL ao vivo: SEMPRE ligado, sem depender de flag nenhuma e
    # sem Playwright. É ele que sustenta o gate factual e os links de
    # plataforma. UMA instância por run -> o cache dela é o que impede a mesma
    # URL de ser visitada 2-3x por página (write -> content_gate -> publish).
    url_verifier = HttpUrlVerifier()

    return Deps(
        llm=llm,
        research=research,
        image_gen=image_gen,
        image_proc=PillowImageProcessor(),
        publisher=publisher,
        loader=DocxBriefingLoader(),
        settings=settings,
        runner=runner,
        sitemap=HttpSitemapProvider(settings.site.domain),
        screenshot=screenshot,
        url_verifier=url_verifier,
    )


@app.command()
def run(briefing: Path, publish: bool = False, only: str | None = None) -> None:
    """LEGADO: roda o pipeline a partir de um briefing em texto (.docx/.txt).

    Este é o caminho ANTIGO, herdado do webgo: o briefing vira texto e o
    `step_extract` gasta uma chamada de LLM para reconstruir o plano. Para um
    card do Pautador, use `run-volc` — o plano já existe e é melhor.
    """
    settings = load_settings()
    run_pipeline(briefing, build_deps(settings), only=only,
                 publish=publish or settings.run.publish,
                 timestamp=datetime.now().strftime("%Y%m%d-%H%M%S"))


@app.command("run-volc")
def run_volc(arquitetura: Path, perfil: Path | None = None, publish: bool = False,
             only: str | None = None, timestamp: str | None = None) -> None:
    """Roda o funil a partir do `funnel_architecture` de um card do Pautador.

    `arquitetura` é o JSON da coluna `funnel_architecture` (ou a linha inteira
    do Supabase que a contém). O plano entra pronto — o que uma PESSOA aprovou
    no Pautador —, então nenhuma chamada de LLM é gasta com extração e nenhum
    campo se perde numa tabela de DOCX que o leitor não enxergava.

    `perfil` é o JSON que o backend monta com o que NÃO é do motor: o site
    (de `project_wordpress`), a credencial daquele projeto e o tema (do card).
    Sem ele, tudo vem do `config.yaml` — que é o caminho do desenvolvedor
    rodando à mão, não o do sistema. Ver `config/perfil.py`.

    `timestamp` fixa o sufixo do `run_id` (`<slug>-<timestamp>`). Existe para
    quem CHAMA conseguir achar a pasta do run sem adivinhar o slug — que o
    `dedupe_slugs` pode alterar. Sem ele, é a hora de agora, como sempre foi.
    """
    from funnelforge.adapters.briefing_volc import (
        carregar_arquitetura,
        plano_do_funnel_architecture,
    )

    from funnelforge.config.perfil import aplicar_perfil, termos_do_tema

    dados_perfil = json.loads(perfil.read_text(encoding="utf-8")) if perfil else None
    settings = aplicar_perfil(load_settings(), dados_perfil)
    dados = carregar_arquitetura(arquitetura)
    plan = plano_do_funnel_architecture(dados)
    deps = build_deps(settings)
    # Campo declarado em `Deps` — não atributo improvisado, para não sumir numa
    # refatoração. Alimenta o desempate do cross-funnel no sitemap, que sem isto
    # teria só o H1 da landing page para representar o funil inteiro.
    deps.tema_termos = termos_do_tema(dados_perfil)
    state = run_pipeline(
        None, deps, only=only, publish=publish or settings.run.publish,
        plan=plan, timestamp=timestamp or datetime.now().strftime("%Y%m%d-%H%M%S"))

    # PROCEDÊNCIA: a arquitetura de ORIGEM fica ao lado do `funnel_plan.json`
    # gerado. É também onde `intro_section`/`closing_section` continuam
    # existindo — eles não têm campo em `Page` e, de propósito, não entram no
    # esqueleto do redator (ver o docstring de `adapters/briefing_volc.py`).
    destino = deps.runner.runs_dir / state.run_id
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "funnel_architecture.json").write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(f"run: {state.run_id} — {len(plan.pages)} páginas vindas do card")


@app.command()
def resume(run_id: str, publish: bool = False, only: str | None = None,
           perfil: Path | None = None) -> None:
    """Resume a previously checkpointed run from `runs/<run_id>/state.json`,
    continuing from the first step that isn't already OK/RETRIED/FALLBACK.

    ⚠️ AS TRÊS OPÇÕES ABAIXO EXISTIAM EM `run-volc` E FALTAVAM AQUI — e a falta
    tornava impossível terminar um run que o Volc começou.

    `--only p4` retoma UMA página (número ou slug, ver `_select_pages`); sem
    ele, retomar uma página condenada por portão exigia arrastar o funil inteiro.

    `--publish` sobrepõe o `run.publish` do `config.yaml`, que é `false`. Sem
    ele, a retomada rodava build e parava — sem publicar e sem dizer por quê.

    `--perfil` é o que decide EM QUE SITE se publica. Medido em 18/08/2026: sem
    ele, o publicador nasce do `WP_APP_TOKEN` do `.env` do motor, que devolveu
    **401 Unauthorized** em `creditoup.com.br` — a credencial viva é a que o
    backend guarda cifrada em `project_wordpress` e entrega neste JSON.

    ⚠️ E o sintoma disso engana. O `except Exception` do laço grava a falha sob
    `page_N` (não `publish_pN`), o comando **sai com status 0** e não imprime
    nada. Quem olha o terminal vê sucesso; quem procura por `publish_p4` no
    estado não acha nada; a verdade está em `page_4`. Foi assim que o 401 acima
    passou despercebido por três tentativas.
    """
    from funnelforge.config.perfil import aplicar_perfil, termos_do_tema
    from funnelforge.domain.models import RunState

    dados_perfil = json.loads(perfil.read_text(encoding="utf-8")) if perfil else None
    settings = aplicar_perfil(load_settings(), dados_perfil)
    deps = build_deps(settings)
    deps.tema_termos = termos_do_tema(dados_perfil)

    state_path = Path("runs") / run_id / "state.json"
    state = RunState.from_json(state_path.read_text(encoding="utf-8"))
    run_pipeline(
        None, deps, only=only,
        publish=publish or settings.run.publish, resume_state=state,
    )


@app.command("print-url")
def print_url(url: str, destino: Path, mode: str = "desktop",
              full_page: bool = True, settle_ms: int = 2500) -> None:
    """Fotografa uma URL inteira, rolando, e grava o PNG em `destino`.

    ## Por que ela existe

    O `PlaywrightScreenshotProvider` foi escrito para provar a página OFICIAL de
    destino — o canal do governo, do banco. Ele não tem lista de domínio: exige
    HTTPS e nada mais. Apontá-lo para a NOSSA página publicada é a mesma
    chamada, e responde a pergunta que só o olho responde: *o tema montou o que
    o motor escreveu, ou quebrou no meio?*

    `full_page=True` com `scroll=True` é o par que importa. Rolar antes de
    fotografar CHUTA o lazy-load: sem isso, a foto de página inteira sai com os
    blocos de baixo em branco e parece defeito de conteúdo quando é só imagem
    que ainda não carregou.

    Imprime um JSON de uma linha com o status HTTP e `is_error_page` — a foto
    sozinha não distingue "página feia" de "404 com tema bonito".
    """
    from funnelforge.adapters.screenshot_playwright import PlaywrightScreenshotProvider

    r = PlaywrightScreenshotProvider().capture(
        url, mode=mode, full_page=full_page, scroll=True, settle_ms=settle_ms)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(r.png)
    typer.echo(json.dumps({
        "arquivo": destino.name, "bytes": len(r.png),
        "status": r.status, "is_error_page": r.is_error_page,
    }, ensure_ascii=False))


@app.command()
def models() -> None:
    """Print the model (+ fallbacks) configured for every pipeline step."""
    settings = load_settings()
    for name, cfg in settings.steps.items():
        typer.echo(f"{name}: {cfg.model}  fallbacks={cfg.fallbacks}")
