-- JoinAds canonical collection plane.
--
-- This layer is deliberately independent from the legacy compatibility tables
-- (daily_project_metrics / joinads_metrics).  The new n8n workflows write here
-- in shadow mode first; the old workflows remain the serving path until the
-- reconciliation receipt proves equivalence.

BEGIN;

CREATE TABLE public.joinads_collection_run (
  run_key               text PRIMARY KEY,
  workflow_id           text,
  workflow_execution_id text,
  collector             text NOT NULL DEFAULT 'n8n_joinads_v2',
  collector_version     integer NOT NULL DEFAULT 2,
  mode                  text NOT NULL,
  trigger_kind          text NOT NULL,
  window_start          date NOT NULL,
  window_end            date NOT NULL,
  timezone              text NOT NULL DEFAULT 'America/Sao_Paulo',
  status                text NOT NULL DEFAULT 'running',
  started_at            timestamptz NOT NULL,
  finished_at           timestamptz,
  endpoint_count        integer NOT NULL DEFAULT 0,
  batches_written       integer NOT NULL DEFAULT 0,
  rows_read             integer NOT NULL DEFAULT 0,
  observations_written  integer NOT NULL DEFAULT 0,
  rows_rejected         integer NOT NULL DEFAULT 0,
  warning_count         integer NOT NULL DEFAULT 0,
  error_class           text,
  error_code            text,
  receipt               jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT joinads_run_key_nonempty CHECK (btrim(run_key) <> ''),
  CONSTRAINT joinads_run_version_positive CHECK (collector_version > 0),
  CONSTRAINT joinads_run_mode CHECK (mode IN ('shadow','canonical','backfill','manual')),
  CONSTRAINT joinads_run_trigger CHECK (trigger_kind IN ('schedule','manual','webhook','replay')),
  CONSTRAINT joinads_run_status CHECK (status IN ('running','completed','partial','failed')),
  CONSTRAINT joinads_run_window CHECK (window_end >= window_start),
  CONSTRAINT joinads_run_finished CHECK (
    (status = 'running' AND finished_at IS NULL)
    OR (status <> 'running' AND finished_at IS NOT NULL)
  ),
  CONSTRAINT joinads_run_counts CHECK (
    endpoint_count >= 0 AND batches_written >= 0 AND rows_read >= 0
    AND observations_written >= 0 AND rows_rejected >= 0 AND warning_count >= 0
  ),
  CONSTRAINT joinads_run_receipt_object CHECK (jsonb_typeof(receipt) = 'object')
);

CREATE TABLE public.joinads_raw_batch (
  batch_key          text PRIMARY KEY,
  run_key            text NOT NULL REFERENCES public.joinads_collection_run(run_key)
                          ON DELETE RESTRICT,
  endpoint           text NOT NULL,
  grain              text NOT NULL,
  request_meta       jsonb NOT NULL DEFAULT '{}'::jsonb,
  http_status        integer NOT NULL,
  row_count          integer NOT NULL,
  payload            jsonb NOT NULL,
  payload_sha256     text NOT NULL DEFAULT repeat('0', 64),
  schema_fingerprint text NOT NULL DEFAULT repeat('0', 64),
  collected_at       timestamptz NOT NULL,
  created_at         timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT joinads_batch_key_nonempty CHECK (btrim(batch_key) <> ''),
  CONSTRAINT joinads_batch_endpoint_nonempty CHECK (btrim(endpoint) <> '' AND btrim(grain) <> ''),
  CONSTRAINT joinads_batch_status CHECK (http_status BETWEEN 100 AND 599),
  CONSTRAINT joinads_batch_rows CHECK (row_count >= 0),
  CONSTRAINT joinads_batch_request_object CHECK (jsonb_typeof(request_meta) = 'object'),
  CONSTRAINT joinads_batch_payload_json CHECK (jsonb_typeof(payload) IN ('object','array')),
  CONSTRAINT joinads_batch_hash CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT joinads_batch_schema_hash CHECK (schema_fingerprint ~ '^[0-9a-f]{64}$')
);

