from __future__ import annotations
from datetime import date
import re
from enum import Enum
from pydantic import BaseModel, Field, field_validator


class PageRole(str, Enum):
    LP = "LP"
    PRESELL = "PRESELL"
    SOLUTION = "SOLUTION"


_ROLE_PRESELL_RE = re.compile(r"-pr\d*$")
_ROLE_SOLUTION_RE = re.compile(r"-p\d+$")


def derive_role(slug: str) -> PageRole:
    """Pure slug->role. `-pr` -> PRESELL, `-p<N>` -> SOLUTION, else LP.
    PRESELL is checked first so `-pr` never matches the numeric rule."""
    s = slug.strip().rstrip("/")
    if _ROLE_PRESELL_RE.search(s):
        return PageRole.PRESELL
    if _ROLE_SOLUTION_RE.search(s):
        return PageRole.SOLUTION
    return PageRole.LP


class Route(BaseModel):
    placement: str
    kind: str
    target: str
    anchor: str = ""


def _url_normalizada(url: str) -> str:
    """Forma canônica para comparar duas URLs: esquema e host em minúsculas,
    sem barra final. O CAMINHO preserva maiúsculas de propósito (há servidor
    que diferencia), então a comparação continua estrita onde precisa ser."""
    from urllib.parse import urlparse
    partes = urlparse((url or "").strip())
    consulta = f"?{partes.query}" if partes.query else ""
    return f"{partes.scheme.lower()}://{partes.netloc.lower()}{partes.path.rstrip('/')}{consulta}"


def resolve_route(route: Route, *, domain: str, post_type: str,
                  authorized_external: list[str] | None = None) -> str:
    """Resolve uma Route no href absoluto, aplicando a LEI DO MESMO DOMÍNIO.

    `authorized_external` são as URLs EXTERNAS que a PESQUISA desta página
    trouxe e o motor já escolheu (ver `steps.build_official_links`). Não é
    lista de domínios por instalação: é a evidência daquela página, URL a URL.
    Sem evidência não há link externo -- falha FECHADO por ausência de prova,
    nunca por o host estar fora de uma lista.

    Por que URL exata e não host: o risco real não é o host errado, é o redator
    inventar um caminho plausível num host legítimo ("gov.br/beneficio-liberado",
    "ifood.com.br/cadastro-vip"). Comparar a URL inteira mata os dois casos."""
    kind = route.kind
    target = route.target.strip()
    if kind == "funnel":
        slug = target.strip("/")
        if not slug:
            raise ValueError("empty funnel target (would produce a bare dead /rec link)")
        href = f"{domain.rstrip('/')}/{post_type}/{slug}"
        if "//" in href.split("://", 1)[-1]:
            raise ValueError(f"double slash in resolved href: {href}")
        return href
    if kind == "cross_funnel":
        # cross_funnel is a REAL, absolute same-domain URL picked from the site
        # sitemap -- NEVER reconstructed from a slug, so an invented page is
        # impossible. It must already be a full same-domain URL.
        from urllib.parse import urlparse
        if not target.startswith(("http://", "https://")):
            raise ValueError(f"cross_funnel target must be an absolute URL: {target}")
        host = urlparse(target).netloc.lower()
        dhost = urlparse(domain).netloc.lower()
        if not (host == dhost or host.endswith("." + dhost) or dhost.endswith("." + host)):
            raise ValueError(f"cross_funnel target not same-domain: {target}")
        return target
    if kind == "external_official":
        if not target.startswith("https://"):
            raise ValueError(f"canal oficial precisa ser uma URL https absoluta: {target}")
        autorizadas = {_url_normalizada(u) for u in (authorized_external or [])}
        if _url_normalizada(target) not in autorizadas:
            raise ValueError(
                f"canal oficial sem lastro na pesquisa desta página: {target}. "
                "Só entra URL que a busca devolveu e o motor verificou.")
        return target
    raise ValueError(f"unknown route kind: {kind}")


