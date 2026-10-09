-- v17_04 — views de arbitragem só mostram lucro com receita reconciliada
--
-- Autoridade: database.agenciavolc.com.br. Pré-requisito: v17_01.
-- Substitui as três views de arbitragem da v17_01. Só lê; não altera tabela.
--
-- ## DEFEITOS DEMONSTRADOS NA v17_01 (09/10/2026)
--
-- 1. SOMA SEM PROVA DE QUE AS RECEITAS SÃO DISTINTAS. A v17_01 somava GAM e
--    JoinAds da mesma campanha-dia. O JoinAds pode monetizar via GAM; somar as
--    duas sem atribuição contaria a mesma impressão duas vezes. Hoje
--    `gam_metrics` tem 0 linhas e o defeito está latente — mas a view somaria
--    no primeiro dia em que o GAM voltasse.
-- 2. GAM CASADO POR IGUALDADE CRUA. `gam_metrics.utm_campaign_value` pode ser
--    campanha Google OU adset Meta. O roteador oficial
--    (`vw_gam_attribution_route`, 20260910143000) já classifica; a v17_01 o
--    ignorava. Agora só a rota `GOOGLE_CAMPAIGN` entra como receita.
-- 3. LUCRO DE JANELA ABERTA. D0 é leitura intradia de custo e o JoinAds
--    intraday reescreve o dia; um lucro de D0 não serve para otimizar.
-- 4. RECEITA POR PLACEMENT INVENTADA. O placement de COMPRA (Google Ads: o site
--    de terceiro onde o anúncio rodou) e a receita GAM por placement só se
--    casam se a receita for atribuída ao placement de origem do visitante
--    (UTM). No WEBGO havia essa ingestão; no VOLC `display_gam_placements` está
--    vazia e não há ingestão versionada provando a atribuição.
-- 5. RECEITA HORÁRIA SEM MOEDA. `hourly_stats.revenue` não declara moeda (não
--    há coluna convertida) e a tabela está vazia; pô-la ao lado do custo em
--    BRL convidava a uma conta errada.
--
-- ## REGRA
--
-- Sem atribuição comprovada a view mostra "receita não reconciliada" e NÃO
-- mostra lucro, ROAS nem receita por clique. Os componentes de receita seguem
-- visíveis para quem for reconciliar à mão.

BEGIN;

DO $$
BEGIN
  IF to_regclass('public.vw_gads_campanha_dia') IS NULL
     OR to_regclass('public.vw_gam_attribution_route') IS NULL THEN
    RAISE EXCEPTION 'v17_04 recusada: exige v17_01 e o roteador vw_gam_attribution_route';
  END IF;
END $$;

DROP VIEW IF EXISTS public.vw_gads_arbitragem_campanha_dia;
DROP VIEW IF EXISTS public.vw_gads_arbitragem_placement_dia;
DROP VIEW IF EXISTS public.vw_gads_arbitragem_hora;

