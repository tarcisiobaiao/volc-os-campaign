-- =============================================================================
-- 20260908120000_meta_financeiro_conjunto_dia.sql
--
-- ⚠️ MIGRATION CANDIDATA. NAO APLICADA OFICIALMENTE NESTA MISSAO.
--    Provada em cluster PostgreSQL 16 descartavel: apply -> uso -> replay ->
--    concorrencia -> rollback -> reapply. Nenhuma escrita no Supabase oficial.
--
-- DEPENDE DE (nesta ordem):
--   v13_01_cofre_de_ativos.sql
--   v15_01_meta_ads_read_model.sql
--   v15_02_meta_ads_insights.sql
--   20260907210000_meta_read_model_consistency.sql
--
-- =============================================================================
-- POR QUE ESTA MIGRATION EXISTE, E POR QUE ELA E SO DUAS VIEWS
-- =============================================================================
--
-- A decisao vinculante de 08/09/2026 fixou o grao financeiro canonico da Meta em
-- CONJUNTO/DIA:
--
--     account_ref + campaign_id + adset_id + date + metric_scope + metric_version
--
-- A pergunta obrigatoria antes de escrever qualquer DDL era: alguma migration
-- ATUAL ja acomoda esse delta? A resposta, conferida tabela por tabela:
--
--   * `trafego_meta_insight_daily` (v15_02:29) ja aceita `nivel = 'adset'`
--     (v15_02:54) e ja guarda `objeto_externo`, `periodo_inicio`, `spend`,
--     `impressions`, `clicks`, `reach`, `currency` (20260907210000:235),
--     `account_timezone` (:234), `completo` (:236) e `observado_em`. O FATO do
--     gasto por conjunto/dia CABE, inteiro, na tabela que ja existe.
--   * `trafego_meta_adset` (v15_01:140) ja carrega `meta_campaign_id`, e
--     `trafego_meta_campaign` (v15_01:117) ja carrega `external_id`. O elo
--     conjunto -> campanha JA E PERSISTIDO.
--
-- Ou seja: nao falta tabela, nao falta coluna e nao falta constraint. O que
-- faltava era o JOIN — o fato guarda `nivel + objeto_externo`, e ninguem
-- resolvia esse par para `campaign_id + adset_id`. Uma cadeia "v16" nova com
-- tabela propria duplicaria o gasto em dois lugares e criaria a pergunta
-- "qual das duas esta certa?", que e exatamente o defeito que o grao veio
-- consertar. Por isso o delta e VIEW, e nao tabela.
--
-- =============================================================================
-- POR QUE A RECEITA ENTRA EM VIEW SEPARADA E CONDICIONAL
-- =============================================================================
--
-- `public.gam_metrics` NAO TEM DDL NESTE REPOSITORIO. Nenhum CREATE TABLE,
-- nenhuma migration: e tabela legada, consumida por PostgREST, cujo schema este
-- repositorio nao controla nem prova. Amarrar a view do NUCLEO Meta a ela
-- tornaria o nucleo indeployavel em qualquer instalacao que nao tenha a tabela
-- legada — inclusive a instalacao portavel que o pacote Webgo preve.
--
-- Entao sao duas views, e a separacao e a decisao:
--
--   1. `vw_trafego_meta_financeiro_conjunto_dia` — SEMPRE criada. So Meta.
--      E o grao. Nao conhece receita.
--   2. `vw_trafego_meta_financeiro_conjunto_dia_gam` — criada SO SE
--      `public.gam_metrics` existir. E o resolvedor de receita, plugado por
--      fora, do jeito que o contrato de portabilidade pede.
--
-- Quando (2) nao nasce, (1) continua servindo gasto — e a ausencia de receita
-- fica sendo ausencia declarada, nunca zero.
--
-- =============================================================================
-- O QUE ESTAS VIEWS DELIBERADAMENTE NAO FAZEM
-- =============================================================================
--
-- Elas NAO somam campanha a partir de leitura campaign-level. O rollup de
-- campanha (`vw_trafego_meta_financeiro_campanha_dia`) le EXCLUSIVAMENTE as
-- linhas de conjunto. Somar `nivel='campaign'` junto contaria a mesma despesa
-- duas vezes: as duas leituras medem o mesmo dinheiro por caminhos diferentes.
-- O `WHERE i.nivel = 'adset'` da view de grao e essa trava, em SQL.
--
-- Elas NAO somam `reach`: alcance e gente, e a mesma pessoa aparece em dois
-- dias. Ele viaja no grao em que foi medido e some no rollup — `NULL`, nunca
-- uma soma que mentiria.
--
-- Elas NAO inventam cambio. `revenue_converted` e o valor que a fonte ja
-- converteu; a taxa implicita e exposta para AUDITAR essa conversao, jamais
-- para fazer uma que a fonte nao fez.
-- =============================================================================
\set ON_ERROR_STOP on

