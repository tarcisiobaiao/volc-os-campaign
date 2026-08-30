-- ================================================
-- FIX: Usar revenue_converted_revshare em vez de revenue
-- Para: listagem de campanhas em /settings/campaigns
-- ================================================
-- Execute no Supabase SQL Editor

-- 1. Atualizar RPC get_campaigns_aggregated (usa revenue_converted_revshare)
DROP FUNCTION IF EXISTS get_campaigns_aggregated(integer, date, date);

CREATE OR REPLACE FUNCTION get_campaigns_aggregated(
  p_project_id integer DEFAULT NULL,
  p_start_date date DEFAULT NULL,
  p_end_date date DEFAULT NULL
)
RETURNS TABLE (
  campaign_id character varying,
  campaign_name character varying,
  project_id integer,
  status character varying,
  start_date date,
  end_date date,
  aggregated_spend numeric,
  aggregated_revenue numeric,
  aggregated_impressions bigint,
  aggregated_clicks bigint,
  roas numeric,
  ctr numeric,
  custom_goal text
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT 
    c.campaign_id,
    c.campaign_name,
    c.project_id,
    c.status::VARCHAR,
    c.start_date,
    c.end_date,
    COALESCE(SUM(dcm.spend), 0) AS aggregated_spend,
    COALESCE(SUM(dcm.revenue_converted_revshare), 0) AS aggregated_revenue,
    COALESCE(SUM(dcm.impressions), 0)::BIGINT AS aggregated_impressions,
    COALESCE(SUM(dcm.clicks), 0)::BIGINT AS aggregated_clicks,
    CASE 
      WHEN COALESCE(SUM(dcm.spend), 0) > 0 THEN 
        ((COALESCE(SUM(dcm.revenue_converted_revshare), 0) / SUM(dcm.spend)) - 1) * 100
      ELSE 0 
    END AS roas,
    CASE 
      WHEN COALESCE(SUM(dcm.impressions), 0) > 0 THEN 
        (COALESCE(SUM(dcm.clicks), 0)::NUMERIC / SUM(dcm.impressions)::NUMERIC) * 100
      ELSE 0 
    END AS ctr,
    c.custom_goal
  FROM campaigns c
  LEFT JOIN daily_campaign_metrics dcm ON c.campaign_id = dcm.campaign_id
    AND (p_start_date IS NULL OR dcm.date >= p_start_date)
    AND (p_end_date IS NULL OR dcm.date <= p_end_date)
  WHERE 
    (p_project_id IS NULL OR c.project_id = p_project_id)
  GROUP BY 
    c.campaign_id,
    c.campaign_name,
    c.project_id,
    c.status,
    c.start_date,
    c.end_date,
    c.custom_goal
  ORDER BY aggregated_revenue DESC;
END;
$$;

-- 2. Atualizar view campaigns_with_revenue (dcm_agg usa revenue_converted_revshare)
DROP VIEW IF EXISTS campaigns_with_revenue CASCADE;

CREATE VIEW campaigns_with_revenue AS
SELECT 
  c.id,
  c.project_id,
  c.campaign_name,
  c.start_date,
  c.status,
  c.notes,
  c.campaign_id,
  c.google_ads_status,
  c.created_at,
  c.updated_at,
  c.end_date,
  c.advertising_channel_type,
  c.bidding_strategy,
  c.advertising_channel,
  c.budget_amount,
  c.budget_id,
  c.target_value,
  c.custom_goal,
  COALESCE(dcm_agg.total_spend, 0) AS spend,
  COALESCE(dcm_agg.total_clicks, 0)::BIGINT AS clicks,
  COALESCE(dcm_agg.total_impressions, 0)::BIGINT AS impressions,
  COALESCE(dcm_agg.total_revenue_revshare, 0) AS revenue,
  COALESCE(dcm_agg.avg_roas, 0) AS roas,
  COALESCE(dcm_agg.total_conversions, 0)::NUMERIC AS conversions,
  COALESCE(gm_agg.total_gam_revenue, 0) AS gam_revenue,
  COALESCE(gm_agg.total_gam_revenue_converted, 0) AS gam_revenue_converted,
  CASE
    WHEN COALESCE(dcm_agg.total_spend, 0) > 0 AND COALESCE(dcm_agg.total_revenue_revshare, 0) > 0 
    THEN (dcm_agg.total_revenue_revshare / dcm_agg.total_spend) * 100
    ELSE 0
  END AS calculated_roas,
  CASE
    WHEN COALESCE(dcm_agg.total_revenue_revshare, 0) > 0 
    THEN dcm_agg.total_revenue_revshare - COALESCE(dcm_agg.total_spend, 0)
    ELSE 0
  END AS profit
FROM campaigns c
LEFT JOIN (
  SELECT 
    dcm.campaign_id,
    SUM(dcm.spend) AS total_spend,
    SUM(dcm.clicks) AS total_clicks,
    SUM(dcm.impressions) AS total_impressions,
    SUM(COALESCE(dcm.revenue_converted_revshare, 0)) AS total_revenue_revshare,
    SUM(dcm.conversions) AS total_conversions,
    AVG(dcm.roas) AS avg_roas
  FROM daily_campaign_metrics dcm
  GROUP BY dcm.campaign_id
) dcm_agg ON c.campaign_id::text = dcm_agg.campaign_id::text
LEFT JOIN (
  SELECT 
    gm.utm_campaign_value,
    SUM(gm.revenue) AS total_gam_revenue,
    SUM(COALESCE(gm.revenue_converted, gm.revenue * 5.35)) AS total_gam_revenue_converted
  FROM gam_metrics gm
  WHERE gm.utm_campaign_value IS NOT NULL
  GROUP BY gm.utm_campaign_value
) gm_agg ON c.campaign_id::text = gm_agg.utm_campaign_value::text;
