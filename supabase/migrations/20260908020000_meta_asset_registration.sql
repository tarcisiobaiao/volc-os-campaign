-- =============================================================================
-- Meta Ads v26 — autoridade duravel do REGISTRO DE MIDIA (adimages/advideos)
-- =============================================================================
-- NAO APLICADO POR ESTA MIGRATION. Execute apenas em janela oficial separada,
-- com psql (este arquivo usa metacomando de barra invertida), na ordem que o
-- SCHEMA-DEPLOY-MANIFEST.json declarar.
--
-- ## Por que esta tabela existe
--
-- Registrar midia e um efeito EXTERNO e IRREVERSIVEL: os bytes passam a existir
-- na biblioteca da conta do cliente. Um upload que estoura o tempo nao prova
-- fracasso — o `adimages` pode ter nascido enquanto ninguem olhava. Sem um
-- recibo gravado ANTES do POST, a unica forma de descobrir seria varrer a
-- biblioteca inteira procurando bytes parecidos, e reenviar "por seguranca"
-- criaria um segundo ativo identico.
--
-- Entao a regra e a mesma da saga de criacao (20260904183418): grava e commita
-- a reserva antes do efeito, cerca quem conclui com um `claim_token`, e trata
-- silencio como AMBIGUO em vez de fracasso.
--
-- ## O que ela NAO faz
--
-- Nao cria Campaign, AdSet, Ad nem Creative. Nao guarda bytes, nome de arquivo
-- do operador, token, nem qualquer identificador de pessoa. O que ela guarda e:
-- de qual conta se trata (referencia OPACA), qual o sha256 dos bytes enviados,
-- quem pediu, e o que a Meta respondeu.
--
-- ## A chave de idempotencia
--
-- (account_ref, content_sha256). NAO o nome do arquivo: nome e do operador e
-- muda; os bytes sao o que a Meta indexa. Dois arquivos com nomes diferentes e
-- bytes iguais sao UM registro.
-- =============================================================================
\set ON_ERROR_STOP on

BEGIN;

DO $guarda$
DECLARE faltando text;
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'meta_asset_registration deve rodar como postgres ou supabase_admin; atual: %', current_user;
  END IF;
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'meta_asset_registration exige PostgreSQL 15 ou maior';
  END IF;
  SELECT string_agg(r, ', ' ORDER BY r) INTO faltando
    FROM unnest(ARRAY['anon','authenticated','service_role']) AS r
   WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r);
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION 'meta_asset_registration exige papeis Supabase; ausentes: %', faltando;
  END IF;
  IF to_regclass('public.trafego_meta_asset_registration') IS NOT NULL THEN
    RAISE EXCEPTION 'meta_asset_registration ja parece aplicado; rode o rollback correspondente';
  END IF;
  -- ⚠️ Depende do helper de papel da janela de criacao. Sem ele, qualquer
  -- chamador da RPC escreveria — e a RPC e SECURITY DEFINER.
  IF to_regprocedure('public.trafego_meta_exigir_service_role()') IS NULL THEN
    RAISE EXCEPTION 'meta_asset_registration depende de trafego_meta_exigir_service_role() (20260904183418)';
  END IF;
END
$guarda$;

