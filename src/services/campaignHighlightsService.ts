import { supabase } from '@/lib/supabase';

export interface CampaignHighlight {
  campaign_id: number;
  campaign_name: string;
  status: 'em_alta' | 'em_baixa' | 'estagnada' | 'alerta_tecnico';
  avg_spend: number;
  roas_inicio: number;
  roas_fim: number;
  variacao_roas: string;
  motivo: string;
}

export interface CampaignHighlightsGrouped {
  alertas_tecnicos: CampaignHighlight[];
  em_alta: CampaignHighlight[];
  estagnadas: CampaignHighlight[];
  em_baixa: CampaignHighlight[];
}

class CampaignHighlightsService {
  private cache: CampaignHighlight[] | null = null;
  private cacheTimestamp: number = 0;
  private readonly CACHE_TTL = 5 * 60 * 1000; // 5 minutos

  /**
   * Busca campanhas destacadas usando a RPC function que já aplica a rotação de 5 dias
   * e registra automaticamente as campanhas selecionadas
   */
  async getCampaignHighlights(): Promise<CampaignHighlight[]> {
    try {
      // Verificar cache
      const now = Date.now();
      if (this.cache && (now - this.cacheTimestamp) < this.CACHE_TTL) {
        console.log('📦 Using cached campaign highlights');
        return this.cache;
      }

      console.log('🔄 Fetching campaign highlights from RPC...');
      
      // Chamar RPC function que executa o SQL modificado e registra automaticamente
      const { data, error } = await supabase.rpc('get_rotated_campaign_highlights');

      if (error) {
        console.error('❌ Error calling get_rotated_campaign_highlights RPC:', error);
        console.error('❌ Error details:', JSON.stringify(error, null, 2));
        
        // Verificar se é erro de função não encontrada
        if (error.message?.includes('function') || error.code === '42883') {
          throw new Error('Função get_rotated_campaign_highlights não encontrada. Execute o SQL get_rotated_campaign_highlights_v2.sql no Supabase.');
        }
        
        throw error;
      }

      console.log('✅ RPC call successful. Results:', data?.length || 0, 'campaigns');

      if (!data || data.length === 0) {
        console.warn('⚠️ No campaign highlights returned from RPC');
        console.warn('💡 Isso pode significar:');
        console.warn('   1. Não há campanhas que atendem os critérios');
        console.warn('   2. Todas as campanhas estão em cooldown (últimos 5 dias)');
        console.warn('   3. Não há dados suficientes em daily_campaign_metrics');
        return [];
      }

      // Converter para o formato esperado
      // campaign_id_out vem como TEXT do Postgres
      const highlights: CampaignHighlight[] = data.map((item: any) => ({
        campaign_id: Number(item.campaign_id_out),
        campaign_name: item.campaign_name_out || 'Sem nome',
        status: item.status_out as CampaignHighlight['status'],
        avg_spend: Number(item.avg_spend_out) || 0,
        roas_inicio: Number(item.roas_inicio_out) || 0,
        roas_fim: Number(item.roas_fim_out) || 0,
        variacao_roas: item.variacao_roas_out || '0%',
        motivo: item.motivo_out || ''
      }));

      console.log('📊 Highlights grouped:', {
        alertas_tecnicos: highlights.filter(h => h.status === 'alerta_tecnico').length,
        em_alta: highlights.filter(h => h.status === 'em_alta').length,
        estagnadas: highlights.filter(h => h.status === 'estagnada').length,
        em_baixa: highlights.filter(h => h.status === 'em_baixa').length
      });

      // Atualizar cache
      this.cache = highlights;
      this.cacheTimestamp = now;

      return highlights;
    } catch (error) {
      console.error('❌ Error fetching campaign highlights:', error);
      throw error;
    }
  }

  /**
   * Retorna campanhas agrupadas por categoria
   */
  async getCampaignHighlightsGrouped(): Promise<CampaignHighlightsGrouped> {
    const highlights = await this.getCampaignHighlights();

    return {
      alertas_tecnicos: highlights.filter(h => h.status === 'alerta_tecnico'),
      em_alta: highlights.filter(h => h.status === 'em_alta'),
      estagnadas: highlights.filter(h => h.status === 'estagnada'),
      em_baixa: highlights.filter(h => h.status === 'em_baixa')
    };
  }

  /**
   * Limpa o cache (útil após atualizações de dados)
   */
  clearCache(): void {
    this.cache = null;
    this.cacheTimestamp = 0;
  }

  /**
   * Busca informações adicionais de uma campanha (nome, projeto, etc.)
   */
  async getCampaignDetails(campaignId: number): Promise<{
    campaign_name: string;
    project_name: string;
    project_domain: string;
  } | null> {
    try {
      const { data, error } = await supabase
        .from('campaigns')
        .select(`
          campaign_name,
          projects:project_id (
            name,
            main_url
          )
        `)
        .eq('id', campaignId)
        .single();

      if (error) {
        console.error('❌ Error fetching campaign details:', error);
        return null;
      }

      return {
        campaign_name: data.campaign_name || 'Campanha sem nome',
        project_name: (data.projects as any)?.name || 'Projeto sem nome',
        project_domain: (data.projects as any)?.main_url || 'N/A'
      };
    } catch (error) {
      console.error('❌ Error in getCampaignDetails:', error);
      return null;
    }
  }
}

// Singleton instance
export const campaignHighlightsService = new CampaignHighlightsService();

