\set ON_ERROR_STOP 1
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
-- só nomes de chaves e tipos, nenhum valor
SELECT 'v21_batch' s, b.grain, jsonb_typeof(b.payload) tp, count(*) n,
       (SELECT string_agg(DISTINCT k, ',') FROM google_ads_raw_batch b2, jsonb_object_keys(CASE WHEN jsonb_typeof(b2.payload)='object' THEN b2.payload ELSE '{}' END) k WHERE b2.grain=b.grain) chaves
  FROM google_ads_raw_batch b GROUP BY b.grain, jsonb_typeof(b.payload);
SELECT 'v21_obs_keys' s, string_agg(DISTINCT 'dim.'||k, ',') FROM google_ads_observation o, jsonb_object_keys(o.dimensions) k WHERE grain='campaign_day';
SELECT 'v21_obs_keys' s, string_agg(DISTINCT 'met.'||k, ',') FROM google_ads_observation o, jsonb_object_keys(o.metrics) k WHERE grain='campaign_day';
SELECT 'v21_obs_keys' s, string_agg(DISTINCT 'attr.'||k, ',') FROM google_ads_observation o, jsonb_object_keys(coalesce(o.attributes,'{}')) k WHERE grain='campaign_day';
SELECT 'v21_currency_paths' s, count(*) FILTER (WHERE jsonb_path_exists(payload, 'strict $.**.currencyCode')) cc, count(*) FILTER (WHERE jsonb_path_exists(payload, 'strict $.**.currency_code')) c2, count(*) FROM google_ads_raw_batch WHERE grain='campaign_day';
SELECT 'v21_rows_per_batch' s, min(c), max(c), count(*) FROM (SELECT batch_id, count(*) c FROM google_ads_observation WHERE grain='campaign_day' GROUP BY 1) x;
SELECT 'ja_batch' s, endpoint, jsonb_typeof(payload), count(*), count(*) FILTER (WHERE jsonb_path_exists(payload,'strict $.**.currency')) cur, count(*) FILTER (WHERE payload_sha256=repeat('0',64)) hz FROM joinads_raw_batch WHERE endpoint IN ('earnings','key_value_campaign_adunit') GROUP BY 1,2,3;
SELECT 'ja_reqmeta_keys' s, string_agg(DISTINCT k, ',') FROM joinads_raw_batch b, jsonb_object_keys(coalesce(b.request_meta,'{}')) k WHERE endpoint IN ('earnings','key_value_campaign_adunit');
SELECT 'ja_kv' s, custom_key, (custom_value ~ '^[0-9]+$') num, count(*), count(DISTINCT custom_value), count(campaign_id), currency_code, data_status FROM joinads_observation WHERE endpoint='key_value_campaign_adunit' GROUP BY 2,3,7,8;
SELECT 'ja_earn' s, currency_code, data_status, count(*), count(DISTINCT domain) FROM joinads_observation WHERE endpoint='earnings' GROUP BY 2,3;
SELECT 'v21_cd' s, count(DISTINCT customer_id) contas, count(DISTINCT campaign_id) camps, count(DISTINCT run_id) runs, string_agg(DISTINCT currency_code, ',') FROM google_ads_observation WHERE grain='campaign_day';
ROLLBACK;
