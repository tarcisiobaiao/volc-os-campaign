/**
 * v6 RBAC — campaignMembersService
 *
 * Read-only. Lê de `public.campaign_members` e enriquece com lookups
 * de `users`, `campaigns` e `campaign_roles` quando necessário.
 *
 * Todas as queries que podem ultrapassar 1000 linhas são paginadas
 * via `fetchAllPaginated` (ver `_pagination.ts`) para escapar do
 * cap silencioso do PostgREST.
 *
 * Não escreve em nada. Não cria mutations.
 */
import { supabase } from '@/lib/supabase';
import { fetchAllPaginated } from '@/v6/services/_pagination';
import { normalizeRole } from '@/v6/hooks/useCampaignRoles';
import type {
  CampaignMember,
  CampaignMemberEnriched,
  CampaignRole,
  CampaignLite,
  UserLite,
  MembersCountByRole,
  CreateMembershipInput,
  UpdateMembershipInput,
  RemoveMembershipInput,
} from '@/v6/types/v6';

class CampaignMembersService {
  /** Lista crua de campaign_members (paginada). */
  async listAll(): Promise<CampaignMember[]> {
    return fetchAllPaginated<CampaignMember>(async (from, to) => {
      const result = await supabase
        .from('campaign_members')
        .select('id, user_id, campaign_id, role_id, created_at, created_by')
        .order('created_at', { ascending: false })
        .order('id', { ascending: true })
        .range(from, to);
      return { data: result.data as CampaignMember[] | null, error: result.error };
    });
  }

  /** Members de uma campanha específica (paginada). */
  async listByCampaign(campaignId: string): Promise<CampaignMember[]> {
    return fetchAllPaginated<CampaignMember>(async (from, to) => {
      const result = await supabase
        .from('campaign_members')
        .select('id, user_id, campaign_id, role_id, created_at, created_by')
        .eq('campaign_id', campaignId)
        .order('created_at', { ascending: false })
        .order('id', { ascending: true })
        .range(from, to);
      return { data: result.data as CampaignMember[] | null, error: result.error };
    });
  }

  /** Members de um usuário específico (paginada). */
  async listByUser(userId: string): Promise<CampaignMember[]> {
    return fetchAllPaginated<CampaignMember>(async (from, to) => {
      const result = await supabase
        .from('campaign_members')
        .select('id, user_id, campaign_id, role_id, created_at, created_by')
        .eq('user_id', userId)
        .order('created_at', { ascending: false })
        .order('id', { ascending: true })
        .range(from, to);
      return { data: result.data as CampaignMember[] | null, error: result.error };
    });
  }

  /** Contagem de members agrupado por role. */
  async countByRole(): Promise<MembersCountByRole[]> {
    const [members, rolesRes] = await Promise.all([
      // members paginado
      fetchAllPaginated<{ role_id: number }>(async (from, to) => {
        const result = await supabase
          .from('campaign_members')
          .select('id, role_id')
          .order('id', { ascending: true })
          .range(from, to);
        return { data: result.data as { role_id: number }[] | null, error: result.error };
      }),
      // roles é catálogo pequeno (<10 linhas) — fetch direto
      supabase
        .from('campaign_roles')
        .select('id, code, label, description, created_at')
        .order('id'),
    ]);

    if (rolesRes.error) throw rolesRes.error;
    const roles = ((rolesRes.data || []) as CampaignRole[]).map(normalizeRole);

    const counts = new Map<number, number>();
    for (const m of members) {
      counts.set(m.role_id, (counts.get(m.role_id) || 0) + 1);
    }

    return roles.map((r) => ({
      role_id: r.id,
      role_code: r.code,
      role_label: r.label,
      total: counts.get(r.id) || 0,
    }));
  }

