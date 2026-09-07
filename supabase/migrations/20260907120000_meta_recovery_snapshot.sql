-- =============================================================================
-- Meta Ads v26 — snapshot duravel e recuperacao de orfaos CREATE_ONLY
-- =============================================================================
-- NAO APLICADO POR ESTA DELEGACAO. SQL proposto para janela oficial.
-- O objetivo e parar de recompor uma decisao antiga a partir da conta de agora:
-- aprovacao nova guarda o plano despachavel congelado; aprovacao antiga fica
-- LEGIVEL como legado sem snapshot, nunca recompilada em silencio.
-- =============================================================================
\set ON_ERROR_STOP on

BEGIN;

DO $guarda$
DECLARE faltando text;
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'meta_recovery_snapshot deve rodar como postgres ou supabase_admin; atual: %', current_user;
  END IF;
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'meta_recovery_snapshot exige PostgreSQL 15 ou maior';
  END IF;
  IF to_regclass('public.trafego_meta_validation_receipt') IS NULL
     OR to_regclass('public.trafego_meta_create_approval') IS NULL
     OR to_regclass('public.trafego_meta_create_step') IS NULL THEN
    RAISE EXCEPTION 'meta_recovery_snapshot exige o CREATE_ONLY ja aplicado';
  END IF;
  SELECT string_agg(r, ', ' ORDER BY r) INTO faltando
    FROM unnest(ARRAY['anon','authenticated','service_role']) AS r
   WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r);
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION 'meta_recovery_snapshot exige papeis Supabase; ausentes: %', faltando;
  END IF;
  IF EXISTS (
    SELECT 1
      FROM pg_attribute
     WHERE attrelid = 'public.trafego_meta_create_approval'::regclass
       AND attname = 'compiled_plan'
       AND NOT attisdropped
  ) THEN
    RAISE EXCEPTION 'meta_recovery_snapshot ja parece aplicado; compiled_plan existe';
  END IF;
END
$guarda$;

ALTER TABLE public.trafego_meta_create_approval
  ADD COLUMN compiled_plan jsonb,
  ADD COLUMN compiler_version text,
  ADD COLUMN snapshot_sha256 text,
  ADD CONSTRAINT trafego_meta_create_approval_compiled_plan CHECK (
    compiled_plan IS NULL
    OR (jsonb_typeof(compiled_plan) = 'object' AND length(compiled_plan::text) <= 200000)
  ),
  ADD CONSTRAINT trafego_meta_create_approval_compiler_version CHECK (
    compiler_version IS NULL
    OR (length(btrim(compiler_version)) BETWEEN 1 AND 80
        AND compiler_version !~ '[[:cntrl:]]')
  ),
  ADD CONSTRAINT trafego_meta_create_approval_snapshot_hash CHECK (
    snapshot_sha256 IS NULL OR snapshot_sha256 ~ '^[a-f0-9]{64}$'
  ),
  ADD CONSTRAINT trafego_meta_create_approval_snapshot_bundle CHECK (
    (compiled_plan IS NULL AND compiler_version IS NULL AND snapshot_sha256 IS NULL)
    OR (compiled_plan IS NOT NULL AND compiler_version IS NOT NULL AND snapshot_sha256 IS NOT NULL)
  );

ALTER TABLE public.trafego_meta_create_step
  ADD COLUMN readback_at timestamptz,
  ADD COLUMN readback_evidence jsonb,
  ADD CONSTRAINT trafego_meta_create_step_readback_evidence CHECK (
    (readback_at IS NULL AND readback_evidence IS NULL)
    OR (
      state = 'CREATED'
      AND readback_at IS NOT NULL
      AND readback_evidence IS NOT NULL
      AND jsonb_typeof(readback_evidence) = 'object'
      AND length(readback_evidence::text) <= 30000
    )
  );

-- A assinatura muda de aridade; manter duas sobrecargas faria o transporte
-- antigo continuar criando aprovacao sem snapshot, exatamente o buraco que esta
-- migration fecha. Legado continua legivel porque a coluna e NULLABLE; criacao
-- nova sem snapshot e recusada na unica RPC de escrita.
DROP FUNCTION public.trafego_meta_create_approve(
  text,text,text,bigint,text,timestamptz,text[],uuid,integer,boolean,jsonb,jsonb
);

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
    'currency', p_currency,
    'validation_id', p_validation_id::text,
    'paused_birth_confirmed', true,
    'compiler_version', p_compiler_version,
    'snapshot_sha256', p_snapshot_sha256
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

CREATE FUNCTION public.trafego_meta_create_reclaim_orphan(
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

  -- O timeout HTTP do executor e 20s. O piso de 60s evita tomar a reivindicacao
  -- de uma chamada ainda drenando fila, GC ou conexao lenta; o teto de 1 dia
  -- evita transformar erro de unidade em uma recuperacao que nunca enxerga o
  -- orfao. A idade do passo pode ser historica: o teto limita o parametro, nao
  -- a linha recuperavel.
  IF p_min_age_seconds IS NULL OR p_min_age_seconds NOT BETWEEN 60 AND 86400 THEN
    RAISE EXCEPTION 'META_ORPHAN_RECLAIM_AGE_INVALID';
  END IF;

  -- ⚠️ SALT 1604, e a escolha nao e cosmetica. O arquivo do CREATE_ONLY reserva
  -- 1601 para a aprovacao, 1602 para o PLANO e 1603 para a identidade do passo
  -- na conta. Reusar 1602 aqui misturaria dois espacos de chave — um step_id e
  -- um plan_sha256 — no mesmo namespace de lock consultivo. A colisao so custaria
  -- serializacao desnecessaria, nunca correcao, mas a convencao documentada e o
  -- que permite ler o arquivo e saber o que disputa com o que.
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

REVOKE ALL ON FUNCTION public.trafego_meta_create_approve(
  text,text,text,bigint,text,timestamptz,text[],uuid,integer,boolean,jsonb,jsonb,jsonb,text,text
) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_approval_manifest(uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_reclaim_orphan(uuid,integer) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_record_readback(uuid,jsonb,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_flag_readback(uuid,text) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.trafego_meta_create_approve(
  text,text,text,bigint,text,timestamptz,text[],uuid,integer,boolean,jsonb,jsonb,jsonb,text,text
) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_approval_manifest(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_reclaim_orphan(uuid,integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_record_readback(uuid,jsonb,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_flag_readback(uuid,text) TO service_role;

COMMIT;
