-- v12_01 — observabilidade persistente da inteligencia oficial do Google Ads
--
-- Autoridade: database.agenciavolc.com.br.
-- Esta migration NAO aplica recomendacao, NAO altera campanha e NAO decide.
-- Ela registra, de forma append-only, o que cada chamada leu — inclusive vazio,
-- ausencia, nao aplicabilidade e falha. Zero medido continua sendo zero.

BEGIN;

DO $$
BEGIN
  IF to_regclass('public.trafego_campanha') IS NULL THEN
    RAISE EXCEPTION USING
      ERRCODE = '55000',
      MESSAGE = 'v12_01 exige v9_01: public.trafego_campanha nao existe';
  END IF;
  IF to_regclass('public.trafego_google_inteligencia_coleta') IS NOT NULL THEN
    RAISE EXCEPTION USING
      ERRCODE = '42P07',
      MESSAGE = 'v12_01 ja aplicada: public.trafego_google_inteligencia_coleta existe';
  END IF;
END $$;

CREATE TABLE public.trafego_google_inteligencia_coleta (
  coleta_id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chave_idempotencia    text NOT NULL UNIQUE,
  plataforma            text NOT NULL DEFAULT 'GOOGLE_ADS',
  tipo_sinal            text NOT NULL,
  estado                text NOT NULL,
  customer_id           text NOT NULL,
  login_customer_id     text NOT NULL,
  volc_campaign_id      text REFERENCES public.trafego_campanha (volc_campaign_id)
                              ON DELETE RESTRICT,
  campaign_id           text,
  janela_inicio         date,
  janela_fim            date,
  competencia           date NOT NULL,
  coletada_em           timestamptz NOT NULL,
  api_versao            text NOT NULL,
  coletor_versao        integer NOT NULL,
  quantidade            integer,
  request_ids           text[] NOT NULL DEFAULT '{}'::text[],
  payload               jsonb NOT NULL DEFAULT '{}'::jsonb,
  payload_sha256        text NOT NULL,
  erro_codigo           text,
  erro_classe           text,
  erro_detalhe          text,

  CONSTRAINT trafego_google_coleta_chave_valida
    CHECK (btrim(chave_idempotencia) <> ''),
  CONSTRAINT trafego_google_coleta_plataforma
    CHECK (plataforma = 'GOOGLE_ADS'),
  CONSTRAINT trafego_google_coleta_tipo
    CHECK (tipo_sinal IN (
      'DIAGNOSTICO_ENTREGA',
      'RECOMENDACOES_ARMAZENADAS',
      'RECOMENDACOES_GERADAS',
      'SIMULACOES_CAMPANHA',
      'FORECAST_KEYWORDS',
      'EXPERIMENTOS'
    )),
  CONSTRAINT trafego_google_coleta_estado
    CHECK (estado IN (
      'com_dados', 'vazio_confirmado', 'parcial',
      'inelegivel', 'nao_suportado', 'falhou'
    )),
  CONSTRAINT trafego_google_coleta_contas
    CHECK (customer_id ~ '^[0-9]{6,12}$' AND login_customer_id ~ '^[0-9]{6,12}$'),
  CONSTRAINT trafego_google_coleta_campanha_par
    CHECK ((volc_campaign_id IS NULL) = (campaign_id IS NULL)),
  CONSTRAINT trafego_google_coleta_campaign_id
    CHECK (campaign_id IS NULL OR campaign_id ~ '^[0-9]+$'),
  CONSTRAINT trafego_google_coleta_janela
    CHECK ((janela_inicio IS NULL AND janela_fim IS NULL)
           OR (janela_inicio IS NOT NULL AND janela_fim >= janela_inicio)),
  CONSTRAINT trafego_google_coleta_quantidade_semantica
    CHECK (
      (estado = 'com_dados' AND quantidade > 0)
      OR (estado = 'vazio_confirmado' AND quantidade = 0)
      OR (estado = 'parcial' AND quantidade >= 0)
      OR (estado IN ('inelegivel', 'nao_suportado', 'falhou') AND quantidade IS NULL)
    ),
  CONSTRAINT trafego_google_coleta_erro_semantica
    CHECK (
      (estado = 'falhou'
       AND btrim(coalesce(erro_codigo, '')) <> ''
       AND btrim(coalesce(erro_classe, '')) <> '')
      OR (estado <> 'falhou'
          AND erro_codigo IS NULL AND erro_classe IS NULL AND erro_detalhe IS NULL)
    ),
  CONSTRAINT trafego_google_coleta_payload_objeto
    CHECK (jsonb_typeof(payload) = 'object'),
  CONSTRAINT trafego_google_coleta_hash
    CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT trafego_google_coleta_versao
    CHECK (btrim(api_versao) <> '' AND coletor_versao > 0)
);

