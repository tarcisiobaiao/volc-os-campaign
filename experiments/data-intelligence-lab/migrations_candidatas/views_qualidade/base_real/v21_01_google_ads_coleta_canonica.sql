-- v21_01 — coleta canônica e extensível da Google Ads API
--
-- Autoridade única: https://database.agenciavolc.com.br
-- Esta migration só recebe leituras. Não contém nem autoriza mutate no Google Ads.

BEGIN;

DO $$
BEGIN
  IF to_regclass('public.google_ads_collection_run') IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE='42P07',
      MESSAGE='v21_01 já aplicada: google_ads_collection_run existe';
  END IF;
END $$;

CREATE TABLE public.google_ads_collection_run (
  run_id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  idempotency_key        text NOT NULL UNIQUE,
  workflow_id            text,
  workflow_execution_id  text,
  collector              text NOT NULL,
  collector_version      integer NOT NULL,
  api_version             text NOT NULL,
  mode                    text NOT NULL,
  trigger_kind            text NOT NULL,
  window_start            date,
  window_end              date,
  timezone                text NOT NULL DEFAULT 'America/Sao_Paulo',
  status                  text NOT NULL DEFAULT 'running',
  started_at              timestamptz NOT NULL,
  finished_at             timestamptz,
  accounts_seen           integer NOT NULL DEFAULT 0,
  batches_written         integer NOT NULL DEFAULT 0,
  rows_read               integer NOT NULL DEFAULT 0,
  rows_written            integer NOT NULL DEFAULT 0,
  rows_rejected           integer NOT NULL DEFAULT 0,
  error_class             text,
  error_code              text,
  receipt                 jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at              timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT google_ads_run_idempotency_nonempty CHECK (btrim(idempotency_key) <> ''),
  CONSTRAINT google_ads_run_collector_nonempty CHECK (btrim(collector) <> ''),
  CONSTRAINT google_ads_run_version_positive CHECK (collector_version > 0),
  CONSTRAINT google_ads_run_api_version CHECK (api_version ~ '^v?[0-9]+$'),
  CONSTRAINT google_ads_run_mode CHECK (mode IN ('shadow','canonical','backfill','manual')),
  CONSTRAINT google_ads_run_trigger CHECK (trigger_kind IN ('schedule','manual','webhook','replay')),
  CONSTRAINT google_ads_run_status CHECK (status IN ('running','completed','partial','failed')),
  CONSTRAINT google_ads_run_window CHECK (
    (window_start IS NULL AND window_end IS NULL)
    OR (window_start IS NOT NULL AND window_end >= window_start)
  ),
  CONSTRAINT google_ads_run_finished CHECK (
    (status = 'running' AND finished_at IS NULL)
    OR (status <> 'running' AND finished_at IS NOT NULL)
  ),
  CONSTRAINT google_ads_run_counts CHECK (
    accounts_seen >= 0 AND batches_written >= 0 AND rows_read >= 0
    AND rows_written >= 0 AND rows_rejected >= 0
  ),
  CONSTRAINT google_ads_run_receipt_object CHECK (jsonb_typeof(receipt) = 'object')
);

CREATE TABLE public.google_ads_raw_batch (
  batch_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id            uuid NOT NULL REFERENCES public.google_ads_collection_run(run_id)
                         ON DELETE RESTRICT,
  batch_key         text NOT NULL,
  customer_id       text NOT NULL,
  resource_type     text NOT NULL,
  grain             text NOT NULL,
  window_start      date,
  window_end        date,
  collected_at      timestamptz NOT NULL,
  request_id        text,
  row_count         integer NOT NULL,
  payload           jsonb NOT NULL,
  payload_sha256    text NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT google_ads_batch_key_nonempty CHECK (btrim(batch_key) <> ''),
  CONSTRAINT google_ads_batch_customer CHECK (customer_id ~ '^[0-9]{6,12}$'),
  CONSTRAINT google_ads_batch_resource CHECK (btrim(resource_type) <> '' AND btrim(grain) <> ''),
  CONSTRAINT google_ads_batch_window CHECK (
    (window_start IS NULL AND window_end IS NULL)
    OR (window_start IS NOT NULL AND window_end >= window_start)
  ),
  CONSTRAINT google_ads_batch_rows CHECK (row_count >= 0),
  CONSTRAINT google_ads_batch_payload CHECK (jsonb_typeof(payload) IN ('object','array')),
  CONSTRAINT google_ads_batch_hash CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT google_ads_batch_unique UNIQUE (run_id, batch_key)
);