-- ───────────────────────────────────────────────── campanha × dia ──
CREATE VIEW public.vw_gads_arbitragem_campanha_dia WITH (security_invoker = true) AS
WITH gam AS (
  -- Só o que o roteador atribui a campanha Google. O resto fica contado à
  -- parte: existir GAM não atribuído para a chave já impede reconciliar.
  SELECT date, utm_campaign_value,
         sum(revenue_converted) FILTER (WHERE attribution_route = 'GOOGLE_CAMPAIGN') AS receita_brl,
         count(*) FILTER (WHERE attribution_route <> 'GOOGLE_CAMPAIGN')              AS linhas_nao_atribuidas,
         min(project_id)                                                             AS project_id,
         count(DISTINCT project_id)                                                  AS projetos
    FROM public.vw_gam_attribution_route
   GROUP BY date, utm_campaign_value
), gam_atualizacao AS (
  SELECT date, utm_campaign_value, max(updated_at) AS atualizada_em
    FROM public.gam_metrics GROUP BY date, utm_campaign_value
), jads AS (
  SELECT date, utm_campaign_value, sum(revenue_converted) AS receita_brl,
         max(updated_at) AS atualizada_em, min(project_id) AS project_id,
         count(DISTINCT project_id) AS projetos
    FROM public.joinads_metrics GROUP BY date, utm_campaign_value
), vinc AS (
  SELECT DISTINCT ON (volc_campaign_id) volc_campaign_id, project_id, opportunity_id, funnel_run_id
    FROM public.trafego_vinculo WHERE desfeito_em IS NULL
   ORDER BY volc_campaign_id, confirmado_em DESC
), base AS (
  SELECT c.*, v.project_id AS project_id_vinculo, v.opportunity_id, v.funnel_run_id,
         g.colhida_em AS custo_colhido_em,
         gam.receita_brl AS receita_gam_brl, coalesce(gam.linhas_nao_atribuidas, 0) AS gam_linhas_nao_atribuidas,
         ga.atualizada_em AS gam_atualizada_em,
         jads.receita_brl AS receita_joinads_brl, jads.atualizada_em AS joinads_atualizada_em,
         coalesce(jads.project_id, gam.project_id) AS project_id_receita,
         coalesce(jads.projetos, 0) + coalesce(gam.projetos, 0) AS projetos_receita
    FROM public.vw_gads_campanha_dia c
    JOIN public.google_ads_campanha_dia g
      ON g.customer_id = c.customer_id AND g.campaign_id = c.campaign_id
     AND g.metric_date = c.metric_date AND g.segmentos = '{}'::jsonb
    LEFT JOIN gam  ON gam.date = c.metric_date AND gam.utm_campaign_value = c.campaign_id
    LEFT JOIN gam_atualizacao ga ON ga.date = c.metric_date AND ga.utm_campaign_value = c.campaign_id
    LEFT JOIN jads ON jads.date = c.metric_date AND jads.utm_campaign_value = c.campaign_id
    LEFT JOIN vinc v ON v.volc_campaign_id = c.volc_campaign_id
), julgada AS (
  SELECT b.*,
    CASE
      WHEN b.receita_gam_brl IS NULL AND b.receita_joinads_brl IS NULL AND b.gam_linhas_nao_atribuidas = 0
        THEN 'sem_receita_registrada'
      WHEN b.gam_linhas_nao_atribuidas > 0
        THEN 'nao_reconciliada_atribuicao'
      WHEN b.receita_gam_brl IS NOT NULL AND b.receita_joinads_brl IS NOT NULL
        THEN 'nao_reconciliada_sobreposicao'
      WHEN b.projetos_receita > 1
        OR (b.project_id_vinculo IS NOT NULL AND b.project_id_receita IS NOT NULL
            AND b.project_id_vinculo <> b.project_id_receita)
        THEN 'nao_reconciliada_projeto'
      WHEN b.currency_code <> 'BRL'
        THEN 'nao_reconciliada_moeda'
      WHEN NOT b.janela_fechada
        THEN 'janela_aberta'
      ELSE 'reconciliada_fonte_unica'
    END AS receita_status
    FROM base b
)
SELECT
  customer_id, campaign_id, metric_date, campaign_name, advertising_channel_type, currency_code,
  coalesce(project_id_vinculo, project_id_receita) AS project_id,
  project_id_vinculo, project_id_receita, opportunity_id, funnel_run_id,
  origem_janela, janela_fechada, custo_colhido_em,
  impressoes, cliques, cliques_invalidos, conversoes,
  round(custo_micros / 1e6, 2) AS custo,
  CASE WHEN cliques > 0 THEN round(custo_micros / 1e6 / cliques, 4) END AS cpc,
  receita_gam_brl, receita_joinads_brl, gam_linhas_nao_atribuidas,
  greatest(gam_atualizada_em, joinads_atualizada_em) AS receita_atualizada_em,
  receita_status,
  CASE WHEN receita_status LIKE 'nao_reconciliada%' THEN 'receita não reconciliada'
       WHEN receita_status = 'janela_aberta' THEN 'janela aberta (parcial)'
       WHEN receita_status = 'sem_receita_registrada' THEN 'sem receita registrada'
       ELSE 'reconciliada (fonte única)' END AS receita_rotulo,
  -- Receita do dia: só quando há UMA fonte atribuída (reconciliada ou parcial).
  CASE WHEN receita_status IN ('reconciliada_fonte_unica', 'janela_aberta')
       THEN coalesce(receita_gam_brl, receita_joinads_brl) END AS receita_brl,
  -- Lucro, ROAS e receita por clique: só reconciliada e de janela fechada.
  CASE WHEN receita_status = 'reconciliada_fonte_unica'
       THEN coalesce(receita_gam_brl, receita_joinads_brl) - custo_micros / 1e6 END AS lucro_brl,
  CASE WHEN receita_status = 'reconciliada_fonte_unica' AND custo_micros > 0
       THEN round(coalesce(receita_gam_brl, receita_joinads_brl) / (custo_micros / 1e6), 4) END AS roas,
  CASE WHEN receita_status = 'reconciliada_fonte_unica' AND cliques > 0
       THEN round(coalesce(receita_gam_brl, receita_joinads_brl) / cliques, 4) END AS receita_por_clique,
  receita_status = 'reconciliada_fonte_unica' AS utilizavel_para_otimizacao
