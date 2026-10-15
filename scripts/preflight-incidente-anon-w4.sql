-- =============================================================================
-- preflight-producao.sql — pacote do incidente anon (W4). SOMENTE LEITURA.
-- Roda com a MENOR identidade de leitura que existe hoje em produção:
-- supabase_read_only_user (LOGIN, membro de pg_read_all_data, sem nenhum grant de
-- escrita), com default_transaction_read_only=on na conexão e BEGIN READ ONLY …
-- ROLLBACK. Quando a v18_01 existir, troca por volc_leitura_agente. Devolve só
-- contagens e booleanos: nenhuma linha de negócio, nenhum e-mail, nenhum hash.
-- Cada linha "BLOQUEIA=t" impede a aplicação; "ATENCAO=t" pede decisão.
-- =============================================================================
BEGIN READ ONLY;
SET LOCAL statement_timeout = '15s';
\pset footer off

SELECT 'P0 sessão só leitura' AS item, current_user AS valor,
       current_setting('transaction_read_only') AS read_only,
       current_setting('transaction_read_only') <> 'on' AS bloqueia,
       current_setting('server_version') AS versao;

-- P1 auth.uid() precisa ler request.jwt.claims (o que o PostgREST atual define).
-- Se só ler request.jwt.claim.sub, nenhum ADMIN é reconhecido pelo JWT e a lista
-- de usuários da tela de admin passa a mostrar só a própria linha.
SELECT 'P1 auth.uid lê request.jwt.claims' AS item,
       pg_get_functiondef('auth.uid()'::regprocedure) LIKE '%request.jwt.claims%' AS ok,
       NOT (pg_get_functiondef('auth.uid()'::regprocedure) LIKE '%request.jwt.claims%') AS bloqueia;

-- P2 estado esperado antes do pacote
SELECT 'P2 users sem RLS e sem policy (v8_03 não aplicada)' AS item,
       (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.users'::regclass) AS rls_ligada,
       (SELECT count(*) FROM pg_policy WHERE polrelid = 'public.users'::regclass) AS policies,
       to_regclass('app_auth.w4_acl_antes') IS NOT NULL AS v19_01_ja_aplicada,
       to_regclass('public.users_safe') IS NOT NULL AS users_safe_existe;

-- md5 do corpo no schema de produção de 15/10 (o que a v19_00 substitui e o
-- v19_99 devolve). Diferente = alguém mexeu na função: reler antes de aplicar.
SELECT 'P3 gatilho de users é o original de 15/10' AS item,
       md5(prosrc) = '600001c0a3c2972060c8e4d6c45d0555' AS ok,
       md5(prosrc) <> '600001c0a3c2972060c8e4d6c45d0555' AS atencao
  FROM pg_proc WHERE oid = 'app_auth.tg_users_guard_privileged_columns()'::regprocedure;

-- P4 quem perde visão: ADMIN em public.users sem ADMIN ativo em app_auth pelo
-- e-mail do auth.users. Depois da v8_03 essas pessoas veem só a própria linha
-- de users (o resto do app continua igual). Corrigir ANTES com volc_grant_role.
SELECT 'P4 ADMIN de public.users sem papel em app_auth' AS item,
       count(*) FILTER (WHERE pu.role = 'ADMIN') AS admins_public_users,
       count(*) FILTER (WHERE pu.role = 'ADMIN' AND NOT EXISTS (
         SELECT 1 FROM auth.users au
           JOIN app_auth.user_roles r ON r.auth_user_id = au.id
          WHERE lower(au.email) = lower(pu.email) AND r.role = 'ADMIN' AND r.revoked_at IS NULL)) AS sem_papel,
       count(*) FILTER (WHERE NOT EXISTS (
         SELECT 1 FROM auth.users au WHERE lower(au.email) = lower(pu.email))) AS sem_login_auth,
       (SELECT count(*) FROM app_auth.user_roles WHERE role = 'ADMIN' AND revoked_at IS NULL) = 0 AS bloqueia
  FROM public.users pu;

SELECT 'P5 e-mails duplicados por caixa (v8_03 aborta)' AS item,
       count(*) AS duplicados, count(*) > 0 AS bloqueia
  FROM (SELECT lower(email) FROM public.users GROUP BY 1 HAVING count(*) > 1) d;

-- P6 superfície que a v19_01 fecha (esperado em 15/10: 62)
SELECT 'P6 relações de public com privilégio de anon' AS item, count(*) AS relacoes
  FROM pg_class c
 WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r','p','v','m','f')
   AND has_table_privilege('anon', c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER');

-- P7 concedentes distintos dos grants de anon (a v19_01 assume cada um)
SELECT 'P7 concedentes de grants a anon em public' AS item,
       string_agg(DISTINCT pg_get_userbyid(x.grantor), ',') AS concedentes
  FROM pg_class c, aclexplode(c.relacl) x
 WHERE c.relnamespace = 'public'::regnamespace AND x.grantee = 'anon'::regrole;

-- P8 papéis de LOGIN fora do padrão Supabase (consumidores diretos possíveis)
SELECT 'P8 papéis de login' AS item, string_agg(rolname, ',' ORDER BY rolname) AS papeis
  FROM pg_roles WHERE rolcanlogin;

ROLLBACK;
