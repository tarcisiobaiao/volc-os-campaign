-- =============================================================================
-- v8_99 — ROLLBACK COMPLETO da Sprint 1A / Frente 2 (v8_01 .. v8_06)
-- ARQUIVO. NAO APLICADO. Restaura o estado medido em 2026-08-24.
-- =============================================================================
-- >>> ATENCAO: rodar este arquivo REABRE public.users para anon: leitura e
-- >>> escrita de password_hash, token_primeiro_acesso, token_expiracao e role
-- >>> com a chave que vai no bundle do browser. Use so para destravar producao,
-- >>> e trate como incidente ate reaplicar a contencao.
--
-- Este arquivo e a inversao literal do conjunto v8_01..v8_06. Nao "adivinha"
-- estado: cada CREATE POLICY da secao 1 e a transcricao do que pg_policies
-- devolvia antes de v8_02.
--
-- -----------------------------------------------------------------------------
-- COMO RODAR — sao DOIS papeis, nesta ordem
-- -----------------------------------------------------------------------------
-- Parte A (postgres)        -> secoes 1 e 6
-- Parte B (supabase_admin)  -> secoes 2, 3, 4 e 5
--
-- O arquivo detecta o papel e pula o que nao pode executar, entao pode ser
-- rodado inteiro duas vezes:
--   -- (comando de aplicacao: ver runbook privado de infraestrutura)
--     -- (comando de aplicacao: ver runbook privado de infraestrutura)
--   -- (comando de aplicacao: ver runbook privado de infraestrutura)
--     -- (comando de aplicacao: ver runbook privado de infraestrutura)
--
-- -----------------------------------------------------------------------------
-- ROLLBACK PARCIAL — quase sempre e o que voce quer
-- -----------------------------------------------------------------------------
-- Sintoma: frontend quebrou com 42501 "permission denied for column password_hash"
--   Causa: v8_06 aplicado antes da Frente 1/3 trocar os select('*').
--   Reverte so v8_06, como supabase_admin, sem tocar no resto:
--     GRANT SELECT ON TABLE public.users TO authenticated;
--
-- Sintoma: telas do Pautador vazias para o admin
--   Causa: o sub do JWT nao tem ADMIN ativo em app_auth.user_roles.
--   NAO faca rollback. Conceda o papel (como postgres):
--     SELECT public.volc_grant_role(
--       (SELECT id FROM auth.users WHERE lower(email)=lower('EMAIL_DO_ADMIN')),
--       'ADMIN', 'correcao pos v8_02');
--
-- Sintoma: admin nao consegue editar role de outro usuario
--   Causa esperada: gatilho tg_users_guard_privileged_columns exigindo ADMIN.
--   Confira o papel do chamador antes de considerar rollback:
--     SELECT public.volc_current_admin();
--
-- Sintoma: um usuario nao ve a propria linha em public.users
--   Causa provavel: id de public.users diferente do de auth.users E email
--   divergente. Confira antes de reverter:
--     SELECT pu.id AS public_id, au.id AS auth_id, pu.email, au.email
--       FROM public.users pu FULL JOIN auth.users au
--         ON lower(au.email)=lower(pu.email);
--
-- -----------------------------------------------------------------------------
-- PERDA DE DADO NESTE ROLLBACK
-- -----------------------------------------------------------------------------
-- A secao 6 apaga o schema app_auth, e com ele as concessoes de papel e a
-- trilha de auditoria. public.users NAO e tocada — nenhuma linha de usuario e
-- perdida, porque a autoridade legada (public.users.role) nunca foi removida.
-- Antes da secao 6, exporte se quiser preservar a trilha:
--   \copy (SELECT * FROM app_auth.user_roles)      TO 'user_roles_backup.csv'      CSV HEADER
--   \copy (SELECT * FROM app_auth.user_role_audit) TO 'user_role_audit_backup.csv' CSV HEADER
-- =============================================================================

\set ON_ERROR_STOP on

