import { supabase } from '@/lib/supabase';

export interface CampaignFunnelUrl {
  id?: number;
  campaign_id: string;
  url: string;
  Active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface CampaignFunnelUrlInput {
  campaign_id: string;
  url: string;
  Active?: boolean;
}

class CampaignFunnelUrlsService {
  // Buscar URLs do funil de uma campanha
  async getFunnelUrlsByCampaign(campaignId: string): Promise<CampaignFunnelUrl[]> {
    try {
      const { data, error } = await supabase
        .from('campaign_funnel_urls')
        .select('*')
        .eq('campaign_id', campaignId)
        .eq('Active', true)
        .order('created_at', { ascending: true });

      if (error) {
        console.error('Error fetching funnel URLs:', error);
        throw error;
      }

      return data || [];
    } catch (error) {
      console.error('Error in getFunnelUrlsByCampaign:', error);
      throw error;
    }
  }

  // Salvar URLs do funil (substituir todas as existentes)
  async saveFunnelUrls(campaignId: string, urls: CampaignFunnelUrlInput[]): Promise<CampaignFunnelUrl[]> {
    try {
      // Primeiro, marcar todas as URLs existentes como inativas
      await supabase
        .from('campaign_funnel_urls')
        .update({ Active: false, updated_at: new Date().toISOString() })
        .eq('campaign_id', campaignId);

      // Agora inserir as novas URLs (ou reativar se já existir)
      const urlsToInsert = urls.map(url => ({
        campaign_id: campaignId,
        url: url.url, // A limpeza será feita pelo trigger
        Active: true
      }));

      if (urlsToInsert.length > 0) {
        const { data, error } = await supabase
          .from('campaign_funnel_urls')
          .upsert(urlsToInsert, { 
            onConflict: 'campaign_id,url',
            ignoreDuplicates: false 
          })
          .select('*');

        if (error) {
          console.error('Error saving funnel URLs:', error);
          throw error;
        }

        return data || [];
      }

      return [];
    } catch (error) {
      console.error('Error in saveFunnelUrls:', error);
      throw error;
    }
  }

  // Adicionar uma URL individual
  async addFunnelUrl(urlData: CampaignFunnelUrlInput): Promise<CampaignFunnelUrl> {
    try {
      const { data, error } = await supabase
        .from('campaign_funnel_urls')
        .insert({
          campaign_id: urlData.campaign_id,
          url: urlData.url, // Trigger clean_funnel_url() fará a limpeza
          Active: true
        })
        .select('*')
        .single();

      if (error) {
        console.error('Error adding funnel URL:', error);
        throw error;
      }

      return data;
    } catch (error) {
      console.error('Error in addFunnelUrl:', error);
      throw error;
    }
  }

  // Remover uma URL específica
  async removeFunnelUrl(id: number): Promise<void> {
    try {
      const { error } = await supabase
        .from('campaign_funnel_urls')
        .update({ Active: false, updated_at: new Date().toISOString() })
        .eq('id', id);

      if (error) {
        console.error('Error removing funnel URL:', error);
        throw error;
      }
    } catch (error) {
      console.error('Error in removeFunnelUrl:', error);
      throw error;
    }
  }

  // Validar URL (básica, já que o trigger fará a limpeza)
  validateUrl(url: string): { isValid: boolean; error?: string } {
    if (!url || url.trim() === '') {
      return { isValid: false, error: 'URL é obrigatória' };
    }

    // Verificação básica - o trigger clean_funnel_url() cuidará da limpeza
    if (url.trim().length < 3) {
      return { isValid: false, error: 'URL muito curta' };
    }

    return { isValid: true };
  }

  // Buscar todas as URLs de um projeto (para relatórios)
  async getFunnelUrlsByProject(projectId: number): Promise<CampaignFunnelUrl[]> {
    try {
      const { data, error } = await supabase
        .from('campaign_funnel_urls')
        .select(`
          *,
          campaigns!inner(
            campaign_id,
            project_id,
            campaign_name
          )
        `)
        .eq('campaigns.project_id', projectId)
        .eq('Active', true)
        .order('created_at', { ascending: true });

      if (error) {
        console.error('Error fetching project funnel URLs:', error);
        throw error;
      }

      return data || [];
    } catch (error) {
      console.error('Error in getFunnelUrlsByProject:', error);
      throw error;
    }
  }
}

export const campaignFunnelUrlsService = new CampaignFunnelUrlsService();
