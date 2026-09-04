-- =============================================================================
-- v15_01 — Meta Ads: read model isolado e recibo de sincronizacao
-- =============================================================================
-- APLICAR COMO: postgres ou supabase_admin.
-- DEPENDE DE: v13_01_cofre_de_ativos.sql.
--
-- Este schema NAO generaliza as tabelas v9, cuja identidade fisica ainda e
-- Google-shaped. Tambem NAO guarda token, locator de cofre, resposta bruta,
-- insight, asset ou qualquer plano de mutacao. Seu unico fato remoto e a
-- hierarquia Campaign -> Ad Set -> Ad -> Creative lida por um backend.
-- =============================================================================
\set ON_ERROR_STOP on

BEGIN;

DO $guarda$
DECLARE faltando text;
BEGIN
  IF current_user NOT IN ('postgres', 'supabase_admin') THEN
    RAISE EXCEPTION 'v15_01 deve rodar como postgres ou supabase_admin; atual: %', current_user;
  END IF;
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'v15_01 exige PostgreSQL 15 ou maior; atual: %', current_setting('server_version');
  END IF;
  IF to_regclass('public.cofre_ativo') IS NULL THEN
    RAISE EXCEPTION 'v15_01 depende de public.cofre_ativo (v13_01)';
  END IF;
  SELECT string_agg(r, ', ' ORDER BY r) INTO faltando
    FROM unnest(ARRAY['anon','authenticated','service_role']) AS r
   WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r);
  IF faltando IS NOT NULL THEN
    RAISE EXCEPTION 'v15_01 exige papeis Supabase; ausentes: %', faltando;
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(ARRAY[
      'trafego_meta_business','trafego_meta_ad_account','trafego_meta_project_binding',
      'trafego_meta_campaign','trafego_meta_adset','trafego_meta_ad',
      'trafego_meta_creative','trafego_meta_ad_creative_binding','trafego_meta_sync_run'
    ]) AS t WHERE to_regclass('public.' || t) IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'v15_01 ja parece aplicada; rode v15_99 antes de reaplicar';
  END IF;
END
$guarda$;

CREATE TABLE public.trafego_meta_business (
  cofre_ativo_id      text PRIMARY KEY REFERENCES public.cofre_ativo (ativo_id) ON DELETE RESTRICT,
  business_external_id text NOT NULL UNIQUE,
  nome_observado      text,
  observado_em        timestamptz,
  criado_em           timestamptz NOT NULL DEFAULT now(),
  atualizado_em       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT trafego_meta_business_external_id_valido
    CHECK (business_external_id ~ '^[0-9]{1,40}$'),
  CONSTRAINT trafego_meta_business_nome_util
    CHECK (nome_observado IS NULL OR btrim(nome_observado) <> ''),
  CONSTRAINT trafego_meta_business_observacao_coerente
    CHECK (nome_observado IS NULL OR observado_em IS NOT NULL)
);

CREATE TABLE public.trafego_meta_ad_account (
  cofre_ativo_id       text PRIMARY KEY REFERENCES public.cofre_ativo (ativo_id) ON DELETE RESTRICT,
  business_ativo_id    text NOT NULL REFERENCES public.trafego_meta_business (cofre_ativo_id) ON DELETE RESTRICT,
  account_external_id  text NOT NULL UNIQUE,
  nome_observado       text,
  moeda                text,
  timezone_name        text,
  account_status       text,
  readiness_state      text NOT NULL DEFAULT 'CONFIG_MISSING',
  observado_em         timestamptz,
  ultima_leitura_ok_em timestamptz,
  ultima_falha_em      timestamptz,
  criado_em            timestamptz NOT NULL DEFAULT now(),
  atualizado_em        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT trafego_meta_account_external_id_valido
    CHECK (account_external_id ~ '^[0-9]{1,40}$'),
  CONSTRAINT trafego_meta_account_sem_prefixo_act
    CHECK (account_external_id !~ '^act_'),
  CONSTRAINT trafego_meta_account_moeda_iso
    CHECK (moeda IS NULL OR moeda ~ '^[A-Z]{3}$'),
  CONSTRAINT trafego_meta_account_timezone_util
    CHECK (timezone_name IS NULL OR btrim(timezone_name) <> ''),
  CONSTRAINT trafego_meta_account_readiness_conhecida CHECK (readiness_state IN (
    'CONFIG_MISSING','REFERENCE_PRESENT','RESOLUTION_UNTESTED','RESOLUTION_FAILED',
    'PERMISSIONS_INSUFFICIENT','ACCOUNT_INACCESSIBLE','READY_FOR_READ',
    'READY_FOR_VALIDATION','READY_FOR_CREATE_PAUSED','READY_FOR_ACTIVATION'
  )),
  CONSTRAINT trafego_meta_account_sucesso_observado
    CHECK (ultima_leitura_ok_em IS NULL OR observado_em IS NOT NULL)
);

