-- Item 5 — integridade por run Google depois do cutover, somente leitura (RR READ ONLY + ROLLBACK).
-- Run fechado; lotes e linhas declarados = gravados; erro silencioso (run completed com rejeição, erro ou sem lote).
-- :desde substituído pelo chamador. Só agregados por coletor/versão, nenhum id.
\set ON_ERROR_STOP 1
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
WITH r AS (
  SELECT r.collector, r.collector_version, r.status, r.batches_written, r.rows_written, r.rows_rejected, r.error_class,
         r.finished_at, (SELECT count(*) FROM google_ads_raw_batch b WHERE b.run_id = r.run_id) lotes_reais,
         (SELECT count(*) FROM google_ads_observation o WHERE o.run_id = r.run_id) obs_reais
    FROM google_ads_collection_run r WHERE r.started_at >= :'desde')
SELECT 'g_integ' t, collector, collector_version, status, count(*) runs,
       count(*) FILTER (WHERE finished_at IS NULL) sem_fim,
       count(*) FILTER (WHERE batches_written IS DISTINCT FROM lotes_reais) lotes_divergentes,
       count(*) FILTER (WHERE rows_written IS DISTINCT FROM obs_reais) linhas_divergentes,
       count(*) FILTER (WHERE status = 'completed' AND (coalesce(rows_rejected,0) > 0 OR error_class IS NOT NULL OR lotes_reais = 0)) erro_silencioso
  FROM r GROUP BY 2,3,4 ORDER BY 2,3,4;
ROLLBACK;