BEGIN;

DO $guarda$
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'meta_financeiro_conjunto_dia deve rodar como postgres ou supabase_admin; atual: %', current_user;
  END IF;
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'exige PostgreSQL 15+ para security_invoker em VIEW (encontrado: %)',
      current_setting('server_version');
  END IF;
  IF to_regclass('public.vw_trafego_meta_insight_latest') IS NULL THEN
    RAISE EXCEPTION 'depende de public.vw_trafego_meta_insight_latest (20260907210000)';
  END IF;
  IF to_regclass('public.trafego_meta_adset') IS NULL
     OR to_regclass('public.trafego_meta_campaign') IS NULL THEN
    RAISE EXCEPTION 'depende do read model de campanha/conjunto (v15_01)';
  END IF;
END
$guarda$;


-- -----------------------------------------------------------------------------
-- 1. O GRAO: uma linha por conjunto/dia, com a campanha JA RESOLVIDA
-- -----------------------------------------------------------------------------
-- `security_invoker = true` de proposito: sem ele a view leria com os
-- privilegios do DONO e viraria porta lateral para qualquer papel que ganhasse
-- SELECT nela por acidente. Com ele, quem le a view precisa poder ler as
-- tabelas base — e `anon`/`authenticated` nao podem.
DROP VIEW IF EXISTS public.vw_trafego_meta_financeiro_campanha_dia;
DROP VIEW IF EXISTS public.vw_trafego_meta_financeiro_conjunto_dia_gam;
DROP VIEW IF EXISTS public.vw_trafego_meta_financeiro_conjunto_dia;

CREATE VIEW public.vw_trafego_meta_financeiro_conjunto_dia
WITH (security_invoker = true) AS
SELECT
  i.ad_account_ativo_id,
  i.conta_externa                          AS account_external_id,
  c.external_id                            AS campaign_id,
  i.objeto_externo                         AS adset_id,
  s.meta_campaign_id,
  s.meta_adset_id,
  i.periodo_inicio                         AS date,
  'adset'::text                            AS metric_scope,
  'meta-atribuicao-adset-v1'::text         AS metric_version,
  i.currency,
  i.account_timezone                       AS timezone,
  i.spend,
  i.impressions,
  i.clicks,
  -- ⚠️ NAO SOMAVEL entre linhas. Viaja no grao, morre no rollup.
  i.reach,
  i.completo,
  i.observado_em                           AS source_freshness,
  'META_ADS'::text                         AS source
FROM public.vw_trafego_meta_insight_latest i
JOIN public.trafego_meta_adset s
  ON s.external_id = i.objeto_externo
JOIN public.trafego_meta_campaign c
  ON c.meta_campaign_id = s.meta_campaign_id
 AND c.ad_account_ativo_id = i.ad_account_ativo_id
WHERE i.nivel = 'adset'
  AND i.provider = 'META_ADS'
  AND i.breakdown = 'none'
  AND i.time_increment = '1'
  AND i.action_report_time = 'impression'
  AND i.janela_atribuicao = 'default'
  -- Um insight diario tem inicio = fim. Uma linha agregada de varios dias nao
  -- e grao diario e nao pode entrar num total por dia.
  AND i.periodo_fim = i.periodo_inicio;

COMMENT ON VIEW public.vw_trafego_meta_financeiro_conjunto_dia IS
  'Grao financeiro canonico da Meta: conjunto/dia, com campaign_id resolvido pelo read model (trafego_meta_adset.meta_campaign_id). SO nivel=adset — somar a leitura campaign-level a estas linhas contaria a mesma despesa duas vezes. reach NAO e somavel.';

