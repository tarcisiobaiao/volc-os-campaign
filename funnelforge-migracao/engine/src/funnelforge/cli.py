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
        "DATAFORSEO_LOGIN": secrets.dataforseo_login,
        "DATAFORSEO_PASSWORD": secrets.dataforseo_password or secrets.dataforseo_senha,
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
    from funnelforge.adapters.images_pillow import PillowImageProcessor
    from funnelforge.adapters.litellm_client import LiteLLMClient
    from funnelforge.adapters.research_perplexity import PerplexityResearch
    from funnelforge.adapters.sitemap_http import HttpSitemapProvider
    from funnelforge.adapters.url_verifier_http import HttpUrlVerifier
    from funnelforge.adapters.wordpress import WordPressPublisher

    from funnelforge.pipeline.budget import Orcamento

    llm = construir_llm(settings, LiteLLMClient())
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
    image_model = settings.run.image_model
    if image_model.startswith("gemini/") or image_model.startswith("gemini-"):
        if settings.secrets.gemini_api_key:
            from funnelforge.adapters.image_gemini import GeminiImageGenerator

            image_gen = GeminiImageGenerator(
                settings.secrets.gemini_api_key,
                model=image_model,
                quality=settings.run.image_quality,
            )
    elif settings.secrets.openai_api_key:
        from funnelforge.adapters.image_openai import OpenAIImageGenerator

        # IMAGE-GENERATION model/quality come from `run.image_model` /
        # `run.image_quality` -- NOT `steps["image"].model`, which is the
        # TEXT model that crafts the English image prompt (see
        # steps.py's step_image / RunConfig in config/settings.py).
        image_gen = OpenAIImageGenerator(
            settings.secrets.openai_api_key,
            model=image_model,
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

    attention_matrix = None
    if settings.run.inteligencia_pre_redacao:
        from funnelforge.adapters.attention_matrix import modulo_do_repo
        attention_matrix = modulo_do_repo(
            "backend/app/motor_pautas/sensores/dataforseo.py").Cliente(
                login=settings.secrets.dataforseo_login,
                senha=(settings.secrets.dataforseo_password
                       or settings.secrets.dataforseo_senha),
            )

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
        attention_matrix=attention_matrix,
    )


class _LiteLLMProibido:
    """`somente_plano`: o LiteLLM nem existe no run. Qualquer tentativa de
    chamada faturada é erro, não cobrança."""

    def complete(self, model, *a, **kw):
        raise RuntimeError(f"chamada faturada a '{model}' bloqueada (openai.somente_plano).")


def construir_llm(settings: Settings, litellm):
    """O cliente de LLM do motor. Modo `api_key`: o LiteLLM de sempre, por
    trás do roteador (que só desvia `chatgpt/<modelo>`). Modo `chatgpt_plan`:
    o roteador ganha o cliente da Responses API com a credencial do plano —
    e o run NÃO começa se a configuração permitir cobrança acidental."""
    from funnelforge.adapters.openai_responses import OpenAIResponsesClient, RoteadorDeLLM
    from funnelforge.config.settings import problemas_do_modo_openai

    if settings.openai.auth_mode == "chatgpt_plan" and not settings.openai.client_id:
        from funnelforge.adapters.credenciais import client_id_do_host
        settings.openai.client_id = client_id_do_host()
    problemas = problemas_do_modo_openai(settings)
    if problemas:
        raise typer.BadParameter("configuração OpenAI recusada:\n- " + "\n- ".join(problemas))
    plano = None
    if settings.openai.auth_mode == "chatgpt_plan":
        from funnelforge.adapters.credenciais import (
            ChatGPTPlanCredentialProvider,
            armazem_padrao,
        )
        plano = OpenAIResponsesClient(
            ChatGPTPlanCredentialProvider(armazem_padrao(settings.openai.armazenamento)))
    if settings.openai.auth_mode == "chatgpt_plan" and settings.openai.somente_plano:
        litellm = _LiteLLMProibido()
    return RoteadorDeLLM(litellm, plano,
                         allow_api_key_fallback=settings.openai.allow_api_key_fallback,
                         max_chamadas=settings.run.max_chamadas_llm)