CREATE TABLE public.google_ads_observation (
  observation_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id            uuid NOT NULL REFERENCES public.google_ads_collection_run(run_id)
                         ON DELETE RESTRICT,
  batch_id          uuid NOT NULL REFERENCES public.google_ads_raw_batch(batch_id)
                         ON DELETE RESTRICT,
  observation_key   text NOT NULL,
  customer_id       text NOT NULL,
  campaign_id       text,
  ad_group_id       text,
  criterion_id      text,
  resource_type     text NOT NULL,
  resource_id       text,
  grain             text NOT NULL,
  metric_date       date,
  metric_hour       smallint,
  currency_code     text,
  dimensions        jsonb NOT NULL DEFAULT '{}'::jsonb,
  metrics           jsonb NOT NULL DEFAULT '{}'::jsonb,
  attributes        jsonb NOT NULL DEFAULT '{}'::jsonb,
  collected_at      timestamptz NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT google_ads_obs_key_nonempty CHECK (btrim(observation_key) <> ''),
  CONSTRAINT google_ads_obs_customer CHECK (customer_id ~ '^[0-9]{6,12}$'),
  CONSTRAINT google_ads_obs_ids CHECK (
    (campaign_id IS NULL OR campaign_id ~ '^[0-9]+$')
    AND (ad_group_id IS NULL OR ad_group_id ~ '^[0-9]+$')
    AND (criterion_id IS NULL OR criterion_id ~ '^[0-9]+$')
  ),
  CONSTRAINT google_ads_obs_hour CHECK (metric_hour IS NULL OR metric_hour BETWEEN 0 AND 23),
  CONSTRAINT google_ads_obs_currency CHECK (currency_code IS NULL OR currency_code ~ '^[A-Z]{3}$'),
  CONSTRAINT google_ads_obs_json CHECK (
    jsonb_typeof(dimensions)='object' AND jsonb_typeof(metrics)='object'
    AND jsonb_typeof(attributes)='object'
  ),
  CONSTRAINT google_ads_obs_unique UNIQUE (run_id, observation_key)
);

CREATE INDEX google_ads_run_freshness_ix
  ON public.google_ads_collection_run (collector, status, started_at DESC);
CREATE INDEX google_ads_batch_scope_ix
  ON public.google_ads_raw_batch (customer_id, resource_type, grain, collected_at DESC);
CREATE INDEX google_ads_obs_campaign_ix
  ON public.google_ads_observation (customer_id, campaign_id, metric_date DESC, collected_at DESC)
  WHERE campaign_id IS NOT NULL;
CREATE INDEX google_ads_obs_resource_ix
  ON public.google_ads_observation (resource_type, grain, metric_date DESC, collected_at DESC);
CREATE INDEX google_ads_obs_dimensions_gin
  ON public.google_ads_observation USING gin (dimensions jsonb_path_ops);
CREATE INDEX google_ads_obs_metrics_gin
  ON public.google_ads_observation USING gin (metrics jsonb_path_ops);

CREATE OR REPLACE FUNCTION public.google_ads_append_only()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
  RAISE EXCEPTION USING ERRCODE='55000',
    MESSAGE=format('%s é append-only: UPDATE/DELETE recusado', TG_TABLE_NAME);
END;
$$;

CREATE TRIGGER google_ads_raw_batch_append_only
  BEFORE UPDATE OR DELETE ON public.google_ads_raw_batch
  FOR EACH ROW EXECUTE FUNCTION public.google_ads_append_only();
CREATE TRIGGER google_ads_observation_append_only
  BEFORE UPDATE OR DELETE ON public.google_ads_observation
  FOR EACH ROW EXECUTE FUNCTION public.google_ads_append_only();

