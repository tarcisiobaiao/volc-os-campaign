-- =============================================================================
-- Meta Ads v26 — autoridade duravel do primeiro nascimento PAUSED
-- =============================================================================
-- NAO APLICADO POR ESTA MIGRATION. Execute apenas em janela oficial separada.
-- Depende do read model Meta v15_01, mas nao escreve nele: criacao e observacao
-- sao autoridades diferentes. Cada passo e gravado/commitado ANTES do POST.
-- =============================================================================
\set ON_ERROR_STOP on

BEGIN;

DO $guarda$
DECLARE faltando text;
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'meta_create_paused_executor deve rodar como postgres ou supabase_admin; atual: %', current_user;
  END IF;
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'meta_create_paused_executor exige PostgreSQL 15 ou maior';
  END IF;
  IF to_regclass('public.trafego_meta_ad_account') IS NULL THEN
    RAISE EXCEPTION 'meta_create_paused_executor depende do read model Meta v15_01';
  END IF;
  SELECT string_agg(r, ', ' ORDER BY r) INTO faltando
    FROM unnest(ARRAY['anon','authenticated','service_role']) AS r
   WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r);
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION 'meta_create_paused_executor exige papeis Supabase; ausentes: %', faltando;
  END IF;
  IF to_regclass('public.trafego_meta_create_approval') IS NOT NULL
     OR to_regclass('public.trafego_meta_create_step') IS NOT NULL THEN
    RAISE EXCEPTION 'meta_create_paused_executor ja parece aplicado; rode o rollback correspondente';
  END IF;
END
$guarda$;

CREATE TABLE public.trafego_meta_create_approval (
  approval_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider             text NOT NULL DEFAULT 'META_ADS',
  capability           text NOT NULL DEFAULT 'META_CREATE_PAUSED',
  plan_sha256          text NOT NULL,
  account_ref          text NOT NULL,
  actor_id             text NOT NULL,
  daily_budget_minor   bigint NOT NULL,
  currency             text NOT NULL DEFAULT 'BRL',
  -- O manifesto imutavel do plano aprovado: quais passos existem e em que
  -- ordem. Sem ele, um approval_id valido para quatro operacoes aceitaria
  -- preparar um "creative:extra" que o operador nunca viu.
  steps_expected       text[] NOT NULL,
  state                text NOT NULL DEFAULT 'APPROVED',
  expires_at           timestamptz NOT NULL,
  approved_at          timestamptz NOT NULL DEFAULT clock_timestamp(),
  revoked_at           timestamptz,
  revoke_reason        text,
  CONSTRAINT trafego_meta_create_approval_provider CHECK (provider = 'META_ADS'),
  CONSTRAINT trafego_meta_create_approval_capability CHECK (capability = 'META_CREATE_PAUSED'),
  CONSTRAINT trafego_meta_create_approval_hash CHECK (plan_sha256 ~ '^[a-f0-9]{64}$'),
  CONSTRAINT trafego_meta_create_approval_account_ref CHECK (account_ref ~ '^[A-Za-z0-9:_-]{8,180}$'),
  CONSTRAINT trafego_meta_create_approval_actor CHECK (length(btrim(actor_id)) BETWEEN 1 AND 200),
  CONSTRAINT trafego_meta_create_approval_budget CHECK (daily_budget_minor > 0),
  CONSTRAINT trafego_meta_create_approval_currency CHECK (currency = 'BRL'),
  CONSTRAINT trafego_meta_create_approval_state CHECK (state IN ('APPROVED','REVOKED')),
  -- CHECK nao aceita subconsulta, entao o tamanho mora aqui e a unicidade e o
  -- formato de cada passo sao validados em trafego_meta_create_approve — a
  -- UNICA porta de escrita, ja que nenhum papel tem INSERT nesta tabela.
  -- ⚠️ cardinality, nao array_length: array_length de ARRAY[] devolve NULL, e
  -- CHECK aceita NULL. Sem isto, uma aprovacao com manifesto VAZIO seria
  -- gravada como APPROVED e nenhum passo poderia ser preparado depois.
  CONSTRAINT trafego_meta_create_approval_manifesto CHECK (
    cardinality(steps_expected) BETWEEN 1 AND 22
    AND array_ndims(steps_expected) = 1
    AND array_lower(steps_expected, 1) = 1
    AND array_position(steps_expected, NULL) IS NULL
  ),
  CONSTRAINT trafego_meta_create_approval_expiry CHECK (expires_at > approved_at),
  CONSTRAINT trafego_meta_create_approval_revocation CHECK (
    (state = 'APPROVED' AND revoked_at IS NULL AND revoke_reason IS NULL)
    OR (state = 'REVOKED' AND revoked_at IS NOT NULL
        AND length(btrim(coalesce(revoke_reason, ''))) BETWEEN 5 AND 500)
  )
);
CREATE INDEX trafego_meta_create_approval_plan_ix
  ON public.trafego_meta_create_approval (plan_sha256, approved_at DESC);

