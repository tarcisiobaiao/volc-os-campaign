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
     OR to_regclass('public.trafego_meta_create_step') IS NOT NULL
     OR to_regclass('public.trafego_meta_validation_receipt') IS NOT NULL THEN
    RAISE EXCEPTION 'meta_create_paused_executor ja parece aplicado; rode o rollback correspondente';
  END IF;
END
$guarda$;

-- =============================================================================
-- RECIBO DURAVEL DO validate_only
-- =============================================================================
-- Antes desta tabela a prova de que a Meta aceitou o plano existia SO no corpo
-- da resposta HTTP, ou seja, so no navegador. Uma aprovacao que aceitasse essa
-- afirmacao estaria confiando no cliente para dizer "eu fui validado" — e um
-- recibo verde inventado pelo browser e exatamente o que separa uma autoridade
-- de um enfeite.
--
-- Quem escreve aqui e o servidor, DEPOIS de a Meta ter respondido `success` a
-- uma chamada com `execution_options=["validate_only"]`. O browser nunca
-- alcanca esta tabela: `anon` e `authenticated` nao tem grant nenhum, e nem
-- `service_role` tem INSERT — so a RPC escreve.
CREATE TABLE public.trafego_meta_validation_receipt (
  validation_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider             text NOT NULL DEFAULT 'META_ADS',
  capability           text NOT NULL DEFAULT 'META_VALIDATE_ONLY',
  plan_sha256          text NOT NULL,
  account_ref          text NOT NULL,
  actor_id             text NOT NULL,
  api_version          text NOT NULL DEFAULT 'v26.0',
  coverage             text NOT NULL,
  steps_validated      text[] NOT NULL,
  steps_pending        text[] NOT NULL,
  operations_total     smallint NOT NULL,
  objects_created      smallint NOT NULL,
  accepted             boolean NOT NULL,
  validated_at         timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT trafego_meta_validation_receipt_provider CHECK (provider = 'META_ADS'),
  CONSTRAINT trafego_meta_validation_receipt_capability CHECK (capability = 'META_VALIDATE_ONLY'),
  CONSTRAINT trafego_meta_validation_receipt_hash CHECK (plan_sha256 ~ '^[a-f0-9]{64}$'),
  CONSTRAINT trafego_meta_validation_receipt_account_ref CHECK (account_ref ~ '^[A-Za-z0-9:_-]{8,180}$'),
  CONSTRAINT trafego_meta_validation_receipt_actor CHECK (length(btrim(actor_id)) BETWEEN 1 AND 200),
  CONSTRAINT trafego_meta_validation_receipt_api CHECK (api_version = 'v26.0'),
  -- A cobertura e literal de proposito. `INDEPENDENT_ROOTS_ONLY` e a UNICA
  -- cobertura que o `validar_raizes` sabe produzir; gravar qualquer outra
  -- palavra deixaria uma aprovacao futura acreditar numa validacao mais ampla
  -- do que a que aconteceu.
  CONSTRAINT trafego_meta_validation_receipt_coverage CHECK (coverage = 'INDEPENDENT_ROOTS_ONLY'),
  -- ⚠️ Um recibo de validacao com objeto criado nao e um recibo de validacao.
  -- A coluna existe para que a afirmacao "zero objetos" seja GRAVADA, e nao
  -- apenas subentendida pelo nome da tabela.
  CONSTRAINT trafego_meta_validation_receipt_clean CHECK (objects_created = 0),
  CONSTRAINT trafego_meta_validation_receipt_accepted CHECK (accepted),
  -- ⚠️ `cardinality`, nunca `array_length`: `array_length(ARRAY[], 1)` devolve
  -- NULL e um CHECK com NULL passa. `steps_pending` PODE ser vazio (uma receita
  -- sem operacoes dependentes), `steps_validated` nao — um recibo que nao
  -- validou nada nao prova nada.
  CONSTRAINT trafego_meta_validation_receipt_manifesto CHECK (
    cardinality(steps_validated) BETWEEN 1 AND 22
    AND array_position(steps_validated, NULL) IS NULL
    AND array_position(steps_pending, NULL) IS NULL
    AND operations_total = cardinality(steps_validated) + cardinality(steps_pending)
    AND operations_total BETWEEN 1 AND 22
  )
);
CREATE INDEX trafego_meta_validation_receipt_plan_ix
  ON public.trafego_meta_validation_receipt (plan_sha256, validated_at DESC);

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
  -- Quantidade de operacoes que o operador CONFERIU na tela. Redundante com
  -- cardinality(steps_expected) de proposito: o numero que a interface mostrou
  -- fica gravado como numero, e o CHECK abaixo prova que os dois concordam.
  operations_expected  smallint NOT NULL,
  -- ⚠️ O recibo duravel do validate_only que sustenta esta aprovacao. NOT NULL
  -- e a regra inteira: nao existe aprovacao sem uma validacao remota gravada
  -- pelo servidor para o MESMO hash. UNIQUE porque um recibo autoriza uma
  -- aprovacao e so uma — reaprovar depois de expirar exige validar de novo,
  -- e e isso que impede o replay de uma prova velha.
  validation_id        uuid NOT NULL UNIQUE
                       REFERENCES public.trafego_meta_validation_receipt (validation_id)
                       ON DELETE RESTRICT,
  -- A confirmacao humana de que o que vai nascer nasce PAUSADO. Nao e um campo
  -- informativo: o CHECK recusa `false`, entao uma aprovacao sem essa frase
  -- nao existe no banco.
  paused_birth_confirmed boolean NOT NULL,
  -- O pedido do operador — referencias OPACAS e texto dele, nunca id bruto da
  -- Meta, image_hash ou token. E o que permite a rota de criacao receber so o
  -- `approval_id` e recompilar o plano no servidor, em vez de aceitar um
  -- payload Meta vindo do navegador.
  plan_request         jsonb NOT NULL,
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
  CONSTRAINT trafego_meta_create_approval_operacoes CHECK (
    operations_expected = cardinality(steps_expected)),
  -- A frase e um portao, nao um rotulo. `false` nao vira linha.
  CONSTRAINT trafego_meta_create_approval_paused CHECK (paused_birth_confirmed),
  CONSTRAINT trafego_meta_create_approval_pedido CHECK (
    jsonb_typeof(plan_request) = 'object' AND length(plan_request::text) <= 60000),
  -- ⚠️ EXPIRACAO CURTA, com teto no proprio banco. `expires_at > approved_at`
  -- sozinho aceitaria uma aprovacao valida por um ano — uma autorizacao de
  -- gasto esquecida numa aba. Uma hora e o teto absoluto; a rota escolhe uma
  -- janela bem menor e o banco garante que ninguem a alargue por fora.
  CONSTRAINT trafego_meta_create_approval_expiry CHECK (
    expires_at > approved_at AND expires_at <= approved_at + interval '1 hour'),
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
  -- ⚠️ O OBJETO EXISTE, MAS NAO E O QUE FOI APROVADO.
  --
  -- O recibo fecha ANTES do read-back de proposito: o id que a Meta acabou de
  -- devolver precisa estar gravado antes de qualquer outra coisa, senao uma
  -- queda entre o POST e o INSERT perde para sempre a unica prova de que o
  -- objeto nasceu. Inverter essa ordem trocaria um problema pequeno (um
  -- CREATED com read-back divergente) por um grande (um objeto orfao sem
  -- registro nenhum).
  --
  -- O preco dessa ordem e que um read-back divergente deixava o recibo
  -- dizendo apenas CREATED, e quem lesse o recibo depois concluiria que
  -- estava tudo certo. Esta coluna e o registro duravel dessa divergencia.
  readback_error       text,
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
  -- Divergencia de leitura so faz sentido sobre um objeto que existe.
  CONSTRAINT trafego_meta_create_step_readback CHECK (
    readback_error IS NULL
    OR (state = 'CREATED' AND readback_error ~ '^[A-Z0-9_]{3,100}$')),
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
-- ⚠️ A IDENTIDADE DO OBJETO NA CONTA, e nao dentro da aprovacao.
--
-- `UNIQUE (approval_id, step_name)` protege UMA saga contra si mesma. Ele nao
-- protege a conta contra DUAS sagas: o `plan_sha256` cobre o plano inteiro,
-- entao mudar a headline de um anuncio produz outro hash — e o payload da
-- Campaign continua byte a byte o mesmo. Sem este indice, a segunda aprovacao
-- comeca de novo em `campaign`, recebe DESPACHAR e cria a MESMA campanha pela
-- segunda vez na conta.
--
-- `trafego_meta_create_prepare_step` consulta por aqui antes de despachar. Nao
-- e UNIQUE: quando um passo identico ja existe CRIADO, a nova saga grava a
-- propria linha CRIADA com o mesmo id externo e segue sem POST.
CREATE INDEX trafego_meta_create_step_identidade_ix
  ON public.trafego_meta_create_step (step_name, payload_sha256, state);