def conferir_modelos_do_plano(settings: Settings, llm) -> None:
    """Antes de QUALQUER chamada paga: todo modelo `chatgpt/*` dos passos tem
    de estar na lista de modelos da conta conectada. Falta um -> o run para,
    dizendo qual, e nenhum outro modelo é usado no lugar."""
    from funnelforge.config.settings import PREFIXO_DO_PLANO
    plano = getattr(llm, "plano", None)
    if plano is None:
        return
    pedidos = sorted({p.model.removeprefix(PREFIXO_DO_PLANO) for p in settings.steps.values()
                      if p.model.startswith(PREFIXO_DO_PLANO)})
    disponiveis = set(plano.modelos_disponiveis())
    faltando = [m for m in pedidos if m not in disponiveis]
    if faltando:
        raise typer.BadParameter(
            f"modelo(s) {faltando} indisponível(is) para a conta ChatGPT conectada. "
            f"Disponíveis: {sorted(disponiveis) or 'nenhum listado'}. Nada foi chamado.")


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
             only: str | None = None, timestamp: str | None = None,
             card_pre_arquitetura: Path | None = typer.Option(
                 None, "--card-pre-arquitetura", help="Card completo para pesquisar intenção "
                 "antes de arquitetar, usando o mesmo motor. Não altera o card original."),
             canario: bool = typer.Option(False, "--canario",
                                          help="Sem publicação, sem publisher, sem imagem, "
                                               "teto de chamadas e recibo em runs-canario/."),
             fatos_de: Path | None = typer.Option(
                 None, "--fatos-de", help="Só com --canario: state.json de um run anterior "
                                          "cujo inventário factual substitui a pesquisa."),
             somente_dossie: bool = typer.Option(
                 False, "--somente-dossie", help="Só com --canario: para depois do portão de "
                                                 "cobertura do dossiê (nenhuma redação)."),
             dossie_de: Path | None = typer.Option(
                 None, "--dossie-de", help="Só com --canario: state.json de um run com dossiê "
                                           "congelado; retoma a redação SEM pesquisar de novo."),
             hints_de: Path | None = typer.Option(
                 None, "--hints-de", help="Só com --canario: JSON de hints do operador (URL + "
                                          "afirmação), conferidos no documento, nunca aceitos "
                                          "como fato pronto.")
             ) -> None:
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
    if canario:
        if publish:
            raise typer.BadParameter("--canario não publica: tire --publish.")
        settings.run.publish = False
        settings.run.publish_status = "draft"
        settings.run.imagens_habilitadas = False
        settings.run.max_chamadas_llm = settings.run.max_chamadas_llm or 40
    dados = carregar_arquitetura(arquitetura)
    card = json.loads(card_pre_arquitetura.read_text()) if card_pre_arquitetura else None
    if card is not None:
        settings.run.dossie_factual = True
        settings.run.inteligencia_pre_redacao = True
        if fatos_de is not None or dossie_de is not None:
            raise typer.BadParameter("card pré-arquitetura exige pesquisa anterior ao plano")
    plan = None if card is not None else plano_do_funnel_architecture(dados)
    deps = build_deps(settings)
    if canario:
        # Trava dupla: mesmo com credencial WP no ambiente, nada publica.
        deps.publisher = None
        deps.image_gen = None
        deps.runner.runs_dir = Path("runs-canario")
    conferir_modelos_do_plano(settings, deps.llm)
    _ligar_bucket(deps)
    if hints_de is not None:
        deps.hints_do_operador = json.loads(hints_de.read_text(encoding="utf-8"))
    estado_inicial = None
    if (somente_dossie or dossie_de is not None or hints_de is not None) and not canario:
        raise typer.BadParameter("--somente-dossie/--dossie-de/--hints-de só valem com --canario.")
    if dossie_de is not None:
        from funnelforge.domain.models import RunState
        estado_inicial = RunState.from_json(dossie_de.read_text(encoding="utf-8"))
        if not (estado_inicial.dossie and estado_inicial.dossie_sha256):
            raise typer.BadParameter("--dossie-de: o estado não tem dossiê congelado.")
    if fatos_de is not None:
        if not canario:
            raise typer.BadParameter("--fatos-de só vale com --canario.")
        from funnelforge.domain.models import RunState
        from funnelforge.pipeline.recibo_canario import pre_carregar_fatos
        timestamp = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
        estado_inicial = pre_carregar_fatos(
            plan, deps, RunState.from_json(fatos_de.read_text(encoding="utf-8")), timestamp)
    # Campo declarado em `Deps` — não atributo improvisado, para não sumir numa
    # refatoração. Alimenta o desempate do cross-funnel no sitemap, que sem isto
    # teria só o H1 da landing page para representar o funil inteiro.
    deps.tema_termos = termos_do_tema(dados_perfil)
    state = run_pipeline(
        None, deps, only=only, publish=publish or settings.run.publish,
        plan=plan, resume_state=estado_inicial, ate_o_dossie=somente_dossie,
        card_pre_arquitetura=card,
        timestamp=timestamp or datetime.now().strftime("%Y%m%d-%H%M%S"))

    # PROCEDÊNCIA: a arquitetura de ORIGEM fica ao lado do `funnel_plan.json`
    # gerado. É também onde `intro_section`/`closing_section` continuam
    # existindo — eles não têm campo em `Page` e, de propósito, não entram no
    # esqueleto do redator (ver o docstring de `adapters/briefing_volc.py`).
    destino = deps.runner.runs_dir / state.run_id
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "funnel_architecture.json").write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    if canario:
        from funnelforge.pipeline.recibo_canario import recibo_do_canario
        recibo = recibo_do_canario(state, settings, publisher_ligado=deps.publisher is not None,
                                   image_gen_ligado=deps.image_gen is not None,
                                   chamadas=getattr(deps.llm, "chamadas", 0))
        nome = "recibo_canario_redacao.json" if dossie_de is not None else "recibo_canario.json"
        (destino / nome).write_text(
            json.dumps(recibo, ensure_ascii=False, indent=2), encoding="utf-8")
        typer.echo(f"recibo: {destino / nome} — nada publicado: "
                   f"{recibo['publicacao']['nada_publicado']}")
    typer.echo(f"run: {state.run_id} — {len(state.plan.pages) if state.plan else 0} páginas")


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
    from funnelforge.config.perfil import (
        aplicar_perfil,
        configuracao_efetiva_do_run,
        termos_do_tema,
    )
    from funnelforge.domain.models import RunState

    dados_perfil = json.loads(perfil.read_text(encoding="utf-8")) if perfil else None
    base = load_settings()
    snapshot = Path("runs") / run_id / "config_snapshot.json"
    if snapshot.exists():
        # A retomada roda com a configuração EFETIVA do run (modelos, workers,
        # prints, tetos); do perfil só valem site e credencial.
        base = configuracao_efetiva_do_run(
            base, json.loads(snapshot.read_text(encoding="utf-8")))
        if dados_perfil:
            dados_perfil = {k: v for k, v in dados_perfil.items() if k != "preset"}
    settings = aplicar_perfil(base, dados_perfil)
    deps = build_deps(settings)
    deps.tema_termos = termos_do_tema(dados_perfil)
    _ligar_bucket(deps)

    state_path = Path("runs") / run_id / "state.json"
    state = RunState.from_json(state_path.read_text(encoding="utf-8"))
    run_pipeline(
        None, deps, only=only,
        publish=publish or settings.run.publish, resume_state=state,
    )


