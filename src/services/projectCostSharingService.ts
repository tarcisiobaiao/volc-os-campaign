import { supabase } from '@/lib/supabase';

class ProjectCostSharingService {
  /**
   * Atualiza se um projeto participa da divisão de custos
   */
  async updateProjectCostsDivision(projectId: string, costsDivision: boolean): Promise<void> {
    try {
      console.log(`🔄 Atualizando projeto ${projectId} para costs_division: ${costsDivision}`);
      
      const { error } = await supabase
        .from('projects')
        .update({ 
          costs_division: costsDivision,
          updated_at: new Date().toISOString()
        })
        .eq('id', projectId);

      if (error) {
        console.error('Erro ao atualizar divisão de custos do projeto:', error);
        
        // Se a coluna não existe, criar ela automaticamente
        if ((error as { message?: string; code?: string }).message?.includes('costs_division') || (error as { code?: string }).code === '42703') {
          console.log('🔧 Criando coluna costs_division...');
          
          // Executar SQL para criar a coluna
          const { error: sqlError } = await supabase.from('projects').select('id').limit(1);
          if (sqlError) throw sqlError;
          
          // Como não temos RPC disponível, vamos orientar o usuário
          throw new Error(`Para usar esta funcionalidade, execute no Supabase SQL Editor:
ALTER TABLE projects ADD COLUMN costs_division BOOLEAN DEFAULT false;`);
        }
        
        throw new Error((error as { message?: string }).message || 'Unknown error');
      }

      console.log(`✅ Projeto ${projectId} ${costsDivision ? 'incluído' : 'removido'} da divisão de custos`);
    } catch (error: unknown) {
      console.error('Erro ao atualizar projeto:', error);
      throw error;
    }
  }

  /**
   * Define todos os projetos ativos para participarem da divisão
   */
  async setAllActiveProjectsForCostsDivision(): Promise<void> {
    try {
      console.log('🔄 Definindo todos os projetos ativos para divisão de custos...');
      
      const { error } = await supabase
        .from('projects')
        .update({ 
          costs_division: true,
          updated_at: new Date().toISOString()
        })
        .eq('status', 'active');

      if (error) {
        console.error('Erro ao definir todos projetos para divisão:', error);
        
        if ((error as { message?: string; code?: string }).message?.includes('costs_division') || (error as { code?: string }).code === '42703') {
          throw new Error(`Para usar esta funcionalidade, execute no Supabase SQL Editor:
ALTER TABLE projects ADD COLUMN costs_division BOOLEAN DEFAULT false;`);
        }
        
        throw new Error((error as { message?: string }).message || 'Unknown error');
      }

      console.log('✅ Todos os projetos ativos definidos para divisão de custos');
    } catch (error: unknown) {
      console.error('Erro ao definir todos projetos:', error);
      throw error;
    }
  }

  /**
   * Remove todos os projetos da divisão de custos
   */
  async removeAllProjectsFromCostsDivision(): Promise<void> {
    try {
      console.log('🔄 Removendo todos os projetos da divisão de custos...');
      
      const { error } = await supabase
        .from('projects')
        .update({ 
          costs_division: false,
          updated_at: new Date().toISOString()
        })
        .eq('status', 'active');

      if (error) {
        console.error('Erro ao remover todos projetos da divisão:', error);
        
        if ((error as { message?: string; code?: string }).message?.includes('costs_division') || (error as { code?: string }).code === '42703') {
          throw new Error(`Para usar esta funcionalidade, execute no Supabase SQL Editor:
ALTER TABLE projects ADD COLUMN costs_division BOOLEAN DEFAULT false;`);
        }
        
        throw new Error((error as { message?: string }).message || 'Unknown error');
      }

      console.log('✅ Todos os projetos removidos da divisão de custos');
    } catch (error: unknown) {
      console.error('Erro ao remover todos projetos:', error);
      throw error;
    }
  }

  /**
   * Busca todos os projetos ativos com sua configuração de divisão de custos
   */
  async getActiveProjectsWithCostsDivision(): Promise<any[]> {
    try {
      const { data, error } = await supabase
        .from('projects')
        .select('id, project_name, domain, status, costs_division')
        .eq('status', 'active')
        .order('project_name');

      if (error) {
        console.error('Erro ao buscar projetos:', error);
        throw new Error((error as { message?: string }).message || 'Unknown error');
      }

      return data || [];
    } catch (error: unknown) {
      console.error('Erro ao buscar projetos:', error);
      throw error;
    }
  }
}

export const projectCostSharingService = new ProjectCostSharingService();