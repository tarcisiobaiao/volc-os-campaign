-- FUNÇÃO QUE ATUALIZA A TABELA campaign_highlights COM FALLBACK INTELIGENTE
-- ⚠️ DEVE SER CHAMADA APENAS PELO CRON ÀS 6AM
-- Esta função seleciona as 30 campanhas do dia (10+10+10) e salva na tabela
--
-- REGRAS DE SELEÇÃO (baseado em 14 dias de dados):
-- EM ALTA (10 campanhas): Prioriza ROAS alto + crescimento
--   1º: var≥15% + ROAS>1.7
--   2º: var≥15% + ROAS>1.5
--   3º: var≥10% + ROAS>1.5
--   4º: crescimento positivo + ROAS>1.7
--
-- ESTAGNADA (10 campanhas): ROAS médio entre 1.4 e 1.7
-- EM BAIXA (10 campanhas): var≤-15% OU ROAS<1.4
-- ROTAÇÃO: Campanhas só podem reaparecer após 5 dias

DROP FUNCTION IF EXISTS refresh_campaign_highlights();

CREATE OR REPLACE FUNCTION refresh_campaign_highlights()
RETURNS TABLE (
  campaign_id_out TEXT,
  campaign_name_out TEXT,
  status_out VARCHAR,
  inserted_count INT
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_today_date DATE := CURRENT_DATE;
  v_exclude_date DATE := v_today_date - INTERVAL '5 days';
  v_result_count INT := 0;
  v_already_executed INT := 0;
BEGIN
  -- ⚠️ VERIFICAR SE JÁ FOI EXECUTADA HOJE
  SELECT COUNT(*) INTO v_already_executed
  FROM campaign_highlights
  WHERE highlighted_at = v_today_date;

  -- Se já tiver registros de hoje, não processar novamente
  IF v_already_executed > 0 THEN
    RAISE NOTICE 'Já existem % registros para hoje. Abortando.', v_already_executed;
    RETURN;
  END IF;

  -- PROCESSAR E INSERIR AS 30 CAMPANHAS DO DIA (10+10+10)
  WITH base AS (
    SELECT
      campaign_id,
      date,
      spend,
      revenue_converted_revshare,
      (revenue_converted_revshare - spend) AS gross_profit,
      CASE WHEN spend > 0 THEN revenue_converted_revshare / spend ELSE 0 END AS roas
    FROM public.daily_campaign_metrics
    WHERE date >= current_date - interval '14 days'
  ),

  metrics AS (
    SELECT
      campaign_id,
      REGR_SLOPE(gross_profit, EXTRACT(EPOCH FROM date)) * 86400 AS profit_daily_trend,
      AVG(spend) AS avg_spend,
      AVG(roas) AS avg_roas
    FROM base
    GROUP BY campaign_id
    HAVING COUNT(*) >= 3 AND AVG(spend) > 20
  ),

  edges AS (
    SELECT DISTINCT ON (campaign_id)
      campaign_id,
      FIRST_VALUE(roas) OVER (PARTITION BY campaign_id ORDER BY date ASC) AS roas_initial,
      LAST_VALUE(roas) OVER (PARTITION BY campaign_id ORDER BY date ASC
        RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS roas_final
    FROM base
  ),

  calculated AS (
    SELECT
      m.campaign_id,
      m.avg_spend,
      m.avg_roas,
      m.profit_daily_trend,
      e.roas_initial,
      e.roas_final,
      CASE
        WHEN e.roas_initial > 0.1 THEN (e.roas_final - e.roas_initial) / e.roas_initial
        WHEN e.roas_initial <= 0.1 AND e.roas_final > 0.5 THEN 1.0
        ELSE 0
      END AS var_roas_pct
    FROM metrics m
    JOIN edges e USING (campaign_id)
    -- EXCLUSÃO DE ROTAÇÃO: Não mostrar campanhas destacadas nos últimos 5 dias
    WHERE m.campaign_id NOT IN (
      SELECT ch.campaign_id::text
      FROM campaign_highlights ch
      WHERE ch.highlighted_at >= v_exclude_date
    )
  ),

  -- EM ALTA: FALLBACK INTELIGENTE COM PRIORIDADE NO ROAS
  -- Prioridade 1: var≥15% + ROAS>1.7 (critério mais rigoroso)
  top_high_p1 AS (
    SELECT *, 'em_alta' as categoria, 1 as priority
    FROM calculated
    WHERE var_roas_pct >= 0.15 AND avg_roas > 1.7
    ORDER BY avg_roas DESC, var_roas_pct DESC
    LIMIT 10
  ),

  -- Prioridade 2: var≥15% + ROAS>1.5 (se não tiver 10)
  top_high_p2 AS (
    SELECT *, 'em_alta' as categoria, 2 as priority
    FROM calculated
    WHERE var_roas_pct >= 0.15 AND avg_roas > 1.5
      AND campaign_id NOT IN (SELECT campaign_id FROM top_high_p1)
    ORDER BY avg_roas DESC, var_roas_pct DESC
    LIMIT 10
  ),

  -- Prioridade 3: var≥10% + ROAS>1.5 (se ainda não tiver 10)
  top_high_p3 AS (
    SELECT *, 'em_alta' as categoria, 3 as priority
    FROM calculated
    WHERE var_roas_pct >= 0.10 AND avg_roas > 1.5
      AND campaign_id NOT IN (SELECT campaign_id FROM top_high_p1)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_high_p2)
    ORDER BY avg_roas DESC, var_roas_pct DESC
    LIMIT 10
  ),

  -- Prioridade 4: crescimento positivo + ROAS>1.7 (última tentativa)
  top_high_p4 AS (
    SELECT *, 'em_alta' as categoria, 4 as priority
    FROM calculated
    WHERE var_roas_pct > 0 AND avg_roas > 1.7
      AND campaign_id NOT IN (SELECT campaign_id FROM top_high_p1)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_high_p2)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_high_p3)
    ORDER BY avg_roas DESC, var_roas_pct DESC
    LIMIT 10
  ),

  -- COMBINAR TODOS OS NÍVEIS DE EM_ALTA E PEGAR AS 10 MELHORES
  top_high AS (
    SELECT campaign_id, avg_spend, avg_roas, profit_daily_trend,
           roas_initial, roas_final, var_roas_pct, categoria
    FROM (
      SELECT * FROM top_high_p1
      UNION ALL
      SELECT * FROM top_high_p2
      UNION ALL
      SELECT * FROM top_high_p3
      UNION ALL
      SELECT * FROM top_high_p4
    ) combined
    ORDER BY priority ASC, avg_roas DESC, var_roas_pct DESC
    LIMIT 10
  ),

  -- EM BAIXA: Mantém critério atual (10 campanhas)
  top_low AS (
    SELECT *, 'em_baixa' as categoria
    FROM calculated
    WHERE (var_roas_pct <= -0.15 OR (profit_daily_trend < -10 AND var_roas_pct < 0))
      AND avg_roas < 1.4
    ORDER BY var_roas_pct ASC
    LIMIT 10
  ),

  -- ESTAGNADA: Mantém critério atual (10 campanhas)
  top_stable AS (
    SELECT *, 'estagnada' as categoria
    FROM calculated
    WHERE campaign_id NOT IN (SELECT campaign_id FROM top_high)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_low)
      AND avg_roas >= 1.4 AND avg_roas <= 1.7
      AND roas_initial > 0.3
    ORDER BY ABS(var_roas_pct) ASC, avg_spend DESC
    LIMIT 10
  ),

  final_list AS (
    SELECT * FROM top_high
    UNION ALL
    SELECT * FROM top_low
    UNION ALL
    SELECT * FROM top_stable
  )

  -- INSERIR NA TABELA campaign_highlights
  INSERT INTO campaign_highlights (campaign_id, category, highlighted_at)
  SELECT
    fl.campaign_id::bigint,
    fl.categoria,
    v_today_date
  FROM final_list fl
  ON CONFLICT (campaign_id, category, highlighted_at) DO NOTHING;

  -- Contar quantos foram inseridos
  GET DIAGNOSTICS v_result_count = ROW_COUNT;

  RAISE NOTICE '✅ Inseridos % registros para %', v_result_count, v_today_date;

  -- Retornar resumo
  RETURN QUERY
  SELECT
    fl.campaign_id,
    COALESCE(c.campaign_name::text, 'Sem nome'::text) as campaign_name,
    fl.categoria,
    v_result_count as inserted_count
  FROM final_list fl
  LEFT JOIN campaigns c ON c.campaign_id = fl.campaign_id;

END;
$$;

COMMENT ON FUNCTION refresh_campaign_highlights IS 'Atualiza a tabela campaign_highlights com 30 campanhas (10+10+10). EM ALTA usa fallback inteligente priorizando ROAS. DEVE SER CHAMADA APENAS PELO CRON ÀS 6AM. Protegido contra múltiplas execuções no mesmo dia.';
