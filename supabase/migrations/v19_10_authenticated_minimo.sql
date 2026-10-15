-- =============================================================================
-- v19_10 — authenticated com privilégio mínimo em public (pacote SEPARADO do
-- incidente anon). MISSÃO W4 (15/10/2026). ARQUIVO. NÃO APLICADO.
-- =============================================================================
-- APLICAR COMO: supabase_admin. DEPOIS do pacote anon (v19_00 v8_03 v19_01 v8_05
-- v19_02) e do cadastro público fechado no GoTrue. Rollback: v19_10_rollback.sql.
--
-- ESTADO DE PARTIDA (medido no lab sobre o schema de produção de 15/10, depois
-- do pacote anon): authenticated tem SELECT/INSERT/UPDATE/DELETE em 61 relações
-- de public (as 62 da S8 menos users, que tem RLS da v8_03); 37 tabelas delas
-- sem RLS. O app escreve direto em ~15; as RPCs que ele chama e os gatilhos que
-- elas disparam são SECURITY INVOKER (rodam como authenticated) e escrevem em
-- outras 6 (daily_campaign_metrics, daily_project_metrics, adsense_metrics,
-- gam_metrics, campaigns, sync_logs).
--
-- O QUE FAZ
-- 1. Fotografa ACL (relação e coluna) e o estado de RLS de toda relação de
--    public em app_auth.w4_auth_acl, e registra as policies que cria em
--    app_auth.w4_auth_policy, para o rollback devolver exatamente o estado anterior.
-- 2. authenticated: para cada relação onde tem privilégio hoje, REVOKE de tudo e
--    GRANT só do que a tabela de decisão abaixo diz — cada linha com a chamada
--    no código que a justifica. Relação fora da tabela fica sem grant.
--    NUNCA concede o que authenticated não tinha antes (só restringe).
-- 3. RLS: liga em toda tabela onde authenticated tinha privilégio e não havia
--    RLS, com uma policy por comando concedido (TO authenticated, USING true).
--    Escopo por usuário (OPERATOR só vê o que é dele) é trabalho de produto,
--    não deste arquivo. Para não mudar o comportamento de outro papel que
--    tenha grant nessas tabelas e não atravesse RLS (ex.: volc_leitura da v18_01,
--    se já existir), cria uma policy de preservação para ele.
-- 4. Postflight: os privilégios efetivos de authenticated batem com a tabela de
--    decisão em todas as relações de public, e nenhuma relação com grant ficou
--    sem policy para os comandos concedidos.
--
-- O QUE NÃO FAZ: não toca users/users_safe (v8_03/v19_01/v8_05), anon,
-- service_role, funções nem tabelas que authenticated não alcança hoje.
-- =============================================================================

\set ON_ERROR_STOP on

BEGIN;
SET LOCAL search_path = pg_catalog;

DO $guard$
BEGIN
  IF NOT (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) THEN
    RAISE EXCEPTION 'v19_10 exige superusuário (supabase_admin). current_user = %', current_user;
  END IF;
  IF to_regclass('app_auth.w4_acl') IS NULL THEN
    RAISE EXCEPTION 'v19_10 abortada: o pacote anon (v19_01) não está aplicado; ele vem antes';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace
               AND c.relkind IN ('r','p','v','m','f')
               AND has_table_privilege('anon', c.oid, 'SELECT,INSERT,UPDATE,DELETE')) THEN
    RAISE EXCEPTION 'v19_10 abortada: anon ainda tem privilégio em public; aplique o pacote anon antes';
  END IF;
  IF to_regclass('app_auth.w4_auth_acl') IS NOT NULL THEN
    RAISE EXCEPTION 'v19_10 já aplicada (app_auth.w4_auth_acl existe) — não reaplica; use v19_10_rollback.sql antes';
  END IF;
END
$guard$;