REVOKE ALL ON public.vw_trafego_meta_financeiro_conjunto_dia FROM PUBLIC;
REVOKE ALL ON public.vw_trafego_meta_financeiro_conjunto_dia FROM anon;
REVOKE ALL ON public.vw_trafego_meta_financeiro_conjunto_dia FROM authenticated;
REVOKE ALL ON public.vw_trafego_meta_financeiro_conjunto_dia FROM service_role;
GRANT SELECT ON public.vw_trafego_meta_financeiro_conjunto_dia TO service_role;


-- -----------------------------------------------------------------------------
-- 2. O ROLLUP: campanha/dia = SOMA dos conjuntos filhos daquele dia
-- -----------------------------------------------------------------------------
-- Ela le a view de grao, e SO ela. Nao existe caminho aqui que alcance
-- `nivel='campaign'`.
--
-- As razoes viajam junto do total, e nao como enfeite: um numero sozinho nao
-- diz se e completo. `conjuntos_no_dia` e `linhas_incompletas` sao a diferenca
-- entre "R$ 0,00 de gasto" e "gasto desconhecido em 2 dos 7 conjuntos".
CREATE VIEW public.vw_trafego_meta_financeiro_campanha_dia
WITH (security_invoker = true) AS
SELECT
  g.ad_account_ativo_id,
  g.account_external_id,
  g.campaign_id,
  g.date,
  'campaign_rollup_de_adset'::text AS metric_scope,
  'meta-atribuicao-adset-v1'::text AS metric_version,
  min(g.currency)                  AS currency,
  min(g.timezone)                  AS timezone,
  count(*)                         AS conjuntos_no_dia,
  count(*) FILTER (WHERE NOT g.completo) AS linhas_incompletas,
  -- Uma parcela desconhecida torna o total desconhecido. `sum()` do Postgres
  -- IGNORA NULL, o que produziria um total que PARECE completo e nao e — por
  -- isso o total so existe quando nenhuma parcela e nula.
  CASE WHEN count(*) FILTER (WHERE g.spend IS NULL) = 0
       THEN sum(g.spend) END       AS spend,
  CASE WHEN count(*) FILTER (WHERE g.impressions IS NULL) = 0
       THEN sum(g.impressions) END AS impressions,
  CASE WHEN count(*) FILTER (WHERE g.clicks IS NULL) = 0
       THEN sum(g.clicks) END      AS clicks,
  -- Alcance nao soma. NULL explicito, e o comentario da view diz por que.
  NULL::bigint                     AS reach,
  bool_and(g.completo)             AS completo,
  min(g.source_freshness)          AS source_freshness,
  'META_ADS'::text                 AS source
FROM public.vw_trafego_meta_financeiro_conjunto_dia g
GROUP BY g.ad_account_ativo_id, g.account_external_id, g.campaign_id, g.date;

COMMENT ON VIEW public.vw_trafego_meta_financeiro_campanha_dia IS
  'Campanha/dia = SOMA dos conjuntos filhos daquele dia, e nada mais. Le apenas vw_trafego_meta_financeiro_conjunto_dia; nao alcanca nivel=campaign. Uma parcela NULL torna o total NULL — sum() ignoraria o NULL e devolveria um total que parece completo. reach e NULL de proposito: alcance nao soma.';

REVOKE ALL ON public.vw_trafego_meta_financeiro_campanha_dia FROM PUBLIC;
REVOKE ALL ON public.vw_trafego_meta_financeiro_campanha_dia FROM anon;
REVOKE ALL ON public.vw_trafego_meta_financeiro_campanha_dia FROM authenticated;
REVOKE ALL ON public.vw_trafego_meta_financeiro_campanha_dia FROM service_role;
GRANT SELECT ON public.vw_trafego_meta_financeiro_campanha_dia TO service_role;


