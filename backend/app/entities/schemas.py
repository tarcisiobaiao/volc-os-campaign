"""
Pydantic contracts for the ENTITY-FIRST layer. Mirror, field-for-field, the
SQL (src/sql/v7_03_pautador_entities.sql), the entity-first agent JSON, and the
frontend types (src/types/pautadorEntity.ts). Keep the three in sync.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


def _lista_ou_vazio(v: Any) -> Any:
    """jsonb NULL (card anterior à v7_16) e rótulo torto do agente viram lista
    vazia. Recusar `None` aqui derrubaria a validação do CARD INTEIRO por causa
    de uma coluna que ainda não existia quando ele foi gravado."""
    if v is None:
        return []
    return v if isinstance(v, list) else []

OpportunityStatus = str  # discovered|validating|mining|funnel|ready|rejected|archived
GoldTier = str           # S|A|B|EXPERIMENTAL


# --- agent output (nested) ----------------------------------------------------
class EntitySpec(BaseModel):
    canonical_name: str
    full_name: Optional[str] = None
    slug: Optional[str] = None  # filled from canonical_name if omitted
    type: Optional[str] = None
    vertical: Optional[str] = None  # linha editorial (financas, carros, gov_beneficios…)
    category: Optional[str] = None
    official_source: Optional[str] = None
    related_systems: List[str] = Field(default_factory=list)
    aliases: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    niche_slug: Optional[str] = None  # slug de pautador_niches (R1), quando a descoberta é focada em nicho


class OpportunitySpec(BaseModel):
    gold_tier: Optional[str] = None
    strategic_stage: Optional[str] = None
    score: Optional[float] = None  # computed deterministically if omitted
    # estimativa de volume de busca mensal (LLM) da keyword/entidade principal.
    # Só um indicativo na etapa de descoberta; a mineração traz o volume real.
    estimated_volume: Optional[int] = None
    ecpm_band: Optional[str] = None  # premium|medio|baixo — sinal de monetização da vertical
    roi_signal: Optional[float] = None
    cpc_min: Optional[float] = None
    cpc_max: Optional[float] = None
    cpc_currency: Optional[str] = None
    volume_level: Optional[str] = None
    rpm_level: Optional[str] = None
    competition_level: Optional[str] = None
    confidence_level: Optional[str] = None
    temporal_window: Optional[str] = None
    # v7_15 · SEGUNDO EIXO (a pessoa LÊ?). Vocabulário fechado, validado em
    # `entities/leitura.py` — de propósito SEM Literal aqui: rótulo torto não pode
    # derrubar a validação do item inteiro e custar a entidade toda. Nível inválido
    # vira "ausente" no portão, e o valor cru fica gravado para diagnóstico.
    # v7_16: TRÊS frases, cada uma com o seu rótulo. O rótulo da oportunidade é a
    # MODA das três — uma frase só é amostra de tamanho 1 de um espaço que o
    # modelo sorteia a cada rodada. Tipo frouxo (dict) de propósito: item torto
    # é descartado em `leitura.respostas_validas`, não derruba a entidade.
    respostas: List[Dict[str, Any]] = Field(default_factory=list)
    _v_respostas = field_validator("respostas", mode="before")(_lista_ou_vazio)
    resposta_em_uma_frase: Optional[str] = None  # legado/fallback; hoje é derivada
    ignorancia_level: Optional[str] = None
    engajamento_level: Optional[str] = None
    opacidade_level: Optional[str] = None
    concrete_pain: Optional[str] = None
    gold_reason: Optional[str] = None


class PainSpec(BaseModel):
    pain_name: str
    pain_description: Optional[str] = None
    user_goal: Optional[str] = None
    intent: Optional[str] = None
    severity: Optional[str] = None


class SeedQuerySpec(BaseModel):
    query: str
    query_type: Optional[str] = None
    intent: Optional[str] = None
    score: Optional[float] = None
    source: Optional[str] = None


class FunnelHypothesisSpec(BaseModel):
    # LLM-INPUT shape (the prompt asks the model for title/summary/pages). The
    # router's _norm_funnels maps this to the canonical OUTPUT/DB shape
    # (funnel_title/funnel_summary) so every API response is consistent.
    title: str
    summary: Optional[str] = None
    pages: List[str] = Field(default_factory=list)


class EntityDiscoveryItem(BaseModel):
    entity: EntitySpec
    opportunity: OpportunitySpec = Field(default_factory=OpportunitySpec)
    pains: List[PainSpec] = Field(default_factory=list)
    seed_queries: List[SeedQuerySpec] = Field(default_factory=list)
    funnel_hypotheses: List[FunnelHypothesisSpec] = Field(default_factory=list)


# --- request / response DTOs --------------------------------------------------
class EntityDiscoveryRequest(BaseModel):
    country: str = Field(..., description="Country name (PT-BR), e.g. 'Colômbia'")
    country_code: Optional[str] = None
    native_language: Optional[str] = None
    count: int = Field(default=20, ge=1, le=60)
    engine: Optional[str] = None
    model: Optional[str] = None
    persist: Optional[bool] = None
    niches: List[str] = Field(default_factory=list)  # slugs de pautador_niches; [] = diversificado (comportamento atual)
    seasonality: Optional[Literal["evergreen", "seasonal"]] = None


class EntityCardEntity(BaseModel):
    id: Optional[int] = None
    canonical_name: str
    full_name: Optional[str] = None
    slug: str
    country_code: str
    country: Optional[str] = None
    entity_type: Optional[str] = None
    entity_category: Optional[str] = None
    official_source: Optional[str] = None
    vertical: Optional[str] = None
    related_systems: List[str] = Field(default_factory=list)
    aliases: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    language: Optional[str] = None
    niche_slug: Optional[str] = None


class EntityCard(BaseModel):
    """A Kanban card = entity opportunity + joined entity + subdata."""
    id: Optional[int] = None
    entity_id: Optional[int] = None
    run_id: Optional[int] = None
    country_code: str
    status: OpportunityStatus = "discovered"
    kanban_stage: str = "discovered"
    gold_tier: Optional[str] = None
    strategic_stage: Optional[str] = None
    score: Optional[float] = None
    estimated_volume: Optional[int] = None
    ecpm_band: Optional[str] = None
    roi_signal: Optional[float] = None
    cpc_min: Optional[float] = None
    cpc_max: Optional[float] = None
    cpc_currency: Optional[str] = None
    volume_level: Optional[str] = None
    rpm_level: Optional[str] = None
    competition_level: Optional[str] = None
    confidence_level: Optional[str] = None
    temporal_window: Optional[str] = None
    # v7_15 · SEGUNDO EIXO. Os três níveis + a frase vêm do agente; os `reading_*`
    # são computados por `entities/leitura.py`. O portão INFORMA e sugere — não
    # bloqueia o Kanban: quem arrasta decide.
    # v7_16: as três frases que sustentam o rótulo (jsonb). São o dado que
    # permite auditar um veredito depois — sem elas a moda é número sem
    # procedência. `resposta_em_uma_frase` é a frase VENCEDORA, derivada delas.
    respostas: List[Dict[str, Any]] = Field(default_factory=list)
    _v_respostas = field_validator("respostas", mode="before")(_lista_ou_vazio)
    resposta_em_uma_frase: Optional[str] = None
    ignorancia_level: Optional[str] = None
    engajamento_level: Optional[str] = None
    opacidade_level: Optional[str] = None
    reading_blocked: Optional[bool] = None
    reading_reason: Optional[str] = None
    # média geométrica de ignorancia × engajamento × opacidade. NÃO é o índice de
    # 10 eixos do motor — ver o docstring de `leitura.compute_reading_gate`.
    reading_strength: Optional[float] = None
    concrete_pain: Optional[str] = None
    gold_reason: Optional[str] = None
    # Direcionamento para o AGENTE de funil (user prompt). Não vai pro DOCX nem
    # pro ClickUp — ver v7_14.
    insights: Optional[str] = None
    # v7_14: corpo da task no ClickUp, escrito para quem executa. Também fica
    # FORA do DOCX.
    task_description: Optional[str] = None
    # v7_12: rótulo do card escrito pelo admin. Diferencia CÓPIAS da mesma
    # entidade (mesmo funil rodando em sites diferentes) sem sujar o
    # canonical_name, que alimenta o tema do agente de funil e o DOCX.
    display_title: Optional[str] = None
    clickup_task_url: Optional[str] = None
    funnel_completed: bool = False
    entity: EntityCardEntity
    pains: List[Dict[str, Any]] = Field(default_factory=list)
    seed_queries: List[Dict[str, Any]] = Field(default_factory=list)
    funnel_hypotheses: List[Dict[str, Any]] = Field(default_factory=list)
    # local-only (dry/ephemeral cards)
    ephemeral: bool = False


class EntityDiscoveryResponse(BaseModel):
    run_id: Optional[int] = None
    country: str
    country_code: Optional[str] = None
    native_language: Optional[str] = None
    engine: str = "mock"
    model: Optional[str] = None
    items: List[EntityCard] = Field(default_factory=list)
    cultural_intelligence: Optional[Dict[str, Any]] = None
    personas: List[Dict[str, Any]] = Field(default_factory=list)
    insights: Optional[Dict[str, Any]] = None
    persisted: bool = False
    created_count: int = 0
    merged_count: int = 0
    warnings: List[str] = Field(default_factory=list)


class EntityListResponse(BaseModel):
    items: List[EntityCard] = Field(default_factory=list)
    source: str = "supabase"


class EntityStatusUpdateRequest(BaseModel):
    status: OpportunityStatus
    reviewed_by: Optional[str] = None


class EntityInsightsRequest(BaseModel):
    insights: str = ""


class EntityTaskDescriptionRequest(BaseModel):
    task_description: str = ""


class EntityDisplayTitleRequest(BaseModel):
    display_title: str = ""


class EntityDuplicateRequest(BaseModel):
    """Duplica um card já minerado p/ rodar a MESMA entidade em outro site."""
    display_title: str = ""


class EntityCompleteRequest(BaseModel):
    completed: bool = True


class QuestionChoiceRequest(BaseModel):
    """v7_17 · a escolha de PERGUNTA no arraste DESCOBERTAS -> EM VALIDAÇÃO.

    A entidade não tem UMA pergunta — tem várias, todas legítimas. Esta etapa
    existe para transformar entidade em pergunta e REGISTRAR a transformação.

    Sem nota, sem ranking, sem score: não há desfecho medido contra o qual
    validar uma nota, e nota sem desfecho é opinião com casas decimais — cujo
    custo não é estar errada, é PARECER MEDIDA.

    Nenhum `outcome` impede o card de mover. `skipped` é DADO (o operador viu e
    pulou), não ausência de dado.
    """
    outcome: Literal["chosen", "custom", "skipped", "entity_rejected"] = "chosen"
    # índice da escolhida dentro de `respostas` (0..n-1). None em custom/skipped.
    chosen_index: Optional[int] = None
    # a pergunta escrita à mão quando o operador recusa as três. É o registro
    # mais valioso da tabela: marca onde o gerador não viu a pergunta que importa.
    custom_frase: Optional[str] = None
    custom_engajamento: Optional[str] = None
    custom_ignorancia: Optional[str] = None
    notes: Optional[str] = None          # livre e OPCIONAL — obrigar texto produz texto vazio
    chosen_by: Optional[str] = None      # uuid de public.users


class EntityManualCreateRequest(BaseModel):
    """Entidade criada MANUALMENTE pelo admin (ex.: já em 'Pronto', p/ sincronizar
    funis existentes). NÃO dispara ClickUp (isso é só no arraste p/ Pronto)."""
    country: str
    country_code: str
    canonical_name: str
    full_name: Optional[str] = None
    entity_type: Optional[str] = None
    entity_category: Optional[str] = None
    official_source: Optional[str] = None
    description: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    native_language: Optional[str] = None
    status: OpportunityStatus = "ready"


class EntityEnrichRequest(BaseModel):
    """Input manual em 'Descobertas': o operador dá só o NOME; um agente secundário
    enriquece o card com os mesmos campos da descoberta principal."""
    country: str
    country_code: str
    canonical_name: str
    native_language: Optional[str] = None
    engine: Optional[str] = None
    model: Optional[str] = None


class EntityMineRequest(BaseModel):
    entity: Optional[Dict[str, Any]] = None  # inline entity for dry mode
    persist: Optional[bool] = None
    engine: Optional[str] = None
    model: Optional[str] = None


class EntityMineResponse(BaseModel):
    entity_id: int
    opportunity_id: Optional[int] = None
    pains: List[Dict[str, Any]] = Field(default_factory=list)
    seed_queries: List[Dict[str, Any]] = Field(default_factory=list)
    keyword_cluster: Optional[Dict[str, Any]] = None  # reuse mining pipeline output (optional)
    services_used: List[str] = Field(default_factory=list)
    engine: str = "mock"
    mode: str = "internal"        # "internal" (py) | "n8n" (webhook disparado)
    dispatched: bool = False      # True quando o webhook n8n foi disparado (resultado vem async)
    persisted: bool = False
    warnings: List[str] = Field(default_factory=list)


class EntityFunnelRequest(EntityMineRequest):
    pass


class EntityFunnelResponse(BaseModel):
    entity_id: int
    opportunity_id: Optional[int] = None
    funnel_hypotheses: List[Dict[str, Any]] = Field(default_factory=list)
    # saída do ARQUITETO (FUNNEL.json) — esqueleto de páginas + briefings
    funnel_strategy: Optional[Dict[str, Any]] = None
    pages: List[Dict[str, Any]] = Field(default_factory=list)
    writing_jobs: List[Dict[str, Any]] = Field(default_factory=list)
    services_used: List[str] = Field(default_factory=list)
    engine: str = "mock"
    persisted: bool = False
    warnings: List[str] = Field(default_factory=list)


class EntityValidateBatchRequest(BaseModel):
    """Entrada da validação em LOTE — o caminho padrão da coluna.

    Ou uma lista explícita de cards, ou um país + status para varrer a coluna
    inteira. O lote existe porque a base de US$ 0,012 por chamada domina na
    cauda curta: os dois nós lotáveis pagam a base uma vez, não uma por card.
    """

    opportunity_ids: List[int] = Field(default_factory=list)
    country_code: Optional[str] = None
    status: Optional[str] = "validating"
    limite: Optional[int] = 50
    # Re-arrastar refaz só o que falta. `refazer=True` remede tudo, inclusive o
    # que já tem medição válida — use quando a régua mudar, não por rotina.
    refazer: bool = False
    engine: Optional[str] = None
    model: Optional[str] = None
