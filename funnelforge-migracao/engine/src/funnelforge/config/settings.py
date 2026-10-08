# funnel-forge/src/funnelforge/config/settings.py
from __future__ import annotations
from pathlib import Path
from typing import Literal
import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, Field, field_validator, model_validator


class Secrets(BaseModel):
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    anthropic_api_key: str | None = None
    perplexity_api_key: str | None = None
    wp_url: str | None = None
    wp_user: str | None = None
    wp_app_token: str | None = None


class RunConfig(BaseModel):
    # Opt-in per funnel; the URL still requires page-specific research evidence.
    terminal_exit_policy: Literal["cross_funnel", "official"] = "cross_funnel"
    max_retries: int = 2
    publish: bool = False
    # A fact verified before this window is stale for a new publication.  The
    # research contract compares ``verificado_em`` against the run date.
    research_max_age_days: int = 45
    # TETO RÍGIDO de chamadas de LLM por run (0 = sem teto). O canário usa:
    # ao atingir, o run para com mensagem clara em vez de seguir chamando.
    max_chamadas_llm: int = 0
    # Imagens (prompt + geração + revisão). Desligado, nenhuma etapa de imagem
    # roda — o canário textual marca a etapa como "não exercitada".
    imagens_habilitadas: bool = True
    # DOSSIÊ FACTUAL pré-redação (só com jornada): uma pesquisa do funil
    # (passo `steps.dossie`), portão de cobertura e fatos congelados por hash.
    dossie_factual: bool = False
    # Páginas em paralelo depois do dossiê. 1 = o laço serial de sempre.
    page_workers: int = Field(default=1, ge=1, le=3)
    # PRODUÇÃO RÁPIDA: uma chamada de redação por página (o redator de sempre,
    # com a doutrina de escrita natural no prompt), SEO, fatos usados, links e
    # pacote da página por CÓDIGO, sem juiz, sem widget por LLM, sem
    # classificador de engajamento, e UMA revisão global do funil no fim.
    perfil: Literal["completo", "rapido"] = "completo"
    # RETENTATIVA DA PESQUISA (Frente 3). Antes disto a pesquisa tinha ZERO
    # retentativa: um 429 do provedor devolvia `sparse=True`, o gate factual
    # reprovava e a página inteira morria — depois de o briefing/extract já
    # terem sido pagos. A pesquisa é o insumo mais barato do funil e o único
    # que, faltando, condena todo o resto; por isso ela ganha o maior número
    # de tentativas do pipeline.
    #
    # Só retenta o que pode mudar: falta de fontes, contrato factual furado,
    # fonte que não resolveu, erro transitório do provedor. NÃO retenta
    # `fact_source_verifier_missing` — não existe verificador ao vivo ligado,
    # e nenhuma pesquisa nova liga o Chromium.
    research_max_attempts: int = 3
    research_backoff_s: float = 4.0        # 4s, 8s, 16s...
    research_backoff_max_s: float = 60.0
    # FORMATO DO GRAFO DE ENTRADA (a decisão de desenho, não um detalhe).
    #
    # `presell_hubs` = quantos hubs qualificadores o funil tem.
    #   1 (padrão)  UM hub, escrito de verdade. A LP abre com ele no primeiro
    #               botão e manda os demais direto para as soluções.
    #   3           o desenho antigo: `expand_presell_hubs` CLONA a única
    #               pré-sell mapeada em -pr1/-pr2/-pr3, com a mesma
    #               `main_content_structure`. Três páginas, um esqueleto só.
    #
    # Por que 1 virou o padrão: medido em campo, >80% dos cliques da LP vão
    # para o PRIMEIRO botão. Os outros dois hubs recebiam pouco tráfego e
    # custavam três páginas quase iguais — o que também obrigou a afrouxar o
    # `hub_distinction_threshold` do validador de unicidade, porque funil
    # homogêneo fazia os clones parecerem duplicata (e eram, por construção).
    #
    # O caminho de 3 hubs continua inteiro e testado. Se um nicho provar que
    # três ângulos ganham, é trocar este número — nada de reescrever grafo.
    presell_hubs: int = 1
    # Quantas SOLUÇÕES ganham botão DIRETO na LP, logo depois do hub.
    # Com presell_hubs=1 e lp_direct_solutions=2 a LP fica: [hub, p1, p2],
    # mantendo os 3 CTAs de sempre. As soluções sem botão direto continuam
    # alcançáveis pelo hub (que faz fan-out para todas) e pelo encadeamento
    # forward entre soluções. 0 desliga e restaura a LP → só hubs.
    lp_direct_solutions: int = 2
    hero_image: bool = False
    # Generate a FEATURED image for interior /rec posts (SOLUTION/PRESELL) --
    # the n8n-style flow: generate -> upload to WP media -> set featured_media
    # (the post thumbnail) AND drop a mid-content wp:image after the first
    # heading. Distinct from `hero_image` (the LP's Elementor hero); an
    # interior post never carries a hero, so its image gate keys on THIS flag
    # (see steps.py's `image_wanted` / step_publish). Opt-in, off by default.
    featured_image: bool = False
    # IMAGE-GENERATION model/quality (OpenAIImageGenerator, wired in cli.py's
    # build_deps). Distinct from `steps.image.model`, which is the TEXT
    # model that CRAFTS the English image-generation prompt via
    # `run_llm_step` (see steps.py's step_image) -- conflating the two used
    # to send a chat-completion call to an image-only model and crash the
    # whole page (smoke-test finding).
    image_model: str = "gpt-image-2"
    image_quality: str = "medium"
    # Image dimensions per surface. The LP HERO is a VERTICAL background (9:16
    # feel) with a black-gradient bottom reserved for the title/buttons overlay
    # (see prompts/image_prompt_lp.jinja) -> portrait size. Interior /rec
    # featured images are the standard WordPress landscape thumbnail.
    image_size_lp: str = "1024x1536"
    image_size_post: str = "1536x1024"
    # WordPress post/page status used by step_publish. Defaults to "draft" so
    # the whole funnel lands in WP as reviewable drafts (the n8n-style flow:
    # generate -> draft -> human reviews and clicks publish), never straight
    # to "publish". Set to "publish" here only for a fully-automated go-live.
    #
    # VOCABULÁRIO FECHADO (B5): os status que o WordPress aceita num post. Um
    # valor fora dele era gravado verbatim no "pino" final do status e ninguém
    # conferia. No ramo editorial novo, só `draft` é aceito (step_publish).
    publish_status: Literal["draft", "pending", "private", "future", "publish"] = "draft"
    # SCREENSHOTS of the official destination pages (CARD-0005). Opt-in feature
    # flag (default OFF) for staged rollout: when true AND the optional
    # `screenshots` extra (playwright) is installed, cli.build_deps wires a
    # PlaywrightScreenshotProvider and step_screenshot captures each SOLUTION
    # page's official_links in the `screenshot.mode` viewport (desktop by
    # default), embedding them after the matching link at publish. Flag OFF or
    # playwright ABSENT -> deps.screenshot
    # is None and the step no-ops (pipeline behaves exactly as before).
    official_screenshots: bool = False
    # Max official screenshots captured per SOLUTION page (caps official_links).
    screenshots_max_per_page: int = 2
    # INTERACTIVE WIDGETS on SOLUTION pages (CARD-0013). Opt-in feature flag,
    # default OFF: the widget subsystem is executable code injected into a
    # published page, so rollout is a deliberate human decision (a conscious
    # divergence from the "default SOTA" of official_screenshots). When true, the
    # per-page pipeline runs step_widget AFTER build and BEFORE publish -- it asks
    # a generator prompt for ONE self-contained wp:html block, runs a hard Python
    # sanitization battery (validators/checks.py's sanitize_widget_block), and
    # injects it before the 3rd H2 (fallbacks FAQ/end) -- all 100% fail-safe (any
    # failure leaves the article intact, never fails the page). Flag OFF -> the
    # step never runs and the pipeline behaves exactly as before.
    widgets_enabled: bool = False
    # RAMO EDITORIAL NOVO (reforma de 30/09/2026): briefing persuasivo por
    # página, prompts de redação v2 a partir dele, SEO antes da revisão. Padrão
    # DESLIGADO: com false, prompts renderizados e ordem de passos ficam
    # idênticos aos de antes (tests/test_editorial_v2_flag_off_identico.py).
    # O perfil do run liga por funil (`tema.editorial_v2`, ver
    # config/perfil.py) e a arquitetura do card também pode ligar.
    editorial_v2: bool = False

    @model_validator(mode="after")
    def _paralelo_exige_dossie(self) -> "RunConfig":
        # A pesquisa é o gasto faturado e só o dossiê a tira de dentro do laço:
        # páginas em paralelo sem ele pesquisariam em paralelo.
        if self.page_workers > 1 and not self.dossie_factual:
            raise ValueError("run.page_workers > 1 exige run.dossie_factual: true")
        return self


