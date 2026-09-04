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

CREATE TABLE public.trafego_meta_custom_measurement (
  ad_account_ativo_id      text NOT NULL REFERENCES public.trafego_meta_ad_account (cofre_ativo_id) ON DELETE RESTRICT,
  measurement_type         text NOT NULL,
  observed_count           integer,
  observado_em             timestamptz NOT NULL,
  snapshot_hash            text NOT NULL,
  criado_em                timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (ad_account_ativo_id, measurement_type, observado_em),
  CONSTRAINT trafego_meta_measurement_type_util CHECK (btrim(measurement_type) <> ''),
  CONSTRAINT trafego_meta_measurement_count_non_negative CHECK (observed_count IS NULL OR observed_count >= 0),
  CONSTRAINT trafego_meta_measurement_hash_valido CHECK (snapshot_hash ~ '^meta_snapshot_[a-f0-9]{32}$')
);

ALTER TABLE public.trafego_meta_insight_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_meta_insight_daily FORCE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_meta_insight_action ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_meta_insight_action FORCE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_meta_custom_measurement ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_meta_custom_measurement FORCE ROW LEVEL SECURITY;

REVOKE ALL ON public.trafego_meta_insight_daily FROM anon, authenticated;
REVOKE ALL ON public.trafego_meta_insight_action FROM anon, authenticated;
REVOKE ALL ON public.trafego_meta_custom_measurement FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.trafego_meta_insight_daily TO service_role;
GRANT SELECT, INSERT ON public.trafego_meta_insight_action TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.trafego_meta_custom_measurement TO service_role;

