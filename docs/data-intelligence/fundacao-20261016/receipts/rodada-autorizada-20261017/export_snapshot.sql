-- Rodada autorizada (item 1) — snapshot read-only para replay/shadow. Somente SELECT.
-- Executado com PGOPTIONS default_transaction_read_only=on, numa única transação
-- REPEATABLE READ READ ONLY encerrada com ROLLBACK. A saída (uma linha JSON por registro) passa direto
-- para o pseudonimizador local (pseudonimizar_export.py), que grava só ids pseudonimizados.
-- Colunas mínimas: nada de dimensions (traz nome de campanha), attributes, receipt, payload bruto,
-- termos de busca, keyword, e-mail, IP, user agent, click ids ou URLs. Do payload do lote saem só
-- dois derivados booleanos/código: "linha de métrica presente" e o conjunto de moedas declaradas.
\set ON_ERROR_STOP 1
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT jsonb_build_object('_t','meta','snapshot_at',now(),'tx_isolation',current_setting('transaction_isolation'),
       'tx_read_only',current_setting('transaction_read_only'),'server_version',current_setting('server_version_num'));
-- Google Ads v21, campaign_day (junção de 02 §9.1)
SELECT jsonb_build_object('_t','v21',
  'observation_id',o.observation_id,'run_id',o.run_id,'batch_id',o.batch_id,'customer_id',o.customer_id,
  'campaign_id',o.campaign_id,'resource_type',o.resource_type,'resource_id',o.resource_id,'grain',o.grain,
  'metric_date',o.metric_date,'metric_hour',o.metric_hour,'currency_code',o.currency_code,
  'metrics',jsonb_strip_nulls(jsonb_build_object('cost_micros',o.metrics->'cost_micros','impressions',o.metrics->'impressions',
             'clicks',o.metrics->'clicks','conversions',o.metrics->'conversions')),
  'metrics_keys',(SELECT jsonb_agg(k ORDER BY k) FROM jsonb_object_keys(o.metrics) k WHERE k IN ('cost_micros','impressions','clicks','conversions')),
  'collected_at',o.collected_at,'created_at',o.created_at,
  'batch_payload_sha256',b.payload_sha256,'batch_request_id',b.request_id,
  'payload_metrics_line',(jsonb_typeof(b.payload)='object' AND jsonb_typeof(b.payload->'metrics')='object' AND b.payload->'metrics'<>'{}'::jsonb),
  'payload_currencies',(SELECT jsonb_agg(DISTINCT v) FROM jsonb_path_query(b.payload,'strict $.**.currencyCode') v),
  'run_collector',r.collector,'run_collector_version',r.collector_version,'run_api_version',r.api_version,
  'run_timezone',r.timezone,'run_status',r.status,'run_mode',r.mode)
  FROM google_ads_observation o JOIN google_ads_raw_batch b ON b.batch_id=o.batch_id
  JOIN google_ads_collection_run r ON r.run_id=o.run_id
 WHERE o.grain='campaign_day' ORDER BY o.collected_at, o.observation_id;
-- execuções v21 (todas; para a análise dos runs presos)
SELECT jsonb_build_object('_t','v21_run','run_id',r.run_id,'collector',r.collector,'collector_version',r.collector_version,
  'mode',r.mode,'trigger_kind',r.trigger_kind,'window_start',r.window_start,'window_end',r.window_end,'status',r.status,
  'started_at',r.started_at,'finished_at',r.finished_at,'batches_written',r.batches_written,'rows_written',r.rows_written,
  'rows_rejected',r.rows_rejected,'error_class',r.error_class,
  'n_obs',(SELECT count(*) FROM google_ads_observation o WHERE o.run_id=r.run_id),
  'n_obs_campaign_day',(SELECT count(*) FROM google_ads_observation o WHERE o.run_id=r.run_id AND o.grain='campaign_day'),
  'max_obs_created_at',(SELECT max(created_at) FROM google_ads_observation o WHERE o.run_id=r.run_id))
  FROM google_ads_collection_run r ORDER BY r.started_at;
-- JoinAds v2: earnings (denominador) e key-value por campanha (numerador) — junção de 02 §9.2
SELECT jsonb_build_object('_t','joinads',
  'observation_key',o.observation_key,'run_key',o.run_key,'batch_key',o.batch_key,'endpoint',o.endpoint,'grain',o.grain,
  'metric_date',o.metric_date,'metric_hour',o.metric_hour,'domain',o.domain,'campaign_id',o.campaign_id,
  'custom_key',o.custom_key,'custom_value',o.custom_value,'ad_unit_name',o.ad_unit_name,'country_iso',o.country_iso,
  'currency_code',o.currency_code,'revenue_client',o.revenue_client,'revenue_gross',o.revenue_gross,
  'impressions',o.impressions,'clicks',o.clicks,'data_status',o.data_status,'collected_at',o.collected_at,'created_at',o.created_at,
  'batch_payload_sha256',b.payload_sha256,'batch_request_custom_key',b.request_meta->>'custom_key',
  'payload_currencies',(SELECT jsonb_agg(DISTINCT v) FROM jsonb_path_query(b.payload,'strict $.**.currency') v),
  'run_collector',r.collector,'run_collector_version',r.collector_version,'run_timezone',r.timezone,'run_status',r.status)
  FROM joinads_observation o JOIN joinads_raw_batch b ON b.batch_key=o.batch_key
  JOIN joinads_collection_run r ON r.run_key=o.run_key
 WHERE o.endpoint IN ('earnings','key_value_campaign_adunit') ORDER BY o.collected_at, o.observation_key;
SELECT jsonb_build_object('_t','joinads_run','run_key',r.run_key,'collector',r.collector,'collector_version',r.collector_version,
  'mode',r.mode,'status',r.status,'started_at',r.started_at,'finished_at',r.finished_at,'warning_count',r.warning_count,'error_class',r.error_class)
  FROM joinads_collection_run r ORDER BY r.started_at;
ROLLBACK;
