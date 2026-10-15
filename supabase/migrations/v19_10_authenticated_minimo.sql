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
-- 5. Funil (seção 2c): RLS de campaign_funnel_urls por escopo (ADMIN ou operador
--    vinculado à campanha, URL do domínio do projeto); os dois gatilhos de
--    agregação recalculam só a campanha da linha e rodam como o papel dedicado
--    volc_agregador_funil (não superusuário, sem BYPASSRLS, só o que o recálculo usa).
-- 6. Default ACL de public: tabela/sequência nova de postgres e supabase_admin
--    nasce sem nada para anon e authenticated (seção 2d).
--
-- O QUE NÃO FAZ: não toca users/users_safe (v8_03/v19_01/v8_05), anon (já
-- fechado), service_role, nem tabelas que authenticated não alcança hoje.
-- LACUNA DECLARADA: função nova em public segue nascendo com EXECUTE para
-- authenticated e service_role (default ACL de funções de postgres e
-- supabase_admin); a próxima SECURITY DEFINER sem REVOKE explícito fica chamável
-- por qualquer logado via /rpc. Não fechado neste ciclo.
--
-- ORDEM (provisória, a confirmar com os revisores): v19 (pacote anon) → v19_10 →
-- v23_01 (W12). Reverter na ordem inversa: v23_01_rollback → v19_10_rollback →
-- v19_99. A revisão local mediu as duas ordens; nenhum rollback confere se o
-- outro rodou.
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
-- admin = escrita (INSERT/UPDATE/DELETE) só passa a policy se public.volc_current_admin()
--         (tabelas de dinheiro: receita, comissão, revshare, imposto, custo). O app
--         escreve nelas por tela de ADMIN ou por gatilho/RPC INVOKER disparado por ela;
--         um OPERADOR que dispare a cascata recebe erro de RLS em vez de reescrever dinheiro.
-- upd_cols = UPDATE só nessas colunas (o código não muda outras).
CREATE TEMP TABLE w4_decisao (relacao text PRIMARY KEY, s bool, i bool, u bool, d bool, evidencia text,
                              admin bool NOT NULL DEFAULT false, upd_cols text[]) ON COMMIT DROP;
INSERT INTO w4_decisao (relacao, s, i, u, d, evidencia) VALUES
-- escrita direta do browser
 ('projects',                    true, true,  true,  false, 'ProjectsSettings.tsx:374 insert, :440 update; supabaseDataService.ts:3032 insert; RPC enrich_campaign_with_google_ads e gatilho DPM inserem'),
 ('campaigns',                   true, false, false, false, 'leitura em ~25 pontos (supabaseDataService.ts, v6/*). INSERT/UPDATE retirados: ver nota abaixo'),
 ('user_campaigns',              true, true,  false, true,  'campaignMembersService.ts:231 insert, :312 delete; usersService.ts:177 insert, :243 delete'),
 ('user_projects',               true, true,  false, true,  'campaignMembersService.ts:252 insert, :343 delete; usersService.ts:155 insert, :225 delete'),
 ('tax_history',                 true, true,  true,  false, 'taxHistoryService.ts:76 update, :91 insert, :285 insert'),
 ('campaign_funnel_urls',        true, true,  true,  false, 'campaignFunnelUrlsService.ts:46 update, :59 upsert, :85 insert'),
 ('gam_metrics',                 true, false, true,  false, 'update_all_revenue_conversions (currencyConversionService.ts:218, GeneralDashboard.tsx:555) atualiza; leitura supabaseDataService.ts:2159. INSERT retirado: ver nota'),
 ('operational_costs',           true, true,  true,  true,  'operationalCostsService.ts:158 insert, :172 update, :187 delete'),
 ('operational_cost_categories', true, true,  true,  true,  'operationalCostsService.ts:43 insert, :54 update, :66 delete'),
 ('incubator_sites',             true, true,  true,  true,  'incubatorService.ts:54 insert, :78 update, :94 delete; RPC insert_incubator_articles_batch atualiza'),
 ('incubator_articles',          true, true,  true,  true,  'useTitles.ts:30 delete, :65 update; incubatorService.ts:259 update; RPC insert_incubator_articles_batch insere'),
 ('pautador_opportunities',      true, false, true,  false, 'pautadorService.ts:110 update'),
 ('pautador_entity_opportunities',true,false, true,  false, 'pautadorEntityService.ts:77 update'),
 ('pautador_countries',          true, true,  false, false, 'pautadorService.ts:51 insert'),
