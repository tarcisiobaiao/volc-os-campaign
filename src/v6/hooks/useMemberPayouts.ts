/**
 * v6 RBAC — useMemberPayouts
 *
 * Faz UMA passada de fetch (payouts + users + campaigns) e expõe
 * todas as agregações via `useMemo`. Evita N round-trips quando a
 * página V6AdminPage usa várias visões dos mesmos dados.
 *
 * Padrão consistente com o resto do projeto: `useState` + `useEffect`,
 * sem React Query. Resultado é cacheado dentro do hook (não persiste
 * entre montagens).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { memberPayoutsService } from '@/v6/services/memberPayoutsService';
import type {
  PayoutsAdminBundle,
  PayoutsByMonth,
  PayoutsByUser,
  SummaryStats,
  TopCampaignResult,
  DailyCampaignMemberPayoutEnriched,
} from '@/v6/types/v6';

const TOP_CAMPAIGNS_LIMIT = 10;
const TOP_PAYOUT_ROWS_LIMIT = 5;

export interface UseMemberPayoutsResult {
  bundle: PayoutsAdminBundle | null;
  summary: SummaryStats | null;
  byUser: PayoutsByUser[];
  byMonth: PayoutsByMonth[];
  topCampaigns: TopCampaignResult[];
  topPayoutRows: DailyCampaignMemberPayoutEnriched[];
  isLoading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

export function useMemberPayouts(): UseMemberPayoutsResult {
  const [bundle, setBundle] = useState<PayoutsAdminBundle | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await memberPayoutsService.fetchAdminBundle();
      setBundle(result);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      setBundle(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  // Estado derivado, calculado uma vez por mudança de bundle.
  // memberPayoutsService aceita receber o bundle pronto, então isso
  // NÃO faz nenhum fetch novo.
  const [derived, setDerived] = useState<{
    summary: SummaryStats | null;
    byUser: PayoutsByUser[];
    byMonth: PayoutsByMonth[];
    topCampaigns: TopCampaignResult[];
    topPayoutRows: DailyCampaignMemberPayoutEnriched[];
  }>({
    summary: null,
    byUser: [],
    byMonth: [],
    topCampaigns: [],
    topPayoutRows: [],
  });

  useEffect(() => {
    if (!bundle) {
      setDerived({
        summary: null,
        byUser: [],
        byMonth: [],
        topCampaigns: [],
        topPayoutRows: [],
      });
      return;
    }

    let cancelled = false;
    Promise.all([
      memberPayoutsService.summaryStats(bundle),
      memberPayoutsService.aggregateByUser(bundle),
      memberPayoutsService.aggregateByMonth(bundle),
      memberPayoutsService.topCampaigns(TOP_CAMPAIGNS_LIMIT, bundle),
      memberPayoutsService.listTopPayoutRows(TOP_PAYOUT_ROWS_LIMIT, bundle),
    ])
      .then(([summary, byUser, byMonth, topCampaigns, topPayoutRows]) => {
        if (cancelled) return;
        setDerived({ summary, byUser, byMonth, topCampaigns, topPayoutRows });
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err : new Error(String(err)));
      });

    return () => {
      cancelled = true;
    };
  }, [bundle]);

  return useMemo(
    () => ({
      bundle,
      summary: derived.summary,
      byUser: derived.byUser,
      byMonth: derived.byMonth,
      topCampaigns: derived.topCampaigns,
      topPayoutRows: derived.topPayoutRows,
      isLoading,
      error,
      refetch,
    }),
    [bundle, derived, isLoading, error, refetch]
  );
}
