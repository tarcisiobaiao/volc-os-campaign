-- =============================================================================
-- dil_obs_0002 — observacao particionada por MÊS (UTC) de janela_inicio — OPCIONAL
-- MIGRATION CANDIDATA OPCIONAL. NÃO APLICADA EM NENHUM BANCO OPERACIONAL.
-- Testada só em PostgreSQL 16 descartável (tests/data-intelligence/fundacao/test_schema_pg_particionamento.py).
-- Pré-requisito: dil_obs_0001 aplicada. Trechos de DDL copiados de dil_obs_0001 (o teste prova que o
-- catálogo depois do down é idêntico ao de 0001 e que o as_of não muda em nenhum sentido).
-- =============================================================================
-- Quando usar: quando o volume de dil_obs.observacao tornar caro o DISTINCT ON global do as_of ou a
-- retenção por mês (detach de partição antiga) virar requisito. Até lá, 0001 sem partição é mais simples.
-- Decisões:
--   * mês em UTC do janela_inicio (dia BRT 00:00-03 cai às 03:00 UTC do mesmo dia: mesmo mês);
--   * SEM partição DEFAULT: linha fora das partições FALHA alto ("no partition of relation found");
--     o coletor (ou um agendador) chama dil_obs.garantir_particao_mensal(mes) antes de escrever;
--     uma DEFAULT com linhas impediria criar a partição do mês depois (erro de restrição);
--   * PK e UNIQUE incluem janela_inicio (exigência do Postgres); como janela_inicio está dentro do
--     hash da chave natural, a unicidade é a mesma de 0001;
--   * identidade vira sequência explícita (IDENTITY em tabela particionada só no PostgreSQL 17);
--   * append-only: trigger de STATEMENT no pai (UPDATE/DELETE/TRUNCATE pelo pai) + trigger de LINHA no
--     pai (clonado em cada partição: UPDATE/DELETE direto na partição) + trigger de TRUNCATE em cada
--     partição (TRUNCATE direto na partição não dispara o do pai).
-- Rollback: dil_obs_0002_observacao_particionada.OPCIONAL.down.sql (copia os dados de volta).

BEGIN;
-- R2-G1: SÓ SUPERUSUÁRIO aplica ou desfaz. Quem tem ADMIN OPTION em dil_obs_dono — inclusive o CREATEROLE
-- que criou os papéis, que no PostgreSQL 16 recebe essa opção automaticamente — pode se conceder o papel a
-- qualquer momento e desligar o append-only (DISABLE TRIGGER, TRUNCATE). Por isso papéis e schema não nascem de
-- não-superusuário, e a membresia temporária da R1 deixou de existir. No Supabase self-hosted: supabase_admin.
DO $$
BEGIN
  IF NOT (SELECT rolsuper FROM pg_catalog.pg_roles WHERE rolname = current_user) THEN
    RAISE EXCEPTION 'dil_obs: aplique como superusuário (% não é superusuário)', current_user
      USING ERRCODE = 'insufficient_privilege',
            HINT = 'No Supabase self-hosted, como supabase_admin. Quem administra dil_obs_dono pode desligar o append-only.';
  END IF;
END $$;

SET LOCAL ROLE dil_obs_dono;

LOCK TABLE dil_obs.observacao IN ACCESS EXCLUSIVE MODE;
DROP VIEW dil_obs.observacao_latest;
DROP FUNCTION dil_obs.observacao_as_of(timestamptz);
ALTER TABLE dil_obs.observacao RENAME TO observacao_v0;
ALTER INDEX dil_obs.observacao_pkey RENAME TO observacao_pkey_v0;
ALTER INDEX dil_obs.uq_obs_chave_idempotencia RENAME TO uq_obs_chave_idempotencia_v0;
ALTER INDEX dil_obs.uq_obs_versao RENAME TO uq_obs_versao_v0;
ALTER INDEX dil_obs.ix_obs_asof RENAME TO ix_obs_asof_v0;
ALTER INDEX dil_obs.ix_obs_entidade RENAME TO ix_obs_entidade_v0;
ALTER INDEX dil_obs.ix_obs_run RENAME TO ix_obs_run_v0;

CREATE SEQUENCE dil_obs.observacao_id_seq AS bigint;
SELECT pg_catalog.setval('dil_obs.observacao_id_seq',
                         coalesce((SELECT max(observacao_id) FROM dil_obs.observacao_v0), 0) + 1, false);