-- escrita só por RPC/gatilho INVOKER que o browser dispara
 ('daily_campaign_metrics',      true, true,  true,  false, 'INSERT/UPDATE pelos gatilhos INVOKER de adsense_metrics (simple_aggregate_campaign_revenue, via update_all_revenue_conversions, GeneralDashboard.tsx:555) e de users (comissão); medido no lab: sem o INSERT, update_all_revenue_conversions falha. Escrita só ADMIN (policy). Leitura em ~20 pontos'),
 ('daily_project_metrics',       true, false, true,  false, 'gatilho de projects (trigger_recalculate_project_revshare) e update_all_revenue_conversions atualizam'),
 ('adsense_metrics',             true, false, true,  false, 'update_all_revenue_conversions atualiza; gatilhos de campaign_funnel_urls e vw_adsense_adjusted leem'),
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
--
-- RETIRADOS na revisão de 15/10 (serviam só a código morto ou já quebrado):
--   INSERT e UPDATE em campaigns, INSERT em gam_metrics, INSERT em sync_logs.
--   Os chamadores são processGoogleAdsData, processGoogleAdsDataLegacy,
--   processGamMetrics e processGamMetricsLegacy (supabaseDataService.ts:2985,
--   3004, 3088, 3107 — nenhum chamador em src/), que usam enrich_campaign_with_google_ads
--   e process_gam_metrics_auto (esta já falha com 42702); e
--   user_update_campaign_status (CampaignsSettings.tsx:261/280), que já falha com
--   42703 (campaigns.user_paused_at não existe em produção). O upsert de
--   gam_metrics (supabaseDataService.ts:3111) já falha hoje com 42501 no gatilho
--   sync_gam_revenue_to_daily_metrics (lê trafego_meta_adset, sem grant).

UPDATE w4_decisao SET admin = true
 WHERE relacao IN ('projects', 'tax_history', 'gam_metrics', 'operational_costs',
                   'daily_campaign_metrics', 'daily_project_metrics', 'adsense_metrics',
                   -- vínculo operador×campanha/projeto decide comissão e escopo: só ADMIN
                   -- (telas adminOnly; o v6 que também grava está desligado)
                   'user_campaigns', 'user_projects');
UPDATE w4_decisao SET upd_cols = ARRAY['status'] WHERE relacao = 'pautador_opportunities';
UPDATE w4_decisao SET upd_cols = ARRAY['status', 'kanban_stage'] WHERE relacao = 'pautador_entity_opportunities';

-- -----------------------------------------------------------------------------
-- 1. Fotografia
-- -----------------------------------------------------------------------------
CREATE TABLE app_auth.w4_auth_acl (
  esquema text NOT NULL, relacao text NOT NULL, coluna text NULL, relkind "char" NOT NULL,
  acl_antes aclitem[], acl_depois aclitem[], rls_antes bool, rls_depois bool,
  pol_antes text, pol_depois text,   -- md5 da definição de todas as policies da relação
  capturado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT (esquema, relacao, coluna));
CREATE TABLE app_auth.w4_auth_policy (
  esquema text NOT NULL, relacao text NOT NULL, policy text NOT NULL, PRIMARY KEY (esquema, relacao, policy));
CREATE TABLE app_auth.w4_auth_func (
  assinatura text PRIMARY KEY, dono_antes text, def_antes text, dono_depois text, def_depois_md5 text);
CREATE TABLE app_auth.w4_auth_criados (tipo text NOT NULL, nome text NOT NULL, PRIMARY KEY (tipo, nome));
CREATE TABLE app_auth.w4_auth_defacl (
  papel text NOT NULL, objtipo "char" NOT NULL, acl_antes aclitem[], acl_depois aclitem[], PRIMARY KEY (papel, objtipo));
REVOKE ALL ON app_auth.w4_auth_acl, app_auth.w4_auth_policy, app_auth.w4_auth_func, app_auth.w4_auth_defacl, app_auth.w4_auth_criados
  FROM PUBLIC, anon, authenticated, service_role;
