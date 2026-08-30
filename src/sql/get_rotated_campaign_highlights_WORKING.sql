-- FUNÇÃO FINAL BASEADA NO SQL QUE JÁ FUNCIONA
DROP FUNCTION IF EXISTS get_rotated_campaign_highlights();

CREATE OR REPLACE FUNCTION get_rotated_campaign_highlights()
RETURNS TABLE (
  campaign_id_out BIGINT,
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
BEGIN
  DROP TABLE IF EXISTS temp_highlights;

  CREATE TEMP TABLE temp_highlights (
    campaign_id BIGINT,
    status VARCHAR,
    avg_spend NUMERIC,
    roas_inicio NUMERIC,
    roas_fim NUMERIC,
    variacao_roas TEXT,
    motivo TEXT
  ) ON COMMIT DROP;

  -- SEU SQL QUE JÁ FUNCIONA + EXCLUSÃO DE ROTAÇÃO
  INSERT INTO temp_highlights
  WITH base AS (
    SELECT
      campaign_id,
      date,
      spend,
      revenue_converted_revshare,
      match_rate,
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

  tech_alert_list AS (
    SELECT
      m.campaign_id,
      ROUND(AVG(m.match_rate)::numeric, 1) AS current_match_rate
    FROM (
      SELECT
        campaign_id,
        match_rate,
        ROW_NUMBER() OVER (PARTITION BY campaign_id ORDER BY date DESC) as rn
      FROM base
    ) m
    JOIN public.campaigns c ON c.id::text = m.campaign_id::text
    JOIN public.projects p ON p.id = c.project_id
    WHERE m.rn <= 2
      AND p.project_type = 'GAM'
      -- EXCLUSÃO DE ROTAÇÃO
      AND m.campaign_id NOT IN (
        SELECT ch.campaign_id
        FROM campaign_highlights ch
        WHERE ch.highlighted_at >= v_exclude_date
          AND ch.category = 'alerta_tecnico'
      )
    GROUP BY m.campaign_id
    HAVING BOOL_AND(m.match_rate <= 70)
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
    WHERE m.campaign_id NOT IN (SELECT campaign_id FROM tech_alert_list)
      -- EXCLUSÃO DE ROTAÇÃO
      AND m.campaign_id NOT IN (
        SELECT ch.campaign_id
        FROM campaign_highlights ch
        WHERE ch.highlighted_at >= v_exclude_date
      )
  ),

  top_high AS (
    SELECT *, 'em_alta' as categoria
    FROM calculated
    WHERE var_roas_pct >= 0.15
    ORDER BY var_roas_pct DESC
    LIMIT 5
  ),

  top_low AS (
    SELECT *, 'em_baixa' as categoria
    FROM calculated
    WHERE var_roas_pct <= -0.15
       OR (profit_daily_trend < -10 AND var_roas_pct < 0)
    ORDER BY var_roas_pct ASC
    LIMIT 5
  ),

  top_stable AS (
    SELECT *, 'estagnada' as categoria
    FROM calculated
    WHERE campaign_id NOT IN (SELECT campaign_id FROM top_high)
      AND campaign_id NOT IN (SELECT campaign_id FROM top_low)
      AND roas_initial > 0.3
    ORDER BY ABS(var_roas_pct) ASC, avg_spend DESC
    LIMIT 5
  )

  SELECT
    campaign_id,
    categoria AS status,
    ROUND(avg_spend::numeric, 2) AS avg_spend,
    ROUND(roas_initial::numeric, 3) AS roas_inicio,
    ROUND(roas_final::numeric, 3) AS roas_fim,
    ROUND((var_roas_pct * 100)::numeric, 2) || '%' AS variacao_roas,
    CASE
      WHEN categoria = 'alerta_tecnico' THEN '🚨 URGENTE: GAM Match Rate Crítico (' || roas_initial || '%)'
      WHEN categoria = 'em_alta' AND roas_initial <= 0.1 THEN 'Escalar: Campanha Nova/Ramping Up'
      WHEN categoria = 'em_alta' THEN 'Escalar: Crescimento real de ' || ROUND((var_roas_pct * 100)::numeric, 1) || '%'
      WHEN categoria = 'em_baixa' THEN 'Atenção: Queda de ' || ROUND((var_roas_pct * 100)::numeric, 1) || '%'
      WHEN categoria = 'estagnada' THEN 'Lateral: Oscilou apenas ' || ROUND((var_roas_pct * 100)::numeric, 1) || '%'
    END AS motivo
  FROM (
    SELECT
      t.campaign_id,
      0::numeric as avg_spend,
      0::numeric as avg_roas,
      0::numeric as profit_daily_trend,
      t.current_match_rate as roas_initial,
      0::numeric as roas_final,
      0::numeric as var_roas_pct,
      'alerta_tecnico' as categoria
    FROM tech_alert_list t

    UNION ALL
    SELECT * FROM top_high
    UNION ALL
    SELECT * FROM top_low
    UNION ALL
    SELECT * FROM top_stable
  ) final_list
  ORDER BY
    CASE
      WHEN categoria = 'alerta_tecnico' THEN 0
      WHEN categoria = 'em_alta' THEN 1
      WHEN categoria = 'estagnada' THEN 2
      ELSE 3
    END,
    ABS(var_roas_pct) DESC;

  -- Contar e salvar
  SELECT COUNT(*) INTO v_result_count FROM temp_highlights;

  IF v_result_count > 0 THEN
    INSERT INTO campaign_highlights (campaign_id, category, highlighted_at)
    SELECT DISTINCT
      th.campaign_id,
      th.status,
      v_today_date
    FROM temp_highlights th
    ON CONFLICT (campaign_id, category, highlighted_at) DO NOTHING;
  END IF;

  -- Retornar resultados
  RETURN QUERY
  SELECT
    th.campaign_id,
    th.status,
    th.avg_spend,
    th.roas_inicio,
    th.roas_fim,
    th.variacao_roas,
    th.motivo
  FROM temp_highlights th
  ORDER BY
    CASE
      WHEN th.status = 'alerta_tecnico' THEN 0
      WHEN th.status = 'em_alta' THEN 1
      WHEN th.status = 'estagnada' THEN 2
      ELSE 3
    END,
    th.campaign_id;

END;
$$;

COMMENT ON FUNCTION get_rotated_campaign_highlights IS 'Retorna campanhas destacadas com rotação de 5 dias';