-- -----------------------------------------------------------------------------
-- Tabela de decisão: o que authenticated PODE em cada relação. s/i/u/d.
-- Fontes: inventário do frontend (src/, chamadas .from/.rpc alcançáveis a partir
-- de src/main.tsx) e grafo de RPCs/gatilhos INVOKER do dump de produção de 15/10.
-- -----------------------------------------------------------------------------
CREATE TEMP TABLE w4_decisao (relacao text PRIMARY KEY, s bool, i bool, u bool, d bool, evidencia text) ON COMMIT DROP;
INSERT INTO w4_decisao VALUES
-- escrita direta do browser
 ('projects',                    true, true,  true,  false, 'ProjectsSettings.tsx:374 insert, :440 update; supabaseDataService.ts:3032 insert; RPC enrich_campaign_with_google_ads e gatilho DPM inserem'),
 ('campaigns',                   true, true,  true,  false, 'supabaseDataService.ts:3057 upsert; RPCs enrich_campaign_with_google_ads, process_gam_metrics_auto, user_update_campaign_status'),
 ('user_campaigns',              true, true,  false, true,  'campaignMembersService.ts:231 insert, :312 delete; usersService.ts:177 insert, :243 delete'),
 ('user_projects',               true, true,  false, true,  'campaignMembersService.ts:252 insert, :343 delete; usersService.ts:155 insert, :225 delete'),
 ('tax_history',                 true, true,  true,  false, 'taxHistoryService.ts:76 update, :91 insert, :285 insert'),
 ('campaign_funnel_urls',        true, true,  true,  false, 'campaignFunnelUrlsService.ts:46 update, :59 upsert, :85 insert'),
 ('gam_metrics',                 true, true,  true,  false, 'supabaseDataService.ts:3111 upsert; RPC process_gam_metrics_auto; update_all_revenue_conversions'),
 ('operational_costs',           true, true,  true,  true,  'operationalCostsService.ts:158 insert, :172 update, :187 delete'),
 ('operational_cost_categories', true, true,  true,  true,  'operationalCostsService.ts:43 insert, :54 update, :66 delete'),
 ('incubator_sites',             true, true,  true,  true,  'incubatorService.ts:54 insert, :78 update, :94 delete; RPC insert_incubator_articles_batch atualiza'),
 ('incubator_articles',          true, true,  true,  true,  'useTitles.ts:30 delete, :65 update; incubatorService.ts:259 update; RPC insert_incubator_articles_batch insere'),
 ('pautador_opportunities',      true, false, true,  false, 'pautadorService.ts:110 update'),
 ('pautador_entity_opportunities',true,false, true,  false, 'pautadorEntityService.ts:77 update'),
 ('pautador_countries',          true, true,  false, false, 'pautadorService.ts:51 insert'),
-- escrita só por RPC/gatilho INVOKER que o browser dispara
 ('daily_campaign_metrics',      true, true,  true,  false, 'gatilhos de gam_metrics/campaign_funnel_urls/adsense_metrics/users e update_all_revenue_conversions inserem/atualizam'),
 ('daily_project_metrics',       true, false, true,  false, 'gatilho de projects (trigger_recalculate_project_revshare) e update_all_revenue_conversions atualizam'),
 ('adsense_metrics',             true, false, true,  false, 'update_all_revenue_conversions atualiza; gatilhos de campaign_funnel_urls e vw_adsense_adjusted leem'),
 ('sync_logs',                   false,true,  false, false, 'RPCs enrich_campaign_with_google_ads, process_gam_metrics_auto, user_update_campaign_status inserem'),
