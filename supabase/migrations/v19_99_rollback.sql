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
--   3. só as ACLs que a v19_01 mudou voltam ao "antes" de app_auth.w4_acl,
--      concedente por concedente; aborta sem desfazer nada se alguma delas foi
--      alterada de novo depois da aplicação; a fotografia é apagada
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

-- 3. v19_01 (e v8_06) — devolve SÓ o que a v19_01 mudou ------------------------
-- Nomes vêm de app_auth.w4_acl (schema e relação separados, citados com %I) e o
-- search_path fica fixo: nenhum objeto fora de public é tocado.
SET LOCAL search_path = pg_catalog;

-- 3a. v8_06, se aplicada: authenticated volta a ter SELECT de tabela em users e
--     perde o SELECT por coluna que a v8_06 deu — volta ao "depois" da v19_01.
DO $v806$
BEGIN
  IF to_regclass('app_auth.w4_acl') IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM pg_class c, aclexplode(c.relacl) x
                      WHERE c.oid = 'public.users'::regclass
                        AND x.grantee = 'authenticated'::regrole AND x.privilege_type = 'SELECT') THEN
    GRANT SELECT ON TABLE public.users TO authenticated;
    REVOKE SELECT (id, name, email, role, first_login, needs_password_change,
                   commission_percentage, created_at, updated_at)
      ON TABLE public.users FROM authenticated;
    RAISE NOTICE 'v19_99: v8_06 desfeita (SELECT de tabela de users devolvido a authenticated)';
  END IF;
END
$v806$;

DO $acl$
DECLARE
  x        record;
  v_alvo   text;
  v_tipo   text;
  v_priv   text;
  v_mudou  text;
  v_n      int := 0;
BEGIN
  IF to_regclass('app_auth.w4_acl') IS NULL THEN
    RAISE NOTICE 'v19_99: sem fotografia (v19_01 não aplicada ou já revertida) — ACL não tocada';
    RETURN;
  END IF;

  -- 3b. Aborta se algo que a v19_01 mudou foi alterado DE NOVO depois (ex.: um
  --     endurecimento posterior). Desfazer por cima apagaria essa mudança calado.
  WITH atual AS (
    SELECT s.esquema, s.relacao, s.coluna, s.acl_depois,
           CASE WHEN s.coluna IS NULL THEN c.relacl ELSE a.attacl END AS acl_agora,
           c.oid IS NOT NULL AS existe
      FROM app_auth.w4_acl s
      LEFT JOIN pg_namespace n ON n.nspname = s.esquema
      LEFT JOIN pg_class c ON c.relnamespace = n.oid AND c.relname = s.relacao
      LEFT JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = s.coluna
  )
  SELECT string_agg(format('%I.%I%s', esquema, relacao, coalesce('.' || quote_ident(coluna), '')), ', ')
    INTO v_mudou
    FROM atual
   WHERE existe
     AND (SELECT array_agg(i::text ORDER BY i::text) FROM unnest(acl_agora) i)
         IS DISTINCT FROM
         (SELECT array_agg(i::text ORDER BY i::text) FROM unnest(acl_depois) i);
  IF v_mudou IS NOT NULL THEN
    RAISE EXCEPTION 'v19_99 abortado: ACL mudou depois da v19_01 em: %. Nada foi desfeito. '
                    'Use os rollbacks parciais do fim deste arquivo, ou alinhe essas ACLs ao estado '
                    'pós-v19_01 conscientemente antes de repetir.', v_mudou;
  END IF;

  -- 3c. Para cada aclitem de anon/authenticated: tira o que só existe no "depois",
  --     devolve o que só existia no "antes". Concedente preservado (SET ROLE).
  FOR x IN
    WITH itens AS (
      SELECT s.esquema, s.relacao, s.coluna, s.relkind, 'antes' AS lado, e.*
        FROM app_auth.w4_acl s, aclexplode(s.acl_antes) e
      UNION ALL
      SELECT s.esquema, s.relacao, s.coluna, s.relkind, 'depois', e.*
        FROM app_auth.w4_acl s, aclexplode(s.acl_depois) e
    )
    SELECT esquema, relacao, coluna, relkind,
           pg_get_userbyid(grantee) AS grantee, pg_get_userbyid(grantor) AS grantor,
           privilege_type, is_grantable,
           bool_or(lado = 'antes') AS no_antes, bool_or(lado = 'depois') AS no_depois
      FROM itens
     WHERE grantee IN ('anon'::regrole, 'authenticated'::regrole)
     GROUP BY 1,2,3,4,5,6,7,8
    HAVING bool_or(lado = 'antes') <> bool_or(lado = 'depois')
     ORDER BY bool_or(lado = 'depois') DESC   -- primeiro tira, depois devolve
  LOOP
    v_alvo := format('%I.%I', x.esquema, x.relacao);
    IF to_regclass(v_alvo) IS NULL THEN CONTINUE; END IF;
    v_tipo := CASE WHEN x.relkind = 'S' THEN 'SEQUENCE' ELSE 'TABLE' END;
    v_priv := CASE WHEN x.coluna IS NULL THEN x.privilege_type
                   ELSE format('%s (%I)', x.privilege_type, x.coluna) END;
    -- GRANTED BY exige ser o próprio concedente: o superusuário assume o papel.
    EXECUTE format('SET LOCAL ROLE %I', x.grantor);
    IF x.no_depois THEN
      EXECUTE format('REVOKE %s ON %s %s FROM %I', v_priv, v_tipo, v_alvo, x.grantee);
    ELSE
      EXECUTE format('GRANT %s ON %s %s TO %I%s', v_priv, v_tipo, v_alvo, x.grantee,
                     CASE WHEN x.is_grantable THEN ' WITH GRANT OPTION' ELSE '' END);
    END IF;
    RESET ROLE;
    v_n := v_n + 1;
  END LOOP;

  DROP TABLE app_auth.w4_acl;
  RAISE WARNING 'v19_99: % privilégio(s) de anon/authenticated devolvidos ao estado anterior — '
                'anon voltou a ler e escrever public. Estado inseguro conhecido.', v_n;
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