class AuthorConfig(BaseModel):
    name: str
    credential: str = ""
    profile_slug: str = ""


class SiteConfig(BaseModel):
    domain: str
    post_type: str = "rec"
    # WordPress REST base for the LANDING PAGE. The winning funnel serves LPs
    # as a custom post type at /r/<slug> (Elementor-enabled), NOT as a generic
    # /pages entry -- so the LP Elementor draft is created under this type.
    lp_post_type: str = "pages"
    author_name: str = ""
    author_credential: str = ""
    cnpj: str = ""
    # O RODAPÉ INSTITUCIONAL QUE O TEMA DO WORDPRESS RENDERIZA EM TODA PÁGINA.
    #
    # ⚠️ É DECLARAÇÃO, não observação. O motor produz o CORPO; identidade,
    # aviso de não-vínculo e divulgação de monetização vêm do tema, e nenhum
    # artefato local os contém. Sem este campo, o portão do destino pago
    # reprovaria toda LP por `IDENTIDADE_OPERADOR_AUSENTE` +
    # `AVISO_NAO_OFICIAL_AUSENTE` + `DIVULGACAO_DE_MONETIZACAO_AUSENTE` — e um
    # portão que reprova 100% das páginas é um portão que alguém desliga.
    #
    # A declaração é rastreável: o texto em `config.yaml` é a transcrição do
    # rodapé MEDIDO na captura preservada de `/r/fgts-saque-aniversario/`
    # (`docs/closure/.../evidence-public/common_desktop-7c674d1d7daf.html`), a
    # mesma URL cujos bloqueios em `GATE-RECEIPTS.json` não incluem nenhum
    # daqueles três códigos.
    #
    # VAZIO (o padrão) é fail-closed de propósito: um site novo, cujo rodapé
    # ninguém mediu, reprova por identidade ausente — que é a verdade.
    rodape_institucional: str = ""
    # Só declare true quando o template do site mantiver o footer em todas as páginas.
    rodape_institucional_persistente: bool = False
    authors: list[AuthorConfig] = []
    # PREFERENCIA de canal oficial -- nunca autorizacao. Aceita dominio
    # ("caixa.gov.br") ou o NOME do orgao/empresa como vem do `official_source`
    # da entidade no VOLC O.S. ("iFood", "DIAN", "Caixa Economica Federal"),
    # porque aquele campo e um nome, nao uma URL. Efeito unico: um candidato da
    # pesquisa que casa com a preferencia sobe na fila dos links oficiais. Nao
    # casar nao reprova nada; a lista VAZIA (padrao) e o caso normal.
    #
    # Substitui `allowed_external`, que era trava dura em build_official_links,
    # em resolve_route(external_official) e no guard do screenshot -- e por isso
    # impedia qualquer funil cujo canal oficial nao fosse governamental.
    # Configs antigos que ainda tragam `allowed_external`/`official_entry_points`
    # continuam carregando: o pydantic ignora chave desconhecida.
    official_preference: list[str] = []
    # DENYLIST opcional (nao e allowlist): hosts que nunca podem receber link,
    # mesmo aparecendo na pesquisa. Vazia por padrao. Nao estar aqui nao
    # autoriza ninguem -- quem autoriza e a evidencia da pesquisa.
    blocked_hosts: list[str] = []
    # Bare LP slugs of OTHER same-domain funnels (cross-funnel exit); never invented by an LLM.
    cross_funnel_lps: list[str] = []

    @field_validator("cnpj")
    @classmethod
    def cnpj_must_be_real_when_configured(cls, value: str) -> str:
        """Reject placeholders and invalid check digits at config load time."""
        digits = "".join(ch for ch in value if ch.isdigit())
        if not digits:
            return ""
        if len(digits) != 14 or len(set(digits)) == 1:
            raise ValueError("CNPJ configurado é placeholder ou tem formato inválido")

        def _digit(base: str, weights: list[int]) -> str:
            remainder = sum(int(n) * w for n, w in zip(base, weights)) % 11
            return str(0 if remainder < 2 else 11 - remainder)

        d1 = _digit(digits[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
        d2 = _digit(digits[:12] + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
        if digits[-2:] != d1 + d2:
            raise ValueError("CNPJ configurado falhou na validação dos dígitos")
        return value


class StepConfig(BaseModel):
    model: str
    fallbacks: list[str] = []
    temperature: float = 0.7
    validators: list[str] = []
    web_search: bool = False
    # Esforço de raciocínio pedido ao modelo (Responses API). None = não envia.
    reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    # Só a pesquisa do dossiê pelo plano (`chatgpt_plan_web_search`): filtro de
    # domínios do web_search. Vazio = sem filtro.
    dominios_permitidos: list[str] = []


#: Prefixo de modelo que roteia o passo para a Responses API com o token do
#: PLANO ChatGPT ("Sign in with ChatGPT"). Sem o prefixo, o passo segue no
#: LiteLLM com API key, como sempre.
PREFIXO_DO_PLANO = "chatgpt/"


class OpenAIConfig(BaseModel):
    """AUTENTICAÇÃO OpenAI do motor. `api_key` é o comportamento de sempre.

    `chatgpt_plan` usa o OAuth oficial "Sign in with ChatGPT" e a Responses
    API com o token do plano. `client_id` é o identificador PÚBLICO do VOLC
    (`oaiapp_...`), nunca um segredo; sem ele não há login. Os modelos abaixo,
    quando preenchidos com `chatgpt_plan`, viram `chatgpt/<modelo>` nos passos
    correspondentes — a troca fica escrita no `config_snapshot.json`.
    `allow_api_key_fallback=false` proíbe qualquer passo do plano de cair para
    um modelo faturado por API."""
    auth_mode: Literal["api_key", "chatgpt_plan"] = "api_key"
    client_id: str = ""
    writer_model: str = ""
    judge_model: str = ""
    reviewer_model: str = ""
    reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    allow_api_key_fallback: bool = False
    armazenamento: Literal["keychain", "arquivo"] = "keychain"
    # Exige que TODO passo de LLM use o plano: um passo faturado por API
    # impede o run de começar (canário sem cobrança acidental).
    somente_plano: bool = False


class RoutingSpecConfig(BaseModel):
    allowed_targets: list[str] = []
    required_targets: list[str] = []
    forbidden_targets: list[str] = []
    cta_min: int = 0
    cta_max: int = 99
    requires_external_official: bool = False
    requires_cross_funnel_exit: bool = False
    distinct_targets: bool = False
    anchor_congruent: bool = True


class AdSlotConfig(BaseModel):
    slot_id: str
    placement: str
    sizes: list[str] = []
    min_height_px: int = 0
    refresh_eligible: bool = False
    source_key: str = ""


class VignetteConfig(BaseModel):
    enabled: bool = True
    max_per_window: int = 1
    window_seconds: int = 600


class AdsConfig(BaseModel):
    vignette: VignetteConfig = VignetteConfig()
    slots: dict[str, list[AdSlotConfig]] = {}
    # Paragraph numbers used by the live ad inserter (1-based).  They are an
    # input to structural validation, not an accidental property discovered
    # after publication.
    paragraph_anchors: list[int] = []


class IndexPolicyConfig(BaseModel):
    robots: str = "noindex,follow"


class UniquenessConfig(BaseModel):
    jaccard_threshold: float = 0.35
    # Jaccard minimum for the CARD-0007 opening_line_unique validator, which
    # compares a PRESELL draft's opening CTA line against every prior one in
    # the cross-run phrase_registry -- a much shorter string than a full page,
    # so it gets its own (higher) threshold rather than reusing jaccard_threshold.
    opening_line_threshold: float = 0.6
    # Jaccard minimum for PRESELL-vs-PRESELL comparison (hub distinctness +
    # cross-hub duplicate check). The 3 NEUTRAL hubs preview the SAME 3
    # solutions, so they legitimately SHARE that solution vocabulary +
    # compliance boilerplate -- a homogeneous-solution funnel (e.g. all-FGTS)
    # lands near ~0.4 by design. The strict 0.35 fights that; this higher bar
    # flags only near-identical (copy-paste) hubs (a real doorway) while passing
    # 3 genuinely distinct framings. Hero-neutrality is guarded separately.
    hub_distinction_threshold: float = 0.6


class BudgetConfig(BaseModel):
    """Teto de gasto do run — rede de segurança, não orçamento apertado.

    Medido em campo: ~US$ 0,45 por página e ~US$ 2,10 num funil de 5 páginas.
    Os padrões abaixo ficam ~2,5x acima disso de propósito: o teto existe para
    matar laço de retentativa em fuga e fallback caro em cascata, NUNCA para
    reprovar trabalho bom. Zero em qualquer campo desliga aquele teto.

    `image_price_usd` é PREÇO DECLARADO, não medido: a imagem sai por httpx cru
    (`adapters/image_openai.py`) e a API de imagens não devolve custo, então sem
    esta tabela a geração era a única despesa invisível do ledger. Confira os
    valores na página de preços do provedor antes de confiar no número.
    """

    max_usd_per_run: float = 6.00
    max_usd_per_page: float = 1.20
    image_price_usd: dict[str, float] = {"low": 0.02, "medium": 0.06, "high": 0.20}
    image_price_fallback_usd: float = 0.06


class ScreenshotConfig(BaseModel):
    """Official-page screenshot wiring (Task 9 / B5). Drives step_screenshot's
    capture + crop from config instead of hardcoded constants.

    - `mode`: Playwright capture viewport/UA -- "desktop" (default: 1366x768 +
      honest desktop UA, so responsive gov.br sites serve the FULL layout) or
      "mobile".
    - `crop_profile`: PillowImageProcessor.screenshot_to_webp profile --
      "desktop" (default: downscale to ~1200px wide, keep the fold) or "mobile"
      (the legacy 800x1200 crop, wrong for a landscape desktop capture).
    - `blank_frac_max` / `blank_contig_max`: B3 blank/under-render guard limits
      (fraction of near-flat horizontal bands / largest contiguous flat run).
    - `retry_settle_ms`: the larger settle the blank retry asks for (paired with
      a scroll to kick lazy-loaders); materially bigger than the adapter's
      1500ms first-pass settle."""
    mode: str = "desktop"
    crop_profile: str = "desktop"
    blank_frac_max: float = 0.18
    blank_contig_max: float = 0.15
    retry_settle_ms: int = 4000


class Settings(BaseModel):
    secrets: Secrets
    run: RunConfig
    site: SiteConfig
    steps: dict[str, StepConfig]
    routing: dict[str, RoutingSpecConfig] = {}
    ads: AdsConfig = AdsConfig()
    index: dict[str, IndexPolicyConfig] = {}
    uniqueness: UniquenessConfig = UniquenessConfig()
    screenshot: ScreenshotConfig = ScreenshotConfig()
    budget: BudgetConfig = BudgetConfig()
    openai: OpenAIConfig = OpenAIConfig()


_PASSOS_POR_PAPEL = {
    "writer_model": ("write_p1", "write_page", "widget"),
    "judge_model": ("judge",),
    "reviewer_model": ("revisor",),
}


def aplicar_modo_openai(settings: Settings) -> Settings:
    """Com `auth_mode: chatgpt_plan`, troca EXPLICITAMENTE o modelo dos passos
    de redação/juiz/revisor pelos declarados em `openai.*_model` (com o
    prefixo do plano e o esforço de raciocínio). Sem fallback faturado quando
    `allow_api_key_fallback` é falso. Com `api_key`, nada muda."""
    oa = settings.openai
    if oa.auth_mode != "chatgpt_plan":
        return settings
    passos = dict(settings.steps)
    for campo, chaves in _PASSOS_POR_PAPEL.items():
        modelo = getattr(oa, campo).strip()
        if not modelo:
            continue
        alvo = modelo if modelo.startswith(PREFIXO_DO_PLANO) else PREFIXO_DO_PLANO + modelo
        for chave in chaves:
            if chave not in passos:
                continue
            atual = passos[chave]
            passos[chave] = atual.model_copy(update={
                "model": alvo,
                "fallbacks": [f for f in atual.fallbacks
                              if oa.allow_api_key_fallback or f.startswith(PREFIXO_DO_PLANO)],
                "reasoning_effort": (oa.reasoning_effort if campo != "writer_model"
                                     else atual.reasoning_effort),
            })
    return settings.model_copy(update={"steps": passos})


def problemas_do_modo_openai(settings: Settings) -> list[str]:
    """O que impede o run de começar no modo escolhido. Lista vazia = ok."""
    oa = settings.openai
    problemas: list[str] = []
    for nome, passo in settings.steps.items():
        no_plano = passo.model.startswith(PREFIXO_DO_PLANO)
        if no_plano and oa.auth_mode != "chatgpt_plan":
            problemas.append(f"steps.{nome} usa {passo.model} mas openai.auth_mode é api_key")
        if no_plano and not oa.allow_api_key_fallback:
            faturados = [f for f in passo.fallbacks if not f.startswith(PREFIXO_DO_PLANO)]
            if faturados:
                problemas.append(f"steps.{nome}: fallback faturado {faturados} proibido "
                                 "(openai.allow_api_key_fallback=false)")
        if oa.auth_mode == "chatgpt_plan" and oa.somente_plano and not no_plano:
            problemas.append(f"steps.{nome} usa {passo.model}, faturado por API "
                             "(openai.somente_plano=true)")
    if oa.auth_mode == "chatgpt_plan" and not oa.client_id.strip():
        problemas.append("openai.client_id vazio: registre o client_id do VOLC antes do login")
    return problemas


def load_settings(env_path: Path | None = None, config_path: Path | None = None) -> Settings:
    env_path = env_path or Path(".env")
    config_path = config_path or Path("config.yaml")
    env = {k.lower(): v for k, v in dotenv_values(env_path).items()}
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    site_raw = dict(raw.get("site", {}))
    author = site_raw.pop("author", {}) or {}
    return aplicar_modo_openai(Settings(
        secrets=Secrets(**env),
        run=RunConfig(**(raw.get("run", {}))),
        site=SiteConfig(
            author_name=author.get("name", ""),
            author_credential=author.get("credential", ""),
            **site_raw,
        ),
        steps={k: StepConfig(**v) for k, v in (raw.get("steps", {})).items()},
        routing={k: RoutingSpecConfig(**v) for k, v in (raw.get("routing", {})).items()},
        ads=AdsConfig(**(raw.get("ads", {}))),
        index={k: IndexPolicyConfig(**v) for k, v in (raw.get("index", {})).items()},
        uniqueness=UniquenessConfig(**(raw.get("uniqueness", {}))),
        screenshot=ScreenshotConfig(**(raw.get("screenshot", {}))),
        budget=BudgetConfig(**(raw.get("budget", {}))),
        openai=OpenAIConfig(**(raw.get("openai", {}) or {})),
    ))