-- só leitura
 ('system_settings',             true, false, false, false, 'supabaseDataService.ts:4122; get_last_data_update e gatilhos leem. UPDATE só em componentes sem import (ExchangeRateManager)'),
 ('exchange_rate_history',       true, false, false, false, 'get_exchange_rate_for_date (gatilhos de daily_campaign_metrics/gam_metrics) lê'),
 ('campaign_highlights',         true, false, false, false, 'RPC get_rotated_campaign_highlights lê'),
 ('incubator_pipeline_logs',     true, false, false, false, 'incubatorService.ts:118'),
 ('v_incubator_schedule_progress',true,false, false, false, 'incubatorService.ts:243'),
 ('vw_display_roi',              true, false, false, false, 'useDisplayROI.ts:29'),
 ('display_ads_placements',      true, false, false, false, 'lida por vw_display_roi (security_invoker) — useDisplayROI.ts:29; medido no lab'),
 ('display_gam_placements',      true, false, false, false, 'lida por vw_display_roi (security_invoker) — useDisplayROI.ts:29; medido no lab'),
 ('vw_adsense_adjusted',         true, false, false, false, 'lida por simple_aggregate_campaign_revenue (gatilho de adsense_metrics)'),
 ('pautador_agent_logs',         true, false, false, false, 'pautadorService.ts:147'),
 ('pautador_entities',           true, false, false, false, 'pautadorEntityService.ts:25 (embed entity:pautador_entities)'),
 ('pautador_entity_funnel_hypotheses', true, false, false, false, 'pautadorEntityService.ts:41'),
 ('pautador_entity_pains',       true, false, false, false, 'pautadorEntityService.ts:39'),
 ('pautador_entity_seed_queries',true, false, false, false, 'pautadorEntityService.ts:40'),
 ('pautador_funnels',            true, false, false, false, 'pautadorService.ts:134'),
 ('pautador_keyword_clusters',   true, false, false, false, 'pautadorService.ts:121'),
 ('pautador_runs',               true, false, false, false, 'pautadorService.ts:64, :77');
-- Qualquer outra relação de public onde authenticated tem privilégio hoje fica
-- SEM grant: nenhuma chamada .from/.rpc alcançável nem RPC/gatilho INVOKER a usa.

-- -----------------------------------------------------------------------------
-- 1. Fotografia
-- -----------------------------------------------------------------------------
CREATE TABLE app_auth.w4_auth_acl (
  esquema text NOT NULL, relacao text NOT NULL, coluna text NULL, relkind "char" NOT NULL,
  acl_antes aclitem[], acl_depois aclitem[], rls_antes bool, rls_depois bool,
  capturado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT (esquema, relacao, coluna));
CREATE TABLE app_auth.w4_auth_policy (
  esquema text NOT NULL, relacao text NOT NULL, policy text NOT NULL, PRIMARY KEY (esquema, relacao, policy));
REVOKE ALL ON app_auth.w4_auth_acl, app_auth.w4_auth_policy FROM PUBLIC, anon, authenticated, service_role;
COMMENT ON TABLE app_auth.w4_auth_acl IS 'v19_10 (W4): ACL e RLS de public antes/depois; lida pelo v19_10_rollback.sql, que a apaga.';

INSERT INTO app_auth.w4_auth_acl (esquema, relacao, coluna, relkind, acl_antes, rls_antes)
SELECT n.nspname, c.relname, NULL, c.relkind, c.relacl, c.relrowsecurity
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','f','S');
INSERT INTO app_auth.w4_auth_acl (esquema, relacao, coluna, relkind, acl_antes)
SELECT n.nspname, c.relname, a.attname, c.relkind, a.attacl
  FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','f') AND a.attnum > 0 AND NOT a.attisdropped;

-- -----------------------------------------------------------------------------
-- 2 e 3. Grants mínimos e RLS
-- -----------------------------------------------------------------------------
DO $aplica$
DECLARE
  r record; g record; o record; dec record;
  v_privs text[]; v_cmd text; v_pol text; v_n_rls int := 0; v_n_rel int := 0;
