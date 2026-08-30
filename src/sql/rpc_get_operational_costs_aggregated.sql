-- RPC Function: get_operational_costs_aggregated
-- Substitui: Loop manual em calculateProjectNetProfitWithOperationalCosts()
-- Problema: Loop de meses + reduce para custos operacionais (N queries por mês)
-- Redução: N queries (1 por mês) → 1 query agregada
--
-- Lógica atual do código:
-- 1. Loop por cada mês no período
-- 2. Para cada mês: operationalCostsService.getActiveCostsByMonth(month)
-- 3. reduce para somar os custos
-- 4. Query para contar projetos com costs_division = true
-- 5. Cálculo proporcional por dia e por projeto

CREATE OR REPLACE FUNCTION get_operational_costs_aggregated(
  p_start_date DATE,
  p_end_date DATE
)
RETURNS TABLE (
  total_operational_costs NUMERIC,
  projects_with_division INT,
  total_days_in_months INT,
  days_in_period INT,
  daily_operational_cost NUMERIC,
  cost_per_project_per_day NUMERIC
) AS $$
DECLARE
  v_total_costs NUMERIC := 0;
  v_projects_count INT := 0;
  v_total_days INT := 0;
  v_period_days INT := 0;
BEGIN
  -- 1. Calcular total de custos operacionais ativos no período
  SELECT COALESCE(SUM(oc.amount), 0)
  INTO v_total_costs
  FROM operational_costs oc
  WHERE oc.is_active = true
    AND oc.month >= date_trunc('month', p_start_date)::DATE
    AND oc.month <= date_trunc('month', p_end_date)::DATE;

  -- 2. Contar projetos com divisão de custos
  SELECT COUNT(*)
  INTO v_projects_count
  FROM projects p
  WHERE p.costs_division = true;
  
  -- Se não há projetos, usar 1 para evitar divisão por zero
  IF v_projects_count = 0 THEN
    v_projects_count := 1;
  END IF;

  -- 3. Calcular total de dias nos meses do período
  SELECT COALESCE(SUM(
    EXTRACT(DAY FROM (date_trunc('month', m) + INTERVAL '1 month - 1 day'))
  ), 0)::INT
  INTO v_total_days
  FROM generate_series(
    date_trunc('month', p_start_date)::DATE,
    date_trunc('month', p_end_date)::DATE,
    '1 month'::INTERVAL
  ) m;

  -- 4. Calcular dias no período específico
  v_period_days := (p_end_date - p_start_date) + 1;

  RETURN QUERY
  SELECT 
    v_total_costs::NUMERIC as total_operational_costs,
    v_projects_count::INT as projects_with_division,
    v_total_days::INT as total_days_in_months,
    v_period_days::INT as days_in_period,
    CASE 
      WHEN v_total_days > 0 THEN v_total_costs / v_total_days
      ELSE 0
    END::NUMERIC as daily_operational_cost,
    CASE 
      WHEN v_total_days > 0 AND v_projects_count > 0 
      THEN (v_total_costs / v_total_days * v_period_days) / v_projects_count
      ELSE 0
    END::NUMERIC as cost_per_project_per_day;
END;
$$ LANGUAGE plpgsql;

-- Permissões
GRANT EXECUTE ON FUNCTION get_operational_costs_aggregated TO authenticated;
GRANT EXECUTE ON FUNCTION get_operational_costs_aggregated TO anon;

-- ============================================
-- TESTES (execute após criar a função)
-- ============================================

-- Teste 1: Mês atual
-- SELECT * FROM get_operational_costs_aggregated(
--   date_trunc('month', CURRENT_DATE)::DATE,
--   CURRENT_DATE::DATE
-- );

-- Teste 2: Últimos 30 dias
-- SELECT * FROM get_operational_costs_aggregated(
--   (CURRENT_DATE - INTERVAL '30 days')::DATE,
--   CURRENT_DATE::DATE
-- );

-- Teste 3: Mês específico (Janeiro 2025)
-- SELECT * FROM get_operational_costs_aggregated(
--   '2025-01-01'::DATE,
--   '2025-01-31'::DATE
-- );
