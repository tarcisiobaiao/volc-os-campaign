"""
Pydantic contracts for Pautador Pro.

These mirror, field-for-field, the canonical opportunity contract and the
n8n GOD MODE JSON output, and they are the single source of truth shared
with the SQL schema (src/sql/v7_01_create_pautador_tables.sql) and the
frontend types (src/types/pautador.ts). Keep the three in sync.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# --- canonical enums (kept identical across SQL / TS / Python) ----------------
Tier = Literal["S", "A", "B", "EXPERIMENTAL"]
Category = Literal[
    "S1", "S2", "S3", "S4", "S5", "S6",
    "A1", "A2", "A3", "A4",
    "B1", "B2", "B3",
    "EXP",
]
Qual4 = Literal["low", "medium", "high", "very_high"]
Competition = Literal["low", "medium", "high"]
Intent = Literal["informational", "navigational", "calculator", "comparison"]
Timing = Literal["evergreen", "seasonal", "event_driven", "trending"]
MarketTier = Literal["high_value", "medium_value", "volume_play"]
OpportunityStatus = Literal[
    "discovered", "validating", "mining", "funnel", "ready", "rejected", "archived"
]
RunStatus = Literal["pending", "running", "completed", "failed", "reviewed", "archived"]
Phase = Literal["discovery", "mining", "funnel"]


# --- cultural intelligence / personas / insights -----------------------------
class Persona(BaseModel):
    name: str
    demographics: str = ""
    core_pain: str = ""
    digital_literacy: Literal["high", "medium", "low"] = "medium"
    typing_style: str = ""
    main_systems: List[str] = Field(default_factory=list)


class CulturalIntelligence(BaseModel):
    key_institutions: List[str] = Field(default_factory=list)
    main_benefits_programs: List[str] = Field(default_factory=list)
    unique_cultural_pains: List[str] = Field(default_factory=list)
    upcoming_events: List[str] = Field(default_factory=list)
    digital_friction_apps: List[str] = Field(default_factory=list)


class Insights(BaseModel):
    market_observation: str = ""
    untapped_angle: str = ""
    recommended_deep_dive: str = ""
    cultural_warning: str = ""


# --- the raw seed the agent emits (pre-enrichment) ---------------------------
class Seed(BaseModel):
    keyword: str
    main_keyword: str
    keyword_pt_translation: Optional[str] = None
    tier: Tier
    category: Category
    volume_estimate: Optional[Qual4] = None
    cpc_estimate_local: Optional[str] = None
    rpm_potential: Optional[Qual4] = None
    competition_estimate: Optional[Competition] = None
    intent: Optional[Intent] = None
    persona: Optional[str] = None
    pain_point: Optional[str] = None
    reasoning: Optional[str] = None
    variations: List[str] = Field(default_factory=list)
    expansion_hooks: List[str] = Field(default_factory=list)
    timing: Optional[Timing] = None
    confidence: Optional[Qual4] = None


# --- the enriched, persistable opportunity (the canonical card) ---------------
class Opportunity(BaseModel):
    # identity
    seed_id: Optional[str] = None
    run_id: Optional[int] = None
    id: Optional[int] = None

    # locale
    country: str
    native_language: Optional[str] = None

    # keyword core (native language)
    keyword: str
    main_keyword: str
    keyword_pt_translation: Optional[str] = None

    # classification
    tier: Tier
    category: Category

    # qualitative economics
    volume_estimate: Optional[Qual4] = None
    rpm_potential: Optional[Qual4] = None
    competition_estimate: Optional[Competition] = None
    confidence: Optional[Qual4] = None
    intent: Optional[Intent] = None
    timing: Optional[Timing] = None

    # CPC raw + parsed
    cpc_estimate_local: Optional[str] = None
    cpc_min: Optional[float] = None
    cpc_max: Optional[float] = None
    cpc_avg: Optional[float] = None
    currency: Optional[str] = None

    # derived
    arbitrage_score: Optional[float] = None
    estimated_roi_signal: Optional[float] = None
    has_seasonal_window: Optional[bool] = None
    is_trending: Optional[bool] = None

    # semantics
    persona: Optional[str] = None
    pain_point: Optional[str] = None
    reasoning: Optional[str] = None
    variations: List[str] = Field(default_factory=list)
    expansion_hooks: List[str] = Field(default_factory=list)

    # workflow
    status: OpportunityStatus = "discovered"
    source: Literal["agent", "manual"] = "agent"


# --- run-level objects --------------------------------------------------------
class RunStats(BaseModel):
    total_seeds: int = 0
    by_tier: Dict[str, int] = Field(default_factory=dict)
    by_category: Dict[str, int] = Field(default_factory=dict)
    by_timing: Dict[str, int] = Field(default_factory=dict)
    by_intent: Dict[str, int] = Field(default_factory=dict)
    avg_arbitrage_score: float = 0.0
    top_persona_by_volume: Optional[Dict[str, Any]] = None
    seasonal_opportunities: int = 0
    trending_opportunities: int = 0
    evergreen_opportunities: int = 0


class RunMeta(BaseModel):
    country: str
    native_language: Optional[str] = None
    market_tier: Optional[MarketTier] = None
    engine: str = "mock"
    model: Optional[str] = None
    grounding_calls: int = 0
    generated_at: Optional[str] = None


class Run(BaseModel):
    id: Optional[int] = None
    run_uuid: Optional[str] = None
    country: str
    country_code: Optional[str] = None
    native_language: Optional[str] = None
    market_tier: Optional[MarketTier] = None
    phase: Phase = "discovery"
    status: RunStatus = "pending"
    requested_count: int = 40
    produced_count: int = 0
    engine: str = "mock"
    model: Optional[str] = None
    grounding_calls: int = 0
    error_message: Optional[str] = None


# --- request / response DTOs --------------------------------------------------
class DiscoveryRequest(BaseModel):
    country: str = Field(..., description="Country name (PT-BR), e.g. 'Reino Unido'")
    country_code: Optional[str] = None
    native_language: Optional[str] = None
    count: int = Field(default=40, ge=1, le=80)
    engine: Optional[str] = Field(default=None, description="override: mock|gemini|openai")
    model: Optional[str] = None
    persist: Optional[bool] = Field(default=None, description="override persistence")


class DiscoveryResponse(BaseModel):
    run: Run
    meta: RunMeta
    cultural_intelligence: CulturalIntelligence
    personas: List[Persona]
    insights: Insights
    opportunities: List[Opportunity]
    stats: RunStats
    persisted: bool = False
    warnings: List[str] = Field(default_factory=list)


class MineRequest(BaseModel):
    opportunity: Optional[Dict[str, Any]] = Field(
        default=None, description="Inline opportunity (used in dry mode when not persisted)"
    )
    persist: Optional[bool] = None
    engine: Optional[str] = None
    model: Optional[str] = None


class FunnelRequest(MineRequest):
    # In dry mode (ephemeral card, no DB), the freshly-mined cluster can be
    # passed inline so the funnel has supporting_data without a DB lookup.
    cluster: Optional[Dict[str, Any]] = None


class StatusUpdateRequest(BaseModel):
    status: OpportunityStatus
    reviewed_by: Optional[str] = Field(default=None, description="users.id (uuid) of the reviewer")


class ManualOpportunityRequest(BaseModel):
    run_id: Optional[int] = None
    country: str
    native_language: Optional[str] = None
    keyword: str
    main_keyword: str
    keyword_pt_translation: Optional[str] = None
    tier: Tier
    category: Category
    volume_estimate: Optional[Qual4] = None
    rpm_potential: Optional[Qual4] = None
    competition_estimate: Optional[Competition] = None
    confidence: Optional[Qual4] = None
    intent: Optional[Intent] = None
    timing: Optional[Timing] = None
    cpc_estimate_local: Optional[str] = None
    persona: Optional[str] = None
    pain_point: Optional[str] = None
    reasoning: Optional[str] = None
    variations: List[str] = Field(default_factory=list)
    expansion_hooks: List[str] = Field(default_factory=list)


class KeywordNode(BaseModel):
    keyword: str
    volume: Optional[Qual4] = None
    cpc_local: Optional[str] = None
    competition: Optional[Competition] = None
    intent: Optional[Intent] = None


class KeywordCluster(BaseModel):
    id: Optional[int] = None
    opportunity_id: Optional[int] = None
    run_id: Optional[int] = None
    cluster_name: str
    main_keyword: Optional[str] = None
    intent: Optional[Intent] = None
    keywords: List[KeywordNode] = Field(default_factory=list)
    total_volume: Optional[float] = None
    avg_cpc_local: Optional[float] = None
    currency: Optional[str] = None


class MineResponse(BaseModel):
    opportunity_id: int
    cluster: KeywordCluster
    # rich pipeline output (Fase 2 — n8n peneirador-kw port). Optional so older
    # clients keep reading `cluster`; new UI reads these.
    summary: Optional[Dict[str, Any]] = None
    production_ads_queue: List[Dict[str, Any]] = Field(default_factory=list)
    content_seo_queue: List[Dict[str, Any]] = Field(default_factory=list)
    funis_sugeridos: List[Dict[str, Any]] = Field(default_factory=list)
    funnel_prospector: Optional[Dict[str, Any]] = None  # full prospector output (resumo/priorizacao/alertas)
    factory_output: List[Dict[str, Any]] = Field(default_factory=list)
    raw_keywords: List[Dict[str, Any]] = Field(default_factory=list)  # merged+classified keyword pool
    metrics: Optional[Dict[str, Any]] = None
    services_used: List[str] = Field(default_factory=list)
    engine: str = "mock"
    duration_ms: Optional[int] = None
    persisted: bool = False
    warnings: List[str] = Field(default_factory=list)


class FunnelPage(BaseModel):
    position: int
    page_title: str
    avatar: Optional[str] = None
    stage: Literal["tofu", "mofu", "bofu"] = "tofu"
    emotional_goal: Optional[str] = None
    subtitles: List[str] = Field(default_factory=list)
    internal_links: List[str] = Field(default_factory=list)


class Funnel(BaseModel):
    opportunity_id: Optional[int] = None
    run_id: Optional[int] = None
    funnel_name: str
    pages: List[FunnelPage] = Field(default_factory=list)


class FunnelResponse(BaseModel):
    opportunity_id: int
    funnel: Funnel
    # rich pipeline output (Fase 3 — n8n funnel-builder port)
    funnel_strategy: Optional[Dict[str, Any]] = None
    writing_jobs: List[Dict[str, Any]] = Field(default_factory=list)
    services_used: List[str] = Field(default_factory=list)
    persisted: bool = False
    warnings: List[str] = Field(default_factory=list)


class RunDetail(BaseModel):
    run: Run
    meta: Optional[RunMeta] = None
    cultural_intelligence: Optional[CulturalIntelligence] = None
    personas: List[Persona] = Field(default_factory=list)
    insights: Optional[Insights] = None
    opportunities: List[Opportunity] = Field(default_factory=list)
    stats: Optional[RunStats] = None
