-- RPC Function: get_projects_summary
-- This function replaces the getProjects() logic that makes 4 queries per project
-- Reduces 80+ queries (for 20 projects) to a single database call
--
-- How to use in Supabase SQL Editor:
-- 1. Copy and paste this entire SQL code
-- 2. Click "Run" to create the function
-- 3. Test with: SELECT * FROM get_projects_summary('2025-01-01', '2025-01-31', NULL);

CREATE OR REPLACE FUNCTION get_projects_summary(
  p_start_date DATE,
  p_end_date DATE,
  p_project_id INT DEFAULT NULL
)
RETURNS TABLE (
  id INT,
  project_name VARCHAR(255),
  domain VARCHAR(255),
  status VARCHAR(50),
  costs_division BOOLEAN,
  project_type VARCHAR(50),
  total_spend NUMERIC,
  total_revenue NUMERIC,
  campaign_count INT,
  active_campaigns INT,
  paused_campaigns INT
) AS $$
BEGIN
  RETURN QUERY
  WITH project_spend AS (
    -- Agregar spend por projeto (evita multiplicação de JOINs)
    SELECT 
      p.id as project_id,
      COALESCE(SUM(dcm.spend), 0)::NUMERIC as total_spend
    FROM projects p
    LEFT JOIN campaigns c ON c.project_id = p.id
    LEFT JOIN daily_campaign_metrics dcm ON dcm.campaign_id = c.campaign_id
      AND dcm.date BETWEEN p_start_date AND p_end_date
    WHERE p.visible = true
      AND (p_project_id IS NULL OR p.id = p_project_id)
    GROUP BY p.id
  ),
  project_revenue AS (
    -- Agregar revenue por projeto (evita multiplicação de JOINs)
    SELECT 
      p.id as project_id,
      COALESCE(SUM(dpm.revenue_converted_revshare), 0)::NUMERIC as total_revenue
    FROM projects p
    LEFT JOIN daily_project_metrics dpm ON dpm.project_id = p.id
      AND dpm.date BETWEEN p_start_date AND p_end_date
    WHERE p.visible = true
      AND (p_project_id IS NULL OR p.id = p_project_id)
    GROUP BY p.id
  ),
  project_campaigns AS (
    -- Contar campanhas por projeto
    SELECT 
      p.id as project_id,
      COUNT(DISTINCT c.id)::INT as campaign_count,
      COUNT(DISTINCT CASE WHEN c.status = 'Active' THEN c.id END)::INT as active_campaigns,
      COUNT(DISTINCT CASE WHEN c.status = 'Paused' THEN c.id END)::INT as paused_campaigns
    FROM projects p
    LEFT JOIN campaigns c ON c.project_id = p.id
    WHERE p.visible = true
      AND (p_project_id IS NULL OR p.id = p_project_id)
    GROUP BY p.id
  )
  SELECT
    p.id,
    p.project_name,
    p.domain,
    p.status::VARCHAR(50),
    p.costs_division,
    p.project_type::VARCHAR(50),
    COALESCE(ps.total_spend, 0)::NUMERIC as total_spend,
    COALESCE(pr.total_revenue, 0)::NUMERIC as total_revenue,
    COALESCE(pc.campaign_count, 0)::INT as campaign_count,
    COALESCE(pc.active_campaigns, 0)::INT as active_campaigns,
    COALESCE(pc.paused_campaigns, 0)::INT as paused_campaigns
  FROM projects p
  LEFT JOIN project_spend ps ON ps.project_id = p.id
  LEFT JOIN project_revenue pr ON pr.project_id = p.id
  LEFT JOIN project_campaigns pc ON pc.project_id = p.id
  WHERE p.visible = true
    AND (p_project_id IS NULL OR p.id = p_project_id)
  ORDER BY p.id;
END;
$$ LANGUAGE plpgsql;

-- Test query examples:
-- Get all projects for January 2025:
-- SELECT * FROM get_projects_summary('2025-01-01', '2025-01-31', NULL);
--
-- Get specific project (id=11) for a date range:
-- SELECT * FROM get_projects_summary('2025-01-01', '2025-01-31', 11);
