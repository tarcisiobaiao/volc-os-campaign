-- =============================================================================
-- v19_01 — Incidente da chave anon: anon perde TODO acesso a relações de public
-- MISSÃO W4 (15/10/2026). ARQUIVO. NÃO APLICADO. Exige decisão humana.
-- =============================================================================
-- APLICAR COMO: supabase_admin (superusuário: as relações de public têm dois
--   donos, postgres e supabase_admin, e só ele revoga grants de qualquer
--   concedente). Pacote completo e ordem: docs/INCIDENTE-ANON-RUNBOOK.md
--
-- DEPENDE DE: v8_01 (aplicada em 24/08), v19_00 (gatilho de users corrigido)
--             e v8_03 (RLS em public.users).
-- SUBSTITUI:  v8_04 — este arquivo faz tudo o que a v8_04 faz em public.users
--             (anon zerado; authenticated com escrita só nas colunas de perfil)
--             e o estende às demais relações. A v8_04 continua no repositório,
--             mas não deve ser aplicada: a guarda dela exige a v8_02, que muda a
--             autoridade de ADMIN do Pautador e não é necessária aqui (a v19_01
--             mantém SELECT de authenticated em users, que as policies do
--             Pautador leem).
--
-- -----------------------------------------------------------------------------
-- ESTADO MEDIDO EM PRODUÇÃO — 15/10/2026 ~10:55Z (sonda read-only, handoff B)
-- -----------------------------------------------------------------------------
-- S5  anon e authenticated: SELECT/INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/
--     TRIGGER em 62 relações de public; 39 delas sem RLS.
-- S8  SELECT real como anon devolve linha em 23, inclusive users, projects,
--     campaigns, system_settings, raw_events, site_visits, tax_history.
-- S10 default ACL de public concede arwdDxt a anon para objetos de postgres e
--     de supabase_admin (corrigido na v19_02, não aqui).
--
-- -----------------------------------------------------------------------------
-- QUEM USA anon HOJE (inventário do repositório, 15/10)
-- -----------------------------------------------------------------------------
-- Ninguém lê ou escreve dado antes do login. src/lib/supabase.ts é o único
-- cliente com a anon key; /login não chama .from/.rpc; toda rota de dado fica
-- atrás de ProtectedRoute (src/App.tsx). Servidor Node (server/, api/), FastAPI
-- (backend/), volc_ads/ e a edge function capi-router usam service_role.
-- Lacuna fora do repositório: a credencial "VOLC Oficial" do n8n (joinads,
-- gads, meta) e qualquer site externo que carregue a anon key. Conferir antes
-- da janela (preflight do pacote).
--
-- -----------------------------------------------------------------------------
-- O QUE FAZ
-- -----------------------------------------------------------------------------
-- 1. Fotografa a ACL atual de toda relação e coluna de public em
--    app_auth.w4_acl_antes (schema sem rota no PostgREST). É o que o rollback
--    usa para devolver EXATAMENTE o estado anterior, concedente por concedente.
-- 2. anon: REVOKE ALL em toda tabela, view, matview, tabela estrangeira e
--    sequência de public, para cada concedente encontrado na ACL.
-- 3. authenticated: perde TRUNCATE, REFERENCES e TRIGGER em toda relação de
--    public. TRUNCATE ignora RLS; nenhum código do repositório usa os três.
-- 4. public.users: authenticated recebe o desenho da v8_04 — SELECT de tabela
--    (até a v8_06), INSERT/UPDATE só nas colunas de perfil, DELETE filtrado pela
--    RLS da v8_03. password_hash e token_* sem escrita.
-- 5. Postflight dentro da transação: falha fechada se sobrar qualquer privilégio
--    de anon (inclusive por coluna ou herdado de PUBLIC) em public.
--
-- O QUE NÃO FAZ, DE PROPÓSITO
-- - Não restringe o SELECT/INSERT/UPDATE/DELETE de authenticated nas demais
--   tabelas: o frontend logado escreve direto em ~30 tabelas pelo PostgREST.
--   Fechar authenticated é trabalho de produto (policies por escopo), não de
--   contenção.
-- - Não mexe em EXECUTE de função. Função SECURITY INVOKER chamada por anon
--   passa a falhar por falta de grant na tabela; as SECURITY DEFINER que a S9
--   mostrou executáveis por anon são só gatilhos.
-- - Não toca storage, realtime, supabase_functions (schemas da imagem).
-- - Não mexe em service_role (BYPASSRLS; backend depende dele).
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;

