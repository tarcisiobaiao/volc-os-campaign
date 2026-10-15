-- =============================================================================
-- tools/freedom-lab/db/sonda_acesso.sql — sonda SOMENTE LEITURA do Supabase oficial
-- Freedom Lab 15/10/2026 · autor: Leitor B; versionada pelo integrador
-- (o auto mode bloqueou a leitura de produção; ver B-banco.md §0)
--
-- Garantias por construção:
--   · tudo dentro de BEGIN READ ONLY … ROLLBACK;
--   · nenhuma linha de negócio é devolvida: só catálogo, booleanos e contagem
--     de OBJETOS (nunca de linhas de tabelas com pessoa);
--   · SET LOCAL ROLE só dura a transação, e o ROLLBACK final desfaz tudo;
--   · statement_timeout curto, para nenhuma varredura pesar no banco vivo.
--
-- Rodar (exige autorização explícita do Tarcísio para leitura de produção):
--   ssh … root@178.156.196.149 'docker exec -i supabase-db psql -U postgres -X \
--        -v ON_ERROR_STOP=1 -P pager=off' < tools/freedom-lab/db/sonda_acesso.sql > sonda.out
-- O arquivo entra por stdin do psql; nenhum shell remoto o interpreta.
-- =============================================================================
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';

\echo '== S0 identidade da sessão'
SELECT version(), current_user, current_setting('transaction_read_only') AS ro;

\echo '== S1 LEDGER — qualquer tabela com cara de controle de migration, em qualquer schema'
SELECT n.nspname, c.relname, c.relkind
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE c.relname ~* '(migration|schema_version|flyway|knex|changelog|prisma)'
 ORDER BY 1, 2;
SELECT to_regclass('supabase_migrations.schema_migrations') AS supabase_cli,
       to_regclass('public.schema_migrations')               AS public_sm,
       to_regclass('auth.schema_migrations')                 AS auth_gotrue,
       to_regclass('storage.migrations')                     AS storage_api,
       to_regclass('realtime.schema_migrations')             AS realtime;
-- Leitura esperada: auth/storage/realtime são ledgers DOS SERVIÇOS do Supabase,
-- não das migrations do VOLC. Só supabase_cli/public_sm contariam como ledger VOLC.

\echo '== S2 PAPÉIS — atributos'
SELECT rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb, rolcanlogin,
       rolreplication, rolbypassrls, rolconnlimit, rolvaliduntil
       -- pg_authid (hash de senha) NÃO é lido; pg_roles mascara rolpassword
  FROM pg_roles
 WHERE rolname IN ('volc_leitor','supabase_read_only_user','anon','authenticated',
                   'service_role','authenticator','postgres','supabase_admin')
    OR rolname ILIKE '%leitor%' OR rolname ILIKE '%read%'
 ORDER BY 1;

\echo '== S3 PAPÉIS — pertencimento (de quem herdam, e quem herda deles)'
SELECT g.rolname AS papel, m.rolname AS membro, am.admin_option
  FROM pg_auth_members am
  JOIN pg_roles g ON g.oid = am.roleid
  JOIN pg_roles m ON m.oid = am.member
 WHERE g.rolname IN ('volc_leitor','supabase_read_only_user','pg_read_all_data',
                     'pg_write_all_data','pg_monitor','pg_read_all_settings',
                     'anon','authenticated','service_role')
    OR m.rolname IN ('volc_leitor','supabase_read_only_user','authenticator')
 ORDER BY 1, 2;

\echo '== S4 PAPÉIS — configuração por papel (default_transaction_read_only etc.)'
SELECT r.rolname, d.datname, s.setconfig
  FROM pg_db_role_setting s
  JOIN pg_roles r ON r.oid = s.setrole
  LEFT JOIN pg_database d ON d.oid = s.setdatabase
 WHERE r.rolname IN ('volc_leitor','supabase_read_only_user','anon','authenticated',
                     'authenticator','service_role');

\echo '== S5 GRANTS diretos dos papéis de leitura (agregado por privilégio e schema)'
SELECT grantee, table_schema, privilege_type, count(*) AS objetos
  FROM information_schema.role_table_grants
 WHERE grantee IN ('volc_leitor','supabase_read_only_user','anon','authenticated','PUBLIC')
 GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;

\echo '== S6 schemas — USAGE/CREATE por papel'
SELECT n.nspname,
       has_schema_privilege('anon', n.oid, 'USAGE')           AS anon_usage,
       has_schema_privilege('authenticated', n.oid, 'USAGE')  AS auth_usage,
       has_schema_privilege('anon', n.oid, 'CREATE')          AS anon_create,
       has_schema_privilege('authenticated', n.oid, 'CREATE') AS auth_create,
       CASE WHEN to_regrole('supabase_read_only_user') IS NOT NULL
            THEN has_schema_privilege('supabase_read_only_user', n.oid, 'USAGE') END AS ro_user_usage,
       CASE WHEN to_regrole('volc_leitor') IS NOT NULL
            THEN has_schema_privilege('volc_leitor', n.oid, 'USAGE') END AS volc_leitor_usage
  FROM pg_namespace n
 WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
 ORDER BY 1;

