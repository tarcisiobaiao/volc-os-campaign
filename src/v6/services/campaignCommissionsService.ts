/**
 * v6 RBAC — campaignCommissionsService
 *
 * Read-only. Lê de `public.campaign_commissions` (comissões versionadas
 * por vigência) e enriquece com lookups de `users` e `campaigns`.
 *
 * Todas as queries que podem ultrapassar 1000 linhas são paginadas
 * via `fetchAllPaginated` (ver `_pagination.ts`) para escapar do
 * cap silencioso do PostgREST.
 */
import { supabase } from '@/lib/supabase';
import { fetchAllPaginated } from '@/v6/services/_pagination';
import type {
  CampaignCommission,
  CampaignCommissionEnriched,
  CampaignLite,
  UserLite,
  CreateCommissionInput,
  EndCommissionInput,
} from '@/v6/types/v6';

const isActive = (c: CampaignCommission, today: string): boolean =>
  c.valid_from <= today && (c.valid_to === null || c.valid_to >= today);

class CampaignCommissionsService {
  /** Lista crua de todas as comissões versionadas (paginada). */
  async listAll(): Promise<CampaignCommission[]> {
    return fetchAllPaginated<CampaignCommission>(async (from, to) => {
      const result = await supabase
        .from('campaign_commissions')
        .select(
          'id, user_id, campaign_id, percentage, valid_from, valid_to, created_at, created_by, notes'
        )
        .order('valid_from', { ascending: false })
        .order('id', { ascending: true })
        .range(from, to);
      return { data: result.data as CampaignCommission[] | null, error: result.error };
    });
  }

  /** Comissões de um usuário específico (todas as vigências). */
  async listByUser(userId: string): Promise<CampaignCommission[]> {
    return fetchAllPaginated<CampaignCommission>(async (from, to) => {
      const result = await supabase
        .from('campaign_commissions')
        .select(
          'id, user_id, campaign_id, percentage, valid_from, valid_to, created_at, created_by, notes'
        )
        .eq('user_id', userId)
        .order('valid_from', { ascending: false })
        .order('id', { ascending: true })
        .range(from, to);
      return { data: result.data as CampaignCommission[] | null, error: result.error };
    });
  }

  /** Apenas comissões vigentes hoje (valid_to NULL). */
  async listActiveByUser(userId: string): Promise<CampaignCommission[]> {
    return fetchAllPaginated<CampaignCommission>(async (from, to) => {
      const result = await supabase
        .from('campaign_commissions')
        .select(
          'id, user_id, campaign_id, percentage, valid_from, valid_to, created_at, created_by, notes'
        )
        .eq('user_id', userId)
        .is('valid_to', null)
        .order('valid_from', { ascending: false })
        .order('id', { ascending: true })
        .range(from, to);
      return { data: result.data as CampaignCommission[] | null, error: result.error };
    });
  }

  /**
   * Lista de comissões enriquecida com user e campaign.
   * Útil para a CommissionsTimeline. Comissões, users e campaigns
   * são todos paginados.
   */
  async listWithUserData(): Promise<CampaignCommissionEnriched[]> {
    const today = new Date().toISOString().slice(0, 10);

    const [commissions, users, campaigns] = await Promise.all([
      // commissions paginado
      fetchAllPaginated<CampaignCommission>(async (from, to) => {
        const result = await supabase
          .from('campaign_commissions')
          .select(
            'id, user_id, campaign_id, percentage, valid_from, valid_to, created_at, created_by, notes'
          )
          .order('valid_from', { ascending: false })
          .order('id', { ascending: true })
          .range(from, to);
        return { data: result.data as CampaignCommission[] | null, error: result.error };
      }),
      // users paginado
      fetchAllPaginated<UserLite>(async (from, to) => {
        const result = await supabase
          .from('users')
          .select('id, name, email, role, commission_percentage')
          .order('id', { ascending: true })
          .range(from, to);
        return { data: result.data as UserLite[] | null, error: result.error };
      }),
      // campaigns paginado
      fetchAllPaginated<CampaignLite>(async (from, to) => {
        const result = await supabase
          .from('campaigns')
          .select('campaign_id, campaign_name')
          .order('campaign_id', { ascending: true })
          .range(from, to);
        return { data: result.data as CampaignLite[] | null, error: result.error };
      }),
    ]);

    const usersById = new Map<string, UserLite>(users.map((u) => [u.id, u]));
    const campaignsById = new Map<string, CampaignLite>(
      campaigns.map((c) => [c.campaign_id, c])
    );

    return commissions.map((c) => ({
      ...c,
      user: usersById.get(c.user_id) || null,
      campaign: campaignsById.get(c.campaign_id) || null,
      is_active: isActive(c, today),
    }));
  }

