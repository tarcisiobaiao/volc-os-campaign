-- =============================================================================
-- Meta Ads v26 — autoridade versionada do trabalhador (fencing) e conclusao
-- por recuperacao
-- =============================================================================
-- NAO APLICADO POR ESTA DELEGACAO. SQL proposto para janela oficial.
--
-- ## O buraco que esta migration fecha
--
-- `20260907120000` deu ao passo orfao uma promocao por IDADE. A idade torna o
-- passo VISIVEL para a recuperacao por leitura, e isso resolveu um defeito
-- real. Mas ela nao FENCEIA ninguem: o trabalhador antigo, cuja resposta de
-- `prepare_step` ficou presa no transporte, volta a vida com a resposta VELHA,
-- despacha o POST e ainda consegue fechar o passo — porque nenhuma escrita
-- posterior confere de QUEM era a autoridade quando o passo foi reivindicado.
--
--   worker A: prepare_step -> DESPACHAR            (resposta atrasa)
--   worker B: reclaim_orphan -> AMBIGUOUS
--   worker A: acorda, POST na Meta, close_step -> CREATED   <-- o defeito
--
-- `MASTER-SPEC.json` pede o mecanismo pelo nome, em
-- `contracts.recovery.concurrency`: "Bloqueio transacional unico sobre conta +
-- identidade de payload do passo, COM VERSIONAMENTO/FENCING NO LEDGER". Idade
-- e elegibilidade para INVESTIGAR; ela nunca provou que o trabalhador morreu.
--
-- ## O que o fencing e, e o que ele nao e
--
-- `prepare_step` passa a CUNHAR um `claim_token` junto do `DESPACHAR`. Toda
-- escrita que conclui aquele despacho — fechar, marcar ambiguo, falhar,
-- gravar read-back — passa a exigir o token VIGENTE. Quem revoga a
-- reivindicacao (o proprio `prepare_step` ao reentrar, ou `reclaim_orphan`)
-- incrementa `claim_generation` e zera o token: a partir dali o trabalhador
-- antigo nao consegue mais escrever nada que pareca autoridade.
--
-- ⚠️ ISSO NAO CANCELA UMA REQUISICAO JA ENVIADA. Nenhuma linha de banco pode.
-- Se o trabalhador antigo ja despachou e voltou com um id real, jogar esse id
-- fora seria perder a UNICA prova de que o objeto pode existir na conta. Por
-- isso existe `record_fenced_dispatch`: ele grava o id como OBSERVACAO em
-- `observed_external_ids`, sem estado novo, sem sobrescrever identidade
-- divergente e sem conceder autoridade nenhuma. Evidencia, nunca conclusao.
--
-- ## Qual mecanismo protege CADA janela
--
--   1. reivindicacao -> envio
--      O token nasce na MESMA transacao que insere a linha IN_FLIGHT, sob o
--      lock consultivo 1601 da aprovacao. Nao existe instante em que o passo
--      esteja em voo sem dono. Uma segunda sessao que entre no mesmo passo cai
--      no ramo de reentrada, que promove para AMBIGUOUS e REVOGA o token.
--
--   2. envio -> conclusao
--      `close_step`, `mark_ambiguous` e `fail_step` exigem o token VIGENTE.
--      Quem foi revogado no meio do voo nao conclui; recebe
--      META_STEP_CLAIM_FENCED e so pode gravar OBSERVACAO.
--      ⚠️ E ele tambem nao avanca para o proximo passo: a regra de ordinal do
--      `prepare_step` exige o degrau anterior CRIADO, e o degrau dele acabou
--      de virar AMBIGUOUS. A cerca de um passo fecha a saga inteira daquele
--      trabalhador, no banco, sem depender de o processo dele cooperar.
--
--   3. conclusao -> read-back
--      `close_step` GIRA o token e devolve o novo. Anotar a leitura exige o
--      token girado, entao uma anotacao emitida com a autoridade do despacho
--      nao pousa sobre uma conclusao mais nova.
--
-- ## O que continua sendo verdade
--
-- Nao ha exactly-once entre PostgreSQL e Meta, e esta migration nao promete
-- nenhum. A janela entre "o banco autorizou" e "a Meta recebeu" e a unica que
-- NENHUMA linha de banco fecha: quando a autorizacao ja saiu, o POST pode
-- acontecer, e cerca nenhuma o desfaz. O que esta migration garante e mais
-- estreito e verificavel: no maximo UM trabalhador detem autoridade de
-- conclusao por reivindicacao, uma autoridade velha nao sobrescreve conclusao
-- mais nova, o id que ela viu nao se perde, e ambiguidade continua sendo estado
-- normal — nunca licenca para reenviar.
-- =============================================================================
\set ON_ERROR_STOP on

