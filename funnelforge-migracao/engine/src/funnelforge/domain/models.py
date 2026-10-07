from __future__ import annotations
from datetime import date
import re
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


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
    reason: str = ""


class EditorialLink(BaseModel):
    target: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class EditorialIntent(BaseModel):
    reader_question: str = Field(min_length=1)
    useful_delivery: str = Field(min_length=1)
    cta_label: str = Field(min_length=1)
    links: list[EditorialLink] = Field(default_factory=list)


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
    # None preserves old checkpoints; new plans carry an explicit reader contract.
    editorial: EditorialIntent | None = None
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


# ---------------------------------------------------------------------------
# CONTEXTOS DO FUNIL que vêm do backend no `funnel_architecture` (contrato
# entre as trilhas, 30/09). Todos OPCIONAIS e aditivos: um card antigo não os
# tem, e ausência é dita como ausência — nunca preenchida por suposição.
# ---------------------------------------------------------------------------

class TermoDeBusca(BaseModel):
    termo: str = Field(min_length=1)
    impressoes: int = Field(ge=0)
    cliques: int = Field(ge=0)
    custo: float | None = None


class JanelaDeColeta(BaseModel):
    inicio: date
    fim: date
    fuso: str = "America/Sao_Paulo"

    @model_validator(mode="after")
    def _fim_depois_do_inicio(self) -> "JanelaDeColeta":
        if self.fim < self.inicio:
            raise ValueError("janela com fim antes do início")
        return self


_FONTE_DE_TERMOS_RE = re.compile(r"^(search_term_view|arquivo:[0-9a-f]{64})$")


class TermosDeBusca(BaseModel):
    """O que o leitor digitou, em TRÊS estados — o mesmo JSON dos dois lados.

    `presente`         -> consulta feita na janela, com termos.
    `vazio_confirmado` -> consulta feita na janela, zero termos (é informação).
    `ausente`          -> ninguém coletou (funil novo, sem credencial...). NUNCA
                          vira lista: `termos` tem de vir vazio.
    """
    estado: Literal["presente", "vazio_confirmado", "ausente"]
    janela: JanelaDeColeta | None = None
    coletado_em: str | None = None
    fonte: str | None = None
    termos: list[TermoDeBusca] = []
    motivo_ausencia: str | None = None

    @model_validator(mode="after")
    def _coerente_com_o_estado(self) -> "TermosDeBusca":
        if self.estado in ("ausente", "vazio_confirmado") and self.termos:
            raise ValueError(f"estado '{self.estado}' não pode trazer termos")
        if self.estado == "presente" and not self.termos:
            raise ValueError("estado 'presente' sem nenhum termo")
        if self.estado != "ausente":
            faltando = [nome for nome in ("janela", "coletado_em", "fonte")
                        if not getattr(self, nome)]
            if faltando:
                raise ValueError(f"estado '{self.estado}' sem {', '.join(faltando)}")
            if not _FONTE_DE_TERMOS_RE.match(self.fonte or ""):
                raise ValueError("fonte deve ser 'search_term_view' ou 'arquivo:<sha256>'")
        return self


class Tensao(BaseModel):
    frase: str = Field(min_length=1)
    evidencia: str = ""


class ContextoDeLeitura(BaseModel):
    """Perguntas reais dos leitores (PAA) e a tensão medida na validação.

    É DADO, não instrução: o briefing trata a tensão como hipótese com a
    evidência que a sustenta."""
    perguntas_paa: list[str] = []
    tensao: Tensao | None = None

    @field_validator("perguntas_paa", mode="after")
    @classmethod
    def _sem_vazias(cls, value: list[str]) -> list[str]:
        return [p.strip() for p in value if isinstance(p, str) and p.strip()]


class ContextoDeAnuncio(BaseModel):
    """A promessa do anúncio que traz o leitor à LP (títulos e descrições)."""
    estado: Literal["presente", "ausente"]
    titulos: list[str] = []
    descricoes: list[str] = []
    fonte: str = ""
    motivo_ausencia: str | None = None

    @model_validator(mode="after")
    def _coerente_com_o_estado(self) -> "ContextoDeAnuncio":
        if self.estado == "presente" and not (self.titulos or self.descricoes):
            raise ValueError("anúncio 'presente' sem título nem descrição")
        if self.estado == "ausente" and (self.titulos or self.descricoes):
            raise ValueError("anúncio 'ausente' não pode trazer texto")
        return self


