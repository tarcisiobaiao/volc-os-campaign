/**
 * v6 RBAC — memberPayoutsService
 *
 * Read-only. Lê de `public.daily_campaign_member_payouts` e produz
 * agregações para a UI admin v6.
 *
 * Padrão de uso recomendado:
 *   1. Hook chama `fetchAdminBundle()` UMA vez (3 fetches paralelos).
 *   2. Hook chama os agregadores passando o bundle como argumento.
 *      Os agregadores são puros (não fazem fetch quando recebem o
 *      bundle).
 *
 * Os métodos públicos exigidos pelo brief (`aggregateByUser()`,
 * `aggregateByMonth()`, etc.) também aceitam ser chamados sem
 * argumento — nesse caso fazem o fetch internamente. Útil para
 * scripts/console, mas a página deve usar o hook (que cacheia).
 */
import { supabase } from '@/lib/supabase';
import { fetchAllPaginated } from '@/v6/services/_pagination';
import type {
  DailyCampaignMemberPayout,
  DailyCampaignMemberPayoutEnriched,
  PayoutsAdminBundle,
  PayoutsByUser,
  PayoutsByMonth,
  TopCampaignResult,
  SummaryStats,
  UserLite,
  CampaignLite,
} from '@/v6/types/v6';

class MemberPayoutsService {
  // -------------------------------------------------------------
  // Fetch primitives — todos paginados via fetchAllPaginated para
  // escapar do cap de 1000 linhas do PostgREST. Ver _pagination.ts
  // -------------------------------------------------------------

  /**
   * Busca o histórico completo de payouts. Pagina internamente
   * (1000 linhas por requisição) até esgotar.
   *
   * Ordenação composta (date desc, id asc) garante paginação
   * estável: muitos payouts compartilham a mesma `date`, então o
   * `id` como tiebreaker é obrigatório.
   */
  async fetchAllPayouts(): Promise<DailyCampaignMemberPayout[]> {
    return fetchAllPaginated<DailyCampaignMemberPayout>(async (from, to) => {
      const result = await supabase
        .from('daily_campaign_member_payouts')
        .select(
          'id, date, campaign_id, user_id, commission_percentage, revenue_revshare, spend, tax_rate, tax_amount, net_profit, amount, calculated_at, source'
        )
        .order('date', { ascending: false })
        .order('id', { ascending: true })
        .range(from, to);
      return { data: result.data as DailyCampaignMemberPayout[] | null, error: result.error };
    });
  }

  /** Mapa id -> UserLite, para enriquecimento client-side. */
  async fetchUsersMap(): Promise<Map<string, UserLite>> {
    const rows = await fetchAllPaginated<UserLite>(async (from, to) => {
      const result = await supabase
        .from('users')
        .select('id, name, email, role, commission_percentage')
        .order('id', { ascending: true })
        .range(from, to);
      return { data: result.data as UserLite[] | null, error: result.error };
    });
    return new Map(rows.map((u) => [u.id, u]));
  }

  /** Mapa campaign_id -> CampaignLite. */
  async fetchCampaignsMap(): Promise<Map<string, CampaignLite>> {
    const rows = await fetchAllPaginated<CampaignLite>(async (from, to) => {
      const result = await supabase
        .from('campaigns')
        .select('campaign_id, campaign_name')
        .order('campaign_id', { ascending: true })
        .range(from, to);
      return { data: result.data as CampaignLite[] | null, error: result.error };
    });
    return new Map(rows.map((c) => [c.campaign_id, c]));
  }

  /**
   * Bundle único usado pelo hook: faz 3 fetches em paralelo e
   * devolve tudo o que os agregadores precisam.
   */
  async fetchAdminBundle(): Promise<PayoutsAdminBundle> {
    const [payouts, usersById, campaignsById] = await Promise.all([
      this.fetchAllPayouts(),
      this.fetchUsersMap(),
      this.fetchCampaignsMap(),
    ]);
    return { payouts, usersById, campaignsById };
  }

  // -------------------------------------------------------------
  // Aggregators (puros se receberem o bundle, fazem fetch caso
  // contrário — para satisfazer o brief)
  // -------------------------------------------------------------

  async aggregateByUser(bundle?: PayoutsAdminBundle): Promise<PayoutsByUser[]> {
    const b = bundle ?? (await this.fetchAdminBundle());
    const acc = new Map<string, PayoutsByUser>();

    for (const p of b.payouts) {
      let row = acc.get(p.user_id);
      if (!row) {
        const u = b.usersById.get(p.user_id);
        row = {
          user_id: p.user_id,
          email: u?.email || '(usuário desconhecido)',
          name: u?.name ?? null,
          dias_com_payout: 0,
          campanhas_distintas: 0,
          revenue_total: 0,
          spend_total: 0,
          net_profit_total: 0,
          comissao_total: 0,
        };
        acc.set(p.user_id, row);
      }
      row.dias_com_payout += 1;
      row.revenue_total += p.revenue_revshare;
      row.spend_total += p.spend;
      row.net_profit_total += p.net_profit;
      row.comissao_total += p.amount;
    }

    // Contar campanhas distintas por usuário em uma segunda passada
    const campaignsByUser = new Map<string, Set<string>>();
    for (const p of b.payouts) {
      let s = campaignsByUser.get(p.user_id);
      if (!s) {
        s = new Set();
        campaignsByUser.set(p.user_id, s);
      }
      s.add(p.campaign_id);
    }
    for (const [user_id, set] of campaignsByUser) {
      const row = acc.get(user_id);
      if (row) row.campanhas_distintas = set.size;
    }

    return [...acc.values()].sort((a, b) => b.comissao_total - a.comissao_total);
  }

