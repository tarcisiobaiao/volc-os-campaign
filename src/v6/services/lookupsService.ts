/**
 * v6 RBAC — lookupsService
 *
 * Read-only. Provê listas de entidades legadas (users, campaigns)
 * usadas pelos formulários do v6 (selects, comboboxes, etc).
 *
 * Lê via supabase direto, sem importar serviços legados — mantém o
 * isolamento de leitura. (A exceção controlada de import legado é
 * apenas em `v6OperationsService.ts` para criação/edição de usuário.)
 */
import { supabase } from '@/lib/supabase';
import { fetchAllPaginated } from '@/v6/services/_pagination';
import { normalizeRole } from '@/v6/hooks/useCampaignRoles';
import type {
  UserLite,
  CampaignLite,
  CampaignWithContext,
  CampaignMember,
  CampaignCommission,
  CampaignRole,
  ProjectLite,
} from '@/v6/types/v6';

interface CampaignRowWithProject {
  campaign_id: string;
  campaign_name: string | null;
  project_id: number | null;
}

class LookupsService {
  /** Todos os usuários do sistema (paginado para futuro-proof). */
  async listUsers(): Promise<UserLite[]> {
    return fetchAllPaginated<UserLite>(async (from, to) => {
      const result = await supabase
        .from('users')
        .select('id, name, email, role, commission_percentage')
        .order('name', { ascending: true })
        .order('id', { ascending: true })
        .range(from, to);
      return { data: result.data as UserLite[] | null, error: result.error };
    });
  }

  /** Todas as campanhas do sistema (paginado). */
  async listCampaigns(): Promise<CampaignLite[]> {
    return fetchAllPaginated<CampaignLite>(async (from, to) => {
      const result = await supabase
        .from('campaigns')
        .select('campaign_id, campaign_name')
        .order('campaign_name', { ascending: true })
        .order('campaign_id', { ascending: true })
        .range(from, to);
      return { data: result.data as CampaignLite[] | null, error: result.error };
    });
  }

  /**
   * Lista projetos/sites do sistema com a contagem de campanhas
   * de cada um. Usado pelo seletor cascata Projeto → Campanha.
   */
  async listProjects(): Promise<ProjectLite[]> {
    const [projectsRes, campaignsForCount] = await Promise.all([
      fetchAllPaginated<{ id: number; project_name: string; domain: string | null; main_url: string | null }>(
        async (from, to) => {
          const result = await supabase
            .from('projects')
            .select('id, project_name, domain, main_url')
            .order('project_name', { ascending: true })
            .order('id', { ascending: true })
            .range(from, to);
          return {
            data: result.data as
              | { id: number; project_name: string; domain: string | null; main_url: string | null }[]
              | null,
            error: result.error,
          };
        }
      ),
      fetchAllPaginated<{ project_id: number | null }>(async (from, to) => {
        const result = await supabase
          .from('campaigns')
          .select('id, project_id')
          .order('id', { ascending: true })
          .range(from, to);
        return {
          data: result.data as { project_id: number | null }[] | null,
          error: result.error,
        };
      }),
    ]);

    const counts = new Map<number, number>();
    for (const c of campaignsForCount) {
      if (c.project_id != null) {
        counts.set(c.project_id, (counts.get(c.project_id) || 0) + 1);
      }
    }

    return projectsRes.map((p) => ({
      id: p.id,
      name: p.project_name,
      domain: p.domain || extractDomain(p.main_url),
      campaigns_count: counts.get(p.id) || 0,
    }));
  }

