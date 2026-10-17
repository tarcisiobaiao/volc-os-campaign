\set ON_ERROR_STOP 1
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
-- reconciliação: earnings USD × cotação efetiva = revenue BRL (sem identificadores)
SELECT 'jm' fonte, j.date, j.revenue usd,
       (SELECT h.rate FROM exchange_rate_history h WHERE h.effective_date <= j.date ORDER BY effective_date DESC, created_at DESC LIMIT 1) taxa_hist,
       round(j.revenue * (SELECT h.rate FROM exchange_rate_history h WHERE h.effective_date <= j.date ORDER BY effective_date DESC, created_at DESC LIMIT 1), 6) calc_brl,
       j.revenue_converted persistido_brl, j.updated_at
  FROM joinads_metrics j WHERE j.revenue > 0 ORDER BY j.date DESC, j.updated_at DESC LIMIT 3;
SELECT 'dcm' fonte, d.date, d.revenue usd, (SELECT CAST(value AS numeric) FROM system_settings WHERE key='dollar_exchange_rate') taxa_atual,
       round(d.revenue * (SELECT CAST(value AS numeric) FROM system_settings WHERE key='dollar_exchange_rate'), 6) calc_brl, d.revenue_converted persistido_brl
  FROM daily_campaign_metrics d WHERE d.revenue > 0 ORDER BY d.date DESC LIMIT 3;
SELECT 'v2_vs_jm' fonte, o.metric_date, sum(o.revenue_gross) v2_usd_gross, sum(o.revenue_client) v2_usd_client,
       (SELECT sum(revenue) FROM joinads_metrics j WHERE j.date=o.metric_date) legado_usd
  FROM joinads_observation o WHERE o.endpoint='key_value_campaign_adunit' AND o.metric_date >= current_date - 3
   AND o.collected_at = (SELECT max(collected_at) FROM joinads_observation x WHERE x.endpoint=o.endpoint AND x.metric_date=o.metric_date)
 GROUP BY 2 ORDER BY 2 DESC LIMIT 3;
ROLLBACK;
