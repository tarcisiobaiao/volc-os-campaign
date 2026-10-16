-- =============================================================================
-- dil_obs_0002 — ROLLBACK do particionamento: volta à tabela única de 0001, com os dados
-- MIGRATION CANDIDATA OPCIONAL. NÃO APLICADA EM NENHUM BANCO OPERACIONAL.
-- Testada só em PostgreSQL 16 descartável (tests/data-intelligence/fundacao/test_schema_pg_particionamento.py).
-- Pré-requisito: dil_obs_0001 aplicada. Trechos de DDL copiados de dil_obs_0001 (o teste prova que o
-- catálogo depois do down é idêntico ao de 0001 e que o as_of não muda em nenhum sentido).
-- =============================================================================

BEGIN;
SET LOCAL ROLE dil_obs_dono;

LOCK TABLE dil_obs.observacao IN ACCESS EXCLUSIVE MODE;
DROP VIEW dil_obs.observacao_latest;
DROP FUNCTION dil_obs.observacao_as_of(timestamptz);
ALTER TABLE dil_obs.observacao RENAME TO observacao_part;
ALTER INDEX dil_obs.observacao_pkey RENAME TO observacao_pkey_part;
ALTER INDEX dil_obs.uq_obs_chave_idempotencia RENAME TO uq_obs_chave_idempotencia_part;
ALTER INDEX dil_obs.uq_obs_versao RENAME TO uq_obs_versao_part;
ALTER INDEX dil_obs.ix_obs_chave_base RENAME TO ix_obs_chave_base_part;
ALTER INDEX dil_obs.ix_obs_entidade RENAME TO ix_obs_entidade_part;
ALTER INDEX dil_obs.ix_obs_lote RENAME TO ix_obs_lote_part;
ALTER INDEX dil_obs.ix_obs_run RENAME TO ix_obs_run_part;

