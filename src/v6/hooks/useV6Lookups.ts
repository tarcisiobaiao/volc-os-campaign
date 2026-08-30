/**
 * v6 RBAC — useV6Lookups
 *
 * Hooks de leitura para alimentar selects/comboboxes dos
 * formulários: lista de usuários, lista de campanhas.
 *
 * Cada hook é independente para que componentes possam carregar
 * só o que precisam.
 */
import { useCallback, useEffect, useState } from 'react';
import { lookupsService } from '@/v6/services/lookupsService';
import type {
  UserLite,
  CampaignLite,
  CampaignWithContext,
  ProjectLite,
} from '@/v6/types/v6';

export interface UseListResult<T> {
  data: T[];
  isLoading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

function useList<T>(fetcher: () => Promise<T[]>): UseListResult<T> {
  const [data, setData] = useState<T[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await fetcher();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      setData([]);
    } finally {
      setIsLoading(false);
    }
  }, [fetcher]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { data, isLoading, error, refetch };
}

export const useV6Users = (): UseListResult<UserLite> =>
  useList<UserLite>(useCallback(() => lookupsService.listUsers(), []));

export const useV6Campaigns = (): UseListResult<CampaignLite> =>
  useList<CampaignLite>(useCallback(() => lookupsService.listCampaigns(), []));

export const useV6Projects = (): UseListResult<ProjectLite> =>
  useList<ProjectLite>(useCallback(() => lookupsService.listProjects(), []));

/**
 * Versão enriquecida: para cada campanha, devolve a lista de
 * membros atuais (com role) e comissões vigentes. NÃO filtra
 * nada — múltiplos membros por campanha é comportamento
 * esperado e a UI deve apenas mostrar contexto, não bloquear.
 */
export const useV6CampaignsWithContext = (): UseListResult<CampaignWithContext> =>
  useList<CampaignWithContext>(
    useCallback(() => lookupsService.listCampaignsWithContext(), [])
  );
