-- 🚀 PRODUCTION MAINTENANCE KIT
-- Use este arquivo para operações de manutenção e monitoramento

-- =====================================
-- 1. SMOKE CHECKS DIÁRIOS
-- =====================================

-- DAGM duplicadas (não deve retornar linhas)
SELECT 'DAGM_DUPLICATES' as check_name, ad_group_id, date, COUNT(*) as duplicate_count 
FROM public.daily_ad_group_metrics
GROUP BY ad_group_id, date 
HAVING COUNT(*) > 1;

-- DCM duplicadas (não deve retornar linhas) 
SELECT 'DCM_DUPLICATES' as check_name, campaign_id, date, COUNT(*) as duplicate_count
FROM public.daily_campaign_metrics  
GROUP BY campaign_id, date
HAVING COUNT(*) > 1;

-- URL Performance duplicadas (não deve retornar linhas)
SELECT 'URL_DUPLICATES' as check_name, project_id, date, url, COUNT(*) as duplicate_count
FROM public.url_daily_performance
GROUP BY project_id, date, url
HAVING COUNT(*) > 1;

-- =====================================
-- 2. LAG DE INGESTÃO
-- =====================================

-- Últimas datas por fonte (monitorar atraso)
SELECT 
  'dagm' as src, 
  MAX(date) as last_date,
  (CURRENT_DATE - MAX(date)) as days_behind,
  COUNT(*) as total_records
FROM public.daily_ad_group_metrics

UNION ALL

SELECT 
  'dcm', 
  MAX(date),
  (CURRENT_DATE - MAX(date)),
  COUNT(*)
FROM public.daily_campaign_metrics

UNION ALL

SELECT 
  'url', 
  MAX(date),
  (CURRENT_DATE - MAX(date)), 
  COUNT(*)
FROM public.url_daily_performance

UNION ALL

SELECT
  'projects',
  MAX(created_at::date),
  (CURRENT_DATE - MAX(created_at::date)),
  COUNT(*)
FROM public.projects;

-- =====================================
-- 3. MÉTRICAS DE SAÚDE
-- =====================================

-- Volume de dados por dia (últimos 7 dias)
SELECT 
  date,
  COUNT(*) as dagm_records,
  SUM(spend) as total_spend,
  SUM(impressions) as total_impressions
FROM public.daily_ad_group_metrics 
WHERE date >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY date
ORDER BY date DESC;

-- Campanhas ativas por projeto
SELECT 
  p.project_name,
  COUNT(c.id) as total_campaigns,
  COUNT(CASE WHEN c.status = 'Active' THEN 1 END) as active_campaigns,
  MAX(c.updated_at) as last_campaign_update
FROM public.projects p
LEFT JOIN public.campaigns c ON p.id = c.project_id
GROUP BY p.id, p.project_name
ORDER BY active_campaigns DESC;

-- =====================================
-- 4. PERFORMANCE QUERIES
-- =====================================

-- Top campanhas por spend (últimos 30 dias)
SELECT 
  c.campaign_name,
  p.project_name,
  SUM(dcm.spend) as total_spend,
  SUM(dcm.clicks) as total_clicks,
  SUM(dcm.impressions) as total_impressions,
  CASE 
    WHEN SUM(dcm.impressions) > 0 
    THEN ROUND((SUM(dcm.clicks)::numeric / SUM(dcm.impressions)) * 100, 2) 
    ELSE 0 
  END as ctr_percent
FROM public.daily_campaign_metrics dcm
JOIN public.campaigns c ON c.id = dcm.campaign_id  
JOIN public.projects p ON p.id = c.project_id
WHERE dcm.date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY c.id, c.campaign_name, p.project_name
ORDER BY total_spend DESC
LIMIT 20;

-- URLs com melhor performance (últimos 7 dias)
SELECT 
  p.project_name,
  udp.url,
  SUM(udp.estimated_earnings_usd) as total_revenue,
  SUM(udp.page_views) as total_page_views,
  ROUND(AVG(udp.viewability), 4) as avg_viewability,
  ROUND(AVG(udp.ecpm), 2) as avg_ecpm
FROM public.url_daily_performance udp
JOIN public.projects p ON p.id = udp.project_id
WHERE udp.date >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY p.project_name, udp.url
HAVING SUM(udp.page_views) > 1000  -- Filtrar URLs com volume significativo
ORDER BY total_revenue DESC
LIMIT 15;