  async aggregateByMonth(
    userIdOrBundle?: string | PayoutsAdminBundle,
    bundleArg?: PayoutsAdminBundle
  ): Promise<PayoutsByMonth[]> {
    // Sobrecarga: chamada pode ser
    //   aggregateByMonth()                — fetch internamente
    //   aggregateByMonth(userId)          — fetch internamente, filtra por user
    //   aggregateByMonth(bundle)          — usa bundle, sem filtro
    //   aggregateByMonth(userId, bundle)  — usa bundle, filtra por user
    let userId: string | undefined;
    let bundle: PayoutsAdminBundle | undefined;
    if (typeof userIdOrBundle === 'string') {
      userId = userIdOrBundle;
      bundle = bundleArg;
    } else {
      bundle = userIdOrBundle;
    }
    const b = bundle ?? (await this.fetchAdminBundle());

    const filtered = userId ? b.payouts.filter((p) => p.user_id === userId) : b.payouts;

    const acc = new Map<string, PayoutsByMonth>();
    const campaignsByMonth = new Map<string, Set<string>>();

    for (const p of filtered) {
      // 'YYYY-MM-01'
      const month = p.date.slice(0, 7) + '-01';
      let row = acc.get(month);
      if (!row) {
        row = {
          month,
          linhas: 0,
          campanhas_distintas: 0,
          revenue_total: 0,
          spend_total: 0,
          net_profit_total: 0,
          comissao_total: 0,
        };
        acc.set(month, row);
      }
      row.linhas += 1;
      row.revenue_total += p.revenue_revshare;
      row.spend_total += p.spend;
      row.net_profit_total += p.net_profit;
      row.comissao_total += p.amount;

      let s = campaignsByMonth.get(month);
      if (!s) {
        s = new Set();
        campaignsByMonth.set(month, s);
      }
      s.add(p.campaign_id);
    }
    for (const [month, set] of campaignsByMonth) {
      const row = acc.get(month);
      if (row) row.campanhas_distintas = set.size;
    }

    return [...acc.values()].sort((a, b) => a.month.localeCompare(b.month));
  }

  async topCampaigns(
    limitOrBundle?: number | PayoutsAdminBundle,
    bundleArg?: PayoutsAdminBundle
  ): Promise<TopCampaignResult[]> {
    let limit = 10;
    let bundle: PayoutsAdminBundle | undefined;
    if (typeof limitOrBundle === 'number') {
      limit = limitOrBundle;
      bundle = bundleArg;
    } else {
      bundle = limitOrBundle;
    }
    const b = bundle ?? (await this.fetchAdminBundle());

    const acc = new Map<string, TopCampaignResult>();
    for (const p of b.payouts) {
      let row = acc.get(p.campaign_id);
      if (!row) {
        const c = b.campaignsById.get(p.campaign_id);
        row = {
          campaign_id: p.campaign_id,
          campaign_name: c?.campaign_name ?? null,
          dias_calculados: 0,
          revenue_total: 0,
          spend_total: 0,
          comissao_total: 0,
        };
        acc.set(p.campaign_id, row);
      }
      row.dias_calculados += 1;
      row.revenue_total += p.revenue_revshare;
      row.spend_total += p.spend;
      row.comissao_total += p.amount;
    }

    return [...acc.values()]
      .sort((a, b) => b.comissao_total - a.comissao_total)
      .slice(0, limit);
  }

  async summaryStats(bundle?: PayoutsAdminBundle): Promise<SummaryStats> {
    const b = bundle ?? (await this.fetchAdminBundle());
    const stats: SummaryStats = {
      total_payouts: b.payouts.length,
      total_payouts_with_commission: 0,
      distinct_users: 0,
      distinct_campaigns: 0,
      date_min: null,
      date_max: null,
      sum_revenue_revshare: 0,
      sum_spend: 0,
      sum_net_profit: 0,
      sum_amount: 0,
    };

    const users = new Set<string>();
    const campaigns = new Set<string>();
    for (const p of b.payouts) {
      users.add(p.user_id);
      campaigns.add(p.campaign_id);
      if (p.amount > 0) stats.total_payouts_with_commission += 1;
      stats.sum_revenue_revshare += p.revenue_revshare;
      stats.sum_spend += p.spend;
      stats.sum_net_profit += p.net_profit;
      stats.sum_amount += p.amount;
      if (!stats.date_min || p.date < stats.date_min) stats.date_min = p.date;
      if (!stats.date_max || p.date > stats.date_max) stats.date_max = p.date;
    }
    stats.distinct_users = users.size;
    stats.distinct_campaigns = campaigns.size;

    return stats;
  }

  async listTopPayoutRows(
    limitOrBundle?: number | PayoutsAdminBundle,
    bundleArg?: PayoutsAdminBundle
  ): Promise<DailyCampaignMemberPayoutEnriched[]> {
    let limit = 5;
    let bundle: PayoutsAdminBundle | undefined;
    if (typeof limitOrBundle === 'number') {
      limit = limitOrBundle;
      bundle = bundleArg;
    } else {
      bundle = limitOrBundle;
    }
    const b = bundle ?? (await this.fetchAdminBundle());

    return [...b.payouts]
      .sort((a, b2) => b2.amount - a.amount)
      .slice(0, limit)
      .map((p) => ({
        ...p,
        user: b.usersById.get(p.user_id) || null,
        campaign: b.campaignsById.get(p.campaign_id) || null,
      }));
  }
}

export const memberPayoutsService = new MemberPayoutsService();
