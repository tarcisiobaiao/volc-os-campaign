-- =============================================================================
-- preflight-incidente-anon-w4.sql — pacote do incidente anon (W4). SOMENTE LEITURA.
-- Roda com a MENOR identidade de leitura que existe hoje em produção:
-- supabase_read_only_user (LOGIN, membro de pg_read_all_data, sem nenhum grant de
-- escrita), com default_transaction_read_only=on na conexão e BEGIN READ ONLY …
-- ROLLBACK. Quando a v18_01 existir, troca por volc_leitura_agente.
-- Saída uniforme, uma linha por item: item|valor|bloqueia. O script de aplicação
-- recusa seguir se qualquer linha tiver bloqueia = t. Só contagens e booleanos:
-- nenhuma linha de negócio, nenhum e-mail, nenhum hash.
-- O que o anon alcança de verdade NÃO é medido aqui (esta identidade não assume
-- anon): é o scripts/verificar-anon-w4.sql.
-- =============================================================================
BEGIN READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL search_path = pg_catalog;

WITH p AS (
  SELECT
    current_setting('default_transaction_read_only') AS sessao_ro,
    pg_get_functiondef('auth.uid()'::regprocedure) LIKE '%request.jwt.claims%' AS uid_claims,
    (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.users'::regclass) AS users_rls,
    (SELECT count(*) FROM pg_policy WHERE polrelid = 'public.users'::regclass) AS users_policies,
    to_regclass('app_auth.w4_acl') IS NOT NULL AS v19_01_aplicada,
    (SELECT md5(prosrc) FROM pg_proc
      WHERE oid = 'app_auth.tg_users_guard_privileged_columns()'::regprocedure) AS md5_gatilho,
    (SELECT count(*) FROM public.users WHERE role = 'ADMIN') AS admins_cadastro,
    (SELECT count(*) FROM public.users pu
      WHERE pu.role = 'ADMIN' AND NOT EXISTS (
        SELECT 1 FROM auth.users au JOIN app_auth.user_roles r ON r.auth_user_id = au.id
         WHERE lower(au.email) = lower(pu.email) AND r.role = 'ADMIN' AND r.revoked_at IS NULL)) AS admins_sem_papel,
    (SELECT count(*) FROM app_auth.user_roles WHERE role = 'ADMIN' AND revoked_at IS NULL) AS admins_app_auth,
    (SELECT count(*) FROM (SELECT lower(email) FROM public.users GROUP BY 1 HAVING count(*) > 1) d) AS emails_dup,
    (SELECT count(*) FROM pg_class c
      WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r','p','v','m','f')
        AND has_table_privilege('anon', c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')) AS anon_relacoes,
    (SELECT string_agg(DISTINCT pg_get_userbyid(x.grantor), ',') FROM pg_class c, aclexplode(c.relacl) x
      WHERE c.relnamespace = 'public'::regnamespace AND x.grantee = 'anon'::regrole) AS concedentes,
    (SELECT string_agg(rolname, ',' ORDER BY rolname) FROM pg_roles WHERE rolcanlogin) AS logins
), itens(item, valor, bloqueia) AS (
SELECT 'P0 sessão só leitura (' || current_user || ')', sessao_ro, (sessao_ro <> 'on')::text FROM p
UNION ALL SELECT 'P1 auth.uid lê request.jwt.claims', uid_claims::text, (NOT uid_claims)::text FROM p
UNION ALL SELECT 'P2 users já com RLS/policies', format('rls=%s policies=%s', users_rls, users_policies),
                 (users_rls OR users_policies > 0)::text FROM p
UNION ALL SELECT 'P2b v19_01 já aplicada', v19_01_aplicada::text, v19_01_aplicada::text FROM p
-- md5 do corpo no schema de produção de 15/10 (o que a v19_00 substitui e o
-- v19_99 devolve). Diferente = alguém mexeu na função: reler antes de aplicar.
UNION ALL SELECT 'P3 gatilho de users = original de 15/10', (md5_gatilho = '600001c0a3c2972060c8e4d6c45d0555')::text,
                 (md5_gatilho IS DISTINCT FROM '600001c0a3c2972060c8e4d6c45d0555')::text FROM p
-- Depois da v8_03, ADMIN sem papel em app_auth vê só a própria linha de users.
-- O frontend agora mostra erro (src/v6/services/visaoDeAdmin.ts), mas a tela de
-- usuários fica inutilizável para essa pessoa: conceder o papel ANTES.
UNION ALL SELECT 'P4 ADMIN do cadastro sem papel em app_auth', format('%s de %s', admins_sem_papel, admins_cadastro),
                 (admins_sem_papel > 0 OR admins_app_auth = 0)::text FROM p
UNION ALL SELECT 'P5 e-mails duplicados por caixa', emails_dup::text, (emails_dup > 0)::text FROM p
UNION ALL SELECT 'P6 relações de public com privilégio de anon (15/10: 62)', anon_relacoes::text, 'f' FROM p
UNION ALL SELECT 'P7 concedentes de grants a anon', coalesce(concedentes, '-'), 'f' FROM p
UNION ALL SELECT 'P8 papéis de login', logins, 'f' FROM p
)
SELECT item, valor, CASE WHEN bloqueia IN ('true', 't') THEN 't' ELSE 'f' END FROM itens;

ROLLBACK;
