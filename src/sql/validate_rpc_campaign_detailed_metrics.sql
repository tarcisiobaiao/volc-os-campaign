-- ============================================
-- VALIDAÇÃO: RPC get_campaign_detailed_metrics
-- Execute APÓS criar a função no Supabase
-- ============================================

-- PASSO 1: Buscar um campaign_id real para usar nos testes
SELECT DISTINCT campaign_id 
FROM daily_campaign_metrics 
WHERE date >= (CURRENT_DATE - INTERVAL '30 days')::DATE
LIMIT 5;

-- PASSO 2: Criar a função (execute rpc_get_campaign_detailed_metrics.sql primeiro)

-- PASSO 3: Validar com um campaign_id específico
-- ⚠️ SUBSTITUA 'CAMPAIGN_ID_AQUI' pelo ID real retornado no PASSO 1

WITH codigo_atual AS (
  -- Simula exatamente o que o código TypeScript faz com os reduces
  SELECT 
    COALESCE(SUM(spend), 0) as total_spend,
    COALESCE(SUM(clicks), 0) as total_clicks,
    COALESCE(SUM(impressions), 0) as total_impressions,
    COALESCE(SUM(conversions), 0) as total_conversions,
    COALESCE(SUM(revenue_converted_revshare), 0) as total_revenue,
    COALESCE(SUM(gam_total_requests), 0) as total_gam_total_requests,
    COALESCE(SUM(gam_impressions), 0) as total_gam_impressions,
    COALESCE(SUM(gam_clicks), 0) as total_gam_clicks,
    COALESCE(SUM(viewable_impressions), 0) as total_viewable_impressions,
    COALESCE(AVG(gam_ecpm), 0) as avg_gam_ecpm,
    COALESCE(AVG(gam_cpc), 0) as avg_gam_cpc,
    COALESCE(AVG(match_rate), 0) as avg_match_rate,
    COALESCE(AVG(fill_rate), 0) as avg_fill_rate,
    COALESCE(AVG(gam_ctr), 0) as avg_gam_ctr
  FROM daily_campaign_metrics
  WHERE campaign_id = 'CAMPAIGN_ID_AQUI'  -- ⚠️ SUBSTITUA
    AND date BETWEEN (CURRENT_DATE - INTERVAL '30 days')::DATE AND CURRENT_DATE::DATE
),
rpc_resultado AS (
  SELECT * FROM get_campaign_detailed_metrics(
    'CAMPAIGN_ID_AQUI',  -- ⚠️ SUBSTITUA
    (CURRENT_DATE - INTERVAL '30 days')::DATE,
    CURRENT_DATE::DATE
  )
)
SELECT 
  -- SPEND
  ROUND(c.total_spend::NUMERIC, 2) as spend_codigo,
  ROUND(r.total_spend::NUMERIC, 2) as spend_rpc,
  -- REVENUE
  ROUND(c.total_revenue::NUMERIC, 2) as revenue_codigo,
  ROUND(r.total_revenue::NUMERIC, 2) as revenue_rpc,
  -- CLICKS
  c.total_clicks as clicks_codigo,
  r.total_clicks as clicks_rpc,
  -- IMPRESSIONS
  c.total_impressions as impressions_codigo,
  r.total_impressions as impressions_rpc,
  -- CONVERSIONS
  c.total_conversions as conversions_codigo,
  r.total_conversions as conversions_rpc,
  -- AVG GAM eCPM
  ROUND(c.avg_gam_ecpm::NUMERIC, 4) as ecpm_codigo,
  ROUND(r.avg_gam_ecpm::NUMERIC, 4) as ecpm_rpc,
  -- STATUS
  CASE 
    WHEN ROUND(ABS(c.total_spend - r.total_spend)::NUMERIC, 2) < 0.01
     AND ROUND(ABS(c.total_revenue - r.total_revenue)::NUMERIC, 2) < 0.01
     AND c.total_clicks = r.total_clicks
     AND c.total_impressions = r.total_impressions
    THEN '✅ OK'
    ELSE '⚠️ VERIFICAR'
  END as status
FROM codigo_atual c
CROSS JOIN rpc_resultado r;

-- ============================================
-- PASSO 4: Validação resumida (mais fácil de ler)
-- ============================================

WITH rpc AS (
  SELECT * FROM get_campaign_detailed_metrics(
    'CAMPAIGN_ID_AQUI',  -- ⚠️ SUBSTITUA
    (CURRENT_DATE - INTERVAL '30 days')::DATE,
    CURRENT_DATE::DATE
  )
)
SELECT 
  'Campanha Teste' as teste,
  ROUND(total_spend::NUMERIC, 2) as spend,
  ROUND(total_revenue::NUMERIC, 2) as revenue,
  ROUND(calculated_profit::NUMERIC, 2) as profit,
  ROUND(calculated_roas::NUMERIC, 2) as roas_percent,
  total_clicks as clicks,
  total_impressions as impressions,
  ROUND(calculated_ctr::NUMERIC, 2) as ctr_percent,
  ROUND(calculated_cpc::NUMERIC, 2) as cpc,
  days_count as dias
FROM rpc;
