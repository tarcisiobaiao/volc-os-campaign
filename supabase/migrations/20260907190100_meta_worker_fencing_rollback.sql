-- =============================================================================
-- ROLLBACK de 20260907190000_meta_worker_fencing.sql
-- =============================================================================
-- Devolve o schema ao estado imediatamente ANTERIOR a cerca versionada: as
-- assinaturas sem `claim_token`, `reclaim_orphan` sem revogacao, o manifesto
-- sem id resolvido e o recibo sem confirmacao duravel.
--
-- ⚠️ ESTE ARQUIVO NUNCA ENTRA NUMA LISTA DE APPLY. Ele derruba a unica coisa
-- que impede um trabalhador cercado de concluir um passo; rodar por engano
-- durante uma janela de apply reabriria o defeito medido em R0-A06.
--
-- ⚠️ ELE NAO E UM CAMINHO DE ATUALIZACAO. Com linhas reais no ledger, o
-- conserto e para frente: fechar as flags de criacao, preservar snapshot e ids,
-- e corrigir por migration nova. Voltar atras aqui APAGA
-- `observed_external_ids` — a unica prova de que um trabalhador sem autoridade
-- viu um objeto nascer.
-- =============================================================================
\set ON_ERROR_STOP on

BEGIN;

DO $guarda$
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'rollback de meta_worker_fencing deve rodar como postgres ou supabase_admin; atual: %', current_user;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_attribute
     WHERE attrelid = 'public.trafego_meta_create_step'::regclass
       AND attname = 'claim_token' AND NOT attisdropped
  ) THEN
    RAISE EXCEPTION 'meta_worker_fencing nao esta aplicado; nada a reverter';
  END IF;
  -- A mesma pergunta que o manifesto faz antes de qualquer rollback: existe
  -- objeto real do outro lado? Se existe, apagar o ledger nao apaga a campanha.
  IF EXISTS (
    SELECT 1 FROM public.trafego_meta_create_step
     WHERE external_object_id IS NOT NULL
        OR jsonb_array_length(observed_external_ids) > 0
  ) THEN
    RAISE EXCEPTION
      'rollback PROIBIDO: ha passo com id externo registrado ou observado; '
      'preserve as linhas e corrija para frente';
  END IF;
END
$guarda$;

DROP FUNCTION IF EXISTS public.trafego_meta_create_conclude_by_recovery(uuid,text,jsonb,text);
DROP FUNCTION IF EXISTS public.trafego_meta_create_record_fenced_dispatch(uuid,uuid,text);
DROP FUNCTION IF EXISTS public.trafego_meta_create_flag_readback(uuid,text,uuid);
DROP FUNCTION IF EXISTS public.trafego_meta_create_record_readback(uuid,jsonb,text,uuid);
DROP FUNCTION IF EXISTS public.trafego_meta_create_fail_step(uuid,text,uuid);
DROP FUNCTION IF EXISTS public.trafego_meta_create_mark_ambiguous(uuid,uuid);
DROP FUNCTION IF EXISTS public.trafego_meta_create_close_step(uuid,text,uuid);
DROP FUNCTION IF EXISTS public.trafego_meta_exigir_claim_vigente(
  public.trafego_meta_create_step, uuid);