CREATE TABLE public.trafego_meta_project_binding (
  binding_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ad_account_ativo_id  text NOT NULL REFERENCES public.trafego_meta_ad_account (cofre_ativo_id) ON DELETE RESTRICT,
  project_id            bigint NOT NULL,
  confirmado_por        text NOT NULL,
  confirmado_em         timestamptz NOT NULL DEFAULT now(),
  evidencia_resumo      text NOT NULL,
  desfeito_por          text,
  desfeito_em           timestamptz,
  desfeito_motivo       text,
  CONSTRAINT trafego_meta_binding_project_positivo CHECK (project_id > 0),
  CONSTRAINT trafego_meta_binding_confirmador_util CHECK (btrim(confirmado_por) <> ''),
  CONSTRAINT trafego_meta_binding_evidencia_util
    CHECK (length(btrim(evidencia_resumo)) BETWEEN 5 AND 500),
  CONSTRAINT trafego_meta_binding_desfeito_completo CHECK (
    (desfeito_em IS NULL AND desfeito_por IS NULL AND desfeito_motivo IS NULL)
    OR (desfeito_em IS NOT NULL AND btrim(coalesce(desfeito_por,'')) <> ''
        AND length(btrim(coalesce(desfeito_motivo,''))) >= 5)
  )
);
CREATE UNIQUE INDEX trafego_meta_project_binding_ativo_ux
  ON public.trafego_meta_project_binding (ad_account_ativo_id)
  WHERE desfeito_em IS NULL;

CREATE TABLE public.trafego_meta_campaign (
  meta_campaign_id      uuid PRIMARY KEY,
  ad_account_ativo_id   text NOT NULL REFERENCES public.trafego_meta_ad_account (cofre_ativo_id) ON DELETE RESTRICT,
  external_id           text NOT NULL,
  nome                  text,
  status                text,
  effective_status      text,
  objetivo              text,
  observado_em          timestamptz NOT NULL,
  ultima_vez_visto_em   timestamptz NOT NULL,
  ausente_desde         timestamptz,
  ausencia_causa        text,
  criado_em             timestamptz NOT NULL DEFAULT now(),
  atualizado_em         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT trafego_meta_campaign_external_id_valido CHECK (external_id ~ '^[0-9]{1,40}$'),
  CONSTRAINT trafego_meta_campaign_ausencia_coerente CHECK (
    (ausente_desde IS NULL AND ausencia_causa IS NULL)
    OR (ausente_desde IS NOT NULL AND ausencia_causa IN ('nao_encontrada','fora_de_escopo'))
  ),
  CONSTRAINT trafego_meta_campaign_tempo_coerente CHECK (ultima_vez_visto_em <= observado_em),
  UNIQUE (ad_account_ativo_id, external_id)
);

CREATE TABLE public.trafego_meta_adset (
  meta_adset_id         uuid PRIMARY KEY,
  meta_campaign_id      uuid NOT NULL REFERENCES public.trafego_meta_campaign (meta_campaign_id) ON DELETE RESTRICT,
  external_id           text NOT NULL,
  nome                  text,
  status                text,
  effective_status      text,
  optimization_goal     text,
  observado_em          timestamptz NOT NULL,
  ultima_vez_visto_em   timestamptz NOT NULL,
  ausente_desde         timestamptz,
  ausencia_causa        text,
  criado_em             timestamptz NOT NULL DEFAULT now(),
  atualizado_em         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT trafego_meta_adset_external_id_valido CHECK (external_id ~ '^[0-9]{1,40}$'),
  CONSTRAINT trafego_meta_adset_ausencia_coerente CHECK (
    (ausente_desde IS NULL AND ausencia_causa IS NULL)
    OR (ausente_desde IS NOT NULL AND ausencia_causa IN ('nao_encontrada','fora_de_escopo'))
  ),
  CONSTRAINT trafego_meta_adset_tempo_coerente CHECK (ultima_vez_visto_em <= observado_em),
  UNIQUE (meta_campaign_id, external_id)
);

