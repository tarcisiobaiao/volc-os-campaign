-- FUNÇÃO QUE ATUALIZA A TABELA campaign_highlights COM FALLBACK INTELIGENTE
-- ⚠️ DEVE SER CHAMADA APENAS PELO CRON ÀS 6AM
-- Esta função seleciona as 30 campanhas do dia (10+10+10) e salva na tabela
--
-- PERÍODO ANALISADO: 14 dias ATÉ O DIA ANTERIOR (D-1)
--   Exemplo: Se hoje é 13/12, analisa de 29/11 até 12/12
--   Motivo: Roda às 6AM quando dados do dia atual ainda não estão consolidados
--
-- CÁLCULO DA VARIAÇÃO %:
--   var_roas_pct = (ROAS_final - ROAS_inicial) / ROAS_inicial
--   Exemplo: ROAS 1.86 → 2.81 = (2.81 - 1.86) / 1.86 = 0.5107 = 51.07%
--
-- REGRAS DE SELEÇÃO (baseado em 14 dias de dados):
--
-- EM ALTA (10 campanhas): Prioriza ROAS alto + crescimento
--   1º: var≥15% + ROAS>1.7 (critério ideal)
--   2º: var≥15% + ROAS>1.5 (fallback)
--   3º: var≥10% + ROAS>1.5 (fallback)
--   4º: crescimento positivo + ROAS>1.7 (fallback final)
--
-- EM BAIXA (10 campanhas): Prioriza pior ROAS
--   1º: var≤-15% OU (tendência negativa E var<0) E ROAS<1.4 (critério ideal)
--   2º: ROAS<1.4 E var<0 (fallback)
--   3º: ROAS<1.0 (fallback final)
--
-- ESTAGNADA (10 campanhas): Prioriza ROAS médio estável
--   1º: ROAS entre 1.4 e 1.7 E roas_inicial>0.3 (critério ideal)
--   2º: ROAS entre 1.4 e 1.8 (fallback)
--   3º: ROAS≥1.2 (fallback final)
--
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
  -- ⚠️ USA DADOS ATÉ DIA ANTERIOR (D-1) pois roda às 6AM antes de dados consolidados
  WITH base AS (
    SELECT
      campaign_id,
      date,
      spend,
      revenue_converted_revshare,
      (revenue_converted_revshare - spend) AS gross_profit,
      CASE WHEN spend > 0 THEN revenue_converted_revshare / spend ELSE 0 END AS roas
    FROM public.daily_campaign_metrics
    WHERE date >= (current_date - interval '1 day') - interval '14 days'
      AND date <= current_date - interval '1 day'
  ),

  metrics AS (
    SELECT
      campaign_id,
      REGR_SLOPE(gross_profit, EXTRACT(EPOCH FROM date)) * 86400 AS profit_daily_trend,
      AVG(spend) AS avg_spend,
      SUM(revenue_converted_revshare) / NULLIF(SUM(spend), 0) AS avg_roas
    FROM base
    GROUP BY campaign_id
    HAVING COUNT(*) >= 3 AND AVG(spend) > 20
  ),

  edges AS (
    SELECT DISTINCT ON (campaign_id)
      campaign_id,
      FIRST_VALUE(roas) OVER (PARTITION BY campaign_id ORDER BY date ASC) AS roas_initial,
      FIRST_VALUE(spend) OVER (PARTITION BY campaign_id ORDER BY date ASC) AS spend_initial,
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
      e.spend_initial,
      CASE
        WHEN e.roas_initial > 0.1 THEN (e.roas_final - e.roas_initial) / e.roas_initial
        WHEN e.roas_initial <= 0.1 AND e.roas_final > 0.5 THEN 1.0
        ELSE 0
      END AS var_roas_pct
    FROM metrics m
    JOIN edges e USING (campaign_id)
    WHERE m.campaign_id NOT IN (
      SELECT ch.campaign_id::text
      FROM campaign_highlights ch
      WHERE ch.highlighted_at >= v_exclude_date
    )
    AND e.spend_initial >= 20
  ),

  -- Pool SEM regra de 5 dias (para fallback final)
  calculated_all AS (
    SELECT
      m.campaign_id,
      m.avg_spend,
      m.avg_roas,
      m.profit_daily_trend,
      e.roas_initial,
      e.roas_final,
      e.spend_initial,
      CASE
        WHEN e.roas_initial > 0.1 THEN (e.roas_final - e.roas_initial) / e.roas_initial
        WHEN e.roas_initial <= 0.1 AND e.roas_final > 0.5 THEN 1.0
        ELSE 0
      END AS var_roas_pct
    FROM metrics m
    JOIN edges e USING (campaign_id)
    WHERE e.spend_initial >= 20
  ),

  -- ========================================
  -- EM ALTA: FALLBACK INTELIGENTE (prioriza ROAS)
  -- ========================================
  top_high_p1 AS (
    SELECT *, 'em_alta' as categoria, 1 as priority
    FROM calculated
    WHERE var_roas_pct >= 0.15 AND avg_roas > 1.7
    ORDER BY avg_roas DESC, var_roas_pct DESC
    LIMIT 10
  ),
  top_high_p2 AS (
    SELECT *, 'em_alta' as categoria, 2 as priority
    FROM calculated
    WHERE var_roas_pct >= 0.15 AND avg_roas > 1.5
      AND campaign_id NOT IN (SELECT campaign_id FROM top_high_p1)
    ORDER BY avg_roas DESC, var_roas_pct DESC
    LIMIT 10
  ),
  top_high_p3 AS (
    SELECT *, 'em_alta' as categoria, 3 as priority
    FROM calculated
    WHERE var_roas_pct >= 0.10 AND avg_roas > 1.5
      AND campaign_id NOT IN (SELECT campaign_id FROM top_high_p1)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_high_p2)
    ORDER BY avg_roas DESC, var_roas_pct DESC
    LIMIT 10
  ),
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
  top_high_p5 AS (
    SELECT *, 'em_alta' as categoria, 5 as priority
    FROM calculated_all
    WHERE var_roas_pct > 0 AND avg_roas > 1.5
      AND campaign_id NOT IN (SELECT campaign_id FROM top_high_p1)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_high_p2)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_high_p3)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_high_p4)
    ORDER BY avg_roas DESC, var_roas_pct DESC
    LIMIT 10
  ),
  top_high AS (
    SELECT campaign_id, avg_spend, avg_roas, profit_daily_trend,
           roas_initial, roas_final, var_roas_pct, categoria, priority
    FROM (
      SELECT * FROM top_high_p1
      UNION ALL SELECT * FROM top_high_p2
      UNION ALL SELECT * FROM top_high_p3
      UNION ALL SELECT * FROM top_high_p4
      UNION ALL SELECT * FROM top_high_p5
    ) combined
    ORDER BY priority ASC, avg_roas DESC, var_roas_pct DESC
    LIMIT 10
  ),

  -- ========================================
  -- EM BAIXA: FALLBACK (prioriza pior ROAS)
  -- ========================================
  top_low_p1 AS (
    SELECT *, 'em_baixa' as categoria, 1 as priority
    FROM calculated
    WHERE (var_roas_pct <= -0.15 OR (profit_daily_trend < -10 AND var_roas_pct < 0))
      AND avg_roas < 1.4
    ORDER BY avg_roas ASC, var_roas_pct ASC
    LIMIT 10
  ),
  top_low_p2 AS (
    SELECT *, 'em_baixa' as categoria, 2 as priority
    FROM calculated
    WHERE avg_roas < 1.4 AND var_roas_pct < 0
      AND campaign_id NOT IN (SELECT campaign_id FROM top_low_p1)
    ORDER BY avg_roas ASC, var_roas_pct ASC
    LIMIT 10
  ),
  top_low_p3 AS (
    SELECT *, 'em_baixa' as categoria, 3 as priority
    FROM calculated
    WHERE avg_roas < 1.0
      AND campaign_id NOT IN (SELECT campaign_id FROM top_low_p1)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_low_p2)
    ORDER BY avg_roas ASC
    LIMIT 10
  ),
  top_low_p4 AS (
    SELECT *, 'em_baixa' as categoria, 4 as priority
    FROM calculated_all
    WHERE avg_roas < 1.5
      AND campaign_id NOT IN (SELECT campaign_id FROM top_low_p1)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_low_p2)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_low_p3)
    ORDER BY avg_roas ASC
    LIMIT 10
  ),
  top_low AS (
    SELECT campaign_id, avg_spend, avg_roas, profit_daily_trend,
           roas_initial, roas_final, var_roas_pct, categoria, priority
    FROM (
      SELECT * FROM top_low_p1
      UNION ALL SELECT * FROM top_low_p2
      UNION ALL SELECT * FROM top_low_p3
      UNION ALL SELECT * FROM top_low_p4
    ) combined
    ORDER BY priority ASC, avg_roas ASC
    LIMIT 10
  ),

  -- ========================================
  -- ESTAGNADA: FALLBACK (prioriza ROAS médio estável)
  -- ========================================
  top_stable_p1 AS (
    SELECT *, 'estagnada' as categoria, 1 as priority
    FROM calculated
    WHERE campaign_id NOT IN (SELECT campaign_id FROM top_high)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_low)
      AND avg_roas >= 1.4 AND avg_roas <= 1.7
      AND roas_initial > 0.3
    ORDER BY ABS(var_roas_pct) ASC, avg_spend DESC
    LIMIT 10
  ),
  top_stable_p2 AS (
    SELECT *, 'estagnada' as categoria, 2 as priority
    FROM calculated
    WHERE campaign_id NOT IN (SELECT campaign_id FROM top_high)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_low)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_stable_p1)
      AND avg_roas >= 1.4 AND avg_roas <= 1.8
    ORDER BY ABS(var_roas_pct) ASC, avg_spend DESC
    LIMIT 10
  ),
  top_stable_p3 AS (
    SELECT *, 'estagnada' as categoria, 3 as priority
    FROM calculated
    WHERE campaign_id NOT IN (SELECT campaign_id FROM top_high)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_low)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_stable_p1)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_stable_p2)
      AND avg_roas >= 1.2
    ORDER BY ABS(var_roas_pct) ASC, avg_roas DESC
    LIMIT 10
  ),
  top_stable_p4 AS (
    SELECT *, 'estagnada' as categoria, 4 as priority
    FROM calculated_all
    WHERE campaign_id NOT IN (SELECT campaign_id FROM top_high)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_low)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_stable_p1)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_stable_p2)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_stable_p3)
      AND avg_roas >= 1.0
    ORDER BY ABS(var_roas_pct) ASC, avg_roas DESC
    LIMIT 10
  ),
  top_stable AS (
    SELECT campaign_id, avg_spend, avg_roas, profit_daily_trend,
           roas_initial, roas_final, var_roas_pct, categoria, priority
    FROM (
      SELECT * FROM top_stable_p1
      UNION ALL SELECT * FROM top_stable_p2
      UNION ALL SELECT * FROM top_stable_p3
      UNION ALL SELECT * FROM top_stable_p4
    ) combined
    ORDER BY priority ASC, ABS(var_roas_pct) ASC
    LIMIT 10
  ),

  final_list AS (
    SELECT campaign_id, categoria, priority,
           ROW_NUMBER() OVER (PARTITION BY categoria ORDER BY priority ASC) as display_order
    FROM (
      SELECT campaign_id, categoria, priority FROM top_high
      UNION ALL
      SELECT campaign_id, categoria, priority FROM top_low
      UNION ALL
      SELECT campaign_id, categoria, priority FROM top_stable
    ) combined
  )

  -- INSERIR DIRETAMENTE NA TABELA campaign_highlights COM ORDEM
  INSERT INTO campaign_highlights (campaign_id, category, highlighted_at, display_order)
  SELECT
    campaign_id::bigint,
    categoria,
    v_today_date,
    display_order
  FROM final_list
  ON CONFLICT (campaign_id, category, highlighted_at) DO UPDATE
  SET display_order = EXCLUDED.display_order;

  -- Contar quantos foram inseridos
  GET DIAGNOSTICS v_result_count = ROW_COUNT;

  RAISE NOTICE '✅ Inseridos % registros para %', v_result_count, v_today_date;

  -- Retornar resumo usando campaign_highlights inserido
  RETURN QUERY
  SELECT
    ch.campaign_id::text,
    COALESCE(c.campaign_name::text, 'Sem nome'::text) as campaign_name,
    ch.category,
    v_result_count as inserted_count
  FROM campaign_highlights ch
  LEFT JOIN campaigns c ON c.campaign_id::text = ch.campaign_id::text
  WHERE ch.highlighted_at = v_today_date
  ORDER BY
    CASE ch.category
      WHEN 'em_alta' THEN 1
      WHEN 'estagnada' THEN 2
      WHEN 'em_baixa' THEN 3
    END,
    ch.display_order;

END;
$$;

COMMENT ON FUNCTION refresh_campaign_highlights IS 'Atualiza campaign_highlights com 30 campanhas (10+10+10). Todas as categorias têm fallback inteligente priorizando ROAS. DEVE SER CHAMADA APENAS PELO CRON ÀS 6AM. Protegido contra múltiplas execuções no mesmo dia.';