BEGIN;

DO $guarda$
DECLARE faltando text;
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'meta_worker_fencing deve rodar como postgres ou supabase_admin; atual: %', current_user;
  END IF;
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'meta_worker_fencing exige PostgreSQL 15 ou maior';
  END IF;
  IF to_regclass('public.trafego_meta_create_step') IS NULL
     OR to_regclass('public.trafego_meta_create_approval') IS NULL THEN
    RAISE EXCEPTION 'meta_worker_fencing exige o CREATE_ONLY ja aplicado';
  END IF;
  -- ⚠️ A DEPENDENCIA E COLUNA, NAO TABELA. `20260907120000` e o que traz
  -- `readback_at`, `readback_evidence` e o `approve` de 15 argumentos. Sem ele
  -- as funcoes recriadas aqui referenciariam colunas inexistentes, e a falha
  -- apareceria so no primeiro despacho — depois de o schema parecer aplicado.
  IF NOT EXISTS (
    SELECT 1 FROM pg_attribute
     WHERE attrelid = 'public.trafego_meta_create_step'::regclass
       AND attname = 'readback_evidence' AND NOT attisdropped
  ) THEN
    RAISE EXCEPTION 'meta_worker_fencing exige 20260907120000_meta_recovery_snapshot aplicado';
  END IF;
  SELECT string_agg(r, ', ' ORDER BY r) INTO faltando
    FROM unnest(ARRAY['anon','authenticated','service_role']) AS r
   WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r);
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION 'meta_worker_fencing exige papeis Supabase; ausentes: %', faltando;
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_attribute
     WHERE attrelid = 'public.trafego_meta_create_step'::regclass
       AND attname = 'claim_token' AND NOT attisdropped
  ) THEN
    RAISE EXCEPTION 'meta_worker_fencing ja parece aplicado; claim_token existe';
  END IF;
END
$guarda$;

-- -----------------------------------------------------------------------------
-- 1. A autoridade versionada, na propria linha do passo
-- -----------------------------------------------------------------------------
ALTER TABLE public.trafego_meta_create_step
  ADD COLUMN claim_generation integer NOT NULL DEFAULT 0,
  ADD COLUMN claim_token uuid,
  ADD COLUMN claim_owner text,
  ADD COLUMN claimed_at timestamptz,
  ADD COLUMN fenced_at timestamptz,
  -- ⚠️ IDS OBSERVADOS SEM AUTORIDADE. Um trabalhador cercado que ja despachou
  -- volta com um id real; ele nao pode concluir nada, e o id nao pode sumir.
  -- Fica aqui, ao lado — nunca em `external_object_id`, que e a IDENTIDADE
  -- concluida do passo.
  ADD COLUMN observed_external_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD CONSTRAINT trafego_meta_create_step_claim_bundle CHECK (
    (claim_token IS NULL AND claim_owner IS NULL AND claimed_at IS NULL)
    OR (claim_token IS NOT NULL AND claim_owner IS NOT NULL AND claimed_at IS NOT NULL)
  ),
  ADD CONSTRAINT trafego_meta_create_step_claim_generation CHECK (claim_generation >= 0),
  ADD CONSTRAINT trafego_meta_create_step_claim_owner CHECK (
    claim_owner IS NULL
    OR (length(btrim(claim_owner)) BETWEEN 1 AND 200 AND claim_owner !~ '[[:cntrl:]]')
  ),
  ADD CONSTRAINT trafego_meta_create_step_observed_ids CHECK (
    jsonb_typeof(observed_external_ids) = 'array'
    AND jsonb_array_length(observed_external_ids) <= 20
    AND length(observed_external_ids::text) <= 4000
  );