CREATE TABLE public.trafego_meta_ad (
  meta_ad_id            uuid PRIMARY KEY,
  meta_adset_id         uuid NOT NULL REFERENCES public.trafego_meta_adset (meta_adset_id) ON DELETE RESTRICT,
  external_id           text NOT NULL,
  nome                  text,
  status                text,
  effective_status      text,
  observado_em          timestamptz NOT NULL,
  ultima_vez_visto_em   timestamptz NOT NULL,
  ausente_desde         timestamptz,
  ausencia_causa        text,
  criado_em             timestamptz NOT NULL DEFAULT now(),
  atualizado_em         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT trafego_meta_ad_external_id_valido CHECK (external_id ~ '^[0-9]{1,40}$'),
  CONSTRAINT trafego_meta_ad_ausencia_coerente CHECK (
    (ausente_desde IS NULL AND ausencia_causa IS NULL)
    OR (ausente_desde IS NOT NULL AND ausencia_causa IN ('nao_encontrada','fora_de_escopo'))
  ),
  CONSTRAINT trafego_meta_ad_tempo_coerente CHECK (ultima_vez_visto_em <= observado_em),
  UNIQUE (meta_adset_id, external_id)
);

CREATE TABLE public.trafego_meta_creative (
  meta_creative_id      uuid PRIMARY KEY,
  ad_account_ativo_id   text NOT NULL REFERENCES public.trafego_meta_ad_account (cofre_ativo_id) ON DELETE RESTRICT,
  external_id           text NOT NULL,
  nome                  text,
  object_story_id       text,
  observado_em          timestamptz NOT NULL,
  ultima_vez_visto_em   timestamptz NOT NULL,
  ausente_desde         timestamptz,
  ausencia_causa        text,
  criado_em             timestamptz NOT NULL DEFAULT now(),
  atualizado_em         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT trafego_meta_creative_external_id_valido CHECK (external_id ~ '^[0-9]{1,40}$'),
  CONSTRAINT trafego_meta_creative_ausencia_coerente CHECK (
    (ausente_desde IS NULL AND ausencia_causa IS NULL)
    OR (ausente_desde IS NOT NULL AND ausencia_causa IN ('nao_encontrada','fora_de_escopo'))
  ),
  CONSTRAINT trafego_meta_creative_tempo_coerente CHECK (ultima_vez_visto_em <= observado_em),
  UNIQUE (ad_account_ativo_id, external_id)
);

CREATE TABLE public.trafego_meta_ad_creative_binding (
  meta_ad_id            uuid NOT NULL REFERENCES public.trafego_meta_ad (meta_ad_id) ON DELETE RESTRICT,
  meta_creative_id      uuid NOT NULL REFERENCES public.trafego_meta_creative (meta_creative_id) ON DELETE RESTRICT,
  observado_em          timestamptz NOT NULL,
  ausente_desde         timestamptz,
  ausencia_causa        text,
  PRIMARY KEY (meta_ad_id, meta_creative_id),
  CONSTRAINT trafego_meta_ad_creative_ausencia_coerente CHECK (
    (ausente_desde IS NULL AND ausencia_causa IS NULL)
    OR (ausente_desde IS NOT NULL AND ausencia_causa IN ('nao_encontrada','fora_de_escopo'))
  )
);

