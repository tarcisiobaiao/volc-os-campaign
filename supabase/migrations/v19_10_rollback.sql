-- =============================================================================
-- v19_10_rollback — desfaz a v19_10 (authenticated mínimo). ARQUIVO. NÃO APLICADO.
-- =============================================================================
-- APLICAR COMO: supabase_admin. Uma transação. Idempotente.
-- Devolve só o que a v19_10 mudou: as policies que ela criou (registradas em
-- app_auth.w4_auth_policy), a RLS das tabelas onde ela a ligou e os aclitems de
-- authenticated (tabelas, colunas e sequências) que ela tirou ou deu. ABORTA sem
-- desfazer nada se a ACL, o estado de RLS ou o conjunto de policies (definição
-- inteira: nome, comando, papéis, USING, WITH CHECK) de qualquer relação que ela
-- mudou foi alterado de novo depois da aplicação.
--
-- Também devolve os dois gatilhos de agregação do funil ao corpo, à segurança e
-- ao dono anteriores (aborta se mudaram depois), remove o gatilho de manutenção
-- do funil, as funções criadas (escopo, host, manutenção) e o papel volc_agregador_funil, e o default ACL de public para anon/authenticated como
-- era antes (aborta se qualquer um dos dois mudou depois da v19_10).
--
-- ORDEM: reverter a v19_10 ANTES do v19_99 (pacote anon); com o W12 aplicado,
-- reverter a v23_01 antes da v19_10 (ordem provisória: v19 → v19_10 → v23_01). Com a v19_10 aplicada,
-- o v19_99 aborta (a ACL das relações que ele restauraria mudou depois dele).
-- Nomes por schema + nome com %I e search_path fixo: nada fora de public.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;
SET LOCAL search_path = pg_catalog;

DO $rb$
DECLARE
  x record; v_alvo text; v_priv text; v_tipo text; v_mudou text; v_n int := 0;
