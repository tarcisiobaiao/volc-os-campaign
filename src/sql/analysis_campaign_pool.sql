-- ANÁLISE COMPLETA DO POOL DE CAMPANHAS DISPONÍVEIS
-- Verificar quantas campanhas temos e como se distribuem

-- 1. Total de campanhas com dados nos últimos 14 dias
SELECT
  'Total campanhas com dados (14 dias)' as metrica,
  COUNT(DISTINCT campaign_id) as quantidade
FROM daily_campaign_metrics
WHERE date >= current_date - interval '14 days';

-- 2. Campanhas que atendem critérios mínimos (gasto > 20, pelo menos 3 dias de dados)
WITH base AS (
  SELECT
    campaign_id,
    date,
    spend,
    revenue_converted_revshare,
    CASE WHEN spend > 0 THEN revenue_converted_revshare / spend ELSE 0 END AS roas
  FROM public.daily_campaign_metrics
  WHERE date >= current_date - interval '14 days'
),
metrics AS (
  SELECT
    campaign_id,
    AVG(spend) AS avg_spend,
    AVG(roas) AS avg_roas,
    COUNT(*) as dias_com_dados
  FROM base
  GROUP BY campaign_id
  HAVING COUNT(*) >= 3 AND AVG(spend) > 20
)
SELECT
  'Campanhas que atendem critérios mínimos (>=3 dias, gasto>20)' as metrica,
  COUNT(*) as quantidade
FROM metrics;

-- 3. Distribuição por faixa de ROAS médio
WITH base AS (
  SELECT
    campaign_id,
    date,
    spend,
    revenue_converted_revshare,
    CASE WHEN spend > 0 THEN revenue_converted_revshare / spend ELSE 0 END AS roas
  FROM public.daily_campaign_metrics
  WHERE date >= current_date - interval '14 days'
),
metrics AS (
  SELECT
    campaign_id,
    AVG(spend) AS avg_spend,
    AVG(roas) AS avg_roas
  FROM base
  GROUP BY campaign_id
  HAVING COUNT(*) >= 3 AND AVG(spend) > 20
)
SELECT
  CASE
    WHEN avg_roas < 1.0 THEN '< 1.0 (muito ruim)'
    WHEN avg_roas >= 1.0 AND avg_roas < 1.4 THEN '1.0-1.4 (ruim)'
    WHEN avg_roas >= 1.4 AND avg_roas < 1.7 THEN '1.4-1.7 (médio)'
    WHEN avg_roas >= 1.7 AND avg_roas < 2.0 THEN '1.7-2.0 (bom)'
    ELSE '>= 2.0 (excelente)'
  END as faixa_roas,
  COUNT(*) as quantidade_campanhas
FROM metrics
GROUP BY
  CASE
    WHEN avg_roas < 1.0 THEN '< 1.0 (muito ruim)'
    WHEN avg_roas >= 1.0 AND avg_roas < 1.4 THEN '1.0-1.4 (ruim)'
    WHEN avg_roas >= 1.4 AND avg_roas < 1.7 THEN '1.4-1.7 (médio)'
    WHEN avg_roas >= 1.7 AND avg_roas < 2.0 THEN '1.7-2.0 (bom)'
    ELSE '>= 2.0 (excelente)'
  END
ORDER BY MIN(avg_roas);

-- 4. Campanhas com crescimento >= 15% (independente do ROAS)
WITH base AS (
  SELECT
    campaign_id,
    date,
    spend,
    revenue_converted_revshare,
    CASE WHEN spend > 0 THEN revenue_converted_revshare / spend ELSE 0 END AS roas
  FROM public.daily_campaign_metrics
  WHERE date >= current_date - interval '14 days'
),
metrics AS (
  SELECT
    campaign_id,
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
  'Campanhas com variação >= 15% (qualquer ROAS)' as metrica,
  COUNT(*) as quantidade
FROM calculated
WHERE var_roas_pct >= 0.15;

-- 5. Campanhas excluídas pela rotação (últimos 5 dias)
SELECT
  'Campanhas em cooldown (últimos 5 dias)' as metrica,
  COUNT(DISTINCT campaign_id) as quantidade
FROM campaign_highlights
WHERE highlighted_at >= current_date - interval '5 days';

-- 6. Verificar o que foi inserido HOJE
SELECT
  'Campanhas inseridas HOJE (12/12/2025)' as metrica,
  COUNT(*) as quantidade
FROM campaign_highlights
WHERE highlighted_at = current_date;

-- 7. Distribuição das campanhas inseridas hoje por categoria
SELECT
  category,
  COUNT(*) as quantidade
FROM campaign_highlights
WHERE highlighted_at = current_date
GROUP BY category
ORDER BY category;
