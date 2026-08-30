// ============================================
// PAUTADOR PRO — ENTITY-FIRST types
// Espelha backend/app/entities/schemas.py + src/sql/v7_03_pautador_entities.sql.
// A UNIDADE do Kanban é a ENTIDADE (RUT, DIAN, INSS…); keywords/dores/funis
// são subestrutura.
// ============================================

import type { OpportunityStatus } from '@/types/pautador';

// Espelha backend/app/entities/schemas.py::EntityDiscoveryRequest.
// niches=[] / seasonality=undefined => comportamento atual (diversificado), backward-compatible.
export interface EntityDiscoveryParams {
  country: string;
  country_code?: string;
  native_language?: string;
  count?: number;
  engine?: string;
  model?: string;
  persist?: boolean;
  niches?: string[];
  seasonality?: 'evergreen' | 'seasonal';
}

// Espelha backend/app/entities/schemas.py::PautadorNiche (Task 3).
// Seed rows podem omitir is_active/sort_order — por isso são opcionais.
export interface PautadorNiche {
  slug: string;
  label: string;
  guidance: string;
  allowed_verticals: string[];
  is_active?: boolean;
  sort_order?: number;
}

export interface EntityMeta {
  id?: number | null;
  canonical_name: string;
  full_name?: string | null;
  slug: string;
  country_code: string;
  country?: string | null;
  entity_type?: string | null;
  entity_category?: string | null;
  vertical?: string | null;
  official_source?: string | null;
  related_systems: string[];
  aliases: string[];
  description?: string | null;
  language?: string | null;
  niche_slug?: string | null;
}

export interface EntityPain {
  id?: number;
  pain_name: string;
  pain_description?: string | null;
  user_goal?: string | null;
  intent?: string | null;
  severity?: string | null;
}

export interface EntitySeedQuery {
  id?: number;
  query: string;
  query_type?: string | null;
  intent?: string | null;
  score?: number | null;
  source?: string | null;
}

// Canonical shape — toda resposta da API emite funnel_title/funnel_summary
// (o backend normaliza o title/summary do LLM em _norm_funnels).
export interface EntityFunnelHypothesis {
  id?: number;
  funnel_title?: string | null;
  funnel_summary?: string | null;
  pages: string[];
  status?: string;
}

/** Uma PERGUNTA CANDIDATA da entidade (v7_16/v7_17). Os dois eixos são da
 *  PERGUNTA, não da entidade — no nível da pergunta eles são bem definidos. */
export interface QuestionCandidate {
  frase: string;
  engajamento_level: string;
  ignorancia_level?: string;
}

/** Desfecho do registro no arraste DESCOBERTAS -> EM VALIDAÇÃO.
 *  `skipped` é DADO (o operador viu e pulou), não ausência de dado — e nenhum
 *  dos quatro impede o card de mover. */
export type QuestionChoiceOutcome = 'chosen' | 'custom' | 'skipped' | 'entity_rejected';

export interface QuestionChoicePayload {
  outcome: QuestionChoiceOutcome;
  chosen_index?: number | null;
  custom_frase?: string | null;
  custom_engajamento?: string | null;
  custom_ignorancia?: string | null;
  notes?: string | null;
  chosen_by?: string | null;
}

