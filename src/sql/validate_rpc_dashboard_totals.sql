-- ============================================
-- VALIDAÇÃO: RPC get_dashboard_totals
-- Execute APÓS criar a função no Supabase
-- ============================================

-- PASSO 1: Criar a função (execute rpc_get_dashboard_totals.sql primeiro)

-- PASSO 2: Validar totais gerais (últimos 30 dias)
WITH codigo_atual AS (
  -- SPEND: igual ao código TypeScript
  SELECT 
    (
      SELECT COALESCE(SUM(dcm.spend), 0)
      FROM daily_campaign_metrics dcm
      INNER JOIN campaigns c ON c.campaign_id = dcm.campaign_id
      INNER JOIN projects p ON p.id = c.project_id
      WHERE dcm.date BETWEEN (CURRENT_DATE - INTERVAL '30 days')::DATE AND CURRENT_DATE::DATE
        AND p.visible = true
    ) as total_spend_codigo,
    -- REVENUE: igual ao código TypeScript
    (
      SELECT COALESCE(SUM(dpm.revenue_converted_revshare), 0)
      FROM daily_project_metrics dpm
      INNER JOIN projects p ON p.id = dpm.project_id
      WHERE dpm.date BETWEEN (CURRENT_DATE - INTERVAL '30 days')::DATE AND CURRENT_DATE::DATE
        AND p.visible = true
    ) as total_revenue_codigo,
    -- CAMPAIGNS: igual ao código TypeScript
    (
      SELECT COUNT(DISTINCT CASE WHEN c.status = 'Active' THEN c.id END)
      FROM campaigns c
      INNER JOIN projects p ON p.id = c.project_id
      WHERE p.visible = true
    ) as active_campaigns_codigo,
    (
      SELECT COUNT(DISTINCT CASE WHEN c.status = 'Paused' THEN c.id END)
      FROM campaigns c
      INNER JOIN projects p ON p.id = c.project_id
      WHERE p.visible = true
    ) as paused_campaigns_codigo
),
rpc_resultado AS (
  SELECT * FROM get_dashboard_totals(
    (CURRENT_DATE - INTERVAL '30 days')::DATE,
    CURRENT_DATE::DATE,
    NULL::INT
  )
)
SELECT 
  -- SPEND
  ROUND(c.total_spend_codigo::NUMERIC, 2) as spend_codigo,
  ROUND(r.total_spend::NUMERIC, 2) as spend_rpc,
  ROUND(ABS(c.total_spend_codigo - r.total_spend)::NUMERIC, 2) as diff_spend,
  -- REVENUE
  ROUND(c.total_revenue_codigo::NUMERIC, 2) as revenue_codigo,
  ROUND(r.total_revenue::NUMERIC, 2) as revenue_rpc,
  ROUND(ABS(c.total_revenue_codigo - r.total_revenue)::NUMERIC, 2) as diff_revenue,
  -- CAMPAIGNS
  c.active_campaigns_codigo,
  r.active_campaigns as active_campaigns_rpc,
  c.paused_campaigns_codigo,
  r.paused_campaigns as paused_campaigns_rpc,
  -- STATUS
  CASE 
    WHEN ROUND(ABS(c.total_spend_codigo - r.total_spend)::NUMERIC, 2) < 0.01
     AND ROUND(ABS(c.total_revenue_codigo - r.total_revenue)::NUMERIC, 2) < 0.01
     AND c.active_campaigns_codigo = r.active_campaigns
     AND c.paused_campaigns_codigo = r.paused_campaigns
    THEN '✅ TUDO OK'
    ELSE '⚠️ VERIFICAR'
  END as status
FROM codigo_atual c
CROSS JOIN rpc_resultado r;

-- ============================================
-- PASSO 3: Validar com projeto específico
-- ============================================
-- Substitua 11 pelo ID de um projeto real

WITH codigo_atual AS (
  SELECT 
    (
      SELECT COALESCE(SUM(dcm.spend), 0)
      FROM daily_campaign_metrics dcm
      INNER JOIN campaigns c ON c.campaign_id = dcm.campaign_id
      WHERE dcm.date BETWEEN (CURRENT_DATE - INTERVAL '30 days')::DATE AND CURRENT_DATE::DATE
        AND c.project_id = 11  -- ⚠️ SUBSTITUA
    ) as total_spend_codigo,
    (
      SELECT COALESCE(SUM(dpm.revenue_converted_revshare), 0)
      FROM daily_project_metrics dpm
      WHERE dpm.date BETWEEN (CURRENT_DATE - INTERVAL '30 days')::DATE AND CURRENT_DATE::DATE
        AND dpm.project_id = 11  -- ⚠️ SUBSTITUA
    ) as total_revenue_codigo
),
rpc_resultado AS (
  SELECT * FROM get_dashboard_totals(
    (CURRENT_DATE - INTERVAL '30 days')::DATE,
    CURRENT_DATE::DATE,
    11  -- ⚠️ SUBSTITUA
  )
)
SELECT 
  'Projeto 11' as teste,
  ROUND(c.total_spend_codigo::NUMERIC, 2) as spend_codigo,
  ROUND(r.total_spend::NUMERIC, 2) as spend_rpc,
  ROUND(c.total_revenue_codigo::NUMERIC, 2) as revenue_codigo,
  ROUND(r.total_revenue::NUMERIC, 2) as revenue_rpc,
  CASE 
    WHEN ROUND(ABS(c.total_spend_codigo - r.total_spend)::NUMERIC, 2) < 0.01
     AND ROUND(ABS(c.total_revenue_codigo - r.total_revenue)::NUMERIC, 2) < 0.01
    THEN '✅ OK'
    ELSE '⚠️ VERIFICAR'
  END as status
FROM codigo_atual c
CROSS JOIN rpc_resultado r;

-- ============================================
-- PASSO 4: Validar dia específico (hoje)
-- ============================================

WITH codigo_atual AS (
  SELECT 
    (
      SELECT COALESCE(SUM(dcm.spend), 0)
      FROM daily_campaign_metrics dcm
      INNER JOIN campaigns c ON c.campaign_id = dcm.campaign_id
      INNER JOIN projects p ON p.id = c.project_id
      WHERE dcm.date = CURRENT_DATE::DATE
        AND p.visible = true
    ) as total_spend_codigo,
    (
      SELECT COALESCE(SUM(dpm.revenue_converted_revshare), 0)
      FROM daily_project_metrics dpm
      INNER JOIN projects p ON p.id = dpm.project_id
      WHERE dpm.date = CURRENT_DATE::DATE
        AND p.visible = true
    ) as total_revenue_codigo
),
rpc_resultado AS (
  SELECT * FROM get_dashboard_totals(
    CURRENT_DATE::DATE,
    CURRENT_DATE::DATE,
    NULL::INT
  )
)
SELECT 
  'Hoje' as teste,
  ROUND(c.total_spend_codigo::NUMERIC, 2) as spend_codigo,
  ROUND(r.total_spend::NUMERIC, 2) as spend_rpc,
  ROUND(c.total_revenue_codigo::NUMERIC, 2) as revenue_codigo,
  ROUND(r.total_revenue::NUMERIC, 2) as revenue_rpc,
  CASE 
    WHEN ROUND(ABS(c.total_spend_codigo - r.total_spend)::NUMERIC, 2) < 0.01
     AND ROUND(ABS(c.total_revenue_codigo - r.total_revenue)::NUMERIC, 2) < 0.01
    THEN '✅ OK'
    ELSE '⚠️ VERIFICAR'
  END as status
FROM codigo_atual c
CROSS JOIN rpc_resultado r;
