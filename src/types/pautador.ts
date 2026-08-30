// ============================================
// PAUTADOR PRO — Types & Constants
// Espelha o contrato do backend (backend/app/schemas.py) e a migração
// src/sql/v7_01_create_pautador_tables.sql. Manter os três em sincronia.
// ============================================

// --- Enums (idênticos ao backend) ---

export type Tier = 'S' | 'A' | 'B' | 'EXPERIMENTAL';

export type Category =
  | 'S1' | 'S2' | 'S3' | 'S4' | 'S5' | 'S6'
  | 'A1' | 'A2' | 'A3' | 'A4'
  | 'B1' | 'B2' | 'B3'
  | 'EXP';

export type Qual4 = 'low' | 'medium' | 'high' | 'very_high';
export type Competition = 'low' | 'medium' | 'high';
export type Intent = 'informational' | 'navigational' | 'calculator' | 'comparison';
export type Timing = 'evergreen' | 'seasonal' | 'event_driven' | 'trending';
export type MarketTier = 'high_value' | 'medium_value' | 'volume_play';

export type OpportunityStatus =
  | 'discovered'
  | 'validating'
  | 'mining'
  | 'funnel'
  | 'ready'
  | 'rejected'
  | 'archived';

export type RunStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'reviewed'
  | 'archived';

// --- Data Interfaces ---

export interface Opportunity {
  id?: number;
  run_id?: number;
  seed_id?: string;
  country: string;
  native_language?: string | null;
  keyword: string;
  main_keyword: string;
  keyword_pt_translation?: string | null;
  tier: Tier;
  category: Category;
  volume_estimate?: Qual4 | null;
  rpm_potential?: Qual4 | null;
  competition_estimate?: Competition | null;
  confidence?: Qual4 | null;
  intent?: Intent | null;
  timing?: Timing | null;
  cpc_estimate_local?: string | null;
  cpc_min?: number | null;
  cpc_max?: number | null;
  cpc_avg?: number | null;
  currency?: string | null;
  arbitrage_score?: number | null;
  estimated_roi_signal?: number | null;
  has_seasonal_window?: boolean | null;
  is_trending?: boolean | null;
  persona?: string | null;
  pain_point?: string | null;
  reasoning?: string | null;
  variations?: string[];
  expansion_hooks?: string[];
  status: OpportunityStatus;
  source?: 'agent' | 'manual';
  // local-only (ephemeral demo, not persisted)
  _ephemeral?: boolean;
}

export interface Persona {
  name: string;
  demographics?: string;
  core_pain?: string;
  digital_literacy?: 'high' | 'medium' | 'low';
  typing_style?: string;
  main_systems?: string[];
}

export interface CulturalIntelligence {
  key_institutions: string[];
  main_benefits_programs: string[];
  unique_cultural_pains: string[];
  upcoming_events: string[];
  digital_friction_apps: string[];
}

export interface Insights {
  market_observation: string;
  untapped_angle: string;
  recommended_deep_dive: string;
  cultural_warning: string;
}

export interface RunStats {
  total_seeds: number;
  by_tier: Record<string, number>;
  by_category: Record<string, number>;
  by_timing: Record<string, number>;
  by_intent: Record<string, number>;
  avg_arbitrage_score: number;
  top_persona_by_volume?: { persona: string; count: number } | null;
  seasonal_opportunities: number;
  trending_opportunities: number;
  evergreen_opportunities: number;
}

export interface PautadorRun {
  id?: number;
  run_uuid?: string | null;
  country: string;
  country_code?: string | null;
  native_language?: string | null;
  market_tier?: MarketTier | null;
  phase?: 'discovery' | 'mining' | 'funnel';
  status: RunStatus;
  requested_count?: number;
  produced_count?: number;
  engine?: string;
  model?: string | null;
  grounding_calls?: number;
  cultural_intelligence?: CulturalIntelligence | null;
  personas?: Persona[] | null;
  insights?: Insights | null;
  created_at?: string;
  updated_at?: string;
}

export interface PautadorCountry {
  id?: number;
  country_code: string;
  country_name: string;
  native_language: string;
  market_tier?: MarketTier;
  flag_emoji?: string | null;
  is_active?: boolean;
}

export interface KeywordNode {
  keyword: string;
  volume?: Qual4 | null;
  cpc_local?: string | null;
  competition?: Competition | null;
  intent?: Intent | null;
}

export interface KeywordCluster {
  id?: number;
  opportunity_id?: number;
  run_id?: number;
  cluster_name: string;
  main_keyword?: string;
  intent?: Intent;
  keywords: KeywordNode[];
  total_volume?: number | null;
  avg_cpc_local?: number | null;
  currency?: string | null;
}

export interface FunnelPage {
  position: number;
  page_title: string;
  avatar?: string | null;
  stage: 'tofu' | 'mofu' | 'bofu';
  emotional_goal?: string | null;
  subtitles: string[];
  internal_links: string[];
}

// --- Fase 2 (Minerador) / Fase 3 (Construtor de Funis) rich outputs ---

export interface MinedKeyword {
  keyword: string;
  volume?: number;
  cpc?: number;
  competition?: string;
  tags?: string[];
  trend_score?: number;
  reason?: string;
}

export interface FunnelSubIntent {
  tipo: string;
  descricao?: string;
  keywords?: { keyword: string; volume?: number; cpc?: number }[];
  volume_sub?: number;
  qtd_keywords?: number;
}

