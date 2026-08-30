import { useState, useEffect, useMemo } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { usersService } from '@/services/usersService';

export interface UserFilters {
  allowedProjectIds: number[];
  allowedCampaignIds: string[]; // Google Ads campaign IDs
  isLoading: boolean;
  hasFilters: boolean;
}

// Arrays vazios constantes para evitar re-renders desnecessários
const EMPTY_PROJECT_IDS: number[] = [];
const EMPTY_CAMPAIGN_IDS: string[] = [];

/**
 * Hook para gerenciar os filtros de projetos e campanhas do usuário
 * Operadores têm acesso limitado aos projetos e campanhas configurados pelo admin
 * Admins têm acesso total (sem filtros)
 */
export function useUserFilters(): UserFilters {
  const { userProfile } = useAuth();
  const [allowedProjectIds, setAllowedProjectIds] = useState<number[]>(EMPTY_PROJECT_IDS);
  const [allowedCampaignIds, setAllowedCampaignIds] = useState<string[]>(EMPTY_CAMPAIGN_IDS);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const loadUserFilters = async () => {
      if (!userProfile?.id) {
        setIsLoading(false);
        return;
      }

      // Admins não têm filtros - acesso total
      if (userProfile.role === 'ADMIN') {
        setAllowedProjectIds(EMPTY_PROJECT_IDS);
        setAllowedCampaignIds(EMPTY_CAMPAIGN_IDS);
        setIsLoading(false);
        return;
      }

      // Operadores - carregar projetos e campanhas permitidos
      if (userProfile.role === 'OPERATOR') {
        try {
          const [projectIds, campaignIds] = await Promise.all([
            usersService.getUserProjects(userProfile.id),
            usersService.getUserCampaigns(userProfile.id)
          ]);

          // Só atualiza se houver mudança real nos valores
          setAllowedProjectIds(prev => {
            if (JSON.stringify(prev) === JSON.stringify(projectIds)) {
              return prev;
            }
            return projectIds.length > 0 ? projectIds : EMPTY_PROJECT_IDS;
          });
          
          setAllowedCampaignIds(prev => {
            if (JSON.stringify(prev) === JSON.stringify(campaignIds)) {
              return prev;
            }
            return campaignIds.length > 0 ? campaignIds : EMPTY_CAMPAIGN_IDS;
          });

          console.log('🔐 Filtros do usuário carregados:', {
            role: userProfile.role,
            projectIds,
            campaignIds,
            hasCampaignFilter: campaignIds.length > 0
          });
        } catch (error) {
          console.error('Erro ao carregar filtros do usuário:', error);
          setAllowedProjectIds(EMPTY_PROJECT_IDS);
          setAllowedCampaignIds(EMPTY_CAMPAIGN_IDS);
        }
      }

      setIsLoading(false);
    };

    loadUserFilters();
  }, [userProfile?.id, userProfile?.role]);

  // Usar useMemo para garantir estabilidade da flag hasFilters
  const hasFilters = useMemo(() => {
    return userProfile?.role === 'OPERATOR' && (allowedProjectIds.length > 0 || allowedCampaignIds.length > 0);
  }, [userProfile?.role, allowedProjectIds.length, allowedCampaignIds.length]);

  return {
    allowedProjectIds,
    allowedCampaignIds,
    isLoading,
    hasFilters
  };
}