COMMENT ON COLUMN public.trafego_meta_create_step.claim_token IS
  'Token de cerca da reivindicacao viva. NULL = ninguem detem autoridade de conclusao.';
COMMENT ON COLUMN public.trafego_meta_create_step.claim_generation IS
  'Incrementa a cada troca de maos. Autoridade antiga nunca volta a valer.';
COMMENT ON COLUMN public.trafego_meta_create_step.observed_external_ids IS
  'Ids vistos por trabalhador SEM autoridade. Evidencia de ambiguidade, nunca identidade concluida.';

-- -----------------------------------------------------------------------------
-- 2. A cerca, num lugar so
-- -----------------------------------------------------------------------------
-- Repetir o predicado em cinco funcoes seria repetir a chance de divergir. A
-- unica autoridade sobre "este token ainda vale?" mora aqui.
CREATE FUNCTION public.trafego_meta_create_exigir_claim(
  p_step public.trafego_meta_create_step,
  p_claim_token uuid
)
RETURNS void
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF p_claim_token IS NULL THEN
    RAISE EXCEPTION 'META_STEP_CLAIM_REQUIRED';
  END IF;
  IF p_step.claim_token IS NULL OR p_step.claim_token <> p_claim_token THEN
    -- A reivindicacao mudou de maos entre o despacho e esta escrita. Quem
    -- chegou aqui perdeu a autoridade — e sabe-lo pelo nome e o que permite ao
    -- chamador preservar o que ele viu em vez de fingir que concluiu.
    RAISE EXCEPTION 'META_STEP_CLAIM_FENCED';
  END IF;
END
$$;

-- -----------------------------------------------------------------------------
-- 3. prepare_step passa a cunhar (e a revogar) autoridade
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

-- -----------------------------------------------------------------------------
-- 4. Toda conclusao de despacho passa a exigir o token vigente
-- -----------------------------------------------------------------------------
DROP FUNCTION public.trafego_meta_create_close_step(uuid, text);

