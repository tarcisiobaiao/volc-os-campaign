-- V1 + V2 approval: derive immutable financial authority from frozen payloads.
-- Requires create_paused_executor, recovery_snapshot and worker_fencing.
-- No provider calls or existing-row rewrites. Apply once or reapply safely.
BEGIN;

ALTER TABLE public.trafego_meta_create_approval ADD COLUMN IF NOT EXISTS budget_manifest jsonb;
ALTER TABLE public.trafego_meta_create_approval ALTER COLUMN daily_budget_minor DROP NOT NULL;
ALTER TABLE public.trafego_meta_create_approval DROP CONSTRAINT IF EXISTS trafego_meta_create_approval_manifesto;
ALTER TABLE public.trafego_meta_create_approval ADD CONSTRAINT trafego_meta_create_approval_manifesto CHECK (
  cardinality(steps_expected) BETWEEN 1 AND 31 AND array_ndims(steps_expected) = 1
  AND array_lower(steps_expected,1) = 1 AND array_position(steps_expected,NULL) IS NULL);
ALTER TABLE public.trafego_meta_validation_receipt DROP CONSTRAINT IF EXISTS trafego_meta_validation_receipt_manifesto;
ALTER TABLE public.trafego_meta_validation_receipt ADD CONSTRAINT trafego_meta_validation_receipt_manifesto CHECK (
  cardinality(steps_validated) BETWEEN 1 AND 31 AND array_position(steps_validated,NULL) IS NULL
  AND array_position(steps_pending,NULL) IS NULL
  AND operations_total = cardinality(steps_validated) + cardinality(steps_pending)
  AND operations_total BETWEEN 1 AND 31);
ALTER TABLE public.trafego_meta_create_step DROP CONSTRAINT IF EXISTS trafego_meta_create_step_name;
ALTER TABLE public.trafego_meta_create_step ADD CONSTRAINT trafego_meta_create_step_name CHECK (
  step_name ~ '^(campaign|(?:adset|creative|ad)(?::[a-z0-9][a-z0-9_-]{0,31})?)$');
ALTER TABLE public.trafego_meta_create_step DROP CONSTRAINT IF EXISTS trafego_meta_create_step_ordinal;
ALTER TABLE public.trafego_meta_create_step ADD CONSTRAINT trafego_meta_create_step_ordinal CHECK (ordinal BETWEEN 1 AND 31);

CREATE OR REPLACE FUNCTION public.trafego_meta_budget_manifest(p_snapshot jsonb)
RETURNS jsonb LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path = pg_catalog, public
AS $$
DECLARE
  op jsonb; payload jsonb; field text; amount bigint; campaigns int; adsets int; ads int;
  entries jsonb := '[]'; schedules jsonb := '[]'; cbo boolean := false;
  daily_total bigint := 0; all_daily boolean := true;
