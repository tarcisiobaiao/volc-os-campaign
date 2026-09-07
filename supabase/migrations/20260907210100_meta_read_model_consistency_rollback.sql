-- =============================================================================
-- ROLLBACK de 20260907210000_meta_read_model_consistency.sql
-- =============================================================================
-- ⚠️ ESTE ARQUIVO NUNCA ENTRA NUMA LISTA DE APPLY.
--
-- ⚠️ REVERTER REABRE OS DEFEITOS, e vale dizer quais em voz alta:
--   * a ausencia volta a nunca ser marcada (objeto apagado na Meta fica
--     "presente" para sempre);
--   * um snapshot atrasado volta a sobrescrever um mais novo em silencio;
--   * `service_role` volta a ter DELETE e TRUNCATE nas tres tabelas de fatos;
--   * a RPC volta a `search_path = public, pg_catalog` (public na frente);
--   * a RPC volta a escrever `cofre_ativo` direto, com custodia 'verified'
--     forjada e sem trilha de revisao;
--   * `credential_asset_id` volta a vir do payload de quem chama.
--
-- ⚠️ ELE PERDE DADO, e nao ha como nao perder: `DROP COLUMN` em
-- `time_increment`, `action_report_time`, `account_timezone`, `currency`,
-- `completo` e `medida` apaga o grao que foi medido. Se ja existir fato
-- gravado com `time_increment` diferente de '1' ou acao com `medida='value'`,
-- este rollback RECUSA — voltar atras ali nao devolveria o schema antigo,
-- produziria um schema antigo com numeros que ninguem mais consegue
-- interpretar. Nesse caso o conserto e para frente.
--
-- ## O QUE ELE NAO FAZ
-- Nao dropa `trafego_meta_insight_daily`, `_action` nem `_custom_measurement`.
-- Nao dropa nada de v15_01 nem do Cofre. Nao apaga linha de fato, de recibo
-- (`trafego_meta_sync_run`) nem de trilha (`cofre_operacao`,
-- `cofre_ativo_revisao`). Historico operacional sai daqui intacto.
--
-- ## SOBRE A DEFINICAO ANTERIOR DA RPC
-- `trafego_meta_persistir_snapshot` e recriada abaixo com o corpo EXATO de
-- v15_02_meta_ads_insights.sql. Ela e reproduzida aqui, e nao "restaurada
-- rodando v15_02 de novo", por um motivo concreto: a guarda de v15_02 ABORTA
-- quando as tabelas de insight ja existem ('v15_02 ja parece aplicada'), entao
-- reexecutar aquele arquivo nao e um caminho disponivel depois deste delta.
-- Os ativos que o Cofre ja registrou com `dono_custodia='declared'` CONTINUAM
-- 'declared': este arquivo nao promove custodia de nada, e a RPC antiga so
-- toca `atualizado_em` em ativo que ja existe.
-- =============================================================================
\set ON_ERROR_STOP on

BEGIN;