  /**
   * Lista de members enriquecida com dados de user, role e campaign.
   * Faz 4 fetches paralelos (members + roles + users + campaigns) e
   * mescla client-side. Members e campaigns são paginados.
   */
  async listWithUserData(): Promise<CampaignMemberEnriched[]> {
    const [members, roles, users, campaigns] = await Promise.all([
      // members paginado
      fetchAllPaginated<CampaignMember>(async (from, to) => {
        const result = await supabase
          .from('campaign_members')
          .select('id, user_id, campaign_id, role_id, created_at, created_by')
          .order('created_at', { ascending: false })
          .order('id', { ascending: true })
          .range(from, to);
        return { data: result.data as CampaignMember[] | null, error: result.error };
      }),
      // roles é catálogo pequeno
      (async () => {
        const r = await supabase
          .from('campaign_roles')
          .select('id, code, label, description, created_at');
        if (r.error) throw r.error;
        return (r.data || []) as CampaignRole[];
      })(),
      // users paginado (preventivo — hoje é pequeno, pode crescer)
      fetchAllPaginated<UserLite>(async (from, to) => {
        const result = await supabase
          .from('users')
          .select('id, name, email, role, commission_percentage')
          .order('id', { ascending: true })
          .range(from, to);
        return { data: result.data as UserLite[] | null, error: result.error };
      }),
      // campaigns paginado (740 hoje, cresce)
      fetchAllPaginated<CampaignLite>(async (from, to) => {
        const result = await supabase
          .from('campaigns')
          .select('campaign_id, campaign_name')
          .order('campaign_id', { ascending: true })
          .range(from, to);
        return { data: result.data as CampaignLite[] | null, error: result.error };
      }),
    ]);

    const normalizedRoles = roles.map(normalizeRole);
    const rolesById = new Map<number, CampaignRole>(
      normalizedRoles.map((r) => [r.id, r])
    );
    const usersById = new Map<string, UserLite>(users.map((u) => [u.id, u]));
    const campaignsById = new Map<string, CampaignLite>(
      campaigns.map((c) => [c.campaign_id, c])
    );

    return members.map((m) => ({
      ...m,
      user: usersById.get(m.user_id) || null,
      role: rolesById.get(m.role_id) || null,
      campaign: campaignsById.get(m.campaign_id) || null,
    }));
  }

  // ============================================================
  // WRITE METHODS — Etapa 3.C operacional
  //
  // DUAL-WRITE: cada operação de escrita também sincroniza com a
  // tabela legada `user_campaigns` para que o app legado continue
  // enxergando os vínculos do operador. Padrão transitional
  // dual-write — manter até o cutover do `useUserFilters`.
  // ============================================================

  /**
   * Cria um vínculo (campaign_members) e garante que o legado
   * `user_campaigns` também tenha o par (user, campaign).
   *
   * Idempotente:
   *   - Se a linha já existir em campaign_members (mesmo
   *     user_id+campaign_id+role_id), reusa via SELECT pós-conflito.
   *   - Se a linha já existir em user_campaigns, ignora silenciosamente.
   */
  async addMember(input: CreateMembershipInput): Promise<CampaignMember> {
    // 1. Insert em campaign_members. Se conflitar com a UNIQUE
    //    (user_id, campaign_id, role_id), precisamos buscar a linha
    //    existente. Não usamos `.upsert` aqui porque a UNIQUE não é
    //    a PK e o postgrest se confunde — fazemos select fallback.
    const insertRes = await supabase
      .from('campaign_members')
      .insert([
        {
          user_id: input.user_id,
          campaign_id: input.campaign_id,
          role_id: input.role_id,
          created_by: input.created_by ?? null,
        },
      ])
      .select('id, user_id, campaign_id, role_id, created_at, created_by')
      .maybeSingle();

    let member: CampaignMember;
    if (insertRes.error) {
      // 23505 = unique_violation
      const code = (insertRes.error as { code?: string }).code;
      if (code === '23505') {
        const existing = await supabase
          .from('campaign_members')
          .select('id, user_id, campaign_id, role_id, created_at, created_by')
          .eq('user_id', input.user_id)
          .eq('campaign_id', input.campaign_id)
          .eq('role_id', input.role_id)
          .maybeSingle();
        if (existing.error || !existing.data) throw insertRes.error;
        member = existing.data as CampaignMember;
      } else {
        throw insertRes.error;
      }
    } else if (!insertRes.data) {
      throw new Error('Falha ao criar membership: nenhuma linha retornada.');
    } else {
      member = insertRes.data as CampaignMember;
    }

    // 2. Dual-write: garantir presença em user_campaigns.
    //    `user_campaigns` tem UNIQUE(user_id, campaign_id), sem role.
    //    Múltiplos roles do mesmo (user, campaign) não duplicam linha.
    const ucRes = await supabase
      .from('user_campaigns')
      .insert([{ user_id: input.user_id, campaign_id: input.campaign_id }]);
    if (ucRes.error) {
      const code = (ucRes.error as { code?: string }).code;
      if (code !== '23505') {
        console.error('[v6] dual-write user_campaigns falhou:', ucRes.error);
        throw ucRes.error;
      }
    }

    // 3. Dual-write: garantir presença em user_projects.
    //    O dashboard legado (useSupabaseData) filtra projetos via
    //    user_projects; sem esta linha o operador não enxerga o
    //    projeto mesmo tendo a campanha em user_campaigns.
    const campRes = await supabase
      .from('campaigns')
      .select('project_id')
      .eq('campaign_id', input.campaign_id)
      .maybeSingle();
    if (!campRes.error && campRes.data?.project_id) {
      const upRes = await supabase
        .from('user_projects')
        .insert([{ user_id: input.user_id, project_id: campRes.data.project_id }]);
      if (upRes.error) {
        const code = (upRes.error as { code?: string }).code;
        if (code !== '23505') {
          console.error('[v6] dual-write user_projects falhou:', upRes.error);
          throw upRes.error;
        }
      }
    }

    return member;
  }