-- =====================================
-- 5. MANUTENÇÃO SEMANAL
-- =====================================

-- VACUUM e ANALYZE nas tabelas principais
-- Execute via cron job semanal:

/*
VACUUM (ANALYZE) public.daily_ad_group_metrics;
VACUUM (ANALYZE) public.daily_campaign_metrics;  
VACUUM (ANALYZE) public.url_daily_performance;
VACUUM (ANALYZE) public.campaigns;
VACUUM (ANALYZE) public.ad_groups;
*/

-- Verificar tamanho das tabelas
SELECT 
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
  pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) as table_size,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) as index_size
FROM pg_tables 
WHERE schemaname = 'public'
  AND tablename IN ('daily_ad_group_metrics', 'daily_campaign_metrics', 'url_daily_performance', 'campaigns', 'ad_groups')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- =====================================
-- 6. ALERTAS PARA MONITORAMENTO
-- =====================================

-- Campanhas com spend muito baixo (possível problema)
SELECT 
  c.campaign_name,
  p.project_name,
  AVG(dcm.spend) as avg_daily_spend,
  COUNT(*) as days_with_data
FROM public.daily_campaign_metrics dcm
JOIN public.campaigns c ON c.id = dcm.campaign_id
JOIN public.projects p ON p.id = c.project_id  
WHERE dcm.date >= CURRENT_DATE - INTERVAL '7 days'
  AND c.status = 'Active'
GROUP BY c.id, c.campaign_name, p.project_name
HAVING AVG(dcm.spend) < 1.0  -- Menos de $1/dia
ORDER BY avg_daily_spend ASC;

-- Projetos sem dados recentes (possível problema de sincronização)
SELECT 
  p.project_name,
  p.last_google_ads_sync,
  p.last_gam_sync,
  COALESCE(MAX(dcm.date), '1900-01-01'::date) as last_campaign_data,
  COALESCE(MAX(udp.date), '1900-01-01'::date) as last_url_data
FROM public.projects p
LEFT JOIN public.campaigns c ON c.project_id = p.id
LEFT JOIN public.daily_campaign_metrics dcm ON dcm.campaign_id = c.id
LEFT JOIN public.url_daily_performance udp ON udp.project_id = p.id
WHERE p.status = 'Active'
GROUP BY p.id, p.project_name, p.last_google_ads_sync, p.last_gam_sync
HAVING 
  COALESCE(MAX(dcm.date), '1900-01-01'::date) < CURRENT_DATE - INTERVAL '3 days'
  OR COALESCE(MAX(udp.date), '1900-01-01'::date) < CURRENT_DATE - INTERVAL '3 days'
ORDER BY p.project_name;

-- =====================================
-- 7. CLEANUP QUERIES (USE COM CUIDADO!)
-- =====================================

-- Remover dados muito antigos (descomente apenas se necessário)
-- DELETE FROM public.daily_ad_group_metrics WHERE date < CURRENT_DATE - INTERVAL '2 years';
-- DELETE FROM public.daily_campaign_metrics WHERE date < CURRENT_DATE - INTERVAL '2 years';  
-- DELETE FROM public.url_daily_performance WHERE date < CURRENT_DATE - INTERVAL '1 year';

-- =====================================
-- 8. TROUBLESHOOTING
-- =====================================

-- Verificar constraints violadas
SELECT conname, conrelid::regclass, pg_get_constraintdef(oid) 
FROM pg_constraint 
WHERE contype IN ('c', 'u') 
  AND connamespace = 'public'::regnamespace
  AND conrelid::regclass::text IN ('daily_ad_group_metrics', 'daily_campaign_metrics', 'campaign_funnel_urls');

-- Verificar triggers ativos  
SELECT tgname, tgrelid::regclass, tgenabled 
FROM pg_trigger 
WHERE tgname LIKE 'trg_%updated_at'
  AND tgrelid::regclass::text IN ('campaigns', 'ad_groups', 'daily_campaign_metrics');

-- =====================================
-- MODO DE USO:
-- =====================================

/*
1. DAILY: Execute seção 1 (Smoke Checks) via cron
2. DAILY: Execute seção 2 (Lag de Ingestão) para monitoramento  
3. WEEKLY: Execute seção 5 (VACUUM/ANALYZE)
4. MONTHLY: Execute seção 4 (Performance) para insights
5. ALERTS: Configure seção 6 em sistema de alertas
*/