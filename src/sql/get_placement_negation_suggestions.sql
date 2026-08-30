-- Placement Negation Suggestions
-- Returns placements with consistently negative ROI across time windows.
-- Two-crivo gate: 3+ negative windows AND ROAS declined ≥10% vs start of period.
-- Minimum: 3 days of data, R$ 15 total spend.
--
-- Note: uses LANGUAGE sql (not plpgsql) to avoid PL/pgSQL name-ambiguity between
-- RETURNS TABLE columns (canal, categoria) and identically-named CTE columns.
-- Internal CTE columns are prefixed with _ to prevent the conflict.

CREATE OR REPLACE FUNCTION get_placement_negation_suggestions(p_campaign_id TEXT)
RETURNS TABLE (
  canal          TEXT,
  categoria      TEXT,
  roas_1d        NUMERIC,
  roas_3d        NUMERIC,
  roas_7d        NUMERIC,
  roas_14d       NUMERIC,
  var_roas_pct   NUMERIC,
  motivo         TEXT
)
LANGUAGE sql
STABLE
SECURITY INVOKER
AS $$
  WITH base AS (
    SELECT
      v.canal   AS _canal,
      v.date    AS _date,
      v.roas_pct,
      v.investido_brl
    FROM vw_display_roi v
    WHERE v.campaign_id = p_campaign_id
      AND v.date >= CURRENT_DATE - INTERVAL '14 days'
      AND v.date < CURRENT_DATE  -- exclude today (partial day)
  ),

  eligible AS (
    -- Minimum data gate: 3+ days, R$15+ spend
    SELECT _canal
    FROM base
    GROUP BY _canal
    HAVING COUNT(DISTINCT _date) >= 3
       AND SUM(investido_brl) >= 15
  ),

  windowed AS (
    SELECT
      b._canal,
      AVG(CASE WHEN b._date = CURRENT_DATE - 1                                     THEN b.roas_pct END) AS roas_1d,
      AVG(CASE WHEN b._date >= CURRENT_DATE - 3                                    THEN b.roas_pct END) AS roas_3d,
      AVG(CASE WHEN b._date >= CURRENT_DATE - 7                                    THEN b.roas_pct END) AS roas_7d,
      AVG(b.roas_pct)                                                                                    AS roas_14d,
      -- Trend: first 3 days in window vs last 3 days
      AVG(CASE WHEN b._date BETWEEN CURRENT_DATE - 14 AND CURRENT_DATE - 12       THEN b.roas_pct END) AS roas_inicio,
      AVG(CASE WHEN b._date >= CURRENT_DATE - 3                                    THEN b.roas_pct END) AS roas_fim -- intentionally equals roas_3d: last 3 days serve as both window and end-of-period for trend
    FROM base b
    JOIN eligible e ON e._canal = b._canal
    GROUP BY b._canal
  ),

  scored AS (
    SELECT
      w.*,
      CASE
        WHEN w.roas_inicio IS NOT NULL AND w.roas_inicio != 0
        THEN (w.roas_fim - w.roas_inicio) / ABS(w.roas_inicio)
        ELSE NULL
      END AS var_roas,
      (CASE WHEN w.roas_1d  < 0 THEN 1 ELSE 0 END +
       CASE WHEN w.roas_3d  < 0 THEN 1 ELSE 0 END +
       CASE WHEN w.roas_7d  < 0 THEN 1 ELSE 0 END +
       CASE WHEN w.roas_14d < 0 THEN 1 ELSE 0 END) AS windows_neg
    FROM windowed w
  ),

  classified AS (
    SELECT
      s.*,
      CASE
        WHEN s.windows_neg >= 3 AND COALESCE(s.var_roas, 0) <= -0.10 THEN 'NEGATIVAR' -- NULL trend (no early data) treated as 0: conservative, requires windows_neg=4 to block
        WHEN s.windows_neg = 4                                         THEN 'NEGATIVAR'
        WHEN s.windows_neg >= 2 AND COALESCE(s.var_roas, 0) <= -0.10  THEN 'OBSERVAR'
        WHEN s.windows_neg = 3                                         THEN 'OBSERVAR'
        ELSE NULL
      END AS _categoria
    FROM scored s
  )

  SELECT
    c._canal::TEXT,
    c._categoria::TEXT,
    ROUND(c.roas_1d::NUMERIC,  1),
    ROUND(c.roas_3d::NUMERIC,  1),
    ROUND(c.roas_7d::NUMERIC,  1),
    ROUND(c.roas_14d::NUMERIC, 1),
    ROUND(c.var_roas::NUMERIC, 3),
    CASE
      WHEN c._categoria = 'NEGATIVAR' THEN
        'Negativo em ' || c.windows_neg || ' de 4 janelas' ||
        CASE WHEN c.var_roas IS NOT NULL
             THEN ', ROAS caiu ' || ROUND((ABS(c.var_roas) * 100)::NUMERIC, 1) || '% no período'
             ELSE '' END
      WHEN c._categoria = 'OBSERVAR' THEN
        'Negativo em ' || c.windows_neg || ' de 4 janelas' ||
        CASE WHEN c.var_roas IS NOT NULL
             THEN ', queda de ' || ROUND((ABS(c.var_roas) * 100)::NUMERIC, 1) || '% — aguardar mais dados'
             ELSE ' — aguardar mais dados' END
    END::TEXT
  FROM classified c
  WHERE c._categoria IS NOT NULL
  ORDER BY
    CASE c._categoria WHEN 'NEGATIVAR' THEN 0 ELSE 1 END,
    c.var_roas ASC NULLS LAST;
$$;
