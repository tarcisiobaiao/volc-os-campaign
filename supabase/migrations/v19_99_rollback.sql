-- =============================================================================
-- v19_99 — ROLLBACK do pacote do incidente anon (W4): v19_02, v8_05, v19_01, v8_03,
-- v19_00 e, se aplicada, v8_06. ARQUIVO. NÃO APLICADO.
-- =============================================================================
-- APLICAR COMO: supabase_admin. Uma transação. Idempotente: rodar duas vezes
-- não falha nem muda nada na segunda.
--
-- ⚠️ DEVOLVE O ESTADO INSEGURO MEDIDO EM 15/10: anon volta a ler e escrever as
-- 62 relações de public, inclusive users. Use só se o pacote quebrar algo que
-- não se conserta para frente. Rollbacks parciais, mais seguros, no fim.
--
-- Ordem inversa da aplicação:
--   1. default ACL (v19_02) volta ao medido na S10
--   2. public.users_safe (v8_05) sai
--   3. ACL de public volta EXATAMENTE à fotografia app_auth.w4_acl_antes (v19_01),
--      concedente por concedente, e a fotografia é apagada
--   4. RLS, policies, gatilhos, índice e constraint de public.users (v8_03) saem
--   5. o gatilho de users volta ao corpo original (v19_00)
-- O rollback da v19_01 cobre também a v8_06: a fotografia é anterior a ambas.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

DO $guard$
BEGIN
  IF NOT (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) THEN
    RAISE EXCEPTION 'v19_99 exige superusuário (supabase_admin). current_user = %', current_user;
  END IF;
END
$guard$;

-- 1. v19_02 — default ACL como na S10 de produção ----------------------------
ALTER DEFAULT PRIVILEGES FOR ROLE postgres, supabase_admin IN SCHEMA public
  GRANT ALL ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres, supabase_admin IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO anon;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres, supabase_admin IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO anon;

-- 2. v8_05 ----------------------------------------------------------------------
DROP VIEW IF EXISTS public.users_safe;

-- 3. v19_01 (e v8_06) — ACL de public restaurada da fotografia --------------------
DO $acl$
DECLARE
  r      record;
  x      record;
  v_tipo text;
  v_n    int := 0;
  v_priv text;
BEGIN
  IF to_regclass('app_auth.w4_acl_antes') IS NULL THEN
    RAISE NOTICE 'v19_99: sem fotografia (v19_01 não aplicada ou já revertida) — ACL não tocada';
    RETURN;
  END IF;

  -- 3a. limpa anon e authenticated em toda relação fotografada que ainda existe
  FOR r IN
    SELECT s.relacao, s.relkind FROM app_auth.w4_acl_antes s
     WHERE s.coluna IS NULL AND to_regclass(s.relacao) IS NOT NULL
  LOOP
    v_tipo := CASE WHEN r.relkind = 'S' THEN 'SEQUENCE' ELSE 'TABLE' END;
    FOR x IN
      SELECT DISTINCT pg_get_userbyid(e.grantor) AS grantor
        FROM pg_class c, aclexplode(c.relacl) e
       WHERE c.oid = to_regclass(r.relacao)
         AND e.grantee IN ('anon'::regrole, 'authenticated'::regrole)
    LOOP
      EXECUTE format('SET LOCAL ROLE %I', x.grantor);
      EXECUTE format('REVOKE ALL ON %s %s FROM anon, authenticated', v_tipo, r.relacao);
      RESET ROLE;
    END LOOP;
  END LOOP;

  -- 3b. regrava, de cada aclitem fotografado de anon/authenticated, o privilégio
  --     com o mesmo concedente (relação e coluna)
  FOR x IN
    SELECT s.relacao, s.coluna, s.relkind,
           pg_get_userbyid(e.grantee) AS grantee, pg_get_userbyid(e.grantor) AS grantor,
           e.privilege_type, e.is_grantable
      FROM app_auth.w4_acl_antes s, aclexplode(s.acl) e
     WHERE to_regclass(s.relacao) IS NOT NULL
       AND e.grantee IN ('anon'::regrole, 'authenticated'::regrole)
  LOOP
    v_tipo := CASE WHEN x.relkind = 'S' THEN 'SEQUENCE' ELSE 'TABLE' END;
    v_priv := CASE WHEN x.coluna IS NULL THEN x.privilege_type
                   ELSE format('%s (%I)', x.privilege_type, x.coluna) END;
    -- GRANTED BY exige ser o próprio concedente: o superusuário assume o papel.
    EXECUTE format('SET LOCAL ROLE %I', x.grantor);
    EXECUTE format('GRANT %s ON %s %s TO %I%s',
                   v_priv, v_tipo, x.relacao, x.grantee,
                   CASE WHEN x.is_grantable THEN ' WITH GRANT OPTION' ELSE '' END);
    RESET ROLE;
    v_n := v_n + 1;
  END LOOP;

  DROP TABLE app_auth.w4_acl_antes;
  RAISE WARNING 'v19_99: % privilégio(s) de anon/authenticated restaurados — anon voltou a ler e '
                'escrever public. Estado inseguro conhecido.', v_n;