export interface EntityCard {
  id?: number | null;
  entity_id?: number | null;
  run_id?: number | null;
  country_code: string;
  status: OpportunityStatus;
  kanban_stage: string;
  gold_tier?: string | null;
  strategic_stage?: string | null;
  score?: number | null;
  estimated_volume?: number | null;
  ecpm_band?: string | null;
  roi_signal?: number | null;
  cpc_min?: number | null;
  cpc_max?: number | null;
  cpc_currency?: string | null;
  volume_level?: string | null;
  rpm_level?: string | null;
  competition_level?: string | null;
  confidence_level?: string | null;
  temporal_window?: string | null;
  /** v7_15 · SEGUNDO EIXO — o `score` diz se o mercado paga; isto diz se a pessoa
   *  LÊ o suficiente para o anúncio ser visto. Um não substitui o outro.
   *  `resposta_em_uma_frase` é o teste literal: a resposta da dúvida em UMA frase,
   *  escrita ANTES do rótulo de engajamento. */
  /** v7_16 · PERGUNTAS CANDIDATAS — três perguntas legítimas e distintas sobre a
   *  entidade, cada uma respondida em uma frase. Rotule assim na UI: nasceram como
   *  "votos" para um rótulo e não servem para isso (a distribuição é multimodal).
   *  Servem para arquitetura de funil: uma página de solução por pergunta, com um
   *  humano escolhendo quais viram página.
   *  ⚠️ Sugestão editorial, NUNCA entrada de score. O mesmo LLM inventando as
   *  perguntas e pontuando as próprias invenções é circuito fechado de opinião.
   *  Não derive `funnel_score` daqui. */
  respostas?: QuestionCandidate[] | null;
  /** A frase representativa, derivada de `respostas`. */
  resposta_em_uma_frase?: string | null;
  /** nao_sei_se_existe|nao_sei_se_sirvo|nao_sei_por_que_falhou|so_falta_um_dado|sei_o_que_fazer|nao_preciso_de_nada */
  ignorancia_level?: string | null;
  /** `sustenta` | `dado_unico`. Card antigo pode trazer um dos quatro
   *  níveis aposentados — a tela mapeia todos para `há o que ler`. */
  engajamento_level?: string | null;
  /** regra_mudou|fragmentada|ilegivel|clara */
  opacidade_level?: string | null;
  /** Portão fechado. INFORMA e sugere — NÃO bloqueia o arraste: quem arrasta decide. */
  reading_blocked?: boolean | null;
  reading_reason?: string | null;
  /** Força de leitura 0–1: média geométrica de ignorancia × engajamento × opacidade.
   *  ⚠️ NUNCA ordenar por ela. Tooltip do card, literalmente: "derivada de rótulos
   *  cuja estabilidade entre rodadas foi medida em 33% (uma frase) e 50% (três),
   *  contra 24–30% de acaso — nenhuma das duas se distingue do acaso. Serve para
   *  leitura humana do caso, não para ordenar." Ordenação é por `score`.
   *  Também não é o índice de 10 eixos do motor e não se compara com `score`. */
  reading_strength?: number | null;
  concrete_pain?: string | null;
  gold_reason?: string | null;
  /** Direcionamento para o AGENTE de funil (user prompt). Fora do DOCX e do ClickUp. */
  insights?: string | null;
  /** ⚠️ ÓRFÃO desde a saída do ClickUp: era o corpo da task, escrito para quem
   *  executa. O campo continua salvo e editável no drawer, mas HOJE NÃO É LIDO
   *  por nada. Fica porque há texto de operador gravado nele; decidir o destino
   *  dele é conversa, não limpeza. */
  task_description?: string | null;
  /** Nome de exibição do card, escrito pelo admin (ex.: "Site XPTO"). Diferencia
   *  cópias da mesma entidade; NÃO altera o canonical_name da entidade. */
  display_title?: string | null;
  /** Herança do webgo. As colunas seguem no banco (vazias: 0 de 20 cards) e
   *  nada mais escreve nelas — ver `tests/test_clickup.py`. */
  clickup_task_url?: string | null;
  funnel_completed?: boolean;
  /** Resumo da coluna "Em validação". Proveniência tem cor, valor não; o
   *  índice é texto e NÃO ordena o board (ordenação segue por `score`). */
  validacao?: import('./pautadorValidacao').ValidacaoResumo | null;
  entity: EntityMeta;
  pains: EntityPain[];
  seed_queries: EntitySeedQuery[];
  funnel_hypotheses: EntityFunnelHypothesis[];
  ephemeral?: boolean;
}

export interface EntityDiscoveryResponse {
  run_id?: number | null;
  country: string;
  country_code?: string | null;
  native_language?: string | null;
  engine: string;
  model?: string | null;
  items: EntityCard[];
  cultural_intelligence?: Record<string, unknown> | null;
  personas?: Array<Record<string, unknown>>;
  insights?: Record<string, unknown> | null;
  persisted: boolean;
  created_count: number;
  merged_count: number;
  warnings: string[];
}

export interface EntityListResponse {
  items: EntityCard[];
  source: string;
}

// resultado do disparo ao ClickUp (ao mover card p/ "Pronto")
export interface ClickupDispatch {
  dispatched: boolean;
  reason?: string;
  task_id?: string;
  task_url?: string | null;
  warnings?: string[];
}

export interface EntityStatusUpdateResult {
  opportunity: EntityCard;
  clickup?: ClickupDispatch;
}

export interface EntityMineResponse {
  entity_id: number;
  opportunity_id?: number | null;
  pains: EntityPain[];
  seed_queries: EntitySeedQuery[];
  services_used: string[];
  engine: string;
  mode?: string;          // 'internal' | 'n8n'
  dispatched?: boolean;   // true = webhook n8n disparado (resultado vem async)
  persisted: boolean;
  warnings: string[];
}

export interface FunnelPageSkeleton {
  position: number;
  page_title: string;
  stage?: string;
  role?: string;
  role_label?: string;
  emotional_goal?: string | null;
  subtitles?: string[];
  internal_links?: string[];
  intro_section?: string | string[];
  closing_section?: string | string[];
}

// papel da página derivado da posição (fallback quando role_label não veio)
export const funnelRoleLabel = (p: { position: number; role_label?: string | null }): string =>
  p.role_label || (p.position === 1 ? 'Landing Page (Pouso)' : p.position === 2 ? 'Pre-sell' : `Página Solução ${p.position - 2}`);

export interface WritingJob {
  job_id?: string;
  page_type?: string;
  writer_briefing?: Record<string, unknown>;
}

export interface EntityFunnelResponse {
  entity_id: number;
  opportunity_id?: number | null;
  funnel_hypotheses: EntityFunnelHypothesis[];
  funnel_strategy?: Record<string, unknown> | null;
  pages?: FunnelPageSkeleton[];
  writing_jobs?: WritingJob[];
  services_used: string[];
  engine: string;
  persisted: boolean;
  warnings: string[];
}

// helpers
export const entityKey = (c: EntityCard): string =>
  c.id ? `ent-${c.id}` : `slug-${c.country_code}-${c.entity.slug}`;

export const funnelTitle = (h: EntityFunnelHypothesis): string =>
  h.funnel_title || 'Funil';

export const funnelSummary = (h: EntityFunnelHypothesis): string =>
  h.funnel_summary || '';

export const entitySubtitle = (e: EntityMeta): string =>
  [e.full_name, e.official_source, e.country || e.country_code].filter(Boolean).join(' · ');