CREATE OR REPLACE FUNCTION public.trafego_meta_persistir_snapshot(p_snapshot jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
DECLARE
  v_account_asset text := p_snapshot->>'account_asset_id';
  v_credential_asset text := p_snapshot->>'credential_asset_id';
  v_snapshot_hash text := p_snapshot->>'snapshot_hash';
  v_idempotency text := p_snapshot->>'idempotency_key';
  v_observed timestamptz := (p_snapshot->>'observed_at')::timestamptz;
  v_window text := p_snapshot->>'window';
  v_run uuid := gen_random_uuid();
BEGIN
  IF current_setting('role', true) <> 'service_role'
     AND session_user <> 'service_role'
     AND current_user <> 'service_role' THEN
    RAISE EXCEPTION 'trafego_meta_persistir_snapshot exige service_role';
  END IF;
  IF p_snapshot->>'provider' <> 'META_ADS' THEN
    RAISE EXCEPTION 'provider invalido para snapshot Meta';
  END IF;
  IF v_account_asset IS NULL OR v_snapshot_hash !~ '^meta_snapshot_[a-f0-9]{32}$' OR v_idempotency !~ '^meta_sync_[a-f0-9]{32}$' THEN
    RAISE EXCEPTION 'snapshot Meta sem chaves canonicas validas';
  END IF;
  IF EXISTS (SELECT 1 FROM public.trafego_meta_sync_run WHERE chave_de_idempotencia = v_idempotency AND resultado = 'ok') THEN
    RETURN jsonb_build_object('ok', true, 'repetido', true, 'run_id', (
      SELECT run_id::text FROM public.trafego_meta_sync_run WHERE chave_de_idempotencia = v_idempotency AND resultado = 'ok' ORDER BY concluido_em DESC LIMIT 1));
  END IF;

  INSERT INTO public.cofre_ativo (ativo_id, kind, cluster, nome, plataforma, estado, criticidade, resumo, dono_nome, dono_custodia, capacidades, tags, proxima_acao)
  VALUES
    (v_credential_asset, 'integration', 'automation', 'Credencial Meta local Keychain', 'Meta Ads', 'restricted', 'critical', 'Referencia local sanitizada; token fica apenas no Keychain/backend.', 'VOLC', 'verified', ARRAY['meta_read'], ARRAY['meta','keychain'], 'Manter token fora do banco e usar somente por backend autorizado.'),
    (v_account_asset, 'meta_ad_account', 'paid_media', coalesce(p_snapshot #>> '{rows,trafego_meta_ad_account,0,nome_observado}', 'Conta Meta'), 'Meta Ads', 'ready', 'high', 'Conta Meta lida por snapshot somente leitura.', 'VOLC', 'verified', ARRAY['meta_read'], ARRAY['meta','read-model'], 'Consultar inventario persistido e habilitar escrita apenas por missao autorizada.')
  ON CONFLICT (ativo_id) DO UPDATE SET atualizado_em = now();

  INSERT INTO public.cofre_ativo (ativo_id, kind, cluster, nome, plataforma, estado, criticidade, resumo, dono_nome, dono_custodia, capacidades, tags, proxima_acao)
  SELECT b.cofre_ativo_id, 'meta_business_portfolio', 'paid_media', coalesce(b.nome_observado, 'Business Meta'), 'Meta Ads', 'ready', 'high', 'Business Meta observado por snapshot somente leitura.', 'VOLC', 'verified', ARRAY['meta_read'], ARRAY['meta','business'], 'Manter como contexto de conta Meta.'
  FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_business}', '[]'::jsonb)) AS b(cofre_ativo_id text, nome_observado text)
  ON CONFLICT (ativo_id) DO UPDATE SET atualizado_em = now();

  INSERT INTO public.trafego_meta_business (cofre_ativo_id, business_external_id, nome_observado, observado_em)
  SELECT cofre_ativo_id, business_external_id, nome_observado, observado_em
  FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_business}', '[]'::jsonb)) AS x(cofre_ativo_id text, business_external_id text, nome_observado text, observado_em timestamptz)
  ON CONFLICT (cofre_ativo_id) DO UPDATE SET nome_observado = EXCLUDED.nome_observado, observado_em = EXCLUDED.observado_em, atualizado_em = now();

  INSERT INTO public.trafego_meta_ad_account (cofre_ativo_id, business_ativo_id, credential_ativo_id, account_external_id, nome_observado, moeda, timezone_name, account_status, readiness_state, observado_em, ultima_leitura_ok_em)
  SELECT cofre_ativo_id, business_ativo_id, credential_ativo_id, account_external_id, nome_observado, moeda, timezone_name, account_status, readiness_state, observado_em, observado_em
  FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_ad_account}', '[]'::jsonb)) AS x(cofre_ativo_id text, business_ativo_id text, credential_ativo_id text, account_external_id text, nome_observado text, moeda text, timezone_name text, account_status text, readiness_state text, observado_em timestamptz)
  ON CONFLICT (cofre_ativo_id) DO UPDATE SET nome_observado=EXCLUDED.nome_observado, moeda=EXCLUDED.moeda, timezone_name=EXCLUDED.timezone_name, account_status=EXCLUDED.account_status, readiness_state=EXCLUDED.readiness_state, observado_em=EXCLUDED.observado_em, ultima_leitura_ok_em=EXCLUDED.ultima_leitura_ok_em, atualizado_em=now();

  INSERT INTO public.trafego_meta_campaign (meta_campaign_id, ad_account_ativo_id, external_id, nome, status, effective_status, objetivo, observado_em, ultima_vez_visto_em)
  SELECT meta_campaign_id, ad_account_ativo_id, external_id, nome, status, effective_status, objetivo, observado_em, ultima_vez_visto_em
  FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_campaign}', '[]'::jsonb)) AS x(meta_campaign_id uuid, ad_account_ativo_id text, external_id text, nome text, status text, effective_status text, objetivo text, observado_em timestamptz, ultima_vez_visto_em timestamptz)
  ON CONFLICT (ad_account_ativo_id, external_id) DO UPDATE SET nome=EXCLUDED.nome, status=EXCLUDED.status, effective_status=EXCLUDED.effective_status, objetivo=EXCLUDED.objetivo, observado_em=EXCLUDED.observado_em, ultima_vez_visto_em=EXCLUDED.ultima_vez_visto_em, ausente_desde=NULL, ausencia_causa=NULL, atualizado_em=now();

  INSERT INTO public.trafego_meta_adset (meta_adset_id, meta_campaign_id, external_id, nome, status, effective_status, optimization_goal, observado_em, ultima_vez_visto_em)
  SELECT meta_adset_id, meta_campaign_id, external_id, nome, status, effective_status, optimization_goal, observado_em, ultima_vez_visto_em
  FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_adset}', '[]'::jsonb)) AS x(meta_adset_id uuid, meta_campaign_id uuid, external_id text, nome text, status text, effective_status text, optimization_goal text, observado_em timestamptz, ultima_vez_visto_em timestamptz)
  ON CONFLICT (meta_campaign_id, external_id) DO UPDATE SET nome=EXCLUDED.nome, status=EXCLUDED.status, effective_status=EXCLUDED.effective_status, optimization_goal=EXCLUDED.optimization_goal, observado_em=EXCLUDED.observado_em, ultima_vez_visto_em=EXCLUDED.ultima_vez_visto_em, ausente_desde=NULL, ausencia_causa=NULL, atualizado_em=now();

  INSERT INTO public.trafego_meta_creative (meta_creative_id, ad_account_ativo_id, external_id, nome, object_story_id, observado_em, ultima_vez_visto_em)
  SELECT meta_creative_id, ad_account_ativo_id, external_id, nome, object_story_id, observado_em, ultima_vez_visto_em
  FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_creative}', '[]'::jsonb)) AS x(meta_creative_id uuid, ad_account_ativo_id text, external_id text, nome text, object_story_id text, observado_em timestamptz, ultima_vez_visto_em timestamptz)
  ON CONFLICT (ad_account_ativo_id, external_id) DO UPDATE SET nome=EXCLUDED.nome, object_story_id=EXCLUDED.object_story_id, observado_em=EXCLUDED.observado_em, ultima_vez_visto_em=EXCLUDED.ultima_vez_visto_em, ausente_desde=NULL, ausencia_causa=NULL, atualizado_em=now();

  INSERT INTO public.trafego_meta_ad (meta_ad_id, meta_adset_id, external_id, nome, status, effective_status, observado_em, ultima_vez_visto_em)
  SELECT meta_ad_id, meta_adset_id, external_id, nome, status, effective_status, observado_em, ultima_vez_visto_em
  FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_ad}', '[]'::jsonb)) AS x(meta_ad_id uuid, meta_adset_id uuid, external_id text, nome text, status text, effective_status text, observado_em timestamptz, ultima_vez_visto_em timestamptz)
  ON CONFLICT (meta_adset_id, external_id) DO UPDATE SET nome=EXCLUDED.nome, status=EXCLUDED.status, effective_status=EXCLUDED.effective_status, observado_em=EXCLUDED.observado_em, ultima_vez_visto_em=EXCLUDED.ultima_vez_visto_em, ausente_desde=NULL, ausencia_causa=NULL, atualizado_em=now();

  INSERT INTO public.trafego_meta_ad_creative_binding (meta_ad_id, meta_creative_id, observado_em)
  SELECT meta_ad_id, meta_creative_id, observado_em
  FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_ad_creative_binding}', '[]'::jsonb)) AS x(meta_ad_id uuid, meta_creative_id uuid, observado_em timestamptz)
  ON CONFLICT (meta_ad_id, meta_creative_id) DO UPDATE SET observado_em=EXCLUDED.observado_em, ausente_desde=NULL, ausencia_causa=NULL;

  INSERT INTO public.trafego_meta_insight_daily (meta_insight_daily_id, ad_account_ativo_id, provider, conta_externa, nivel, objeto_externo, periodo_inicio, periodo_fim, janela_atribuicao, breakdown, observado_em, spend, impressions, reach, frequency, clicks, inline_link_clicks, landing_page_views, cpm, cpc, ctr)
  SELECT meta_insight_daily_id, ad_account_ativo_id, provider, conta_externa, nivel, objeto_externo, periodo_inicio, periodo_fim, janela_atribuicao, breakdown, observado_em, spend, impressions, reach, frequency, clicks, inline_link_clicks, landing_page_views, cpm, cpc, ctr
  FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_insight_daily}', '[]'::jsonb)) AS x(meta_insight_daily_id text, ad_account_ativo_id text, provider text, conta_externa text, nivel text, objeto_externo text, periodo_inicio date, periodo_fim date, janela_atribuicao text, breakdown text, observado_em timestamptz, spend numeric, impressions bigint, reach bigint, frequency numeric, clicks bigint, inline_link_clicks bigint, landing_page_views bigint, cpm numeric, cpc numeric, ctr numeric)
  ON CONFLICT (meta_insight_daily_id) DO UPDATE SET spend=EXCLUDED.spend, impressions=EXCLUDED.impressions, reach=EXCLUDED.reach, frequency=EXCLUDED.frequency, clicks=EXCLUDED.clicks, inline_link_clicks=EXCLUDED.inline_link_clicks, landing_page_views=EXCLUDED.landing_page_views, cpm=EXCLUDED.cpm, cpc=EXCLUDED.cpc, ctr=EXCLUDED.ctr;

  INSERT INTO public.trafego_meta_insight_action (meta_insight_daily_id, ordem, action_type, value, attribution_window, object_level, date_start, date_stop)
  SELECT meta_insight_daily_id, ordem, action_type, value, attribution_window, object_level, date_start, date_stop
  FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_insight_action}', '[]'::jsonb)) AS x(meta_insight_daily_id text, ordem integer, action_type text, value numeric, attribution_window text, object_level text, date_start date, date_stop date)
  ON CONFLICT (meta_insight_daily_id, ordem) DO UPDATE SET action_type=EXCLUDED.action_type, value=EXCLUDED.value, attribution_window=EXCLUDED.attribution_window, object_level=EXCLUDED.object_level, date_start=EXCLUDED.date_start, date_stop=EXCLUDED.date_stop;

  INSERT INTO public.trafego_meta_custom_measurement (ad_account_ativo_id, measurement_type, observed_count, observado_em, snapshot_hash)
  SELECT ad_account_ativo_id, measurement_type, observed_count, observado_em, snapshot_hash
  FROM jsonb_to_recordset(coalesce(p_snapshot #> '{rows,trafego_meta_custom_measurement}', '[]'::jsonb)) AS x(ad_account_ativo_id text, measurement_type text, observed_count integer, observado_em timestamptz, snapshot_hash text)
  ON CONFLICT (ad_account_ativo_id, measurement_type, observado_em) DO UPDATE SET observed_count=EXCLUDED.observed_count, snapshot_hash=EXCLUDED.snapshot_hash;

  INSERT INTO public.trafego_meta_sync_run (run_id, ad_account_ativo_id, chave_de_idempotencia, escopo, resultado, iniciado_em, concluido_em, paginas_lidas, contagens, cursor_final, snapshot_hash, escrita_executada, parcialidade)
  VALUES (v_run, v_account_asset, v_idempotency, 'hierarchy', 'ok', v_observed, clock_timestamp(), coalesce((p_snapshot->>'page_count')::int, 0), coalesce(p_snapshot->'counts','{}'::jsonb), jsonb_build_object('window', v_window), v_snapshot_hash, true, coalesce(p_snapshot->'partiality','[]'::jsonb));

  RETURN jsonb_build_object('ok', true, 'repetido', false, 'run_id', v_run::text);
EXCEPTION WHEN unique_violation THEN
  IF EXISTS (SELECT 1 FROM public.trafego_meta_sync_run WHERE chave_de_idempotencia = v_idempotency AND resultado = 'ok') THEN
    RETURN jsonb_build_object('ok', true, 'repetido', true, 'run_id', (
      SELECT run_id::text FROM public.trafego_meta_sync_run WHERE chave_de_idempotencia = v_idempotency AND resultado = 'ok' ORDER BY concluido_em DESC LIMIT 1));
  END IF;
  RAISE;
END;
$$;

REVOKE ALL ON FUNCTION public.trafego_meta_persistir_snapshot(jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.trafego_meta_persistir_snapshot(jsonb) TO service_role;

COMMIT;
