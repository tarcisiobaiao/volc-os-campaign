-- =============================================================================
-- v19_02 — Incidente da chave anon: tabela e sequência NOVAS em public param de
--          nascer abertas a anon (função nova continua executável por PUBLIC)
-- MISSÃO W4 (15/10/2026). ARQUIVO. NÃO APLICADO. Exige decisão humana.
-- =============================================================================
-- APLICAR COMO: supabase_admin (superusuário: altera o default ACL dos DOIS
--   donos, postgres e supabase_admin, com FOR ROLE; um só deixa metade aberta).
-- DEPENDE DE: v19_01 (que fecha o que já existe; esta fecha o que vier).
-- SUBSTITUI:  v8_07 (.OPCIONAL), que exigia rodar duas vezes com papéis
--             diferentes e tirava também a leitura de authenticated em tabela
--             nova — o que quebraria tela nova do frontend sem aviso.
--
-- ESTADO MEDIDO EM PRODUÇÃO (S10, 15/10/2026):
--   postgres       r  {postgres,anon,authenticated,service_role = arwdDxt}
--   postgres       f  {postgres,anon,authenticated,service_role = X}
--   postgres       S  {postgres,anon,authenticated,service_role = rwU}
--   supabase_admin r/f/S  idem
-- PUBLIC não aparece nessas entradas, mas o default ACL por schema só SOMA ao
-- default global, e o global embutido do Postgres dá EXECUTE a PUBLIC em toda
-- função nova. Medido no ensaio: depois desta migration, função nova nasce
-- `=X/postgres`. Uma SECURITY DEFINER nova sem REVOKE explícito é chamável por
-- anon e lê com o privilégio do dono.
-- DECISÃO: não aplicar `ALTER DEFAULT PRIVILEGES … REVOKE EXECUTE ON FUNCTIONS
-- FROM PUBLIC` global aqui — ele vale para TODOS os schemas desses donos (auth,
-- storage, meta_*_private, extensions) e mudaria função de serviço da imagem.
-- Fica a convenção que as migrations do repo já seguem: toda SECURITY DEFINER
-- nova faz REVOKE EXECUTE … FROM PUBLIC, anon nominalmente.
--
-- O QUE FAZ, para objetos criados por postgres e por supabase_admin em public:
--   tabelas/views  : anon perde tudo; authenticated perde TRUNCATE, REFERENCES,
--                    TRIGGER (mantém SELECT/INSERT/UPDATE/DELETE, como a v19_01)
--   sequências     : anon perde tudo
--   funções        : anon perde o EXECUTE nominal (o EXECUTE por PUBLIC, que é
--                    o default embutido do Postgres, continua — ver a prova)
-- service_role e authenticated mantêm o resto. Nada existente muda.
-- Prova dentro da transação: cria uma tabela, uma sequência e uma função como
-- cada dono, confere que anon não alcança a tabela nem a sequência e não tem
-- grant nominal na função, e desfaz.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

DO $guard$
BEGIN
  IF NOT (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) THEN
    RAISE EXCEPTION 'v19_02 exige superusuário (supabase_admin). current_user = %', current_user;
  END IF;
END
$guard$;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres, supabase_admin IN SCHEMA public
  REVOKE ALL ON TABLES FROM anon;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres, supabase_admin IN SCHEMA public
  REVOKE TRUNCATE, REFERENCES, TRIGGER ON TABLES FROM authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres, supabase_admin IN SCHEMA public
  REVOKE ALL ON SEQUENCES FROM anon;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres, supabase_admin IN SCHEMA public
  REVOKE ALL ON FUNCTIONS FROM anon;

-- Prova por construção: objetos novos de cada dono, inspecionados e descartados
-- dentro desta mesma transação (SAVEPOINT + ROLLBACK TO não deixa resíduo).
DO $prova$
DECLARE
  v_dono text;
  v_falha text := '';
BEGIN
  FOREACH v_dono IN ARRAY ARRAY['postgres', 'supabase_admin'] LOOP
    EXECUTE format('SET LOCAL ROLE %I', v_dono);
    CREATE TABLE public.w4_sonda_default_acl (i int);
    CREATE SEQUENCE public.w4_sonda_default_acl_seq;
    CREATE FUNCTION public.w4_sonda_default_acl_fn() RETURNS int LANGUAGE sql AS 'select 1';
    RESET ROLE;

    IF has_table_privilege('anon', 'public.w4_sonda_default_acl',
                           'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') THEN
      v_falha := v_falha || format(' tabela-de-%s:anon', v_dono);
    END IF;
    IF has_table_privilege('authenticated', 'public.w4_sonda_default_acl', 'TRUNCATE,REFERENCES,TRIGGER') THEN
      v_falha := v_falha || format(' tabela-de-%s:authenticated-TRUNCATE', v_dono);
    END IF;
    IF NOT has_table_privilege('authenticated', 'public.w4_sonda_default_acl', 'SELECT') THEN
      v_falha := v_falha || format(' tabela-de-%s:authenticated-perdeu-SELECT', v_dono);
    END IF;
    IF NOT has_table_privilege('service_role', 'public.w4_sonda_default_acl', 'SELECT,INSERT,UPDATE,DELETE') THEN
      v_falha := v_falha || format(' tabela-de-%s:service_role-perdeu', v_dono);
    END IF;
    IF has_sequence_privilege('anon', 'public.w4_sonda_default_acl_seq', 'USAGE,SELECT,UPDATE') THEN
      v_falha := v_falha || format(' sequencia-de-%s:anon', v_dono);
    END IF;
    -- Função: só o grant NOMINAL a anon sai. EXECUTE por PUBLIC vem do default
    -- embutido do Postgres (global, não por schema) e não é tocado aqui: tirá-lo
    -- afetaria funções de todos os schemas desses donos. Com a v19_01, função
    -- INVOKER chamada por anon falha na tabela; DEFINER nova exige REVOKE nominal.
    IF EXISTS (SELECT 1 FROM pg_proc p, aclexplode(p.proacl) x
                WHERE p.oid = 'public.w4_sonda_default_acl_fn()'::regprocedure
                  AND x.grantee = 'anon'::regrole) THEN
      v_falha := v_falha || format(' funcao-de-%s:anon-nominal', v_dono);
    END IF;

    DROP FUNCTION public.w4_sonda_default_acl_fn();
    DROP SEQUENCE public.w4_sonda_default_acl_seq;
    DROP TABLE public.w4_sonda_default_acl;
  END LOOP;

  IF v_falha <> '' THEN
    RAISE EXCEPTION 'v19_02 falhou: objeto novo ainda nasce aberto →%', v_falha;
  END IF;
  RAISE NOTICE 'v19_02: tabela, sequência e função novas de postgres e de supabase_admin nascem sem anon';
END
$prova$;

COMMIT;
