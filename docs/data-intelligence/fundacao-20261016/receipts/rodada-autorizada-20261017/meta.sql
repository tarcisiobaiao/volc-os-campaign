\set ON_ERROR_STOP 1
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SHOW transaction_isolation; SHOW transaction_read_only;
SELECT table_name, string_agg(column_name||':'||data_type, ', ' ORDER BY ordinal_position)
  FROM information_schema.columns WHERE table_schema='public'
   AND table_name IN ('google_ads_observation','google_ads_raw_batch','google_ads_collection_run','joinads_observation','joinads_raw_batch','joinads_collection_run')
 GROUP BY 1 ORDER BY 1;
SELECT 'v21_obs' t, grain, count(*), min(metric_date), max(metric_date), min(collected_at), max(collected_at) FROM google_ads_observation GROUP BY grain
UNION ALL SELECT 'ja_obs', endpoint||'/'||grain, count(*), min(metric_date), max(metric_date), min(collected_at), max(collected_at) FROM joinads_observation GROUP BY endpoint, grain ORDER BY 1,2;
ROLLBACK;