  /**
   * Atualiza apenas o role funcional de um membership existente.
   * Não toca em user_campaigns (legado não tem role).
   */
  async updateMemberRole(input: UpdateMembershipInput): Promise<CampaignMember> {
    const { data, error } = await supabase
      .from('campaign_members')
      .update({ role_id: input.role_id })
      .eq('id', input.id)
      .select('id, user_id, campaign_id, role_id, created_at, created_by')
      .single();

    if (error) throw error;
    return data as CampaignMember;
  }

  /**
   * Remove um membership de campaign_members E sincroniza com
   * user_campaigns. ATENÇÃO: se o usuário tiver outros memberships
   * (outros roles) na mesma campanha, o user_campaigns NÃO é
   * removido — só é removido quando não há mais nenhum membership
   * desse par (user, campaign) no v6.
   *
   * NÃO remove campaign_commissions: a comissão tem ciclo de vida
   * próprio (deve ser encerrada explicitamente).
   */
  async removeMember(input: RemoveMembershipInput): Promise<void> {
    // 1. Delete em campaign_members
    const delRes = await supabase
      .from('campaign_members')
      .delete()
      .eq('id', input.id);
    if (delRes.error) throw delRes.error;

    // 2. Verifica se ainda existem outros memberships do mesmo
    //    (user, campaign). Se não, remove de user_campaigns também.
    const checkRes = await supabase
      .from('campaign_members')
      .select('id', { head: true, count: 'exact' })
      .eq('user_id', input.user_id)
      .eq('campaign_id', input.campaign_id);

    if (checkRes.error) throw checkRes.error;

    if ((checkRes.count ?? 0) === 0) {
      const ucDel = await supabase
        .from('user_campaigns')
        .delete()
        .eq('user_id', input.user_id)
        .eq('campaign_id', input.campaign_id);
      if (ucDel.error) {
        console.error('[v6] dual-write delete user_campaigns falhou:', ucDel.error);
        throw ucDel.error;
      }

      // Verifica se ainda há outras campanhas do mesmo projeto vinculadas
      // ao usuário. Se não houver, remove também de user_projects.
      const campRes = await supabase
        .from('campaigns')
        .select('project_id')
        .eq('campaign_id', input.campaign_id)
        .maybeSingle();
      if (!campRes.error && campRes.data?.project_id) {
        const projectId = campRes.data.project_id;
        // Todas as campanhas deste projeto que o usuário ainda tem em user_campaigns
        const remainingCamps = await supabase
          .from('campaigns')
          .select('campaign_id')
          .eq('project_id', projectId);
        const projectCampaignIds = (remainingCamps.data ?? []).map((c) => c.campaign_id);
        const remainingLinks = await supabase
          .from('user_campaigns')
          .select('id', { head: true, count: 'exact' })
          .eq('user_id', input.user_id)
          .in('campaign_id', projectCampaignIds.length > 0 ? projectCampaignIds : ['__none__']);
        if (!remainingLinks.error && (remainingLinks.count ?? 0) === 0) {
          await supabase
            .from('user_projects')
            .delete()
            .eq('user_id', input.user_id)
            .eq('project_id', projectId);
        }
      }
    }
  }
}

export const campaignMembersService = new CampaignMembersService();
