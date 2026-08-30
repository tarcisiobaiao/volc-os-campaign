import { supabase } from '@/lib/supabase';

export interface OperatorDailyMetric {
  date: string;
  investment: number;
  revenue: number;
}

/**
 * Serviço de apoio ao relatório por operador (admin).
 *
 * getSummary/getDailyMetrics do supabaseDataService não aplicam
 * userProjectIds/userCampaignIds, então a série diária do recorte por
 * operador é agregada aqui direto de daily_campaign_metrics, restrita
 * aos campaign_ids (Google Ads, varchar) atribuídos ao operador.
 */
class OperatorReportService {
  async getDailyMetricsForCampaigns(
    campaignIds: string[],
    startDate: string,
    endDate: string
  ): Promise<OperatorDailyMetric[]> {
    if (!campaignIds.length || !startDate || !endDate) return [];

    const IN_CHUNK = 200; // evita estourar limite de URL do PostgREST
    const PAGE_SIZE = 1000;
    const HARD_CAP_PAGES = 500;
    const byDate = new Map<string, { investment: number; revenue: number }>();

    for (let i = 0; i < campaignIds.length; i += IN_CHUNK) {
      const slice = campaignIds.slice(i, i + IN_CHUNK);

      for (let page = 0; page < HARD_CAP_PAGES; page++) {
        // Ordenação com desempate único (date, campaign_id): 'date' sozinho não é
        // ordem total e a paginação via .range() poderia duplicar/pular linhas
        const { data: rows, error } = await supabase
          .from('daily_campaign_metrics')
          .select('date, spend, revenue_converted_revshare')
          .gte('date', startDate)
          .lte('date', endDate)
          .in('campaign_id', slice)
          .order('date', { ascending: true })
          .order('campaign_id', { ascending: true })
          .range(page * PAGE_SIZE, (page + 1) * PAGE_SIZE - 1);

        if (error) {
          console.error('❌ Erro ao buscar métricas diárias do operador:', error);
          throw error;
        }
        if (!rows || rows.length === 0) break;

        for (const r of rows) {
          const acc = byDate.get(r.date) ?? { investment: 0, revenue: 0 };
          acc.investment += Number(r.spend ?? 0);
          acc.revenue += Number(r.revenue_converted_revshare ?? 0);
          byDate.set(r.date, acc);
        }

        if (rows.length < PAGE_SIZE) break;

        if (page === HARD_CAP_PAGES - 1) {
          console.warn('⚠️ Série diária do operador truncada no limite de páginas:', {
            chunkStart: i, pages: HARD_CAP_PAGES, startDate, endDate
          });
        }
      }
    }

    return Array.from(byDate.entries())
      .map(([date, m]) => ({ date, ...m }))
      .sort((a, b) => a.date.localeCompare(b.date));
  }
}

export const operatorReportService = new OperatorReportService();