\echo '== S7 MATRIZ por tabela de public: GRANT × RLS (sem tocar em linha)'
-- classe = o que um SELECT do papel faria, ANTES de rodar:
--   negado        → sem privilégio SELECT (SQLSTATE 42501)
--   aberto        → SELECT e sem RLS: devolve todas as linhas
--   rls_filtrado  → SELECT, RLS ligada e ≥1 policy aplicável ao papel
--   rls_vazio     → SELECT, RLS ligada e zero policy aplicável: devolve 0 linhas
--   bypass        → o papel tem BYPASSRLS: RLS não vale
WITH alvo AS (
  SELECT c.oid, c.relname, c.relkind, c.relrowsecurity, c.relforcerowsecurity,
         coalesce(array_to_string(c.reloptions, ','), '') LIKE '%security_invoker=true%' AS invoker
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','f')
), papeis AS (
  SELECT rolname, oid, rolbypassrls FROM pg_roles
   WHERE rolname IN ('anon','authenticated','supabase_read_only_user','volc_leitor')
), m AS (
  SELECT p.rolname, a.relname, a.relkind, a.relrowsecurity, a.invoker,
         has_table_privilege(p.oid, a.oid, 'SELECT') AS sel,
         has_table_privilege(p.oid, a.oid, 'INSERT') OR has_table_privilege(p.oid, a.oid, 'UPDATE')
           OR has_table_privilege(p.oid, a.oid, 'DELETE') AS escreve,
         p.rolbypassrls,
         EXISTS (SELECT 1 FROM pg_policy pol
                  WHERE pol.polrelid = a.oid AND pol.polcmd IN ('r','*')
                    AND (pol.polroles = '{0}' OR p.oid = ANY (pol.polroles))) AS tem_policy
    FROM papeis p CROSS JOIN alvo a
)
SELECT rolname,
       CASE WHEN NOT sel THEN 'negado'
            WHEN rolbypassrls THEN 'bypass'
            WHEN relkind IN ('v','m') AND NOT invoker THEN 'view_definer'
            WHEN NOT relrowsecurity THEN 'aberto'
            WHEN tem_policy THEN 'rls_filtrado'
            ELSE 'rls_vazio' END AS classe,
       count(*) AS objetos,
       count(*) FILTER (WHERE escreve) AS com_escrita
  FROM m GROUP BY 1, 2 ORDER BY 1, 2;

\echo '== S7b tabelas ABERTAS a anon (nomes; sem conteúdo)'
SELECT c.relname, c.relkind
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m')
   AND has_table_privilege('anon', c.oid, 'SELECT')
   AND (NOT c.relrowsecurity OR EXISTS (SELECT 1 FROM pg_policy pol WHERE pol.polrelid = c.oid
        AND pol.polcmd IN ('r','*') AND (pol.polroles = '{0}' OR to_regrole('anon') = ANY (pol.polroles))))
 ORDER BY 1;

\echo '== S8 SELECT REAL como anon e authenticated — só booleano "viu ≥1 linha"'
-- EXISTS devolve t/f, nunca a linha. 42501 = negado por GRANT; f com grant = RLS
-- (ou tabela vazia — distinguido abaixo pela coluna vazia_para_postgres).
DO $$
DECLARE r record; papel text; viu boolean; vazia boolean; estado text;
BEGIN
  FOR papel IN SELECT unnest(ARRAY['anon','authenticated']) LOOP
    FOR r IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
              WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m')
                AND has_table_privilege(papel, c.oid, 'SELECT') ORDER BY 1 LOOP
      BEGIN
        EXECUTE format('SELECT NOT EXISTS (SELECT 1 FROM public.%I)', r.relname) INTO vazia;
        EXECUTE format('SET LOCAL ROLE %I', papel);
        EXECUTE format('SELECT EXISTS (SELECT 1 FROM public.%I)', r.relname) INTO viu;
        estado := CASE WHEN viu THEN 'VE_LINHAS' WHEN vazia THEN 'tabela_vazia' ELSE 'rls_esconde' END;
        RESET ROLE;
      EXCEPTION WHEN OTHERS THEN
        RESET ROLE; estado := 'erro_' || SQLSTATE;
      END;
      RAISE NOTICE 'S8|%|%|%', papel, r.relname, estado;
    END LOOP;
  END LOOP;
END $$;

\echo '== S9 SECURITY DEFINER executáveis por anon/authenticated (nome + volatilidade)'
SELECT n.nspname, p.proname, pg_get_function_identity_arguments(p.oid) AS args,
       p.provolatile AS vol, pg_get_userbyid(p.proowner) AS dono,
       has_function_privilege('anon', p.oid, 'EXECUTE')          AS anon_exec,
       has_function_privilege('authenticated', p.oid, 'EXECUTE') AS auth_exec,
       (p.proconfig IS NOT NULL AND array_to_string(p.proconfig, ',') LIKE '%search_path%') AS fixa_search_path
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE p.prosecdef AND n.nspname IN ('public','app_auth')
   AND (has_function_privilege('anon', p.oid, 'EXECUTE')
        OR has_function_privilege('authenticated', p.oid, 'EXECUTE'))
 ORDER BY 1, 2;
SELECT count(*) FILTER (WHERE p.prosecdef) AS definer_total,
       count(*) FILTER (WHERE p.prosecdef AND p.provolatile = 'v') AS definer_volatil
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname = 'public';

\echo '== S10 default ACL de public (o defeito medido em 24/08 ainda existe?)'
SELECT pg_get_userbyid(d.defaclrole) AS para_objetos_de, d.defaclobjtype, d.defaclacl
  FROM pg_default_acl d JOIN pg_namespace n ON n.oid = d.defaclnamespace
 WHERE n.nspname = 'public';

\echo '== S11 rede — como um papel de LOGIN chegaria (só configuração)'
SELECT name, setting FROM pg_settings
 WHERE name IN ('listen_addresses','port','ssl','password_encryption','max_connections');

ROLLBACK;