BEGIN
  IF jsonb_typeof(p_snapshot->'operacoes') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'META_PLAN_SNAPSHOT_INVALID';
  END IF;
  SELECT count(*) FILTER (WHERE value->>'tipo'='campaign'),
         count(*) FILTER (WHERE value->>'tipo'='adset'),
         count(*) FILTER (WHERE value->>'tipo'='ad') INTO campaigns,adsets,ads
    FROM jsonb_array_elements(p_snapshot->'operacoes');
  IF campaigns <> 1 OR adsets NOT BETWEEN 1 AND 10 OR ads NOT BETWEEN 1 AND 10
     OR jsonb_array_length(p_snapshot->'operacoes') > 31 THEN
    RAISE EXCEPTION 'META_APPROVAL_OPERATION_LIMIT';
  END IF;
  FOR op IN SELECT value FROM jsonb_array_elements(p_snapshot->'operacoes') WITH ORDINALITY AS x(value,n)
             WHERE value->>'tipo' IN ('campaign','adset')
             ORDER BY CASE value->>'tipo' WHEN 'campaign' THEN 0 ELSE 1 END,n LOOP
    payload := op->'payload';
    IF jsonb_typeof(payload) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'META_PLAN_SNAPSHOT_INVALID'; END IF;
    IF op->>'tipo'='adset' THEN
      schedules := schedules || jsonb_build_array(jsonb_build_object(
        'step',op->>'nome','start_time',payload->'start_time','end_time',payload->'end_time',
        'bid_strategy',payload->'bid_strategy','bid_amount',payload->'bid_amount',
        'optimization_goal',payload->'optimization_goal','billing_event',payload->'billing_event'));
    END IF;
    IF payload ? 'daily_budget' AND payload ? 'lifetime_budget' THEN RAISE EXCEPTION 'META_BUDGET_INVALID'; END IF;
    IF NOT (payload ? 'daily_budget' OR payload ? 'lifetime_budget') THEN CONTINUE; END IF;
    field := CASE WHEN payload ? 'daily_budget' THEN 'daily_budget' ELSE 'lifetime_budget' END;
    IF jsonb_typeof(payload->field) IS DISTINCT FROM 'number'
       OR coalesce(payload->>field,'') !~ '^[0-9]+$' THEN RAISE EXCEPTION 'META_BUDGET_INVALID'; END IF;
    amount := (payload->>field)::bigint;
    IF amount NOT BETWEEN 1 AND 9007199254740991 THEN RAISE EXCEPTION 'META_BUDGET_INVALID'; END IF;
    cbo := cbo OR op->>'tipo'='campaign';
    all_daily := all_daily AND field='daily_budget';
    daily_total := daily_total + amount;
    entries := entries || jsonb_build_array(jsonb_build_object(
      'step',op->>'nome','level',op->>'tipo','period',CASE field WHEN 'daily_budget' THEN 'DAILY' ELSE 'LIFETIME' END,
      'amount_minor',amount,'currency','BRL','start_time',payload->'start_time','end_time',payload->'end_time',
      'bid_strategy',payload->'bid_strategy','bid_amount',payload->'bid_amount'));
  END LOOP;
  IF (cbo AND jsonb_array_length(entries) <> 1) OR (NOT cbo AND jsonb_array_length(entries) <> adsets) THEN
    RAISE EXCEPTION 'META_BUDGET_NOT_IN_PLAN';
  END IF;
  IF all_daily AND daily_total > 9007199254740991 THEN RAISE EXCEPTION 'META_BUDGET_INVALID'; END IF;
  RETURN jsonb_build_object('version',1,'scope',CASE WHEN cbo THEN 'CBO' ELSE 'ABO' END,'currency','BRL',
    'entries',entries,'adsets',schedules,'daily_total_minor',CASE WHEN all_daily THEN daily_total ELSE NULL END);