-- =============================================================================
-- SECAO 1 (postgres) — restaura as 23 policies originais do Pautador
-- =============================================================================
-- Transcricao literal do estado anterior a v8_02. Autoridade volta a ser
-- public.users.role casado por lower(email), e volta a exigir que
-- `authenticated` tenha SELECT em public.users (por isso a secao 3 vem junto).
DO $s1$
BEGIN
  IF NOT pg_has_role(current_user, 'postgres', 'USAGE') THEN
    RAISE NOTICE 'SECAO 1 pulada: exige postgres (current_user = %)', current_user;
    RETURN;
  END IF;
  IF to_regclass('public.pautador_entities') IS NULL THEN
    RAISE NOTICE 'SECAO 1 pulada: tabelas pautador_* ausentes';
    RETURN;
  END IF;

  EXECUTE $q$DROP POLICY IF EXISTS "pautador_logs admin read" ON public.pautador_agent_logs$q$;
  EXECUTE $q$CREATE POLICY "pautador_logs admin read" ON public.pautador_agent_logs AS PERMISSIVE FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text)))))$q$;

  EXECUTE $q$DROP POLICY IF EXISTS "pautador_countries admin all" ON public.pautador_countries$q$;
  EXECUTE $q$CREATE POLICY "pautador_countries admin all" ON public.pautador_countries AS PERMISSIVE FOR ALL TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text))))) WITH CHECK ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text)))))$q$;
  EXECUTE $q$DROP POLICY IF EXISTS "pautador_countries read auth" ON public.pautador_countries$q$;
  EXECUTE $q$CREATE POLICY "pautador_countries read auth" ON public.pautador_countries AS PERMISSIVE FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE (lower(u.email) = lower((auth.jwt() ->> 'email'::text))))))$q$;

  EXECUTE $q$DROP POLICY IF EXISTS "pautador_entities admin all" ON public.pautador_entities$q$;
  EXECUTE $q$CREATE POLICY "pautador_entities admin all" ON public.pautador_entities AS PERMISSIVE FOR ALL TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text))))) WITH CHECK ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text)))))$q$;
  EXECUTE $q$DROP POLICY IF EXISTS "pautador_entities read auth" ON public.pautador_entities$q$;
  EXECUTE $q$CREATE POLICY "pautador_entities read auth" ON public.pautador_entities AS PERMISSIVE FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE (lower(u.email) = lower((auth.jwt() ->> 'email'::text))))))$q$;

  EXECUTE $q$DROP POLICY IF EXISTS "pautador_entity_funnel_hypotheses admin all" ON public.pautador_entity_funnel_hypotheses$q$;
  EXECUTE $q$CREATE POLICY "pautador_entity_funnel_hypotheses admin all" ON public.pautador_entity_funnel_hypotheses AS PERMISSIVE FOR ALL TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text))))) WITH CHECK ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text)))))$q$;
  EXECUTE $q$DROP POLICY IF EXISTS "pautador_entity_funnel_hypotheses read auth" ON public.pautador_entity_funnel_hypotheses$q$;
  EXECUTE $q$CREATE POLICY "pautador_entity_funnel_hypotheses read auth" ON public.pautador_entity_funnel_hypotheses AS PERMISSIVE FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE (lower(u.email) = lower((auth.jwt() ->> 'email'::text))))))$q$;

  EXECUTE $q$DROP POLICY IF EXISTS "pautador_entity_opportunities admin all" ON public.pautador_entity_opportunities$q$;
  EXECUTE $q$CREATE POLICY "pautador_entity_opportunities admin all" ON public.pautador_entity_opportunities AS PERMISSIVE FOR ALL TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text))))) WITH CHECK ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text)))))$q$;
  EXECUTE $q$DROP POLICY IF EXISTS "pautador_entity_opportunities read auth" ON public.pautador_entity_opportunities$q$;
  EXECUTE $q$CREATE POLICY "pautador_entity_opportunities read auth" ON public.pautador_entity_opportunities AS PERMISSIVE FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE (lower(u.email) = lower((auth.jwt() ->> 'email'::text))))))$q$;

  EXECUTE $q$DROP POLICY IF EXISTS "pautador_entity_pains admin all" ON public.pautador_entity_pains$q$;
  EXECUTE $q$CREATE POLICY "pautador_entity_pains admin all" ON public.pautador_entity_pains AS PERMISSIVE FOR ALL TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text))))) WITH CHECK ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text)))))$q$;
  EXECUTE $q$DROP POLICY IF EXISTS "pautador_entity_pains read auth" ON public.pautador_entity_pains$q$;
  EXECUTE $q$CREATE POLICY "pautador_entity_pains read auth" ON public.pautador_entity_pains AS PERMISSIVE FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE (lower(u.email) = lower((auth.jwt() ->> 'email'::text))))))$q$;

  EXECUTE $q$DROP POLICY IF EXISTS "pautador_entity_seed_queries admin all" ON public.pautador_entity_seed_queries$q$;
  EXECUTE $q$CREATE POLICY "pautador_entity_seed_queries admin all" ON public.pautador_entity_seed_queries AS PERMISSIVE FOR ALL TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text))))) WITH CHECK ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text)))))$q$;
  EXECUTE $q$DROP POLICY IF EXISTS "pautador_entity_seed_queries read auth" ON public.pautador_entity_seed_queries$q$;
  EXECUTE $q$CREATE POLICY "pautador_entity_seed_queries read auth" ON public.pautador_entity_seed_queries AS PERMISSIVE FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE (lower(u.email) = lower((auth.jwt() ->> 'email'::text))))))$q$;

  EXECUTE $q$DROP POLICY IF EXISTS "pautador_funnels admin all" ON public.pautador_funnels$q$;
  EXECUTE $q$CREATE POLICY "pautador_funnels admin all" ON public.pautador_funnels AS PERMISSIVE FOR ALL TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text))))) WITH CHECK ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text)))))$q$;
  EXECUTE $q$DROP POLICY IF EXISTS "pautador_funnels read auth" ON public.pautador_funnels$q$;
  EXECUTE $q$CREATE POLICY "pautador_funnels read auth" ON public.pautador_funnels AS PERMISSIVE FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE (lower(u.email) = lower((auth.jwt() ->> 'email'::text))))))$q$;

  EXECUTE $q$DROP POLICY IF EXISTS "pautador_clusters admin all" ON public.pautador_keyword_clusters$q$;
  EXECUTE $q$CREATE POLICY "pautador_clusters admin all" ON public.pautador_keyword_clusters AS PERMISSIVE FOR ALL TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text))))) WITH CHECK ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text)))))$q$;
  EXECUTE $q$DROP POLICY IF EXISTS "pautador_clusters read auth" ON public.pautador_keyword_clusters$q$;
  EXECUTE $q$CREATE POLICY "pautador_clusters read auth" ON public.pautador_keyword_clusters AS PERMISSIVE FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE (lower(u.email) = lower((auth.jwt() ->> 'email'::text))))))$q$;

  EXECUTE $q$DROP POLICY IF EXISTS "pautador_niches admin all" ON public.pautador_niches$q$;
  EXECUTE $q$CREATE POLICY "pautador_niches admin all" ON public.pautador_niches AS PERMISSIVE FOR ALL TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text))))) WITH CHECK ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text)))))$q$;
  EXECUTE $q$DROP POLICY IF EXISTS "pautador_niches read auth" ON public.pautador_niches$q$;
  EXECUTE $q$CREATE POLICY "pautador_niches read auth" ON public.pautador_niches AS PERMISSIVE FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE (lower(u.email) = lower((auth.jwt() ->> 'email'::text))))))$q$;

  EXECUTE $q$DROP POLICY IF EXISTS "pautador_opportunities admin all" ON public.pautador_opportunities$q$;
  EXECUTE $q$CREATE POLICY "pautador_opportunities admin all" ON public.pautador_opportunities AS PERMISSIVE FOR ALL TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text))))) WITH CHECK ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text)))))$q$;
  EXECUTE $q$DROP POLICY IF EXISTS "pautador_opportunities read auth" ON public.pautador_opportunities$q$;
  EXECUTE $q$CREATE POLICY "pautador_opportunities read auth" ON public.pautador_opportunities AS PERMISSIVE FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE (lower(u.email) = lower((auth.jwt() ->> 'email'::text))))))$q$;

  EXECUTE $q$DROP POLICY IF EXISTS "pautador_runs admin all" ON public.pautador_runs$q$;
  EXECUTE $q$CREATE POLICY "pautador_runs admin all" ON public.pautador_runs AS PERMISSIVE FOR ALL TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text))))) WITH CHECK ((EXISTS ( SELECT 1 FROM users u WHERE ((lower(u.email) = lower((auth.jwt() ->> 'email'::text))) AND (u.role = 'ADMIN'::text)))))$q$;
  EXECUTE $q$DROP POLICY IF EXISTS "pautador_runs read auth" ON public.pautador_runs$q$;
  EXECUTE $q$CREATE POLICY "pautador_runs read auth" ON public.pautador_runs AS PERMISSIVE FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1 FROM users u WHERE (lower(u.email) = lower((auth.jwt() ->> 'email'::text))))))$q$;

  RAISE NOTICE 'SECAO 1: 23 policies do Pautador restauradas ao estado pre-v8_02';