CREATE TABLE public.trafego_meta_sync_run (
  run_id                 uuid PRIMARY KEY,
  ad_account_ativo_id    text NOT NULL REFERENCES public.trafego_meta_ad_account (cofre_ativo_id) ON DELETE RESTRICT,
  chave_de_idempotencia  text NOT NULL,
  escopo                 text NOT NULL DEFAULT 'hierarchy',
  resultado              text NOT NULL,
  iniciado_em            timestamptz NOT NULL,
  concluido_em           timestamptz NOT NULL,
  paginas_lidas          integer NOT NULL DEFAULT 0,
  contagens              jsonb NOT NULL DEFAULT '{}'::jsonb,
  cursor_final           jsonb NOT NULL DEFAULT '{}'::jsonb,
  erro_codigo            text,
  erro_mensagem          text,
  criado_em              timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT trafego_meta_sync_chave_valida
    CHECK (chave_de_idempotencia ~ '^meta_sync_[a-f0-9]{32}$'),
  CONSTRAINT trafego_meta_sync_escopo_conhecido CHECK (escopo = 'hierarchy'),
  CONSTRAINT trafego_meta_sync_resultado_conhecido CHECK (resultado IN ('ok','falhou')),
  CONSTRAINT trafego_meta_sync_tempo_coerente CHECK (concluido_em >= iniciado_em),
  CONSTRAINT trafego_meta_sync_paginas_nao_negativas CHECK (paginas_lidas >= 0),
  CONSTRAINT trafego_meta_sync_json_objetos CHECK (
    jsonb_typeof(contagens) = 'object' AND jsonb_typeof(cursor_final) = 'object'),
  CONSTRAINT trafego_meta_sync_erro_coerente CHECK (
    (resultado = 'ok' AND erro_codigo IS NULL AND erro_mensagem IS NULL)
    OR (resultado = 'falhou' AND btrim(coalesce(erro_codigo,'')) <> '')
  ),
  CONSTRAINT trafego_meta_sync_erro_limitado CHECK (
    erro_mensagem IS NULL OR length(erro_mensagem) <= 500)
);
CREATE UNIQUE INDEX trafego_meta_sync_sucesso_idempotente_ux
  ON public.trafego_meta_sync_run (chave_de_idempotencia)
  WHERE resultado = 'ok';
CREATE INDEX trafego_meta_sync_conta_ix
  ON public.trafego_meta_sync_run (ad_account_ativo_id, concluido_em DESC);

-- The owner can still bypass grants; make accidental DELETE fail for it too.
CREATE FUNCTION public.trafego_meta_recusa_delete()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
  RAISE EXCEPTION 'trafego_meta e historico/read model: DELETE recusado; marque ausencia';
END
$$;

DO $triggers$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'trafego_meta_business','trafego_meta_ad_account','trafego_meta_project_binding',
    'trafego_meta_campaign','trafego_meta_adset','trafego_meta_ad',
    'trafego_meta_creative','trafego_meta_ad_creative_binding','trafego_meta_sync_run'
  ] LOOP
    EXECUTE format(
      'CREATE TRIGGER %I BEFORE DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.trafego_meta_recusa_delete()',
      t || '_sem_delete', t);
  END LOOP;
END
$triggers$;

DO $seguranca$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'trafego_meta_business','trafego_meta_ad_account','trafego_meta_project_binding',
    'trafego_meta_campaign','trafego_meta_adset','trafego_meta_ad',
    'trafego_meta_creative','trafego_meta_ad_creative_binding','trafego_meta_sync_run'
  ] LOOP
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM authenticated', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM service_role', t);
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON TABLE public.%I TO service_role', t);
  END LOOP;
END
$seguranca$;

REVOKE ALL ON FUNCTION public.trafego_meta_recusa_delete() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.trafego_meta_recusa_delete() FROM anon;
REVOKE ALL ON FUNCTION public.trafego_meta_recusa_delete() FROM authenticated;
REVOKE ALL ON FUNCTION public.trafego_meta_recusa_delete() FROM service_role;

COMMENT ON TABLE public.trafego_meta_sync_run IS
  'Recibo read-only de uma tentativa Meta. Falhas podem repetir a chave; um unico sucesso pode vence-la.';
COMMENT ON COLUMN public.trafego_meta_ad_account.account_external_id IS
  'ID canonico server-side, sem prefixo act_. Nao expor em view de navegador.';

COMMIT;