COMMENT ON TABLE app_auth.w4_auth_acl IS 'v19_10 (W4): ACL e RLS de public antes/depois; lida pelo v19_10_rollback.sql, que a apaga.';

-- Assinatura das policies de uma relação: nome, comando, permissiva, papéis e
-- expressões. Mesma função no rollback, que aborta se ela mudou depois.
CREATE FUNCTION app_auth.w4_policies_md5(rel oid) RETURNS text LANGUAGE sql STABLE
SET search_path = pg_catalog AS $f$
  SELECT md5(coalesce(string_agg(format('%s|%s|%s|%s|%s|%s', p.polname, p.polcmd, p.polpermissive,
           (SELECT string_agg(r::regrole::text, ',' ORDER BY r::regrole::text) FROM unnest(p.polroles) r),
           coalesce(pg_get_expr(p.polqual, p.polrelid), ''), coalesce(pg_get_expr(p.polwithcheck, p.polrelid), '')),
           E'\n' ORDER BY p.polname), ''))
    FROM pg_policy p WHERE p.polrelid = rel
$f$;
REVOKE ALL ON FUNCTION app_auth.w4_policies_md5(oid) FROM PUBLIC, anon, authenticated, service_role;

INSERT INTO app_auth.w4_auth_acl (esquema, relacao, coluna, relkind, acl_antes, rls_antes, pol_antes)
SELECT n.nspname, c.relname, NULL, c.relkind, c.relacl, c.relrowsecurity, app_auth.w4_policies_md5(c.oid)
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
  v_privs text[]; v_cmd text; v_pol text; v_cond text; v_n_rls int := 0; v_n_rel int := 0; v_n_seq int := 0;
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
        IF v_cmd = 'UPDATE' AND dec.upd_cols IS NOT NULL THEN
          EXECUTE format('GRANT UPDATE (%s) ON TABLE %s TO authenticated',
                         (SELECT string_agg(quote_ident(c), ', ') FROM unnest(dec.upd_cols) c), r.obj);
        ELSE
          EXECUTE format('GRANT %s ON TABLE %s TO authenticated', v_cmd, r.obj);
        END IF;
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
          v_cond := CASE WHEN dec.admin THEN '(public.volc_current_admin())' ELSE '(true)' END;
          EXECUTE format('CREATE POLICY %I ON %s AS PERMISSIVE FOR %s TO authenticated %s',
                         v_pol, r.obj, v_cmd,
                         CASE v_cmd WHEN 'SELECT' THEN 'USING (true)'
                                    WHEN 'INSERT' THEN 'WITH CHECK ' || v_cond
                                    WHEN 'UPDATE' THEN 'USING (true) WITH CHECK ' || v_cond
                                    ELSE 'USING ' || v_cond END);
          INSERT INTO app_auth.w4_auth_policy VALUES ('public', r.relname, v_pol);
        END IF;
      END LOOP;
    END IF;
    -- preserva quem já lia/escrevia a tabela sem atravessar RLS (papéis que não
    -- são anon/authenticated nem BYPASSRLS/superusuário)
    -- Uma policy por comando que o papel TEM (não FOR ALL): preserva exatamente o
    -- que ele fazia, sem pré-autorizar outros comandos.
    FOR o IN SELECT DISTINCT pr.rolname AS papel, x.privilege_type AS cmd
               FROM pg_class c, aclexplode(c.relacl) x JOIN pg_roles pr ON pr.oid = x.grantee
              WHERE c.oid = r.oid AND x.grantee <> 0
                AND x.privilege_type IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE')
                AND pr.rolname NOT IN ('anon', 'authenticated')
                AND NOT pr.rolbypassrls AND NOT pr.rolsuper LOOP
      v_pol := 'w4a_preserva_' || o.papel || '_' || lower(o.cmd);
      EXECUTE format('CREATE POLICY %I ON %s AS PERMISSIVE FOR %s TO %I %s', v_pol, r.obj, o.cmd, o.papel,
                     CASE o.cmd WHEN 'INSERT' THEN 'WITH CHECK (true)' WHEN 'UPDATE' THEN 'USING (true) WITH CHECK (true)'
                                ELSE 'USING (true)' END);
      INSERT INTO app_auth.w4_auth_policy VALUES ('public', r.relname, v_pol);
    END LOOP;
  END LOOP;
  -- Sequências: authenticated perde tudo (UPDATE = setval, que deixaria um logado
  -- reposicionar a sequência de uma tabela do n8n e provocar colisão de PK) e
  -- recebe só USAGE (nextval) nas sequências que os defaults de colunas das
  -- tabelas com INSERT decidido usam.
  FOR r IN
    SELECT c.oid, c.oid::regclass AS obj, c.relname
      FROM pg_class c
     WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'S'
       AND EXISTS (SELECT 1 FROM aclexplode(c.relacl) x WHERE x.grantee = 'authenticated'::regrole)
  LOOP
    v_n_seq := v_n_seq + 1;
    FOR g IN SELECT DISTINCT pg_get_userbyid(x.grantor) AS grantor
               FROM pg_class c, aclexplode(c.relacl) x
              WHERE c.oid = r.oid AND x.grantee = 'authenticated'::regrole LOOP
      EXECUTE format('SET LOCAL ROLE %I', g.grantor);
      EXECUTE format('REVOKE ALL ON SEQUENCE %s FROM authenticated', r.obj);
      RESET ROLE;
    END LOOP;
    IF EXISTS (SELECT 1 FROM pg_depend dp
                 JOIN pg_attrdef ad ON dp.classid = 'pg_attrdef'::regclass AND dp.objid = ad.oid
                 JOIN pg_class t ON t.oid = ad.adrelid
                 JOIN w4_decisao d ON d.relacao = t.relname AND d.i
                WHERE dp.refclassid = 'pg_class'::regclass AND dp.refobjid = r.oid
                  AND t.relnamespace = 'public'::regnamespace) THEN
      EXECUTE format('GRANT USAGE ON SEQUENCE %s TO authenticated', r.obj);
    END IF;
  END LOOP;

  FOR dec IN SELECT relacao FROM w4_decisao WHERE to_regclass('public.' || quote_ident(relacao)) IS NULL LOOP
    RAISE NOTICE 'v19_10: % está na decisão mas não existe neste banco — ignorada', dec.relacao;
  END LOOP;
  RAISE NOTICE 'v19_10: % relações e % sequências revistas para authenticated; RLS ligada em % tabelas', v_n_rel, v_n_seq, v_n_rls;
