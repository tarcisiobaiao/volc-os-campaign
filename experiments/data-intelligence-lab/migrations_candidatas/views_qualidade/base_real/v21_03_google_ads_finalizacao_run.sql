BEGIN;

CREATE OR REPLACE FUNCTION public.volc_ingest_google_ads_batch_auto(documento jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, extensions
AS $$
DECLARE
  payload_hash text;
  result jsonb;
BEGIN
  IF jsonb_typeof(documento) <> 'object'
     OR jsonb_typeof(coalesce(documento->'payload','null'::jsonb)) NOT IN ('object','array') THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='documento/payload inválido';
  END IF;
  payload_hash := encode(extensions.digest((documento->'payload')::text, 'sha256'), 'hex');
  result := public.volc_ingest_google_ads_batch(
    documento || jsonb_build_object('payload_sha256', payload_hash)
  );
  UPDATE public.google_ads_collection_run
     SET status='running', finished_at=NULL
   WHERE run_id=(result->>'run_id')::uuid;
  RETURN result || jsonb_build_object('status','running');
END;
$$;

CREATE OR REPLACE FUNCTION public.volc_finish_google_ads_run(documento jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
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
$$;

REVOKE ALL ON FUNCTION public.volc_finish_google_ads_run(jsonb)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.volc_finish_google_ads_run(jsonb)
  TO service_role;

NOTIFY pgrst, 'reload schema';
COMMIT;