BEGIN
  IF NOT (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) THEN
    RAISE EXCEPTION 'v19_10_rollback exige superusuário (supabase_admin)';
  END IF;
  IF to_regclass('app_auth.w4_auth_acl') IS NULL THEN
    RAISE NOTICE 'v19_10_rollback: sem fotografia (v19_10 não aplicada ou já revertida) — nada a fazer';
    RETURN;
  END IF;

  -- 1. aborta se o que a v19_10 mudou foi mexido depois
  WITH atual AS (
    SELECT s.esquema, s.relacao, s.coluna, s.acl_depois, s.rls_depois, s.pol_depois,
           CASE WHEN s.coluna IS NULL THEN c.relacl ELSE a.attacl END AS acl_agora,
           c.relrowsecurity AS rls_agora,
           CASE WHEN s.coluna IS NULL AND c.oid IS NOT NULL THEN app_auth.w4_policies_md5(c.oid) END AS pol_agora,
           c.oid IS NOT NULL AS existe
      FROM app_auth.w4_auth_acl s
      LEFT JOIN pg_namespace n ON n.nspname = s.esquema
      LEFT JOIN pg_class c ON c.relnamespace = n.oid AND c.relname = s.relacao
      LEFT JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = s.coluna
  )
  SELECT string_agg(format('%I.%I%s', esquema, relacao, coalesce('.' || quote_ident(coluna), '')), ', ')
    INTO v_mudou
    FROM atual
   WHERE existe
     AND ((SELECT array_agg(i::text ORDER BY i::text) FROM unnest(acl_agora) i)
          IS DISTINCT FROM (SELECT array_agg(i::text ORDER BY i::text) FROM unnest(acl_depois) i)
          OR (coluna IS NULL AND rls_agora IS DISTINCT FROM rls_depois)
          OR (coluna IS NULL AND pol_agora IS DISTINCT FROM pol_depois));
  IF v_mudou IS NOT NULL THEN
    RAISE EXCEPTION 'v19_10_rollback abortado: ACL, RLS ou policies mudaram depois da v19_10 em: %. Nada foi desfeito.', v_mudou;
  END IF;

  -- 1b. funções e default ACL também têm de estar como a v19_10 deixou
  SELECT string_agg(f.assinatura, ', ') INTO v_mudou
    FROM app_auth.w4_auth_func f JOIN pg_proc pr ON pr.oid = to_regprocedure(f.assinatura)
   WHERE pg_get_userbyid(pr.proowner) IS DISTINCT FROM f.dono_depois
      OR md5(pg_get_functiondef(pr.oid)) IS DISTINCT FROM f.def_depois_md5;
  IF v_mudou IS NOT NULL THEN
    RAISE EXCEPTION 'v19_10_rollback abortado: função alterada depois da v19_10: %. Nada foi desfeito.', v_mudou;
  END IF;
  SELECT string_agg(a.papel || '/' || a.objtipo::text, ', ') INTO v_mudou
    FROM app_auth.w4_auth_defacl a
   WHERE (SELECT array_agg(i::text ORDER BY i::text) FROM pg_default_acl d, unnest(d.defaclacl) i
           WHERE d.defaclrole = a.papel::regrole AND d.defaclnamespace = 'public'::regnamespace AND d.defaclobjtype = a.objtipo)
         IS DISTINCT FROM (SELECT array_agg(i::text ORDER BY i::text) FROM unnest(a.acl_depois) i);
  IF v_mudou IS NOT NULL THEN
    RAISE EXCEPTION 'v19_10_rollback abortado: default ACL de public mudou depois da v19_10 (%). Nada foi desfeito.', v_mudou;
  END IF;

  -- 1c. gatilhos do funil voltam ao corpo, à segurança e ao dono anteriores
  --     (o corpo salvo por pg_get_functiondef é um CREATE OR REPLACE completo:
  --     sem SECURITY DEFINER nem SET, ele devolve INVOKER e config vazia)
  FOR x IN SELECT * FROM app_auth.w4_auth_func LOOP
    IF to_regprocedure(x.assinatura) IS NULL THEN CONTINUE; END IF;
    EXECUTE x.def_antes;
    EXECUTE format('ALTER FUNCTION %s OWNER TO %I', x.assinatura, x.dono_antes);
  END LOOP;

  -- 1d. default ACL: devolve a anon/authenticated o que existia antes
  FOR x IN
    SELECT a.papel, a.objtipo, pg_get_userbyid(e.grantee) AS grantee, e.privilege_type
      FROM app_auth.w4_auth_defacl a, aclexplode(a.acl_antes) e
     WHERE e.grantee IN ('anon'::regrole, 'authenticated'::regrole)
       AND NOT EXISTS (SELECT 1 FROM aclexplode(a.acl_depois) e2
                        WHERE e2.grantee = e.grantee AND e2.privilege_type = e.privilege_type)
  LOOP
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT %s ON %s TO %I',
                   x.papel, x.privilege_type, CASE x.objtipo WHEN 'S' THEN 'SEQUENCES' ELSE 'TABLES' END, x.grantee);
  END LOOP;

  -- 2. policies criadas pela v19_10
  FOR x IN SELECT * FROM app_auth.w4_auth_policy LOOP
    IF to_regclass(format('%I.%I', x.esquema, x.relacao)) IS NOT NULL THEN
      EXECUTE format('DROP POLICY IF EXISTS %I ON %I.%I', x.policy, x.esquema, x.relacao);
    END IF;
  END LOOP;

  -- 3. RLS volta ao estado anterior onde a v19_10 a ligou
  FOR x IN SELECT * FROM app_auth.w4_auth_acl WHERE coluna IS NULL AND rls_antes IS DISTINCT FROM rls_depois LOOP
    v_alvo := format('%I.%I', x.esquema, x.relacao);
    IF to_regclass(v_alvo) IS NULL THEN CONTINUE; END IF;
    EXECUTE format('ALTER TABLE %s %s ROW LEVEL SECURITY', v_alvo, CASE WHEN x.rls_antes THEN 'ENABLE' ELSE 'DISABLE' END);
  END LOOP;

  -- 4. aclitems de authenticated: tira o que só existe no depois, devolve o que só existia no antes
  FOR x IN
    WITH itens AS (
      SELECT s.esquema, s.relacao, s.coluna, s.relkind, 'antes' AS lado, e.*
        FROM app_auth.w4_auth_acl s, aclexplode(s.acl_antes) e
      UNION ALL
      SELECT s.esquema, s.relacao, s.coluna, s.relkind, 'depois', e.*
        FROM app_auth.w4_auth_acl s, aclexplode(s.acl_depois) e
    )
    SELECT esquema, relacao, coluna, relkind,
           pg_get_userbyid(grantee) AS grantee, pg_get_userbyid(grantor) AS grantor,
           privilege_type, is_grantable, bool_or(lado = 'depois') AS no_depois
      FROM itens
     WHERE grantee = 'authenticated'::regrole
     GROUP BY 1,2,3,4,5,6,7,8
    HAVING bool_or(lado = 'antes') <> bool_or(lado = 'depois')
     ORDER BY bool_or(lado = 'depois') DESC
  LOOP
    v_alvo := format('%I.%I', x.esquema, x.relacao);
    IF to_regclass(v_alvo) IS NULL THEN CONTINUE; END IF;
    v_priv := CASE WHEN x.coluna IS NULL THEN x.privilege_type ELSE format('%s (%I)', x.privilege_type, x.coluna) END;
    v_tipo := CASE WHEN x.relkind = 'S' THEN 'SEQUENCE' ELSE 'TABLE' END;
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

  -- objetos criados pela v19_10: gatilho de manutenção do funil (antes da função dele)
  FOR x IN SELECT * FROM app_auth.w4_auth_criados WHERE tipo = 'gatilho' LOOP
    IF to_regclass('public.' || split_part(x.nome, '.', 1)) IS NOT NULL THEN
      EXECUTE format('DROP TRIGGER IF EXISTS %I ON public.%I', split_part(x.nome, '.', 2), split_part(x.nome, '.', 1));
    END IF;
  END LOOP;
  -- objetos criados pela v19_10: funções do escopo do funil e papel do agregador
  FOR x IN SELECT * FROM app_auth.w4_auth_criados WHERE tipo = 'funcao' LOOP
    IF to_regprocedure(x.nome) IS NOT NULL THEN EXECUTE format('DROP FUNCTION %s', x.nome); END IF;
  END LOOP;
  IF EXISTS (SELECT 1 FROM app_auth.w4_auth_criados WHERE tipo = 'papel' AND nome = 'volc_agregador_funil')
     AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'volc_agregador_funil') THEN
    IF EXISTS (SELECT 1 FROM pg_proc WHERE proowner = 'volc_agregador_funil'::regrole)
       OR EXISTS (SELECT 1 FROM pg_class WHERE relowner = 'volc_agregador_funil'::regrole) THEN
      RAISE EXCEPTION 'v19_10_rollback: volc_agregador_funil ainda é dono de objeto — nada removido';
    END IF;
    DROP OWNED BY volc_agregador_funil;   -- só privilégios e policies (não é dono de nada)
    DROP ROLE volc_agregador_funil;
  END IF;

  DROP TABLE app_auth.w4_auth_policy;
  DROP TABLE app_auth.w4_auth_criados;
  DROP TABLE app_auth.w4_auth_func;
  DROP TABLE app_auth.w4_auth_defacl;
  DROP TABLE app_auth.w4_auth_acl;
  DROP FUNCTION app_auth.w4_policies_md5(oid);
  RAISE NOTICE 'v19_10_rollback: % aclitem(s) de authenticated devolvidos; policies e RLS da v19_10 desfeitas', v_n;
END
$rb$;

COMMIT;

NOTIFY pgrst, 'reload schema';