class FunnelPlan(BaseModel):
    avatar_summary: str = ""
    tone_voice: str = ""
    total_pages: int = 0
    pages: list[Page] = []
    # Ramo editorial novo pedido pela ARQUITETURA do card (o perfil do run
    # também pode ligar; ver `pipeline.editorial_v2_do_run`).
    editorial_v2: bool = False
    contexto_de_leitura: ContextoDeLeitura | None = None
    contexto_de_busca: TermosDeBusca | None = None
    contexto_de_anuncio: ContextoDeAnuncio | None = None


# ---------------------------------------------------------------------------
# FATOS TIPADOS — o vocabulário fechado do contrato entre as trilhas (30/09).
#
# O tipo diz o que o fato AFIRMA, não de que campo da pesquisa ele veio. Antes
# desta reforma a ponte do backend deduzia o tipo pelo campo de origem
# (`dados_validados` -> "afirmacao", `fatos_verificados` -> "numero") e o motor
# jogava fora qualquer `tipo` que a pesquisa mandasse. No run Senac isso custou
# 3 de 7 fatos na copy e transformou o número de um decreto em "numero".
#
# `contexto` sustenta relevância e nomeação; NUNCA sustenta número, prazo ou
# condição. A mesma lista vale no backend (`volc_ads`): mudar aqui exige mudar
# lá, e o teste de contrato da integração compara as duas.
# ---------------------------------------------------------------------------
TIPOS_DE_FATO: tuple[str, ...] = (
    "numero", "prazo", "data", "mudanca", "condicao",
    "orgao", "fonte_legal", "processo", "contexto",
)

#: Unidades da federação aceitas em `escopo = "regional:UF"`.
UFS: frozenset[str] = frozenset({
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
})


def _sem_acento(texto: str) -> str:
    import unicodedata
    normal = unicodedata.normalize("NFKD", texto)
    return "".join(ch for ch in normal if not unicodedata.combining(ch))


def canon_tipo_de_fato(valor: object) -> str | None:
    """Grafia canônica de um tipo: minúsculas, sem acento, `_` no lugar de
    espaço/hífen ("Fonte legal" -> "fonte_legal", "Condição" -> "condicao").

    NÃO decide se o tipo é válido: um valor fora do vocabulário sai canonizado
    e intacto, para o validador `research_facts_contract` recusá-lo com o nome
    certo. Trocar por None aqui esconderia o erro da pesquisa."""
    if valor is None:
        return None
    texto = _sem_acento(str(valor)).strip().lower()
    texto = re.sub(r"[\s\-]+", "_", texto)
    return texto or None


def canon_escopo(valor: object) -> str | None:
    """`nacional` | `unidade` | `regional:UF` (UF em maiúsculas). Fora disso,
    sai minúsculo e intacto para o validador recusar."""
    if valor is None:
        return None
    texto = _sem_acento(str(valor)).strip().lower()
    if not texto:
        return None
    texto = re.sub(r"\s*:\s*", ":", texto)
    if texto.startswith("regional:"):
        uf = texto.split(":", 1)[1].strip()
        return f"regional:{uf.upper()}"
    return texto


def canon_citavel(valor: object) -> bool | None:
    """Booleano tolerante ("sim"/"não" também). Desconhecido = não declarado."""
    if isinstance(valor, bool) or valor is None:
        return valor
    texto = _sem_acento(str(valor)).strip().lower()
    if texto in {"sim", "true", "1", "yes", "verdadeiro"}:
        return True
    if texto in {"nao", "false", "0", "no", "falso"}:
        return False
    return None


def escopo_valido(escopo: str | None) -> bool:
    if escopo is None:
        return True
    if escopo in ("nacional", "unidade"):
        return True
    return escopo.startswith("regional:") and escopo.split(":", 1)[1] in UFS


