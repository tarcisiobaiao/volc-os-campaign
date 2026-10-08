-- v17_01 — fatos granulares Google Ads + correlação com a receita (Fase B)
--
-- Autoridade: database.agenciavolc.com.br. Pré-requisito: v12_04 aplicada.
-- Desenho: docs/architecture/GADS-FATOS-GRANULARES-v17.md.
-- Estilo e invariantes: v12_04_gads_fato_canonico_dia.sql (o mesmo ledger
-- `trafego_coleta_execucao`, a mesma precedência, o mesmo NULL ≠ 0).
--
-- ## POR QUE UMA TABELA PARTICIONADA E NÃO SETE
--
-- Sete famílias (hora×dispositivo, URL, geo, placement, termo, keyword, asset)
-- dividem a mesma prova (execução, janela, precedência, moeda, API) e o mesmo
-- núcleo de métricas. Sete tabelas seriam sete RPCs com a mesma lógica de
-- precedência copiada — e a cópia é onde a precedência diverge. Uma tabela
-- particionada por `familia` dá:
--   * uma RPC e uma regra de precedência;
--   * dimensões em COLUNAS tipadas (não EAV), com CHECK por família dizendo
--     quais são obrigatórias e quais DEVEM ser nulas;
--   * índices próprios em cada partição, sem índice inútil nas outras.
--
-- ## O QUE ESTA MIGRATION NÃO FAZ
--
-- Não altera `google_ads_campanha_dia`, `daily_campaign_metrics`, `gam_metrics`
-- nem `joinads_metrics`. Cliques inválidos de campanha-dia já cabem em
-- `google_ads_campanha_dia.metricas_extras` (mesma granularidade) e são
-- expostos pela view. As views de arbitragem só LEEM.
--
-- ## INVARIANTES DEFENDIDAS PELO SCHEMA
--
--  1. Identidade completa: (familia, customer_id, campaign_id, metric_date,
--     dimensao_hash). O hash é calculado AQUI, a partir das colunas da família,
--     nunca aceito do chamador.
--  2. NULL ≠ 0: nenhuma métrica tem DEFAULT; número que chega como string é
--     linha REJEITADA, com motivo no recibo.
--  3. Precedência total D0(1) < D-1(2) < backfill(3); empate decide por
--     `colhida_em`. Leitura menor nunca rebaixa a maior.
--  4. Idempotência com memória: mesma chave + mesmo conteúdo devolve o recibo;
--     mesma chave + conteúdo diferente é RECUSADA.
--  5. Fato sem recibo não sobrevive ao COMMIT (FK DEFERRABLE para o ledger).
--  6. Escrita só pela RPC (SECURITY DEFINER); RLS forçada, sem policy.

BEGIN;

DO $$
BEGIN
  IF to_regclass('public.google_ads_campanha_dia') IS NULL
     OR to_regclass('public.trafego_coleta_execucao') IS NULL THEN
    RAISE EXCEPTION 'v17_01 recusada: exige v12_04 (google_ads_campanha_dia e trafego_coleta_execucao)';
  END IF;
  IF to_regclass('public.google_ads_fato_granular') IS NOT NULL THEN
    RAISE EXCEPTION 'v17_01 recusada: google_ads_fato_granular já existe';
  END IF;
END $$;

