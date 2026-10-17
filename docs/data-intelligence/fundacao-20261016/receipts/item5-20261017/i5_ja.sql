\set ON_ERROR_STOP 1
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
-- só nomes de chaves (nenhum valor) do payload JoinAds, por endpoint
WITH b AS (SELECT endpoint, payload FROM joinads_raw_batch WHERE created_at > now() - interval '3 days')
SELECT endpoint, 'top' nivel, string_agg(DISTINCT k, ',') FROM b, jsonb_object_keys(CASE WHEN jsonb_typeof(payload)='object' THEN payload ELSE '{}' END) k GROUP BY 1
UNION ALL
SELECT endpoint, 'linha', string_agg(DISTINCT k, ',') FROM b, jsonb_array_elements(CASE WHEN jsonb_typeof(payload->'data')='array' THEN payload->'data' ELSE '[]' END) r, jsonb_object_keys(CASE WHEN jsonb_typeof(r)='object' THEN r ELSE '{}' END) k GROUP BY 1 ORDER BY 1,2;
SELECT jsonb_typeof(payload->'data'->0->'earnings') tipo_earnings, jsonb_typeof(payload->'data'->0->'revenue') tipo_revenue, count(*) FROM joinads_raw_batch WHERE endpoint='earnings' GROUP BY 1,2;
SELECT status, count(*), min(started_at), max(started_at) FROM google_ads_collection_run GROUP BY 1;
ROLLBACK;
