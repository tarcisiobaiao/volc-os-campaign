-- RPC Function: get_top_campaigns_by_revenue
-- Substitui: Fetch all + .sort() + .slice() no frontend
-- Problema: Busca todas campanhas, ordena e filtra no frontend
-- Redução: Fetch all + sort + slice → ORDER BY + LIMIT no SQL
--
-- Usado em: GeneralDashboard.tsx, Reports.tsx
-- .sort((a, b) => (b.revenue || 0) - (a.revenue || 0)).slice(0, 5)

CREATE OR REPLACE FUNCTION get_top_campaigns_by_revenue(
  p_start_date DATE,
  p_end_date DATE,
  p_project_id INT DEFAULT NULL,
  p_limit INT DEFAULT 10
)
RETURNS TABLE (
  campaign_id TEXT,
  campaign_name TEXT,
  project_id INT,
  project_name TEXT,
  status VARCHAR(50),
  total_spend NUMERIC,
  total_revenue NUMERIC,
  total_profit NUMERIC,
  roas NUMERIC,
  roi NUMERIC,
  total_clicks BIGINT,
  total_impressions BIGINT,
  total_conversions BIGINT,
  ctr NUMERIC,
  cpc NUMERIC
) AS $$
BEGIN
  RETURN QUERY
  SELECT 
    c.campaign_id::TEXT,
    c.campaign_name::TEXT,
    c.project_id::INT,
    p.project_name::TEXT,
    c.status::VARCHAR(50),
    COALESCE(SUM(dcm.spend), 0)::NUMERIC as total_spend,
    COALESCE(SUM(dcm.revenue_converted_revshare), 0)::NUMERIC as total_revenue,
    (COALESCE(SUM(dcm.revenue_converted_revshare), 0) - COALESCE(SUM(dcm.spend), 0))::NUMERIC as total_profit,
    -- ROAS
    CASE 
      WHEN COALESCE(SUM(dcm.spend), 0) > 0 
      THEN ((COALESCE(SUM(dcm.revenue_converted_revshare), 0) / SUM(dcm.spend)) - 1) * 100
      ELSE 0
    END::NUMERIC as roas,
    -- ROI
    CASE 
      WHEN COALESCE(SUM(dcm.spend), 0) > 0 
      THEN ((COALESCE(SUM(dcm.revenue_converted_revshare), 0) - SUM(dcm.spend)) / SUM(dcm.spend)) * 100
      ELSE 0
    END::NUMERIC as roi,
    COALESCE(SUM(dcm.clicks), 0)::BIGINT as total_clicks,
    COALESCE(SUM(dcm.impressions), 0)::BIGINT as total_impressions,
    COALESCE(SUM(dcm.conversions), 0)::BIGINT as total_conversions,
    -- CTR
    CASE 
      WHEN COALESCE(SUM(dcm.impressions), 0) > 0 
      THEN (COALESCE(SUM(dcm.clicks), 0)::NUMERIC / SUM(dcm.impressions)) * 100
      ELSE 0
    END::NUMERIC as ctr,
    -- CPC
    CASE 
      WHEN COALESCE(SUM(dcm.clicks), 0) > 0 
      THEN COALESCE(SUM(dcm.spend), 0) / SUM(dcm.clicks)
      ELSE 0
    END::NUMERIC as cpc
  FROM campaigns c
  INNER JOIN projects p ON p.id = c.project_id
  LEFT JOIN daily_campaign_metrics dcm ON dcm.campaign_id = c.campaign_id
    AND dcm.date BETWEEN p_start_date AND p_end_date
  WHERE p.visible = true
    AND (p_project_id IS NULL OR c.project_id = p_project_id)
  GROUP BY c.campaign_id, c.campaign_name, c.project_id, p.project_name, c.status
  HAVING COALESCE(SUM(dcm.revenue_converted_revshare), 0) > 0  -- Apenas com revenue > 0
  ORDER BY total_revenue DESC
  LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- Permissões
GRANT EXECUTE ON FUNCTION get_top_campaigns_by_revenue TO authenticated;
GRANT EXECUTE ON FUNCTION get_top_campaigns_by_revenue TO anon;

-- ============================================
-- TESTES (execute após criar a função)
-- ============================================

-- Teste 1: Top 5 campanhas (todos os projetos), últimos 30 dias
-- SELECT * FROM get_top_campaigns_by_revenue(
--   (CURRENT_DATE - INTERVAL '30 days')::DATE,
--   CURRENT_DATE::DATE,
--   NULL::INT,
--   5
-- );

-- Teste 2: Top 10 campanhas de um projeto específico
-- SELECT * FROM get_top_campaigns_by_revenue(
--   (CURRENT_DATE - INTERVAL '30 days')::DATE,
--   CURRENT_DATE::DATE,
--   11,  -- ⚠️ SUBSTITUA pelo ID real
--   10
-- );
