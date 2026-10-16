SELECT o.metric_date,
  round(sum(o.revenue_client) FILTER (WHERE o.endpoint='earnings'),2) AS earnings_dominio,
  round(sum(o.revenue_client) FILTER (WHERE o.endpoint='key_value_campaign_adunit'),2) AS receita_kv_campanha,
  round(sum(o.revenue_client) FILTER (WHERE o.endpoint='key_value_campaign_adunit' AND o.custom_value ~ '^[0-9]{10,}$'),2) AS receita_campanha_numerica,
  round(sum(o.revenue_client) FILTER (WHERE o.endpoint='key_value_campaign_adunit' AND (o.custom_value IS NULL OR o.custom_value='' OR o.custom_value !~ '^[0-9]{10,}$')),2) AS receita_kv_nao_numerica,
  count(*) FILTER (WHERE o.endpoint='key_value_campaign_adunit') AS n_kv,
  sum(o.pageviews) FILTER (WHERE o.endpoint='pageviews_campaign_batch' AND o.custom_value ~ '^[0-9]{10,}$') AS pv_campanha_numerica,
  sum(o.pageviews) FILTER (WHERE o.endpoint='pageviews_domain') AS pv_dominio,
  max(o.collected_at) AS ultima_coleta
FROM public.joinads_observation_latest o
WHERE o.metric_date BETWEEN '2026-10-08' AND current_date
GROUP BY 1 ORDER BY 1;
SELECT CASE WHEN custom_value ~ '^[0-9]{10,}$' THEN 'numerico>=10' WHEN custom_value IS NULL OR custom_value='' THEN 'vazio' ELSE 'texto' END AS forma, metric_date, count(*) FROM public.joinads_observation_latest WHERE endpoint='key_value_campaign_adunit' AND metric_date>='2026-10-13' GROUP BY 1,2 ORDER BY 2,1;