ALTER TABLE public.trafego_meta_validation_receipt ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_meta_validation_receipt FORCE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_meta_create_approval ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_meta_create_approval FORCE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_meta_create_step ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_meta_create_step FORCE ROW LEVEL SECURITY;

-- ⚠️ service_role tambem entra no REVOKE. O default ACL do Supabase concede
-- ALL em public, e sem esta linha o backend poderia gravar recibo direto na
-- tabela, contornando as RPCs transacionais que sao a unica autoridade da
-- saga. Ler o recibo continua permitido; escrever, so pela funcao.
REVOKE ALL ON public.trafego_meta_validation_receipt FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON public.trafego_meta_create_approval FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON public.trafego_meta_create_step FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.trafego_meta_validation_receipt TO service_role;
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

-- Grava a prova de que a Meta aceitou este plano exato sob `validate_only`.
--
-- Chamada pelo servidor DEPOIS da resposta da Meta, nunca antes. O navegador
-- nao tem caminho ate aqui: ele recebe apenas o `validation_id` opaco, e um
-- `validation_id` inventado nao existe na tabela — a aprovacao para em
-- META_VALIDATION_RECEIPT_NOT_FOUND.
CREATE FUNCTION public.trafego_meta_create_record_validation(
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
     WHERE passo !~ '^(campaign|adset|creative(?::[a-z0-9][a-z0-9_-]{0,31})?|ad(?::[a-z0-9][a-z0-9_-]{0,31})?)$'
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
  p_plan_request jsonb
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

  -- ⚠️ UMA APROVAÇÃO VIVA POR PLANO — o portão que impede nascer duas vezes.
  --
  -- A idempotência dos passos é por approval_id (UNIQUE (approval_id,
  -- step_name)), então duas aprovações do MESMO plano produzem dois livros de
  -- passos independentes, cada um passando por todas as verificações, e a mesma
  -- campanha nasce duas vezes na conta. `plan_sha256` é a identidade canônica
  -- do plano: o hash é calculado sobre a matéria compilada, que já inclui
  -- account_ref e todos os payloads (compilador.py:197-215).
  --
  -- NÃO é um UNIQUE permanente. Um UNIQUE em plan_sha256 barraria para sempre;
  -- um UNIQUE parcial `WHERE state = 'APPROVED'` barraria depois da expiração,
  -- porque uma aprovação expirada continua APPROVED. Ambos transformariam uma
  -- reaprovação legítima em trabalho de DBA.
  --
  -- O lock consultivo é transacional e cobre exatamente a janela entre o
  -- SELECT e o INSERT: sem ele, duas chamadas simultâneas para o mesmo plano
  -- leem "não existe" ao mesmo tempo e ambas inserem. Salt 1602 mantém este
  -- espaço de chaves separado do 1601 de prepare_step.
  IF p_plan_sha256 !~ '^[a-f0-9]{64}$' THEN
    RAISE EXCEPTION 'META_APPROVAL_PLAN_HASH_INVALID';
  END IF;

  -- ⚠️ A CONFIRMACAO HUMANA E UM PARAMETRO, NAO UM PRESSUPOSTO.
  -- Se a rota esquecesse de exigir a frase digitada, o banco ainda recusaria.
  IF p_paused_birth_confirmed IS NOT TRUE THEN
    RAISE EXCEPTION 'META_PAUSED_BIRTH_NOT_CONFIRMED';
  END IF;
  IF p_currency IS DISTINCT FROM 'BRL' THEN
    RAISE EXCEPTION 'META_CURRENCY_UNSUPPORTED';
  END IF;
  IF p_plan_request IS NULL OR jsonb_typeof(p_plan_request) <> 'object' THEN
    RAISE EXCEPTION 'META_APPROVAL_PLAN_REQUEST_INVALID';
  END IF;
  IF p_expires_at IS NULL OR p_expires_at <= clock_timestamp() THEN
    RAISE EXCEPTION 'META_APPROVAL_EXPIRY_INVALID';
  END IF;
  IF p_expires_at > clock_timestamp() + interval '1 hour' THEN
    RAISE EXCEPTION 'META_APPROVAL_EXPIRY_TOO_LONG';
  END IF;

  -- ⚠️ A APROVACAO SO EXISTE SOBRE UMA VALIDACAO GRAVADA PELO SERVIDOR.
  --
  -- Cada campo abaixo e uma forma diferente de o recibo nao descrever ESTE
  -- ato: outro plano, outra conta, outra pessoa, cobertura menor, objeto
  -- criado, prova velha, manifesto diferente. Recusar cada uma pelo nome faz o
  -- operador ler a causa em vez de "aprovacao invalida".
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
  -- A janela e curta de proposito: uma prova de ontem nao descreve a conta de
  -- hoje. `clock_timestamp()` anda dentro da transacao, entao a idade e real.
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
       -- Uma saga que já falhou está gasta: o passo FALHO nunca volta a
       -- DESPACHAR (META_STEP_PREVIOUSLY_FAILED), então segurar o plano refém
       -- dela até a expiração seria prender o operador a um livro morto.
       -- AMBIGUOUS NÃO entra aqui de propósito: ambíguo significa que pode ter
       -- nascido objeto, e reaprovar antes de reconciliar é exatamente a
       -- duplicação que este portão existe para impedir.
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
    steps_expected, operations_expected, validation_id, paused_birth_confirmed, plan_request
  ) VALUES (
    p_plan_sha256, p_account_ref, p_actor_id, p_daily_budget_minor, p_currency, p_expires_at,
    p_steps_expected, cardinality(p_steps_expected)::smallint, p_validation_id,
    p_paused_birth_confirmed, p_plan_request
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

  -- ⚠️ A MESMA CAMPANHA NAO PODE NASCER POR DUAS APROVACOES.
  --
  -- `UNIQUE (approval_id, step_name)` protege UMA saga contra si mesma, e a
  -- aprovacao unica por `plan_sha256` protege UM plano contra si mesmo. Nenhum
  -- dos dois protege a CONTA, e o buraco entre eles e concreto:
  --
  --   1. o operador aprova P1 e a campanha nasce;
  --   2. o AdSet falha, o que LIBERA o plano para nova aprovacao;
  --   3. o operador corrige a headline de um anuncio;
  --   4. mudar um filho muda o `plan_sha256` do plano INTEIRO, mas o payload da
  --      Campaign continua byte a byte o mesmo;
  --   5. P2 e aprovado, o ledger novo comeca em `campaign` e responde
  --      DESPACHAR — e a mesma campanha nasce pela segunda vez.
  --
  -- A identidade que importa aqui nao e a do plano: e a do OBJETO na conta, ou
  -- seja, (conta, tipo de passo, payload resolvido). Um passo identico ja
  -- CRIADO e retomado sem POST; um identico em voo ou ambiguo obriga a
  -- reconciliar antes de qualquer coisa.
  --
  -- O lock consultivo cobre a janela entre a sonda e o INSERT: sem ele, duas
  -- aprovacoes simultaneas leem "nao existe" ao mesmo tempo e ambas despacham.
  -- Salt 1603, separado do 1601 (aprovacao) e do 1602 (plano).
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
      -- Pode existir objeto do outro lado. Despachar aqui e a duplicacao.
      RAISE EXCEPTION 'META_STEP_DUPLICATE_IN_FLIGHT';
    END IF;
    -- O objeto ja existe e e exatamente este. A saga nova o adota, com o mesmo
    -- id externo, e segue sem um unico POST.
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

-- ⚠️ RECONCILIACAO: o unico caminho de AMBIGUOUS para FAILED.
--
-- `trafego_meta_create_fail_step` so aceita IN_FLIGHT, e isso e correto: um
-- passo em voo que a Meta recusou por escrito e uma falha provada. AMBIGUOUS e
-- outra coisa — pode existir objeto do outro lado — e so pode ser encerrado
-- depois de alguem PROVAR a ausencia por leitura. Esta funcao e o registro
-- dessa prova, e o unico caminho de volta.
--
-- O caminho oposto — provar que o objeto EXISTE — nao precisa de funcao nova:
-- `trafego_meta_create_close_step` ja aceita AMBIGUOUS -> CREATED com o id
-- lido, e ja recusa um id diferente do gravado.
CREATE FUNCTION public.trafego_meta_create_resolve_absent(
  p_step_ref uuid, p_error_code text, p_idade_minima_s integer DEFAULT 120
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE v_step public.trafego_meta_create_step%ROWTYPE;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  IF p_error_code !~ '^[A-Z0-9_]{3,100}$' THEN
    RAISE EXCEPTION 'META_STEP_ERROR_CODE_INVALID';
  END IF;
  IF p_idade_minima_s IS NULL OR p_idade_minima_s < 60 OR p_idade_minima_s > 3600 THEN
    RAISE EXCEPTION 'META_RECONCILE_WINDOW_INVALID';
  END IF;

  SELECT * INTO v_step FROM public.trafego_meta_create_step
   WHERE step_id = p_step_ref FOR UPDATE;
  IF NOT FOUND OR v_step.state <> 'AMBIGUOUS' THEN
    RAISE EXCEPTION 'META_STEP_NOT_AMBIGUOUS';
  END IF;

  -- ⚠️ AUSENCIA NAO PODE SER PROVADA ENQUANTO ALGUEM AINDA PODE DESPACHAR.
  --
  -- O passo vira AMBIGUOUS assim que uma segunda chamada reentra nele — e isso
  -- pode acontecer com a PRIMEIRA ainda dentro do `await` do POST, antes de a
  -- Meta receber qualquer coisa. Uma reconciliacao imediata listaria a conta,
  -- nao acharia nada, fecharia FALHO, e o POST original criaria o objeto
  -- depois, com o livro ja dizendo que ele nao existe. O resultado seria
  -- exatamente o que esta lane existe para impedir: uma nova aprovacao
  -- liberada sobre um objeto vivo.
  --
  -- O cliente HTTP da criacao tem timeout de 20 s. Dois minutos e folga
  -- suficiente para que nenhum despachante ainda tenha autoridade para enviar.
  -- Nao e um lease — e um piso temporal, e o risco residual (uma requisicao
  -- patologicamente lenta) esta declarado em REMAINING-RISKS.
  IF greatest(v_step.prepared_at, v_step.updated_at)
     > clock_timestamp() - make_interval(secs => p_idade_minima_s) THEN
    RAISE EXCEPTION 'META_RECONCILE_TOO_SOON';
  END IF;

  UPDATE public.trafego_meta_create_step
     SET state = 'FAILED', error_code = p_error_code,
         closed_at = clock_timestamp(), updated_at = clock_timestamp()
   WHERE step_id = p_step_ref;
  RETURN jsonb_build_object('ok', true, 'state', 'FAILED');
END
$$;

-- ⚠️ Registro duravel de um read-back que divergiu DEPOIS de o recibo fechar.
--
-- O objeto existe — a Meta devolveu id e o ledger o gravou — mas ele nao e o
-- que foi aprovado. Sem esta marca o recibo diria apenas CREATED, e quem o
-- lesse depois concluiria que estava tudo certo. A resposta HTTP ja diz 502; o
-- livro precisa dizer o mesmo.
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

-- Leitura do recibo de validacao, para a rota poder recusar ANTES do Keychain.
--
-- A autoridade continua sendo `trafego_meta_create_approve`, que reconfere
-- tudo. Esta funcao existe só para que um `validation_id` inventado, de outra
-- pessoa ou velho pare o pedido sem que o token seja lido e sem que a Meta
-- receba uma unica requisicao de leitura.
CREATE FUNCTION public.trafego_meta_create_validation_lookup(p_validation_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
SET search_path = pg_catalog, public
AS $$
DECLARE v public.trafego_meta_validation_receipt%ROWTYPE;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  SELECT * INTO v FROM public.trafego_meta_validation_receipt
   WHERE validation_id = p_validation_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'META_VALIDATION_RECEIPT_NOT_FOUND'; END IF;
  RETURN jsonb_build_object(
    'validation_id', v.validation_id::text,
    'plan_sha256', v.plan_sha256,
    'account_ref', v.account_ref,
    'actor_id', v.actor_id,
    'coverage', v.coverage,
    'objects_created', v.objects_created,
    'accepted', v.accepted,
    'operations_total', v.operations_total,
    'validated_at', v.validated_at,
    'idade_s', floor(extract(epoch FROM clock_timestamp() - v.validated_at))::bigint,
    -- Ja usado por alguma aprovacao? Um recibo autoriza uma e so uma.
    'ja_consumido', EXISTS (
      SELECT 1 FROM public.trafego_meta_create_approval a
       WHERE a.validation_id = v.validation_id)
  );
END
$$;

-- O manifesto do lado do SERVIDOR. Diferente de `trafego_meta_create_receipt`,
-- que e a projecao sanitizada para o navegador, esta funcao devolve o que o
-- backend precisa para recompilar o plano sozinho: o pedido do operador, o
-- orcamento aprovado, a moeda, o manifesto e o `step_ref` de cada passo — a
-- chave que a reconciliacao usa para fechar um passo ambiguo.
--
-- Continua sem devolver `external_object_id`: nem o servidor precisa dele para
-- decidir, e nao devolve-lo mantem o id da Meta fora de todo corpo JSON que
-- possa acabar num log.
CREATE FUNCTION public.trafego_meta_create_approval_manifest(p_approval_id uuid)
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
        -- A reconciliacao usa este carimbo para recusar um objeto que ja
        -- existia ANTES de o passo ser preparado: nome igual nao prova
        -- nascimento, mas nascer depois do recibo, sim.
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
    -- O que o operador aprovou, para o recibo poder ser conferido contra o que
    -- ele leu na tela. Sem id externo, sem payload, sem referencia resolvida.
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

REVOKE ALL ON FUNCTION public.trafego_meta_exigir_service_role() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_record_validation(text,text,text,text,text[],text[],integer,integer) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_approve(text,text,text,bigint,text,timestamptz,text[],uuid,integer,boolean,jsonb) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_prepare_step(text,uuid,text,text,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_close_step(uuid,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_mark_ambiguous(uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_fail_step(uuid,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_resolve_absent(uuid,text,integer) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_flag_readback(uuid,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_validation_lookup(uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_approval_manifest(uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_create_receipt(uuid) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.trafego_meta_create_record_validation(text,text,text,text,text[],text[],integer,integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_approve(text,text,text,bigint,text,timestamptz,text[],uuid,integer,boolean,jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_prepare_step(text,uuid,text,text,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_close_step(uuid,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_mark_ambiguous(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_fail_step(uuid,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_resolve_absent(uuid,text,integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_flag_readback(uuid,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_validation_lookup(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_approval_manifest(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_create_receipt(uuid) TO service_role;

COMMIT;
