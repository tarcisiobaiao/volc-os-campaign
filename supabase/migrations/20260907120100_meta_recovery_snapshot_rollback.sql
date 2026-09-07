-- Rollback do snapshot duravel e da recuperacao de orfaos Meta CREATE_ONLY.
--
-- Ordem deliberada: primeiro remove/recria funcoes que conhecem as colunas
-- novas; so depois remove as colunas. Assim o rollback nao deixa uma funcao
-- velha compilada contra uma tabela ja rebaixada.
\set ON_ERROR_STOP on

BEGIN;

DO $guarda$
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'rollback meta_recovery_snapshot deve rodar como postgres ou supabase_admin';
  END IF;
  IF to_regclass('public.trafego_meta_validation_receipt') IS NULL
     OR to_regclass('public.trafego_meta_create_approval') IS NULL
     OR to_regclass('public.trafego_meta_create_step') IS NULL THEN
    RAISE EXCEPTION 'rollback meta_recovery_snapshot exige o CREATE_ONLY aplicado';
  END IF;
END
$guarda$;

DROP FUNCTION IF EXISTS public.trafego_meta_create_approve(
  text,text,text,bigint,text,timestamptz,text[],uuid,integer,boolean,jsonb,jsonb,jsonb,text,text
);
DROP FUNCTION IF EXISTS public.trafego_meta_create_record_readback(uuid,jsonb,text);
DROP FUNCTION IF EXISTS public.trafego_meta_create_reclaim_orphan(uuid,integer);