class PageTypeSpec(BaseModel):
    role: PageRole
    allowed_targets: list[str]
    required_targets: list[str]
    forbidden_targets: list[str]
    cta_min: int
    cta_max: int
    requires_external_official: bool = False
    requires_cross_funnel_exit: bool = False
    distinct_targets: bool = False
    anchor_congruent: bool = True


class Page(BaseModel):
    page_number: int
    page_type: str
    h1_title: str
    slug: str
    emotional_objective: str = ""
    main_content_structure: list[str] = []
    hook_to_next_page: str = ""
    next_page_slug: str = ""
    target_keywords: list[str] = []
    role: PageRole | None = None
    ordinal: int = 0
    routes: list[Route] = []
    # A FORMA DA PERGUNTA que esta página responde, no vocabulário do eixo
    # `engajamento` do motor de pautas: condicional | sequencial | comparativo |
    # diagnostico | dado_unico. Vazio = desconhecido (o motor não opinou), e aí
    # o motor aplica inferência semântica determinística sobre H1/estrutura.
    #
    # Este é o campo de ligação da F06 (ponte Pautador -> Runner): é a menor
    # superfície possível entre os dois projetos -- uma string por página, sem
    # acoplar modelos. Ver `ENGAJAMENTO_PARA_ARQUETIPO` em pipeline/steps.py.
    engajamento: str = ""


def effective_role(page: Page) -> PageRole:
    return page.role or derive_role(page.slug)


def role_matches_slug(page: Page) -> bool:
    return page.role is None or page.role == derive_role(page.slug)


class FunnelPlan(BaseModel):
    avatar_summary: str = ""
    tone_voice: str = ""
    total_pages: int = 0
    pages: list[Page] = []


