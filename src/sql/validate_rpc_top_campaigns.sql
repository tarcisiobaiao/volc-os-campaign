-- ============================================
-- VALIDAÇÃO: RPC get_top_campaigns_by_revenue
-- Execute APÓS criar a função no Supabase
-- ============================================

-- PASSO 1: Criar a função (execute rpc_get_top_campaigns_by_revenue.sql primeiro)

-- PASSO 2: Testar top 5 campanhas (últimos 30 dias)
SELECT * FROM get_top_campaigns_by_revenue(
  (CURRENT_DATE - INTERVAL '30 days')::DATE,
  CURRENT_DATE::DATE,
  NULL::INT,
  5
);

-- PASSO 3: Comparar com método atual do frontend
-- O código faz: .sort((a, b) => (b.revenue || 0) - (a.revenue || 0)).slice(0, 5)

WITH codigo_atual AS (
  SELECT 
    c.campaign_id,
    c.campaign_name,
    c.project_id,
    p.project_name,
    COALESCE(SUM(dcm.revenue_converted_revshare), 0) as total_revenue,
    COALESCE(SUM(dcm.spend), 0) as total_spend
  FROM campaigns c
  INNER JOIN projects p ON p.id = c.project_id
  LEFT JOIN daily_campaign_metrics dcm ON dcm.campaign_id = c.campaign_id
    AND dcm.date BETWEEN (CURRENT_DATE - INTERVAL '30 days')::DATE AND CURRENT_DATE::DATE
  WHERE p.visible = true
  GROUP BY c.campaign_id, c.campaign_name, c.project_id, p.project_name
  HAVING COALESCE(SUM(dcm.revenue_converted_revshare), 0) > 0
  ORDER BY total_revenue DESC
  LIMIT 5
),
rpc_resultado AS (
  SELECT campaign_id, campaign_name, project_name, total_revenue, total_spend
  FROM get_top_campaigns_by_revenue(
    (CURRENT_DATE - INTERVAL '30 days')::DATE,
    CURRENT_DATE::DATE,
    NULL::INT,
    5
  )
)
SELECT 
  COALESCE(c.campaign_name, r.campaign_name) as campanha,
  ROUND(c.total_revenue::NUMERIC, 2) as revenue_codigo,
  ROUND(r.total_revenue::NUMERIC, 2) as revenue_rpc,
  ROUND(c.total_spend::NUMERIC, 2) as spend_codigo,
  ROUND(r.total_spend::NUMERIC, 2) as spend_rpc,
  CASE 
    WHEN c.campaign_id = r.campaign_id 
     AND ROUND(ABS(c.total_revenue - r.total_revenue)::NUMERIC, 2) < 0.01
    THEN '✅'
    ELSE '⚠️'
  END as status
FROM codigo_atual c
FULL OUTER JOIN rpc_resultado r ON c.campaign_id = r.campaign_id
ORDER BY COALESCE(c.total_revenue, r.total_revenue) DESC;