CREATE FUNCTION public.trafego_meta_create_close_step(
  p_step_ref uuid,
  p_external_object_id text,
  p_claim_token uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_step public.trafego_meta_create_step%ROWTYPE;
  v_token uuid;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  PERFORM pg_advisory_xact_lock(hashtextextended(p_step_ref::text, 1602));
  SELECT * INTO v_step FROM public.trafego_meta_create_step
   WHERE step_id = p_step_ref FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'META_STEP_NOT_FOUND'; END IF;
  IF p_external_object_id !~ '^[0-9]{1,40}$' THEN RAISE EXCEPTION 'META_EXTERNAL_ID_INVALID'; END IF;

  -- ⚠️ A CERCA VEM ANTES DA DIVERGENCIA DE ID, e a ordem decide se uma prova
  -- se perde.
  --
  -- Se a linha ja foi concluida — pela recuperacao, ou por outra geracao — quem
  -- chega com token velho precisa ouvir "voce foi cercado", NUNCA "o id
  -- diverge". Sao as duas unicas saidas possiveis, e elas levam a lugares
  -- opostos: a cerca manda o chamador para o caminho da OBSERVACAO, onde o id
  -- que ele tem na mao e preservado; a divergencia o manda para o tratamento de
  -- erro generico, onde esse id se perde. Inverter a ordem apagaria exatamente
  -- a evidencia de que existem DOIS objetos.
  IF v_step.state = 'CREATED' THEN
    IF p_claim_token IS NULL OR v_step.claim_token IS NULL
       OR v_step.claim_token <> p_claim_token THEN
      RAISE EXCEPTION 'META_STEP_CLAIM_FENCED';
    END IF;
    IF v_step.external_object_id <> p_external_object_id THEN
      RAISE EXCEPTION 'META_EXTERNAL_ID_DIVERGED';
    END IF;
    -- Repeticao do MESMO fechamento pelo MESMO dono: idempotente, e o token
    -- gira igual, porque a anotacao de read-back que vem depois precisa dele.
    v_token := gen_random_uuid();
    UPDATE public.trafego_meta_create_step
       SET claim_token = v_token,
           claim_generation = v_step.claim_generation + 1,
           updated_at = clock_timestamp()
     WHERE step_id = p_step_ref;
    RETURN jsonb_build_object(
      'ok', true, 'repeated', true, 'claim_token', v_token::text);
  END IF;

  PERFORM public.trafego_meta_create_exigir_claim(v_step, p_claim_token);

  -- ⚠️ AMBIGUOUS SAIU DAQUI. Antes o fechamento aceitava AMBIGUOUS -> CREATED,
  -- e era por essa porta que o trabalhador cercado concluia. Um passo ambiguo
  -- so fecha por LEITURA, e a leitura tem RPC propria
  -- (`trafego_meta_create_conclude_by_recovery`).
  IF v_step.state <> 'IN_FLIGHT' THEN
    RAISE EXCEPTION 'META_STEP_CANNOT_CLOSE';
  END IF;

  -- ⚠️ O TOKEN GIRA AO FECHAR, e isto fecha a terceira janela.
  --
  -- Fechar o passo e uma conclusao; o read-back que vem depois e OUTRO ato,
  -- sobre um passo que ja existe. Se o token continuasse o mesmo, uma anotacao
  -- de read-back atrasada — emitida com a autoridade do despacho — poderia
  -- pousar sobre uma conclusao mais nova. Girando o token, so quem recebeu ESTA
  -- resposta consegue anotar a leitura deste fechamento.
  v_token := gen_random_uuid();
  UPDATE public.trafego_meta_create_step
     SET state = 'CREATED', external_object_id = p_external_object_id,
         claim_token = v_token,
         claim_generation = v_step.claim_generation + 1,
         closed_at = clock_timestamp(), updated_at = clock_timestamp()
   WHERE step_id = p_step_ref;
  RETURN jsonb_build_object(
    'ok', true, 'repeated', false, 'claim_token', v_token::text);
END
$$;

DROP FUNCTION public.trafego_meta_create_mark_ambiguous(uuid);

CREATE FUNCTION public.trafego_meta_create_mark_ambiguous(
  p_step_ref uuid,
  p_claim_token uuid
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

  -- Ja ambiguo ou ja criado: nada a conceder e nada a apagar. Continua ok para
  -- que o tratamento de erro do executor nao vire um segundo incidente.
  IF v_step.state IN ('AMBIGUOUS','CREATED') THEN
    RETURN jsonb_build_object('ok', true, 'repeated', true);
  END IF;
  IF v_step.state <> 'IN_FLIGHT' THEN
    RAISE EXCEPTION 'META_STEP_CANNOT_MARK_AMBIGUOUS';
  END IF;

  PERFORM public.trafego_meta_create_exigir_claim(v_step, p_claim_token);

  -- Declarar a propria duvida ENCERRA a reivindicacao: quem nao sabe o que
  -- aconteceu nao pode seguir detendo autoridade de conclusao sobre o passo.
  UPDATE public.trafego_meta_create_step
     SET state = 'AMBIGUOUS',
         claim_token = NULL, claim_owner = NULL, claimed_at = NULL,
         claim_generation = v_step.claim_generation + 1,
         fenced_at = clock_timestamp(),
         updated_at = clock_timestamp()
   WHERE step_id = p_step_ref;
  RETURN jsonb_build_object('ok', true, 'repeated', false);
END
$$;

DROP FUNCTION public.trafego_meta_create_fail_step(uuid, text);

CREATE FUNCTION public.trafego_meta_create_fail_step(
  p_step_ref uuid,
  p_error_code text,
  p_claim_token uuid
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
  IF v_step.state <> 'IN_FLIGHT' THEN RAISE EXCEPTION 'META_STEP_CANNOT_FAIL'; END IF;

  -- ⚠️ FALHAR E A ESCRITA MAIS PERIGOSA DE TODAS para um trabalhador cercado.
  -- FAILED e o unico estado que declara "nada nasceu", e ele LIBERA o plano
  -- para nova aprovacao. Uma autoridade velha nunca pode emiti-lo.
  PERFORM public.trafego_meta_create_exigir_claim(v_step, p_claim_token);

  UPDATE public.trafego_meta_create_step
     SET state = 'FAILED', error_code = p_error_code,
         claim_token = NULL, claim_owner = NULL, claimed_at = NULL,
         claim_generation = v_step.claim_generation + 1,
         closed_at = clock_timestamp(), updated_at = clock_timestamp()
   WHERE step_id = p_step_ref;
  RETURN jsonb_build_object('ok', true);
END
$$;

-- -----------------------------------------------------------------------------
-- 5. O read-back do despacho tambem e cercado
-- -----------------------------------------------------------------------------
DROP FUNCTION public.trafego_meta_create_flag_readback(uuid, text);
DROP FUNCTION public.trafego_meta_create_record_readback(uuid, jsonb, text);

CREATE FUNCTION public.trafego_meta_create_record_readback(
  p_step_ref uuid,
  p_evidence jsonb,
  p_error_code text DEFAULT NULL,
  p_claim_token uuid DEFAULT NULL
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

  -- ⚠️ A CERCA VALE ENQUANTO A REIVINDICACAO EXISTIR. Se o passo ainda tem
  -- dono, so o dono anota; se ninguem detem a reivindicacao — porque o
  -- despacho ja concluiu e soltou a caneta — a anotacao e da recuperacao, que
  -- tem RPC propria e passa por aqui sem token.
  IF v_step.claim_token IS NOT NULL THEN
    PERFORM public.trafego_meta_create_exigir_claim(v_step, p_claim_token);
  END IF;

  IF v_step.readback_error IS NOT NULL
     AND (p_error_code IS NULL OR p_error_code <> v_step.readback_error) THEN
    RAISE EXCEPTION 'META_READBACK_ERROR_ALREADY_RECORDED';
  END IF;

  -- ⚠️ E AQUI A REIVINDICACAO TERMINA. Anotar a leitura e o ultimo ato do
  -- despacho sobre este passo: dali em diante nao ha conclusao pendente para
  -- cercar, e manter o token vivo teria um custo concreto — uma saga posterior
  -- que RETOMA este passo (`prepare_step` devolvendo CRIADO, sem token, porque
  -- nao ha POST a autorizar) nao conseguiria mais anotar nada, e uma retomada
  -- legitima passaria a parecer falha de durabilidade.
  --
  -- Soltar nao reabre porta: `close_step` sobre um passo CRIADO sem dono recusa
  -- por cerca, `fail_step` exige IN_FLIGHT, e uma divergencia ja registrada
  -- continua protegida por META_READBACK_ERROR_ALREADY_RECORDED.
  UPDATE public.trafego_meta_create_step
     SET readback_at = v_at,
         readback_evidence = p_evidence,
         readback_error = coalesce(p_error_code, readback_error),
         claim_token = NULL, claim_owner = NULL, claimed_at = NULL,
         claim_generation = claim_generation
           + CASE WHEN claim_token IS NOT NULL THEN 1 ELSE 0 END,
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
  p_step_ref uuid, p_error_code text, p_claim_token uuid DEFAULT NULL
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
    p_error_code,
    p_claim_token
  );
END
$$;

-- -----------------------------------------------------------------------------
-- 6. O despacho cercado: gravar o que ele VIU, sem conceder o que ele perdeu
-- -----------------------------------------------------------------------------
CREATE FUNCTION public.trafego_meta_create_record_fenced_dispatch(
  p_step_ref uuid,
  p_claim_token uuid,
  p_external_object_id text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_step public.trafego_meta_create_step%ROWTYPE;
  v_ja_conhecido boolean;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  IF p_external_object_id !~ '^[0-9]{1,40}$' THEN
    RAISE EXCEPTION 'META_EXTERNAL_ID_INVALID';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_step_ref::text, 1602));
  SELECT * INTO v_step FROM public.trafego_meta_create_step
   WHERE step_id = p_step_ref FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'META_STEP_NOT_FOUND'; END IF;

  -- ⚠️ ESTA RPC EXISTE PARA QUEM PERDEU A AUTORIDADE. Chamar com o token
  -- VIGENTE seria o caminho normal de conclusao entrando pela porta errada, e
  -- aceitar isso transformaria a excecao num atalho para fechar sem fechar.
  IF p_claim_token IS NOT NULL
     AND v_step.claim_token IS NOT NULL
     AND v_step.claim_token = p_claim_token THEN
    RAISE EXCEPTION 'META_STEP_CLAIM_STILL_VALID';
  END IF;

  v_ja_conhecido := (
    v_step.external_object_id IS NOT NULL
    AND v_step.external_object_id = p_external_object_id
  );

  -- O id observado entra na LISTA, nunca em `external_object_id`. Um
  -- trabalhador sem autoridade nao decide a identidade do passo — nem quando
  -- ela ainda esta vazia, porque `CREATED` afirma "conferido e concluido", e
  -- ele nao conferiu nada.
  IF NOT v_ja_conhecido
     AND NOT (v_step.observed_external_ids @> to_jsonb(ARRAY[p_external_object_id])) THEN
    UPDATE public.trafego_meta_create_step
       SET observed_external_ids = observed_external_ids || to_jsonb(p_external_object_id),
           updated_at = clock_timestamp()
     WHERE step_id = p_step_ref;
  END IF;

  -- Um passo ainda IN_FLIGHT cujo dono foi cercado e, por definicao, duvidoso:
  -- ele precisa ficar VISIVEL para a recuperacao por leitura. Estados ja
  -- concluidos (CREATED/FAILED) NAO sao tocados — sobrescrever conclusao mais
  -- nova e exatamente o que o fencing existe para impedir.
  IF v_step.state = 'IN_FLIGHT' THEN
    UPDATE public.trafego_meta_create_step
       SET state = 'AMBIGUOUS',
           claim_token = NULL, claim_owner = NULL, claimed_at = NULL,
           claim_generation = v_step.claim_generation + 1,
           fenced_at = clock_timestamp(),
           updated_at = clock_timestamp()
     WHERE step_id = p_step_ref;
  END IF;

  RETURN jsonb_build_object(
    'ok', true,
    'step_ref', p_step_ref::text,
    'recorded_as', CASE WHEN v_ja_conhecido THEN 'ALREADY_CONCLUDED' ELSE 'OBSERVED_WITHOUT_AUTHORITY' END,
    'state', CASE WHEN v_step.state = 'IN_FLIGHT' THEN 'AMBIGUOUS' ELSE v_step.state END,
    'contested', NOT v_ja_conhecido AND v_step.external_object_id IS NOT NULL
  );
END
$$;

-- -----------------------------------------------------------------------------
-- 7. A conclusao por LEITURA, que e a autoridade da recuperacao
-- -----------------------------------------------------------------------------
CREATE FUNCTION public.trafego_meta_create_conclude_by_recovery(
  p_step_ref uuid,
  p_external_object_id text,
  p_evidence jsonb,
  p_error_code text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_step public.trafego_meta_create_step%ROWTYPE;
  v_at timestamptz := clock_timestamp();
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  IF p_external_object_id !~ '^[0-9]{1,40}$' THEN
    RAISE EXCEPTION 'META_EXTERNAL_ID_INVALID';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_step_ref::text, 1602));
  SELECT * INTO v_step FROM public.trafego_meta_create_step
   WHERE step_id = p_step_ref FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'META_STEP_NOT_FOUND'; END IF;

  IF v_step.state NOT IN ('AMBIGUOUS','CREATED') THEN
    -- IN_FLIGHT tem dono vivo ate prova em contrario, e FAILED ja e conclusao.
    -- A recuperacao le; ela nao arranca a caneta de quem esta escrevendo.
    RAISE EXCEPTION 'META_STEP_NOT_RECOVERABLE';
  END IF;
  IF v_step.external_object_id IS NOT NULL
     AND v_step.external_object_id <> p_external_object_id THEN
    -- Identidade divergente NUNCA e sobrescrita: o passo ja aponta para outro
    -- objeto, e trocar o ponteiro apagaria a prova de qual deles existe.
    RAISE EXCEPTION 'META_EXTERNAL_ID_DIVERGED';
  END IF;

  UPDATE public.trafego_meta_create_step
     SET state = 'CREATED',
         external_object_id = p_external_object_id,
         closed_at = coalesce(closed_at, v_at),
         -- A leitura supera qualquer reivindicacao aberta: ela provou o que o
         -- despacho nao conseguiu declarar.
         claim_token = NULL, claim_owner = NULL, claimed_at = NULL,
         claim_generation = v_step.claim_generation + 1,
         fenced_at = CASE WHEN v_step.claim_token IS NOT NULL THEN v_at ELSE fenced_at END,
         updated_at = v_at
   WHERE step_id = p_step_ref;

  IF p_evidence IS NOT NULL THEN
    PERFORM public.trafego_meta_create_record_readback(
      p_step_ref, p_evidence, p_error_code, NULL);
  END IF;

  RETURN jsonb_build_object(
    'ok', true,
    'step_ref', p_step_ref::text,
    'state', 'CREATED',
    'concluded_by', 'RECOVERY_READ',
    'readback_recorded', p_evidence IS NOT NULL
  );
END
$$;

-- -----------------------------------------------------------------------------
-- 8. reclaim_orphan continua promovendo por idade — e agora TAMBEM cerca
-- -----------------------------------------------------------------------------
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
  v_generation integer;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();

  IF p_min_age_seconds IS NULL OR p_min_age_seconds NOT BETWEEN 60 AND 86400 THEN
    RAISE EXCEPTION 'META_ORPHAN_RECLAIM_AGE_INVALID';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_step_ref::text, 1604));

  -- ⚠️ A IDADE CONTINUA SENDO ELEGIBILIDADE, NAO PROVA DE MORTE. O que mudou e
  -- que a promocao agora REVOGA a reivindicacao: o trabalhador antigo pode
  -- estar vivo, pode voltar, e a partir daqui ele nao concluira nada. Sem esta
  -- revogacao a promocao anunciava a duvida e deixava a caneta na mao de quem
  -- a causou — que era o defeito medido.
  UPDATE public.trafego_meta_create_step
     SET state = 'AMBIGUOUS',
         claim_token = NULL, claim_owner = NULL, claimed_at = NULL,
         claim_generation = claim_generation + 1,
         fenced_at = v_reclaimed_at,
         updated_at = v_reclaimed_at
   WHERE step_id = p_step_ref
     AND state = 'IN_FLIGHT'
     AND prepared_at <= v_reclaimed_at - make_interval(secs => p_min_age_seconds)
   RETURNING prepared_at, claim_generation INTO v_prepared_at, v_generation;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'META_STEP_ORPHAN_NOT_RECLAIMABLE';
  END IF;

  RETURN jsonb_build_object(
    'ok', true,
    'step_ref', p_step_ref::text,
    'state', 'AMBIGUOUS',
    'claim_generation', v_generation,
    'prepared_at', v_prepared_at,
    'reclaimed_at', v_reclaimed_at
  );
