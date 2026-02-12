// Script de debug para verificar dados de revenue
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = 'https://your-project.supabase.co' // Substitua pela sua URL
const supabaseKey = 'your-anon-key' // Substitua pela sua chave

const supabase = createClient(supabaseUrl, supabaseKey)

async function debugRevenueData() {
  console.log('🔍 Verificando dados de revenue...')
  
  try {
    // 1. Verificar se há dados na tabela daily_campaign_metrics
    const { data: campaignMetrics, error: campaignError } = await supabase
      .from('daily_campaign_metrics')
      .select('*')
      .limit(5)
      .order('date', { ascending: false })
    
    if (campaignError) {
      console.error('❌ Erro ao buscar daily_campaign_metrics:', campaignError)
      return
    }
    
    console.log('📊 Dados de daily_campaign_metrics (últimos 5 registros):')
    console.log(JSON.stringify(campaignMetrics, null, 2))
    
    // 2. Verificar especificamente as colunas de revenue
    const { data: revenueData, error: revenueError } = await supabase
      .from('daily_campaign_metrics')
      .select('date, spend, revenue, revenue_converted, revenue_converted_revshare, campaign_id')
      .not('revenue_converted', 'is', null)
      .limit(10)
      .order('date', { ascending: false })
    
    if (revenueError) {
      console.error('❌ Erro ao buscar dados de revenue:', revenueError)
      return
    }
    
    console.log('\n💰 Dados de revenue (últimos 10 registros com revenue_converted):')
    console.log(JSON.stringify(revenueData, null, 2))
    
    // 3. Verificar se a coluna revenue_converted_revshare existe e tem valores
    const { data: revshareData, error: revshareError } = await supabase
      .from('daily_campaign_metrics')
      .select('date, revenue_converted, revenue_converted_revshare, campaign_id')
      .not('revenue_converted_revshare', 'is', null)
      .limit(10)
      .order('date', { ascending: false })
    
    if (revshareError) {
      console.error('❌ Erro ao buscar dados de revenue_converted_revshare:', revshareError)
      return
    }
    
    console.log('\n🎯 Dados de revenue_converted_revshare (últimos 10 registros):')
    console.log(JSON.stringify(revshareData, null, 2))
    
    // 4. Verificar projetos e seus revshare
    const { data: projects, error: projectsError } = await supabase
      .from('projects')
      .select('id, project_name, revshare')
      .limit(5)
    
    if (projectsError) {
      console.error('❌ Erro ao buscar projetos:', projectsError)
      return
    }
    
    console.log('\n🏢 Projetos e seus revshare:')
    console.log(JSON.stringify(projects, null, 2))
    
    // 5. Verificar campanhas e seus projetos
    const { data: campaigns, error: campaignsError } = await supabase
      .from('campaigns')
      .select('id, campaign_id, project_id, campaign_name')
      .limit(5)
    
    if (campaignsError) {
      console.error('❌ Erro ao buscar campanhas:', campaignsError)
      return
    }
    
    console.log('\n📢 Campanhas e seus projetos:')
    console.log(JSON.stringify(campaigns, null, 2))
    
    // 6. Verificar se há dados para hoje
    const today = new Date().toISOString().split('T')[0]
    const { data: todayData, error: todayError } = await supabase
      .from('daily_campaign_metrics')
      .select('*')
      .eq('date', today)
      .limit(5)
    
    if (todayError) {
      console.error('❌ Erro ao buscar dados de hoje:', todayError)
      return
    }
    
    console.log(`\n📅 Dados para hoje (${today}):`)
    console.log(JSON.stringify(todayData, null, 2))
    
    // 7. Contar registros totais
    const { count: totalCount, error: countError } = await supabase
      .from('daily_campaign_metrics')
      .select('*', { count: 'exact', head: true })
    
    if (countError) {
      console.error('❌ Erro ao contar registros:', countError)
      return
    }
    
    console.log(`\n📊 Total de registros na tabela daily_campaign_metrics: ${totalCount}`)
    
  } catch (error) {
    console.error('❌ Erro geral:', error)
  }
}

// Executar o debug
debugRevenueData()