-- -----------------------------------------------------------------------------
-- 3. O RESOLVEDOR DE RECEITA — condicional, porque a tabela e legada
-- -----------------------------------------------------------------------------
DO $receita$
BEGIN
  IF to_regclass('public.gam_metrics') IS NULL THEN
    RAISE NOTICE 'meta_financeiro: public.gam_metrics ausente — a view de receita NAO foi criada. O gasto continua disponivel; a receita fica explicitamente ausente, nunca zero.';
    RETURN;
  END IF;

  EXECUTE $sql$
    CREATE VIEW public.vw_trafego_meta_financeiro_conjunto_dia_gam
    WITH (security_invoker = true) AS
    SELECT
      g.*,
      m.gam_accounts_id,
      m.revenue                AS gam_revenue_original,
      m.revenue_converted      AS gam_revenue_brl,
      m.updated_at             AS revenue_freshness,
      CASE
        WHEN m.utm_campaign_value IS NOT NULL THEN 'FATURAMENTO_ATRIBUIDO_VIA_ADSET'
        ELSE 'SEM_UTM_ADSET_NO_GAM'
      END                      AS mapping_status,
      CASE
        WHEN m.utm_campaign_value IS NOT NULL THEN 'GAM.utm_campaign_value = adset_id'
      END                      AS attribution_method,
      -- Cambio DERIVADO da propria linha, para AUDITAR a conversao que a fonte
      -- ja fez. Nunca para fazer uma conversao que a fonte nao fez.
      CASE WHEN m.revenue IS NOT NULL AND m.revenue <> 0 AND m.revenue_converted IS NOT NULL
           THEN m.revenue_converted / m.revenue END AS fx_rate
    FROM public.vw_trafego_meta_financeiro_conjunto_dia g
    -- LEFT JOIN de proposito: um conjunto/dia sem linha no GAM continua
    -- existindo com o gasto dele. Um INNER JOIN faria o conjunto SUMIR, e o
    -- total do gasto encolheria em silencio.
    LEFT JOIN public.gam_metrics m
      ON m.utm_campaign_value = g.adset_id
     AND m.date = g.date
  $sql$;

  EXECUTE 'COMMENT ON VIEW public.vw_trafego_meta_financeiro_conjunto_dia_gam IS '
    || quote_literal('Grao conjunto/dia com a receita do GAM plugada por utm_campaign_value = adset_id. LEFT JOIN: conjunto sem linha no GAM mantem o gasto e recebe mapping_status SEM_UTM_ADSET_NO_GAM com receita NULL — associacao desconhecida NUNCA e receita zero. O escopo por conta GAM e por vinculo de projeto e responsabilidade de quem consulta.');

  EXECUTE 'REVOKE ALL ON public.vw_trafego_meta_financeiro_conjunto_dia_gam FROM PUBLIC';
  EXECUTE 'REVOKE ALL ON public.vw_trafego_meta_financeiro_conjunto_dia_gam FROM anon';
  EXECUTE 'REVOKE ALL ON public.vw_trafego_meta_financeiro_conjunto_dia_gam FROM authenticated';
  EXECUTE 'REVOKE ALL ON public.vw_trafego_meta_financeiro_conjunto_dia_gam FROM service_role';
  EXECUTE 'GRANT SELECT ON public.vw_trafego_meta_financeiro_conjunto_dia_gam TO service_role';
  RAISE NOTICE 'meta_financeiro: view de receita criada sobre public.gam_metrics';
END
$receita$;


-- -----------------------------------------------------------------------------
-- 4. CONFERENCIA DA PROPRIA MIGRATION
-- -----------------------------------------------------------------------------
DO $confere$
DECLARE
  v_invoker text;
  v_grants  int;
BEGIN
  FOR v_invoker IN
    SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind = 'v'
       AND c.relname LIKE 'vw_trafego_meta_financeiro%'
  LOOP
    IF NOT EXISTS (
      SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE n.nspname = 'public' AND c.relname = v_invoker
         AND c.reloptions @> ARRAY['security_invoker=true']
    ) THEN
      RAISE EXCEPTION 'view % nasceu sem security_invoker', v_invoker;
    END IF;
  END LOOP;

  SELECT count(*) INTO v_grants
    FROM information_schema.role_table_grants
   WHERE table_schema = 'public'
     AND table_name LIKE 'vw_trafego_meta_financeiro%'
     AND grantee IN ('anon', 'authenticated', 'PUBLIC');
  IF v_grants > 0 THEN
    RAISE EXCEPTION 'as views financeiras nao podem conceder nada a anon/authenticated/PUBLIC (encontrado: %)', v_grants;
  END IF;

  RAISE NOTICE 'meta_financeiro OK: views com security_invoker, zero grants a anon/authenticated';
END
$confere$;

COMMIT;
