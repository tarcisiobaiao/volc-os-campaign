-- =============================================================================
-- v8_03 — RLS em public.users + policies explicitas por operacao + gatilhos
-- SPRINT 1A / FRENTE 2 — CONTENCAO DE SEGURANCA. ARQUIVO. NAO APLICADO.
-- =============================================================================
-- APLICAR COMO: supabase_admin  (NAO postgres — ver M6 abaixo)
--   -- (comando de aplicacao: ver runbook privado de infraestrutura)
--     -- (comando de aplicacao: ver runbook privado de infraestrutura)
--
-- DEPENDE DE: v8_01 (app_auth + funcoes), v8_02 (policies do Pautador)
--
-- -----------------------------------------------------------------------------
-- ESTADO REAL MEDIDO EM 2026-08-24
-- -----------------------------------------------------------------------------
-- M1. public.users: relrowsecurity = f, relforcerowsecurity = f.
--     pg_policies para public.users: ZERO linhas.
--     Combinado com os grants plenos de anon (ver v8_04), a tabela e leitura e
--     escrita irrestritas para qualquer portador da anon key — que vai embutida
--     no bundle do browser (src/lib/supabase.ts:10 usa VITE_SUPABASE_ANON_KEY).
--
-- M2. Colunas (12): id, name, email, role, first_login, created_at, updated_at,
--     password_hash, token_primeiro_acesso, token_expiracao,
--     needs_password_change, commission_percentage.
--     CHECK users_role_check: role IN ('ADMIN','OPERATOR','VIEWER').
--     Conteudo: 1 linha, role='ADMIN'; password_hash, token_primeiro_acesso e
--     token_expiracao 100% NULL hoje (count(coluna)=0). Nada e apagado aqui.
--
-- M3. public.users.id NAO e auth.users.id.
--     JOIN por id => 0 linhas. JOIN por lower(email) => 1 linha.
--     Uma policy `id = auth.uid()` sozinha TRANCARIA o unico ADMIN existente
--     para fora. Por isso toda policy de "self" abaixo e
--     `id = auth.uid() OR lower(email) = lower(jwt->>'email')`.
--     As 23 policies do Pautador ja usavam email pelo mesmo motivo.
--
-- M4. public.users e propriedade de supabase_admin. postgres NAO e membro de
--     supabase_admin (pg_has_role = f) e seus grants na tabela tem
--     is_grantable = NO. Logo ENABLE RLS, CREATE POLICY, CREATE TRIGGER e os
--     GRANT/REVOKE de v8_04/v8_06 exigem supabase_admin. Guarda no inicio.
--
-- M5. service_role tem rolbypassrls = t. NENHUMA policy deste arquivo contem os
--     endpoints com service key (api/supabase/*.js, server/index.js:165-403,
--     api/users/query.js:34, api/users/create.js:63). Isso e Frente 1/3.
--     Esta frente fecha anon e authenticated. Dizer o contrario seria falso.
--
-- -----------------------------------------------------------------------------
-- MODELO DE AUTORIZACAO APLICADO
-- -----------------------------------------------------------------------------
--   anon           -> nenhuma policy. Com os grants revogados em v8_04, zero
--                     acesso. anon nao e um usuario; e um portador de chave.
--   authenticated  -> le a propria linha; ADMIN le todas.
--                     escreve a propria linha em colunas nao privilegiadas;
--                     ADMIN escreve/insere/apaga.
--   ADMIN          -> public.volc_current_admin(): papel vem de
--                     app_auth.user_roles pelo sub do JWT. NAO de
--                     public.users.role e NAO de user_metadata.
--
-- POR QUE OS GATILHOS: RLS e por LINHA. WITH CHECK nao enxerga OLD, entao uma
-- policy nao consegue dizer "pode editar a propria linha, mas nao a coluna
-- role". Sem gatilho, `users_update_self` permitiria a um OPERATOR rodar
-- UPDATE users SET role='ADMIN' WHERE id = <ele mesmo> — autopromocao em um
-- request. O gatilho e o que fecha isso.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

-- --- Guardas de pre-condicao ------------------------------------------------
DO $guard$
DECLARE
  v_owner text;
BEGIN
  SELECT pg_get_userbyid(c.relowner) INTO v_owner
  FROM pg_class c WHERE c.oid = 'public.users'::regclass;

  IF NOT pg_has_role(current_user, v_owner, 'USAGE') THEN
    RAISE EXCEPTION
      'v8_03 exige o dono de public.users (%). current_user = %. '
      'Rode: docker exec -i supabase-db psql -U % -v ON_ERROR_STOP=1',
      v_owner, current_user, v_owner;
  END IF;

  IF to_regprocedure('public.volc_current_admin()') IS NULL THEN
    RAISE EXCEPTION 'v8_03 abortada: aplique v8_01 antes';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM app_auth.user_roles
    WHERE role = 'ADMIN' AND revoked_at IS NULL
  ) THEN
    RAISE EXCEPTION
      'v8_03 ABORTADA: nenhum ADMIN ativo em app_auth.user_roles. Ligar a RLS '
      'agora trancaria todo mundo para fora de public.users.';
  END IF;

  IF to_regprocedure('app_auth.tg_users_guard_privileged_columns()') IS NULL
     OR to_regprocedure('app_auth.tg_users_block_last_admin_delete()') IS NULL THEN
    RAISE EXCEPTION 'v8_03 abortada: funcoes de gatilho de v8_01 ausentes';
  END IF;
END
$guard$;

-- =============================================================================
-- 1. LIGA A RLS
-- =============================================================================
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- FORCE aplica a RLS tambem ao dono da tabela. Nao muda nada para service_role
-- (BYPASSRLS, M5), mas impede que uma sessao psql do dono acredite estar
-- testando a policy quando na verdade a esta ignorando.
ALTER TABLE public.users FORCE ROW LEVEL SECURITY;

-- =============================================================================
-- 2. POLICIES — uma por operacao, nomeadas, sem FOR ALL
-- =============================================================================
-- Deliberadamente NAO existe policy para `anon`: ausencia de policy = negacao.

-- --- SELECT ------------------------------------------------------------------
DROP POLICY IF EXISTS users_select_self ON public.users;
CREATE POLICY users_select_self ON public.users
  AS PERMISSIVE FOR SELECT TO authenticated
  USING (
    id = (SELECT auth.uid())
    OR lower(email) = lower(((SELECT auth.jwt()) ->> 'email'))
  );
COMMENT ON POLICY users_select_self ON public.users IS
  'Cada autenticado le a propria linha. O OR por email e obrigatorio: '
  'public.users.id nao casa com auth.users.id (M3).';

DROP POLICY IF EXISTS users_select_admin ON public.users;
CREATE POLICY users_select_admin ON public.users
  AS PERMISSIVE FOR SELECT TO authenticated
  USING (public.volc_current_admin());
COMMENT ON POLICY users_select_admin ON public.users IS
  'ADMIN le todas as linhas. Papel vem de app_auth.user_roles pelo sub do JWT.';

-- --- INSERT ------------------------------------------------------------------
DROP POLICY IF EXISTS users_insert_admin ON public.users;
CREATE POLICY users_insert_admin ON public.users
  AS PERMISSIVE FOR INSERT TO authenticated
  WITH CHECK (public.volc_current_admin());
COMMENT ON POLICY users_insert_admin ON public.users IS
  'So ADMIN cria usuario pelo cliente. O caminho de servico '
  '(api/users/create.js) usa service_role e passa por BYPASSRLS — fechar '
  'aquele endpoint e Frente 1/3.';

-- --- UPDATE ------------------------------------------------------------------
DROP POLICY IF EXISTS users_update_self ON public.users;
CREATE POLICY users_update_self ON public.users
  AS PERMISSIVE FOR UPDATE TO authenticated
  USING (
    id = (SELECT auth.uid())
    OR lower(email) = lower(((SELECT auth.jwt()) ->> 'email'))
  )
  WITH CHECK (
    id = (SELECT auth.uid())
    OR lower(email) = lower(((SELECT auth.jwt()) ->> 'email'))
  );
COMMENT ON POLICY users_update_self ON public.users IS
  'Atende src/pages/ChangePassword.tsx:88 (needs_password_change da propria '
  'linha). O WITH CHECK impede mover a linha para outra identidade. A protecao '
  'de COLUNA e o gatilho tg_users_guard_privileged_columns, nao esta policy.';

DROP POLICY IF EXISTS users_update_admin ON public.users;
CREATE POLICY users_update_admin ON public.users
  AS PERMISSIVE FOR UPDATE TO authenticated
  USING (public.volc_current_admin())
  WITH CHECK (public.volc_current_admin());

-- --- DELETE ------------------------------------------------------------------
DROP POLICY IF EXISTS users_delete_admin ON public.users;
CREATE POLICY users_delete_admin ON public.users
  AS PERMISSIVE FOR DELETE TO authenticated
  USING (public.volc_current_admin());
COMMENT ON POLICY users_delete_admin ON public.users IS
  'Sem policy de DELETE para nao-admin: src/services/usersService.ts:277 '
  'apagava qualquer linha com a anon key.';

-- =============================================================================
-- 3. GATILHOS — o que a RLS nao consegue expressar
-- =============================================================================
DROP TRIGGER IF EXISTS trg_users_guard_privileged_columns ON public.users;
CREATE TRIGGER trg_users_guard_privileged_columns
  BEFORE UPDATE ON public.users
  FOR EACH ROW
  EXECUTE FUNCTION app_auth.tg_users_guard_privileged_columns();

DROP TRIGGER IF EXISTS trg_users_block_last_admin_delete ON public.users;
CREATE TRIGGER trg_users_block_last_admin_delete
  BEFORE DELETE ON public.users
  FOR EACH ROW
  EXECUTE FUNCTION app_auth.tg_users_block_last_admin_delete();

-- =============================================================================
-- 4. CONSTRAINTS E INDICES (item 5 do escopo)
-- =============================================================================
-- Indices ja existentes e conferidos (nao recriados):
--   users_pkey                      UNIQUE (id)
--   users_new_email_key             UNIQUE (email)
--   idx_users_commission_percentage (commission_percentage, role) WHERE role='OPERATOR'
--   idx_users_token_primeiro_acesso (token_primeiro_acesso) WHERE NOT NULL
--
-- users_new_email_key e UNIQUE(email) sensivel a caixa. Todo o modelo de
-- autorizacao — as 23 policies do Pautador, users_select_self acima e o seed de
-- v8_01 — casa por lower(email). Sem o indice abaixo, 'A@x.com' e 'a@x.com'
-- podem coexistir e as policies passam a casar duas identidades diferentes.
-- CREATE UNIQUE INDEX ... IF NOT EXISTS falha se ja houver duplicata por caixa;
-- por isso a verificacao antes, que aborta com mensagem em vez de erro cru.
DO $emailidx$
DECLARE
  v_dups int;
BEGIN
  SELECT count(*) INTO v_dups FROM (
    SELECT lower(email) FROM public.users GROUP BY 1 HAVING count(*) > 1
  ) d;
  IF v_dups > 0 THEN
    RAISE EXCEPTION
      'v8_03 abortada: % email(s) duplicados ignorando caixa em public.users. '
      'Resolva o dado antes — esta migration NAO apaga nem funde linhas.',
      v_dups;
  END IF;
END
$emailidx$;

CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_uniq
  ON public.users (lower(email));

COMMENT ON INDEX public.users_email_lower_uniq IS
  'Garante identidade unica por email ignorando caixa. Pre-requisito de '
  'correcao das policies que casam por lower(email).';

-- Indice de suporte a users_select_self / users_update_self pelo ramo do id.
-- users_pkey ja cobre id; nao ha indice novo necessario para o ramo do email
-- alem de users_email_lower_uniq, que a policy usa diretamente.

-- Constraint de higiene: email nao vazio e sem espaco nas pontas. NOT VALID
-- para nao rejeitar linha legada nenhuma (item "nao apague dado"): passa a
-- valer para INSERT/UPDATE novos; a validacao do historico e decisao a parte.
ALTER TABLE public.users
  DROP CONSTRAINT IF EXISTS users_email_formato_check;
ALTER TABLE public.users
  ADD CONSTRAINT users_email_formato_check
  CHECK (email = btrim(email) AND position('@' in email) > 1)
  NOT VALID;

COMMENT ON CONSTRAINT users_email_formato_check ON public.users IS
  'NOT VALID de proposito: nao toca linha existente. Para validar o historico '
  'depois de conferir: ALTER TABLE public.users VALIDATE CONSTRAINT '
  'users_email_formato_check;';

COMMIT;

-- =============================================================================
-- VERIFICACAO POS-APLICACAO (somente leitura)
-- =============================================================================
-- SELECT relrowsecurity, relforcerowsecurity FROM pg_class
--  WHERE oid = 'public.users'::regclass;                       -- t | t
-- SELECT policyname, cmd, roles, qual, with_check FROM pg_policies
--  WHERE schemaname='public' AND tablename='users' ORDER BY policyname;  -- 6 linhas
-- SELECT tgname FROM pg_trigger
--  WHERE tgrelid='public.users'::regclass AND NOT tgisinternal;          -- 2 linhas
-- SELECT count(*) FROM app_auth.user_role_audit;              -- trilha viva