CREATE OR REPLACE FUNCTION public.trafego_meta_create_flag_readback(
  p_step_ref uuid, p_error_code text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  IF p_error_code !~ '^[A-Z0-9_]{3,100}$' THEN
    RAISE EXCEPTION 'META_STEP_ERROR_CODE_INVALID';
  END IF;
  UPDATE public.trafego_meta_create_step
     SET readback_error = p_error_code, updated_at = clock_timestamp()
   WHERE step_id = p_step_ref AND state = 'CREATED';
  IF NOT FOUND THEN RAISE EXCEPTION 'META_STEP_NOT_CREATED'; END IF;
  RETURN jsonb_build_object('ok', true, 'readback_error', p_error_code);
END
$$;

CREATE FUNCTION public.trafego_meta_create_approve(
  p_plan_sha256 text,
  p_account_ref text,
  p_actor_id text,
  p_daily_budget_minor bigint,
  p_currency text,
  p_expires_at timestamptz,
  p_steps_expected text[],
  p_validation_id uuid,
  p_validation_max_age_seconds integer,
  p_paused_birth_confirmed boolean,
  p_plan_request jsonb,
  p_asset_supply_receipts jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_id uuid;
  v_distintos integer;
  v_validacao public.trafego_meta_validation_receipt%ROWTYPE;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  IF p_steps_expected IS NULL OR cardinality(p_steps_expected) = 0 THEN
    RAISE EXCEPTION 'META_APPROVAL_MANIFEST_EMPTY';
  END IF;
  SELECT count(DISTINCT passo) INTO v_distintos FROM unnest(p_steps_expected) AS passo;
  IF v_distintos <> cardinality(p_steps_expected) THEN
    RAISE EXCEPTION 'META_APPROVAL_MANIFEST_DUPLICATE';
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(p_steps_expected) AS passo
     WHERE passo !~ '^(campaign|adset|creative(?::[a-z0-9][a-z0-9_-]{0,31})?|ad(?::[a-z0-9][a-z0-9_-]{0,31})?)$'
  ) THEN
    RAISE EXCEPTION 'META_APPROVAL_MANIFEST_INVALID';
  END IF;

  IF p_plan_sha256 !~ '^[a-f0-9]{64}$' THEN
    RAISE EXCEPTION 'META_APPROVAL_PLAN_HASH_INVALID';
  END IF;
  IF p_paused_birth_confirmed IS NOT TRUE THEN
    RAISE EXCEPTION 'META_PAUSED_BIRTH_NOT_CONFIRMED';
  END IF;
  IF p_currency IS DISTINCT FROM 'BRL' THEN
    RAISE EXCEPTION 'META_CURRENCY_UNSUPPORTED';
  END IF;
  IF p_plan_request IS NULL OR jsonb_typeof(p_plan_request) <> 'object' THEN
    RAISE EXCEPTION 'META_APPROVAL_PLAN_REQUEST_INVALID';
  END IF;
  IF p_asset_supply_receipts IS NULL
     OR jsonb_typeof(p_asset_supply_receipts) <> 'array'
     OR jsonb_array_length(p_asset_supply_receipts) NOT BETWEEN 1 AND 10
     OR EXISTS (
       SELECT 1 FROM jsonb_array_elements(p_asset_supply_receipts) AS recibo
        WHERE jsonb_typeof(recibo) <> 'object'
           OR recibo->>'asset_ref' !~ '^[A-Za-z0-9:_-]{8,180}$'
           OR recibo->>'content_sha256' !~ '^[a-f0-9]{64}$'
           OR recibo->>'supply_sha256' !~ '^[a-f0-9]{64}$'
           OR recibo->>'policy_receipt_ref' !~ '^metapolicy_[a-f0-9]{24}$'
           OR recibo->>'policy_state' NOT IN ('CLEAR','AUTHORIZED')
           OR recibo->>'lifecycle' <> 'READY_FOR_PAID_MEDIA'
           OR coalesce((recibo->>'image_hash_bound')::boolean, false) IS NOT TRUE
           OR (recibo->>'policy_expires_at')::timestamptz <= clock_timestamp()
     ) THEN
    RAISE EXCEPTION 'META_ASSET_SUPPLY_RECEIPTS_INVALID';
  END IF;
  IF p_expires_at IS NULL OR p_expires_at <= clock_timestamp() THEN
    RAISE EXCEPTION 'META_APPROVAL_EXPIRY_INVALID';
  END IF;
  IF p_expires_at > clock_timestamp() + interval '1 hour' THEN
    RAISE EXCEPTION 'META_APPROVAL_EXPIRY_TOO_LONG';
  END IF;

  SELECT * INTO v_validacao
    FROM public.trafego_meta_validation_receipt
   WHERE validation_id = p_validation_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'META_VALIDATION_RECEIPT_NOT_FOUND';
  END IF;
  IF v_validacao.plan_sha256 <> p_plan_sha256 THEN
    RAISE EXCEPTION 'META_VALIDATION_PLAN_DIVERGED';
  END IF;
  IF v_validacao.account_ref <> p_account_ref THEN
    RAISE EXCEPTION 'META_VALIDATION_ACCOUNT_DIVERGED';
  END IF;
  IF v_validacao.actor_id <> p_actor_id THEN
    RAISE EXCEPTION 'META_VALIDATION_ACTOR_DIVERGED';
  END IF;
  IF v_validacao.coverage <> 'INDEPENDENT_ROOTS_ONLY' OR v_validacao.accepted IS NOT TRUE THEN
    RAISE EXCEPTION 'META_VALIDATION_NOT_ACCEPTED';
  END IF;
  IF v_validacao.objects_created <> 0 THEN
    RAISE EXCEPTION 'META_VALIDATION_NOT_CLEAN';
  END IF;
  IF v_validacao.operations_total <> cardinality(p_steps_expected) THEN
    RAISE EXCEPTION 'META_VALIDATION_MANIFEST_DIVERGED';
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(v_validacao.steps_validated || v_validacao.steps_pending) AS passo
     WHERE passo <> ALL (p_steps_expected)
  ) THEN
    RAISE EXCEPTION 'META_VALIDATION_MANIFEST_DIVERGED';
  END IF;
  IF p_validation_max_age_seconds IS NULL OR p_validation_max_age_seconds <= 0
     OR p_validation_max_age_seconds > 3600 THEN
    RAISE EXCEPTION 'META_VALIDATION_WINDOW_INVALID';
  END IF;
  IF v_validacao.validated_at
     < clock_timestamp() - make_interval(secs => p_validation_max_age_seconds) THEN
    RAISE EXCEPTION 'META_VALIDATION_RECEIPT_STALE';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_plan_sha256, 1602));
  IF EXISTS (
    SELECT 1
      FROM public.trafego_meta_create_approval AS viva
     WHERE viva.plan_sha256 = p_plan_sha256
       AND viva.state = 'APPROVED'
       AND viva.expires_at > clock_timestamp()
       AND NOT EXISTS (
         SELECT 1 FROM public.trafego_meta_create_step AS passo
          WHERE passo.approval_id = viva.approval_id
            AND passo.state = 'FAILED'
       )
  ) THEN
    RAISE EXCEPTION 'META_APPROVAL_ALREADY_LIVE';
  END IF;

  INSERT INTO public.trafego_meta_create_approval (
    plan_sha256, account_ref, actor_id, daily_budget_minor, currency, expires_at,
    steps_expected, operations_expected, validation_id, paused_birth_confirmed, plan_request,
    asset_supply_receipts
  ) VALUES (
    p_plan_sha256, p_account_ref, p_actor_id, p_daily_budget_minor, p_currency, p_expires_at,
    p_steps_expected, cardinality(p_steps_expected)::smallint, p_validation_id,
    p_paused_birth_confirmed, p_plan_request, p_asset_supply_receipts
  ) RETURNING approval_id INTO v_id;
  RETURN jsonb_build_object(
    'ok', true,
    'approval_id', v_id::text,
    'plan_sha256', p_plan_sha256,
    'capability', 'META_CREATE_PAUSED',
    'expires_at', p_expires_at,
    'steps_expected', to_jsonb(p_steps_expected),
    'operations_expected', cardinality(p_steps_expected),
    'daily_budget_minor', p_daily_budget_minor,
    'currency', p_currency,
    'validation_id', p_validation_id::text,
    'paused_birth_confirmed', true
  );