export interface FunnelSuggestion {
  rank?: number;
  nome_funil?: string;
  keyword_ancora?: string;
  volume_ancora?: number;
  sub_intencoes?: FunnelSubIntent[];
  metricas?: Record<string, number>;
  justificativa?: string;
  tags?: string[];
}

export interface MineResult {
  opportunity_id: number;
  cluster: KeywordCluster;
  summary?: Record<string, unknown> | null;
  production_ads_queue: MinedKeyword[];
  content_seo_queue: MinedKeyword[];
  funis_sugeridos: FunnelSuggestion[];
  funnel_prospector?: Record<string, unknown> | null;
  factory_output: unknown[];
  raw_keywords?: MinedKeyword[];
  metrics?: Record<string, unknown> | null;
  services_used: string[];
  engine: string;
  duration_ms?: number | null;
  persisted: boolean;
  warnings: string[];
}

export interface WritingJob {
  job_id?: string;
  page_type?: string;
  writer_briefing?: Record<string, unknown>;
}

export interface FunnelResult {
  opportunity_id: number;
  funnel: { funnel_name: string; pages: FunnelPage[] };
  funnel_strategy?: Record<string, unknown> | null;
  writing_jobs: WritingJob[];
  services_used: string[];
  persisted: boolean;
  warnings: string[];
}

export interface AgentLog {
  id?: number;
  run_id?: number;
  opportunity_id?: number | null;
  agent?: string;
  phase?: string;
  level: 'debug' | 'info' | 'warn' | 'error';
  step?: string | null;
  message: string;
  payload?: Record<string, unknown> | null;
  n8n_execution_id?: string | null;
  duration_ms?: number | null;
  created_at?: string;
}

// --- API response shapes ---

export interface DiscoveryResponse {
  run: PautadorRun;
  meta: {
    country: string;
    native_language?: string | null;
    market_tier?: MarketTier | null;
    engine: string;
    model?: string | null;
    grounding_calls: number;
    generated_at?: string | null;
  };
  cultural_intelligence: CulturalIntelligence;
  personas: Persona[];
  insights: Insights;
  opportunities: Opportunity[];
  stats: RunStats;
  persisted: boolean;
  warnings: string[];
}

// --- Kanban ---

export interface PautadorKanbanColumn {
  id: string;
  title: string;
  statuses: OpportunityStatus[];
  color: string;
}

export const PAUTADOR_KANBAN_COLUMNS: PautadorKanbanColumn[] = [
  { id: 'discovered', title: 'Descobertas',  statuses: ['discovered'], color: 'gray'   },
  { id: 'validating', title: 'Em validação', statuses: ['validating'], color: 'blue'   },
  { id: 'mining',     title: 'Em mineração', statuses: ['mining'],     color: 'yellow' },
  { id: 'funnel',     title: 'Em funil',     statuses: ['funnel'],     color: 'purple' },
  { id: 'ready',      title: 'Pronto',       statuses: ['ready'],      color: 'green'  },
  { id: 'rejected',   title: 'Rejeitado',    statuses: ['rejected'],   color: 'red'    },
];

// --- Labels & Colors ---

export const TIER_META: Record<Tier, { label: string; short: string; bg: string; text: string; border: string }> = {
  S:            { label: 'Ouro Puro',    short: 'S',   bg: 'bg-amber-50',   text: 'text-amber-700',   border: 'border-amber-300'   },
  A:            { label: 'Ouro',         short: 'A',   bg: 'bg-yellow-50',  text: 'text-yellow-700',  border: 'border-yellow-300'  },
  B:            { label: 'Prata',        short: 'B',   bg: 'bg-slate-100',  text: 'text-slate-600',   border: 'border-slate-300'   },
  EXPERIMENTAL: { label: 'Experimental', short: 'EXP', bg: 'bg-fuchsia-50', text: 'text-fuchsia-700', border: 'border-fuchsia-300' },
};

export const CATEGORY_LABELS: Record<Category, string> = {
  S1: 'Ponte de utilidade',
  S2: 'Ouro processual',
  S3: 'Quem tem direito',
  S4: 'Calculadora',
  S5: 'Janela temporal',
  S6: 'Dor única do país',
  A1: 'Problema-solução',
  A2: 'Comparação',
  A3: 'Sintomas e condições',
  A4: 'Direitos do cidadão',
  B1: 'Como usar apps',
  B2: 'Documentos e certidões',
  B3: 'Calendário',
  EXP: 'Experimental',
};

export const QUAL_LABELS: Record<Qual4, string> = {
  low: 'Baixo',
  medium: 'Médio',
  high: 'Alto',
  very_high: 'Muito alto',
};

export const COMPETITION_LABELS: Record<Competition, string> = {
  low: 'Baixa',
  medium: 'Média',
  high: 'Alta',
};

export const INTENT_LABELS: Record<Intent, string> = {
  informational: 'Informacional',
  navigational: 'Navegacional',
  calculator: 'Calculadora',
  comparison: 'Comparação',
};

export const TIMING_LABELS: Record<Timing, string> = {
  evergreen: 'Perene',
  seasonal: 'Sazonal',
  event_driven: 'Dirigido por evento',
  trending: 'Em alta',
};

export const STATUS_LABELS: Record<OpportunityStatus, string> = {
  discovered: 'Descoberta',
  validating: 'Em validação',
  mining: 'Em mineração',
  funnel: 'Em funil',
  ready: 'Pronto',
  rejected: 'Rejeitado',
  archived: 'Arquivado',
};