  /**
   * Timeline de comissões de um único usuário (todas as suas
   * vigências, mais recentes primeiro).
   */
  async listTimelineByUser(userId: string): Promise<CampaignCommissionEnriched[]> {
    const today = new Date().toISOString().slice(0, 10);

    const [commissions, userRes, campaigns] = await Promise.all([
      // commissions do usuário, paginado
      fetchAllPaginated<CampaignCommission>(async (from, to) => {
        const result = await supabase
          .from('campaign_commissions')
          .select(
            'id, user_id, campaign_id, percentage, valid_from, valid_to, created_at, created_by, notes'
          )
          .eq('user_id', userId)
          .order('valid_from', { ascending: false })
          .order('id', { ascending: true })
          .range(from, to);
        return { data: result.data as CampaignCommission[] | null, error: result.error };
      }),
      // single user — fetch direto
      supabase
        .from('users')
        .select('id, name, email, role, commission_percentage')
        .eq('id', userId)
        .maybeSingle(),
      // campaigns paginado
      fetchAllPaginated<CampaignLite>(async (from, to) => {
        const result = await supabase
          .from('campaigns')
          .select('campaign_id, campaign_name')
          .order('campaign_id', { ascending: true })
          .range(from, to);
        return { data: result.data as CampaignLite[] | null, error: result.error };
      }),
    ]);

    if (userRes.error) throw userRes.error;

    const user = (userRes.data as UserLite | null) || null;
    const campaignsById = new Map<string, CampaignLite>(
      campaigns.map((c) => [c.campaign_id, c])
    );

    return commissions.map((c) => ({
      ...c,
      user,
      campaign: campaignsById.get(c.campaign_id) || null,
      is_active: isActive(c, today),
    }));
  }

  // ============================================================
  // WRITE METHODS — Etapa 3.C operacional
  //
  // Comissão é VERSIONADA por vigência. Por design:
  //   - createCommission cria uma nova vigência (linha nova)
  //   - endCommission fecha uma vigência setando valid_to
  //   - NÃO há "editar percentage in-place": para mudar a taxa,
  //     o admin encerra a vigência atual e cria uma nova. Isso
  //     preserva o histórico financeiro intocado.
  //
  // NÃO toca em users.commission_percentage (legado).
  // ============================================================

  /**
   * Cria uma nova vigência de comissão. Se já houver uma vigência
   * aberta (valid_to NULL) para o mesmo (user, campaign), ela é
   * automaticamente encerrada com `valid_to = (valid_from - 1 dia)`
   * antes da nova ser criada — para evitar overlap semântico.
   */
  async createCommission(input: CreateCommissionInput): Promise<CampaignCommission> {
    // 1. Auto-encerrar vigência aberta anterior, se houver.
    const validFrom = input.valid_from;
    const dayBefore = subtractOneDay(validFrom);

    const openRes = await supabase
      .from('campaign_commissions')
      .select('id, valid_from')
      .eq('user_id', input.user_id)
      .eq('campaign_id', input.campaign_id)
      .is('valid_to', null)
      .order('valid_from', { ascending: false })
      .limit(1);

    if (openRes.error) throw openRes.error;
    const open = openRes.data?.[0];

    if (open) {
      // Só fecha se a vigência aberta começou ANTES da nova
      if (open.valid_from < validFrom) {
        const closeRes = await supabase
          .from('campaign_commissions')
          .update({ valid_to: dayBefore })
          .eq('id', open.id);
        if (closeRes.error) throw closeRes.error;
      } else if (open.valid_from === validFrom) {
        throw new Error(
          'Já existe uma comissão vigente começando exatamente nesta data. Use outra data ou edite a vigência existente.'
        );
      }
    }

    // 2. Criar a nova vigência
    const insertRes = await supabase
      .from('campaign_commissions')
      .insert([
        {
          user_id: input.user_id,
          campaign_id: input.campaign_id,
          percentage: input.percentage,
          valid_from: input.valid_from,
          valid_to: null,
          notes: input.notes ?? null,
          created_by: input.created_by ?? null,
        },
      ])
      .select(
        'id, user_id, campaign_id, percentage, valid_from, valid_to, created_at, created_by, notes'
      )
      .single();

    if (insertRes.error) throw insertRes.error;
    return insertRes.data as CampaignCommission;
  }

  /** Encerra uma vigência setando valid_to. */
  async endCommission(input: EndCommissionInput): Promise<CampaignCommission> {
    const { data, error } = await supabase
      .from('campaign_commissions')
      .update({ valid_to: input.valid_to })
      .eq('id', input.id)
      .select(
        'id, user_id, campaign_id, percentage, valid_from, valid_to, created_at, created_by, notes'
      )
      .single();

    if (error) throw error;
    return data as CampaignCommission;
  }
}

/** Subtrai 1 dia de uma data ISO 'YYYY-MM-DD'. */
function subtractOneDay(iso: string): string {
  const d = new Date(iso + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

export const campaignCommissionsService = new CampaignCommissionsService();
