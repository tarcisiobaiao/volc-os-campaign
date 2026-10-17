-- Item 5 — canário funcional do Google D-1 (cópia temporária), somente leitura. Ids só por prefixo de 4.
\set ON_ERROR_STOP 1
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT 'd1_run' t, left(r.workflow_id,4)||'…' wf, r.collector, r.collector_version, r.trigger_kind, r.status, r.window_start, r.window_end,
       r.started_at, r.finished_at, r.batches_written, r.rows_written, r.rows_rejected, r.error_class,
       (SELECT count(DISTINCT o.customer_id) FROM google_ads_observation o WHERE o.run_id=r.run_id) contas,
       (SELECT string_agg(DISTINCT o.metric_date::text, ',') FROM google_ads_observation o WHERE o.run_id=r.run_id) datas
  FROM google_ads_collection_run r WHERE r.collector='n8n-google-ads-d1' AND r.started_at >= :'desde' ORDER BY r.started_at;
SELECT 'd1_obs' t, o.attributes->>'metric_row_status' linha, o.currency_code, o.attributes->>'currency_status' st, o.attributes->>'currency_source' fonte,
       count(*) n, count(*) FILTER (WHERE o.metrics ? 'cost_micros') com_custo,
       count(*) FILTER (WHERE (o.metrics->>'cost_micros')::numeric = 0) custo_zero,
       count(*) FILTER (WHERE o.metrics->>'cost_micros' ~ '\.') custo_nao_inteiro,
       count(*) FILTER (WHERE jsonb_typeof(b.payload->'metrics')='object' AND b.payload->'metrics' <> '{}'::jsonb) payload_com_linha,
       count(*) FILTER (WHERE jsonb_path_exists(b.payload, 'strict $.**.currencyCode')) payload_com_moeda,
       count(*) FILTER (WHERE o.attributes ? 'conversion' OR o.metrics ? 'cost_converted') com_conversao
  FROM google_ads_observation o JOIN google_ads_raw_batch b ON b.batch_id=o.batch_id JOIN google_ads_collection_run r ON r.run_id=o.run_id
 WHERE r.collector='n8n-google-ads-d1' AND r.started_at >= :'desde' GROUP BY 2,3,4,5 ORDER BY 2;
-- mesma célula campanha-dia observada pelo D-1 antigo (14:17 BRT) e pelo canário: vintages distintas, sem colisão de chave
SELECT 'd1_vintages' t, o.metric_date, count(DISTINCT o.run_id) runs, count(*) obs, count(DISTINCT o.observation_id) ids
  FROM google_ads_observation o JOIN google_ads_collection_run r ON r.run_id=o.run_id
 WHERE r.collector='n8n-google-ads-d1' AND o.metric_date = (now() AT TIME ZONE 'America/Sao_Paulo')::date - 1 GROUP BY 2;
ROLLBACK;