FROM julgada;

-- ───────────────────────────────────────────────── placement × dia ──
-- Custo de compra por domínio. Receita por placement fica NULL: no VOLC não há
-- ingestão que atribua receita ao placement de origem do visitante.
CREATE VIEW public.vw_gads_arbitragem_placement_dia WITH (security_invoker = true) AS
SELECT customer_id, campaign_id, metric_date, volc_dominio(placement) AS dominio,
       max(placement_tipo) AS placement_tipo, max(currency_code) AS currency_code,
       bool_and(janela_fechada) AS janela_fechada, max(colhida_em) AS custo_colhido_em,
       sum(impressoes) AS impressoes, sum(cliques) AS cliques, sum(conversoes) AS conversoes,
       round(sum(custo_micros) / 1e6, 2) AS custo,
       NULL::numeric AS receita_brl,
       'nao_reconciliada_atribuicao'::text AS receita_status,
       'receita não reconciliada: não há ingestão que atribua receita ao placement de compra'::text AS receita_rotulo,
       false AS utilizavel_para_otimizacao
  FROM public.google_ads_fato_granular_placement
 WHERE placement_view = 'detail'
 GROUP BY customer_id, campaign_id, metric_date, volc_dominio(placement);

-- ───────────────────────────────────────────────── campanha × hora ──
-- Custo por hora no fuso da conta, convertido para instante. Receita horária
-- fica NULL: `hourly_stats` não declara moeda nem atribuição.
CREATE VIEW public.vw_gads_arbitragem_hora WITH (security_invoker = true) AS
SELECT customer_id, campaign_id, metric_date, hora, fuso,
       ((metric_date + make_interval(hours => hora)) AT TIME ZONE fuso) AS inicio_da_hora,
       max(currency_code) AS currency_code, bool_and(janela_fechada) AS janela_fechada,
       max(colhida_em) AS custo_colhido_em,
       sum(impressoes) AS impressoes, sum(cliques) AS cliques, sum(conversoes) AS conversoes,
       round(sum(custo_micros) / 1e6, 2) AS custo,
       NULL::numeric AS receita_brl,
       'nao_reconciliada_moeda'::text AS receita_status,
       'receita não reconciliada: hourly_stats não declara moeda nem atribuição'::text AS receita_rotulo,
       false AS utilizavel_para_otimizacao
  FROM public.google_ads_fato_granular_hora_dispositivo
 GROUP BY customer_id, campaign_id, metric_date, hora, fuso;

COMMENT ON VIEW public.vw_gads_arbitragem_campanha_dia IS
  'Custo Google × receita por campanha-dia. Lucro/ROAS só com receita_status = reconciliada_fonte_unica (uma fonte atribuída, projeto coerente, BRL, janela fechada); senão "receita não reconciliada".';
COMMENT ON VIEW public.vw_gads_arbitragem_placement_dia IS
  'Custo de compra por domínio de placement. Sem receita: não há atribuição comprovada de receita ao placement de compra.';
COMMENT ON VIEW public.vw_gads_arbitragem_hora IS
  'Custo por campanha-hora (fuso da conta → instante). Sem receita: hourly_stats não declara moeda nem atribuição.';

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['vw_gads_arbitragem_campanha_dia','vw_gads_arbitragem_placement_dia','vw_gads_arbitragem_hora'] LOOP
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC, anon, authenticated', t);
    EXECUTE format('GRANT SELECT ON public.%I TO service_role', t);
  END LOOP;
END $$;

NOTIFY pgrst, 'reload schema';
COMMIT;