CREATE TABLE dil_obs.observacao (
  observacao_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  chave_idempotencia  text NOT NULL,
  chave_base          text NOT NULL,
  chave_natural       text NOT NULL,
  tipo_registro       text NOT NULL,
  fonte               text NOT NULL,
  conta               text NOT NULL,
  entidade_tipo       text NOT NULL,
  entidade_id         text NOT NULL,
  grao                text[] NOT NULL,
  dimensoes           jsonb NOT NULL,
  metrica             text NOT NULL,
  value_kind          text,
  valor               bigint,          -- micros ou contagem. SEM DEFAULT: null != 0
  unidade             text NOT NULL,
  moeda               char(3),
  janela_inicio       timestamptz NOT NULL,
  janela_fim          timestamptz NOT NULL,
  timezone            text NOT NULL,
  observed_at         timestamptz NOT NULL,
  source_updated_at   timestamptz,
  available_at        timestamptz NOT NULL,
  ingested_at         timestamptz NOT NULL,
  run_id              text NOT NULL REFERENCES dil_obs.run_coleta (run_id),
  request_id          text,
  lote_id             text NOT NULL REFERENCES dil_obs.lote (lote_id),
  payload_sha256      text NOT NULL REFERENCES dil_obs.payload_bruto (sha256),
  payload_ref         text NOT NULL,
  schema_version      text NOT NULL,
  coletor_nome        text NOT NULL,
  coletor_versao      text NOT NULL,
  status              text NOT NULL,
  motivo              text,
  cobertura_ppm       integer,

  CONSTRAINT uq_obs_chave_idempotencia UNIQUE (chave_idempotencia),
  CONSTRAINT ck_obs_chaves CHECK (
    chave_idempotencia ~ '^[0-9a-f]{64}$' AND chave_base ~ '^[0-9a-f]{64}$' AND chave_natural ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_obs_tipo_registro CHECK (
    (tipo_registro = 'leitura' AND chave_idempotencia = chave_base)
    OR (tipo_registro = 'reafirmacao' AND chave_idempotencia <> chave_base)),
  CONSTRAINT ck_obs_fonte CHECK (fonte ~ '^[a-z][a-z0-9_]*$'),
  CONSTRAINT ck_obs_identidade CHECK (
        conta <> '' AND conta = btrim(conta) AND conta !~ '[\x01-\x1f\x7f]'
    AND entidade_tipo <> '' AND entidade_tipo = btrim(entidade_tipo) AND entidade_tipo !~ '[\x01-\x1f\x7f]'
    AND entidade_id <> '' AND entidade_id = btrim(entidade_id) AND entidade_id !~ '[\x01-\x1f\x7f]'
    AND timezone <> '' AND schema_version <> '' AND coletor_nome <> '' AND coletor_versao <> ''),
  CONSTRAINT ck_obs_grao CHECK (
    cardinality(grao) >= 1
    AND grao <@ ARRAY['account', 'campaign', 'ad_group', 'keyword', 'funnel', 'url', 'ad_unit', 'country',
                      'device', 'day', 'hour', 'session', 'click', 'cell']::text[]),
  CONSTRAINT ck_obs_dimensoes CHECK (jsonb_typeof(dimensoes) = 'array'),
  CONSTRAINT ck_obs_metrica CHECK (
    metrica IN ('cost', 'revenue', 'clicks', 'impressions', 'sessions', 'conversions', 'signal')),
  CONSTRAINT ck_obs_value_kind_vocab CHECK (value_kind IS NULL OR value_kind IN (
    'observed_auction_signal', 'estimated_revenue', 'reported_revenue', 'reconciled_revenue', 'business_value')),
  CONSTRAINT ck_obs_unidade CHECK (unidade IN ('micros', 'contagem')),
  CONSTRAINT ck_obs_moeda CHECK (moeda IS NULL OR moeda ~ '^[A-Z]{3}$'),
  CONSTRAINT ck_obs_status CHECK (status IN (
    'observed', 'zero_confirmed', 'missing', 'late', 'unavailable', 'unsupported', 'invalid', 'partial')),

  -- relógios: janela_inicio < janela_fim; janela_inicio <= observed_at <= available_at <= ingested_at;
  -- source_updated_at <= available_at
  CONSTRAINT ck_obs_janela CHECK (janela_inicio < janela_fim),
  CONSTRAINT ck_obs_relogios CHECK (
    observed_at >= janela_inicio AND available_at >= observed_at AND ingested_at >= available_at
    AND (source_updated_at IS NULL OR source_updated_at <= available_at)),

  -- status × valor (null != 0). Atenção: CHECK com NULL passa; por isso os IS NOT NULL explícitos.
  CONSTRAINT ck_obs_motivo CHECK (
    status IN ('observed', 'zero_confirmed') OR (motivo IS NOT NULL AND btrim(motivo) <> '')),
  CONSTRAINT ck_obs_observed CHECK (status <> 'observed' OR (valor IS NOT NULL AND valor <> 0)),
  CONSTRAINT ck_obs_zero_confirmed CHECK (status <> 'zero_confirmed' OR (valor IS NOT NULL AND valor = 0)),
  CONSTRAINT ck_obs_sem_valor CHECK (
    status NOT IN ('missing', 'late', 'unavailable', 'unsupported', 'invalid') OR valor IS NULL),
  CONSTRAINT ck_obs_partial CHECK (
    (status = 'partial' AND cobertura_ppm IS NOT NULL AND cobertura_ppm BETWEEN 1 AND 999999)
    OR (status <> 'partial' AND cobertura_ppm IS NULL)),
  CONSTRAINT ck_obs_janela_fechada CHECK (status NOT IN ('observed', 'zero_confirmed') OR observed_at >= janela_fim),

  -- unidade × métrica × moeda × value_kind
  CONSTRAINT ck_obs_unidade_metrica CHECK (
    (metrica IN ('cost', 'revenue') AND unidade = 'micros')
    OR (metrica IN ('clicks', 'impressions', 'sessions', 'conversions') AND unidade = 'contagem')
    OR metrica = 'signal'),
  CONSTRAINT ck_obs_contagem CHECK (unidade <> 'contagem' OR (moeda IS NULL AND (valor IS NULL OR valor >= 0))),
  CONSTRAINT ck_obs_micros_moeda CHECK (unidade <> 'micros' OR valor IS NULL OR moeda IS NOT NULL),
  CONSTRAINT ck_obs_value_kind_regra CHECK (
    (metrica = 'revenue' AND value_kind IS NOT NULL AND value_kind <> 'observed_auction_signal')
    OR (metrica = 'signal' AND unidade = 'micros' AND value_kind IS NOT DISTINCT FROM 'observed_auction_signal')
    OR (metrica = 'signal' AND unidade = 'contagem' AND value_kind IS NULL)
    OR (metrica NOT IN ('revenue', 'signal') AND value_kind IS NULL)),

  -- referência imutável = endereçada pelo conteúdo
  CONSTRAINT ck_obs_payload CHECK (payload_sha256 ~ '^[0-9a-f]{64}$' AND strpos(payload_ref, payload_sha256) > 0)
);
COMMENT ON TABLE dil_obs.observacao IS
  'Observação canônica append-only. Cada linha é uma versão de conhecimento de um fato '
  '(chave_natural). Restatement = linha nova; nunca UPDATE.';
COMMENT ON COLUMN dil_obs.observacao.ingested_at IS 'Relógio do banco (now() da transação), nunca do escritor.';
COMMENT ON COLUMN dil_obs.observacao.available_at IS 'Relógio do replay as_of: quando o VOLC passou a ter o payload. Nunca retroativo.';

-- uma versão por (fato, instante de conhecimento): torna o as_of determinístico e serve o DISTINCT ON
CREATE UNIQUE INDEX uq_obs_versao ON dil_obs.observacao (chave_natural, available_at DESC);
CREATE INDEX ix_obs_chave_base ON dil_obs.observacao (chave_base);
CREATE INDEX ix_obs_entidade ON dil_obs.observacao (fonte, conta, entidade_tipo, entidade_id, janela_inicio);
CREATE INDEX ix_obs_lote ON dil_obs.observacao (lote_id);
CREATE INDEX ix_obs_run ON dil_obs.observacao (run_id);

CREATE TRIGGER tg_obs_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON dil_obs.observacao
  FOR EACH STATEMENT EXECUTE FUNCTION dil_obs._rejeitar_mutacao();

ALTER TABLE dil_obs.observacao ENABLE ROW LEVEL SECURITY;
ALTER TABLE dil_obs.observacao FORCE ROW LEVEL SECURITY;
CREATE POLICY pl_obs_leitura ON dil_obs.observacao FOR SELECT TO dil_obs_leitor, dil_obs_dono USING (true);
CREATE POLICY pl_obs_insercao ON dil_obs.observacao FOR INSERT TO dil_obs_dono WITH CHECK (true);

INSERT INTO dil_obs.observacao OVERRIDING SYSTEM VALUE SELECT * FROM dil_obs.observacao_part;
SELECT pg_catalog.setval(pg_catalog.pg_get_serial_sequence('dil_obs.observacao', 'observacao_id'),
                         coalesce((SELECT max(observacao_id) FROM dil_obs.observacao), 0) + 1, false);
DROP TABLE dil_obs.observacao_part;  -- leva as partições e a sequência explícita
DROP FUNCTION dil_obs.garantir_particao_mensal(date);

CREATE FUNCTION dil_obs.observacao_as_of(t timestamptz) RETURNS SETOF dil_obs.observacao
LANGUAGE sql STABLE STRICT SECURITY INVOKER SET search_path = ''
AS $$
  SELECT DISTINCT ON (o.chave_natural) o.*
    FROM dil_obs.observacao AS o
   WHERE o.available_at <= t
   ORDER BY o.chave_natural, o.available_at DESC
$$;
COMMENT ON FUNCTION dil_obs.observacao_as_of(timestamptz) IS
  'Estado conhecido em t: por chave_natural, a versão de maior available_at <= t. Status preservado.';

CREATE VIEW dil_obs.observacao_latest WITH (security_invoker = true) AS
  SELECT * FROM dil_obs.observacao_as_of(now());
COMMENT ON VIEW dil_obs.observacao_latest IS 'latest = as_of(now()). Derivada do histórico; não o substitui.';

REVOKE ALL ON dil_obs.observacao, dil_obs.observacao_latest FROM PUBLIC;
REVOKE ALL ON FUNCTION dil_obs.observacao_as_of(timestamptz) FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA dil_obs FROM PUBLIC;  -- materializa a ACL como em 0001
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = r) THEN
      EXECUTE format('REVOKE ALL ON dil_obs.observacao, dil_obs.observacao_latest FROM %I', r);
      EXECUTE format('REVOKE ALL ON FUNCTION dil_obs.observacao_as_of(timestamptz) FROM %I', r);
    END IF;
  END LOOP;
END $$;
GRANT SELECT ON dil_obs.observacao, dil_obs.observacao_latest TO dil_obs_leitor;
GRANT EXECUTE ON FUNCTION dil_obs.observacao_as_of(timestamptz) TO dil_obs_leitor;

RESET ROLE;
COMMIT;