  /**
   * Lista todas as campanhas COM contexto enriquecido para os
   * formulários da v6: para cada campanha, informa quem já é
   * membro (com role) e quais comissões estão vigentes hoje.
   *
   * Importante: NÃO filtra nada. Toda campanha aparece, mesmo que
   * já tenha N membros. O contexto é apenas informacional.
   */
  async listCampaignsWithContext(): Promise<CampaignWithContext[]> {
    const today = new Date().toISOString().slice(0, 10);

    const [campaigns, members, commissions, users, roles] = await Promise.all([
      this.listCampaignsWithProject(),
      this.listAllMembers(),
      this.listActiveCommissions(today),
      this.listUsers(),
      this.listAllRoles(),
    ]);

    const usersById = new Map(users.map((u) => [u.id, u]));
    const rolesById = new Map(roles.map(normalizeRole).map((r) => [r.id, r]));

    // Indexa members por campaign_id
    const membersByCampaign = new Map<string, typeof members>();
    for (const m of members) {
      const arr = membersByCampaign.get(m.campaign_id) || [];
      arr.push(m);
      membersByCampaign.set(m.campaign_id, arr);
    }

    // Indexa commissions vigentes por campaign_id
    const commissionsByCampaign = new Map<string, typeof commissions>();
    for (const c of commissions) {
      const arr = commissionsByCampaign.get(c.campaign_id) || [];
      arr.push(c);
      commissionsByCampaign.set(c.campaign_id, arr);
    }

    return campaigns.map((c) => {
      const ms = membersByCampaign.get(c.campaign_id) || [];
      const cs = commissionsByCampaign.get(c.campaign_id) || [];
      return {
        campaign_id: c.campaign_id,
        campaign_name: c.campaign_name,
        project_id: c.project_id,
        members: ms.map((m) => {
          const u = usersById.get(m.user_id);
          const r = rolesById.get(m.role_id);
          return {
            user_id: m.user_id,
            user_name: u?.name ?? null,
            user_email: u?.email ?? '(desconhecido)',
            role_id: m.role_id,
            role_code: r?.code ?? `#${m.role_id}`,
            role_label: r?.label ?? `role ${m.role_id}`,
          };
        }),
        active_commissions: cs.map((cc) => {
          const u = usersById.get(cc.user_id);
          return {
            user_id: cc.user_id,
            user_email: u?.email ?? '(desconhecido)',
            percentage: cc.percentage,
            valid_from: cc.valid_from,
          };
        }),
      };
    });
  }

  // ----------------------------------------------------------------
  // Helpers privados — paginados, focados em apenas as colunas
  // necessárias para enriquecer o contexto
  // ----------------------------------------------------------------

  /** Igual ao listCampaigns, mas inclui project_id (necessário para o cascade). */
  private async listCampaignsWithProject(): Promise<CampaignRowWithProject[]> {
    return fetchAllPaginated<CampaignRowWithProject>(async (from, to) => {
      const result = await supabase
        .from('campaigns')
        .select('campaign_id, campaign_name, project_id')
        .order('campaign_name', { ascending: true })
        .order('campaign_id', { ascending: true })
        .range(from, to);
      return {
        data: result.data as CampaignRowWithProject[] | null,
        error: result.error,
      };
    });
  }

  private async listAllMembers(): Promise<CampaignMember[]> {
    return fetchAllPaginated<CampaignMember>(async (from, to) => {
      const result = await supabase
        .from('campaign_members')
        .select('id, user_id, campaign_id, role_id, created_at, created_by')
        .order('id', { ascending: true })
        .range(from, to);
      return { data: result.data as CampaignMember[] | null, error: result.error };
    });
  }

  private async listActiveCommissions(today: string): Promise<CampaignCommission[]> {
    return fetchAllPaginated<CampaignCommission>(async (from, to) => {
      const result = await supabase
        .from('campaign_commissions')
        .select(
          'id, user_id, campaign_id, percentage, valid_from, valid_to, created_at, created_by, notes'
        )
        .lte('valid_from', today)
        .or(`valid_to.is.null,valid_to.gte.${today}`)
        .order('id', { ascending: true })
        .range(from, to);
      return { data: result.data as CampaignCommission[] | null, error: result.error };
    });
  }

  private async listAllRoles(): Promise<CampaignRole[]> {
    const { data, error } = await supabase
      .from('campaign_roles')
      .select('id, code, label, description, created_at')
      .order('id', { ascending: true });
    if (error) throw error;
    return (data || []) as CampaignRole[];
  }
}

/**
 * Extrai o host (sem `www.`) de uma URL. Usado como fallback do
 * campo `domain` do projeto. Retorna `null` se a URL for inválida
 * ou ausente.
 */
function extractDomain(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const u = new URL(url.startsWith('http') ? url : `https://${url}`);
    return u.host.replace(/^www\./, '');
  } catch {
    return null;
  }
}

export const lookupsService = new LookupsService();
