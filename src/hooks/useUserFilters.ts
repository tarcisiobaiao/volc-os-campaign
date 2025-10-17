import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { usersService } from '@/services/usersService';

export interface UserFilters {
  allowedProjectIds: number[];
  allowedCampaignIds: string[]; // Google Ads campaign IDs
  isLoading: boolean;
  hasFilters: boolean;
}

/**
 * Hook para gerenciar os filtros de projetos e campanhas do usuário
 * Operadores têm acesso limitado aos projetos e campanhas configurados pelo admin
 * Admins têm acesso total (sem filtros)
 */
export function useUserFilters(): UserFilters {
  const { userProfile } = useAuth();
  const [allowedProjectIds, setAllowedProjectIds] = useState<number[]>([]);
  const [allowedCampaignIds, setAllowedCampaignIds] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const loadUserFilters = async () => {
      if (!userProfile?.id) {
        setIsLoading(false);
        return;
      }

      // Admins não têm filtros - acesso total
      if (userProfile.role === 'ADMIN') {
        setAllowedProjectIds([]);
        setAllowedCampaignIds([]);
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

          setAllowedProjectIds(projectIds);
          setAllowedCampaignIds(campaignIds);

          console.log('🔐 Filtros do usuário carregados:', {
            role: userProfile.role,
            projectIds,
            campaignIds,
            hasCampaignFilter: campaignIds.length > 0
          });
        } catch (error) {
          console.error('Erro ao carregar filtros do usuário:', error);
        }
      }

      setIsLoading(false);
    };

    loadUserFilters();
  }, [userProfile]);

  return {
    allowedProjectIds,
    allowedCampaignIds,
    isLoading,
    hasFilters: userProfile?.role === 'OPERATOR' && (allowedProjectIds.length > 0 || allowedCampaignIds.length > 0)
  };
}