END
$$;

CREATE OR REPLACE FUNCTION public.trafego_meta_create_approval_manifest(p_approval_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
SET search_path = pg_catalog, public
AS $$
DECLARE v_result jsonb;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  SELECT jsonb_build_object(
    'approval_id', a.approval_id::text,
    'plan_sha256', a.plan_sha256,
    'account_ref', a.account_ref,
    'actor_id', a.actor_id,
    'capability', a.capability,
    'daily_budget_minor', a.daily_budget_minor,
    'currency', a.currency,
    'steps_expected', to_jsonb(a.steps_expected),
    'operations_expected', a.operations_expected,
    'paused_birth_confirmed', a.paused_birth_confirmed,
    'plan_request', a.plan_request,
    'asset_supply_receipts', a.asset_supply_receipts,
    'validation_id', a.validation_id::text,
    'state', CASE WHEN a.expires_at <= clock_timestamp() THEN 'EXPIRED' ELSE a.state END,
    'expires_at', a.expires_at,
    'approved_at', a.approved_at,
    'steps', coalesce((
      SELECT jsonb_agg(jsonb_build_object(
        'step_ref', s.step_id::text,
        'name', s.step_name,
        'ordinal', s.ordinal,
        'state', s.state,
        'has_external_id', s.external_object_id IS NOT NULL,
        'error_code', s.error_code,
        'readback_error', s.readback_error,
        'prepared_at', s.prepared_at
      ) ORDER BY s.ordinal)
      FROM public.trafego_meta_create_step s WHERE s.approval_id = a.approval_id
    ), '[]'::jsonb)
  ) INTO v_result
  FROM public.trafego_meta_create_approval a WHERE a.approval_id = p_approval_id;
  IF v_result IS NULL THEN RAISE EXCEPTION 'META_APPROVAL_NOT_FOUND'; END IF;
  RETURN v_result;
END
$$;

REVOKE ALL ON FUNCTION public.trafego_meta_create_approve(
  text,text,text,bigint,text,timestamptz,text[],uuid,integer,boolean,jsonb,jsonb
) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_approval_manifest(uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_flag_readback(uuid,text) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.trafego_meta_create_approve(
  text,text,text,bigint,text,timestamptz,text[],uuid,integer,boolean,jsonb,jsonb
) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_approval_manifest(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_flag_readback(uuid,text) TO service_role;

ALTER TABLE public.trafego_meta_create_step
  DROP CONSTRAINT IF EXISTS trafego_meta_create_step_readback_evidence,
  DROP COLUMN IF EXISTS readback_at,
  DROP COLUMN IF EXISTS readback_evidence;

ALTER TABLE public.trafego_meta_create_approval
  DROP CONSTRAINT IF EXISTS trafego_meta_create_approval_snapshot_bundle,
  DROP CONSTRAINT IF EXISTS trafego_meta_create_approval_snapshot_hash,
  DROP CONSTRAINT IF EXISTS trafego_meta_create_approval_compiler_version,
  DROP CONSTRAINT IF EXISTS trafego_meta_create_approval_compiled_plan,
  DROP COLUMN IF EXISTS snapshot_sha256,
  DROP COLUMN IF EXISTS compiler_version,
  DROP COLUMN IF EXISTS compiled_plan;

COMMIT;
