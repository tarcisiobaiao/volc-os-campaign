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

// Mesma limpeza de public.clean_funnel_url (trim, sem http(s)://, sem www., sem / final).
export function limparUrlFunil(url: string): string {
  return url.trim().replace(/^https?:\/\//i, '').replace(/^www\./i, '').replace(/\/+$/, '');
}

function rpcAusente(error: { code?: string }): boolean {
  return error.code === 'PGRST202' || error.code === '42883';
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

  // Salvar URLs do funil (substituir todas as existentes).
  // Uma chamada só (RPC volc_salvar_funil, atômica): URL já ativa e igual não é
  // reenviada, nova é inserida, inativa na lista é reativada e a ativa que saiu
  // da lista é desativada por último. Se o banco recusar qualquer item (ex.: URL
  // histórica fora do domínio reativada), nada muda — a campanha nunca fica com
  // menos URLs ativas por falha parcial.
  async saveFunnelUrls(campaignId: string, urls: CampaignFunnelUrlInput[]): Promise<CampaignFunnelUrl[]> {
    try {
      const lista = urls.map(u => u.url);
      const { data, error } = await supabase.rpc('volc_salvar_funil', {
        p_campaign_id: campaignId,
        p_urls: lista,
      });
      if (error && rpcAusente(error)) {
        return await this.saveFunnelUrlsSemRpc(campaignId, lista);
      }
      if (error) {
        console.error('Error saving funnel URLs:', error);
        throw error;
      }
      return (data as CampaignFunnelUrl[]) || [];
    } catch (error) {
      console.error('Error in saveFunnelUrls:', error);
      throw error;
    }
  }

  // Banco ainda sem a RPC (front publicado antes da migration): só o que mudou,
  // e gravando ANTES de desativar — uma recusa no meio nunca reduz as ativas.
  private async saveFunnelUrlsSemRpc(campaignId: string, lista: string[]): Promise<CampaignFunnelUrl[]> {
    const { data: atuais, error: erroLeitura } = await supabase
      .from('campaign_funnel_urls')
      .select('*')
      .eq('campaign_id', campaignId);
    if (erroLeitura) throw erroLeitura;

    const desejadas = Array.from(new Set(lista.map(limparUrlFunil).filter(u => u !== '')));
    const porUrl = new Map((atuais || []).map((r: CampaignFunnelUrl) => [r.url, r]));

    for (const url of desejadas) {
      const existente = porUrl.get(url);
      if (existente?.Active) continue; // igual e ativa: não reenvia
      const { error } = existente
        ? await supabase.from('campaign_funnel_urls')
            .update({ Active: true, updated_at: new Date().toISOString() })
            .eq('campaign_id', campaignId).eq('url', url)
        : await supabase.from('campaign_funnel_urls')
            .insert({ campaign_id: campaignId, url, Active: true });
      if (error) throw error;
    }

    const sairam = (atuais || []).filter((r: CampaignFunnelUrl) => r.Active && !desejadas.includes(r.url));
    for (const r of sairam) {
      const { error } = await supabase.from('campaign_funnel_urls')
        .update({ Active: false, updated_at: new Date().toISOString() })
        .eq('campaign_id', campaignId).eq('url', r.url);
      if (error) throw error;
    }
    return this.getFunnelUrlsByCampaign(campaignId);
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