END
$acl$;

-- 4. v8_03 ----------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_users_guard_privileged_columns ON public.users;
DROP TRIGGER IF EXISTS trg_users_block_last_admin_delete ON public.users;
DROP POLICY IF EXISTS users_select_self  ON public.users;
DROP POLICY IF EXISTS users_select_admin ON public.users;
DROP POLICY IF EXISTS users_insert_admin ON public.users;
DROP POLICY IF EXISTS users_update_self  ON public.users;
DROP POLICY IF EXISTS users_update_admin ON public.users;
DROP POLICY IF EXISTS users_delete_admin ON public.users;
ALTER TABLE public.users NO FORCE ROW LEVEL SECURITY;
ALTER TABLE public.users DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_email_formato_check;
DROP INDEX IF EXISTS public.users_email_lower_uniq;

-- 5. v19_00 — corpo original do gatilho (transcrito do schema de produção de 15/10).
--    ⚠️ O original não barra autopromoção (ver cabeçalho da v19_00).
CREATE OR REPLACE FUNCTION app_auth.tg_users_guard_privileged_columns() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
    AS $$
DECLARE
  v_caller uuid := (SELECT auth.uid());
BEGIN
  IF NEW.role IS DISTINCT FROM OLD.role
     OR NEW.commission_percentage IS DISTINCT FROM OLD.commission_percentage THEN

    IF NOT (
      public.volc_current_admin()
      OR current_user IN ('service_role', 'postgres', 'supabase_admin')
    ) THEN
      INSERT INTO app_auth.user_role_audit
        (legacy_user_id, old_role, new_role, actor_db_role, actor_auth_uid, source)
      VALUES
        (OLD.id, OLD.role, NEW.role, current_user, v_caller,
         'public.users UPDATE NEGADO — coluna privilegiada sem ADMIN');
      RAISE EXCEPTION
        'public.users: alterar role/commission_percentage exige ADMIN';
    END IF;

    INSERT INTO app_auth.user_role_audit
      (legacy_user_id, old_role, new_role, actor_db_role, actor_auth_uid, source)
    VALUES
      (OLD.id, OLD.role, NEW.role, current_user, v_caller,
       'public.users UPDATE de coluna privilegiada');
  END IF;

  RETURN NEW;
END;
$$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- =============================================================================
-- ROLLBACKS PARCIAIS (preferíveis ao completo; supabase_admin)
-- =============================================================================
-- Sintoma: tela quebra com 42501 "permission denied for column password_hash"
--   Causa: v8_06 aplicada antes do frontend sem select('*') estar em produção.
--   GRANT SELECT ON TABLE public.users TO authenticated;
--
-- Sintoma: admin não vê a lista de usuários (só a própria linha)
--   Causa: o sub do JWT dele não tem ADMIN ativo em app_auth.user_roles.
--   SELECT public.volc_grant_role('<auth.users.id>', 'ADMIN', 'pos-W4');
--
-- Sintoma: um fluxo externo (site, n8n com a anon key) parou de gravar em X
--   Conserto pontual, sem reabrir o resto:
--   GRANT INSERT ON TABLE public.<x> TO anon;   -- e avaliar RLS em <x>
--
-- Sintoma: migration nova criou tabela e o frontend não lê
--   Não é a v19_02: ela mantém SELECT/INSERT/UPDATE/DELETE de authenticated.
--   Conferir o GRANT da própria migration.
