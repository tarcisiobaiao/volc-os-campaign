-- =============================================================================
-- v15_02 — Meta Ads: insights read model draft
-- =============================================================================
-- NAO APLICADO NESTA MISSAO.
-- DEPENDE DE: v15_01_meta_ads_read_model.sql.
-- Grão: provider + conta + nivel + objeto externo + periodo + janela de
-- atribuicao + breakdown + observado_em. Metricas permanecem NULL quando a Meta
-- nao retornou o campo; NULL nunca vira zero. Actions ficam em tabela propria.
-- =============================================================================
\set ON_ERROR_STOP on

BEGIN;

DO $guarda$
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'v15_02 deve rodar como postgres ou supabase_admin; atual: %', current_user;
  END IF;
  IF to_regclass('public.trafego_meta_ad_account') IS NULL THEN
    RAISE EXCEPTION 'v15_02 depende de public.trafego_meta_ad_account (v15_01)';
  END IF;
  IF to_regclass('public.trafego_meta_insight_daily') IS NOT NULL
     OR to_regclass('public.trafego_meta_insight_action') IS NOT NULL THEN
    RAISE EXCEPTION 'v15_02 ja parece aplicada; rode v15_98 antes de reaplicar';
  END IF;
END
$guarda$;

CREATE TABLE public.trafego_meta_insight_daily (
  meta_insight_daily_id text PRIMARY KEY,
  ad_account_ativo_id   text NOT NULL REFERENCES public.trafego_meta_ad_account (cofre_ativo_id) ON DELETE RESTRICT,
  provider              text NOT NULL DEFAULT 'META_ADS',
  conta_externa          text NOT NULL,
  nivel                  text NOT NULL,
  objeto_externo         text NOT NULL,
  periodo_inicio         date NOT NULL,
  periodo_fim            date NOT NULL,
  janela_atribuicao      text NOT NULL,
  breakdown              text NOT NULL DEFAULT 'none',
  observado_em           timestamptz NOT NULL,
  spend                  numeric,
  impressions            bigint,
  reach                  bigint,
  frequency              numeric,
  clicks                 bigint,
  inline_link_clicks     bigint,
  landing_page_views     bigint,
  cpm                    numeric,
  cpc                    numeric,
  ctr                    numeric,
  criado_em              timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT trafego_meta_insight_provider CHECK (provider = 'META_ADS'),
  CONSTRAINT trafego_meta_insight_conta_valida CHECK (conta_externa ~ '^[0-9]{1,40}$'),
  CONSTRAINT trafego_meta_insight_nivel CHECK (nivel IN ('account','campaign','adset','ad')),
  CONSTRAINT trafego_meta_insight_periodo CHECK (periodo_fim >= periodo_inicio),
  CONSTRAINT trafego_meta_insight_janela_util CHECK (btrim(janela_atribuicao) <> ''),
  CONSTRAINT trafego_meta_insight_breakdown_util CHECK (btrim(breakdown) <> ''),
  CONSTRAINT trafego_meta_insight_metricas_nao_negativas CHECK (
    coalesce(spend, 0) >= 0
    AND coalesce(impressions, 0) >= 0
    AND coalesce(reach, 0) >= 0
    AND coalesce(frequency, 0) >= 0
    AND coalesce(clicks, 0) >= 0
    AND coalesce(inline_link_clicks, 0) >= 0
    AND coalesce(landing_page_views, 0) >= 0
    AND coalesce(cpm, 0) >= 0
    AND coalesce(cpc, 0) >= 0
    AND coalesce(ctr, 0) >= 0
  ),
  UNIQUE (
    ad_account_ativo_id,
    nivel,
    objeto_externo,
    periodo_inicio,
    periodo_fim,
    janela_atribuicao,
    breakdown,
    observado_em
  )
);

CREATE TABLE public.trafego_meta_insight_action (
  meta_insight_daily_id text NOT NULL REFERENCES public.trafego_meta_insight_daily (meta_insight_daily_id) ON DELETE RESTRICT,
  ordem                 integer NOT NULL,
  action_type           text NOT NULL,
  value                 numeric,
  attribution_window    text NOT NULL,
  object_level          text NOT NULL,
  date_start            date NOT NULL,
  date_stop             date NOT NULL,
  criado_em             timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (meta_insight_daily_id, ordem),
  CONSTRAINT trafego_meta_action_type_util CHECK (btrim(action_type) <> ''),
  CONSTRAINT trafego_meta_action_window_util CHECK (btrim(attribution_window) <> ''),
  CONSTRAINT trafego_meta_action_level CHECK (object_level IN ('account','campaign','adset','ad')),
  CONSTRAINT trafego_meta_action_periodo CHECK (date_stop >= date_start),
  CONSTRAINT trafego_meta_action_value_nao_negativo CHECK (value IS NULL OR value >= 0)
);

ALTER TABLE public.trafego_meta_insight_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_meta_insight_daily FORCE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_meta_insight_action ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_meta_insight_action FORCE ROW LEVEL SECURITY;

REVOKE ALL ON public.trafego_meta_insight_daily FROM anon, authenticated;
REVOKE ALL ON public.trafego_meta_insight_action FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.trafego_meta_insight_daily TO service_role;
GRANT SELECT, INSERT ON public.trafego_meta_insight_action TO service_role;

COMMIT;