END
$$;

-- -----------------------------------------------------------------------------
-- 9. Manifesto interno: o ID resolvido e a confirmacao, para a recuperacao
-- -----------------------------------------------------------------------------
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

-- -----------------------------------------------------------------------------
-- 10. Recibo do navegador: a confirmacao duravel, ainda sem id nenhum
-- -----------------------------------------------------------------------------
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

-- -----------------------------------------------------------------------------
-- 11. Autoridade: nada disto e executavel por anon/authenticated
-- -----------------------------------------------------------------------------
REVOKE ALL ON FUNCTION public.trafego_meta_create_exigir_claim(
  public.trafego_meta_create_step, uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_prepare_step(text,uuid,text,text,text)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_close_step(uuid,text,uuid)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_mark_ambiguous(uuid,uuid)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_fail_step(uuid,text,uuid)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_record_readback(uuid,jsonb,text,uuid)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_flag_readback(uuid,text,uuid)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_record_fenced_dispatch(uuid,uuid,text)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_conclude_by_recovery(uuid,text,jsonb,text)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_reclaim_orphan(uuid,integer)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_approval_manifest(uuid)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_receipt(uuid)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.trafego_meta_create_prepare_step(text,uuid,text,text,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_close_step(uuid,text,uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_mark_ambiguous(uuid,uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_fail_step(uuid,text,uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_record_readback(uuid,jsonb,text,uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_flag_readback(uuid,text,uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_record_fenced_dispatch(uuid,uuid,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_conclude_by_recovery(uuid,text,jsonb,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_reclaim_orphan(uuid,integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_approval_manifest(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_receipt(uuid) TO service_role;

DO $verificacao$
DECLARE faltando text;
BEGIN
  SELECT string_agg(assinatura, ', ' ORDER BY assinatura) INTO faltando
    FROM unnest(ARRAY[
      'trafego_meta_create_close_step(uuid,text,uuid)',
      'trafego_meta_create_mark_ambiguous(uuid,uuid)',
      'trafego_meta_create_fail_step(uuid,text,uuid)',
      'trafego_meta_create_record_readback(uuid,jsonb,text,uuid)',
      'trafego_meta_create_record_fenced_dispatch(uuid,uuid,text)',
      'trafego_meta_create_conclude_by_recovery(uuid,text,jsonb,text)'
    ]) AS assinatura
   WHERE to_regprocedure('public.' || assinatura) IS NULL;
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION 'meta_worker_fencing nao criou: %', faltando;
  END IF;
  -- As assinaturas ANTIGAS precisam ter sumido: mante-las faria um transporte
  -- desatualizado continuar concluindo sem cerca nenhuma, que e o buraco.
  SELECT string_agg(assinatura, ', ' ORDER BY assinatura) INTO faltando
    FROM unnest(ARRAY[
      'trafego_meta_create_close_step(uuid,text)',
      'trafego_meta_create_mark_ambiguous(uuid)',
      'trafego_meta_create_fail_step(uuid,text)',
      'trafego_meta_create_record_readback(uuid,jsonb,text)'
    ]) AS assinatura
   WHERE to_regprocedure('public.' || assinatura) IS NOT NULL;
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION 'meta_worker_fencing deixou assinatura sem cerca viva: %', faltando;
  END IF;
  RAISE NOTICE 'meta_worker_fencing OK: cerca versionada ativa em close/ambiguous/fail/readback';
END
$verificacao$;

COMMIT;