class VerifiedFact(BaseModel):
    """One publication-grade fact, with enough provenance to audit it.

    ``dados_validados`` remains available on :class:`ResearchFacts` for
    backwards-compatible qualitative notes.  Numbers, deadlines and legal
    claims, however, are only publishable when represented by this stricter
    shape and later accepted by the research/content gates.
    """

    valor: str = Field(min_length=1)
    unidade: str = Field(min_length=1)
    fonte_primaria: str = Field(min_length=1)
    dispositivo: str = Field(min_length=1)
    vigente_desde: date
    verificado_em: date

    @field_validator("fonte_primaria")
    @classmethod
    def fonte_must_be_absolute_https(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("https://"):
            raise ValueError("fonte_primaria deve ser uma URL HTTPS absoluta")
        return value


class ResearchFacts(BaseModel):
    resumo: str = ""
    dados_validados: list[dict] = []
    fatos_verificados: list[VerifiedFact] = []
    passo_a_passo: list[str] = []
    fontes: list[str] = []
    # Filled by the engine, never trusted from prose.  When a live verifier is
    # wired, only URLs that actually resolved are copied here.  Critical-claim
    # validation trusts this set rather than the model-authored ``fontes``.
    fontes_resolvidas: list[str] = []
    sparse: bool = False


class PageDraft(BaseModel):
    page_number: int
    page_type: str
    format: str            # "markers" (P1) | "gutenberg" (P2-P5)
    content: str
    word_count: int = 0


class Verdict(BaseModel):
    approved: bool = False
    blocking: bool = False
    scores: dict[str, int] = {}
    feedback: list[str] = []


# Fail-closed gate criteria: a judge score < 7 on any of these FAILS the page
# (skips build+publish). proof_and_authority was DEMOTED out of this set
# ("cirurgico"/trust-Gemini smoke decision): we trust the Gemini web-search
# research, so weak/thin proof is now advisory feedback, never a hard block.
# Only the arbitrage + legal invariants stay existential. See
# `_existential_criteria_for` (SOLUTION also drops single_destination) and
# judge.jinja's REGRA_DE_APROVACAO, which are kept consistent with this tuple.
EXISTENTIAL_CRITERIA: tuple[str, ...] = (
    "single_destination", "compliance", "cta_discipline",
)


class Issue(BaseModel):
    code: str
    message: str


class StepStatus(str, Enum):
    OK = "OK"
    RETRIED = "RETRIED"
    FALLBACK = "FALLBACK"
    FAILED = "FAILED"
    # Non-essential step that failed/errored and was deliberately skipped
    # rather than failing the page (e.g. image generation -- see
    # steps.py's step_image). Distinct from FAILED so build/publish gates
    # (`_page_blocked` in pipeline.py) that key on FAILED never trip on it.
    SKIPPED = "SKIPPED"


class StepResult(BaseModel):
    step: str
    status: StepStatus
    model_used: str = ""
    attempts: int = 0
    issues: list[Issue] = []
    artifact_path: str | None = None
    # --- telemetry (summed across attempts) ---
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


class AdSlot(BaseModel):
    slot_id: str
    page_role: PageRole
    placement: str
    sizes: list[str] = []
    min_height_px: int = 0
    refresh_eligible: bool = False
    source_key: str = ""


class VignetteCap(BaseModel):
    enabled: bool = True
    max_per_window: int = 1
    window_seconds: int = 600


class AdManifest(BaseModel):
    slots: list[AdSlot] = []
    vignette: VignetteCap = VignetteCap()


class IndexDecision(BaseModel):
    robots: str = "noindex,follow"
    canonical: str | None = None


class RunState(BaseModel):
    run_id: str
    briefing_text: str = ""
    plan: FunnelPlan | None = None
    facts: dict[int, ResearchFacts] = {}
    drafts: dict[int, PageDraft] = {}
    seo: dict[int, dict] = {}
    images: dict[int, str] = {}
    # Official-destination screenshots per SOLUTION page (CARD-0005): each value
    # is a list of {"url": <official_link>, "path": <local webp>} dicts captured
    # best-effort by step_screenshot and embedded after the matching link at
    # publish. Empty/absent when the feature flag is off, the page is not
    # SOLUTION, or no ScreenshotProvider is wired.
    screenshots: dict[int, list[dict]] = {}
    # AS URLS EXTERNAS QUE CADA PÁGINA PODE USAR -- decididas UMA VEZ, logo
    # depois da pesquisa daquela página (ver steps.registrar_canais_oficiais),
    # porque a decisão precisa de browser (confirmar que a página existe e que
    # não é um portal que vive de anúncio) e browser é caro. O redator, o gate
    # de conteúdo e o screenshot LEEM daqui, então os três nunca discordam sobre
    # qual é o canal oficial da página. Vazio = a pesquisa não trouxe nada
    # linkável, e a página falha fechada no gate de densidade.
    official_links: dict[int, list[str]] = {}
    # O QUE O WORDPRESS DEVOLVEU AO PUBLICAR, por página. É o contrato de elo
    # com o módulo de campanha do Google Ads.
    #
    # Até aqui o motor recebia do WP um objeto com `id`, `slug`, `link` e
    # `status`, extraía SÓ o `id` e descartava o resto — então as 5 a 7 URLs de
    # um funil publicado precisavam ser REDIGITADAS à mão para que a receita do
    # AdSense fosse atribuída à campanha.
    #
    # ⚠️ GRAVADO VERBATIM, nunca remontado a partir do slug. O slug muda em três
    # pontos independentes: `_slug_com_sufixo` (a ponte), `dedupe_slugs` (o
    # motor) e o próprio WordPress, que acrescenta `-2` quando o slug já existe
    # e só conta isso na resposta REST.
    #
    # ⚠️ E o `link` de um RASCUNHO não é o permalink: o WP devolve
    # `?post_type=r&p=2146` e só troca por `/r/<slug>/` quando o post vai ao ar.
    # Medido no run de 17/08/2026. Quem consome tem de saber disso — por isso o
    # `status_wp` viaja junto, e não se deve derivar URL final de rascunho.
    published: dict[int, dict] = {}
    step_status: dict[str, StepResult] = {}

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, s: str) -> RunState:
        return cls.model_validate_json(s)