BEGIN
  FOR r IN
    SELECT c.oid, c.oid::regclass AS obj, c.relname, c.relkind
      FROM pg_class c
     WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r','p','v','m','f')
       AND c.relname NOT IN ('users', 'users_safe')
       AND EXISTS (SELECT 1 FROM aclexplode(c.relacl) x WHERE x.grantee = 'authenticated'::regrole)
     ORDER BY c.relname
  LOOP
    v_n_rel := v_n_rel + 1;
    SELECT * INTO dec FROM w4_decisao WHERE relacao = r.relname;
    -- o que authenticated tinha (para nunca conceder além disso)
    SELECT array_agg(DISTINCT x.privilege_type) INTO v_privs
      FROM pg_class c, aclexplode(c.relacl) x
     WHERE c.oid = r.oid AND x.grantee = 'authenticated'::regrole;

    -- REVOKE de tudo, concedente por concedente
    FOR g IN SELECT DISTINCT pg_get_userbyid(x.grantor) AS grantor
               FROM pg_class c, aclexplode(c.relacl) x
              WHERE c.oid = r.oid AND x.grantee = 'authenticated'::regrole LOOP
      EXECUTE format('SET LOCAL ROLE %I', g.grantor);
      EXECUTE format('REVOKE ALL ON TABLE %s FROM authenticated', r.obj);
      RESET ROLE;
    END LOOP;

    IF dec.relacao IS NULL THEN CONTINUE; END IF;  -- sem grant

    -- GRANT só do decidido e que já existia
    FOR v_cmd IN SELECT unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE']) LOOP
      IF (v_cmd = 'SELECT' AND dec.s) OR (v_cmd = 'INSERT' AND dec.i)
         OR (v_cmd = 'UPDATE' AND dec.u) OR (v_cmd = 'DELETE' AND dec.d) THEN
        IF NOT v_cmd = ANY (coalesce(v_privs, '{}')) THEN
          RAISE EXCEPTION 'v19_10: a decisão concederia % em % que authenticated não tinha — recusado (só restringe)', v_cmd, r.obj;
        END IF;
        EXECUTE format('GRANT %s ON TABLE %s TO authenticated', v_cmd, r.obj);
      END IF;
    END LOOP;
  END LOOP;

  -- RLS nas tabelas (r/p) que authenticated alcançava sem RLS
  FOR r IN
    SELECT c.oid, c.oid::regclass AS obj, c.relname
      FROM pg_class c JOIN app_auth.w4_auth_acl s
        ON s.esquema = 'public' AND s.relacao = c.relname AND s.coluna IS NULL
     WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r','p')
       AND c.relname NOT IN ('users')
       AND NOT s.rls_antes
       AND EXISTS (SELECT 1 FROM aclexplode(s.acl_antes) x WHERE x.grantee = 'authenticated'::regrole)
     ORDER BY c.relname
  LOOP
    EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', r.obj);
    v_n_rls := v_n_rls + 1;
    SELECT * INTO dec FROM w4_decisao WHERE relacao = r.relname;
    IF dec.relacao IS NOT NULL THEN
      FOR v_cmd IN SELECT unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE']) LOOP
        IF (v_cmd = 'SELECT' AND dec.s) OR (v_cmd = 'INSERT' AND dec.i)
           OR (v_cmd = 'UPDATE' AND dec.u) OR (v_cmd = 'DELETE' AND dec.d) THEN
          v_pol := 'w4a_' || lower(v_cmd);
          EXECUTE format('CREATE POLICY %I ON %s AS PERMISSIVE FOR %s TO authenticated %s',
                         v_pol, r.obj, v_cmd,
                         CASE v_cmd WHEN 'INSERT' THEN 'WITH CHECK (true)'
                                    WHEN 'UPDATE' THEN 'USING (true) WITH CHECK (true)'
                                    ELSE 'USING (true)' END);
          INSERT INTO app_auth.w4_auth_policy VALUES ('public', r.relname, v_pol);
        END IF;
      END LOOP;
    END IF;
    -- preserva quem já lia/escrevia a tabela sem atravessar RLS (papéis que não
    -- são anon/authenticated nem BYPASSRLS/superusuário)
    FOR o IN SELECT DISTINCT x.grantee::regrole::text AS papel
               FROM pg_class c, aclexplode(c.relacl) x JOIN pg_roles pr ON pr.oid = x.grantee
              WHERE c.oid = r.oid AND x.grantee <> 0
                AND pr.rolname NOT IN ('anon', 'authenticated')
                AND NOT pr.rolbypassrls AND NOT pr.rolsuper LOOP
      v_pol := 'w4a_preserva_' || o.papel;
      EXECUTE format('CREATE POLICY %I ON %s AS PERMISSIVE FOR ALL TO %I USING (true) WITH CHECK (true)', v_pol, r.obj, o.papel);
      INSERT INTO app_auth.w4_auth_policy VALUES ('public', r.relname, v_pol);
    END LOOP;
  END LOOP;
  FOR dec IN SELECT relacao FROM w4_decisao WHERE to_regclass('public.' || quote_ident(relacao)) IS NULL LOOP
    RAISE NOTICE 'v19_10: % está na decisão mas não existe neste banco — ignorada', dec.relacao;
  END LOOP;
  RAISE NOTICE 'v19_10: % relações revistas para authenticated; RLS ligada em % tabelas', v_n_rel, v_n_rls;