END
$aplica$;

-- -----------------------------------------------------------------------------
-- 2c. Funil: escopo na RLS e recálculo só da campanha afetada, por papel dedicado
-- -----------------------------------------------------------------------------
-- A tela "Configurar" da campanha (CampaignDetailDashboard.tsx:472 → FunnelUrlsEditor)
-- é aberta a OPERATOR e grava em campaign_funnel_urls (campaignFunnelUrlsService.ts
-- :46/:59/:85/:110). Os gatilhos AFTER dessa tabela recalculam receita em
-- daily_campaign_metrics. Revisão de 15/10 (ciclo 2): com o recálculo como dono e
-- a tabela aberta a qualquer logado, um operador ou uma conta sem papel zerava a
-- receita de campanha alheia, puxava receita de outro projeto e, vinculando-se em
-- user_campaigns, recebia comissão. Correção:
--   a) RLS de campaign_funnel_urls por escopo: escrever só ADMIN ou operador
--      vinculado à campanha (user_campaigns, ou user_projects do projeto da
--      campanha); a URL gravada tem de ser do domínio do projeto da campanha;
--   b) user_campaigns e user_projects: escrita só ADMIN (decisão acima);
--   c) os dois gatilhos recalculam só a(s) campanha(s) da linha (NEW e OLD), e
--      rodam como o papel dedicado volc_agregador_funil — NOLOGIN, não
--      superusuário, sem BYPASSRLS — com só o que o recálculo usa.
DO $guarda_papel$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'volc_agregador_funil') THEN
    RAISE EXCEPTION 'v19_10: o papel volc_agregador_funil já existe — não reaplica';
  END IF;
  IF to_regprocedure('public.volc_pode_editar_funil(text,text)') IS NOT NULL THEN
    RAISE EXCEPTION 'v19_10: public.volc_pode_editar_funil já existe — não reaplica';
  END IF;
END
$guarda_papel$;

