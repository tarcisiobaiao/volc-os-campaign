/**
 * v6 RBAC — useCampaignMembers
 *
 * Carrega members enriquecidos (com user, role e campaign já mesclados)
 * + contagem por role. Faz duas chamadas paralelas via Promise.all.
 */
import { useCallback, useEffect, useState } from 'react';
import { campaignMembersService } from '@/v6/services/campaignMembersService';
import type { CampaignMemberEnriched, MembersCountByRole } from '@/v6/types/v6';

export interface UseCampaignMembersResult {
  members: CampaignMemberEnriched[];
  countByRole: MembersCountByRole[];
  isLoading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

export function useCampaignMembers(): UseCampaignMembersResult {
  const [members, setMembers] = useState<CampaignMemberEnriched[]>([]);
  const [countByRole, setCountByRole] = useState<MembersCountByRole[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [enriched, counts] = await Promise.all([
        campaignMembersService.listWithUserData(),
        campaignMembersService.countByRole(),
      ]);
      setMembers(enriched);
      setCountByRole(counts);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      setMembers([]);
      setCountByRole([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { members, countByRole, isLoading, error, refetch };
}
