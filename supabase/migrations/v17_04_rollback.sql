-- Rollback da v17_04: devolve as três views de arbitragem como a v17_01 as criou.
-- As definições abaixo são cópia literal da v17_01 (gerada pelo script de fechamento,
-- não reescrita à mão).
BEGIN;
DROP VIEW IF EXISTS public.vw_gads_arbitragem_campanha_dia;
DROP VIEW IF EXISTS public.vw_gads_arbitragem_placement_dia;
DROP VIEW IF EXISTS public.vw_gads_arbitragem_hora;

CREATE VIEW public.vw_gads_arbitragem_campanha_dia WITH (security_invoker = true) AS
WITH gam AS (
  SELECT date, utm_campaign_value, sum(revenue_converted) AS receita_brl,
         sum(gam_impressions) AS impressoes_gam
    FROM public.gam_metrics GROUP BY date, utm_campaign_value
), jads AS (
  SELECT date, utm_campaign_value, sum(revenue_converted) AS receita_brl,
         sum(impressions) AS impressoes_joinads
    FROM public.joinads_metrics GROUP BY date, utm_campaign_value
), vinc AS (
  SELECT DISTINCT ON (volc_campaign_id) volc_campaign_id, project_id, opportunity_id, funnel_run_id
    FROM public.trafego_vinculo WHERE desfeito_em IS NULL
   ORDER BY volc_campaign_id, confirmado_em DESC
)
SELECT c.customer_id, c.campaign_id, c.metric_date, c.campaign_name, c.advertising_channel_type,
       c.currency_code, c.janela_fechada, v.project_id, v.opportunity_id, v.funnel_run_id,
       c.impressoes, c.cliques, c.cliques_invalidos, c.conversoes,
       round(c.custo_micros / 1e6, 2) AS custo,
       gam.receita_brl AS receita_gam_brl, jads.receita_brl AS receita_joinads_brl,
       CASE WHEN gam.receita_brl IS NULL AND jads.receita_brl IS NULL THEN NULL
            ELSE coalesce(gam.receita_brl, 0) + coalesce(jads.receita_brl, 0) END AS receita_brl,
       CASE WHEN c.cliques > 0 THEN round(c.custo_micros / 1e6 / c.cliques, 4) END AS cpc,
       CASE WHEN c.currency_code = 'BRL' AND (gam.receita_brl IS NOT NULL OR jads.receita_brl IS NOT NULL)
            THEN coalesce(gam.receita_brl, 0) + coalesce(jads.receita_brl, 0) - c.custo_micros / 1e6 END AS lucro_brl,
       CASE WHEN c.currency_code = 'BRL' AND c.custo_micros > 0
                 AND (gam.receita_brl IS NOT NULL OR jads.receita_brl IS NOT NULL)
            THEN round((coalesce(gam.receita_brl, 0) + coalesce(jads.receita_brl, 0)) / (c.custo_micros / 1e6), 4) END AS roas,
       CASE WHEN c.currency_code = 'BRL' AND c.cliques > 0
                 AND (gam.receita_brl IS NOT NULL OR jads.receita_brl IS NOT NULL)
            THEN round((coalesce(gam.receita_brl, 0) + coalesce(jads.receita_brl, 0)) / c.cliques, 4) END AS receita_por_clique
  FROM public.vw_gads_campanha_dia c
  LEFT JOIN gam  ON gam.date = c.metric_date AND gam.utm_campaign_value = c.campaign_id
  LEFT JOIN jads ON jads.date = c.metric_date AND jads.utm_campaign_value = c.campaign_id
  LEFT JOIN vinc v ON v.volc_campaign_id = c.volc_campaign_id;

CREATE VIEW public.vw_gads_arbitragem_placement_dia WITH (security_invoker = true) AS
WITH custo AS (
  SELECT customer_id, campaign_id, metric_date, volc_dominio(placement) AS dominio,
         max(placement_tipo) AS placement_tipo, sum(impressoes) AS impressoes, sum(cliques) AS cliques,
         sum(custo_micros) AS custo_micros, sum(conversoes) AS conversoes, max(currency_code) AS currency_code
    FROM public.google_ads_fato_granular_placement
   WHERE placement_view = 'detail'
   GROUP BY customer_id, campaign_id, metric_date, volc_dominio(placement)
), receita AS (
  SELECT campaign_id, date, volc_dominio(placement_url) AS dominio,
         sum(revenue_brl) AS receita_brl, sum(impressions) AS impressoes_gam
    FROM public.display_gam_placements GROUP BY campaign_id, date, volc_dominio(placement_url)
)
SELECT c.customer_id, c.campaign_id, c.metric_date, c.dominio, c.placement_tipo, c.currency_code,
       c.impressoes, c.cliques, c.conversoes, round(c.custo_micros / 1e6, 2) AS custo,
       r.receita_brl, r.impressoes_gam,
       CASE WHEN c.currency_code = 'BRL' AND r.receita_brl IS NOT NULL
            THEN r.receita_brl - c.custo_micros / 1e6 END AS lucro_brl,
       CASE WHEN c.currency_code = 'BRL' AND r.receita_brl IS NOT NULL AND c.custo_micros > 0
            THEN round(r.receita_brl / (c.custo_micros / 1e6), 4) END AS roas
  FROM custo c
  LEFT JOIN receita r ON r.campaign_id = c.campaign_id AND r.date = c.metric_date AND r.dominio = c.dominio;

CREATE VIEW public.vw_gads_arbitragem_hora WITH (security_invoker = true) AS
WITH custo AS (
  SELECT customer_id, campaign_id, metric_date, hora, fuso,
         ((metric_date + make_interval(hours => hora)) AT TIME ZONE fuso) AS inicio_da_hora,
         sum(impressoes) AS impressoes, sum(cliques) AS cliques, sum(custo_micros) AS custo_micros,
         sum(conversoes) AS conversoes, max(currency_code) AS currency_code
    FROM public.google_ads_fato_granular_hora_dispositivo
   GROUP BY customer_id, campaign_id, metric_date, hora, fuso
), receita AS (
  SELECT campaign_id, hour_bucket, sum(revenue) AS receita, sum(impressions) AS impressoes_gam
    FROM public.hourly_stats GROUP BY campaign_id, hour_bucket
)
SELECT c.customer_id, c.campaign_id, c.metric_date, c.hora, c.fuso, c.inicio_da_hora, c.currency_code,
       c.impressoes, c.cliques, c.conversoes, round(c.custo_micros / 1e6, 2) AS custo,
       r.receita, r.impressoes_gam
  FROM custo c
  LEFT JOIN receita r ON r.campaign_id = c.campaign_id AND r.hour_bucket = c.inicio_da_hora;

COMMENT ON VIEW public.vw_gads_arbitragem_campanha_dia IS
  'Custo Google × receita GAM+JoinAds por campanha-dia (utm_campaign_value = campaign_id). Lucro/ROAS só quando a conta é BRL.';
COMMENT ON VIEW public.vw_gads_arbitragem_placement_dia IS
  'Custo Google por domínio de placement × receita GAM por placement (display_gam_placements), por campanha-dia.';
COMMENT ON VIEW public.vw_gads_arbitragem_hora IS
  'Custo Google por campanha-hora (fuso da conta convertido para instante) × receita GAM horária (hourly_stats).';

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