-- -----------------------------------------------------------------------------
-- Assinaturas do CREATE_ONLY, como eram antes da cerca
-- -----------------------------------------------------------------------------
CREATE FUNCTION public.trafego_meta_create_close_step(
  p_step_ref uuid,
  p_external_object_id text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE v_step public.trafego_meta_create_step%ROWTYPE;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  PERFORM pg_advisory_xact_lock(hashtextextended(p_step_ref::text, 1602));
  SELECT * INTO v_step FROM public.trafego_meta_create_step
   WHERE step_id = p_step_ref FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'META_STEP_NOT_FOUND'; END IF;
  IF p_external_object_id !~ '^[0-9]{1,40}$' THEN RAISE EXCEPTION 'META_EXTERNAL_ID_INVALID'; END IF;
  IF v_step.state = 'CREATED' THEN
    IF v_step.external_object_id <> p_external_object_id THEN
      RAISE EXCEPTION 'META_EXTERNAL_ID_DIVERGED';
    END IF;
    RETURN jsonb_build_object('ok', true, 'repeated', true);
  END IF;
  IF v_step.state NOT IN ('IN_FLIGHT','AMBIGUOUS') THEN
    RAISE EXCEPTION 'META_STEP_CANNOT_CLOSE';
  END IF;
  UPDATE public.trafego_meta_create_step
     SET state = 'CREATED', external_object_id = p_external_object_id,
         closed_at = clock_timestamp(), updated_at = clock_timestamp()
   WHERE step_id = p_step_ref;
  RETURN jsonb_build_object('ok', true, 'repeated', false);
END
$$;

CREATE FUNCTION public.trafego_meta_create_mark_ambiguous(p_step_ref uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  UPDATE public.trafego_meta_create_step
     SET state = 'AMBIGUOUS', updated_at = clock_timestamp()
   WHERE step_id = p_step_ref AND state = 'IN_FLIGHT';
  IF NOT FOUND AND NOT EXISTS (
    SELECT 1 FROM public.trafego_meta_create_step
     WHERE step_id = p_step_ref AND state IN ('AMBIGUOUS','CREATED')
  ) THEN RAISE EXCEPTION 'META_STEP_CANNOT_MARK_AMBIGUOUS'; END IF;
  RETURN jsonb_build_object('ok', true);
END
$$;

CREATE FUNCTION public.trafego_meta_create_fail_step(p_step_ref uuid, p_error_code text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  UPDATE public.trafego_meta_create_step
     SET state = 'FAILED', error_code = p_error_code,
         closed_at = clock_timestamp(), updated_at = clock_timestamp()
   WHERE step_id = p_step_ref AND state = 'IN_FLIGHT';
  IF NOT FOUND THEN RAISE EXCEPTION 'META_STEP_CANNOT_FAIL'; END IF;
  RETURN jsonb_build_object('ok', true);
END
$$;

-- -----------------------------------------------------------------------------
-- Assinaturas do snapshot (20260907120000), como eram antes da cerca
-- -----------------------------------------------------------------------------
CREATE FUNCTION public.trafego_meta_create_record_readback(
  p_step_ref uuid,
  p_evidence jsonb,
  p_error_code text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_at timestamptz := clock_timestamp();
  v_step public.trafego_meta_create_step%ROWTYPE;
  v_sensitive_key text;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();

  IF p_evidence IS NULL
     OR jsonb_typeof(p_evidence) <> 'object'
     OR length(p_evidence::text) > 30000 THEN
    RAISE EXCEPTION 'META_READBACK_EVIDENCE_INVALID';
  END IF;
  IF jsonb_typeof(p_evidence->'matched') IS DISTINCT FROM 'boolean' THEN
    RAISE EXCEPTION 'META_READBACK_EVIDENCE_INVALID';
  END IF;
  IF p_error_code IS NOT NULL AND p_error_code !~ '^[A-Z0-9_]{3,100}$' THEN
    RAISE EXCEPTION 'META_STEP_ERROR_CODE_INVALID';
  END IF;
  IF p_error_code IS NULL AND p_evidence->>'matched' <> 'true' THEN
    RAISE EXCEPTION 'META_READBACK_POSITIVE_EVIDENCE_INVALID';
  END IF;
  IF p_error_code IS NOT NULL AND p_evidence->>'matched' <> 'false' THEN
    RAISE EXCEPTION 'META_READBACK_DIVERGENT_EVIDENCE_INVALID';
  END IF;

  WITH RECURSIVE walk(valor) AS (
    SELECT p_evidence
    UNION ALL
    SELECT filho.valor
      FROM walk
      CROSS JOIN LATERAL (
        SELECT value AS valor
          FROM jsonb_each(CASE WHEN jsonb_typeof(walk.valor) = 'object' THEN walk.valor ELSE '{}'::jsonb END)
        UNION ALL
        SELECT value AS valor
          FROM jsonb_array_elements(CASE WHEN jsonb_typeof(walk.valor) = 'array' THEN walk.valor ELSE '[]'::jsonb END)
      ) AS filho
  )
  SELECT e.key INTO v_sensitive_key
    FROM walk
    CROSS JOIN LATERAL jsonb_each(
      CASE WHEN jsonb_typeof(walk.valor) = 'object' THEN walk.valor ELSE '{}'::jsonb END
    ) AS e(key, value)
   WHERE e.key ~* '(^id$|_id$|external|token|secret|account_id|campaign_id|adset_id|creative_id|ad_id|page_id|image_hash)'
   LIMIT 1;

  IF v_sensitive_key IS NOT NULL THEN
    RAISE EXCEPTION 'META_READBACK_EVIDENCE_NOT_SANITIZED';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_step_ref::text, 1602));

  SELECT * INTO v_step
    FROM public.trafego_meta_create_step
   WHERE step_id = p_step_ref
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'META_STEP_NOT_FOUND';
  END IF;
  IF v_step.state <> 'CREATED' THEN
    RAISE EXCEPTION 'META_STEP_NOT_CREATED';
  END IF;
  IF v_step.readback_error IS NOT NULL
     AND (p_error_code IS NULL OR p_error_code <> v_step.readback_error) THEN
    RAISE EXCEPTION 'META_READBACK_ERROR_ALREADY_RECORDED';
  END IF;

  UPDATE public.trafego_meta_create_step
     SET readback_at = v_at,
         readback_evidence = p_evidence,
         readback_error = coalesce(p_error_code, readback_error),
         updated_at = v_at
   WHERE step_id = p_step_ref;

  RETURN jsonb_build_object(
    'ok', true,
    'step_ref', p_step_ref::text,
    'readback_at', v_at,
    'readback_error', p_error_code,
    'matched', p_error_code IS NULL
  );
END
$$;

CREATE FUNCTION public.trafego_meta_create_flag_readback(
  p_step_ref uuid, p_error_code text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  RETURN public.trafego_meta_create_record_readback(
    p_step_ref,
    jsonb_build_object(
      'matched', false,
      'source', 'trafego_meta_create_flag_readback',
      'reason', 'legacy_divergent_marker'
    ),
    p_error_code
  );
END
$$;

-- -----------------------------------------------------------------------------
-- prepare_step, reclaim_orphan, manifesto e recibo sem a cerca
-- -----------------------------------------------------------------------------
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
  IF p_step_name !~ '^(campaign|adset|creative(?::[a-z0-9][a-z0-9_-]{0,31})?|ad(?::[a-z0-9][a-z0-9_-]{0,31})?)$' THEN
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
      RETURN jsonb_build_object(
        'step_ref', v_step.step_id::text,
        'state', 'CRIADO',
        'external_object_id', v_step.external_object_id
      );
    END IF;
    IF v_step.state = 'IN_FLIGHT' THEN
      UPDATE public.trafego_meta_create_step
         SET state = 'AMBIGUOUS', updated_at = clock_timestamp()
       WHERE step_id = v_step.step_id;
    END IF;
    IF v_step.state IN ('IN_FLIGHT','AMBIGUOUS') THEN
      RETURN jsonb_build_object('step_ref', v_step.step_id::text, 'state', 'AMBIGUO');
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
      'adotado_de_aprovacao_anterior', true
    );
  END IF;

  INSERT INTO public.trafego_meta_create_step (
    approval_id, step_name, ordinal, payload_sha256
  ) VALUES (
    p_approval_id, p_step_name, v_ordinal, p_payload_sha256
  ) RETURNING * INTO v_step;
  RETURN jsonb_build_object('step_ref', v_step.step_id::text, 'state', 'DESPACHAR');
END
$$;

CREATE OR REPLACE FUNCTION public.trafego_meta_create_reclaim_orphan(
  p_step_ref uuid,
  p_min_age_seconds integer
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_reclaimed_at timestamptz := clock_timestamp();
  v_prepared_at timestamptz;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  IF p_min_age_seconds IS NULL OR p_min_age_seconds NOT BETWEEN 60 AND 86400 THEN
    RAISE EXCEPTION 'META_ORPHAN_RECLAIM_AGE_INVALID';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_step_ref::text, 1604));
  UPDATE public.trafego_meta_create_step
     SET state = 'AMBIGUOUS',
         updated_at = v_reclaimed_at
   WHERE step_id = p_step_ref
     AND state = 'IN_FLIGHT'
     AND prepared_at <= v_reclaimed_at - make_interval(secs => p_min_age_seconds)
   RETURNING prepared_at INTO v_prepared_at;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'META_STEP_ORPHAN_NOT_RECLAIMABLE';
  END IF;
  RETURN jsonb_build_object(
    'ok', true,
    'step_ref', p_step_ref::text,
    'state', 'AMBIGUOUS',
    'prepared_at', v_prepared_at,
    'reclaimed_at', v_reclaimed_at
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
        'error_code', s.error_code,
        'readback_error', s.readback_error,
        'readback_at', s.readback_at,
        'readback_evidence', s.readback_evidence,
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
    'currency', a.currency,
    'operations_expected', a.operations_expected,
    'paused_birth_confirmed', a.paused_birth_confirmed,
    'approved_at', a.approved_at,
    'state', CASE WHEN a.expires_at <= clock_timestamp() THEN 'EXPIRED' ELSE a.state END,
    'expires_at', a.expires_at,
    'steps', coalesce((
      SELECT jsonb_agg(jsonb_build_object(
        'name', s.step_name,
        'state', s.state,
        'prepared_at', s.prepared_at,
        'closed_at', s.closed_at,
        'has_external_id', s.external_object_id IS NOT NULL,
        'error_code', s.error_code,
        'readback_error', s.readback_error
      ) ORDER BY s.ordinal)
      FROM public.trafego_meta_create_step s WHERE s.approval_id = a.approval_id
    ), '[]'::jsonb)
  ) INTO v_result
  FROM public.trafego_meta_create_approval a WHERE a.approval_id = p_approval_id;
  IF v_result IS NULL THEN RAISE EXCEPTION 'META_APPROVAL_NOT_FOUND'; END IF;
  RETURN v_result;
END
$$;

ALTER TABLE public.trafego_meta_create_step
  DROP CONSTRAINT IF EXISTS trafego_meta_create_step_claim_bundle,
  DROP CONSTRAINT IF EXISTS trafego_meta_create_step_claim_generation,
  DROP CONSTRAINT IF EXISTS trafego_meta_create_step_claim_owner,
  DROP CONSTRAINT IF EXISTS trafego_meta_create_step_observed_ids,
  DROP COLUMN IF EXISTS claim_generation,
  DROP COLUMN IF EXISTS claim_token,
  DROP COLUMN IF EXISTS claim_owner,
  DROP COLUMN IF EXISTS claimed_at,
  DROP COLUMN IF EXISTS fenced_at,
  DROP COLUMN IF EXISTS observed_external_ids;

REVOKE ALL ON FUNCTION public.trafego_meta_create_close_step(uuid,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_mark_ambiguous(uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_fail_step(uuid,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_record_readback(uuid,jsonb,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_flag_readback(uuid,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_prepare_step(text,uuid,text,text,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_reclaim_orphan(uuid,integer) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_approval_manifest(uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_receipt(uuid) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.trafego_meta_create_close_step(uuid,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_mark_ambiguous(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_fail_step(uuid,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_record_readback(uuid,jsonb,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_flag_readback(uuid,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_prepare_step(text,uuid,text,text,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_reclaim_orphan(uuid,integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_approval_manifest(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_receipt(uuid) TO service_role;

COMMIT;
