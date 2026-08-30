/**
 * v6 RBAC — tipos TypeScript
 *
 * Espelham o schema real das 4 tabelas v6 em produção, validado via
 * `pg_constraint` e `information_schema.columns`. Mantenha alinhado
 * caso o schema mude.
 *
 * Convenções:
 *   - colunas `numeric` no Postgres viram `number` no TS
 *     (perda mínima de precisão para os volumes do projeto)
 *   - colunas `timestamptz` viram `string` ISO 8601
 *   - colunas `date` viram `string` no formato 'YYYY-MM-DD'
 *   - `uuid` vira `string`
 */

// =============================================================
// 1. Tipos espelho das tabelas
// =============================================================

export type CampaignRoleCode = 'OWNER' | 'OPERATOR' | 'REVIEWER' | 'VIEWER';

export interface CampaignRole {
  id: number;
  code: CampaignRoleCode | string;
  label: string;
  description: string | null;
  created_at: string;
}

export interface CampaignMember {
  id: number;
  user_id: string;
  campaign_id: string; // varchar = ID do Google Ads, NÃO o int PK
  role_id: number;
  created_at: string;
  created_by: string | null;
}

export interface CampaignCommission {
  id: number;
  user_id: string;
  campaign_id: string;
  percentage: number;
  valid_from: string; // 'YYYY-MM-DD'
  valid_to: string | null;
  created_at: string;
  created_by: string | null;
  notes: string | null;
}

export interface DailyCampaignMemberPayout {
  id: number;
  date: string; // 'YYYY-MM-DD'
  campaign_id: string;
  user_id: string;
  commission_percentage: number;
  revenue_revshare: number;
  spend: number;
  tax_rate: number;
  tax_amount: number;
  net_profit: number;
  amount: number;
  calculated_at: string;
  source: string;
}

// =============================================================
// 2. Lookups (entidades legadas que enriquecem a UI v6)
// =============================================================

export interface UserLite {
  id: string;
  name: string | null;
  email: string;
  role: 'ADMIN' | 'OPERATOR' | string;
  commission_percentage: number | null;
}

export interface CampaignLite {
  campaign_id: string;
  campaign_name: string | null;
}

/** Projeto/site para o seletor cascata projeto → campanha. */
export interface ProjectLite {
  id: number;
  name: string;
  domain: string | null;
  campaigns_count: number;
}

/**
 * Campanha com contexto enriquecido para os formulários da v6.
 *
 * Princípio: campanha pode ter múltiplos membros (cada um com role
 * funcional próprio) e múltiplas comissões vigentes (cada uma para
 * um par usuário/campanha distinto). NUNCA bloquear seleção apenas
 * por já existirem membros — só MOSTRAR contexto.
 */
export interface CampaignMemberContext {
  user_id: string;
  user_name: string | null;
  user_email: string;
  role_id: number;
  role_code: string;
  role_label: string;
}

export interface CampaignCommissionContext {
  user_id: string;
  user_email: string;
  percentage: number;
  valid_from: string;
}

export interface CampaignWithContext {
  campaign_id: string;
  campaign_name: string | null;
  /** FK para projects.id (int). Usado pelo cascade Projeto → Campanha. */
  project_id: number | null;
  members: CampaignMemberContext[];
  active_commissions: CampaignCommissionContext[];
}

// =============================================================
// 3. Tipos enriquecidos (com dados de lookup já mesclados)
// =============================================================

export interface CampaignMemberEnriched extends CampaignMember {
  user: UserLite | null;
  role: CampaignRole | null;
  campaign: CampaignLite | null;
}

export interface CampaignCommissionEnriched extends CampaignCommission {
  user: UserLite | null;
  campaign: CampaignLite | null;
  is_active: boolean;
}

export interface DailyCampaignMemberPayoutEnriched extends DailyCampaignMemberPayout {
  user: UserLite | null;
  campaign: CampaignLite | null;
}

// =============================================================
// 4. DTOs agregados para a UI
// =============================================================

export interface PayoutsByUser {
  user_id: string;
  email: string;
  name: string | null;
  dias_com_payout: number;
  campanhas_distintas: number;
  revenue_total: number;
  spend_total: number;
  net_profit_total: number;
  comissao_total: number;
}

export interface PayoutsByMonth {
  /** Primeiro dia do mês: 'YYYY-MM-01' */
  month: string;
  linhas: number;
  campanhas_distintas: number;
  revenue_total: number;
  spend_total: number;
  net_profit_total: number;
  comissao_total: number;
}

export interface TopCampaignResult {
  campaign_id: string;
  campaign_name: string | null;
  dias_calculados: number;
  revenue_total: number;
  spend_total: number;
  comissao_total: number;
}

export interface SummaryStats {
  total_payouts: number;
  total_payouts_with_commission: number;
  distinct_users: number;
  distinct_campaigns: number;
  date_min: string | null;
  date_max: string | null;
  sum_revenue_revshare: number;
  sum_spend: number;
  sum_net_profit: number;
  sum_amount: number;
}

export interface MembersCountByRole {
  role_id: number;
  role_code: string;
  role_label: string;
  total: number;
}

// =============================================================
// 5. Bundle interno usado pelos hooks (não export para a UI)
// =============================================================

export interface PayoutsAdminBundle {
  payouts: DailyCampaignMemberPayout[];
  usersById: Map<string, UserLite>;
  campaignsById: Map<string, CampaignLite>;
}

// =============================================================
// 6. Inputs de mutação (Etapa 3.C — fase operacional)
// =============================================================

export interface CreateUserInput {
  name: string;
  email: string;
  password: string;
  role: 'ADMIN' | 'OPERATOR';
}

export interface UpdateUserInput {
  id: string;
  name?: string;
  email?: string;
  role?: 'ADMIN' | 'OPERATOR';
}

export interface CreateMembershipInput {
  user_id: string;
  campaign_id: string;
  role_id: number;
  /** id do admin que criou; usado para auditoria. */
  created_by?: string | null;
}

export interface UpdateMembershipInput {
  id: number;
  role_id: number;
}

export interface RemoveMembershipInput {
  id: number;
  user_id: string;
  campaign_id: string;
}

export interface CreateCommissionInput {
  user_id: string;
  campaign_id: string;
  percentage: number;
  /** 'YYYY-MM-DD' */
  valid_from: string;
  notes?: string | null;
  created_by?: string | null;
}

export interface EndCommissionInput {
  id: number;
  /** 'YYYY-MM-DD'. Default = hoje. */
  valid_to: string;
}

/** Item de membership a ser criado durante onboarding unificado. */
export interface OnboardingMembership {
  campaign_id: string;
  role_id: number;
}

/** Item de comissão a ser criado durante onboarding unificado. */
export interface OnboardingCommission {
  campaign_id: string;
  percentage: number;
  valid_from: string;
  notes?: string | null;
}

/**
 * Input do fluxo unificado: cria usuário, adiciona memberships e
 * opcionalmente cria comissões em uma única operação atômica
 * (best-effort com rollback parcial em caso de falha).
 */
export interface OnboardingInput {
  user: CreateUserInput;
  memberships: OnboardingMembership[];
  commissions: OnboardingCommission[];
}