DO $guarda$
DECLARE
  fatos_com_grao bigint;
  acoes_com_valor bigint;
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION
      'rollback de meta_read_model_consistency deve rodar como postgres ou supabase_admin; atual: %',
      current_user;
  END IF;

  IF to_regclass('public.trafego_meta_insight_daily') IS NULL THEN
    RAISE EXCEPTION
      'rollback sem alvo: public.trafego_meta_insight_daily nao existe (v15_02 nao aplicada)';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_attribute
     WHERE attrelid = 'public.trafego_meta_insight_daily'::regclass
       AND attname = 'time_increment' AND NOT attisdropped
  ) THEN
    RAISE EXCEPTION 'meta_read_model_consistency nao esta aplicado; nada a reverter';
  END IF;

  -- A mesma pergunta que o manifesto faz antes de qualquer rollback: existe
  -- fato do outro lado que este DROP tornaria ilegivel?
  SELECT count(*) INTO fatos_com_grao
    FROM public.trafego_meta_insight_daily
   WHERE time_increment <> '1' OR action_report_time <> 'impression' OR completo = false;
  SELECT count(*) INTO acoes_com_valor
    FROM public.trafego_meta_insight_action
   WHERE medida <> 'count';
  IF fatos_com_grao > 0 OR acoes_com_valor > 0 THEN
    RAISE EXCEPTION
      'rollback PROIBIDO: % fato(s) com grao nao-default e % acao(oes) com medida de valor. DROP COLUMN aqui nao volta ao schema antigo, deixa numeros sem significado. Corrija para frente.',
      fatos_com_grao, acoes_com_valor;
  END IF;

  -- O UNIQUE antigo tem MENOS colunas: ele so pode voltar se nao houver par de
  -- linhas que hoje convive por causa de `time_increment`/`action_report_time`.
  IF EXISTS (
    SELECT 1 FROM public.trafego_meta_insight_daily
     GROUP BY ad_account_ativo_id, nivel, objeto_externo, periodo_inicio,
              periodo_fim, janela_atribuicao, breakdown, observado_em
    HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION
      'rollback PROIBIDO: existem linhas que so nao colidem porque time_increment/action_report_time entraram na identidade. Restaurar o UNIQUE antigo exigiria escolher qual apagar.';
  END IF;
END
$guarda$;

-- -----------------------------------------------------------------------------
-- 1. A RPC, como era em v15_02 (corpo reproduzido, com os defeitos que tinha)
-- -----------------------------------------------------------------------------
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

COMMENT ON FUNCTION public.trafego_meta_persistir_snapshot(jsonb) IS NULL;

REVOKE ALL ON FUNCTION public.trafego_meta_persistir_snapshot(jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.trafego_meta_persistir_snapshot(jsonb) TO service_role;

-- -----------------------------------------------------------------------------
-- 2. A view de projecao corrente e o indice que a serve
-- -----------------------------------------------------------------------------
DROP VIEW  IF EXISTS public.vw_trafego_meta_insight_latest;
DROP INDEX IF EXISTS public.trafego_meta_insight_grao_corrente_ix;

-- -----------------------------------------------------------------------------
-- 3. Gatilhos de recusa e grants, como v15_02 os deixava
-- -----------------------------------------------------------------------------
DO $seguranca$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'trafego_meta_insight_daily','trafego_meta_insight_action',
    'trafego_meta_custom_measurement'
  ] LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS %I ON public.%I', t || '_sem_delete', t);
    EXECUTE format('DROP TRIGGER IF EXISTS %I ON public.%I', t || '_sem_truncate', t);
  END LOOP;
END
$seguranca$;

DROP FUNCTION IF EXISTS public.trafego_meta_recusa_remocao();

-- v15_02:123-125 concedia exatamente isto, e nada mais nem menos.
GRANT SELECT, INSERT, UPDATE ON public.trafego_meta_insight_daily TO service_role;
GRANT SELECT, INSERT          ON public.trafego_meta_insight_action TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.trafego_meta_custom_measurement TO service_role;

-- -----------------------------------------------------------------------------
-- 4. A identidade antiga do fato
-- -----------------------------------------------------------------------------
ALTER TABLE public.trafego_meta_insight_daily
  DROP CONSTRAINT IF EXISTS trafego_meta_insight_grao_unico;
ALTER TABLE public.trafego_meta_insight_action
  DROP CONSTRAINT IF EXISTS trafego_meta_action_grao_unico;

DO $identidade$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c
     WHERE c.conrelid = 'public.trafego_meta_insight_daily'::regclass
       AND c.contype = 'u'
       AND (SELECT array_agg(a.attname::text ORDER BY a.attname)
              FROM unnest(c.conkey) AS k(attnum)
              JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum)
           = ARRAY['ad_account_ativo_id','breakdown','janela_atribuicao','nivel',
                   'objeto_externo','observado_em','periodo_fim','periodo_inicio']
  ) THEN
    ALTER TABLE public.trafego_meta_insight_daily
      ADD CONSTRAINT trafego_meta_insight_daily_ad_account_ativo_id_nivel_objet_key
      UNIQUE (ad_account_ativo_id, nivel, objeto_externo, periodo_inicio,
              periodo_fim, janela_atribuicao, breakdown, observado_em);
  END IF;
END
$identidade$;

-- -----------------------------------------------------------------------------
-- 5. As colunas de grao e as funcoes auxiliares
-- -----------------------------------------------------------------------------
ALTER TABLE public.trafego_meta_insight_daily
  DROP CONSTRAINT IF EXISTS trafego_meta_insight_time_increment_conhecido,
  DROP CONSTRAINT IF EXISTS trafego_meta_insight_report_time_conhecido,
  DROP CONSTRAINT IF EXISTS trafego_meta_insight_timezone_util,
  DROP CONSTRAINT IF EXISTS trafego_meta_insight_moeda_iso,
  DROP COLUMN IF EXISTS time_increment,
  DROP COLUMN IF EXISTS action_report_time,
  DROP COLUMN IF EXISTS account_timezone,
  DROP COLUMN IF EXISTS currency,
  DROP COLUMN IF EXISTS completo;

ALTER TABLE public.trafego_meta_insight_action
  DROP CONSTRAINT IF EXISTS trafego_meta_action_medida_conhecida,
  DROP COLUMN IF EXISTS medida;

DROP FUNCTION IF EXISTS public.trafego_meta_cofre_declarar_ativo(
  text,text,text,text,text,text,text,text,text[],text[]);
DROP FUNCTION IF EXISTS public.trafego_meta_credencial_pinada();

COMMIT;