CREATE TABLE public.trafego_google_inteligencia_item (
  item_id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  coleta_id              uuid NOT NULL REFERENCES public.trafego_google_inteligencia_coleta (coleta_id)
                               ON DELETE RESTRICT,
  ordinal                integer NOT NULL,
  tipo_item              text NOT NULL,
  recurso_externo        text,
  payload                jsonb NOT NULL,

  CONSTRAINT trafego_google_item_ordinal CHECK (ordinal >= 0),
  CONSTRAINT trafego_google_item_tipo CHECK (btrim(tipo_item) <> ''),
  CONSTRAINT trafego_google_item_payload CHECK (jsonb_typeof(payload) = 'object'),
  CONSTRAINT trafego_google_item_unico UNIQUE (coleta_id, ordinal)
);

CREATE TABLE public.trafego_google_inteligencia_metrica (
  metrica_id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  coleta_id              uuid NOT NULL REFERENCES public.trafego_google_inteligencia_coleta (coleta_id)
                               ON DELETE RESTRICT,
  recurso_tipo           text NOT NULL,
  recurso_externo        text NOT NULL,
  nome                   text NOT NULL,
  estado_valor           text NOT NULL,
  valor_numerico         numeric,
  valor_texto            text,
  unidade                text,
  moeda                  text,

  CONSTRAINT trafego_google_metrica_identidade
    CHECK (btrim(recurso_tipo) <> '' AND btrim(recurso_externo) <> '' AND btrim(nome) <> ''),
  CONSTRAINT trafego_google_metrica_estado
    CHECK (estado_valor IN ('medido', 'ausente', 'nao_aplicavel', 'falhou')),
  CONSTRAINT trafego_google_metrica_valor
    CHECK (
      (estado_valor = 'medido'
       AND ((valor_numerico IS NOT NULL AND valor_texto IS NULL)
            OR (valor_numerico IS NULL AND valor_texto IS NOT NULL)))
      OR (estado_valor <> 'medido' AND valor_numerico IS NULL AND valor_texto IS NULL)
    ),
  CONSTRAINT trafego_google_metrica_moeda CHECK (moeda IS NULL OR moeda ~ '^[A-Z]{3}$'),
  CONSTRAINT trafego_google_metrica_unica
    UNIQUE (coleta_id, recurso_tipo, recurso_externo, nome)
);

CREATE INDEX trafego_google_coleta_conta_ix
  ON public.trafego_google_inteligencia_coleta
  (customer_id, tipo_sinal, coletada_em DESC);
CREATE INDEX trafego_google_coleta_campanha_ix
  ON public.trafego_google_inteligencia_coleta
  (volc_campaign_id, tipo_sinal, coletada_em DESC)
  WHERE volc_campaign_id IS NOT NULL;
CREATE INDEX trafego_google_coleta_estado_ix
  ON public.trafego_google_inteligencia_coleta
  (estado, coletada_em DESC);
CREATE INDEX trafego_google_item_coleta_ix
  ON public.trafego_google_inteligencia_item (coleta_id, tipo_item);
CREATE INDEX trafego_google_metrica_consulta_ix
  ON public.trafego_google_inteligencia_metrica
  (recurso_tipo, recurso_externo, nome, coleta_id);

COMMENT ON TABLE public.trafego_google_inteligencia_coleta IS
  'Envelope append-only de cada consulta de inteligencia Google Ads. vazio_confirmado e diferente de falhou; quantidade nula nunca vira zero.';
COMMENT ON COLUMN public.trafego_google_inteligencia_coleta.estado IS
  'com_dados, vazio_confirmado, parcial, inelegivel, nao_suportado ou falhou.';
COMMENT ON TABLE public.trafego_google_inteligencia_metrica IS
  'Valor tipado: medido pode ser exatamente zero; ausente, nao_aplicavel e falhou nao carregam valor.';

CREATE OR REPLACE FUNCTION public.trafego_google_inteligencia_append_only()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
  RAISE EXCEPTION USING
    ERRCODE = '55000',
    MESSAGE = format('%s e append-only: UPDATE e DELETE recusados', TG_TABLE_NAME);
END;
$$;

CREATE TRIGGER trafego_google_coleta_append_only
  BEFORE UPDATE OR DELETE ON public.trafego_google_inteligencia_coleta
  FOR EACH ROW EXECUTE FUNCTION public.trafego_google_inteligencia_append_only();
CREATE TRIGGER trafego_google_item_append_only
  BEFORE UPDATE OR DELETE ON public.trafego_google_inteligencia_item
  FOR EACH ROW EXECUTE FUNCTION public.trafego_google_inteligencia_append_only();
CREATE TRIGGER trafego_google_metrica_append_only
  BEFORE UPDATE OR DELETE ON public.trafego_google_inteligencia_metrica
  FOR EACH ROW EXECUTE FUNCTION public.trafego_google_inteligencia_append_only();