CREATE OR REPLACE FUNCTION public.volc_ingest_google_ads_batch(documento jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_run uuid;
  v_batch uuid;
  v_existing_hash text;
  v_observation jsonb;
  v_inserted integer := 0;
  v_rejected integer := 0;
  v_row_count integer;
  v_status text;
BEGIN
  IF jsonb_typeof(documento) <> 'object' THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='documento precisa ser objeto JSON';
  END IF;
  IF jsonb_typeof(coalesce(documento->'payload','null'::jsonb)) NOT IN ('object','array') THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='payload precisa ser objeto ou array';
  END IF;
  IF jsonb_typeof(coalesce(documento->'observations','[]'::jsonb)) <> 'array' THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='observations precisa ser array';
  END IF;

  INSERT INTO public.google_ads_collection_run (
    idempotency_key, workflow_id, workflow_execution_id, collector,
    collector_version, api_version, mode, trigger_kind, window_start, window_end,
    timezone, status, started_at, receipt
  ) VALUES (
    documento->>'run_key', nullif(documento->>'workflow_id',''),
    nullif(documento->>'workflow_execution_id',''), documento->>'collector',
    (documento->>'collector_version')::integer, documento->>'api_version',
    documento->>'mode', documento->>'trigger_kind',
    nullif(documento->>'window_start','')::date,
    nullif(documento->>'window_end','')::date,
    coalesce(nullif(documento->>'timezone',''),'America/Sao_Paulo'),
    'running', (documento->>'started_at')::timestamptz,
    coalesce(documento->'receipt','{}'::jsonb)
  )
  ON CONFLICT (idempotency_key) DO UPDATE
    SET workflow_execution_id = coalesce(EXCLUDED.workflow_execution_id,
                                          google_ads_collection_run.workflow_execution_id)
  RETURNING run_id INTO v_run;

  SELECT payload_sha256, batch_id INTO v_existing_hash, v_batch
    FROM public.google_ads_raw_batch
   WHERE run_id=v_run AND batch_key=documento->>'batch_key';

  IF v_batch IS NOT NULL THEN
    IF v_existing_hash <> documento->>'payload_sha256' THEN
      RAISE EXCEPTION USING ERRCODE='23505',
        MESSAGE='mesma batch_key com payload diferente';
    END IF;
    RETURN jsonb_build_object('run_id',v_run,'batch_id',v_batch,
                              'idempotent_replay',true,'rows_written',0);
  END IF;

  v_row_count := jsonb_array_length(coalesce(documento->'observations','[]'::jsonb));
  IF (documento->>'row_count')::integer <> v_row_count THEN
    RAISE EXCEPTION USING ERRCODE='22023',
      MESSAGE='row_count diverge do tamanho de observations';
  END IF;

  INSERT INTO public.google_ads_raw_batch (
    run_id,batch_key,customer_id,resource_type,grain,window_start,window_end,
    collected_at,request_id,row_count,payload,payload_sha256
  ) VALUES (
    v_run,documento->>'batch_key',documento->>'customer_id',
    documento->>'resource_type',documento->>'grain',
    nullif(documento->>'window_start','')::date,
    nullif(documento->>'window_end','')::date,
    (documento->>'collected_at')::timestamptz,nullif(documento->>'request_id',''),
    v_row_count,documento->'payload',documento->>'payload_sha256'
  ) RETURNING batch_id INTO v_batch;

  FOR v_observation IN
    SELECT value FROM jsonb_array_elements(documento->'observations')
  LOOP
    BEGIN
      INSERT INTO public.google_ads_observation (
        run_id,batch_id,observation_key,customer_id,campaign_id,ad_group_id,
        criterion_id,resource_type,resource_id,grain,metric_date,metric_hour,
        currency_code,dimensions,metrics,attributes,collected_at
      ) VALUES (
        v_run,v_batch,v_observation->>'observation_key',documento->>'customer_id',
        nullif(v_observation->>'campaign_id',''),nullif(v_observation->>'ad_group_id',''),
        nullif(v_observation->>'criterion_id',''),documento->>'resource_type',
        nullif(v_observation->>'resource_id',''),documento->>'grain',
        nullif(v_observation->>'metric_date','')::date,
        nullif(v_observation->>'metric_hour','')::smallint,
        nullif(v_observation->>'currency_code',''),
        coalesce(v_observation->'dimensions','{}'::jsonb),
        coalesce(v_observation->'metrics','{}'::jsonb),
        coalesce(v_observation->'attributes','{}'::jsonb),
        (documento->>'collected_at')::timestamptz
      );
      v_inserted := v_inserted + 1;
    EXCEPTION WHEN check_violation OR not_null_violation OR invalid_text_representation THEN
      v_rejected := v_rejected + 1;
    END;
  END LOOP;

  v_status := CASE WHEN v_rejected = 0 THEN 'completed' ELSE 'partial' END;
  UPDATE public.google_ads_collection_run
     SET status=v_status,
         finished_at=(documento->>'collected_at')::timestamptz,
         accounts_seen=GREATEST(accounts_seen,1),
         batches_written=batches_written+1,
         rows_read=rows_read+v_row_count,
         rows_written=rows_written+v_inserted,
         rows_rejected=rows_rejected+v_rejected
   WHERE run_id=v_run;

  RETURN jsonb_build_object('run_id',v_run,'batch_id',v_batch,
                            'idempotent_replay',false,'rows_written',v_inserted,
                            'rows_rejected',v_rejected,'status',v_status);
END;
$$;

CREATE VIEW public.google_ads_campaign_day_latest
WITH (security_invoker=true) AS
SELECT DISTINCT ON (customer_id,campaign_id,metric_date)
  observation_id,run_id,customer_id,campaign_id,metric_date,currency_code,
  dimensions,metrics,attributes,collected_at
FROM public.google_ads_observation
WHERE resource_type='campaign' AND grain='campaign_day'
ORDER BY customer_id,campaign_id,metric_date,collected_at DESC;

CREATE VIEW public.google_ads_collection_health
WITH (security_invoker=true) AS
SELECT collector, max(started_at) AS last_started_at,
       max(finished_at) AS last_finished_at,
       (array_agg(status ORDER BY started_at DESC))[1] AS last_status,
       count(*) FILTER (WHERE status='failed' AND started_at >= now()-interval '24 hours') AS failures_24h
FROM public.google_ads_collection_run
GROUP BY collector;

ALTER TABLE public.google_ads_collection_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.google_ads_collection_run FORCE ROW LEVEL SECURITY;
ALTER TABLE public.google_ads_raw_batch ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.google_ads_raw_batch FORCE ROW LEVEL SECURITY;
ALTER TABLE public.google_ads_observation ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.google_ads_observation FORCE ROW LEVEL SECURITY;

REVOKE ALL ON public.google_ads_collection_run FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.google_ads_raw_batch FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.google_ads_observation FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.google_ads_campaign_day_latest FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.google_ads_collection_health FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.volc_ingest_google_ads_batch(jsonb) FROM PUBLIC, anon, authenticated;

GRANT SELECT ON public.google_ads_collection_run TO service_role;
GRANT SELECT ON public.google_ads_raw_batch TO service_role;
GRANT SELECT ON public.google_ads_observation TO service_role;
GRANT SELECT ON public.google_ads_campaign_day_latest TO service_role;
GRANT SELECT ON public.google_ads_collection_health TO service_role;
GRANT EXECUTE ON FUNCTION public.volc_ingest_google_ads_batch(jsonb) TO service_role;

COMMENT ON TABLE public.google_ads_raw_batch IS
  'Resposta preservada por lote da Google Ads API; append-only e idempotente por run+batch.';
COMMENT ON TABLE public.google_ads_observation IS
  'Observações normalizadas multi-granularidade; métricas ausentes não recebem zero inventado.';
COMMENT ON FUNCTION public.volc_ingest_google_ads_batch(jsonb) IS
  'Única fronteira de escrita da coleta Google Ads. Não aplica decisões nem mutações na plataforma.';

NOTIFY pgrst, 'reload schema';
COMMIT;
