-- RPC Function: get_daily_metrics_aggregated
-- Substitui: getDailyMetrics() em supabaseDataService.ts
-- Problema: 2 queries separadas + iterações para agregar por data
-- Redução: 2 queries + forEach → 1 query agregada por dia
--
-- Lógica atual do código:
-- 1. Query daily_project_metrics → revenue por data
-- 2. Query daily_campaign_metrics → spend, clicks, impressions, conversions por data
-- 3. Itera para juntar por data
-- 4. Calcula métricas derivadas (profit, roas, roi, ctr, cpc)

CREATE OR REPLACE FUNCTION get_daily_metrics_aggregated(
  p_start_date DATE,
  p_end_date DATE,
  p_project_id INT DEFAULT NULL
)
RETURNS TABLE (
  metric_date DATE,
  investment NUMERIC,
  revenue NUMERIC,
  profit NUMERIC,
  roas NUMERIC,
  roi NUMERIC,
  impressions BIGINT,
  clicks BIGINT,
  ctr NUMERIC,
  conversions BIGINT,
  cpc NUMERIC
) AS $$
BEGIN
  RETURN QUERY
  WITH spend_by_date AS (
    -- Agregar spend e métricas de campanha por data (TODOS os projetos)
    SELECT 
      dcm.date as metric_date,
      COALESCE(SUM(dcm.spend), 0)::NUMERIC as total_spend,
      COALESCE(SUM(dcm.clicks), 0)::BIGINT as total_clicks,
      COALESCE(SUM(dcm.impressions), 0)::BIGINT as total_impressions,
      COALESCE(SUM(dcm.conversions), 0)::BIGINT as total_conversions
    FROM daily_campaign_metrics dcm
    INNER JOIN campaigns c ON c.campaign_id = dcm.campaign_id
    WHERE dcm.date BETWEEN p_start_date AND p_end_date
      AND (p_project_id IS NULL OR c.project_id = p_project_id)
    GROUP BY dcm.date
  ),
  revenue_by_date AS (
    -- Agregar revenue por data (TODOS os projetos, já com revshare aplicado)
    SELECT 
      dpm.date as metric_date,
      COALESCE(SUM(dpm.revenue_converted_revshare), 0)::NUMERIC as total_revenue
    FROM daily_project_metrics dpm
    WHERE dpm.date BETWEEN p_start_date AND p_end_date
      AND (p_project_id IS NULL OR dpm.project_id = p_project_id)
    GROUP BY dpm.date
  ),
  all_dates AS (
    -- Gerar todas as datas no intervalo
    SELECT generate_series(p_start_date, p_end_date, '1 day'::interval)::DATE as metric_date
  )
  SELECT 
    d.metric_date,
    COALESCE(s.total_spend, 0)::NUMERIC as investment,
    COALESCE(r.total_revenue, 0)::NUMERIC as revenue,
    (COALESCE(r.total_revenue, 0) - COALESCE(s.total_spend, 0))::NUMERIC as profit,
    -- ROAS: (revenue / spend) * 100
    CASE 
      WHEN COALESCE(s.total_spend, 0) > 0 
      THEN (COALESCE(r.total_revenue, 0) / s.total_spend) * 100
      ELSE 0
    END::NUMERIC as roas,
    -- ROI: (profit / spend) * 100
    CASE 
      WHEN COALESCE(s.total_spend, 0) > 0 
      THEN ((COALESCE(r.total_revenue, 0) - s.total_spend) / s.total_spend) * 100
      ELSE 0
    END::NUMERIC as roi,
    COALESCE(s.total_impressions, 0)::BIGINT as impressions,
    COALESCE(s.total_clicks, 0)::BIGINT as clicks,
    -- CTR: (clicks / impressions) * 100
    CASE 
      WHEN COALESCE(s.total_impressions, 0) > 0 
      THEN (COALESCE(s.total_clicks, 0)::NUMERIC / s.total_impressions) * 100
      ELSE 0
    END::NUMERIC as ctr,
    COALESCE(s.total_conversions, 0)::BIGINT as conversions,
    -- CPC: spend / clicks
    CASE 
      WHEN COALESCE(s.total_clicks, 0) > 0 
      THEN COALESCE(s.total_spend, 0) / s.total_clicks
      ELSE 0
    END::NUMERIC as cpc
  FROM all_dates d
  LEFT JOIN spend_by_date s ON s.metric_date = d.metric_date
  LEFT JOIN revenue_by_date r ON r.metric_date = d.metric_date
  ORDER BY d.metric_date DESC;
END;
$$ LANGUAGE plpgsql;

-- Permissões
GRANT EXECUTE ON FUNCTION get_daily_metrics_aggregated TO authenticated;
GRANT EXECUTE ON FUNCTION get_daily_metrics_aggregated TO anon;

-- ============================================
-- TESTES (execute após criar a função)
-- ============================================

-- Teste 1: Todos os projetos, últimos 7 dias
-- SELECT * FROM get_daily_metrics_aggregated(
--   (CURRENT_DATE - INTERVAL '7 days')::DATE,
--   CURRENT_DATE::DATE,
--   NULL::INT
-- );

-- Teste 2: Projeto específico, últimos 30 dias
-- SELECT * FROM get_daily_metrics_aggregated(
--   (CURRENT_DATE - INTERVAL '30 days')::DATE,
--   CURRENT_DATE::DATE,
--   11  -- ⚠️ SUBSTITUA pelo ID real
-- );