CREATE TABLE dil_obs.observacao (
  observacao_id       bigint NOT NULL DEFAULT nextval('dil_obs.observacao_id_seq'),
  chave_idempotencia  bytea NOT NULL,  -- sha256 (32 bytes); hex = Observacao.chave_base no Python
  chave_natural       bytea NOT NULL,  -- sha256 (32 bytes); hex = Observacao.chave_natural no Python
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

  -- índice único em tabela particionada precisa conter a chave de partição; janela_inicio já está
  -- dentro do hash da chave natural, então (chave, janela_inicio) único ≡ chave única
  CONSTRAINT observacao_pkey PRIMARY KEY (observacao_id, janela_inicio),
  CONSTRAINT uq_obs_chave_idempotencia UNIQUE (chave_idempotencia, janela_inicio),
  CONSTRAINT ck_obs_chaves CHECK (octet_length(chave_idempotencia) = 32 AND octet_length(chave_natural) = 32),
  CONSTRAINT ck_obs_fonte CHECK (fonte ~ '^[a-z][a-z0-9_]*$'),
  CONSTRAINT ck_obs_identidade CHECK (
    dil_obs._texto_ok(conta) AND dil_obs._texto_ok(entidade_tipo) AND dil_obs._texto_ok(entidade_id)
    AND dil_obs._texto_ok(timezone) AND dil_obs._texto_ok(schema_version) AND dil_obs._texto_ok(coletor_nome)
    AND dil_obs._texto_ok(coletor_versao) AND dil_obs._texto_ok(run_id) AND dil_obs._texto_ok(lote_id)
    AND dil_obs._texto_ok(payload_ref) AND (request_id IS NULL OR dil_obs._texto_ok(request_id))),
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
  -- partial: cobertura declarada (1..999999) OU desconhecida (nula, motivo com `cobertura_desconhecida`) — R1-F17
  CONSTRAINT ck_obs_partial CHECK (
    (status = 'partial' AND cobertura_ppm IS NOT NULL AND cobertura_ppm BETWEEN 1 AND 999999)
    OR (status = 'partial' AND cobertura_ppm IS NULL AND strpos(coalesce(motivo, ''), 'cobertura_desconhecida') > 0)
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
) PARTITION BY RANGE (janela_inicio);
COMMENT ON TABLE dil_obs.observacao IS
  'Observação canônica append-only. Cada linha é uma versão de conhecimento de um fato '
  '(chave_natural). Restatement = linha nova; nunca UPDATE.';
COMMENT ON COLUMN dil_obs.observacao.ingested_at IS 'Relógio do banco (now() da transação), nunca do escritor.';
COMMENT ON COLUMN dil_obs.observacao.available_at IS 'Relógio do replay as_of: quando o VOLC passou a ter o payload. Nunca retroativo.';

-- uma versão por (fato, instante de conhecimento): torna o as_of determinístico e serve o DISTINCT ON
CREATE UNIQUE INDEX uq_obs_versao ON dil_obs.observacao (chave_natural, available_at DESC, janela_inicio);
-- serve o DISTINCT ON do as_of na ordem de versão (D1)
CREATE INDEX ix_obs_asof ON dil_obs.observacao (chave_natural, observed_at DESC, available_at DESC);
CREATE INDEX ix_obs_entidade ON dil_obs.observacao (fonte, conta, entidade_tipo, entidade_id, janela_inicio);
-- (sem índice em lote_id: nenhuma função consulta por lote e as FKs nunca precisam dele — não há DELETE;
--  run_id fica indexado porque finalizar_run conta por run)
CREATE INDEX ix_obs_run ON dil_obs.observacao (run_id);
ALTER SEQUENCE dil_obs.observacao_id_seq OWNED BY dil_obs.observacao.observacao_id;

CREATE TRIGGER tg_obs_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON dil_obs.observacao
  FOR EACH STATEMENT EXECUTE FUNCTION dil_obs._rejeitar_mutacao();
CREATE TRIGGER tg_obs_append_only_linha BEFORE UPDATE OR DELETE ON dil_obs.observacao
  FOR EACH ROW EXECUTE FUNCTION dil_obs._rejeitar_mutacao();

ALTER TABLE dil_obs.observacao ENABLE ROW LEVEL SECURITY;
ALTER TABLE dil_obs.observacao FORCE ROW LEVEL SECURITY;
CREATE POLICY pl_obs_leitura ON dil_obs.observacao FOR SELECT TO dil_obs_leitor, dil_obs_dono USING (true);
CREATE POLICY pl_obs_insercao ON dil_obs.observacao FOR INSERT TO dil_obs_dono WITH CHECK (true);

CREATE FUNCTION dil_obs.garantir_particao_mensal(p_mes date) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
  v_ini timestamptz := (date_trunc('month', p_mes)::date::text || ' 00:00:00+00')::timestamptz;
  v_fim timestamptz := ((date_trunc('month', p_mes) + interval '1 month')::date::text || ' 00:00:00+00')::timestamptz;
  v_nome text := 'observacao_p' || to_char(date_trunc('month', p_mes), 'YYYY_MM');
BEGIN
  IF p_mes IS NULL THEN
    RAISE EXCEPTION 'contrato: mês nulo' USING ERRCODE = 'DLC01';
  END IF;
  IF to_regclass('dil_obs.' || v_nome) IS NOT NULL THEN
    RETURN 'noop';
  END IF;
  EXECUTE format('CREATE TABLE dil_obs.%I PARTITION OF dil_obs.observacao FOR VALUES FROM (%L) TO (%L)',
                 v_nome, v_ini, v_fim);
  EXECUTE format('ALTER TABLE dil_obs.%I ENABLE ROW LEVEL SECURITY', v_nome);
  EXECUTE format('ALTER TABLE dil_obs.%I FORCE ROW LEVEL SECURITY', v_nome);
  EXECUTE format('REVOKE ALL ON dil_obs.%I FROM PUBLIC', v_nome);
  EXECUTE format('CREATE TRIGGER tg_obs_append_only_truncate BEFORE TRUNCATE ON dil_obs.%I '
                 'FOR EACH STATEMENT EXECUTE FUNCTION dil_obs._rejeitar_mutacao()', v_nome);
  RETURN 'criada';
END $$;
REVOKE ALL ON FUNCTION dil_obs.garantir_particao_mensal(date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION dil_obs.garantir_particao_mensal(date) TO dil_obs_escritor;

-- partições para os dados existentes e para os próximos 3 meses
DO $$
DECLARE m date;
BEGIN
  FOR m IN
    SELECT generate_series(
             date_trunc('month', coalesce((SELECT min(janela_inicio) FROM dil_obs.observacao_v0), now()) AT TIME ZONE 'UTC'),
             date_trunc('month', greatest(coalesce((SELECT max(janela_inicio) FROM dil_obs.observacao_v0), now()), now())
                        AT TIME ZONE 'UTC') + interval '3 months',
             interval '1 month')::date
  LOOP
    PERFORM dil_obs.garantir_particao_mensal(m);
  END LOOP;
END $$;

INSERT INTO dil_obs.observacao SELECT * FROM dil_obs.observacao_v0;
DROP TABLE dil_obs.observacao_v0;

-- INLINÁVEL de propósito (medição da frente B: sem inline, 8,5–17,5 s em 1e6 linhas contra 0,2–0,3 s):
-- o planejador só expande no lugar uma função SQL de conjunto que NÃO tenha SET (search_path), NÃO seja
-- STRICT nem SECURITY DEFINER. Por isso: sem SET, nomes e o operador totalmente qualificados (o search_path
-- de quem chama não muda nada), SECURITY INVOKER (grants e RLS de quem chama valem) e t nulo → conjunto vazio
-- (available_at <= NULL nunca é verdade), o mesmo efeito que o STRICT tinha.
-- Ordem de versão (D1): maior observed_at, depois maior available_at. O UNIQUE (chave_natural, available_at)
-- torna esse par único por fato, então a ordem é total sem desempate extra e o índice ix_obs_asof a cobre.
CREATE FUNCTION dil_obs.observacao_as_of(t timestamptz) RETURNS SETOF dil_obs.observacao
LANGUAGE sql STABLE PARALLEL SAFE SECURITY INVOKER
AS $$
  SELECT DISTINCT ON (o.chave_natural) o.*
    FROM dil_obs.observacao AS o
   WHERE o.available_at OPERATOR(pg_catalog.<=) t
   ORDER BY o.chave_natural, o.observed_at DESC, o.available_at DESC
$$;
COMMENT ON FUNCTION dil_obs.observacao_as_of(timestamptz) IS
  'Estado conhecido em t: por chave_natural, entre as versões com available_at <= t, a de maior observed_at '
  '(empate: maior available_at; o UNIQUE (chave_natural, available_at) impede empate total). Status preservado. '
  'Inlinável: sem SET, sem STRICT, nomes qualificados.';

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
-- R2-G1: ninguém além de superusuários deve poder agir como dil_obs_dono. Membresias ou ADMIN OPTION que já
-- existiam (concedidas por alguém, fora deste arquivo) não são revogadas em silêncio: viram WARNING com o comando.
DO $$
DECLARE v_membros text;
BEGIN
  SELECT string_agg(m.rolname || CASE WHEN a.admin_option THEN ' (ADMIN OPTION)' ELSE '' END, ', ' ORDER BY m.rolname)
    INTO v_membros
    FROM pg_catalog.pg_auth_members a
    JOIN pg_catalog.pg_roles r ON r.oid = a.roleid
    JOIN pg_catalog.pg_roles m ON m.oid = a.member
   WHERE r.rolname = 'dil_obs_dono' AND NOT m.rolsuper;
  IF v_membros IS NOT NULL THEN
    RAISE WARNING 'dil_obs: podem agir como dil_obs_dono e desligar o append-only: %', v_membros
      USING HINT = 'Um superusuário deve rodar: REVOKE dil_obs_dono FROM <papel>;';
  END IF;
END $$;

COMMIT;