-- --- Guardas de pré-condição -------------------------------------------------
DO $guard$
BEGIN
  IF NOT (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) THEN
    RAISE EXCEPTION 'v19_01 exige superusuário (supabase_admin). current_user = %', current_user;
  END IF;
  IF to_regnamespace('app_auth') IS NULL THEN
    RAISE EXCEPTION 'v19_01 abortada: schema app_auth ausente (v8_01)';
  END IF;
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.users'::regclass) THEN
    RAISE EXCEPTION 'v19_01 abortada: RLS desligada em public.users. Aplique v8_03 antes — '
                    'sem ela, o SELECT mantido para authenticated expõe todas as linhas.';
  END IF;
  IF to_regclass('app_auth.w4_acl_antes') IS NOT NULL THEN
    RAISE EXCEPTION 'v19_01 já aplicada (app_auth.w4_acl_antes existe) — esta migration não reaplica. '
                    'Para refazer: v19_99_rollback.sql e depois esta.';
  END IF;
END
$guard$;

-- =============================================================================
-- 1. Fotografia da ACL anterior (só o necessário para o rollback)
-- =============================================================================
CREATE TABLE app_auth.w4_acl_antes (
  relacao      text        NOT NULL,   -- nome qualificado, sem depender de oid
  coluna       text        NULL,       -- NULL = privilégio de relação
  relkind      "char"      NOT NULL,
  acl          aclitem[]   NULL,       -- NULL = ACL padrão do dono
  capturado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (relacao, coluna)
);
REVOKE ALL ON app_auth.w4_acl_antes FROM PUBLIC, anon, authenticated, service_role;
COMMENT ON TABLE app_auth.w4_acl_antes IS
  'v19_01 (incidente anon, W4): ACL de public antes do fechamento. Lida só pelo '
  'v19_99_rollback.sql, que a apaga ao terminar. Sem rota REST.';

INSERT INTO app_auth.w4_acl_antes (relacao, coluna, relkind, acl)
SELECT c.oid::regclass::text, NULL, c.relkind, c.relacl
  FROM pg_class c
 WHERE c.relnamespace = 'public'::regnamespace
   AND c.relkind IN ('r','p','v','m','f','S');

INSERT INTO app_auth.w4_acl_antes (relacao, coluna, relkind, acl)
SELECT c.oid::regclass::text, a.attname, c.relkind, a.attacl
  FROM pg_attribute a
  JOIN pg_class c ON c.oid = a.attrelid
 WHERE c.relnamespace = 'public'::regnamespace
   AND c.relkind IN ('r','p','v','m','f')
   AND a.attnum > 0 AND NOT a.attisdropped
   AND a.attacl IS NOT NULL;

-- =============================================================================
-- 2. anon — zero acesso a relações de public; 3. authenticated sem T/x/t
-- =============================================================================
DO $fecha$
DECLARE
  r       record;
  g       record;
  v_tipo  text;
  v_n     int := 0;
BEGIN
  FOR r IN
    SELECT c.oid, c.oid::regclass AS obj, c.relkind
      FROM pg_class c
     WHERE c.relnamespace = 'public'::regnamespace
       AND c.relkind IN ('r','p','v','m','f','S')
     ORDER BY 2
  LOOP
    v_tipo := CASE WHEN r.relkind = 'S' THEN 'SEQUENCE' ELSE 'TABLE' END;

    -- Um REVOKE por concedente: grant dado por um papel só sai com GRANTED BY ele.
    FOR g IN
      SELECT DISTINCT pg_get_userbyid(x.grantor) AS grantor
        FROM pg_class c, aclexplode(c.relacl) x
       WHERE c.oid = r.oid
         AND x.grantee IN ('anon'::regrole, 'authenticated'::regrole)
    LOOP
      -- GRANTED BY exige ser o próprio concedente: o superusuário assume o papel.
      EXECUTE format('SET LOCAL ROLE %I', g.grantor);
      EXECUTE format('REVOKE ALL ON %s %s FROM anon', v_tipo, r.obj);
      IF r.relkind <> 'S' THEN
        EXECUTE format('REVOKE TRUNCATE, REFERENCES, TRIGGER ON TABLE %s FROM authenticated', r.obj);
      END IF;
      RESET ROLE;
      v_n := v_n + 1;
    END LOOP;

    -- Privilégio de coluna concedido por papel que não aparece na ACL da relação.
    FOR g IN
      SELECT DISTINCT pg_get_userbyid(x.grantor) AS grantor
        FROM pg_attribute a, aclexplode(a.attacl) x
       WHERE a.attrelid = r.oid AND a.attnum > 0
         AND x.grantee = 'anon'::regrole
    LOOP
      EXECUTE format('SET LOCAL ROLE %I', g.grantor);
      EXECUTE format('REVOKE ALL ON TABLE %s FROM anon', r.obj);
      RESET ROLE;
    END LOOP;
  END LOOP;
  RAISE NOTICE 'v19_01: % par(es) relação×concedente revogados para anon', v_n;
