-- SÓ PARA TESTE EM POSTGRESQL DESCARTÁVEL. Reconstrução mínima do ledger Google Ads v21 de produção,
-- lida read-only do catálogo oficial em 2026-10-17 ~23:45 UTC (information_schema, pg_constraint, pg_indexes,
-- pg_trigger, pg_get_functiondef). Não é migration e nunca deve rodar em produção.
-- Colunas, CHECKs, índices e a RPC volc_finish_google_ads_run são cópia literal; raw_batch e observation trazem as
-- colunas reais sem FKs (o catálogo lido não mostrou FKs nessas tabelas); google_ads_append_only é reescrita com o
-- mesmo efeito (recusar UPDATE/DELETE), porque o corpo original não foi lido.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN CREATE ROLE service_role NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
END $$;

CREATE TABLE public.google_ads_collection_run (
  run_id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  idempotency_key text NOT NULL UNIQUE,
  workflow_id text, workflow_execution_id text,
  collector text NOT NULL, collector_version integer NOT NULL, api_version text NOT NULL,
  mode text NOT NULL, trigger_kind text NOT NULL,
  window_start date, window_end date,
  timezone text NOT NULL DEFAULT 'America/Sao_Paulo',
  status text NOT NULL DEFAULT 'running',
  started_at timestamptz NOT NULL, finished_at timestamptz,
  accounts_seen integer NOT NULL DEFAULT 0, batches_written integer NOT NULL DEFAULT 0,
  rows_read integer NOT NULL DEFAULT 0, rows_written integer NOT NULL DEFAULT 0, rows_rejected integer NOT NULL DEFAULT 0,
  error_class text, error_code text,
  receipt jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT google_ads_run_idempotency_nonempty CHECK ((btrim(idempotency_key) <> ''::text)),
  CONSTRAINT google_ads_run_collector_nonempty CHECK ((btrim(collector) <> ''::text)),
  CONSTRAINT google_ads_run_version_positive CHECK ((collector_version > 0)),
  CONSTRAINT google_ads_run_api_version CHECK ((api_version ~ '^v?[0-9]+$'::text)),
  CONSTRAINT google_ads_run_mode CHECK ((mode = ANY (ARRAY['shadow'::text, 'canonical'::text, 'backfill'::text, 'manual'::text]))),
  CONSTRAINT google_ads_run_trigger CHECK ((trigger_kind = ANY (ARRAY['schedule'::text, 'manual'::text, 'webhook'::text, 'replay'::text]))),
  CONSTRAINT google_ads_run_status CHECK ((status = ANY (ARRAY['running'::text, 'completed'::text, 'partial'::text, 'failed'::text]))),
  CONSTRAINT google_ads_run_window CHECK ((((window_start IS NULL) AND (window_end IS NULL)) OR ((window_start IS NOT NULL) AND (window_end >= window_start)))),
  CONSTRAINT google_ads_run_finished CHECK ((((status = 'running'::text) AND (finished_at IS NULL)) OR ((status <> 'running'::text) AND (finished_at IS NOT NULL)))),
  CONSTRAINT google_ads_run_counts CHECK (((accounts_seen >= 0) AND (batches_written >= 0) AND (rows_read >= 0) AND (rows_written >= 0) AND (rows_rejected >= 0))),
  CONSTRAINT google_ads_run_receipt_object CHECK ((jsonb_typeof(receipt) = 'object'::text))
);
CREATE INDEX google_ads_run_freshness_ix ON public.google_ads_collection_run USING btree (collector, status, started_at DESC);
ALTER TABLE public.google_ads_collection_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.google_ads_collection_run FORCE ROW LEVEL SECURITY;