-- a) quem pode escrever uma URL de funil
CREATE FUNCTION public.volc_pode_editar_funil(p_campaign text, p_url text)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $f$
  SELECT public.volc_current_admin()
      OR (
        EXISTS (
          SELECT 1 FROM public.users u
           WHERE lower(u.email) = lower((SELECT auth.jwt()) ->> 'email')
             AND u.role IN ('OPERATOR', 'ADMIN')
             AND (EXISTS (SELECT 1 FROM public.user_campaigns uc
                           WHERE uc.user_id = u.id AND uc.campaign_id = p_campaign)
                  OR EXISTS (SELECT 1 FROM public.user_projects up
                               JOIN public.campaigns c ON c.project_id = up.project_id
                              WHERE up.user_id = u.id AND c.campaign_id = p_campaign)))
        AND (p_url IS NULL OR EXISTS (
          SELECT 1 FROM public.campaigns c JOIN public.projects pr ON pr.id = c.project_id
           WHERE c.campaign_id = p_campaign
             AND split_part(regexp_replace(regexp_replace(lower(p_url), '^[a-z]+://', ''), '^www\.', ''), '/', 1)
                 = split_part(regexp_replace(regexp_replace(lower(coalesce(nullif(pr.domain, ''), pr.main_url)), '^[a-z]+://', ''), '^www\.', ''), '/', 1)))
      )
$f$;
COMMENT ON FUNCTION public.volc_pode_editar_funil(text, text) IS
  'v19_10 (W4): ADMIN, ou operador vinculado à campanha (user_campaigns ou user_projects '
  'do projeto), e — com p_url — URL do domínio do projeto da campanha. Usada pela RLS '
  'de campaign_funnel_urls. Removida pelo v19_10_rollback.sql.';
ALTER FUNCTION public.volc_pode_editar_funil(text, text) OWNER TO supabase_admin;
REVOKE ALL ON FUNCTION public.volc_pode_editar_funil(text, text) FROM PUBLIC, anon, service_role;
GRANT EXECUTE ON FUNCTION public.volc_pode_editar_funil(text, text) TO authenticated;
INSERT INTO app_auth.w4_auth_criados VALUES ('funcao', 'public.volc_pode_editar_funil(text,text)');

ALTER POLICY w4a_insert ON public.campaign_funnel_urls
  WITH CHECK (public.volc_pode_editar_funil(campaign_id::text, url::text));
ALTER POLICY w4a_update ON public.campaign_funnel_urls
  USING (public.volc_pode_editar_funil(campaign_id::text, NULL))
  WITH CHECK (public.volc_pode_editar_funil(campaign_id::text, url::text));

-- c) papel dedicado e recálculo só da campanha da linha
CREATE ROLE volc_agregador_funil NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEDB NOCREATEROLE;
COMMENT ON ROLE volc_agregador_funil IS 'v19_10 (W4): dono dos gatilhos de agregação do funil; só o que o recálculo de daily_campaign_metrics usa.';
INSERT INTO app_auth.w4_auth_criados VALUES ('papel', 'volc_agregador_funil');