END
$fecha$;

-- =============================================================================
-- 4. public.users — desenho da v8_04 para authenticated
-- =============================================================================
REVOKE ALL PRIVILEGES ON TABLE public.users FROM authenticated;

-- SELECT de tabela até a v8_06 (que exige o frontend sem select('*') em users).
GRANT SELECT ON TABLE public.users TO authenticated;

GRANT INSERT (id, name, email, role, first_login, needs_password_change, commission_percentage)
  ON TABLE public.users TO authenticated;

GRANT UPDATE (name, email, role, first_login, needs_password_change, commission_percentage, updated_at)
  ON TABLE public.users TO authenticated;

-- DELETE filtrado por users_delete_admin (v8_03) e pelo gatilho de último ADMIN.
GRANT DELETE ON TABLE public.users TO authenticated;

-- =============================================================================
-- 5. Postflight — falha fechada
-- =============================================================================
DO $verify$
DECLARE
  v_rel   text;
  v_col   text;
  v_trunc text;
  v_sens  int;
BEGIN
  -- has_*_privilege considera também o que anon herda de PUBLIC.
  SELECT string_agg(c.oid::regclass::text, ', ') INTO v_rel
    FROM pg_class c
   WHERE c.relnamespace = 'public'::regnamespace
     AND c.relkind IN ('r','p','v','m','f')
     AND has_table_privilege('anon', c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER');
  IF v_rel IS NOT NULL THEN
    RAISE EXCEPTION 'v19_01 falhou: anon ainda tem privilégio em: %', v_rel;
  END IF;

  SELECT string_agg(c.oid::regclass::text, ', ') INTO v_rel
    FROM pg_class c
   WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'S'
     -- CASE: o planejador não garante a ordem do AND, e has_sequence_privilege
     -- aborta se avaliado sobre um índice ou tabela.
     AND CASE WHEN c.relkind = 'S' THEN has_sequence_privilege('anon', c.oid, 'USAGE,SELECT,UPDATE') END;
  IF v_rel IS NOT NULL THEN
    RAISE EXCEPTION 'v19_01 falhou: anon ainda usa a(s) sequência(s): %', v_rel;
  END IF;

  SELECT string_agg(DISTINCT c.oid::regclass::text, ', ') INTO v_col
    FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
   WHERE c.relnamespace = 'public'::regnamespace
     AND c.relkind IN ('r','p','v','m','f')
     AND a.attnum > 0 AND NOT a.attisdropped
     AND has_column_privilege('anon', c.oid, a.attnum, 'SELECT,INSERT,UPDATE,REFERENCES');
  IF v_col IS NOT NULL THEN
    RAISE EXCEPTION 'v19_01 falhou: anon ainda tem privilégio de coluna em: %', v_col;
  END IF;

  SELECT string_agg(c.oid::regclass::text, ', ') INTO v_trunc
    FROM pg_class c
   WHERE c.relnamespace = 'public'::regnamespace
     AND c.relkind IN ('r','p','f')
     AND has_table_privilege('authenticated', c.oid, 'TRUNCATE');
  IF v_trunc IS NOT NULL THEN
    RAISE EXCEPTION 'v19_01 falhou: authenticated ainda pode TRUNCATE em: %', v_trunc;
  END IF;

  SELECT count(*) INTO v_sens
    FROM information_schema.column_privileges
   WHERE table_schema = 'public' AND table_name = 'users'
     AND grantee IN ('anon', 'authenticated', 'PUBLIC')
     AND column_name IN ('password_hash', 'token_primeiro_acesso', 'token_expiracao')
     AND privilege_type IN ('INSERT', 'UPDATE');
  IF v_sens > 0 THEN
    RAISE EXCEPTION 'v19_01 falhou: escrita em coluna sensível de users ainda aberta (%)', v_sens;
  END IF;

  RAISE NOTICE 'v19_01: anon sem privilégio em relação, coluna ou sequência de public; '
               'authenticated sem TRUNCATE; users com escrita só nas colunas de perfil';
END
$verify$;

COMMIT;

-- PostgREST relê o cache de schema (fora da transação; inofensivo se repetir).
NOTIFY pgrst, 'reload schema';
