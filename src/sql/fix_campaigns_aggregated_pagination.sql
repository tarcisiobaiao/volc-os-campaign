-- ============================================================
-- FIX: Paginação na RPC get_campaigns_aggregated
-- ============================================================
-- Problema: PostgREST aplica cap silencioso de 1000 linhas no
-- retorno da RPC. Em dias com >1000 campanhas ativas (caso atual
-- já passou de 1100), o front recebia só 1000 linhas, caía no
-- fallback bugado e zerava todas as métricas para o usuário.
--
-- Solução: adicionar parâmetros p_limit/p_offset (additivos,
-- backwards-compatible) e aplicar OFFSET/LIMIT dentro da própria
-- função, antes do retorno. Isso garante que o cap do PostgREST
-- nunca corta o resultado, porque cada página já chega abaixo
-- do limite. O client paginha em loop.
--
-- Tiebreaker `campaign_id ASC` adicionado ao ORDER BY para
-- garantir ordenação estável entre páginas (regra de paginação
-- v6: ORDER BY composto obrigatório).
--
-- Execute no Supabase SQL Editor.
-- ============================================================

DROP FUNCTION IF EXISTS get_campaigns_aggregated(integer, date, date);
DROP FUNCTION IF EXISTS get_campaigns_aggregated(integer, date, date, integer, integer);

CREATE OR REPLACE FUNCTION get_campaigns_aggregated(
  p_project_id integer DEFAULT NULL,
  p_start_date date DEFAULT NULL,
  p_end_date date DEFAULT NULL,
  p_limit integer DEFAULT NULL,
  p_offset integer DEFAULT 0
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
STABLE
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
  ORDER BY aggregated_revenue DESC, c.campaign_id ASC
  OFFSET COALESCE(p_offset, 0)
  LIMIT p_limit;
END;
$$;

-- Smoke test (opcional — descomente para validar após criar):
-- SELECT count(*) AS total_sem_paginacao
--   FROM get_campaigns_aggregated(NULL, CURRENT_DATE, CURRENT_DATE);
-- SELECT count(*) AS pagina_1
--   FROM get_campaigns_aggregated(NULL, CURRENT_DATE, CURRENT_DATE, 500, 0);
-- SELECT count(*) AS pagina_2
--   FROM get_campaigns_aggregated(NULL, CURRENT_DATE, CURRENT_DATE, 500, 500);