@app.command("reconstruir-lp")
def reconstruir_lp(run_id: str, perfil: Path | None = None) -> None:
    """Refaz SÓ o build da LP de um run histórico com o template atual.

    Para o `lp_template_desatualizado` do portão final: LP montada antes de o
    template mudar. Lê `runs/<run_id>/state.json`, roda `step_build` da LP
    sobre o rascunho já aprovado e grava o estado. Não chama modelo, não
    publica e não toca WordPress; a publicação continua sendo `resume
    --publish`, que passa de novo pelo portão final."""
    from funnelforge.config.perfil import aplicar_perfil, configuracao_efetiva_do_run
    from funnelforge.domain.models import RunState, StepStatus
    from funnelforge.pipeline.steps import reconstruir_build_da_lp

    dados_perfil = json.loads(perfil.read_text(encoding="utf-8")) if perfil else None
    base = load_settings()
    snapshot = Path("runs") / run_id / "config_snapshot.json"
    if snapshot.exists():
        base = configuracao_efetiva_do_run(
            base, json.loads(snapshot.read_text(encoding="utf-8")))
        if dados_perfil:
            dados_perfil = {k: v for k, v in dados_perfil.items() if k != "preset"}
    deps = build_deps(aplicar_perfil(base, dados_perfil))
    state_path = Path("runs") / run_id / "state.json"
    state = RunState.from_json(state_path.read_text(encoding="utf-8"))
    resultado = reconstruir_build_da_lp(state, deps)
    deps.runner.checkpoint(state.run_id, state.to_json())
    typer.echo(f"build da LP: {resultado.status.value} "
               f"{[i.code for i in resultado.issues]}")
    if resultado.status is StepStatus.FAILED:
        raise typer.Exit(code=1)


