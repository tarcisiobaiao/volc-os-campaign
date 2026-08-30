# funnel-forge/src/funnelforge/config/settings.py
from __future__ import annotations
from pathlib import Path
import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, field_validator


class Secrets(BaseModel):
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    anthropic_api_key: str | None = None
    perplexity_api_key: str | None = None
    wp_url: str | None = None
    wp_user: str | None = None
    wp_app_token: str | None = None


class RunConfig(BaseModel):
    max_retries: int = 2
    publish: bool = False
    # A fact verified before this window is stale for a new publication.  The
    # research contract compares ``verificado_em`` against the run date.
    research_max_age_days: int = 45
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
    publish_status: str = "draft"
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


def load_settings(env_path: Path | None = None, config_path: Path | None = None) -> Settings:
    env_path = env_path or Path(".env")
    config_path = config_path or Path("config.yaml")
    env = {k.lower(): v for k, v in dotenv_values(env_path).items()}
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    site_raw = dict(raw.get("site", {}))
    author = site_raw.pop("author", {}) or {}
    return Settings(
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
    )