CREATE TABLE public.google_ads_raw_batch (
  batch_id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY, run_id uuid NOT NULL, batch_key text NOT NULL,
  customer_id text NOT NULL, resource_type text NOT NULL, grain text NOT NULL, window_start date, window_end date,
  collected_at timestamptz NOT NULL, request_id text, row_count integer NOT NULL, payload jsonb NOT NULL,
  payload_sha256 text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE public.google_ads_observation (
  observation_id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY, run_id uuid NOT NULL, batch_id uuid NOT NULL,
  observation_key text NOT NULL, customer_id text NOT NULL, campaign_id text, ad_group_id text, criterion_id text,
  resource_type text NOT NULL, resource_id text, grain text NOT NULL, metric_date date, metric_hour smallint,
  currency_code text, dimensions jsonb NOT NULL DEFAULT '{}', metrics jsonb NOT NULL DEFAULT '{}',
  attributes jsonb NOT NULL DEFAULT '{}', collected_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now());

CREATE FUNCTION public.google_ads_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='append-only'; END $$;
CREATE TRIGGER google_ads_raw_batch_append_only BEFORE DELETE OR UPDATE ON public.google_ads_raw_batch FOR EACH ROW EXECUTE FUNCTION google_ads_append_only();
CREATE TRIGGER google_ads_observation_append_only BEFORE DELETE OR UPDATE ON public.google_ads_observation FOR EACH ROW EXECUTE FUNCTION google_ads_append_only();

-- cópia literal de produção
CREATE OR REPLACE FUNCTION public.volc_finish_google_ads_run(documento jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
  v_run uuid;
  v_accounts integer;
  v_status text;
BEGIN
  IF jsonb_typeof(documento) <> 'object' THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='documento precisa ser objeto JSON';
  END IF;
  v_status := coalesce(nullif(documento->>'status',''),'completed');
  IF v_status NOT IN ('completed','partial','failed') THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='status final inválido';
  END IF;

  INSERT INTO public.google_ads_collection_run (
    idempotency_key,workflow_id,workflow_execution_id,collector,collector_version,
    api_version,mode,trigger_kind,window_start,window_end,timezone,status,
    started_at,finished_at,receipt,error_class,error_code
  ) VALUES (
    documento->>'run_key',nullif(documento->>'workflow_id',''),
    nullif(documento->>'workflow_execution_id',''),documento->>'collector',
    (documento->>'collector_version')::integer,documento->>'api_version',
    documento->>'mode',documento->>'trigger_kind',
    nullif(documento->>'window_start','')::date,nullif(documento->>'window_end','')::date,
    coalesce(nullif(documento->>'timezone',''),'America/Sao_Paulo'),v_status,
    (documento->>'started_at')::timestamptz,(documento->>'finished_at')::timestamptz,
    coalesce(documento->'receipt','{}'::jsonb),nullif(documento->>'error_class',''),
    nullif(documento->>'error_code','')
  )
  ON CONFLICT (idempotency_key) DO UPDATE SET
    status=EXCLUDED.status,finished_at=EXCLUDED.finished_at,
    receipt=google_ads_collection_run.receipt || EXCLUDED.receipt,
    error_class=EXCLUDED.error_class,error_code=EXCLUDED.error_code
  RETURNING run_id INTO v_run;

  SELECT count(DISTINCT customer_id) INTO v_accounts
    FROM public.google_ads_raw_batch WHERE run_id=v_run;
  UPDATE public.google_ads_collection_run
     SET accounts_seen=v_accounts
   WHERE run_id=v_run;

  RETURN jsonb_build_object(
    'run_id',v_run,'status',v_status,'accounts_seen',v_accounts,
    'batches_written',(SELECT batches_written FROM public.google_ads_collection_run WHERE run_id=v_run),
    'rows_written',(SELECT rows_written FROM public.google_ads_collection_run WHERE run_id=v_run),
    'rows_rejected',(SELECT rows_rejected FROM public.google_ads_collection_run WHERE run_id=v_run)
  );
END;
$function$;
REVOKE ALL ON FUNCTION public.volc_finish_google_ads_run(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.volc_finish_google_ads_run(jsonb) TO service_role;
GRANT ALL ON public.google_ads_collection_run TO service_role;