END
$aplica$;

-- -----------------------------------------------------------------------------
-- 4. Fotografia do depois e postflight
-- -----------------------------------------------------------------------------
UPDATE app_auth.w4_auth_acl s SET acl_depois = c.relacl, rls_depois = c.relrowsecurity
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE s.coluna IS NULL AND n.nspname = s.esquema AND c.relname = s.relacao;
UPDATE app_auth.w4_auth_acl s SET acl_depois = a.attacl
  FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE s.coluna IS NOT NULL AND n.nspname = s.esquema AND c.relname = s.relacao AND a.attname = s.coluna;
DELETE FROM app_auth.w4_auth_acl
 WHERE acl_antes IS NOT DISTINCT FROM acl_depois AND rls_antes IS NOT DISTINCT FROM rls_depois;

DO $verify$
DECLARE v_err text;
BEGIN
  SELECT string_agg(format('%s(%s)', c.relname, p.cmd), ', ') INTO v_err
    FROM pg_class c
    CROSS JOIN (VALUES ('SELECT'),('INSERT'),('UPDATE'),('DELETE')) p(cmd)
    LEFT JOIN w4_decisao d ON d.relacao = c.relname
   WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r','p','v','m','f')
     AND c.relname NOT IN ('users', 'users_safe')
     AND has_table_privilege('authenticated', c.oid, p.cmd)
         IS DISTINCT FROM coalesce(CASE p.cmd WHEN 'SELECT' THEN d.s WHEN 'INSERT' THEN d.i
                                              WHEN 'UPDATE' THEN d.u ELSE d.d END, false)
     -- relação que authenticated não tinha antes nem ganha: fora do escopo
     AND (has_table_privilege('authenticated', c.oid, p.cmd)
          OR EXISTS (SELECT 1 FROM app_auth.w4_auth_acl s, aclexplode(s.acl_antes) x
                      WHERE s.relacao = c.relname AND s.coluna IS NULL
                        AND x.grantee = 'authenticated'::regrole AND x.privilege_type = p.cmd));
  IF v_err IS NOT NULL THEN
    RAISE EXCEPTION 'v19_10 falhou: privilégio de authenticated diverge da decisão em: %', v_err;
  END IF;

  SELECT string_agg(c.relname, ', ') INTO v_err
    FROM pg_class c
   WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r','p')
     AND c.relname <> 'users'
     AND has_table_privilege('authenticated', c.oid, 'SELECT,INSERT,UPDATE,DELETE')
     AND NOT c.relrowsecurity;
  IF v_err IS NOT NULL THEN
    RAISE EXCEPTION 'v19_10 falhou: tabela com grant para authenticated e sem RLS: %', v_err;
  END IF;

  IF EXISTS (SELECT 1 FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace
               AND c.relkind IN ('r','p','f') AND has_table_privilege('authenticated', c.oid, 'TRUNCATE')) THEN
    RAISE EXCEPTION 'v19_10 falhou: authenticated com TRUNCATE';
  END IF;
  RAISE NOTICE 'v19_10: privilégios de authenticated = tabela de decisão; RLS em toda tabela que ele alcança';
END
$verify$;

COMMIT;

NOTIFY pgrst, 'reload schema';
