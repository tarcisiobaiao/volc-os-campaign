-- RPC Function: get_campaign_detailed_metrics
-- Substitui: getCampaignDashboardDataFiltered() em supabaseDataService.ts
-- Problema: 14+ reduces consecutivos no mesmo array
-- Redução: 14 reduces + 2 queries → 1 query agregada
--
-- Lógica atual do código:
-- 1. Query daily_campaign_metrics
-- 2. 14 reduces para calcular: spend, clicks, impressions, conversions, revenue,
--    gam_ecpm, gam_cpc, match_rate, gam_total_requests, gam_impressions,
--    fill_rate, gam_clicks, gam_ctr, viewable_impressions

CREATE OR REPLACE FUNCTION get_campaign_detailed_metrics(
  p_campaign_id TEXT,
  p_start_date DATE,
  p_end_date DATE
)
RETURNS TABLE (
  -- Totais agregados
  total_spend NUMERIC,
  total_clicks BIGINT,
  total_impressions BIGINT,
  total_conversions BIGINT,
  total_revenue NUMERIC,
  -- Totais GAM
  total_gam_total_requests BIGINT,
  total_gam_impressions BIGINT,
  total_gam_clicks BIGINT,
  total_viewable_impressions BIGINT,
  -- Médias (para métricas que precisam de média, não soma)
  avg_gam_ecpm NUMERIC,
  avg_gam_cpc NUMERIC,
  avg_match_rate NUMERIC,
  avg_fill_rate NUMERIC,
  avg_gam_ctr NUMERIC,
  -- Métricas derivadas
  calculated_ctr NUMERIC,
  calculated_cpc NUMERIC,
  calculated_cost_per_conversion NUMERIC,
  calculated_roas NUMERIC,
  calculated_profit NUMERIC,
  -- Contagem de dias
  days_count INT
) AS $$
BEGIN
  RETURN QUERY
  SELECT
    -- Totais agregados
    COALESCE(SUM(dcm.spend), 0)::NUMERIC as total_spend,
    COALESCE(SUM(dcm.clicks), 0)::BIGINT as total_clicks,
    COALESCE(SUM(dcm.impressions), 0)::BIGINT as total_impressions,
    COALESCE(SUM(dcm.conversions), 0)::BIGINT as total_conversions,
    COALESCE(SUM(dcm.revenue_converted_revshare), 0)::NUMERIC as total_revenue,
    -- Totais GAM
    COALESCE(SUM(dcm.gam_total_requests), 0)::BIGINT as total_gam_total_requests,
    COALESCE(SUM(dcm.gam_impressions), 0)::BIGINT as total_gam_impressions,
    COALESCE(SUM(dcm.gam_clicks), 0)::BIGINT as total_gam_clicks,
    COALESCE(SUM(dcm.viewable_impressions), 0)::BIGINT as total_viewable_impressions,
    -- Médias
    COALESCE(AVG(dcm.gam_ecpm), 0)::NUMERIC as avg_gam_ecpm,
    COALESCE(AVG(dcm.gam_cpc), 0)::NUMERIC as avg_gam_cpc,
    COALESCE(AVG(dcm.match_rate), 0)::NUMERIC as avg_match_rate,
    COALESCE(AVG(dcm.fill_rate), 0)::NUMERIC as avg_fill_rate,
    COALESCE(AVG(dcm.gam_ctr), 0)::NUMERIC as avg_gam_ctr,
    -- Métricas derivadas calculadas no SQL
    CASE 
      WHEN COALESCE(SUM(dcm.impressions), 0) > 0 
      THEN (COALESCE(SUM(dcm.clicks), 0)::NUMERIC / COALESCE(SUM(dcm.impressions), 0)) * 100
      ELSE 0
    END::NUMERIC as calculated_ctr,
    CASE 
      WHEN COALESCE(SUM(dcm.clicks), 0) > 0 
      THEN COALESCE(SUM(dcm.spend), 0) / COALESCE(SUM(dcm.clicks), 0)
      ELSE 0
    END::NUMERIC as calculated_cpc,
    CASE 
      WHEN COALESCE(SUM(dcm.conversions), 0) > 0 
      THEN COALESCE(SUM(dcm.spend), 0) / COALESCE(SUM(dcm.conversions), 0)
      ELSE 0
    END::NUMERIC as calculated_cost_per_conversion,
    CASE 
      WHEN COALESCE(SUM(dcm.spend), 0) > 0 
      THEN ((COALESCE(SUM(dcm.revenue_converted_revshare), 0) / COALESCE(SUM(dcm.spend), 0)) - 1) * 100
      ELSE 0
    END::NUMERIC as calculated_roas,
    (COALESCE(SUM(dcm.revenue_converted_revshare), 0) - COALESCE(SUM(dcm.spend), 0))::NUMERIC as calculated_profit,
    -- Contagem
    COUNT(DISTINCT dcm.date)::INT as days_count
  FROM daily_campaign_metrics dcm
  WHERE dcm.campaign_id = p_campaign_id
    AND dcm.date BETWEEN p_start_date AND p_end_date;
END;
$$ LANGUAGE plpgsql;

-- Permissões
GRANT EXECUTE ON FUNCTION get_campaign_detailed_metrics TO authenticated;
GRANT EXECUTE ON FUNCTION get_campaign_detailed_metrics TO anon;

-- ============================================
-- TESTES (execute após criar a função)
-- ============================================

-- Teste 1: Campanha específica, últimos 30 dias
-- Substitua 'CAMPAIGN_ID_AQUI' pelo ID real da campanha
-- SELECT * FROM get_campaign_detailed_metrics(
--   'CAMPAIGN_ID_AQUI',
--   (CURRENT_DATE - INTERVAL '30 days')::DATE,
--   CURRENT_DATE::DATE
-- );

-- Teste 2: Buscar um campaign_id real para testar
-- SELECT DISTINCT campaign_id FROM daily_campaign_metrics LIMIT 5;