CREATE OR REPLACE FUNCTION public.volc_registrar_google_inteligencia(documento jsonb)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  cid uuid;
  existente uuid;
  it jsonb;
  mt jsonb;
BEGIN
  IF jsonb_typeof(documento) <> 'object' THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='documento precisa ser objeto JSON';
  END IF;

  SELECT coleta_id INTO existente
    FROM public.trafego_google_inteligencia_coleta
   WHERE chave_idempotencia = documento->>'chave_idempotencia';
  IF existente IS NOT NULL THEN
    RETURN existente;
  END IF;

  INSERT INTO public.trafego_google_inteligencia_coleta (
    chave_idempotencia, tipo_sinal, estado, customer_id, login_customer_id,
    volc_campaign_id, campaign_id, janela_inicio, janela_fim, competencia,
    coletada_em, api_versao, coletor_versao, quantidade, request_ids,
    payload, payload_sha256, erro_codigo, erro_classe, erro_detalhe
  ) VALUES (
    documento->>'chave_idempotencia', documento->>'tipo_sinal', documento->>'estado',
    documento->>'customer_id', documento->>'login_customer_id',
    nullif(documento->>'volc_campaign_id',''), nullif(documento->>'campaign_id',''),
    nullif(documento->>'janela_inicio','')::date, nullif(documento->>'janela_fim','')::date,
    (documento->>'competencia')::date, (documento->>'coletada_em')::timestamptz,
    documento->>'api_versao', (documento->>'coletor_versao')::integer,
    (documento->>'quantidade')::integer,
    ARRAY(SELECT jsonb_array_elements_text(coalesce(documento->'request_ids','[]'::jsonb))),
    coalesce(documento->'payload','{}'::jsonb), documento->>'payload_sha256',
    nullif(documento->>'erro_codigo',''), nullif(documento->>'erro_classe',''),
    nullif(documento->>'erro_detalhe','')
  ) RETURNING coleta_id INTO cid;

  FOR it IN SELECT value FROM jsonb_array_elements(coalesce(documento->'itens','[]'::jsonb)) LOOP
    INSERT INTO public.trafego_google_inteligencia_item
      (coleta_id, ordinal, tipo_item, recurso_externo, payload)
    VALUES
      (cid, (it->>'ordinal')::integer, it->>'tipo_item',
       nullif(it->>'recurso_externo',''), it->'payload');
  END LOOP;

  FOR mt IN SELECT value FROM jsonb_array_elements(coalesce(documento->'metricas','[]'::jsonb)) LOOP
    INSERT INTO public.trafego_google_inteligencia_metrica
      (coleta_id, recurso_tipo, recurso_externo, nome, estado_valor,
       valor_numerico, valor_texto, unidade, moeda)
    VALUES
      (cid, mt->>'recurso_tipo', mt->>'recurso_externo', mt->>'nome', mt->>'estado_valor',
       nullif(mt->>'valor_numerico','')::numeric, nullif(mt->>'valor_texto',''),
       nullif(mt->>'unidade',''), nullif(mt->>'moeda',''));
  END LOOP;

  RETURN cid;
EXCEPTION
  WHEN unique_violation THEN
    SELECT coleta_id INTO existente
      FROM public.trafego_google_inteligencia_coleta
     WHERE chave_idempotencia = documento->>'chave_idempotencia';
    IF existente IS NULL THEN RAISE; END IF;
    RETURN existente;
END;
$$;

ALTER TABLE public.trafego_google_inteligencia_coleta ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_google_inteligencia_coleta FORCE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_google_inteligencia_item ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_google_inteligencia_item FORCE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_google_inteligencia_metrica ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trafego_google_inteligencia_metrica FORCE ROW LEVEL SECURITY;

REVOKE ALL ON public.trafego_google_inteligencia_coleta FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.trafego_google_inteligencia_item FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.trafego_google_inteligencia_metrica FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.trafego_google_inteligencia_coleta FROM service_role;
REVOKE ALL ON public.trafego_google_inteligencia_item FROM service_role;
REVOKE ALL ON public.trafego_google_inteligencia_metrica FROM service_role;
REVOKE ALL ON FUNCTION public.volc_registrar_google_inteligencia(jsonb) FROM PUBLIC, anon, authenticated;

GRANT SELECT ON public.trafego_google_inteligencia_coleta TO service_role;
GRANT SELECT ON public.trafego_google_inteligencia_item TO service_role;
GRANT SELECT ON public.trafego_google_inteligencia_metrica TO service_role;
GRANT EXECUTE ON FUNCTION public.volc_registrar_google_inteligencia(jsonb) TO service_role;

NOTIFY pgrst, 'reload schema';
COMMIT;