END
$s1$;

-- =============================================================================
-- SECAO 2 (supabase_admin) — desfaz v8_03: gatilhos, policies, RLS, constraint
-- =============================================================================
DO $s2$
DECLARE
  v_owner text;
BEGIN
  SELECT pg_get_userbyid(c.relowner) INTO v_owner
  FROM pg_class c WHERE c.oid = 'public.users'::regclass;
  IF NOT pg_has_role(current_user, v_owner, 'USAGE') THEN
    RAISE NOTICE 'SECOES 2-5 puladas: exigem % (current_user = %)', v_owner, current_user;
    RETURN;
  END IF;

  EXECUTE 'DROP TRIGGER IF EXISTS trg_users_guard_privileged_columns ON public.users';
  EXECUTE 'DROP TRIGGER IF EXISTS trg_users_block_last_admin_delete ON public.users';

  EXECUTE 'DROP POLICY IF EXISTS users_select_self  ON public.users';
  EXECUTE 'DROP POLICY IF EXISTS users_select_admin ON public.users';
  EXECUTE 'DROP POLICY IF EXISTS users_insert_admin ON public.users';
  EXECUTE 'DROP POLICY IF EXISTS users_update_self  ON public.users';
  EXECUTE 'DROP POLICY IF EXISTS users_update_admin ON public.users';
  EXECUTE 'DROP POLICY IF EXISTS users_delete_admin ON public.users';

  -- Estado medido antes de v8_03: relrowsecurity = f, relforcerowsecurity = f
  EXECUTE 'ALTER TABLE public.users NO FORCE ROW LEVEL SECURITY';
  EXECUTE 'ALTER TABLE public.users DISABLE ROW LEVEL SECURITY';

  -- Constraint e indice adicionados por v8_03 (nao existiam antes)
  EXECUTE 'ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_email_formato_check';
  EXECUTE 'DROP INDEX IF EXISTS public.users_email_lower_uniq';

  -- =========================================================================
  -- SECAO 3+4 — desfaz v8_04 e v8_06: devolve os 7 privilegios a anon e
  -- authenticated, exatamente como information_schema.role_table_grants
  -- mostrava em 2026-08-24 (28 linhas, 7 por papel).
  -- =========================================================================
  EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public.users FROM anon';
  EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public.users FROM authenticated';
  EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER '
          'ON TABLE public.users TO anon';
  EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER '
          'ON TABLE public.users TO authenticated';

  RAISE WARNING
    'ROLLBACK: public.users voltou a ser lida e escrita por anon, inclusive '
    'password_hash, token_primeiro_acesso, token_expiracao e role. Estado '
    'inseguro conhecido — reaplique v8_01..v8_06 assim que possivel.';

  -- =========================================================================
  -- SECAO 5 — desfaz v8_05
  -- =========================================================================
  EXECUTE 'DROP VIEW IF EXISTS public.users_safe';

  RAISE NOTICE 'SECOES 2-5 concluidas';
