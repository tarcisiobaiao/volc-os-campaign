-- RPC Function: get_dashboard_totals
-- Substitui: getDashboardData() em supabaseDataService.ts
-- Problema: Múltiplos reduces + queries separadas para spend e revenue
-- Redução: ~10 queries + reduces → 1 query agregada
--
-- Lógica atual do código:
-- 1. Query daily_project_metrics → SUM(revenue_converted_revshare)
-- 2. Query daily_campaign_metrics → SUM(spend) via campaigns
-- 3. Query campaigns → COUNT ativas/pausadas
-- 4. Múltiplos .reduce() no frontend

CREATE OR REPLACE FUNCTION get_dashboard_totals(
  p_start_date DATE,
  p_end_date DATE,
  p_project_id INT DEFAULT NULL
)
RETURNS TABLE (
  total_spend NUMERIC,
  total_revenue NUMERIC,
  total_profit NUMERIC,
  general_roas NUMERIC,
  final_roi NUMERIC,
  active_campaigns INT,
  paused_campaigns INT,
  total_campaigns INT
) AS $$
BEGIN
  RETURN QUERY
  WITH spend_data AS (
    -- SUM de spend via daily_campaign_metrics (TODOS os projetos, igual ao código atual)
    SELECT 
      COALESCE(SUM(dcm.spend), 0)::NUMERIC as total_spend
    FROM daily_campaign_metrics dcm
    INNER JOIN campaigns c ON c.campaign_id = dcm.campaign_id
    WHERE dcm.date BETWEEN p_start_date AND p_end_date
      AND (p_project_id IS NULL OR c.project_id = p_project_id)
  ),
  revenue_data AS (
    -- SUM de revenue via daily_project_metrics (TODOS os projetos, igual ao código atual)
    SELECT 
      COALESCE(SUM(dpm.revenue_converted_revshare), 0)::NUMERIC as total_revenue
    FROM daily_project_metrics dpm
    WHERE dpm.date BETWEEN p_start_date AND p_end_date
      AND (p_project_id IS NULL OR dpm.project_id = p_project_id)
  ),
  campaign_counts AS (
    -- Contagem de campanhas por status (apenas projetos visíveis para listagem)
    SELECT 
      COUNT(DISTINCT CASE WHEN c.status = 'Active' THEN c.id END)::INT as active_campaigns,
      COUNT(DISTINCT CASE WHEN c.status = 'Paused' THEN c.id END)::INT as paused_campaigns,
      COUNT(DISTINCT c.id)::INT as total_campaigns
    FROM campaigns c
    INNER JOIN projects p ON p.id = c.project_id
    WHERE p.visible = true
      AND (p_project_id IS NULL OR c.project_id = p_project_id)
  )
  SELECT
    s.total_spend,
    r.total_revenue,
    (r.total_revenue - s.total_spend)::NUMERIC as total_profit,
    CASE 
      WHEN s.total_spend > 0 THEN ((r.total_revenue / s.total_spend) - 1) * 100
      ELSE 0
    END::NUMERIC as general_roas,
    CASE 
      WHEN s.total_spend > 0 THEN ((r.total_revenue - s.total_spend) / s.total_spend) * 100
      ELSE 0
    END::NUMERIC as final_roi,
    cc.active_campaigns,
    cc.paused_campaigns,
    cc.total_campaigns
  FROM spend_data s
  CROSS JOIN revenue_data r
  CROSS JOIN campaign_counts cc;
END;
$$ LANGUAGE plpgsql;

-- Permissões
GRANT EXECUTE ON FUNCTION get_dashboard_totals TO authenticated;
GRANT EXECUTE ON FUNCTION get_dashboard_totals TO anon;

-- ============================================
-- TESTES (execute após criar a função)
-- ============================================

-- Teste 1: Todos os projetos, últimos 30 dias
-- SELECT * FROM get_dashboard_totals(
--   (CURRENT_DATE - INTERVAL '30 days')::DATE,
--   CURRENT_DATE::DATE,
--   NULL::INT
-- );

-- Teste 2: Projeto específico (substitua 11 pelo ID real)
-- SELECT * FROM get_dashboard_totals(
--   (CURRENT_DATE - INTERVAL '30 days')::DATE,
--   CURRENT_DATE::DATE,
--   11
-- );

-- Teste 3: Dia específico (hoje)
-- SELECT * FROM get_dashboard_totals(
--   CURRENT_DATE::DATE,
--   CURRENT_DATE::DATE,
--   NULL::INT
-- );
