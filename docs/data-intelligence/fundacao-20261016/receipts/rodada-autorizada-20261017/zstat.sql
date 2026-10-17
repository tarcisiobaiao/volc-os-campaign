\set ON_ERROR_STOP 1
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
-- só agregados: status declarado das campanhas por presença de linha de métrica no payload
SELECT o.dimensions->>'status' st, (b.payload->'metrics' <> '{}'::jsonb) tem_linha, count(*) linhas, count(DISTINCT o.campaign_id) campanhas
  FROM google_ads_observation o JOIN google_ads_raw_batch b ON b.batch_id=o.batch_id
 WHERE o.grain='campaign_day' GROUP BY 1,2 ORDER BY 1,2;
ROLLBACK;
