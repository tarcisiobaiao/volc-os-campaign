/**
 * v6 RBAC — useCampaignCommissions
 *
 * Carrega comissões versionadas enriquecidas (com user e campaign).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { campaignCommissionsService } from '@/v6/services/campaignCommissionsService';
import type { CampaignCommissionEnriched } from '@/v6/types/v6';

export interface UseCampaignCommissionsResult {
  data: CampaignCommissionEnriched[];
  active: CampaignCommissionEnriched[];
  isLoading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

export function useCampaignCommissions(): UseCampaignCommissionsResult {
  const [data, setData] = useState<CampaignCommissionEnriched[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await campaignCommissionsService.listWithUserData();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      setData([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  const active = useMemo(() => data.filter((c) => c.is_active), [data]);

  return { data, active, isLoading, error, refetch };
}
