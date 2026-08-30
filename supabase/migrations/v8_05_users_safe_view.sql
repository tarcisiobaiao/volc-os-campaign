-- =============================================================================
-- v8_05 — View/DTO public.users_safe: superficie de leitura sem coluna sensivel
-- SPRINT 1A / FRENTE 2 — CONTENCAO DE SEGURANCA. ARQUIVO. NAO APLICADO.
-- =============================================================================
-- APLICAR COMO: postgres (cria view em public; nao altera public.users)
--   -- (comando de aplicacao: ver runbook privado de infraestrutura)
--     -- (comando de aplicacao: ver runbook privado de infraestrutura)
--
-- DEPENDE DE: v8_03 (RLS ligada), v8_04 (grants). NAO e destrutivo.
-- HABILITA: v8_06 — este arquivo entrega o substituto ANTES de tirar o acesso.
--
-- -----------------------------------------------------------------------------
-- PROBLEMA QUE RESOLVE
-- -----------------------------------------------------------------------------
-- O item 4 do escopo pede proteger password_hash, token_primeiro_acesso e
-- token_expiracao. Revogar SELECT dessas colunas de `authenticated` (v8_06)
-- quebra qualquer consulta que peca `*`, porque PostgREST expande `select=*`
-- para todas as colunas do cache de schema e o Postgres devolve 42501
-- (permission denied for column). Consumidores medidos que pedem `*`:
--   src/hooks/useUserProfile.ts:62   -> .from('users').select('*').eq('id', ...)
--   src/hooks/useUserProfile.ts:72   -> .from('users').select('*').eq('email', ...)
--
-- Os demais consumidores ja pedem colunas nominais e nao sao afetados:
--   src/services/usersService.ts:26,128,215 -> id,name,email,role,commission_percentage,created_at
--   src/v6/services/*.ts                    -> id,name,email,role,commission_percentage
--   src/services/incubatorService.ts:43     -> id
--   src/pages/ChangePassword.tsx:88         -> UPDATE de needs_password_change
--
-- Esta view e o destino para o qual esses dois `select('*')` devem migrar.
-- A troca no frontend NAO e feita aqui (propriedade da Frente 1/3).
--
-- -----------------------------------------------------------------------------
-- DECISOES
-- -----------------------------------------------------------------------------
-- security_invoker = true (PostgreSQL 15+; medido: 15.8). A view roda com os
-- privilegios e a RLS de QUEM CONSULTA, nao do dono. Sem isso a view viraria um
-- bypass de RLS: qualquer autenticado leria a linha de todo mundo, exatamente o
-- buraco que v8_03 fechou.
--
-- security_barrier = true: impede que uma funcao barata injetada no WHERE do
-- chamador seja avaliada antes do filtro da view e vaze linha por canal lateral.
--
-- A view NAO e atualizavel na pratica sob RLS + grants por coluna, e nem
-- pretende ser: escrita continua em public.users, sob as policies de v8_03.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

DO $guard$
BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION
      'v8_05 exige PostgreSQL 15+ para security_invoker (encontrado: %)',
      current_setting('server_version');
  END IF;
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid='public.users'::regclass) THEN
    RAISE EXCEPTION
      'v8_05 abortada: RLS desligada em public.users. Com security_invoker e '
      'sem RLS a view nao filtra nada. Aplique v8_03 antes.';
  END IF;
END
$guard$;

DROP VIEW IF EXISTS public.users_safe;

CREATE VIEW public.users_safe
WITH (security_invoker = true, security_barrier = true) AS
SELECT
  u.id,
  u.name,
  u.email,
  u.role,
  u.first_login,
  u.needs_password_change,
  u.commission_percentage,
  u.created_at,
  u.updated_at
FROM public.users u;

COMMENT ON VIEW public.users_safe IS
  'DTO de leitura de public.users sem password_hash, token_primeiro_acesso e '
  'token_expiracao. security_invoker: herda a RLS do chamador (v8_03). '
  'Destino dos dois select(*) em src/hooks/useUserProfile.ts (62 e 72) antes '
  'de aplicar v8_06.';

-- pg_default_acl concede arwdDxt em objeto novo de public para anon,
-- authenticated e service_role. REVOKE nominal, senao a view nasce aberta —
-- e uma view aberta sobre uma tabela fechada anula v8_04.
REVOKE ALL ON TABLE public.users_safe FROM PUBLIC;
REVOKE ALL ON TABLE public.users_safe FROM anon;
REVOKE ALL ON TABLE public.users_safe FROM authenticated;
REVOKE ALL ON TABLE public.users_safe FROM service_role;

GRANT SELECT ON TABLE public.users_safe TO authenticated;
GRANT SELECT ON TABLE public.users_safe TO service_role;
-- anon: nada.

DO $verify$
DECLARE
  v_cols int;
BEGIN
  SELECT count(*) INTO v_cols
  FROM information_schema.columns
  WHERE table_schema = 'public' AND table_name = 'users_safe'
    AND column_name IN ('password_hash', 'token_primeiro_acesso', 'token_expiracao');
  IF v_cols > 0 THEN
    RAISE EXCEPTION 'v8_05 falhou: users_safe expoe coluna sensivel';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.role_table_grants
    WHERE table_schema='public' AND table_name='users_safe' AND grantee='anon'
  ) THEN
    RAISE EXCEPTION 'v8_05 falhou: anon tem privilegio em public.users_safe';
  END IF;

  RAISE NOTICE 'v8_05: public.users_safe criada com 9 colunas, security_invoker, sem anon';
END
$verify$;

COMMIT;

-- =============================================================================
-- VERIFICACAO POS-APLICACAO (somente leitura)
-- =============================================================================
-- SELECT column_name FROM information_schema.columns
--  WHERE table_schema='public' AND table_name='users_safe' ORDER BY ordinal_position;
-- SELECT c.reloptions FROM pg_class c WHERE c.oid='public.users_safe'::regclass;
--   -- deve conter security_invoker=true e security_barrier=true
