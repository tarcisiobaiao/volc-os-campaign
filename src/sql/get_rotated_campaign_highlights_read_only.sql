-- FUNÇÃO QUE APENAS LÊ AS CAMPANHAS DESTACADAS DO DIA
-- ⚠️ NÃO INSERE NADA NA TABELA - APENAS LÊ
-- Pode ser chamada quantas vezes necessário (ex: ao acessar a home)

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
BEGIN
  -- APENAS LER da tabela campaign_highlights para o dia de hoje
  -- E calcular métricas reais de daily_campaign_metrics

  RETURN QUERY
  WITH today_highlights AS (
    SELECT ch.campaign_id::text as campaign_id, ch.category, ch.display_order
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
    WHERE date >= (current_date - interval '1 day') - interval '14 days'
      AND date <= current_date - interval '1 day'
      AND campaign_id IN (SELECT campaign_id FROM today_highlights)
  ),
  metrics AS (
    SELECT
      campaign_id,
      AVG(spend) AS avg_spend,
      SUM(revenue_converted_revshare) / NULLIF(SUM(spend), 0) AS avg_roas
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
      WHEN th.category = 'em_alta' AND calc.roas_initial <= 0.1 THEN 'Escalar: Campanha Nova/Ramping Up'
      WHEN th.category = 'em_alta' THEN 'Escalar: +' || ROUND((calc.var_roas_pct * 100)::numeric, 1) || '%'
      WHEN th.category = 'em_baixa' THEN 'Atenção: ' || ROUND((calc.var_roas_pct * 100)::numeric, 1) || '%'
      WHEN th.category = 'estagnada' THEN 'Estável: ' || ROUND((calc.var_roas_pct * 100)::numeric, 1) || '%'
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
    COALESCE(th.display_order, 999),  -- Ordem de prioridade (menores primeiro)
    th.campaign_id
  LIMIT 30;

END;
$$;

COMMENT ON FUNCTION get_rotated_campaign_highlights IS 'Retorna campanhas destacadas do dia. APENAS LÊ da tabela campaign_highlights - NÃO insere nada. Pode ser chamada quantas vezes necessário.';