END $$;
REVOKE ALL ON FUNCTION public.trafego_meta_budget_manifest(jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.trafego_meta_budget_manifest(jsonb) TO service_role;

ALTER TABLE public.trafego_meta_create_approval DROP CONSTRAINT IF EXISTS trafego_meta_approval_budget_bundle;
ALTER TABLE public.trafego_meta_create_approval ADD CONSTRAINT trafego_meta_approval_budget_bundle CHECK (
  (budget_manifest IS NULL AND daily_budget_minor IS NOT NULL)
  OR (budget_manifest IS NOT NULL AND compiled_plan IS NOT NULL
      AND budget_manifest = public.trafego_meta_budget_manifest(compiled_plan)
      AND daily_budget_minor IS NOT DISTINCT FROM (budget_manifest->>'daily_total_minor')::bigint));

CREATE OR REPLACE FUNCTION public.trafego_meta_guard_approval_budget()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
BEGIN
  IF TG_OP='UPDATE' THEN
    IF (to_jsonb(NEW)-ARRAY['state','revoked_at','revoke_reason']) IS DISTINCT FROM
       (to_jsonb(OLD)-ARRAY['state','revoked_at','revoke_reason']) THEN
      RAISE EXCEPTION 'META_APPROVAL_IMMUTABLE';
    END IF;
    RETURN NEW;
  END IF;
  NEW.budget_manifest := public.trafego_meta_budget_manifest(NEW.compiled_plan);
  IF NEW.daily_budget_minor IS DISTINCT FROM (NEW.budget_manifest->>'daily_total_minor')::bigint THEN
    RAISE EXCEPTION 'META_BUDGET_DIVERGED';
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.trafego_meta_guard_approval_budget() FROM PUBLIC,anon,authenticated;
DROP TRIGGER IF EXISTS trafego_meta_guard_approval_budget ON public.trafego_meta_create_approval;
CREATE TRIGGER trafego_meta_guard_approval_budget BEFORE INSERT OR UPDATE ON public.trafego_meta_create_approval
FOR EACH ROW EXECUTE FUNCTION public.trafego_meta_guard_approval_budget();


-- Existing signatures and their service-role-only ACLs are preserved.
CREATE OR REPLACE FUNCTION public.trafego_meta_create_record_validation(
  p_plan_sha256 text,
  p_account_ref text,
  p_actor_id text,
  p_coverage text,
  p_steps_validated text[],
  p_steps_pending text[],
  p_operations_total integer,
  p_objects_created integer
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_id uuid;
  v_validado_at timestamptz;
  v_todos text[];
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  IF p_plan_sha256 !~ '^[a-f0-9]{64}$' THEN
    RAISE EXCEPTION 'META_VALIDATION_PLAN_HASH_INVALID';
  END IF;
  IF p_coverage IS DISTINCT FROM 'INDEPENDENT_ROOTS_ONLY' THEN
    RAISE EXCEPTION 'META_VALIDATION_COVERAGE_UNKNOWN';
  END IF;
  IF p_objects_created IS DISTINCT FROM 0 THEN
    RAISE EXCEPTION 'META_VALIDATION_NOT_CLEAN';
  END IF;
  IF p_steps_validated IS NULL OR cardinality(p_steps_validated) = 0 THEN
    RAISE EXCEPTION 'META_VALIDATION_MANIFEST_EMPTY';
  END IF;
  v_todos := p_steps_validated || coalesce(p_steps_pending, ARRAY[]::text[]);
  IF (SELECT count(DISTINCT passo) FROM unnest(v_todos) AS passo) <> cardinality(v_todos) THEN
    RAISE EXCEPTION 'META_VALIDATION_MANIFEST_DUPLICATE';
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(v_todos) AS passo
     WHERE passo !~ '^(campaign|(?:adset|creative|ad)(?::[a-z0-9][a-z0-9_-]{0,31})?)$'
  ) THEN
    RAISE EXCEPTION 'META_VALIDATION_MANIFEST_INVALID';
  END IF;
  IF p_operations_total IS DISTINCT FROM cardinality(v_todos) THEN
    RAISE EXCEPTION 'META_VALIDATION_MANIFEST_DIVERGED';
  END IF;

  INSERT INTO public.trafego_meta_validation_receipt (
    plan_sha256, account_ref, actor_id, coverage,
    steps_validated, steps_pending, operations_total, objects_created, accepted
  ) VALUES (
    p_plan_sha256, p_account_ref, p_actor_id, p_coverage,
    p_steps_validated, coalesce(p_steps_pending, ARRAY[]::text[]),
    p_operations_total::smallint, p_objects_created::smallint, true
  ) RETURNING validation_id, validated_at INTO v_id, v_validado_at;
  RETURN jsonb_build_object(
    'ok', true,
    'validation_id', v_id::text,
    'plan_sha256', p_plan_sha256,
    'coverage', p_coverage,
    'objects_created', 0,
    'validated_at', v_validado_at
  );
END
$$;

CREATE OR REPLACE FUNCTION public.trafego_meta_create_approve(
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
  p_asset_supply_receipts jsonb,
  p_compiled_plan jsonb,
  p_compiler_version text,
  p_snapshot_sha256 text
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
     WHERE passo !~ '^(campaign|(?:adset|creative|ad)(?::[a-z0-9][a-z0-9_-]{0,31})?)$'
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

  -- O snapshot e server-only e pode carregar page_id, image_hash, endpoints e
  -- payloads resolvidos. Por isso o teto e maior que `plan_request`, mas ainda
  -- finito: sem teto, uma RPC privilegiada viraria canal de TOAST sem limite.
  IF p_compiled_plan IS NULL
     OR jsonb_typeof(p_compiled_plan) <> 'object'
     OR length(p_compiled_plan::text) > 200000 THEN
    RAISE EXCEPTION 'META_PLAN_SNAPSHOT_INVALID';
  END IF;
  IF p_compiler_version IS NULL
     OR length(btrim(p_compiler_version)) NOT BETWEEN 1 AND 80
     OR p_compiler_version ~ '[[:cntrl:]]' THEN
    RAISE EXCEPTION 'META_PLAN_SNAPSHOT_VERSION_INVALID';
  END IF;
  IF p_snapshot_sha256 !~ '^[a-f0-9]{64}$' THEN
    RAISE EXCEPTION 'META_PLAN_SNAPSHOT_HASH_INVALID';
  END IF;
  IF p_compiled_plan->>'compiler_version' IS DISTINCT FROM p_compiler_version
     OR p_compiled_plan->>'plano_sha256' IS DISTINCT FROM p_plan_sha256
     OR p_snapshot_sha256 <> p_plan_sha256
     OR p_compiled_plan->>'account_ref' IS DISTINCT FROM p_account_ref
     OR p_compiled_plan->>'estado_ao_nascer' IS DISTINCT FROM 'PAUSED'
     OR p_compiled_plan->>'api_version' IS DISTINCT FROM 'v26.0'
     OR jsonb_typeof(p_compiled_plan->'operacoes') <> 'array'
     OR jsonb_array_length(p_compiled_plan->'operacoes') <> cardinality(p_steps_expected)
     OR jsonb_typeof(p_compiled_plan->'asset_supply') <> 'array'
     OR jsonb_array_length(p_compiled_plan->'asset_supply') NOT BETWEEN 1 AND 10
     OR EXISTS (
       SELECT 1
         FROM jsonb_array_elements(p_compiled_plan->'operacoes') WITH ORDINALITY AS op(item, ord)
        WHERE jsonb_typeof(op.item) <> 'object'
           OR op.item->>'nome' IS DISTINCT FROM p_steps_expected[op.ord::integer]
           OR op.item->>'endpoint' IS NULL
           OR length(op.item->>'endpoint') NOT BETWEEN 3 AND 300
           OR jsonb_typeof(op.item->'payload') <> 'object'
     ) THEN
    RAISE EXCEPTION 'META_PLAN_SNAPSHOT_DIVERGED';
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
    steps_expected, operations_expected, validation_id, paused_birth_confirmed,
    plan_request, asset_supply_receipts, compiled_plan, compiler_version, snapshot_sha256
  ) VALUES (
    p_plan_sha256, p_account_ref, p_actor_id, p_daily_budget_minor, p_currency, p_expires_at,
    p_steps_expected, cardinality(p_steps_expected)::smallint, p_validation_id,
    p_paused_birth_confirmed, p_plan_request, p_asset_supply_receipts,
    p_compiled_plan, p_compiler_version, p_snapshot_sha256
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
    'budget_manifest', public.trafego_meta_budget_manifest(p_compiled_plan),
    'currency', p_currency,
    'validation_id', p_validation_id::text,
    'paused_birth_confirmed', true,
    'compiler_version', p_compiler_version,
    'snapshot_sha256', p_snapshot_sha256
  );
END
$$;

CREATE OR REPLACE FUNCTION public.trafego_meta_create_prepare_step(
  p_plan_sha256 text,
  p_approval_id uuid,
  p_actor_id text,
  p_step_name text,
  p_payload_sha256 text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_approval public.trafego_meta_create_approval%ROWTYPE;
  v_step public.trafego_meta_create_step%ROWTYPE;
  v_gemeo public.trafego_meta_create_step%ROWTYPE;
  v_ordinal smallint;
  v_token uuid;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  PERFORM pg_advisory_xact_lock(hashtextextended(p_approval_id::text, 1601));

  SELECT * INTO v_approval
    FROM public.trafego_meta_create_approval
   WHERE approval_id = p_approval_id
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'META_APPROVAL_NOT_FOUND';
  END IF;
  IF v_approval.state <> 'APPROVED' OR v_approval.expires_at <= clock_timestamp() THEN
    RAISE EXCEPTION 'META_APPROVAL_NOT_ACTIVE';
  END IF;
  IF v_approval.plan_sha256 <> p_plan_sha256 THEN
    RAISE EXCEPTION 'META_APPROVED_PLAN_DIVERGED';
  END IF;
  IF v_approval.actor_id <> p_actor_id THEN
    RAISE EXCEPTION 'META_APPROVAL_ACTOR_DIVERGED';
  END IF;
  IF p_step_name !~ '^(campaign|(?:adset|creative|ad)(?::[a-z0-9][a-z0-9_-]{0,31})?)$' THEN
    RAISE EXCEPTION 'META_STEP_UNKNOWN';
  END IF;

  v_ordinal := array_position(v_approval.steps_expected, p_step_name)::smallint;
  IF v_ordinal IS NULL THEN
    RAISE EXCEPTION 'META_STEP_OUTSIDE_APPROVED_PLAN';
  END IF;

  SELECT * INTO v_step
    FROM public.trafego_meta_create_step
   WHERE approval_id = p_approval_id AND step_name = p_step_name
   FOR UPDATE;
  IF FOUND THEN
    IF v_step.payload_sha256 <> p_payload_sha256 THEN
      RAISE EXCEPTION 'META_STEP_PAYLOAD_DIVERGED';
    END IF;
    IF v_step.state = 'CREATED' THEN
      -- Retomada sem POST. Nao ha despacho, entao nao se cunha autoridade de
      -- conclusao: nao existe conclusao pendente para cercar.
      RETURN jsonb_build_object(
        'step_ref', v_step.step_id::text,
        'state', 'CRIADO',
        'external_object_id', v_step.external_object_id,
        'claim_generation', v_step.claim_generation
      );
    END IF;
    IF v_step.state = 'IN_FLIGHT' THEN
      -- ⚠️ REENTRAR REVOGA A REIVINDICACAO ANTERIOR. Antes esta linha so mudava
      -- o estado; o trabalhador anterior continuava com um token valido e
      -- fechava o passo depois. Promover sem revogar era anunciar a duvida sem
      -- tirar a caneta da mao de quem a causou.
      UPDATE public.trafego_meta_create_step
         SET state = 'AMBIGUOUS',
             claim_token = NULL,
             claim_owner = NULL,
             claimed_at = NULL,
             claim_generation = v_step.claim_generation + 1,
             fenced_at = clock_timestamp(),
             updated_at = clock_timestamp()
       WHERE step_id = v_step.step_id;
    END IF;
    IF v_step.state IN ('IN_FLIGHT','AMBIGUOUS') THEN
      RETURN jsonb_build_object(
        'step_ref', v_step.step_id::text,
        'state', 'AMBIGUO',
        'claim_generation', v_step.claim_generation + CASE WHEN v_step.state = 'IN_FLIGHT' THEN 1 ELSE 0 END
      );
    END IF;
    RAISE EXCEPTION 'META_STEP_PREVIOUSLY_FAILED';
  END IF;

  IF v_ordinal > 1 AND NOT EXISTS (
    SELECT 1 FROM public.trafego_meta_create_step
     WHERE approval_id = p_approval_id AND ordinal = v_ordinal - 1 AND state = 'CREATED'
  ) THEN
    RAISE EXCEPTION 'META_STEP_OUT_OF_ORDER';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(
    v_approval.account_ref || ':' || p_step_name || ':' || p_payload_sha256, 1603));
  SELECT passo.* INTO v_gemeo
    FROM public.trafego_meta_create_step AS passo
    JOIN public.trafego_meta_create_approval AS dono
      ON dono.approval_id = passo.approval_id
   WHERE dono.account_ref = v_approval.account_ref
     AND passo.step_name = p_step_name
     AND passo.payload_sha256 = p_payload_sha256
     AND passo.approval_id <> p_approval_id
     AND passo.state IN ('CREATED', 'IN_FLIGHT', 'AMBIGUOUS')
   ORDER BY CASE passo.state WHEN 'CREATED' THEN 0 ELSE 1 END, passo.prepared_at
   LIMIT 1;
  IF FOUND THEN
    IF v_gemeo.state <> 'CREATED' THEN
      RAISE EXCEPTION 'META_STEP_DUPLICATE_IN_FLIGHT';
    END IF;
    INSERT INTO public.trafego_meta_create_step (
      approval_id, step_name, ordinal, payload_sha256,
      state, external_object_id, closed_at
    ) VALUES (
      p_approval_id, p_step_name, v_ordinal, p_payload_sha256,
      'CREATED', v_gemeo.external_object_id, clock_timestamp()
    ) RETURNING * INTO v_step;
    RETURN jsonb_build_object(
      'step_ref', v_step.step_id::text,
      'state', 'CRIADO',
      'external_object_id', v_step.external_object_id,
      'claim_generation', v_step.claim_generation,
      'adotado_de_aprovacao_anterior', true
    );
  END IF;

  -- ⚠️ A AUTORIDADE NASCE JUNTO COM A LINHA, na MESMA transacao que autoriza o
  -- despacho. Cunhar depois abriria exatamente a janela que esta migration
  -- fecha: um instante em que o passo esta IN_FLIGHT e ninguem e o dono.
  v_token := gen_random_uuid();
  INSERT INTO public.trafego_meta_create_step (
    approval_id, step_name, ordinal, payload_sha256,
    claim_token, claim_owner, claimed_at, claim_generation
  ) VALUES (
    p_approval_id, p_step_name, v_ordinal, p_payload_sha256,
    v_token, p_actor_id, clock_timestamp(), 1
  ) RETURNING * INTO v_step;
  RETURN jsonb_build_object(
    'step_ref', v_step.step_id::text,
    'state', 'DESPACHAR',
    'claim_token', v_token::text,
    'claim_generation', v_step.claim_generation
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
    'budget_manifest', a.budget_manifest,
    'currency', a.currency,
    'steps_expected', to_jsonb(a.steps_expected),
    'operations_expected', a.operations_expected,
    'paused_birth_confirmed', a.paused_birth_confirmed,
    'plan_request', a.plan_request,
    'asset_supply_receipts', a.asset_supply_receipts,
    'compiled_plan', a.compiled_plan,
    'compiler_version', a.compiler_version,
    'snapshot_sha256', a.snapshot_sha256,
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
        -- ⚠️ O ID RESOLVIDO, e SO no manifesto interno. A recuperacao precisa
        -- dele para LER o objeto direto — `MASTER-SPEC.json` pede "Read-back
        -- por ID conhecido e prioritario". Reconstruir a identidade por nome
        -- quando o id ja esta gravado e o caminho para adotar um homonimo.
        -- O recibo do navegador continua dizendo apenas `has_external_id`.
        'external_object_id', s.external_object_id,
        'observed_external_ids', s.observed_external_ids,
        'error_code', s.error_code,
        'readback_error', s.readback_error,
        'readback_at', s.readback_at,
        'readback_evidence', s.readback_evidence,
        -- "ID registrado" e "read-back confirmado" sao fatos DIFERENTES, e
        -- confundi-los era o que fazia a recuperacao enxergar zero ambiguos
        -- sobre um objeto que ninguem conferiu.
        'readback_confirmed', (
          s.readback_at IS NOT NULL
          AND s.readback_error IS NULL
          AND (s.readback_evidence->>'matched') = 'true'
        ),
        'claim_generation', s.claim_generation,
        'claim_active', s.claim_token IS NOT NULL,
        'fenced_at', s.fenced_at,
        'prepared_at', s.prepared_at,
        'closed_at', s.closed_at
      ) ORDER BY s.ordinal)
      FROM public.trafego_meta_create_step s WHERE s.approval_id = a.approval_id
    ), '[]'::jsonb)
  ) INTO v_result
  FROM public.trafego_meta_create_approval a WHERE a.approval_id = p_approval_id;
  IF v_result IS NULL THEN RAISE EXCEPTION 'META_APPROVAL_NOT_FOUND'; END IF;
  RETURN v_result;