CREATE TABLE public.joinads_observation (
  observation_key   text PRIMARY KEY,
  run_key           text NOT NULL REFERENCES public.joinads_collection_run(run_key)
                         ON DELETE RESTRICT,
  batch_key         text NOT NULL REFERENCES public.joinads_raw_batch(batch_key)
                         ON DELETE RESTRICT,
  endpoint          text NOT NULL,
  grain             text NOT NULL,
  metric_date       date,
  metric_hour       smallint,
  domain            text,
  campaign_id       text,
  custom_key        text,
  custom_value      text,
  post_id           text,
  land_uri          text,
  ad_unit_name      text,
  country           text,
  country_iso       text,
  advertiser        text,
  network           text,
  currency_code     text NOT NULL DEFAULT 'USD',
  revenue_gross     numeric,
  revenue_client    numeric,
  impressions       bigint,
  clicks            bigint,
  requests_served   bigint,
  unfilled          bigint,
  active_view       numeric,
  pmr               numeric,
  ctr               numeric,
  ecpm_gross        numeric,
  ecpm_client       numeric,
  pageviews         bigint,
  unique_views      bigint,
  first_views       bigint,
  dimensions        jsonb NOT NULL DEFAULT '{}'::jsonb,
  attributes        jsonb NOT NULL DEFAULT '{}'::jsonb,
  data_status       text NOT NULL DEFAULT 'observed',
  collected_at      timestamptz NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT joinads_obs_key_nonempty CHECK (btrim(observation_key) <> ''),
  CONSTRAINT joinads_obs_endpoint_nonempty CHECK (btrim(endpoint) <> '' AND btrim(grain) <> ''),
  CONSTRAINT joinads_obs_hour CHECK (metric_hour IS NULL OR metric_hour BETWEEN 0 AND 23),
  CONSTRAINT joinads_obs_currency CHECK (currency_code ~ '^[A-Z]{3}$'),
  CONSTRAINT joinads_obs_campaign CHECK (campaign_id IS NULL OR campaign_id ~ '^[0-9]+$'),
  CONSTRAINT joinads_obs_country_iso CHECK (country_iso IS NULL OR country_iso ~ '^[A-Z]{2,3}$'),
  CONSTRAINT joinads_obs_nonnegative CHECK (
    (revenue_gross IS NULL OR revenue_gross >= 0)
    AND (revenue_client IS NULL OR revenue_client >= 0)
    AND (impressions IS NULL OR impressions >= 0)
    AND (clicks IS NULL OR clicks >= 0)
    AND (requests_served IS NULL OR requests_served >= 0)
    AND (unfilled IS NULL OR unfilled >= 0)
    AND (pageviews IS NULL OR pageviews >= 0)
    AND (unique_views IS NULL OR unique_views >= 0)
    AND (first_views IS NULL OR first_views >= 0)
  ),
  CONSTRAINT joinads_obs_json CHECK (
    jsonb_typeof(dimensions) = 'object' AND jsonb_typeof(attributes) = 'object'
  ),
  CONSTRAINT joinads_obs_status CHECK (data_status IN ('observed','zero_confirmed','unavailable','unsupported'))
);

CREATE INDEX joinads_run_freshness_ix
  ON public.joinads_collection_run (collector, status, started_at DESC);
CREATE INDEX joinads_raw_run_endpoint_ix
  ON public.joinads_raw_batch (run_key, endpoint, collected_at DESC);
CREATE INDEX joinads_obs_campaign_day_ix
  ON public.joinads_observation (campaign_id, metric_date DESC, collected_at DESC)
  WHERE campaign_id IS NOT NULL;
CREATE INDEX joinads_obs_page_day_ix
  ON public.joinads_observation (domain, post_id, metric_date DESC, collected_at DESC)
  WHERE post_id IS NOT NULL;
CREATE INDEX joinads_obs_land_day_ix
  ON public.joinads_observation (domain, metric_date DESC, collected_at DESC)
  WHERE land_uri IS NOT NULL;
CREATE INDEX joinads_obs_endpoint_grain_ix
  ON public.joinads_observation (endpoint, grain, metric_date DESC, collected_at DESC);
CREATE INDEX joinads_obs_dimensions_gin
  ON public.joinads_observation USING gin (dimensions jsonb_path_ops);

CREATE OR REPLACE FUNCTION public.joinads_hash_raw_batch()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public, extensions
AS $$
DECLARE
  v_shape text;
BEGIN
  NEW.payload_sha256 := encode(extensions.digest(NEW.payload::text, 'sha256'), 'hex');

  WITH documents AS (
    SELECT NEW.payload AS document
    UNION ALL
    SELECT value
      FROM jsonb_array_elements(
        CASE
          WHEN jsonb_typeof(NEW.payload) = 'array' THEN NEW.payload
          WHEN jsonb_typeof(NEW.payload->'data') = 'array' THEN NEW.payload->'data'
          ELSE '[]'::jsonb
        END
      )
  ), field_names AS (
    SELECT DISTINCT key
      FROM documents d
      CROSS JOIN LATERAL jsonb_object_keys(
        CASE WHEN jsonb_typeof(d.document) = 'object' THEN d.document ELSE '{}'::jsonb END
      ) AS key
  )
  SELECT coalesce(string_agg(key, ',' ORDER BY key), '') INTO v_shape FROM field_names;

  NEW.schema_fingerprint := encode(extensions.digest(v_shape, 'sha256'), 'hex');
  RETURN NEW;
