// Teste rápido da conexão com Supabase
import { supabase } from './lib/supabase.js';

async function testConnection() {
  try {
    console.log('Testando conexão com Supabase...');
    
    // Teste 1: Buscar projetos
    const { data: projects, error: projectError } = await supabase
      .from('projects')
      .select('*')
      .limit(3);
    
    if (projectError) {
      console.error('Erro ao buscar projetos:', projectError);
    } else {
      console.log('✅ Projetos encontrados:', projects.length);
      console.log('Primeiro projeto:', projects[0]);
    }
    
    // Teste 2: Buscar métricas
    const { data: metrics, error: metricsError } = await supabase
      .from('daily_project_metrics')
      .select('*')
      .order('date', { ascending: false })
      .limit(5);
    
    if (metricsError) {
      console.error('Erro ao buscar métricas:', metricsError);
    } else {
      console.log('✅ Métricas encontradas:', metrics.length);
      console.log('Primeira métrica:', metrics[0]);
    }
    
  } catch (error) {
    console.error('Erro geral:', error);
  }
}

testConnection();