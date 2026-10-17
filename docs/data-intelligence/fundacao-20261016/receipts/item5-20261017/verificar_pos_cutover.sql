-- Item 5 — prova pós-cutover, somente leitura (RR READ ONLY + ROLLBACK). Só agregados, nenhum valor de id.
-- :desde = instante do cutover (timestamptz), substituído pelo chamador.
\set ON_ERROR_STOP 1
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
-- runs Google depois do cutover
SELECT 'g_run' t, collector, collector_version, status, count(*) n, min(started_at) ini, max(finished_at) fim,
       sum(batches_written) lotes, sum(rows_written) linhas, sum(rows_rejected) rejeitadas
  FROM google_ads_collection_run WHERE started_at >= :'desde' GROUP BY 2,3,4 ORDER BY 2,3,4;
-- observações Google: linha de métrica, moeda e zero sem linha
SELECT 'g_obs' t, r.collector, o.grain, o.attributes->>'metric_row_status' linha, o.currency_code moeda,
       o.attributes->>'currency_status' st_moeda, o.attributes->>'currency_source' fonte_moeda,
       count(*) n,
       count(*) FILTER (WHERE o.metrics ? 'cost_micros') com_custo,
       count(*) FILTER (WHERE (o.metrics->>'cost_micros')::numeric = 0) custo_zero,
       count(*) FILTER (WHERE (o.metrics->>'cost_micros')::numeric = 0 AND jsonb_typeof(b.payload)='object' AND b.payload->'metrics' = '{}'::jsonb) zero_sem_linha,
       count(*) FILTER (WHERE jsonb_path_exists(b.payload, 'strict $.**.currencyCode')) payload_com_moeda
  FROM google_ads_observation o JOIN google_ads_raw_batch b ON b.batch_id=o.batch_id JOIN google_ads_collection_run r ON r.run_id=o.run_id
 WHERE r.started_at >= :'desde' GROUP BY 2,3,4,5,6,7 ORDER BY 2,3,4,5;
-- duplicação: mais de um run por coletor no mesmo slot horário
SELECT 'g_dup' t, collector, date_trunc('hour', started_at) slot, count(*) runs FROM google_ads_collection_run
 WHERE started_at >= :'desde' GROUP BY 2,3 HAVING count(*) > 1;
-- JoinAds depois do cutover
SELECT 'j_run' t, collector_version, trigger_kind, status, count(*) n, min(started_at) ini, max(finished_at) fim,
       sum(batches_written) lotes, sum(observations_written) obs, sum(rows_rejected) rejeitadas, sum(warning_count) avisos
  FROM joinads_collection_run WHERE started_at >= :'desde' GROUP BY 2,3,4 ORDER BY 2,3,4;
SELECT 'j_obs' t, o.endpoint, o.attributes->>'currency_status' st_moeda, o.currency_code moeda,
       count(*) n, count(o.revenue_gross) com_receita,
       max(scale(o.revenue_gross)) escala_max_gross, max(scale(o.revenue_client)) escala_max_client,
       count(*) FILTER (WHERE o.attributes ? 'revenue_original') com_original,
       count(*) FILTER (WHERE o.attributes->>'revenue_quantization' = 'decimal_half_even_micros') quantizadas
  FROM joinads_observation o JOIN joinads_collection_run r ON r.run_key=o.run_key
 WHERE r.started_at >= :'desde' GROUP BY 2,3,4 ORDER BY 2;
SELECT 'j_dup' t, collector_version, trigger_kind, date_trunc('hour', started_at) slot, window_start, window_end, count(*) runs
  FROM joinads_collection_run WHERE started_at >= :'desde' GROUP BY 2,3,4,5,6 HAVING count(*) > 1;
-- runs presos (não alterados nesta rodada)
SELECT 'presos' t, collector, status, count(*) FROM google_ads_collection_run WHERE status='running' AND started_at < now() - interval '60 minutes' GROUP BY 2,3;
ROLLBACK;