DO $agregador$
DECLARE t text; f record; v_n int := 1; v_ant int := 0; v_pol text;
BEGIN
  -- leitura do que o recálculo e os gatilhos BEFORE de daily_campaign_metrics leem
  FOREACH t IN ARRAY ARRAY['campaign_funnel_urls', 'adsense_metrics', 'campaigns', 'projects', 'system_settings',
                           'exchange_rate_history', 'user_campaigns', 'users', 'tax_history'] LOOP
    IF to_regclass('public.' || t) IS NULL THEN CONTINUE; END IF;
    EXECUTE format('GRANT SELECT ON public.%I TO volc_agregador_funil', t);
    IF (SELECT relrowsecurity FROM pg_class WHERE oid = ('public.' || t)::regclass) THEN
      v_pol := 'w4a_agregador_select';
      EXECUTE format('CREATE POLICY %I ON public.%I AS PERMISSIVE FOR SELECT TO volc_agregador_funil USING (true)', v_pol, t);
      INSERT INTO app_auth.w4_auth_policy VALUES ('public', t, v_pol);
    END IF;
  END LOOP;
  -- escrita só em daily_campaign_metrics
  GRANT SELECT, INSERT, UPDATE ON public.daily_campaign_metrics TO volc_agregador_funil;
  CREATE POLICY w4a_agregador_select ON public.daily_campaign_metrics AS PERMISSIVE FOR SELECT TO volc_agregador_funil USING (true);
  CREATE POLICY w4a_agregador_insert ON public.daily_campaign_metrics AS PERMISSIVE FOR INSERT TO volc_agregador_funil WITH CHECK (true);
  CREATE POLICY w4a_agregador_update ON public.daily_campaign_metrics AS PERMISSIVE FOR UPDATE TO volc_agregador_funil USING (true) WITH CHECK (true);
  INSERT INTO app_auth.w4_auth_policy VALUES ('public', 'daily_campaign_metrics', 'w4a_agregador_select'),
    ('public', 'daily_campaign_metrics', 'w4a_agregador_insert'), ('public', 'daily_campaign_metrics', 'w4a_agregador_update');
  -- nextval das sequências que os defaults de daily_campaign_metrics usam
  FOR f IN SELECT DISTINCT dp.refobjid::regclass AS seq FROM pg_depend dp
             JOIN pg_attrdef ad ON dp.classid = 'pg_attrdef'::regclass AND dp.objid = ad.oid
            WHERE ad.adrelid = 'public.daily_campaign_metrics'::regclass AND dp.refclassid = 'pg_class'::regclass
              AND (SELECT relkind FROM pg_class WHERE oid = dp.refobjid) = 'S' LOOP
    EXECUTE format('GRANT USAGE ON SEQUENCE %s TO volc_agregador_funil', f.seq);
  END LOOP;
  -- EXECUTE nas funções de public que o recálculo e os gatilhos de daily_campaign_metrics
  -- chamam (fecho transitivo pelo nome no corpo), e só nelas
  CREATE TEMP TABLE w4_fn (oid oid PRIMARY KEY) ON COMMIT DROP;
  INSERT INTO w4_fn SELECT to_regprocedure('public.aggregate_adsense_funnel_revenue(text,date)')
    WHERE to_regprocedure('public.aggregate_adsense_funnel_revenue(text,date)') IS NOT NULL;
  INSERT INTO w4_fn SELECT DISTINCT tg.tgfoid FROM pg_trigger tg
   WHERE tg.tgrelid = 'public.daily_campaign_metrics'::regclass AND NOT tg.tgisinternal ON CONFLICT DO NOTHING;
  WHILE v_n <> v_ant LOOP
    v_ant := (SELECT count(*) FROM w4_fn);
    INSERT INTO w4_fn
    SELECT DISTINCT p2.oid FROM w4_fn w JOIN pg_proc p1 ON p1.oid = w.oid
      JOIN pg_proc p2 ON p2.pronamespace = 'public'::regnamespace
                     AND p1.prosrc ~* ('\m' || p2.proname || '\s*\(')
    ON CONFLICT DO NOTHING;
    v_n := (SELECT count(*) FROM w4_fn);
  END LOOP;
  FOR f IN SELECT w.oid::regprocedure AS fn FROM w4_fn w JOIN pg_proc p ON p.oid = w.oid WHERE p.prorettype <> 'trigger'::regtype LOOP
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO volc_agregador_funil', f.fn);
  END LOOP;
END
$agregador$;

DO $gatilhos$
DECLARE f text; p record;
BEGIN
  FOREACH f IN ARRAY ARRAY['public.trigger_calculate_adsense_campaign_revenue()',
                           'public.trigger_funnel_url_change()'] LOOP
    SELECT pr.oid, pg_get_userbyid(pr.proowner) AS dono INTO p FROM pg_proc pr WHERE pr.oid = to_regprocedure(f);
    IF p.oid IS NULL THEN RAISE EXCEPTION 'v19_10: função % não existe', f; END IF;
    IF p.dono <> 'supabase_admin' THEN RAISE EXCEPTION 'v19_10: % pertence a % (esperado supabase_admin)', f, p.dono; END IF;
    INSERT INTO app_auth.w4_auth_func (assinatura, dono_antes, def_antes)
    VALUES (f, p.dono, pg_get_functiondef(p.oid));
  END LOOP;
END
$gatilhos$;