CREATE TABLE public.trafego_meta_asset_registration (
  registration_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider          text NOT NULL DEFAULT 'META_ADS',
  -- Referencia OPACA da conta, nunca o act_<id> do provedor. E a mesma forma
  -- que o resto da lane usa para nao ligar o handle do navegador ao id real.
  account_ref       text NOT NULL,
  -- sha256 dos BYTES FINAIS EXATOS enviados. Nao do arquivo original.
  content_sha256    text NOT NULL,
  actor_id          text NOT NULL,
  master_ref        text NOT NULL,
  state             text NOT NULL,
  -- So existe quando a Meta devolveu. `NULL` aqui e "ainda nao sei", nunca
  -- "nao tem" — a diferenca e o motivo inteiro do estado AMBIGUO existir.
  image_hash        text,
  failure_code      text,
  claim_token       uuid,
  claim_owner       text,
  claimed_at        timestamptz,
  dispatched_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
  settled_at        timestamptz,
  created_at        timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at        timestamptz NOT NULL DEFAULT clock_timestamp(),

  CONSTRAINT trafego_meta_asset_registration_state CHECK (
    state IN ('DESPACHAR','REGISTRADO','AMBIGUO','FALHOU')),
  CONSTRAINT trafego_meta_asset_registration_sha CHECK (
    content_sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT trafego_meta_asset_registration_account CHECK (
    length(btrim(account_ref)) BETWEEN 8 AND 180),
  CONSTRAINT trafego_meta_asset_registration_actor CHECK (
    length(btrim(actor_id)) BETWEEN 1 AND 200),
  -- ⚠️ REGISTRADO exige hash. Sem esta CHECK, um bug poderia fechar o recibo
  -- dizendo "deu certo" sem saber QUAL peça nasceu — que e exatamente o estado
  -- que o codigo chama de AMBIGUO e trata como perigoso.
  CONSTRAINT trafego_meta_asset_registration_hash_quando_registrado CHECK (
    (state = 'REGISTRADO' AND image_hash IS NOT NULL
       AND length(btrim(image_hash)) BETWEEN 6 AND 160)
    OR (state <> 'REGISTRADO' AND image_hash IS NULL)),
  CONSTRAINT trafego_meta_asset_registration_falha CHECK (
    (state = 'FALHOU' AND failure_code IS NOT NULL)
    OR (state <> 'FALHOU' AND failure_code IS NULL)),
  -- A cerca so pertence a quem tem despacho pendente. Cunhar token para um
  -- recibo ja fechado seria conceder autoridade que ele nao tem.
  CONSTRAINT trafego_meta_asset_registration_cerca CHECK (
    (state = 'DESPACHAR' AND claim_token IS NOT NULL
       AND claim_owner IS NOT NULL AND claimed_at IS NOT NULL)
    OR (state <> 'DESPACHAR' AND claim_token IS NULL))
);

-- A chave de idempotencia, no banco e nao so no codigo. Uma corrida entre dois
-- cliques do operador precisa perder aqui, nao virar dois uploads.
CREATE UNIQUE INDEX trafego_meta_asset_registration_idem_ux
  ON public.trafego_meta_asset_registration (account_ref, content_sha256);

COMMENT ON TABLE public.trafego_meta_asset_registration IS
  'Recibo duravel de registro de midia Meta. Gravado ANTES do POST; timeout vira AMBIGUO e nunca reenvia.';
COMMENT ON COLUMN public.trafego_meta_asset_registration.content_sha256 IS
  'sha256 dos bytes finais exatos enviados ao provedor; e a chave de idempotencia com account_ref.';
COMMENT ON COLUMN public.trafego_meta_asset_registration.image_hash IS
  'NULL significa "ainda nao sei", nunca "nao tem". Ver o estado AMBIGUO.';

ALTER TABLE public.trafego_meta_asset_registration ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_meta_asset_registration FORCE ROW LEVEL SECURITY;

-- ⚠️ service_role tambem entra no REVOKE. O default ACL do Supabase concede
-- CRUD a ele em tabelas novas do schema public; sem revogar, a escrita direta
-- contornaria a RPC e o recibo deixaria de ser autoridade.
REVOKE ALL ON public.trafego_meta_asset_registration FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.trafego_meta_asset_registration TO service_role;

-- =============================================================================
-- RESERVAR — grava e COMMITA antes de qualquer byte sair
-- =============================================================================
CREATE OR REPLACE FUNCTION public.trafego_meta_reservar_registro_ativo(
  p_account_ref text,
  p_content_sha256 text,
  p_actor_id text,
  p_master_ref text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_linha public.trafego_meta_asset_registration;
  v_token uuid;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();

  SELECT * INTO v_linha
    FROM public.trafego_meta_asset_registration
   WHERE account_ref = p_account_ref AND content_sha256 = p_content_sha256
   FOR UPDATE;

  IF FOUND THEN
    -- Ja registrado: devolve o hash que existe. Reenviar criaria um segundo
    -- ativo identico na biblioteca do cliente.
    IF v_linha.state = 'REGISTRADO' THEN
      RETURN jsonb_build_object(
        'estado', 'REGISTRADO', 'image_hash', v_linha.image_hash,
        'reserva_ref', v_linha.registration_id::text);
    END IF;
    -- Ambiguo continua ambiguo. So a leitura da conta resolve.
    IF v_linha.state = 'AMBIGUO' THEN
      RETURN jsonb_build_object(
        'estado', 'AMBIGUO', 'reserva_ref', v_linha.registration_id::text);
    END IF;
    -- Despacho pendente de OUTRO trabalhador: para quem chega agora, o estado
    -- honesto e ambiguo — o POST daquele pode estar no ar neste instante.
    IF v_linha.state = 'DESPACHAR' THEN
      RETURN jsonb_build_object(
        'estado', 'AMBIGUO', 'reserva_ref', v_linha.registration_id::text);
    END IF;
    -- FALHOU: a Meta recusou explicitamente, entao nada nasceu e tentar de
    -- novo e seguro. A cerca e girada.
    v_token := gen_random_uuid();
    UPDATE public.trafego_meta_asset_registration
       SET state = 'DESPACHAR', failure_code = NULL, image_hash = NULL,
           claim_token = v_token, claim_owner = p_actor_id,
           claimed_at = clock_timestamp(), dispatched_at = clock_timestamp(),
           settled_at = NULL, actor_id = p_actor_id, master_ref = p_master_ref,
           updated_at = clock_timestamp()
     WHERE registration_id = v_linha.registration_id;
    RETURN jsonb_build_object(
      'estado', 'DESPACHAR', 'reserva_ref', v_linha.registration_id::text,
      'claim_token', v_token::text);
  END IF;

  v_token := gen_random_uuid();
  INSERT INTO public.trafego_meta_asset_registration (
    account_ref, content_sha256, actor_id, master_ref, state,
    claim_token, claim_owner, claimed_at
  ) VALUES (
    p_account_ref, p_content_sha256, p_actor_id, p_master_ref, 'DESPACHAR',
    v_token, p_actor_id, clock_timestamp()
  ) RETURNING * INTO v_linha;

  RETURN jsonb_build_object(
    'estado', 'DESPACHAR', 'reserva_ref', v_linha.registration_id::text,
    'claim_token', v_token::text);
END;
$$;

-- =============================================================================
-- CONCLUIR / AMBIGUO / FALHAR — os tres fechamentos, todos cercados
-- =============================================================================
CREATE OR REPLACE FUNCTION public.trafego_meta_concluir_registro_ativo(
  p_reserva_ref uuid,
  p_image_hash text,
  p_claim_token uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE v_linha public.trafego_meta_asset_registration;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  SELECT * INTO v_linha FROM public.trafego_meta_asset_registration
   WHERE registration_id = p_reserva_ref FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'META_ASSET_RESERVATION_NOT_FOUND';
  END IF;
  IF v_linha.claim_token IS NULL OR v_linha.claim_token <> p_claim_token THEN
    -- ⚠️ A REQUISICAO JA FOI ENVIADA E O ATIVO PODE EXISTIR. Outro processo
    -- tomou a reivindicacao; concluir por cima sobrescreveria uma decisao mais
    -- nova. A recusa tem nome proprio para o chamador poder trata-la.
    RAISE EXCEPTION 'META_ASSET_CLAIM_FENCED';
  END IF;
  UPDATE public.trafego_meta_asset_registration
     SET state = 'REGISTRADO', image_hash = p_image_hash,
         claim_token = NULL, settled_at = clock_timestamp(),
         updated_at = clock_timestamp()
   WHERE registration_id = p_reserva_ref;
  RETURN jsonb_build_object('estado', 'REGISTRADO');
END;
$$;

CREATE OR REPLACE FUNCTION public.trafego_meta_marcar_registro_ativo_ambiguo(
  p_reserva_ref uuid,
  p_claim_token uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE v_linha public.trafego_meta_asset_registration;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  SELECT * INTO v_linha FROM public.trafego_meta_asset_registration
   WHERE registration_id = p_reserva_ref FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'META_ASSET_RESERVATION_NOT_FOUND';
  END IF;
  IF v_linha.claim_token IS NULL OR v_linha.claim_token <> p_claim_token THEN
    RAISE EXCEPTION 'META_ASSET_CLAIM_FENCED';
  END IF;
  UPDATE public.trafego_meta_asset_registration
     SET state = 'AMBIGUO', claim_token = NULL,
         settled_at = clock_timestamp(), updated_at = clock_timestamp()
   WHERE registration_id = p_reserva_ref;
  RETURN jsonb_build_object('estado', 'AMBIGUO');
END;
$$;

CREATE OR REPLACE FUNCTION public.trafego_meta_falhar_registro_ativo(
  p_reserva_ref uuid,
  p_codigo text,
  p_claim_token uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE v_linha public.trafego_meta_asset_registration;
BEGIN
  PERFORM public.trafego_meta_exigir_service_role();
  SELECT * INTO v_linha FROM public.trafego_meta_asset_registration
   WHERE registration_id = p_reserva_ref FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'META_ASSET_RESERVATION_NOT_FOUND';
  END IF;
  IF v_linha.claim_token IS NULL OR v_linha.claim_token <> p_claim_token THEN
    RAISE EXCEPTION 'META_ASSET_CLAIM_FENCED';
  END IF;
  UPDATE public.trafego_meta_asset_registration
     SET state = 'FALHOU', failure_code = p_codigo, claim_token = NULL,
         settled_at = clock_timestamp(), updated_at = clock_timestamp()
   WHERE registration_id = p_reserva_ref;
  RETURN jsonb_build_object('estado', 'FALHOU');
END;
$$;

REVOKE ALL ON FUNCTION public.trafego_meta_reservar_registro_ativo(text, text, text, text)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_concluir_registro_ativo(uuid, text, uuid)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_marcar_registro_ativo_ambiguo(uuid, uuid)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_falhar_registro_ativo(uuid, text, uuid)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.trafego_meta_reservar_registro_ativo(text, text, text, text)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_concluir_registro_ativo(uuid, text, uuid)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_marcar_registro_ativo_ambiguo(uuid, uuid)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.trafego_meta_falhar_registro_ativo(uuid, text, uuid)
  TO service_role;

COMMIT;