-- ───────────────────────────────────────────────────────── fato granular ──
CREATE TABLE public.google_ads_fato_granular (
  fato_id               uuid        NOT NULL DEFAULT gen_random_uuid(),
  familia               text        NOT NULL,

  -- IDENTIDADE
  customer_id           text        NOT NULL,
  campaign_id           text        NOT NULL,
  metric_date           date        NOT NULL,
  dimensao_hash         text        NOT NULL,

  -- DIMENSÕES (cada grupo pertence a UMA família; nas outras, NULL)
  hora                  smallint,          -- hora_dispositivo: 0..23 no fuso da conta
  dispositivo           text,
  rede                  text,
  fuso                  text,
  url                   text,              -- url
  url_tipo              text,
  geo_constant          text,              -- geo
  geo_nivel             text,
  local_tipo            text,
  placement             text,              -- placement
  placement_tipo        text,
  placement_view        text,
  placement_nome        text,
  ad_group_id           text,              -- termo (opcional: PMax não tem grupo), keyword
  termo                 text,              -- termo
  termo_match           text,
  termo_status          text,
  criterion_id          text,              -- keyword
  keyword_texto         text,
  keyword_match         text,
  quality_score         smallint,
  qs_anuncio            text,
  qs_pagina             text,
  qs_ctr_previsto       text,
  asset_id              text,              -- asset
  asset_campo           text,
  asset_contexto        text,
  asset_contexto_id     text,
  asset_rotulo          text,

  -- PROVA
  execucao_id           uuid        NOT NULL
                                    REFERENCES public.trafego_coleta_execucao (execucao_id)
                                    ON DELETE RESTRICT
                                    DEFERRABLE INITIALLY DEFERRED,
  colhida_em            timestamptz NOT NULL,
  api_versao            text        NOT NULL,
  currency_code         text        NOT NULL,
  origem_janela         text        NOT NULL,
  janela_fechada        boolean     NOT NULL,
  precedencia           smallint    NOT NULL,

  -- MÉTRICAS (sem DEFAULT: NULL = não medido)
  impressoes            bigint,
  cliques               bigint,
  interacoes            bigint,
  custo_micros          bigint,
  conversoes            numeric,
  todas_conversoes      numeric,
  valor_conversoes      numeric,
  valor_todas_conversoes numeric,
  metricas_extras       jsonb       NOT NULL DEFAULT '{}'::jsonb,

  atualizada_em         timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT google_ads_fato_granular_pk PRIMARY KEY (familia, fato_id),
  CONSTRAINT google_ads_fato_granular_chave
    UNIQUE (familia, customer_id, campaign_id, metric_date, dimensao_hash),

  CONSTRAINT google_ads_fato_granular_familia CHECK (familia IN
    ('hora_dispositivo', 'url', 'geo', 'placement', 'termo', 'keyword', 'asset')),
  CONSTRAINT google_ads_fato_granular_identidade
    CHECK (customer_id ~ '^[0-9]{6,12}$' AND campaign_id ~ '^[0-9]{1,20}$'),
  CONSTRAINT google_ads_fato_granular_hash CHECK (dimensao_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT google_ads_fato_granular_moeda CHECK (currency_code ~ '^[A-Z]{3}$'),
  CONSTRAINT google_ads_fato_granular_api CHECK (api_versao ~ '^v[0-9]{1,3}$'),
  CONSTRAINT google_ads_fato_granular_origem CHECK (origem_janela IN ('D0', 'D-1', 'backfill')),
  CONSTRAINT google_ads_fato_granular_janela_coerente
    CHECK (janela_fechada = (origem_janela <> 'D0')),
  CONSTRAINT google_ads_fato_granular_precedencia_coerente
    CHECK (precedencia = CASE origem_janela WHEN 'D0' THEN 1 WHEN 'D-1' THEN 2 ELSE 3 END),
  CONSTRAINT google_ads_fato_granular_extras_objeto
    CHECK (jsonb_typeof(metricas_extras) = 'object'),

  -- cada grupo de dimensões: obrigatório na sua família, nulo nas outras
  CONSTRAINT google_ads_fato_granular_dim_hora CHECK (
    (familia = 'hora_dispositivo'
       AND hora BETWEEN 0 AND 23 AND dispositivo IS NOT NULL AND rede IS NOT NULL AND fuso IS NOT NULL)
    OR (familia <> 'hora_dispositivo'
       AND hora IS NULL AND dispositivo IS NULL AND rede IS NULL AND fuso IS NULL)),
  CONSTRAINT google_ads_fato_granular_dim_url CHECK (
    (familia = 'url' AND url IS NOT NULL AND btrim(url) <> '' AND url_tipo IN ('final', 'expandida'))
    OR (familia <> 'url' AND url IS NULL AND url_tipo IS NULL)),
  CONSTRAINT google_ads_fato_granular_dim_geo CHECK (
    (familia = 'geo' AND geo_constant ~ '^geoTargetConstants/[0-9]+$'
       AND local_tipo IN ('area_de_interesse', 'localizacao_fisica'))
    OR (familia <> 'geo' AND geo_constant IS NULL AND geo_nivel IS NULL AND local_tipo IS NULL)),
  CONSTRAINT google_ads_fato_granular_dim_placement CHECK (
    (familia = 'placement' AND placement IS NOT NULL AND btrim(placement) <> ''
       AND placement_view IN ('detail', 'group', 'pmax'))
    OR (familia <> 'placement' AND placement IS NULL AND placement_tipo IS NULL
       AND placement_view IS NULL AND placement_nome IS NULL)),
  CONSTRAINT google_ads_fato_granular_dim_termo CHECK (
    (familia = 'termo' AND termo IS NOT NULL AND btrim(termo) <> '')
    OR (familia <> 'termo' AND termo IS NULL AND termo_match IS NULL AND termo_status IS NULL)),
  CONSTRAINT google_ads_fato_granular_dim_keyword CHECK (
    (familia = 'keyword' AND ad_group_id ~ '^[0-9]{1,20}$' AND criterion_id ~ '^[0-9]{1,20}$'
       AND keyword_texto IS NOT NULL AND (quality_score IS NULL OR quality_score BETWEEN 1 AND 10))
    OR (familia <> 'keyword' AND criterion_id IS NULL AND keyword_texto IS NULL
       AND keyword_match IS NULL AND quality_score IS NULL AND qs_anuncio IS NULL
       AND qs_pagina IS NULL AND qs_ctr_previsto IS NULL)),
  CONSTRAINT google_ads_fato_granular_dim_asset CHECK (
    (familia = 'asset' AND asset_id ~ '^[0-9]{1,20}$' AND asset_campo IS NOT NULL
       AND asset_contexto IN ('ad_group', 'asset_group', 'campanha') AND asset_contexto_id IS NOT NULL)
    OR (familia <> 'asset' AND asset_id IS NULL AND asset_campo IS NULL AND asset_contexto IS NULL
       AND asset_contexto_id IS NULL AND asset_rotulo IS NULL)),
  CONSTRAINT google_ads_fato_granular_grupo CHECK (
    ad_group_id IS NULL OR (familia IN ('termo', 'keyword') AND ad_group_id ~ '^[0-9]{1,20}$')),

  CONSTRAINT google_ads_fato_granular_nao_negativo CHECK (
    (impressoes IS NULL OR impressoes >= 0) AND (cliques IS NULL OR cliques >= 0)
    AND (interacoes IS NULL OR interacoes >= 0) AND (custo_micros IS NULL OR custo_micros >= 0)
    AND (conversoes IS NULL OR conversoes >= 0) AND (todas_conversoes IS NULL OR todas_conversoes >= 0)
    AND (valor_conversoes IS NULL OR valor_conversoes >= 0)
    AND (valor_todas_conversoes IS NULL OR valor_todas_conversoes >= 0))
) PARTITION BY LIST (familia);

CREATE TABLE public.google_ads_fato_granular_hora_dispositivo PARTITION OF public.google_ads_fato_granular FOR VALUES IN ('hora_dispositivo');
CREATE TABLE public.google_ads_fato_granular_url       PARTITION OF public.google_ads_fato_granular FOR VALUES IN ('url');
CREATE TABLE public.google_ads_fato_granular_geo       PARTITION OF public.google_ads_fato_granular FOR VALUES IN ('geo');
CREATE TABLE public.google_ads_fato_granular_placement PARTITION OF public.google_ads_fato_granular FOR VALUES IN ('placement');
CREATE TABLE public.google_ads_fato_granular_termo     PARTITION OF public.google_ads_fato_granular FOR VALUES IN ('termo');
CREATE TABLE public.google_ads_fato_granular_keyword   PARTITION OF public.google_ads_fato_granular FOR VALUES IN ('keyword');
CREATE TABLE public.google_ads_fato_granular_asset     PARTITION OF public.google_ads_fato_granular FOR VALUES IN ('asset');

CREATE INDEX google_ads_fato_granular_conta_ix ON public.google_ads_fato_granular (customer_id, metric_date DESC);
CREATE INDEX google_ads_fato_granular_campanha_ix ON public.google_ads_fato_granular (campaign_id, metric_date);
CREATE INDEX google_ads_fato_granular_execucao_ix ON public.google_ads_fato_granular (execucao_id);
CREATE INDEX google_ads_fato_granular_hora_ix ON public.google_ads_fato_granular_hora_dispositivo (campaign_id, metric_date, hora);
CREATE INDEX google_ads_fato_granular_url_ix ON public.google_ads_fato_granular_url (url, metric_date);
CREATE INDEX google_ads_fato_granular_geo_ix ON public.google_ads_fato_granular_geo (geo_constant, metric_date);
CREATE INDEX google_ads_fato_granular_placement_ix ON public.google_ads_fato_granular_placement (placement, metric_date);
CREATE INDEX google_ads_fato_granular_termo_ix ON public.google_ads_fato_granular_termo (termo, metric_date);
CREATE INDEX google_ads_fato_granular_keyword_ix ON public.google_ads_fato_granular_keyword (ad_group_id, criterion_id, metric_date);
CREATE INDEX google_ads_fato_granular_asset_ix ON public.google_ads_fato_granular_asset (asset_id, metric_date);

COMMENT ON TABLE public.google_ads_fato_granular IS
  'Fatos Google Ads abaixo de campanha-dia, por família (partição). NULL = não medido; 0 = medido e zerado. Dinheiro em micros + moeda. Escrita só por volc_registrar_gads_fatos.';
COMMENT ON COLUMN public.google_ads_fato_granular.dimensao_hash IS
  'sha256 das dimensões da família, calculado pela RPC. Nunca aceito do chamador.';
COMMENT ON COLUMN public.google_ads_fato_granular.fuso IS
  'Fuso da conta (customer.time_zone). metric_date + hora estão NESSE fuso; a view de hora converte para comparar com a receita.';

-- ─────────────────────────────────────────────────────────── mudanças ──
CREATE TABLE public.google_ads_mudanca (
  mudanca_id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id           text        NOT NULL,
  change_event_rn       text        NOT NULL,   -- change_event.resource_name (identidade do evento)
  ocorrido_em           timestamptz NOT NULL,   -- change_event.change_date_time
  tipo_recurso          text        NOT NULL,   -- change_event.change_resource_type
  recurso_alterado      text        NOT NULL,   -- change_event.change_resource_name
  operacao              text        NOT NULL,   -- CREATE | UPDATE | REMOVE
  campaign_id           text,
  ad_group_id           text,
  cliente               text,                   -- client_type (WEB, API, EDITOR…)
  usuario               text,                   -- user_email
  campos_alterados      text[]      NOT NULL DEFAULT '{}',
  antes                 jsonb,
  depois                jsonb,
  execucao_id           uuid        NOT NULL
                                    REFERENCES public.trafego_coleta_execucao (execucao_id)
                                    ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
  colhida_em            timestamptz NOT NULL,
  registrada_em         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT google_ads_mudanca_identidade CHECK (customer_id ~ '^[0-9]{6,12}$'),
  CONSTRAINT google_ads_mudanca_operacao CHECK (operacao IN ('CREATE', 'UPDATE', 'REMOVE', 'UNKNOWN')),
  CONSTRAINT google_ads_mudanca_evento_unico UNIQUE (customer_id, change_event_rn)
);
CREATE INDEX google_ads_mudanca_campanha_ix ON public.google_ads_mudanca (campaign_id, ocorrido_em DESC);
CREATE INDEX google_ads_mudanca_conta_ix ON public.google_ads_mudanca (customer_id, ocorrido_em DESC);
COMMENT ON TABLE public.google_ads_mudanca IS
  'Histórico de mudanças da conta (change_event; a API guarda só 30 dias). Append-only; o mesmo evento nunca entra duas vezes.';

-- ─────────────────────────────────────────────────────────── estado ──
CREATE TABLE public.google_ads_estado (
  estado_id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id           text        NOT NULL,
  entidade_tipo         text        NOT NULL,
  entidade_id           text        NOT NULL,
  campaign_id           text,
  status                text,
  primary_status        text,
  primary_status_reasons text[]     NOT NULL DEFAULT '{}',
  aprovacao             text,
  revisao               text,
  topicos_politica      jsonb       NOT NULL DEFAULT '[]'::jsonb,
  estado_hash           text        NOT NULL,
  observado_em          timestamptz NOT NULL,
  execucao_id           uuid        NOT NULL
                                    REFERENCES public.trafego_coleta_execucao (execucao_id)
                                    ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
  registrada_em         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT google_ads_estado_identidade CHECK (customer_id ~ '^[0-9]{6,12}$' AND btrim(entidade_id) <> ''),
  CONSTRAINT google_ads_estado_tipo CHECK (entidade_tipo IN
    ('campaign', 'ad_group', 'ad_group_ad', 'asset_group', 'asset_group_asset', 'keyword', 'campaign_asset')),
  CONSTRAINT google_ads_estado_hash CHECK (estado_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT google_ads_estado_topicos CHECK (jsonb_typeof(topicos_politica) = 'array')
);
CREATE INDEX google_ads_estado_entidade_ix
  ON public.google_ads_estado (customer_id, entidade_tipo, entidade_id, observado_em DESC);
COMMENT ON TABLE public.google_ads_estado IS
  'Status primário, motivos e política por entidade. Uma linha nova só quando o estado MUDA (estado_hash); a sequência é a linha do tempo da entrega.';

-- ─────────────────────────────────────────────────────── append-only ──
CREATE OR REPLACE FUNCTION public.google_ads_append_only()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
  RAISE EXCEPTION '% é append-only: % recusado', TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'check_violation';
END $$;
CREATE TRIGGER google_ads_mudanca_append_only BEFORE UPDATE OR DELETE ON public.google_ads_mudanca
  FOR EACH ROW EXECUTE FUNCTION public.google_ads_append_only();
CREATE TRIGGER google_ads_estado_append_only BEFORE UPDATE OR DELETE ON public.google_ads_estado
  FOR EACH ROW EXECUTE FUNCTION public.google_ads_append_only();

-- ─────────────────────────────────────────────────────── utilitários ──
CREATE OR REPLACE FUNCTION public.volc_sha256(texto text)
RETURNS text LANGUAGE sql IMMUTABLE STRICT SET search_path = pg_catalog AS $$
  SELECT encode(sha256(convert_to(texto, 'UTF8')), 'hex')
$$;

-- Domínio comparável entre o placement do Google ("site.com", "www.site.com",
-- "https://site.com/x") e a URL de placement do GAM.
CREATE OR REPLACE FUNCTION public.volc_dominio(entrada text)
RETURNS text LANGUAGE sql IMMUTABLE STRICT SET search_path = pg_catalog AS $$
  SELECT nullif(regexp_replace(regexp_replace(regexp_replace(lower(btrim(entrada)),
         '^[a-z]+://', ''), '^www\.', ''), '[/?#:].*$', ''), '')
$$;

-- Número da linha: só JSON number vale. String vira motivo de rejeição.
CREATE OR REPLACE FUNCTION public.volc_gads_num(linha jsonb, campo text, OUT valor numeric, OUT erro text)
LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog AS $$
BEGIN
  IF NOT (linha ? campo) OR jsonb_typeof(linha -> campo) = 'null' THEN
    valor := NULL;
  ELSIF jsonb_typeof(linha -> campo) = 'number' THEN
    valor := (linha ->> campo)::numeric;
  ELSE
    erro := campo || ' não é número (' || jsonb_typeof(linha -> campo) || ')';
  END IF;
END $$;

-- ──────────────────────────────────────────────────────────────── RPC ──
CREATE OR REPLACE FUNCTION public.volc_registrar_gads_fatos(documento jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_familia   text := documento ->> 'familia';
  v_chave     text := documento ->> 'chave_idempotencia';
  v_cid       text := documento ->> 'customer_id';
  v_origem    text := documento ->> 'origem_janela';
  v_ini       date;
  v_fim       date;
  v_api       text := documento ->> 'api_versao';
  v_linhas    jsonb := documento -> 'linhas';
  v_payload   text;
  v_exec_id   uuid := gen_random_uuid();
  v_exist     record;
  v_linha     jsonb;
  v_i         integer := 0;
  v_aceitas   integer := 0;
  v_preter    integer := 0;
  v_rejeit    integer := 0;
  v_rejeicoes jsonb := '[]'::jsonb;
  v_prec      smallint;
  v_erro      text;
  v_m         numeric[];
  v_n         record;
  v_campos    text[] := ARRAY['impressoes','cliques','interacoes','custo_micros',
                              'conversoes','todas_conversoes','valor_conversoes','valor_todas_conversoes'];
  v_c         text;
  v_dims      jsonb;
  v_hash      text;
  v_ok        boolean;
  v_resultado text;
  v_recibo    jsonb;
BEGIN
  IF current_setting('transaction_isolation') <> 'read committed' THEN
    RAISE EXCEPTION 'ISOLAMENTO_NAO_SUPORTADO_V17_01' USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF v_familia IS NULL OR v_familia NOT IN
     ('hora_dispositivo','url','geo','placement','termo','keyword','asset','mudanca','estado') THEN
    RAISE EXCEPTION 'FAMILIA_INVALIDA: %', coalesce(v_familia, '(nula)') USING ERRCODE = 'invalid_parameter_value';
  END IF;
  IF coalesce(btrim(v_chave), '') = '' OR v_cid !~ '^[0-9]{6,12}$'
     OR v_origem NOT IN ('D0','D-1','backfill') OR jsonb_typeof(v_linhas) IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'DOCUMENTO_INVALIDO: chave, customer_id, origem_janela e linhas[] são obrigatórios'
      USING ERRCODE = 'invalid_parameter_value';
  END IF;
  v_ini := (documento ->> 'janela_inicio')::date;
  v_fim := (documento ->> 'janela_fim')::date;
  IF v_ini IS NULL OR v_fim IS NULL OR v_fim < v_ini THEN
    RAISE EXCEPTION 'DOCUMENTO_INVALIDO: janela_inicio/janela_fim ausentes ou invertidas'
      USING ERRCODE = 'invalid_parameter_value';
  END IF;
  v_prec := CASE v_origem WHEN 'D0' THEN 1 WHEN 'D-1' THEN 2 ELSE 3 END;
  v_payload := volc_sha256(v_linhas::text);

  -- Idempotência com memória (mesmo namespace de lock da v12_04: 120405).
  PERFORM pg_advisory_xact_lock(120405, hashtext(v_chave));
  SELECT execucao_id, payload_sha256, resultado, linhas_aceitas, linhas_preteridas, linhas_rejeitadas
    INTO v_exist FROM trafego_coleta_execucao WHERE chave_idempotencia = v_chave;
  IF FOUND THEN
    IF v_exist.payload_sha256 = v_payload THEN
      RETURN jsonb_build_object('repetida', true, 'execucao_id', v_exist.execucao_id,
        'resultado', v_exist.resultado, 'aceitas', v_exist.linhas_aceitas,
        'preteridas', v_exist.linhas_preteridas, 'rejeitadas', v_exist.linhas_rejeitadas);
    END IF;
    RAISE EXCEPTION 'CHAVE_IDEMPOTENCIA_CONTEUDO_DIVERGENTE: %', v_chave USING ERRCODE = 'unique_violation';
  END IF;

  FOR v_linha IN SELECT * FROM jsonb_array_elements(v_linhas) LOOP
    v_i := v_i + 1;
    v_erro := NULL;
    BEGIN
      IF v_familia IN ('hora_dispositivo','url','geo','placement','termo','keyword','asset') THEN
        -- métricas: só número
        v_m := ARRAY[]::numeric[];
        FOREACH v_c IN ARRAY v_campos LOOP
          SELECT * INTO v_n FROM volc_gads_num(v_linha, v_c);
          IF v_n.erro IS NOT NULL THEN v_erro := v_n.erro; EXIT; END IF;
          v_m := v_m || v_n.valor;
        END LOOP;
        IF v_erro IS NULL AND ((v_linha ->> 'metric_date')::date < v_ini OR (v_linha ->> 'metric_date')::date > v_fim) THEN
          v_erro := 'metric_date fora da janela declarada';
        END IF;
        IF v_erro IS NULL THEN
          v_dims := jsonb_strip_nulls(jsonb_build_object(
            'hora', v_linha -> 'hora', 'dispositivo', v_linha -> 'dispositivo', 'rede', v_linha -> 'rede',
            'url', v_linha -> 'url', 'url_tipo', v_linha -> 'url_tipo',
            'geo_constant', v_linha -> 'geo_constant', 'local_tipo', v_linha -> 'local_tipo',
            'placement', v_linha -> 'placement', 'placement_view', v_linha -> 'placement_view',
            'ad_group_id', v_linha -> 'ad_group_id', 'termo', v_linha -> 'termo', 'termo_match', v_linha -> 'termo_match',
            'criterion_id', v_linha -> 'criterion_id',
            'asset_id', v_linha -> 'asset_id', 'asset_campo', v_linha -> 'asset_campo',
            'asset_contexto', v_linha -> 'asset_contexto', 'asset_contexto_id', v_linha -> 'asset_contexto_id'));
          v_hash := volc_sha256(v_familia || '|' || v_dims::text);
          INSERT INTO google_ads_fato_granular AS t (
            familia, customer_id, campaign_id, metric_date, dimensao_hash,
            hora, dispositivo, rede, fuso, url, url_tipo, geo_constant, geo_nivel, local_tipo,
            placement, placement_tipo, placement_view, placement_nome,
            ad_group_id, termo, termo_match, termo_status,
            criterion_id, keyword_texto, keyword_match, quality_score, qs_anuncio, qs_pagina, qs_ctr_previsto,
            asset_id, asset_campo, asset_contexto, asset_contexto_id, asset_rotulo,
            execucao_id, colhida_em, api_versao, currency_code, origem_janela, janela_fechada, precedencia,
            impressoes, cliques, interacoes, custo_micros,
            conversoes, todas_conversoes, valor_conversoes, valor_todas_conversoes, metricas_extras)
          VALUES (
            v_familia, v_cid, v_linha ->> 'campaign_id', (v_linha ->> 'metric_date')::date, v_hash,
            (v_linha ->> 'hora')::smallint, v_linha ->> 'dispositivo', v_linha ->> 'rede', v_linha ->> 'fuso',
            v_linha ->> 'url', v_linha ->> 'url_tipo', v_linha ->> 'geo_constant', v_linha ->> 'geo_nivel', v_linha ->> 'local_tipo',
            v_linha ->> 'placement', v_linha ->> 'placement_tipo', v_linha ->> 'placement_view', v_linha ->> 'placement_nome',
            v_linha ->> 'ad_group_id', v_linha ->> 'termo', v_linha ->> 'termo_match', v_linha ->> 'termo_status',
            v_linha ->> 'criterion_id', v_linha ->> 'keyword_texto', v_linha ->> 'keyword_match',
            (v_linha ->> 'quality_score')::smallint, v_linha ->> 'qs_anuncio', v_linha ->> 'qs_pagina', v_linha ->> 'qs_ctr_previsto',
            v_linha ->> 'asset_id', v_linha ->> 'asset_campo', v_linha ->> 'asset_contexto', v_linha ->> 'asset_contexto_id', v_linha ->> 'asset_rotulo',
            v_exec_id, (v_linha ->> 'colhida_em')::timestamptz, v_api, v_linha ->> 'currency_code',
            v_origem, v_origem <> 'D0', v_prec,
            v_m[1]::bigint, v_m[2]::bigint, v_m[3]::bigint, v_m[4]::bigint, v_m[5], v_m[6], v_m[7], v_m[8],
            coalesce(v_linha -> 'metricas_extras', '{}'::jsonb))
          ON CONFLICT (familia, customer_id, campaign_id, metric_date, dimensao_hash) DO UPDATE SET
            execucao_id = EXCLUDED.execucao_id, colhida_em = EXCLUDED.colhida_em, api_versao = EXCLUDED.api_versao,
            currency_code = EXCLUDED.currency_code, origem_janela = EXCLUDED.origem_janela,
            janela_fechada = EXCLUDED.janela_fechada, precedencia = EXCLUDED.precedencia,
            fuso = EXCLUDED.fuso, geo_nivel = EXCLUDED.geo_nivel, placement_tipo = EXCLUDED.placement_tipo,
            placement_nome = EXCLUDED.placement_nome, termo_status = EXCLUDED.termo_status,
            keyword_texto = EXCLUDED.keyword_texto, keyword_match = EXCLUDED.keyword_match,
            quality_score = EXCLUDED.quality_score, qs_anuncio = EXCLUDED.qs_anuncio,
            qs_pagina = EXCLUDED.qs_pagina, qs_ctr_previsto = EXCLUDED.qs_ctr_previsto,
            asset_rotulo = EXCLUDED.asset_rotulo,
            impressoes = EXCLUDED.impressoes, cliques = EXCLUDED.cliques, interacoes = EXCLUDED.interacoes,
            custo_micros = EXCLUDED.custo_micros, conversoes = EXCLUDED.conversoes,
            todas_conversoes = EXCLUDED.todas_conversoes, valor_conversoes = EXCLUDED.valor_conversoes,
            valor_todas_conversoes = EXCLUDED.valor_todas_conversoes,
            metricas_extras = EXCLUDED.metricas_extras, atualizada_em = now()
          WHERE EXCLUDED.precedencia > t.precedencia
             OR (EXCLUDED.precedencia = t.precedencia AND EXCLUDED.colhida_em > t.colhida_em)
          RETURNING true INTO v_ok;
          IF FOUND THEN v_aceitas := v_aceitas + 1; ELSE v_preter := v_preter + 1; END IF;
        END IF;

      ELSIF v_familia = 'mudanca' THEN
        INSERT INTO google_ads_mudanca (customer_id, change_event_rn, ocorrido_em, tipo_recurso,
          recurso_alterado, operacao, campaign_id, ad_group_id, cliente, usuario, campos_alterados,
          antes, depois, execucao_id, colhida_em)
        VALUES (v_cid, v_linha ->> 'change_event_rn', (v_linha ->> 'ocorrido_em')::timestamptz,
          v_linha ->> 'tipo_recurso', v_linha ->> 'recurso_alterado', coalesce(v_linha ->> 'operacao', 'UNKNOWN'),
          v_linha ->> 'campaign_id', v_linha ->> 'ad_group_id', v_linha ->> 'cliente', v_linha ->> 'usuario',
          coalesce(ARRAY(SELECT jsonb_array_elements_text(v_linha -> 'campos_alterados')), '{}'),
          v_linha -> 'antes', v_linha -> 'depois', v_exec_id, (v_linha ->> 'colhida_em')::timestamptz)
        ON CONFLICT (customer_id, change_event_rn) DO NOTHING
        RETURNING true INTO v_ok;
        IF FOUND THEN v_aceitas := v_aceitas + 1; ELSE v_preter := v_preter + 1; END IF;

      ELSE  -- estado: só entra se mudou
        v_hash := volc_sha256(jsonb_build_object(
          'status', v_linha -> 'status', 'primary_status', v_linha -> 'primary_status',
          'reasons', coalesce(v_linha -> 'primary_status_reasons', '[]'::jsonb),
          'aprovacao', v_linha -> 'aprovacao', 'revisao', v_linha -> 'revisao',
          'topicos', coalesce(v_linha -> 'topicos_politica', '[]'::jsonb))::text);
        IF EXISTS (
          SELECT 1 FROM (
            SELECT estado_hash FROM google_ads_estado
             WHERE customer_id = v_cid AND entidade_tipo = v_linha ->> 'entidade_tipo'
               AND entidade_id = v_linha ->> 'entidade_id'
             ORDER BY observado_em DESC LIMIT 1) u
          WHERE u.estado_hash = v_hash) THEN
          v_preter := v_preter + 1;
        ELSE
          INSERT INTO google_ads_estado (customer_id, entidade_tipo, entidade_id, campaign_id, status,
            primary_status, primary_status_reasons, aprovacao, revisao, topicos_politica, estado_hash,
            observado_em, execucao_id)
          VALUES (v_cid, v_linha ->> 'entidade_tipo', v_linha ->> 'entidade_id', v_linha ->> 'campaign_id',
            v_linha ->> 'status', v_linha ->> 'primary_status',
            coalesce(ARRAY(SELECT jsonb_array_elements_text(v_linha -> 'primary_status_reasons')), '{}'),
            v_linha ->> 'aprovacao', v_linha ->> 'revisao', coalesce(v_linha -> 'topicos_politica', '[]'::jsonb),
            v_hash, (v_linha ->> 'observado_em')::timestamptz, v_exec_id);
          v_aceitas := v_aceitas + 1;
        END IF;
      END IF;
    EXCEPTION
      WHEN check_violation OR not_null_violation OR invalid_text_representation
        OR invalid_datetime_format OR datetime_field_overflow OR numeric_value_out_of_range THEN
        v_erro := SQLSTATE || ' ' || left(SQLERRM, 200);
    END;
    IF v_erro IS NOT NULL THEN
      v_rejeit := v_rejeit + 1;
      v_rejeicoes := v_rejeicoes || jsonb_build_object('linha', v_i, 'motivo', v_erro);
    END IF;
  END LOOP;

  v_resultado := CASE WHEN v_rejeit = 0 THEN 'ok'
                      WHEN v_aceitas = 0 THEN 'falhou'
                      ELSE 'parcial' END;

  -- Recibo DEPOIS dos fatos (FK deferida): fato sem recibo não sobrevive ao COMMIT.
  INSERT INTO trafego_coleta_execucao (
    execucao_id, chave_idempotencia, execucao_chave, fonte, job, disparo, api_versao,
    contrato_versao, contrato_sha256, tipo_lote, lote_ordinal, origem_janela, janela_inicio, janela_fim,
    iniciada_em, encerrada_em, duracao_ms, batimento_em, resultado, motivo, escopo,
    contas_tentadas, contas_aceitas, contas_recusadas,
    linhas_lidas, linhas_aceitas, linhas_preteridas, linhas_rejeitadas, rejeicoes,
    projecao_estado, projecao_linhas, payload_sha256)
  VALUES (
    v_exec_id, v_chave, coalesce(documento ->> 'execucao_chave', v_chave),
    coalesce(documento ->> 'fonte', 'python_oneshot'), coalesce(documento ->> 'job', 'gads_' || v_familia),
    coalesce(documento ->> 'disparo', 'agenda'), v_api,
    documento ->> 'contrato_versao', documento ->> 'contrato_sha256',
    'contas', coalesce((documento ->> 'lote_ordinal')::integer, 1), v_origem, v_ini, v_fim,
    (documento ->> 'iniciada_em')::timestamptz, (documento ->> 'encerrada_em')::timestamptz,
    greatest(0, (extract(epoch FROM ((documento ->> 'encerrada_em')::timestamptz
                                     - (documento ->> 'iniciada_em')::timestamptz)) * 1000)::integer),
    coalesce((documento ->> 'batimento_em')::timestamptz, now()),
    v_resultado,
    CASE WHEN v_resultado = 'ok' THEN NULL ELSE v_rejeit || ' linha(s) rejeitada(s)' END,
    v_familia,
    ARRAY[v_cid], CASE WHEN v_aceitas + v_preter > 0 THEN ARRAY[v_cid] ELSE '{}'::text[] END, '[]'::jsonb,
    v_i, v_aceitas, v_preter, v_rejeit, v_rejeicoes,
    'nao_solicitada', 0, v_payload);

  v_recibo := jsonb_build_object('repetida', false, 'execucao_id', v_exec_id, 'familia', v_familia,
    'resultado', v_resultado, 'lidas', v_i, 'aceitas', v_aceitas, 'preteridas', v_preter,
    'rejeitadas', v_rejeit, 'rejeicoes', v_rejeicoes);
  RETURN v_recibo;
END $$;

COMMENT ON FUNCTION public.volc_registrar_gads_fatos(jsonb) IS
  'Única porta de escrita dos fatos granulares, mudanças e estados Google Ads. Idempotência com memória, precedência D0<D-1<backfill, número em string rejeitado, recibo em trafego_coleta_execucao.';

-- ─────────────────────────────────────────────── views de correlação ──
-- Campanha-dia sem segmentação (segmentos '{}' é a linha que a coleta D0/D-1
-- grava; filtrar por ela é o que impede somar em dobro).
CREATE VIEW public.vw_gads_campanha_dia WITH (security_invoker = true) AS
SELECT g.customer_id, g.campaign_id, g.metric_date, g.volc_campaign_id, g.campaign_name,
       g.advertising_channel_type, g.currency_code, g.origem_janela, g.janela_fechada,
       g.impressoes, g.cliques, g.custo_micros, g.conversoes, g.valor_conversoes,
       nullif(g.metricas_extras ->> 'invalid_clicks', '')::bigint AS cliques_invalidos,
       nullif(g.metricas_extras ->> 'invalid_click_rate', '')::numeric AS taxa_cliques_invalidos,
       g.search_impression_share, g.search_budget_lost_impression_share, g.search_rank_lost_impression_share
  FROM public.google_ads_campanha_dia g
 WHERE g.segmentos = '{}'::jsonb;

-- Arbitragem por campanha-dia: custo do Google × receita GAM + JoinAds,
-- casadas por utm_campaign_value = campaign_id. Receitas estão em BRL
-- (revenue_converted); se a conta não é BRL, lucro e ROAS ficam NULL em vez de
-- comparar moedas diferentes.
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

-- Arbitragem por placement-dia (Display / Demand Gen): custo do Google por
-- domínio × receita GAM por placement. A view `detail` é a de URL/domínio.
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

-- Arbitragem por campanha-hora: custo (somado sobre dispositivo e rede) ×
-- receita GAM horária. A hora do Google está no fuso da conta; `hourly_stats`
-- guarda instante (timestamptz), então a junção converte.
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

-- ─────────────────────────────────────────────────────────── segurança ──
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['google_ads_fato_granular','google_ads_fato_granular_hora_dispositivo',
    'google_ads_fato_granular_url','google_ads_fato_granular_geo','google_ads_fato_granular_placement',
    'google_ads_fato_granular_termo','google_ads_fato_granular_keyword','google_ads_fato_granular_asset',
    'google_ads_mudanca','google_ads_estado'] LOOP
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC, anon, authenticated', t);
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('GRANT SELECT ON public.%I TO service_role', t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['vw_gads_campanha_dia','vw_gads_arbitragem_campanha_dia',
    'vw_gads_arbitragem_placement_dia','vw_gads_arbitragem_hora'] LOOP
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC, anon, authenticated', t);
    EXECUTE format('GRANT SELECT ON public.%I TO service_role', t);
  END LOOP;
END $$;

REVOKE ALL ON FUNCTION public.volc_registrar_gads_fatos(jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.volc_registrar_gads_fatos(jsonb) TO service_role;
REVOKE ALL ON FUNCTION public.volc_gads_num(jsonb, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.google_ads_append_only() FROM PUBLIC, anon, authenticated;

NOTIFY pgrst, 'reload schema';
COMMIT;