def _ligar_bucket(deps) -> None:
    """O bucket temporário do run: cada documento baixado uma vez, com recibo.
    O cache compartilhado fica ao lado dos runs; a cópia de cada run não expira."""
    from funnelforge.adapters.bucket import BucketDoRun

    deps.bucket = BucketDoRun(cache=deps.runner.runs_dir / "_cache_documentos")
    deps.ler_documento = deps.bucket.documento


def _cliente_do_revisor():
    """O cliente de LLM do `revisar` (isolado para o teste trocar por um falso)."""
    from funnelforge.adapters.litellm_client import LiteLLMClient

    return LiteLLMClient()


@app.command()
def decidir(
    run_id: str,
    pagina: int = typer.Option(..., "--pagina", help="número da página no run"),
    decisao: str = typer.Option(..., "--decisao", help="aprovar | rejeitar"),
    sha256: str = typer.Option(..., "--sha256", help="sha256 do conteúdo lido (revisao.json)"),
    nota: str = typer.Option("", "--nota"),
    quem: str = typer.Option("operador", "--quem"),
    runs_dir: Path = typer.Option(Path("runs"), "--runs-dir"),
) -> None:
    """SAÍDA DA REVISÃO HUMANA (ramo editorial novo): grava no `state.json` a
    decisão da pessoa sobre uma página, PRESA ao sha256 do conteúdo que ela leu.

    Não publica nada. O próximo `resume` aplica a decisão: `aprovar` com o hash
    igual ao conteúdo atual gera o recibo e libera a publicação (como rascunho);
    `rejeitar` fecha a página. Hash diferente do conteúdo atual é recusado aqui
    mesmo — a pessoa aprova o que leu, não outra versão."""
    from funnelforge.domain.models import RunState
    from funnelforge.pipeline.revisao import decidir_pagina

    caminho = runs_dir / run_id / "state.json"
    state = RunState.from_json(caminho.read_text(encoding="utf-8"))
    try:
        registro = decidir_pagina(state, pagina, decisao=decisao, sha256=sha256,
                                  nota=nota, quem=quem)
    except ValueError as exc:
        typer.echo(f"decisão recusada: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    temporario = caminho.with_name("state.json.tmp")
    temporario.write_text(state.to_json(), encoding="utf-8")
    temporario.replace(caminho)
    typer.echo(json.dumps({"run": run_id, "pagina": pagina, **registro}, ensure_ascii=False))


@app.command()
def revisar(
    conteudo: Path,
    briefing: Path = typer.Option(..., "--briefing", help="briefing-v1 (JSON) da página"),
    contexto: Path | None = typer.Option(None, "--contexto",
                                         help="fatos, destinos, origem, termos (JSON)"),
    saida: Path | None = typer.Option(None, "--saida"),
    config: Path = typer.Option(Path("config.yaml"), "--config"),
    env: Path = typer.Option(Path(".env"), "--env"),
) -> None:
    """Revisa conteúdo JÁ PUBLICADO exportado em arquivo (.html ou .json), com o
    mesmo revisor e as mesmas travas do pipeline. Grava revisao.json e
    patches.json. NÃO fala com o WordPress e NÃO publica: os patches são um
    lote para aprovação humana. Faz chamada paga ao modelo do passo `revisor`
    (no máximo 2), sob o teto por página do config."""
    from funnelforge.pipeline.budget import Orcamento
    from funnelforge.pipeline.revisao_avulsa import revisar_arquivo

    settings = load_settings(env, config)
    cfg = settings.steps.get("revisor")
    if cfg is None:
        typer.echo("passo 'revisor' ausente no config (steps.revisor)", err=True)
        raise typer.Exit(code=2)
    _export_secrets(settings.secrets)
    destino = saida or conteudo.with_name(f"{conteudo.stem}_revisao")
    runner = Runner(llm=_cliente_do_revisor(), max_retries=settings.run.max_retries,
                    runs_dir=destino,
                    budget=Orcamento(teto_run_usd=settings.budget.max_usd_per_page,
                                     teto_pagina_usd=settings.budget.max_usd_per_page))
    resumo = revisar_arquivo(conteudo, briefing, contexto, destino, runner=runner, cfg=cfg)
    typer.echo(json.dumps(resumo, ensure_ascii=False))


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


# ---------------------------------------------------------------------------
# AUTENTICAÇÃO — "Sign in with ChatGPT" (OAuth oficial, perfil próprio do VOLC)
# ---------------------------------------------------------------------------

auth_app = typer.Typer(add_completion=False, help="Conectar o motor ao plano ChatGPT.")
app.add_typer(auth_app, name="auth")

_COMO_OBTER_CLIENT_ID = (
    "Sem client_id do VOLC configurado (openai.client_id no config.yaml).\n"
    "Caminhos oficiais (https://developers.openai.com/siwc):\n"
    "  1. App pago ou hospedado remotamente: formulário de interesse\n"
    "     https://openai.com/form/sign-in-with-chatgpt-interest/\n"
    "  2. App open-source/hospedado localmente: registro dinâmico no primeiro login\n"
    "     (funnelforge auth login --provider chatgpt --registrar-dinamico), que emite o\n"
    "     client_id próprio deste app (oaiapp_...). Use só se o VOLC se enquadrar.\n"
    "Configure apenas o client_id PÚBLICO; não há client_secret neste fluxo.")


def _settings_sem_segredos() -> Settings:
    # Os comandos de autenticação não precisam de nenhuma chave do `.env`.
    return load_settings(env_path=Path(os.devnull))


@auth_app.command("login")
def auth_login(provider: str = typer.Option("chatgpt", "--provider"),
               client_id: str = typer.Option("", "--client-id"),
               registrar_dinamico: bool = typer.Option(False, "--registrar-dinamico"),
               porta: int = typer.Option(1455, "--porta"),
               timeout_s: int = typer.Option(300, "--timeout"),
               sem_navegador: bool = typer.Option(False, "--sem-navegador")) -> None:
    """Abre o consentimento no navegador e guarda a sessão deste host."""
    import webbrowser

    from funnelforge.adapters import chatgpt_oauth as oa
    from funnelforge.adapters.credenciais import (
        ChatGPTPlanCredentialProvider,
        armazem_padrao,
        client_id_do_host,
        gravar_client_id_do_host,
        id_do_host,
    )

    if provider != "chatgpt":
        raise typer.BadParameter("único provedor suportado: chatgpt")
    settings = _settings_sem_segredos()
    cid = client_id or settings.openai.client_id or client_id_do_host()
    if registrar_dinamico and cid:
        raise typer.BadParameter("registro dinâmico é só para o PRIMEIRO login, sem client_id.")
    if not cid and not registrar_dinamico:
        typer.echo(_COMO_OBTER_CLIENT_ID)
        raise typer.Exit(2)
    host = id_do_host() if registrar_dinamico else None
    verifier, challenge = oa.gerar_pkce()
    state, nonce = oa.gerar_state(), oa.gerar_state()
    redirect = oa.redirect_uri(porta)
    url = oa.url_de_autorizacao(client_id=cid, redirect=redirect, state=state, nonce=nonce,
                                challenge=challenge, host_id=host)
    typer.echo("Conclua o consentimento no navegador. Se ele não abrir, use esta URL:")
    typer.echo(url)
    if not sem_navegador:
        webbrowser.open(url)
    try:
        cb = oa.esperar_callback(porta, state, registrando=bool(host), timeout_s=timeout_s)
        emitido = cb["client_id"] or cid
        if host and emitido:
            # Público e emitido UMA vez para este host: guardado já, para não se
            # perder se a troca de código ou a validação falharem depois.
            gravar_client_id_do_host(emitido)
        typer.echo("Callback recebido; trocando o código e validando o ID token...")
        token = oa.trocar_codigo(client_id=emitido, code=cb["code"], verifier=verifier,
                                 redirect=redirect)
        claims = oa.validar_id_token(token.id_token, client_id=emitido, nonce=nonce)
        token.conta = oa.mascarar_conta(str(claims.get("email") or ""), str(claims.get("sub") or ""))
    except oa.ErroDeAutenticacao as exc:
        typer.echo(f"Login não concluído [{exc.codigo}]: {exc}")
        raise typer.Exit(1)
    armazem = armazem_padrao(settings.openai.armazenamento)
    armazem.gravar(token.to_dict())
    typer.echo(json.dumps(ChatGPTPlanCredentialProvider(armazem).status(), ensure_ascii=False,
                          indent=2))
    if host:
        typer.echo(f"client_id emitido para o VOLC: {emitido[:12]}… — guardado neste host "
                   "(fora do repositório); é público, não é segredo.")


@auth_app.command("status")
def auth_status() -> None:
    """Mostra o modo e a sessão, nunca o token."""
    from funnelforge.adapters.credenciais import (
        ApiKeyCredentialProvider,
        ChatGPTPlanCredentialProvider,
        armazem_padrao,
    )
    settings = _settings_sem_segredos()
    # O modo CONFIGURADO e, separado, a sessão ChatGPT deste host: uma não
    # implica a outra (dá para estar conectado e o motor seguir em api_key).
    info = {
        "modo_configurado": settings.openai.auth_mode,
        # Só a PRESENÇA da variável no ambiente; o `.env` não é lido aqui.
        "api_key": ApiKeyCredentialProvider().status(),
        "sessao_chatgpt": ChatGPTPlanCredentialProvider(
            armazem_padrao(settings.openai.armazenamento)).status(),
    }
    typer.echo(json.dumps(info, ensure_ascii=False, indent=2))


@auth_app.command("logout")
def auth_logout() -> None:
    """Apaga a sessão LOCAL do ChatGPT neste host."""
    from funnelforge.adapters.credenciais import ChatGPTPlanCredentialProvider, armazem_padrao
    settings = _settings_sem_segredos()
    ChatGPTPlanCredentialProvider(armazem_padrao(settings.openai.armazenamento)).logout()
    typer.echo("Sessão local removida. Para desconectar o app da conta, use as "
               "configurações do ChatGPT (a revogação remota não é documentada).")
