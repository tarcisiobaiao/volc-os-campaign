-- RPC Function: get_period_comparison
-- Substitui: Múltiplas chamadas para calcular trendsPercentage
-- Problema: Precisa buscar dados de 2 períodos separadamente e calcular variação
-- Redução: 2+ queries → 1 query com comparação temporal
--
-- Usado em: GeneralDashboard.tsx (trendsPercentage), ProjectDashboard.tsx
-- Exemplo: "+5.5% vs período anterior"

CREATE OR REPLACE FUNCTION get_period_comparison(
  p_current_start DATE,
  p_current_end DATE,
  p_project_id INT DEFAULT NULL
)
RETURNS TABLE (
  -- Período atual
  current_spend NUMERIC,
  current_revenue NUMERIC,
  current_profit NUMERIC,
  current_roas NUMERIC,
  current_roi NUMERIC,
  -- Período anterior (mesmo tamanho)
  previous_spend NUMERIC,
  previous_revenue NUMERIC,
  previous_profit NUMERIC,
  previous_roas NUMERIC,
  previous_roi NUMERIC,
  -- Variação percentual
  trend_investment NUMERIC,
  trend_revenue NUMERIC,
  trend_profit NUMERIC,
  trend_roas NUMERIC,
  trend_roi NUMERIC
)
LANGUAGE plpgsql
AS $func$
DECLARE
  v_period_days INT;
  v_previous_start DATE;
  v_previous_end DATE;
  -- Current period values
  v_current_spend NUMERIC := 0;
  v_current_revenue NUMERIC := 0;
  -- Previous period values
  v_previous_spend NUMERIC := 0;
  v_previous_revenue NUMERIC := 0;
BEGIN
  -- Calcular tamanho do período
  v_period_days := (p_current_end - p_current_start) + 1;
  
  -- Calcular período anterior (mesmo tamanho, imediatamente antes)
  v_previous_end := p_current_start - 1;
  v_previous_start := v_previous_end - v_period_days + 1;

  -- Buscar dados do período ATUAL
  SELECT 
    COALESCE(SUM(dcm.spend), 0),
    COALESCE(SUM(dcm.revenue_converted_revshare), 0)
  INTO v_current_spend, v_current_revenue
  FROM daily_campaign_metrics dcm
  INNER JOIN campaigns c ON c.campaign_id = dcm.campaign_id
  WHERE dcm.date BETWEEN p_current_start AND p_current_end
    AND (p_project_id IS NULL OR c.project_id = p_project_id);

  -- Adicionar revenue de daily_project_metrics (para projetos sem campanhas diretas)
  SELECT v_current_revenue + COALESCE(SUM(dpm.revenue_converted_revshare), 0)
  INTO v_current_revenue
  FROM daily_project_metrics dpm
  WHERE dpm.date BETWEEN p_current_start AND p_current_end
    AND (p_project_id IS NULL OR dpm.project_id = p_project_id)
    AND NOT EXISTS (
      SELECT 1 FROM campaigns c2 
      WHERE c2.project_id = dpm.project_id
    );

  -- Buscar dados do período ANTERIOR
  SELECT 
    COALESCE(SUM(dcm.spend), 0),
    COALESCE(SUM(dcm.revenue_converted_revshare), 0)
  INTO v_previous_spend, v_previous_revenue
  FROM daily_campaign_metrics dcm
  INNER JOIN campaigns c ON c.campaign_id = dcm.campaign_id
  WHERE dcm.date BETWEEN v_previous_start AND v_previous_end
    AND (p_project_id IS NULL OR c.project_id = p_project_id);

  -- Adicionar revenue de daily_project_metrics para período anterior
  SELECT v_previous_revenue + COALESCE(SUM(dpm.revenue_converted_revshare), 0)
  INTO v_previous_revenue
  FROM daily_project_metrics dpm
  WHERE dpm.date BETWEEN v_previous_start AND v_previous_end
    AND (p_project_id IS NULL OR dpm.project_id = p_project_id)
    AND NOT EXISTS (
      SELECT 1 FROM campaigns c2 
      WHERE c2.project_id = dpm.project_id
    );

  RETURN QUERY
  SELECT
    -- Período atual
    v_current_spend,
    v_current_revenue,
    (v_current_revenue - v_current_spend),
    CASE WHEN v_current_spend > 0 THEN ((v_current_revenue / v_current_spend) - 1) * 100 ELSE 0 END,
    CASE WHEN v_current_spend > 0 THEN ((v_current_revenue - v_current_spend) / v_current_spend) * 100 ELSE 0 END,
    -- Período anterior
    v_previous_spend,
    v_previous_revenue,
    (v_previous_revenue - v_previous_spend),
    CASE WHEN v_previous_spend > 0 THEN ((v_previous_revenue / v_previous_spend) - 1) * 100 ELSE 0 END,
    CASE WHEN v_previous_spend > 0 THEN ((v_previous_revenue - v_previous_spend) / v_previous_spend) * 100 ELSE 0 END,
    -- Variações percentuais
    CASE WHEN v_previous_spend > 0 THEN ((v_current_spend - v_previous_spend) / v_previous_spend) * 100 ELSE 0 END,
    CASE WHEN v_previous_revenue > 0 THEN ((v_current_revenue - v_previous_revenue) / v_previous_revenue) * 100 ELSE 0 END,
    CASE WHEN (v_previous_revenue - v_previous_spend) != 0 
         THEN (((v_current_revenue - v_current_spend) - (v_previous_revenue - v_previous_spend)) / ABS(v_previous_revenue - v_previous_spend)) * 100 
         ELSE 0 END,
    CASE WHEN v_previous_spend > 0 AND ((v_previous_revenue / v_previous_spend) - 1) != 0
         THEN ((((v_current_revenue / NULLIF(v_current_spend, 0)) - 1) - ((v_previous_revenue / v_previous_spend) - 1)) / ABS((v_previous_revenue / v_previous_spend) - 1)) * 100
         ELSE 0 END,
    CASE WHEN v_previous_spend > 0 AND ((v_previous_revenue - v_previous_spend) / v_previous_spend) != 0
         THEN (((v_current_revenue - v_current_spend) / NULLIF(v_current_spend, 0) - (v_previous_revenue - v_previous_spend) / v_previous_spend) / ABS((v_previous_revenue - v_previous_spend) / v_previous_spend)) * 100
         ELSE 0 END;
END;
$func$;

-- Permissões
GRANT EXECUTE ON FUNCTION get_period_comparison TO authenticated;
GRANT EXECUTE ON FUNCTION get_period_comparison TO anon;

-- ============================================
-- TESTES (execute após criar a função)
-- ============================================

-- Teste 1: Comparar hoje vs ontem
-- SELECT * FROM get_period_comparison(
--   CURRENT_DATE::DATE,
--   CURRENT_DATE::DATE,
--   NULL::INT
-- );

-- Teste 2: Comparar últimos 7 dias vs 7 dias anteriores
-- SELECT * FROM get_period_comparison(
--   (CURRENT_DATE - INTERVAL '7 days')::DATE,
--   CURRENT_DATE::DATE,
--   NULL::INT
-- );

-- Teste 3: Comparar últimos 30 dias vs 30 dias anteriores
-- SELECT * FROM get_period_comparison(
--   (CURRENT_DATE - INTERVAL '30 days')::DATE,
--   CURRENT_DATE::DATE,
--   NULL::INT
-- );