CREATE TABLE public.trafego_meta_create_step (
  step_id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  approval_id          uuid NOT NULL REFERENCES public.trafego_meta_create_approval (approval_id) ON DELETE RESTRICT,
  step_name            text NOT NULL,
  ordinal              smallint NOT NULL,
  payload_sha256       text NOT NULL,
  state                text NOT NULL DEFAULT 'IN_FLIGHT',
  external_object_id   text,
  error_code           text,
  prepared_at          timestamptz NOT NULL DEFAULT clock_timestamp(),
  closed_at            timestamptz,
  updated_at           timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT trafego_meta_create_step_name CHECK (
    step_name ~ '^(campaign|adset|creative(?::[a-z0-9][a-z0-9_-]{0,31})?|ad(?::[a-z0-9][a-z0-9_-]{0,31})?)$'
  ),
  CONSTRAINT trafego_meta_create_step_ordinal CHECK (ordinal BETWEEN 1 AND 22),
  CONSTRAINT trafego_meta_create_step_hash CHECK (payload_sha256 ~ '^[a-f0-9]{64}$'),
  CONSTRAINT trafego_meta_create_step_state CHECK (state IN ('IN_FLIGHT','CREATED','AMBIGUOUS','FAILED')),
  CONSTRAINT trafego_meta_create_step_external_id CHECK (
    external_object_id IS NULL OR external_object_id ~ '^[0-9]{1,40}$'),
  CONSTRAINT trafego_meta_create_step_error CHECK (
    error_code IS NULL OR error_code ~ '^[A-Z0-9_]{3,100}$'),
  CONSTRAINT trafego_meta_create_step_shape CHECK (
    (state = 'IN_FLIGHT' AND external_object_id IS NULL AND error_code IS NULL AND closed_at IS NULL)
    OR (state = 'CREATED' AND external_object_id IS NOT NULL AND error_code IS NULL AND closed_at IS NOT NULL)
    OR (state = 'AMBIGUOUS' AND external_object_id IS NULL AND error_code IS NULL AND closed_at IS NULL)
    OR (state = 'FAILED' AND external_object_id IS NULL AND error_code IS NOT NULL AND closed_at IS NOT NULL)
  ),
  UNIQUE (approval_id, step_name),
  UNIQUE (approval_id, ordinal)
);
CREATE INDEX trafego_meta_create_step_state_ix
  ON public.trafego_meta_create_step (state, updated_at DESC);

ALTER TABLE public.trafego_meta_create_approval ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_meta_create_approval FORCE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_meta_create_step ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_meta_create_step FORCE ROW LEVEL SECURITY;

-- ⚠️ service_role tambem entra no REVOKE. O default ACL do Supabase concede
-- ALL em public, e sem esta linha o backend poderia gravar recibo direto na
-- tabela, contornando as RPCs transacionais que sao a unica autoridade da
-- saga. Ler o recibo continua permitido; escrever, so pela funcao.
REVOKE ALL ON public.trafego_meta_create_approval FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON public.trafego_meta_create_step FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.trafego_meta_create_approval TO service_role;
GRANT SELECT ON public.trafego_meta_create_step TO service_role;