-- Recalcula só as campanhas da linha (NEW e OLD), com a mesma conta de
-- calculate_adsense_campaign_revenue() restrita a elas.
CREATE OR REPLACE FUNCTION public.trigger_calculate_adsense_campaign_revenue()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $f$
DECLARE v_campanhas text[];
BEGIN
  v_campanhas := array_remove(ARRAY[
    CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN NEW.campaign_id::text END,
    CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN OLD.campaign_id::text END], NULL);
  WITH adsense_campaign_revenue AS (
    SELECT cfu.campaign_id, am.date, SUM(am.revenue_converted) AS total_revenue_converted
      FROM campaign_funnel_urls cfu
      JOIN adsense_metrics am ON cfu.url = am.url
     WHERE cfu."Active" = true AND cfu.campaign_id::text = ANY (v_campanhas)
     GROUP BY cfu.campaign_id, am.date
  )
  INSERT INTO daily_campaign_metrics (campaign_id, date, revenue_converted_revshare, spend, revenue, roas,
                                      clicks, impressions, conversions, cost_per_conversion, created_at, updated_at)
  SELECT acr.campaign_id, acr.date, acr.total_revenue_converted, 0, 0, 0, 0, 0, 0, 0, NOW(), NOW()
    FROM adsense_campaign_revenue acr
  ON CONFLICT (campaign_id, date) DO UPDATE SET
    revenue_converted_revshare = EXCLUDED.revenue_converted_revshare, updated_at = NOW();
  RETURN COALESCE(NEW, OLD);
END;
$f$;

CREATE OR REPLACE FUNCTION public.trigger_funnel_url_change()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $f$
BEGIN
  IF TG_OP IN ('INSERT', 'UPDATE') THEN
    PERFORM aggregate_adsense_funnel_revenue(NEW.campaign_id, CURRENT_DATE);
  END IF;
  IF TG_OP = 'DELETE' OR (TG_OP = 'UPDATE' AND OLD.campaign_id IS DISTINCT FROM NEW.campaign_id) THEN
    PERFORM aggregate_adsense_funnel_revenue(OLD.campaign_id, CURRENT_DATE);
  END IF;
  RETURN COALESCE(NEW, OLD);
END;
$f$;

ALTER FUNCTION public.trigger_calculate_adsense_campaign_revenue() OWNER TO volc_agregador_funil;
ALTER FUNCTION public.trigger_funnel_url_change() OWNER TO volc_agregador_funil;
UPDATE app_auth.w4_auth_func f SET dono_depois = pg_get_userbyid(p.proowner), def_depois_md5 = md5(pg_get_functiondef(p.oid))
  FROM pg_proc p WHERE p.oid = to_regprocedure(f.assinatura);

-- -----------------------------------------------------------------------------
-- 2d. Default ACL: o mínimo vale também para tabela e sequência NOVAS em public
-- -----------------------------------------------------------------------------
-- Para os dois papéis que criam objetos em public (postgres e supabase_admin),
-- anon e authenticated deixam de receber qualquer privilégio em tabela/view e
-- sequência novas: toda migration futura declara o seu GRANT. Funções novas NÃO
-- mudam neste ciclo (lacuna declarada no cabeçalho).
INSERT INTO app_auth.w4_auth_defacl (papel, objtipo, acl_antes)
SELECT r.papel, t.objtipo,
       (SELECT d.defaclacl FROM pg_default_acl d
         WHERE d.defaclrole = r.papel::regrole AND d.defaclnamespace = 'public'::regnamespace AND d.defaclobjtype = t.objtipo)
  FROM (VALUES ('postgres'), ('supabase_admin')) r(papel), (VALUES ('r'::"char"), ('S'::"char")) t(objtipo);
ALTER DEFAULT PRIVILEGES FOR ROLE postgres, supabase_admin IN SCHEMA public
  REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres, supabase_admin IN SCHEMA public
  REVOKE ALL ON SEQUENCES FROM anon, authenticated;
UPDATE app_auth.w4_auth_defacl a SET acl_depois =
       (SELECT d.defaclacl FROM pg_default_acl d
         WHERE d.defaclrole = a.papel::regrole AND d.defaclnamespace = 'public'::regnamespace AND d.defaclobjtype = a.objtipo);