END
$$;

CREATE OR REPLACE FUNCTION public.trafego_meta_create_receipt(p_approval_id uuid)
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
    'capability', a.capability,
    'daily_budget_minor', a.daily_budget_minor,
    'budget_manifest', a.budget_manifest,
    'currency', a.currency,
    'operations_expected', a.operations_expected,
    'steps_expected', to_jsonb(a.steps_expected),
    'paused_birth_confirmed', a.paused_birth_confirmed,
    'approved_at', a.approved_at,
    'state', CASE WHEN a.expires_at <= clock_timestamp() THEN 'EXPIRED' ELSE a.state END,
    'expires_at', a.expires_at,
    'steps', coalesce((
      SELECT jsonb_agg(jsonb_build_object(
        'name', s.step_name,
        'ordinal', s.ordinal,
        'state', s.state,
        'prepared_at', s.prepared_at,
        'closed_at', s.closed_at,
        'has_external_id', s.external_object_id IS NOT NULL,
        'error_code', s.error_code,
        'readback_error', s.readback_error,
        -- ⚠️ A CONFIRMACAO DURAVEL VIAJA ATE A TELA. Sem ela a interface tinha
        -- de acreditar no `read_back` que veio na resposta HTTP do nascimento
        -- — quer dizer, num estado de memoria que o reload apaga. Um recibo
        -- que so existe na aba nao e recibo.
        'readback_at', s.readback_at,
        'readback_confirmed', (
          s.readback_at IS NOT NULL
          AND s.readback_error IS NULL
          AND (s.readback_evidence->>'matched') = 'true'
        ),
        -- A evidencia ja nasce sanitizada e a RPC de gravacao recusa chave
        -- sensivel; o recibo a repassa como esta.
        'readback_evidence', s.readback_evidence,
        -- Quantos ids um trabalhador SEM autoridade viu. O numero denuncia a
        -- ambiguidade; os ids em si nunca saem do servidor.
        'observed_external_id_count', jsonb_array_length(s.observed_external_ids),
        'claim_active', s.claim_token IS NOT NULL
      ) ORDER BY s.ordinal)
      FROM public.trafego_meta_create_step s WHERE s.approval_id = a.approval_id
    ), '[]'::jsonb)
  ) INTO v_result
  FROM public.trafego_meta_create_approval a WHERE a.approval_id = p_approval_id;
  IF v_result IS NULL THEN RAISE EXCEPTION 'META_APPROVAL_NOT_FOUND'; END IF;
  RETURN v_result;
END
$$;

NOTIFY pgrst, 'reload schema';
COMMIT;
