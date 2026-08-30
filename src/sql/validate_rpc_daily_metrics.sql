-- ============================================
-- VALIDAÇÃO: RPC get_daily_metrics_aggregated
-- Execute APÓS criar a função no Supabase
-- ============================================

-- PASSO 1: Criar a função (execute rpc_get_daily_metrics_aggregated.sql primeiro)

-- PASSO 2: Validar últimos 7 dias (todos os projetos)
SELECT * FROM get_daily_metrics_aggregated(
  (CURRENT_DATE - INTERVAL '7 days')::DATE,
  CURRENT_DATE::DATE,
  NULL::INT
);

-- PASSO 3: Comparar com método atual (código TypeScript)
WITH codigo_atual AS (
  -- Spend por data (igual ao código)
  SELECT 
    dcm.date as metric_date,
    COALESCE(SUM(dcm.spend), 0) as total_spend,
    COALESCE(SUM(dcm.clicks), 0) as total_clicks,
    COALESCE(SUM(dcm.impressions), 0) as total_impressions
  FROM daily_campaign_metrics dcm
  INNER JOIN campaigns c ON c.campaign_id = dcm.campaign_id
  INNER JOIN projects p ON p.id = c.project_id
  WHERE dcm.date BETWEEN (CURRENT_DATE - INTERVAL '7 days')::DATE AND CURRENT_DATE::DATE
    AND p.visible = true
  GROUP BY dcm.date
),
codigo_revenue AS (
  -- Revenue por data (igual ao código)
  SELECT 
    dpm.date as metric_date,
    COALESCE(SUM(dpm.revenue_converted_revshare), 0) as total_revenue
  FROM daily_project_metrics dpm
  INNER JOIN projects p ON p.id = dpm.project_id
  WHERE dpm.date BETWEEN (CURRENT_DATE - INTERVAL '7 days')::DATE AND CURRENT_DATE::DATE
    AND p.visible = true
  GROUP BY dpm.date
),
codigo_combinado AS (
  SELECT 
    COALESCE(c.metric_date, r.metric_date) as metric_date,
    COALESCE(c.total_spend, 0) as spend_codigo,
    COALESCE(r.total_revenue, 0) as revenue_codigo,
    COALESCE(c.total_clicks, 0) as clicks_codigo,
    COALESCE(c.total_impressions, 0) as impressions_codigo
  FROM codigo_atual c
  FULL OUTER JOIN codigo_revenue r ON c.metric_date = r.metric_date
),
rpc_resultado AS (
  SELECT 
    metric_date,
    investment as spend_rpc,
    revenue as revenue_rpc,
    clicks as clicks_rpc,
    impressions as impressions_rpc
  FROM get_daily_metrics_aggregated(
    (CURRENT_DATE - INTERVAL '7 days')::DATE,
    CURRENT_DATE::DATE,
    NULL::INT
  )
)
SELECT 
  COALESCE(c.metric_date, r.metric_date) as data,
  ROUND(c.spend_codigo::NUMERIC, 2) as spend_codigo,
  ROUND(r.spend_rpc::NUMERIC, 2) as spend_rpc,
  ROUND(c.revenue_codigo::NUMERIC, 2) as revenue_codigo,
  ROUND(r.revenue_rpc::NUMERIC, 2) as revenue_rpc,
  CASE 
    WHEN ROUND(ABS(COALESCE(c.spend_codigo, 0) - COALESCE(r.spend_rpc, 0))::NUMERIC, 2) < 0.01
     AND ROUND(ABS(COALESCE(c.revenue_codigo, 0) - COALESCE(r.revenue_rpc, 0))::NUMERIC, 2) < 0.01
    THEN '✅'
    ELSE '⚠️'
  END as status
FROM codigo_combinado c
FULL OUTER JOIN rpc_resultado r ON c.metric_date = r.metric_date
ORDER BY COALESCE(c.metric_date, r.metric_date) DESC;

-- PASSO 4: Validar totais gerais
WITH rpc AS (
  SELECT 
    SUM(investment) as total_spend,
    SUM(revenue) as total_revenue,
    SUM(clicks) as total_clicks,
    SUM(impressions) as total_impressions,
    COUNT(*) as dias
  FROM get_daily_metrics_aggregated(
    (CURRENT_DATE - INTERVAL '7 days')::DATE,
    CURRENT_DATE::DATE,
    NULL::INT
  )
)
SELECT 
  'Últimos 7 dias' as periodo,
  ROUND(total_spend::NUMERIC, 2) as total_spend,
  ROUND(total_revenue::NUMERIC, 2) as total_revenue,
  total_clicks,
  total_impressions,
  dias
FROM rpc;