END;
$$;

CREATE TRIGGER joinads_raw_batch_hash
  BEFORE INSERT ON public.joinads_raw_batch
  FOR EACH ROW EXECUTE FUNCTION public.joinads_hash_raw_batch();

CREATE OR REPLACE FUNCTION public.joinads_reject_append_only_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
  RAISE EXCEPTION USING ERRCODE='55000',
    MESSAGE=format('%s is append-only: UPDATE/DELETE rejected', TG_TABLE_NAME);
END;
$$;

CREATE TRIGGER joinads_raw_batch_append_only
  BEFORE UPDATE OR DELETE ON public.joinads_raw_batch
  FOR EACH ROW EXECUTE FUNCTION public.joinads_reject_append_only_mutation();
CREATE TRIGGER joinads_observation_append_only
  BEFORE UPDATE OR DELETE ON public.joinads_observation
  FOR EACH ROW EXECUTE FUNCTION public.joinads_reject_append_only_mutation();

CREATE OR REPLACE FUNCTION public.joinads_guard_run_update()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF NEW.run_key IS DISTINCT FROM OLD.run_key
     OR NEW.collector IS DISTINCT FROM OLD.collector
     OR NEW.collector_version IS DISTINCT FROM OLD.collector_version
     OR NEW.mode IS DISTINCT FROM OLD.mode
     OR NEW.window_start IS DISTINCT FROM OLD.window_start
     OR NEW.window_end IS DISTINCT FROM OLD.window_end
     OR NEW.started_at IS DISTINCT FROM OLD.started_at THEN
    RAISE EXCEPTION USING ERRCODE='55000',
      MESSAGE='immutable JoinAds run identity cannot be changed';
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER joinads_collection_run_guard
  BEFORE UPDATE ON public.joinads_collection_run
  FOR EACH ROW EXECUTE FUNCTION public.joinads_guard_run_update();

CREATE VIEW public.joinads_observation_latest
WITH (security_invoker = true)
AS
SELECT DISTINCT ON (
  o.endpoint, o.grain, o.metric_date, o.metric_hour, coalesce(o.domain,''),
  coalesce(o.campaign_id,''), coalesce(o.custom_key,''), coalesce(o.custom_value,''),
  coalesce(o.post_id,''), coalesce(o.land_uri,''), coalesce(o.ad_unit_name,''),
  coalesce(o.country_iso,'')
)
  o.*
FROM public.joinads_observation o
JOIN public.joinads_collection_run r ON r.run_key = o.run_key
WHERE r.status IN ('completed','partial')
ORDER BY
  o.endpoint, o.grain, o.metric_date, o.metric_hour, coalesce(o.domain,''),
  coalesce(o.campaign_id,''), coalesce(o.custom_key,''), coalesce(o.custom_value,''),
  coalesce(o.post_id,''), coalesce(o.land_uri,''), coalesce(o.ad_unit_name,''),
  coalesce(o.country_iso,''), o.collected_at DESC, o.observation_key DESC;

ALTER TABLE public.joinads_collection_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.joinads_raw_batch ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.joinads_observation ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.joinads_collection_run FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.joinads_raw_batch FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.joinads_observation FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.joinads_observation_latest FROM PUBLIC, anon, authenticated;

GRANT SELECT, INSERT, UPDATE ON TABLE public.joinads_collection_run TO service_role;
GRANT SELECT, INSERT ON TABLE public.joinads_raw_batch TO service_role;
GRANT SELECT, INSERT ON TABLE public.joinads_observation TO service_role;
GRANT SELECT ON TABLE public.joinads_observation_latest TO service_role;

COMMENT ON TABLE public.joinads_collection_run IS
  'Canonical JoinAds collection receipt. One row per deterministic schedule/manual run.';
COMMENT ON TABLE public.joinads_raw_batch IS
  'Append-only sanitized aggregate API response; never stores authorization headers.';
COMMENT ON TABLE public.joinads_observation IS
  'Typed append-only JoinAds observations by domain/campaign/page/ad-unit/country/hour.';
COMMENT ON VIEW public.joinads_observation_latest IS
  'Latest completed or partial observation for each declared JoinAds grain.';

NOTIFY pgrst, 'reload schema';
COMMIT;