END
$s2$;

-- =============================================================================
-- SECAO 6 (postgres) — desfaz v8_01: funcoes, schema app_auth, portao legado
-- =============================================================================
-- Rode DEPOIS da secao 1: as policies restauradas nao dependem das funcoes
-- volc_*, mas as policies de v8_02 dependem. Derrubar as funcoes antes de
-- restaurar as policies deixaria o Pautador quebrado no intervalo.
DO $s6$
BEGIN
  IF NOT pg_has_role(current_user, 'postgres', 'USAGE') THEN
    RAISE NOTICE 'SECAO 6 pulada: exige postgres (current_user = %)', current_user;
    RETURN;
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_policies
    WHERE coalesce(qual,'') ~ 'volc_current_' OR coalesce(with_check,'') ~ 'volc_current_'
  ) THEN
    RAISE EXCEPTION
      'SECAO 6 abortada: ainda existem policies usando volc_current_*. Rode a '
      'SECAO 1 (como postgres) e a SECAO 2 (como supabase_admin) antes.';
  END IF;

  EXECUTE 'DROP FUNCTION IF EXISTS public.volc_grant_role(uuid, text, text)';
  EXECUTE 'DROP FUNCTION IF EXISTS public.volc_revoke_role(uuid)';
  EXECUTE 'DROP FUNCTION IF EXISTS public.volc_is_admin(uuid)';
  EXECUTE 'DROP FUNCTION IF EXISTS public.volc_current_user_known()';
  EXECUTE 'DROP FUNCTION IF EXISTS public.volc_current_role()';
  EXECUTE 'DROP FUNCTION IF EXISTS public.volc_current_admin()';

  -- Apaga papeis concedidos e trilha de auditoria. Exporte antes se precisar
  -- (comandos \copy no cabecalho). public.users NAO e tocada.
  EXECUTE 'DROP SCHEMA IF EXISTS app_auth CASCADE';

  -- Devolve o EXECUTE do portao falso, como estava medido
  IF to_regprocedure('public.get_current_user_role()') IS NOT NULL THEN
    EXECUTE 'GRANT EXECUTE ON FUNCTION public.get_current_user_role() TO anon';
    EXECUTE 'GRANT EXECUTE ON FUNCTION public.get_current_user_role() TO authenticated';
    EXECUTE 'GRANT EXECUTE ON FUNCTION public.get_current_user_role() TO service_role';
    EXECUTE 'COMMENT ON FUNCTION public.get_current_user_role() IS NULL';
  END IF;

  RAISE NOTICE 'SECAO 6: app_auth removido, funcoes volc_* removidas';
END
$s6$;

-- =============================================================================
-- VERIFICACAO POS-ROLLBACK (somente leitura) — deve reproduzir o estado medido
-- =============================================================================
-- SELECT relrowsecurity, relforcerowsecurity FROM pg_class
--  WHERE oid='public.users'::regclass;                              -- f | f
-- SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename='users';  -- 0
-- SELECT count(*) FROM information_schema.role_table_grants
--  WHERE table_schema='public' AND table_name='users';              -- 28
-- SELECT count(*) FROM pg_policies
--  WHERE schemaname='public' AND tablename LIKE 'pautador%';        -- 23
-- SELECT to_regnamespace('app_auth');                               -- NULL