CREATE FUNCTION public.trafego_meta_exigir_service_role()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF current_setting('role', true) <> 'service_role'
     AND session_user <> 'service_role'
     AND current_user <> 'service_role' THEN
    RAISE EXCEPTION 'operacao Meta exige service_role' USING ERRCODE = '42501';
  END IF;
END
$$;

CREATE FUNCTION public.trafego_meta_create_approve(
  p_plan_sha256 text,
  p_account_ref text,
  p_actor_id text,
  p_daily_budget_minor bigint,
  p_expires_at timestamptz,
  p_steps_expected text[]
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_id uuid;
  v_distintos integer;
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
  INSERT INTO public.trafego_meta_create_approval (
    plan_sha256, account_ref, actor_id, daily_budget_minor, expires_at, steps_expected
  ) VALUES (
    p_plan_sha256, p_account_ref, p_actor_id, p_daily_budget_minor, p_expires_at,
    p_steps_expected
  ) RETURNING approval_id INTO v_id;
  RETURN jsonb_build_object(
    'ok', true,
    'approval_id', v_id::text,
    'plan_sha256', p_plan_sha256,
    'capability', 'META_CREATE_PAUSED',
    'expires_at', p_expires_at,
    'steps_expected', to_jsonb(p_steps_expected)
  );
END
$$;

CREATE FUNCTION public.trafego_meta_create_prepare_step(
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

  -- O passo precisa pertencer ao manifesto aprovado, e o ordinal e a POSICAO
  -- dele no manifesto: nao o proximo numero livre. Assim um passo extra nao
  -- entra e a ordem nao pode ser invertida entre duas tentativas.
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

  -- O degrau anterior do manifesto precisa estar CRIADO. Uma saga so avanca
  -- sobre objetos que existem de verdade.
  IF v_ordinal > 1 AND NOT EXISTS (
    SELECT 1 FROM public.trafego_meta_create_step
     WHERE approval_id = p_approval_id AND ordinal = v_ordinal - 1 AND state = 'CREATED'
  ) THEN
    RAISE EXCEPTION 'META_STEP_OUT_OF_ORDER';
  END IF;

  INSERT INTO public.trafego_meta_create_step (
    approval_id, step_name, ordinal, payload_sha256
  ) VALUES (
    p_approval_id, p_step_name, v_ordinal, p_payload_sha256
  ) RETURNING * INTO v_step;
  RETURN jsonb_build_object('step_ref', v_step.step_id::text, 'state', 'DESPACHAR');
END
$$;

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

CREATE FUNCTION public.trafego_meta_create_receipt(p_approval_id uuid)
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
    'state', CASE WHEN a.expires_at <= clock_timestamp() THEN 'EXPIRED' ELSE a.state END,
    'expires_at', a.expires_at,
    'steps', coalesce((
      SELECT jsonb_agg(jsonb_build_object(
        'name', s.step_name,
        'state', s.state,
        'prepared_at', s.prepared_at,
        'closed_at', s.closed_at,
        'has_external_id', s.external_object_id IS NOT NULL,
        'error_code', s.error_code
      ) ORDER BY s.ordinal)
      FROM public.trafego_meta_create_step s WHERE s.approval_id = a.approval_id
    ), '[]'::jsonb)
  ) INTO v_result
  FROM public.trafego_meta_create_approval a WHERE a.approval_id = p_approval_id;
  IF v_result IS NULL THEN RAISE EXCEPTION 'META_APPROVAL_NOT_FOUND'; END IF;
  RETURN v_result;
END
$$;

REVOKE ALL ON FUNCTION public.trafego_meta_exigir_service_role() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_approve(text,text,text,bigint,timestamptz,text[]) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_prepare_step(text,uuid,text,text,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_close_step(uuid,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_mark_ambiguous(uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_fail_step(uuid,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_receipt(uuid) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.trafego_meta_create_approve(text,text,text,bigint,timestamptz,text[]) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_prepare_step(text,uuid,text,text,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_close_step(uuid,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_mark_ambiguous(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_fail_step(uuid,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_receipt(uuid) TO service_role;

COMMIT;
