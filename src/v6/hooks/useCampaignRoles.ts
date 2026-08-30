/**
 * v6 RBAC — useCampaignRoles
 *
 * Carrega o catálogo de roles funcionais e aplica:
 *
 * 1. **Override de labels** — o banco continua com seus valores
 *    originais ('Dono', 'Operador', 'Revisor', 'Espectador'), mas
 *    a UI mostra rótulos mais apropriados (ex: 'Espectador' →
 *    'Visualizador'). Isso evita mexer em `campaign_roles` no banco.
 *
 * 2. **Filtro `selectable`** — devolve apenas os roles aceitos
 *    como opções em formulários novos. Por decisão de produto,
 *    o sistema hoje aceita apenas `OPERATOR` e `VIEWER` nos
 *    selects. Roles legados (`OWNER`, `REVIEWER`) continuam no
 *    banco para que memberships pré-existentes não quebrem, mas
 *    não aparecem mais nos dropdowns de criação/edição.
 *
 * Regra de consumo:
 *   - Para **exibir** um role (ex: badge numa tabela), use `data`.
 *   - Para **selecionar** um role (ex: formulário), use `selectable`.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { campaignRolesService } from '@/v6/services/campaignRolesService';
import type { CampaignRole } from '@/v6/types/v6';

/** Codes aceitos em dropdowns de criação/edição de memberships. */
export const SELECTABLE_ROLE_CODES = new Set<string>(['OPERATOR', 'VIEWER']);

/** Overrides de label aplicados no front sem mexer no banco. */
const ROLE_LABEL_OVERRIDES: Record<string, string> = {
  VIEWER: 'Visualizador',
};

/**
 * Aplica o override de label (se houver) a um role, retornando
 * um novo objeto (não muta o original). Exportado para que
 * outros services (ex: `campaignMembersService`) possam aplicar
 * a mesma normalização ao enriquecer membros com dados de role.
 */
export function normalizeRole<T extends { code: string; label: string }>(
  role: T
): T {
  const override = ROLE_LABEL_OVERRIDES[role.code];
  if (!override || override === role.label) return role;
  return { ...role, label: override };
}

export interface UseCampaignRolesResult {
  /** Todos os roles do catálogo, com labels normalizados. */
  data: CampaignRole[];
  /** Só os roles aceitos para novos memberships (OPERATOR + VIEWER). */
  selectable: CampaignRole[];
  isLoading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

export function useCampaignRoles(): UseCampaignRolesResult {
  const [rawData, setRawData] = useState<CampaignRole[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await campaignRolesService.listAll();
      setRawData(result);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      setRawData([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  const data = useMemo(() => rawData.map(normalizeRole), [rawData]);
  const selectable = useMemo(
    () => data.filter((r) => SELECTABLE_ROLE_CODES.has(r.code)),
    [data]
  );

  return { data, selectable, isLoading, error, refetch };
}
