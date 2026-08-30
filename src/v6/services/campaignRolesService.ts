/**
 * v6 RBAC — campaignRolesService
 *
 * Service singleton read-only para a tabela `public.campaign_roles`.
 * Espelha o padrão dos services legados (`usersService`, etc.):
 * class singleton + supabase direto + tratamento de erro lança exception.
 */
import { supabase } from '@/lib/supabase';
import type { CampaignRole } from '@/v6/types/v6';

class CampaignRolesService {
  /** Lista todos os roles do catálogo, ordenados por id. */
  async listAll(): Promise<CampaignRole[]> {
    const { data, error } = await supabase
      .from('campaign_roles')
      .select('id, code, label, description, created_at')
      .order('id', { ascending: true });

    if (error) throw error;
    return (data || []) as CampaignRole[];
  }
}

export const campaignRolesService = new CampaignRolesService();