-- Prova por construção: tabela e sequência novas de cada dono, sem nada para
-- anon/authenticated; criadas e descartadas nesta transação.
DO $novo$
DECLARE v_dono text; v_falha text := '';
BEGIN
  FOREACH v_dono IN ARRAY ARRAY['postgres', 'supabase_admin'] LOOP
    EXECUTE format('SET LOCAL ROLE %I', v_dono);
    CREATE TABLE public.w4_sonda_v19_10 (i int);
    CREATE SEQUENCE public.w4_sonda_v19_10_seq;
    RESET ROLE;
    IF has_table_privilege('authenticated', 'public.w4_sonda_v19_10', 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
       OR has_table_privilege('anon', 'public.w4_sonda_v19_10', 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') THEN
      v_falha := v_falha || format(' tabela-de-%s', v_dono);
    END IF;
    IF has_sequence_privilege('authenticated', 'public.w4_sonda_v19_10_seq', 'USAGE,SELECT,UPDATE')
       OR has_sequence_privilege('anon', 'public.w4_sonda_v19_10_seq', 'USAGE,SELECT,UPDATE') THEN
      v_falha := v_falha || format(' sequencia-de-%s', v_dono);
    END IF;
    IF NOT has_table_privilege('service_role', 'public.w4_sonda_v19_10', 'SELECT,INSERT,UPDATE,DELETE') THEN
      v_falha := v_falha || format(' service_role-perdeu-%s', v_dono);
    END IF;
    DROP SEQUENCE public.w4_sonda_v19_10_seq;
    DROP TABLE public.w4_sonda_v19_10;
  END LOOP;
  IF v_falha <> '' THEN RAISE EXCEPTION 'v19_10 falhou: objeto novo ainda nasce aberto →%', v_falha; END IF;
END
$novo$;

-- -----------------------------------------------------------------------------
-- 4. Fotografia do depois e postflight
-- -----------------------------------------------------------------------------
UPDATE app_auth.w4_auth_acl s SET acl_depois = c.relacl, rls_depois = c.relrowsecurity,
                                  pol_depois = app_auth.w4_policies_md5(c.oid)
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE s.coluna IS NULL AND n.nspname = s.esquema AND c.relname = s.relacao;
UPDATE app_auth.w4_auth_acl s SET acl_depois = a.attacl
  FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE s.coluna IS NOT NULL AND n.nspname = s.esquema AND c.relname = s.relacao AND a.attname = s.coluna;
DELETE FROM app_auth.w4_auth_acl
 WHERE acl_antes IS NOT DISTINCT FROM acl_depois AND rls_antes IS NOT DISTINCT FROM rls_depois
   AND pol_antes IS NOT DISTINCT FROM pol_depois;

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
                                              WHEN 'UPDATE' THEN d.u AND d.upd_cols IS NULL ELSE d.d END, false)
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

  -- toda escrita concedida numa tabela com RLS tem policy que se aplica a authenticated
  SELECT string_agg(format('%s(%s)', c.relname, p.cmd), ', ') INTO v_err
    FROM pg_class c
    CROSS JOIN (VALUES ('SELECT','r'),('INSERT','a'),('UPDATE','w'),('DELETE','d')) p(cmd, letra)
   WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r','p') AND c.relrowsecurity
     AND c.relname <> 'users'
     AND (has_table_privilege('authenticated', c.oid, p.cmd)
          OR (p.cmd = 'UPDATE' AND has_any_column_privilege('authenticated', c.oid, 'UPDATE')))
     AND NOT EXISTS (SELECT 1 FROM pg_policy pl
                      WHERE pl.polrelid = c.oid AND (pl.polcmd = p.letra OR pl.polcmd = '*')
                        AND (0 = ANY (pl.polroles) OR 'authenticated'::regrole = ANY (pl.polroles)));
  IF v_err IS NOT NULL THEN
    RAISE EXCEPTION 'v19_10 falhou: comando concedido sem policy para authenticated: %', v_err;
  END IF;

  -- sequências: nenhum UPDATE/SELECT; USAGE só onde há INSERT decidido
  SELECT string_agg(c.relname, ', ') INTO v_err
    FROM pg_class c
   WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'S'
     AND CASE WHEN c.relkind = 'S' THEN has_sequence_privilege('authenticated', c.oid, 'UPDATE,SELECT') END;
  IF v_err IS NOT NULL THEN
    RAISE EXCEPTION 'v19_10 falhou: authenticated ainda pode setval/currval em: %', v_err;
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
