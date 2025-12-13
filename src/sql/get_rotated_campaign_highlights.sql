-- VERSÃO FINAL FUNCIONANDO COM PROTEÇÃO CONTRA MÚLTIPLAS EXECUÇÕES
-- Retorna campanhas destacadas com rotação de 5 dias
-- Esta função salva automaticamente na tabela campaign_highlights
-- E evita salvar múltiplas vezes no mesmo dia
--
-- REGRAS DE SELEÇÃO (baseado em 14 dias de dados):
-- EM ALTA: variação ≥ +15% E ROAS médio > 1.7
-- ESTAGNADA: ROAS médio entre 1.4 e 1.7
-- EM BAIXA: variação ≤ -15% (ou tendência de queda) E ROAS médio < 1.4

DROP FUNCTION IF EXISTS get_rotated_campaign_highlights();

CREATE OR REPLACE FUNCTION get_rotated_campaign_highlights()
RETURNS TABLE (
  campaign_id_out TEXT,
  campaign_name_out TEXT,
  status_out VARCHAR,
  avg_spend_out NUMERIC,
  roas_inicio_out NUMERIC,
  roas_fim_out NUMERIC,
  variacao_roas_out TEXT,
  motivo_out TEXT
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

  -- Se já tiver 15 registros de hoje, retornar os existentes com dados reais
  IF v_already_executed >= 15 THEN
    RAISE NOTICE 'Função já foi executada hoje. Retornando registros existentes com métricas atualizadas.';

    RETURN QUERY
    WITH today_highlights AS (
      SELECT ch.campaign_id::text as campaign_id, ch.category
      FROM campaign_highlights ch
      WHERE ch.highlighted_at = v_today_date
    ),
    base AS (
      SELECT
        campaign_id,
        date,
        spend,
        revenue_converted_revshare,
        (revenue_converted_revshare - spend) AS gross_profit,
        CASE WHEN spend > 0 THEN revenue_converted_revshare / spend ELSE 0 END AS roas
      FROM public.daily_campaign_metrics
      WHERE date >= current_date - interval '14 days'
        AND campaign_id IN (SELECT campaign_id FROM today_highlights)
    ),
    metrics AS (
      SELECT
        campaign_id,
        AVG(spend) AS avg_spend,
        AVG(roas) AS avg_roas
      FROM base
      GROUP BY campaign_id
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
        e.roas_initial,
        e.roas_final,
        CASE
          WHEN e.roas_initial > 0.1 THEN (e.roas_final - e.roas_initial) / e.roas_initial
          WHEN e.roas_initial <= 0.1 AND e.roas_final > 0.5 THEN 1.0
          ELSE 0
        END AS var_roas_pct
      FROM metrics m
      JOIN edges e USING (campaign_id)
    )
    SELECT
      th.campaign_id,
      COALESCE(c.campaign_name::text, 'Sem nome'::text) as campaign_name,
      th.category,
      COALESCE(ROUND(calc.avg_spend::numeric, 2), 0::numeric) as avg_spend,
      COALESCE(ROUND(calc.roas_initial::numeric, 3), 0::numeric) as roas_inicio,
      COALESCE(ROUND(calc.roas_final::numeric, 3), 0::numeric) as roas_fim,
      COALESCE(ROUND((calc.var_roas_pct * 100)::numeric, 2) || '%', '0%') as variacao_roas,
      CASE
        WHEN th.category = 'em_alta' AND calc.roas_initial <= 0.1 THEN 'Escalar: Campanha Nova/Ramping Up (ROAS médio: ' || ROUND(calc.avg_roas::numeric, 2) || ')'
        WHEN th.category = 'em_alta' THEN 'Escalar: +' || ROUND((calc.var_roas_pct * 100)::numeric, 1) || '% | ROAS médio: ' || ROUND(calc.avg_roas::numeric, 2)
        WHEN th.category = 'em_baixa' THEN 'Atenção: ' || ROUND((calc.var_roas_pct * 100)::numeric, 1) || '% | ROAS médio: ' || ROUND(calc.avg_roas::numeric, 2)
        WHEN th.category = 'estagnada' THEN 'Estável: ' || ROUND((calc.var_roas_pct * 100)::numeric, 1) || '% | ROAS médio: ' || ROUND(calc.avg_roas::numeric, 2)
        ELSE 'Sem dados'
      END as motivo
    FROM today_highlights th
    LEFT JOIN campaigns c ON c.campaign_id = th.campaign_id
    LEFT JOIN calculated calc ON calc.campaign_id = th.campaign_id
    ORDER BY
      CASE
        WHEN th.category = 'alerta_tecnico' THEN 0
        WHEN th.category = 'em_alta' THEN 1
        WHEN th.category = 'estagnada' THEN 2
        ELSE 3
      END,
      th.campaign_id
    LIMIT 15;

    RETURN;
  END IF;

  DROP TABLE IF EXISTS temp_highlights;

  CREATE TEMP TABLE temp_highlights (
    campaign_id TEXT,
    campaign_name TEXT,
    status VARCHAR,
    avg_spend NUMERIC,
    roas_inicio NUMERIC,
    roas_fim NUMERIC,
    variacao_roas TEXT,
    motivo TEXT
  ) ON COMMIT DROP;

  -- INSERE RESULTADOS EXCLUINDO CAMPANHAS DESTACADAS NOS ÚLTIMOS 5 DIAS
  INSERT INTO temp_highlights
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

  top_high AS (
    SELECT *, 'em_alta' as categoria
    FROM calculated
    WHERE var_roas_pct >= 0.15
      AND avg_roas > 1.7  -- Média de ROAS acima de 1.7 para escalar
    ORDER BY var_roas_pct DESC
    LIMIT 5
  ),

  top_low AS (
    SELECT *, 'em_baixa' as categoria
    FROM calculated
    WHERE (var_roas_pct <= -0.15 OR (profit_daily_trend < -10 AND var_roas_pct < 0))
      AND avg_roas < 1.4  -- Média de ROAS abaixo de 1.4 = alerta
    ORDER BY var_roas_pct ASC
    LIMIT 5
  ),

  top_stable AS (
    SELECT *, 'estagnada' as categoria
    FROM calculated
    WHERE campaign_id NOT IN (SELECT campaign_id FROM top_high)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_low)
      AND avg_roas >= 1.4 AND avg_roas <= 1.7  -- Média de ROAS entre 1.4 e 1.7
      AND roas_initial > 0.3
    ORDER BY ABS(var_roas_pct) ASC, avg_spend DESC
    LIMIT 5
  )

  SELECT
    final_list.campaign_id,
    COALESCE(c.campaign_name::text, 'Sem nome'::text) AS campaign_name,
    final_list.categoria AS status,
    ROUND(final_list.avg_spend::numeric, 2) AS avg_spend,
    ROUND(final_list.roas_initial::numeric, 3) AS roas_inicio,
    ROUND(final_list.roas_final::numeric, 3) AS roas_fim,
    ROUND((final_list.var_roas_pct * 100)::numeric, 2) || '%' AS variacao_roas,
    CASE
      WHEN final_list.categoria = 'em_alta' AND final_list.roas_initial <= 0.1 THEN 'Escalar: Campanha Nova/Ramping Up (ROAS médio: ' || ROUND(final_list.avg_roas::numeric, 2) || ')'
      WHEN final_list.categoria = 'em_alta' THEN 'Escalar: +' || ROUND((final_list.var_roas_pct * 100)::numeric, 1) || '% | ROAS médio: ' || ROUND(final_list.avg_roas::numeric, 2)
      WHEN final_list.categoria = 'em_baixa' THEN 'Atenção: ' || ROUND((final_list.var_roas_pct * 100)::numeric, 1) || '% | ROAS médio: ' || ROUND(final_list.avg_roas::numeric, 2)
      WHEN final_list.categoria = 'estagnada' THEN 'Estável: ' || ROUND((final_list.var_roas_pct * 100)::numeric, 1) || '% | ROAS médio: ' || ROUND(final_list.avg_roas::numeric, 2)
    END AS motivo
  FROM (
    SELECT * FROM top_high
    UNION ALL
    SELECT * FROM top_low
    UNION ALL
    SELECT * FROM top_stable
  ) final_list
  LEFT JOIN campaigns c ON c.campaign_id = final_list.campaign_id
  ORDER BY
    CASE
      WHEN final_list.categoria = 'em_alta' THEN 1
      WHEN final_list.categoria = 'estagnada' THEN 2
      ELSE 3
    END,
    ABS(final_list.var_roas_pct) DESC;

  -- Contar resultados
  SELECT COUNT(*) INTO v_result_count FROM temp_highlights;

  -- SALVAR AUTOMATICAMENTE NA TABELA campaign_highlights
  IF v_result_count > 0 THEN
    INSERT INTO campaign_highlights (campaign_id, category, highlighted_at)
    SELECT DISTINCT
      th.campaign_id::bigint,
      th.status,
      v_today_date
    FROM temp_highlights th
    ON CONFLICT (campaign_id, category, highlighted_at) DO NOTHING;
  END IF;

  -- RETORNAR RESULTADOS
  RETURN QUERY
  SELECT
    th.campaign_id,
    th.campaign_name,
    th.status,
    th.avg_spend,
    th.roas_inicio,
    th.roas_fim,
    th.variacao_roas,
    th.motivo
  FROM temp_highlights th
  ORDER BY
    CASE
      WHEN th.status = 'em_alta' THEN 1
      WHEN th.status = 'estagnada' THEN 2
      ELSE 3
    END,
    th.campaign_id;

END;
$$;

COMMENT ON FUNCTION get_rotated_campaign_highlights IS 'Retorna campanhas destacadas com rotação de 5 dias. REGRAS: Em Alta (var≥15% + ROAS médio>1.7), Estagnada (ROAS médio 1.4-1.7), Em Baixa (var≤-15% + ROAS médio<1.4). Protegido contra múltiplas execuções.';