class VerifiedFact(BaseModel):
    """One publication-grade fact, with enough provenance to audit it.

    ``dados_validados`` remains available on :class:`ResearchFacts` for
    backwards-compatible qualitative notes.  Numbers, deadlines and legal
    claims, however, are only publishable when represented by this stricter
    shape and later accepted by the research/content gates.

    `tipo`, `escopo` e `citavel` são ADITIVOS e opcionais: um `state.json`
    anterior à reforma não os tem e continua carregando (None = não declarado;
    a ponte aplica a regra de legado). O vocabulário é conferido pelo validador
    `research_facts_contract`, não aqui — ver `canon_tipo_de_fato`.
    """

    valor: str = Field(min_length=1)
    unidade: str = Field(min_length=1)
    fonte_primaria: str = Field(min_length=1)
    dispositivo: str = Field(min_length=1)
    vigente_desde: date
    verificado_em: date
    tipo: str | None = None
    escopo: str | None = None
    citavel: bool | None = None

    @field_validator("fonte_primaria")
    @classmethod
    def fonte_must_be_absolute_https(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("https://"):
            raise ValueError("fonte_primaria deve ser uma URL HTTPS absoluta")
        return value

    @field_validator("tipo", mode="before")
    @classmethod
    def _tipo_canonico(cls, value: object) -> str | None:
        return canon_tipo_de_fato(value)

    @field_validator("escopo", mode="before")
    @classmethod
    def _escopo_canonico(cls, value: object) -> str | None:
        return canon_escopo(value)

    @field_validator("citavel", mode="before")
    @classmethod
    def _citavel_tolerante(cls, value: object) -> bool | None:
        return canon_citavel(value)


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

    @field_validator("dados_validados", mode="after")
    @classmethod
    def _dados_tipados_canonicos(cls, value: list[dict]) -> list[dict]:
        """Mesma grafia canônica dos fatos verificados, só onde a chave existe:
        um dado antigo sem `tipo` continua sem `tipo` (a ponte decide)."""
        saida: list[dict] = []
        for item in value:
            if isinstance(item, dict):
                item = dict(item)
                if "tipo" in item:
                    item["tipo"] = canon_tipo_de_fato(item["tipo"])
                if "escopo" in item:
                    item["escopo"] = canon_escopo(item["escopo"])
                if "citavel" in item:
                    item["citavel"] = canon_citavel(item["citavel"])
            saida.append(item)
        return saida


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
    image_reviews: dict[int, dict] = {}
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
    # RAMO EDITORIAL NOVO (B4). Gravado no estado para ser PEGAJOSO: um run que
    # nasceu no ramo novo continua nele quando retomado sem o perfil, em vez
    # de escrever metade do funil com um prompt e metade com outro.
    editorial_v2: bool = False
    # O briefing-v1 VALIDADO de cada página escrita no ramo novo. Página com
    # briefing aqui = página escrita a partir dele (a B5 usa isso para exigir
    # revisão e recibo só onde o ramo novo escreveu).
    briefings: dict[int, dict] = {}
    # REVISOR CONTEXTUAL (B5), só no ramo novo. `revisoes[n]` é o registro
    # revisao-v1 da página (rodadas, achados, patches aplicados e recusados,
    # decisão, erro, sha256 de entrada e de saída); `recibos[n]` só existe com
    # decisão `aprovado` (do revisor ou da pessoa) e carrega o sha256 que o
    # `step_publish` confere; `decisoes_humanas[n]` é a saída da revisão humana
    # (`funnelforge decidir`), presa ao sha256 do conteúdo.
    revisoes: dict[int, dict] = {}
    recibos: dict[int, dict] = {}
    decisoes_humanas: dict[int, dict] = {}
    # O que as normalizações determinísticas mudaram no texto (normalize do
    # Gutenberg, aviso canônico, template da LP) e as decorações estruturais
    # que a publicação acrescentou DEPOIS do recibo (aviso de identidade,
    # imagem, prints). Nada mais pode mudar o texto depois do recibo.
    normalizacoes: dict[int, list[dict]] = {}
    decoracoes: dict[int, list[dict]] = {}

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, s: str) -> RunState:
        return cls.model_validate_json(s)
