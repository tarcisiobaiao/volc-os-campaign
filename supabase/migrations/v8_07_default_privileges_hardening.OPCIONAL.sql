-- =============================================================================
-- v8_07 — Correcao de raiz: tabela nova em public para de nascer aberta a anon
-- SPRINT 1A / FRENTE 2 — ARQUIVO OPCIONAL. NAO FAZ PARTE DA SEQUENCIA MINIMA.
-- =============================================================================
-- NAO APLICADO. Convencao de sufixo herdada de
-- src/sql/volc-sync/04_monthly_exchange_rate.BLOQUEADO.sql: arquivo fora da
-- ordem obrigatoria, que exige decisao antes de rodar.
--
-- APLICAR COMO: postgres E depois como supabase_admin (sao DOIS donos de
--   default ACL; um so nao resolve — ver medicao abaixo)
--
-- -----------------------------------------------------------------------------
-- POR QUE ISSO EXISTE
-- -----------------------------------------------------------------------------
-- v8_04 conteve public.users. Mas a causa de fundo nao esta em public.users:
-- esta em pg_default_acl. Medido em 2026-08-24:
--
--   dono            schema  tipo  acl
--   postgres        public  r     anon=arwdDxt, authenticated=arwdDxt, service_role=arwdDxt
--   supabase_admin  public  r     anon=arwdDxt, authenticated=arwdDxt, service_role=arwdDxt
--   postgres        public  f     anon=X, authenticated=X, service_role=X
--   supabase_admin  public  f     anon=X, authenticated=X, service_role=X
--
-- Leitura: TODA tabela criada em public por postgres ou supabase_admin nasce
-- com SELECT/INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER para anon. TODA
-- funcao nasce executavel por anon. Isso explica o estado das 59 tabelas de
-- public, das quais 38 estao com RLS desligada, e explica por que v8_01 e v8_05
-- precisam revogar nominalmente cada objeto que criam.
--
-- Enquanto esse default existir, cada migration futura tem que lembrar de
-- revogar, e a chance de esquecer e alta.
--
-- -----------------------------------------------------------------------------
-- POR QUE NAO ESTA NA SEQUENCIA OBRIGATORIA
-- -----------------------------------------------------------------------------
-- 1. E uma mudanca de plataforma, nao de uma tabela: afeta TODO objeto futuro
--    de public, inclusive os trazidos pelo sync com o webgo
--    (scripts/sync-upstream.sh, src/sql/volc-sync/*). Migration de upstream que
--    hoje depende do grant implicito passa a criar tabela que a UI nao le, e o
--    sintoma aparece longe da causa.
-- 2. NAO altera nenhum objeto que ja existe. Ligar isto NAO contem nada do que
--    ja esta aberto — so impede novos casos. Sem um passo separado de auditoria
--    e revogacao das 59 tabelas atuais, o ganho e apenas prospectivo.
-- 3. O rollback e trivial, mas o intervalo em que alguem cria uma tabela e nao
--    entende por que a tela nao carrega nao e.
--
-- Recomendacao: aplicar DEPOIS que a Frente 1/3 estabilizar e junto de uma
-- convencao escrita de "toda migration declara seus grants".
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

DO $guard$
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'v8_07 deve rodar como postgres e, em seguida, como supabase_admin';
  END IF;
  RAISE NOTICE 'v8_07: ajustando default privileges de public para o dono %', current_user;
END
$guard$;

-- Aplica ao dono corrente. Rode o arquivo DUAS vezes: uma como postgres,
-- outra como supabase_admin. As duas entradas de pg_default_acl sao
-- independentes; corrigir uma so deixa metade do buraco aberto.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE ALL ON TABLES FROM anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE ALL ON TABLES FROM authenticated;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE ALL ON FUNCTIONS FROM anon;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE ALL ON SEQUENCES FROM anon;

-- service_role permanece com o default. Sem ele o backend inteiro para, e o
-- problema do service_role nao e o grant: e nao haver autenticacao nos
-- endpoints que carregam a chave (Frente 1/3).

COMMIT;

-- =============================================================================
-- ROLLBACK DESTE ARQUIVO (rodar tambem duas vezes, um dono por vez)
-- =============================================================================
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES    TO anon, authenticated;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO anon;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO anon;
--
-- VERIFICACAO (somente leitura)
-- SELECT defaclrole::regrole, defaclobjtype, defaclacl FROM pg_default_acl
--  WHERE defaclnamespace = 'public'::regnamespace;
