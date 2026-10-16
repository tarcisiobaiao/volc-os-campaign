-- =============================================================================
-- dil_obs_0001 — Observação canônica append-only (Fundação Data Intelligence, thread A)
-- MIGRATION CANDIDATA. NÃO APLICADA EM NENHUM BANCO OPERACIONAL.
-- Testada só em PostgreSQL 16 descartável (tests/data-intelligence/fundacao/test_schema_pg_*.py).
-- Rollback: dil_obs_0001_schema_observacao.down.sql
-- Contrato: docs/data-intelligence/fundacao-20261016/02-CONTRATO-DE-DADOS.md
-- Espelho Python (mesmas regras): volc_dil.fundacao.observacao
-- =============================================================================
-- O que este arquivo garante (cada item tem teste):
--   * observacao, payload_bruto, lote e dead_letter são APPEND-ONLY: UPDATE, DELETE e
--     TRUNCATE são rejeitados por trigger de statement (vale até para superusuário, que
--     só escapa desligando o trigger de propósito — ALTER TABLE ... DISABLE TRIGGER ou
--     session_replication_role=replica; isso é decisão de operador, não acidente);
--   * null != 0: CHECKs de status × valor; nenhuma métrica tem DEFAULT;
--   * dinheiro em micros (bigint) + moeda char(3); contagem sem moeda e >= 0;
--   * relógios coerentes: janela_inicio < janela_fim <= ... (ver ck_obs_relogios);
--   * idempotência: chave_idempotencia UNIQUE, calculada PELO BANCO (o escritor não escolhe);
--   * versão ambígua impossível: UNIQUE (chave_natural, available_at);
--   * leitura as_of: dil_obs.observacao_as_of(t) e view observacao_latest = as_of(now());
--   * RLS habilitado e FORÇADO; escrita só por funções SECURITY DEFINER com search_path vazio;
--     papel de leitura só SELECT; anon/authenticated sem nada, mesmo com default ACL aberto.
-- Endurecimento após a revisão adversarial R1 (cada item com teste de regressão):
--   * F1  nunca retroativo: lote.recebido_em é o relógio do banco; available_at >= recebimento dos bytes;
--   * F2  quem aplica não continua membro de dil_obs_dono (membresia só durante a transação);
--   * F3  linhagem: observação só no run do próprio lote, em andamento; fonte/coletor/schema conferidos;
--   * F8  fechamento de run com contagens do banco, coerentes e NOT NULL; fechamento repetido = noop;
--   * F9  fronteira estrita: entrada `json` (texto preservado), inteiro literal, offset ISO, texto JSON,
--         sem controle/espaço de borda em identidade, ingested_at >= available_at, timezone exato;
--   * F17 partial com cobertura desconhecida (nula + motivo `cobertura_desconhecida`);
--   * F22 reaplicável por não-superusuário com ADMIN OPTION nos papéis; erro claro sem ela;
--   * H3/H4 READ COMMITTED obrigatório na escrita; run travado (FOR SHARE/FOR UPDATE) contra fechamento concorrente.
-- Relógio do banco: dil_obs._agora() (= now()). É o único ponto de tempo do servidor; os testes o
-- substituem como superusuário no cluster descartável para simular datas (não há GUC nem desvio em runtime).
-- Compatibilidade: sintaxe válida em PostgreSQL 15 (produção roda 15.8) e 16; testado só em 16.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 0. Papéis dedicados (idempotente). Sem LOGIN: uma credencial de serviço vira membro.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'dil_obs_dono') THEN
    CREATE ROLE dil_obs_dono NOLOGIN NOINHERIT NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'dil_obs_escritor') THEN
    CREATE ROLE dil_obs_escritor NOLOGIN NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'dil_obs_leitor') THEN
    CREATE ROLE dil_obs_leitor NOLOGIN NOBYPASSRLS;
  END IF;
END $$;

-- Agir como dil_obs_dono SÓ nesta transação (R1-F2/F22): superusuário não precisa de membresia;
-- quem já pode SET ROLE dil_obs_dono recebe um WARNING (membresia permanente desliga triggers);
-- os demais se concedem a membresia (exige ADMIN OPTION no papel) e a revogam no fim do arquivo.
DO $$
DECLARE
  v_super boolean;
  v_pode boolean;
BEGIN
  SELECT rolsuper INTO v_super FROM pg_catalog.pg_roles WHERE rolname = current_user;
  IF v_super THEN
    PERFORM pg_catalog.set_config('dil_obs.revogar_dono', 'nao', true);
    RETURN;
  END IF;
  IF current_setting('server_version_num')::integer >= 160000 THEN
    EXECUTE 'SELECT pg_catalog.pg_has_role(current_user, ''dil_obs_dono'', ''SET'')' INTO v_pode;
  ELSE
    v_pode := pg_catalog.pg_has_role(current_user, 'dil_obs_dono', 'MEMBER');
  END IF;
  IF v_pode THEN
    RAISE WARNING 'dil_obs: % já pode agir como dil_obs_dono de forma permanente (pode desligar o append-only); revise essa membresia', current_user;
    PERFORM pg_catalog.set_config('dil_obs.revogar_dono', 'nao', true);
    RETURN;
  END IF;
  BEGIN
    EXECUTE format('GRANT dil_obs_dono TO %I', current_user);
  EXCEPTION WHEN insufficient_privilege THEN
    RAISE EXCEPTION 'dil_obs: % não pode administrar o papel dil_obs_dono', current_user
      USING ERRCODE = 'insufficient_privilege',
            HINT = 'Aplique como superusuário ou como quem criou os papéis, ou peça a um superusuário: '
                   'GRANT dil_obs_dono TO <aplicador> WITH ADMIN OPTION, INHERIT FALSE, SET FALSE;';
  END;
  PERFORM pg_catalog.set_config('dil_obs.revogar_dono', 'sim', true);
END $$;

CREATE SCHEMA dil_obs AUTHORIZATION dil_obs_dono;
REVOKE ALL ON SCHEMA dil_obs FROM PUBLIC;

-- Tudo daqui em diante nasce com dono dil_obs_dono (nem superusuário, nem BYPASSRLS).
SET LOCAL ROLE dil_obs_dono;

-- Funções novas do dono não nascem executáveis por PUBLIC (o default do Postgres é nascer).
-- Precisa ser global (sem IN SCHEMA): default por schema só ACRESCENTA privilégio.
ALTER DEFAULT PRIVILEGES FOR ROLE dil_obs_dono REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

COMMENT ON SCHEMA dil_obs IS
  'Observação canônica append-only do Data Intelligence (candidata, thread A da Fundação DIL). '
  'Escrita só via dil_obs.registrar_*; leitura via observacao_as_of/observacao_latest.';

-- Relógio do banco (único). STABLE: constante dentro de um comando.
CREATE FUNCTION dil_obs._agora() RETURNS timestamptz
LANGUAGE sql STABLE PARALLEL SAFE SET search_path = ''
AS $$ SELECT pg_catalog.now() $$;

-- Texto de identidade: não vazio, sem espaço ASCII de borda, sem caractere de controle (espelho de
-- modelo._texto no Python: strip(" ") e ord < 32 ou 127).
CREATE FUNCTION dil_obs._texto_ok(s text) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path = ''
AS $$ SELECT s IS NOT NULL AND s <> '' AND s = pg_catalog.btrim(s, ' ') AND s !~ '[\x01-\x1f\x7f]' $$;

-- ---------------------------------------------------------------------------
-- 1. Funções puras de chave (espelho de volc_dil/fundacao/observacao/chaves.py)
-- ---------------------------------------------------------------------------
CREATE FUNCTION dil_obs._sha256_texto(s text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE SET search_path = ''
AS $$ SELECT pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(s, 'UTF8')), 'hex') $$;

CREATE FUNCTION dil_obs._ts(t timestamptz) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE SET search_path = ''
AS $$ SELECT pg_catalog.to_char(t AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') $$;

CREATE FUNCTION dil_obs._chave_natural(
  p_fonte text, p_conta text, p_entidade_tipo text, p_entidade_id text, p_grao text[], p_dimensoes jsonb,
  p_metrica text, p_value_kind text, p_janela_inicio timestamptz, p_janela_fim timestamptz, p_timezone text
) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path = ''
AS $$
  SELECT dil_obs._sha256_texto(
    'dil_obs.chave_natural.v1'
    || chr(31) || p_fonte || chr(31) || p_conta || chr(31) || p_entidade_tipo || chr(31) || p_entidade_id
    || chr(31) || coalesce((SELECT string_agg(g, ',' ORDER BY g COLLATE "C")
                             FROM (SELECT DISTINCT g FROM unnest(p_grao) AS u(g)) AS x), '')
    || chr(31) || coalesce((SELECT string_agg((e ->> 0) || chr(29) || (e ->> 1), chr(30) ORDER BY (e ->> 0) COLLATE "C")
                             FROM jsonb_array_elements(p_dimensoes) AS d(e)), '')
    || chr(31) || p_metrica || chr(31) || coalesce(p_value_kind, '')
    || chr(31) || dil_obs._ts(p_janela_inicio) || chr(31) || dil_obs._ts(p_janela_fim) || chr(31) || p_timezone)
$$;

-- v2 (D1/D2): observed_at entra na chave da LEITURA. Retry/reentrega = mesma chave = no-op; o mesmo payload
-- relido em outra hora (janela que fechou, cobertura que mudou, cron D0) = leitura nova = versão nova.
CREATE FUNCTION dil_obs._chave_base(
  p_chave_natural text, p_payload_sha256 text, p_schema_version text, p_coletor_nome text, p_coletor_versao text,
  p_observed_at timestamptz
) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE SET search_path = ''
AS $$
  SELECT dil_obs._sha256_texto('dil_obs.chave_idempotencia.v2' || chr(31) || p_chave_natural || chr(31) || p_payload_sha256
                               || chr(31) || p_schema_version || chr(31) || p_coletor_nome || chr(31) || p_coletor_versao
                               || chr(31) || dil_obs._ts(p_observed_at))
$$;

-- ---------------------------------------------------------------------------
-- 2. Tabelas
-- ---------------------------------------------------------------------------
CREATE TABLE dil_obs.run_coleta (
  run_id          text PRIMARY KEY,
  fonte           text NOT NULL,
  coletor_nome    text NOT NULL,
  coletor_versao  text NOT NULL,
  iniciado_em     timestamptz NOT NULL,
  finalizado_em   timestamptz,
  status          text NOT NULL,
  n_lidas         integer,
  n_inseridas     integer,
  n_noop          integer,
  n_dead_letter   integer,
  erro            text,
  CONSTRAINT ck_run_textos CHECK (
    dil_obs._texto_ok(run_id) AND dil_obs._texto_ok(coletor_nome) AND dil_obs._texto_ok(coletor_versao)),
  CONSTRAINT ck_run_fonte CHECK (fonte ~ '^[a-z][a-z0-9_]*$'),
  CONSTRAINT ck_run_status CHECK (status IN ('running', 'succeeded', 'failed', 'partial')),
  CONSTRAINT ck_run_fim CHECK ((status = 'running') = (finalizado_em IS NULL)
                               AND (finalizado_em IS NULL OR finalizado_em >= iniciado_em)),
  CONSTRAINT ck_run_erro CHECK (status <> 'failed' OR (erro IS NOT NULL AND btrim(erro) <> '')),
  -- contagens só existem quando a execução termina; nunca nascem 0 por default; no fim são
  -- obrigatórias (IS NOT NULL explícito: CHECK com NULL passaria — R1-F8) e coerentes
  CONSTRAINT ck_run_contagens CHECK (
    (status = 'running' AND n_lidas IS NULL AND n_inseridas IS NULL AND n_noop IS NULL AND n_dead_letter IS NULL)
    OR (status <> 'running'
       AND n_lidas IS NOT NULL AND n_inseridas IS NOT NULL AND n_noop IS NOT NULL AND n_dead_letter IS NOT NULL
       AND n_lidas >= 0 AND n_inseridas >= 0 AND n_noop >= 0 AND n_dead_letter >= 0
       AND n_lidas >= n_inseridas + n_noop))
);
COMMENT ON TABLE dil_obs.run_coleta IS 'Uma execução de coletor. Única tabela com UPDATE: running → estado final, uma vez.';

CREATE TABLE dil_obs.payload_bruto (
  sha256         text PRIMARY KEY,
  corpo_bruto    bytea NOT NULL,
  corpo          jsonb,  -- NULL quando o corpo não é JSON (erro HTML, lixo): o bruto continua guardado
  content_type   text NOT NULL,
  tamanho_bytes  integer GENERATED ALWAYS AS (octet_length(corpo_bruto)) STORED,
  recebido_em    timestamptz NOT NULL,
  CONSTRAINT ck_payload_sha256 CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  -- endereçamento por conteúdo provado pelo próprio banco
  CONSTRAINT ck_payload_hash_confere CHECK (sha256 = encode(sha256(corpo_bruto), 'hex')),
  CONSTRAINT ck_payload_content_type CHECK (content_type <> '')
);
COMMENT ON TABLE dil_obs.payload_bruto IS 'Resposta bruta imutável, endereçada por sha256 dos bytes recebidos.';

CREATE TABLE dil_obs.lote (
  lote_id         text PRIMARY KEY,
  run_id          text NOT NULL REFERENCES dil_obs.run_coleta (run_id),
  payload_sha256  text NOT NULL REFERENCES dil_obs.payload_bruto (sha256),
  schema_version  text NOT NULL,
  pedido          jsonb NOT NULL,
  recebido_em     timestamptz NOT NULL,
  registrado_em   timestamptz NOT NULL,
  CONSTRAINT ck_lote_textos CHECK (dil_obs._texto_ok(lote_id) AND dil_obs._texto_ok(schema_version)),
  CONSTRAINT ck_lote_pedido CHECK (jsonb_typeof(pedido) = 'object'),
  CONSTRAINT ck_lote_relogio CHECK (recebido_em <= registrado_em)
);
COMMENT ON TABLE dil_obs.lote IS 'Um pedido à fonte e o payload que voltou. recebido_em (relógio do banco) limita o available_at.';

CREATE TABLE dil_obs.observacao (
  observacao_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  chave_idempotencia  text NOT NULL,
  chave_natural       text NOT NULL,
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
  CONSTRAINT ck_obs_chaves CHECK (chave_idempotencia ~ '^[0-9a-f]{64}$' AND chave_natural ~ '^[0-9a-f]{64}$'),
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
);
COMMENT ON TABLE dil_obs.observacao IS
  'Observação canônica append-only. Cada linha é uma versão de conhecimento de um fato '
  '(chave_natural). Restatement = linha nova; nunca UPDATE.';
COMMENT ON COLUMN dil_obs.observacao.ingested_at IS 'Relógio do banco (now() da transação), nunca do escritor.';
COMMENT ON COLUMN dil_obs.observacao.available_at IS 'Relógio do replay as_of: quando o VOLC passou a ter o payload. Nunca retroativo.';

-- uma versão por (fato, instante de conhecimento): torna o as_of determinístico e serve o DISTINCT ON
CREATE UNIQUE INDEX uq_obs_versao ON dil_obs.observacao (chave_natural, available_at DESC);
-- serve o DISTINCT ON do as_of na ordem de versão (D1)
CREATE INDEX ix_obs_asof ON dil_obs.observacao (chave_natural, observed_at DESC, available_at DESC);
CREATE INDEX ix_obs_entidade ON dil_obs.observacao (fonte, conta, entidade_tipo, entidade_id, janela_inicio);
CREATE INDEX ix_obs_lote ON dil_obs.observacao (lote_id);
CREATE INDEX ix_obs_run ON dil_obs.observacao (run_id);

CREATE TABLE dil_obs.dead_letter (
  dead_letter_id  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id          text NOT NULL REFERENCES dil_obs.run_coleta (run_id),
  lote_id         text REFERENCES dil_obs.lote (lote_id),
  payload_sha256  text REFERENCES dil_obs.payload_bruto (sha256),
  motivo          text NOT NULL,
  detalhe         jsonb NOT NULL,
  registrado_em   timestamptz NOT NULL,
  CONSTRAINT ck_dl_motivo CHECK (btrim(motivo) <> ''),
  CONSTRAINT ck_dl_detalhe CHECK (jsonb_typeof(detalhe) = 'object')
);
COMMENT ON TABLE dil_obs.dead_letter IS 'O que não virou observação (linha sem identidade, chave substituída, esquema desconhecido).';
CREATE INDEX ix_dl_run ON dil_obs.dead_letter (run_id);

-- ---------------------------------------------------------------------------
-- 3. Append-only provado: UPDATE/DELETE/TRUNCATE rejeitados (trigger de statement:
--    dispara mesmo quando nenhuma linha casa, e mesmo para superusuário)
-- ---------------------------------------------------------------------------
CREATE FUNCTION dil_obs._rejeitar_mutacao() RETURNS trigger
LANGUAGE plpgsql SET search_path = ''
AS $$
BEGIN
  RAISE EXCEPTION 'append_only: dil_obs.% não aceita %', TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'DLA01',
          HINT = 'Correção é versão nova (restatement), nunca UPDATE/DELETE.';
END $$;

CREATE TRIGGER tg_obs_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON dil_obs.observacao
  FOR EACH STATEMENT EXECUTE FUNCTION dil_obs._rejeitar_mutacao();
CREATE TRIGGER tg_payload_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON dil_obs.payload_bruto
  FOR EACH STATEMENT EXECUTE FUNCTION dil_obs._rejeitar_mutacao();
CREATE TRIGGER tg_lote_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON dil_obs.lote
  FOR EACH STATEMENT EXECUTE FUNCTION dil_obs._rejeitar_mutacao();
CREATE TRIGGER tg_dl_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON dil_obs.dead_letter
  FOR EACH STATEMENT EXECUTE FUNCTION dil_obs._rejeitar_mutacao();

-- run_coleta: DELETE/TRUNCATE proibidos; UPDATE só running → final, e só nos campos de fechamento
CREATE TRIGGER tg_run_sem_delete BEFORE DELETE OR TRUNCATE ON dil_obs.run_coleta
  FOR EACH STATEMENT EXECUTE FUNCTION dil_obs._rejeitar_mutacao();

CREATE FUNCTION dil_obs._guardar_run() RETURNS trigger
LANGUAGE plpgsql SET search_path = ''
AS $$
BEGIN
  IF OLD.status <> 'running' THEN
    RAISE EXCEPTION 'append_only: run_coleta % já finalizada (%)', OLD.run_id, OLD.status USING ERRCODE = 'DLA01';
  END IF;
  IF (NEW.run_id, NEW.fonte, NEW.coletor_nome, NEW.coletor_versao, NEW.iniciado_em)
     IS DISTINCT FROM (OLD.run_id, OLD.fonte, OLD.coletor_nome, OLD.coletor_versao, OLD.iniciado_em) THEN
    RAISE EXCEPTION 'append_only: identidade da run_coleta não muda' USING ERRCODE = 'DLA01';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tg_run_guarda BEFORE UPDATE ON dil_obs.run_coleta
  FOR EACH ROW EXECUTE FUNCTION dil_obs._guardar_run();

-- ---------------------------------------------------------------------------
-- 4. Escrita: só por funções SECURITY DEFINER (dono sem BYPASSRLS, search_path vazio)
-- ---------------------------------------------------------------------------
CREATE FUNCTION dil_obs.registrar_run(
  p_run_id text, p_fonte text, p_coletor_nome text, p_coletor_versao text, p_iniciado_em timestamptz
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE r dil_obs.run_coleta%ROWTYPE;
BEGIN
  IF p_iniciado_em IS NULL OR p_iniciado_em > dil_obs._agora() THEN
    RAISE EXCEPTION 'contrato: iniciado_em nulo ou no futuro' USING ERRCODE = 'DLC01';
  END IF;
  IF NOT (dil_obs._texto_ok(p_run_id) AND dil_obs._texto_ok(p_coletor_nome) AND dil_obs._texto_ok(p_coletor_versao)) THEN
    RAISE EXCEPTION 'contrato: run_id/coletor vazio, com espaço de borda ou caractere de controle' USING ERRCODE = 'DLC01';
  END IF;
  SELECT * INTO r FROM dil_obs.run_coleta WHERE run_id = p_run_id;
  IF FOUND THEN
    IF (r.fonte, r.coletor_nome, r.coletor_versao, r.iniciado_em) IS DISTINCT FROM
       (p_fonte, p_coletor_nome, p_coletor_versao, p_iniciado_em) THEN
      RAISE EXCEPTION 'conflito_idempotencia: run_coleta % já existe com outra identidade', p_run_id USING ERRCODE = 'DLI01';
    END IF;
    RETURN 'noop';
  END IF;
  INSERT INTO dil_obs.run_coleta (run_id, fonte, coletor_nome, coletor_versao, iniciado_em, status)
  VALUES (p_run_id, p_fonte, p_coletor_nome, p_coletor_versao, p_iniciado_em, 'running');
  RETURN 'inserido';
END $$;

-- Fechamento (R1-F8): inseridas e dead letters são CONTADAS PELO BANCO; o chamador só informa n_lidas
-- (itens submetidos) e n_noop, que precisam ser coerentes; valores informados para as contagens do banco
-- precisam bater. Repetir o mesmo fechamento é 'noop'; outro desfecho é erro.
-- Trava a linha da execução (FOR UPDATE) antes de contar: observações em voo (que seguram FOR SHARE)
-- entram na contagem ou são recusadas depois — nunca gravadas num run já fechado (R1-H4).
CREATE FUNCTION dil_obs.finalizar_run(
  p_run_id text, p_status text, p_n_lidas integer, p_n_inseridas integer, p_n_noop integer,
  p_n_dead_letter integer, p_erro text
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
  r dil_obs.run_coleta%ROWTYPE;
  v_ins integer;
  v_dl integer;
BEGIN
  IF p_status IS NULL OR p_status NOT IN ('succeeded', 'failed', 'partial') THEN
    RAISE EXCEPTION 'contrato: finalizar exige estado final (succeeded, failed, partial)' USING ERRCODE = 'DLC01';
  END IF;
  SELECT * INTO r FROM dil_obs.run_coleta WHERE run_id = p_run_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'contrato: run_coleta % inexistente', p_run_id USING ERRCODE = 'DLC01';
  END IF;
  IF r.status = 'running' THEN
    -- a policy de UPDATE só enxerga runs em andamento: sem linha aqui = outro fechamento ganhou a corrida
    SELECT * INTO r FROM dil_obs.run_coleta WHERE run_id = p_run_id AND status = 'running' FOR UPDATE;
    IF NOT FOUND THEN
      SELECT * INTO r FROM dil_obs.run_coleta WHERE run_id = p_run_id;
    END IF;
  END IF;
  -- contagens em comandos novos: em READ COMMITTED enxergam o que foi confirmado até a trava
  SELECT count(*) INTO v_ins FROM dil_obs.observacao WHERE run_id = p_run_id;
  SELECT count(*) INTO v_dl FROM dil_obs.dead_letter WHERE run_id = p_run_id;
  IF r.status <> 'running' THEN
    IF (r.status, r.n_lidas, r.n_noop, r.erro) IS NOT DISTINCT FROM (p_status, p_n_lidas, p_n_noop, p_erro)
       AND coalesce(p_n_inseridas, r.n_inseridas) = r.n_inseridas
       AND coalesce(p_n_dead_letter, r.n_dead_letter) = r.n_dead_letter THEN
      RETURN 'noop';
    END IF;
    RAISE EXCEPTION 'conflito_idempotencia: run_coleta % já finalizada como % com outras contagens', p_run_id, r.status
      USING ERRCODE = 'DLI01';
  END IF;
  IF p_n_lidas IS NULL OR p_n_noop IS NULL OR p_n_lidas < 0 OR p_n_noop < 0 THEN
    RAISE EXCEPTION 'contagem_incoerente: n_lidas e n_noop são obrigatórios e >= 0' USING ERRCODE = 'DLC01';
  END IF;
  IF p_n_inseridas IS DISTINCT FROM v_ins AND p_n_inseridas IS NOT NULL
     OR p_n_dead_letter IS DISTINCT FROM v_dl AND p_n_dead_letter IS NOT NULL THEN
    RAISE EXCEPTION 'contagem_incoerente: o banco contou inseridas=%, dead_letter=%', v_ins, v_dl USING ERRCODE = 'DLC01';
  END IF;
  IF p_n_lidas < v_ins + p_n_noop THEN
    RAISE EXCEPTION 'contagem_incoerente: n_lidas (%) menor que inseridas+noop (%)', p_n_lidas, v_ins + p_n_noop
      USING ERRCODE = 'DLC01';
  END IF;
  UPDATE dil_obs.run_coleta
     SET status = p_status, finalizado_em = greatest(dil_obs._agora(), iniciado_em), n_lidas = p_n_lidas,
         n_inseridas = v_ins, n_noop = p_n_noop, n_dead_letter = v_dl, erro = p_erro
   WHERE run_id = p_run_id;
  RETURN 'finalizado';
END $$;

CREATE FUNCTION dil_obs.registrar_payload(p_sha256 text, p_corpo bytea, p_content_type text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE v_json jsonb;
BEGIN
  IF p_corpo IS NULL OR p_sha256 IS DISTINCT FROM encode(sha256(p_corpo), 'hex') THEN
    RAISE EXCEPTION 'contrato: sha256 não confere com os bytes do payload' USING ERRCODE = 'DLC01';
  END IF;
  IF EXISTS (SELECT 1 FROM dil_obs.payload_bruto WHERE sha256 = p_sha256) THEN
    RETURN 'noop';  -- mesmo hash ⇒ mesmos bytes; recebido_em continua o do PRIMEIRO recebimento
  END IF;
  BEGIN
    v_json := convert_from(p_corpo, 'UTF8')::jsonb;
  EXCEPTION WHEN others THEN
    v_json := NULL;  -- corpo não-JSON é guardado como bytes; a observação dirá `invalid`
  END;
  INSERT INTO dil_obs.payload_bruto (sha256, corpo_bruto, corpo, content_type, recebido_em)
  VALUES (p_sha256, p_corpo, v_json, p_content_type, dil_obs._agora());
  RETURN 'inserido';
END $$;

-- recebido_em do lote é o RELÓGIO DO BANCO (R1-F1). p_recebido_em é só conferido: o coletor pode
-- informar o seu relógio, mas nunca no passado (mais de 5 min de folga de relógio) nem no futuro.
CREATE FUNCTION dil_obs.registrar_lote(
  p_lote_id text, p_run_id text, p_payload_sha256 text, p_schema_version text, p_pedido jsonb, p_recebido_em timestamptz
) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
  l dil_obs.lote%ROWTYPE;
  v_agora timestamptz := dil_obs._agora();
BEGIN
  IF p_recebido_em > v_agora THEN
    RAISE EXCEPTION 'contrato: recebido_em no futuro' USING ERRCODE = 'DLC01';
  END IF;
  IF p_recebido_em < v_agora - interval '5 minutes' THEN
    RAISE EXCEPTION 'contrato: recebido_em no passado (conhecimento retroativo); o banco data o lote pelo próprio relógio'
      USING ERRCODE = 'DLC01';
  END IF;
  IF NOT (dil_obs._texto_ok(p_lote_id) AND dil_obs._texto_ok(p_schema_version)) THEN
    RAISE EXCEPTION 'contrato: lote_id/schema_version vazio, com espaço de borda ou caractere de controle' USING ERRCODE = 'DLC01';
  END IF;
  SELECT * INTO l FROM dil_obs.lote WHERE lote_id = p_lote_id;
  IF FOUND THEN
    IF (l.run_id, l.payload_sha256, l.schema_version, l.pedido) IS DISTINCT FROM
       (p_run_id, p_payload_sha256, p_schema_version, p_pedido) THEN
      RAISE EXCEPTION 'conflito_idempotencia: lote % já existe com outro conteúdo', p_lote_id USING ERRCODE = 'DLI01';
    END IF;
    RETURN 'noop';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM dil_obs.run_coleta WHERE run_id = p_run_id AND status = 'running') THEN
    RAISE EXCEPTION 'contrato: run_coleta % inexistente ou finalizada', p_run_id USING ERRCODE = 'DLC01';
  END IF;
  INSERT INTO dil_obs.lote (lote_id, run_id, payload_sha256, schema_version, pedido, recebido_em, registrado_em)
  VALUES (p_lote_id, p_run_id, p_payload_sha256, p_schema_version, p_pedido, v_agora, v_agora);
  RETURN 'inserido';
END $$;

CREATE FUNCTION dil_obs.registrar_dead_letter(
  p_run_id text, p_lote_id text, p_payload_sha256 text, p_motivo text, p_detalhe jsonb
) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE v_id bigint;
BEGIN
  INSERT INTO dil_obs.dead_letter (run_id, lote_id, payload_sha256, motivo, detalhe, registrado_em)
  VALUES (p_run_id, p_lote_id, p_payload_sha256, p_motivo, coalesce(p_detalhe, '{}'::jsonb), dil_obs._agora())
  RETURNING dead_letter_id INTO v_id;
  RETURN v_id;
END $$;

-- Regras idênticas a volc_dil.fundacao.observacao.Registro.registrar (oráculo do teste de equivalência):
--   chave da leitura nova → 'inserido'; mesma chave com conteúdo diferente → conflito_idempotencia;
--   mesma chave e mesmo conteúdo → 'noop'. Mesmo (chave_natural, available_at) com outra leitura → versao_ambigua.
-- Entrada `json` (não jsonb): o texto original é preservado, então `5e0`, `1.0` e chave repetida são
-- detectáveis (jsonb normalizaria) — paridade com Observacao.de_json_texto (R1-F9).
CREATE FUNCTION dil_obs.registrar_observacao(p json) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
  k_campos CONSTANT text[] := ARRAY[
    'fonte', 'conta', 'entidade_tipo', 'entidade_id', 'grao', 'dimensoes', 'metrica', 'value_kind', 'valor',
    'unidade', 'moeda', 'janela_inicio', 'janela_fim', 'timezone', 'observed_at', 'source_updated_at',
    'available_at', 'ingested_at', 'run_id', 'request_id', 'lote_id', 'payload_sha256', 'payload_ref',
    'schema_version', 'coletor_nome', 'coletor_versao', 'status', 'motivo', 'cobertura_ppm'];
  k_texto_obrig CONSTANT text[] := ARRAY[
    'fonte', 'conta', 'entidade_tipo', 'entidade_id', 'metrica', 'unidade', 'janela_inicio', 'janela_fim',
    'timezone', 'observed_at', 'available_at', 'ingested_at', 'run_id', 'lote_id', 'payload_sha256',
    'payload_ref', 'schema_version', 'coletor_nome', 'coletor_versao', 'status'];
  k_texto_opc CONSTANT text[] := ARRAY['value_kind', 'moeda', 'source_updated_at', 'request_id', 'motivo'];
  k_identidade CONSTANT text[] := ARRAY[
    'conta', 'entidade_tipo', 'entidade_id', 'timezone', 'run_id', 'lote_id', 'payload_ref', 'schema_version',
    'coletor_nome', 'coletor_versao'];
  k_instantes CONSTANT text[] := ARRAY['janela_inicio', 'janela_fim', 'observed_at', 'available_at', 'ingested_at'];
  k_instante_re CONSTANT text :=
    '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]{1,6})?)?(Z|[+-][0-9]{2}:[0-9]{2})$';
  v_campo text;
  v_extras text[];
  j jsonb;
  v_grao text[];
  v_dims jsonb;
  v_valor bigint;
  v_cob integer;
  v_avail timestamptz;
  v_nat text;
  v_base text;
  v_exist dil_obs.observacao%ROWTYPE;
  v_lote dil_obs.lote%ROWTYPE;
  v_run dil_obs.run_coleta%ROWTYPE;
  v_payload_recebido timestamptz;
BEGIN
  -- a checagem de idempotência sob trava precisa ver commits concorrentes (R1-H3)
  IF current_setting('transaction_isolation') <> 'read committed' THEN
    RAISE EXCEPTION 'isolamento: registrar_observacao exige READ COMMITTED (sob %, um retry concorrente viraria unique_violation)',
      current_setting('transaction_isolation') USING ERRCODE = 'DLX01';
  END IF;
  IF p IS NULL OR json_typeof(p) <> 'object' THEN
    RAISE EXCEPTION 'contrato: observação precisa ser objeto JSON' USING ERRCODE = 'DLC01';
  END IF;
  SELECT array_agg(k ORDER BY k) INTO v_extras FROM json_object_keys(p) AS o(k) WHERE NOT (k = ANY (k_campos));
  IF v_extras IS NOT NULL THEN
    RAISE EXCEPTION 'contrato: campos desconhecidos %', v_extras USING ERRCODE = 'DLC01';
  END IF;
  IF (SELECT count(*) FROM json_object_keys(p)) <> (SELECT count(DISTINCT k) FROM json_object_keys(p) AS o(k)) THEN
    RAISE EXCEPTION 'contrato: JSON com chave repetida' USING ERRCODE = 'DLC01';
  END IF;

  -- tipos JSON estritos (conta numérica, instante número etc. não passam)
  FOREACH v_campo IN ARRAY k_texto_obrig LOOP
    IF coalesce(json_typeof(p -> v_campo), 'ausente') <> 'string' THEN
      RAISE EXCEPTION 'contrato: % precisa ser texto JSON', v_campo USING ERRCODE = 'DLC01';
    END IF;
  END LOOP;
  FOREACH v_campo IN ARRAY k_texto_opc LOOP
    IF coalesce(json_typeof(p -> v_campo), 'null') NOT IN ('string', 'null') THEN
      RAISE EXCEPTION 'contrato: % precisa ser texto JSON ou null', v_campo USING ERRCODE = 'DLC01';
    END IF;
  END LOOP;
  FOREACH v_campo IN ARRAY k_identidade LOOP
    IF NOT dil_obs._texto_ok(p ->> v_campo) THEN
      RAISE EXCEPTION 'contrato: % vazio, com espaço de borda ou caractere de controle', v_campo USING ERRCODE = 'DLC01';
    END IF;
  END LOOP;
  IF p ->> 'request_id' IS NOT NULL AND NOT dil_obs._texto_ok(p ->> 'request_id') THEN
    RAISE EXCEPTION 'contrato: request_id vazio, com espaço de borda ou caractere de controle' USING ERRCODE = 'DLC01';
  END IF;
  FOREACH v_campo IN ARRAY k_instantes || ARRAY['source_updated_at'] LOOP
    IF p ->> v_campo IS NOT NULL AND (p ->> v_campo) !~ k_instante_re THEN
      RAISE EXCEPTION 'contrato: % precisa ser ISO-8601 com offset explícito', v_campo USING ERRCODE = 'DLC01';
    END IF;
  END LOOP;

  -- números estritos: o TEXTO JSON precisa ser inteiro (json preserva `5e0`/`1.0`, jsonb não)
  IF coalesce(json_typeof(p -> 'valor'), 'null') NOT IN ('number', 'null')
     OR (json_typeof(p -> 'valor') = 'number' AND (p -> 'valor')::text !~ '^-?[0-9]+$') THEN
    RAISE EXCEPTION 'contrato: valor precisa ser inteiro (micros ou contagem) ou null' USING ERRCODE = 'DLC01';
  END IF;
  IF coalesce(json_typeof(p -> 'cobertura_ppm'), 'null') NOT IN ('number', 'null')
     OR (json_typeof(p -> 'cobertura_ppm') = 'number' AND (p -> 'cobertura_ppm')::text !~ '^-?[0-9]+$') THEN
    RAISE EXCEPTION 'contrato: cobertura_ppm precisa ser inteiro ou null' USING ERRCODE = 'DLC01';
  END IF;
  v_valor := (p ->> 'valor')::bigint;
  v_cob := (p ->> 'cobertura_ppm')::integer;

  j := p::jsonb;  -- daqui em diante, leitura normalizada (as checagens de forma já passaram)
  IF jsonb_typeof(j -> 'grao') IS DISTINCT FROM 'array'
     OR EXISTS (SELECT 1 FROM jsonb_array_elements(j -> 'grao') AS e(g) WHERE jsonb_typeof(g) <> 'string') THEN
    RAISE EXCEPTION 'contrato: grao precisa ser lista de textos' USING ERRCODE = 'DLC01';
  END IF;
  v_grao := ARRAY(SELECT g FROM (SELECT DISTINCT g FROM jsonb_array_elements_text(j -> 'grao') AS e(g)) AS x
                  ORDER BY g COLLATE "C");

  v_dims := coalesce(j -> 'dimensoes', '[]'::jsonb);
  IF v_dims = 'null'::jsonb THEN
    v_dims := '[]'::jsonb;
  END IF;
  IF jsonb_typeof(v_dims) <> 'array'
     OR EXISTS (SELECT 1 FROM jsonb_array_elements(v_dims) AS d(e)
                WHERE jsonb_typeof(e) <> 'array' OR jsonb_array_length(e) <> 2
                   OR jsonb_typeof(e -> 0) <> 'string' OR jsonb_typeof(e -> 1) <> 'string'
                   OR NOT dil_obs._texto_ok(e ->> 0) OR NOT dil_obs._texto_ok(e ->> 1)) THEN
    RAISE EXCEPTION 'contrato: dimensoes precisa ser lista de pares [nome, valor] de texto' USING ERRCODE = 'DLC01';
  END IF;
  IF v_dims IS DISTINCT FROM coalesce((SELECT jsonb_agg(e ORDER BY (e ->> 0) COLLATE "C")
                                         FROM jsonb_array_elements(v_dims) AS d(e)), '[]'::jsonb)
     OR (SELECT count(DISTINCT e ->> 0) FROM jsonb_array_elements(v_dims) AS d(e)) <> jsonb_array_length(v_dims) THEN
    RAISE EXCEPTION 'contrato: dimensões precisam vir ordenadas e sem repetição' USING ERRCODE = 'DLC01';
  END IF;

  -- nome exato da base IANA (pg_timezone_names compara com caixa)
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_timezone_names WHERE name = j ->> 'timezone') THEN
    RAISE EXCEPTION 'contrato: timezone inválido: %', j ->> 'timezone' USING ERRCODE = 'DLC01';
  END IF;

  v_avail := (j ->> 'available_at')::timestamptz;
  IF (j ->> 'ingested_at')::timestamptz < v_avail THEN
    -- o banco grava o próprio relógio, mas o que o escritor declarou também precisa ser coerente (paridade)
    RAISE EXCEPTION 'contrato: ingested_at declarado anterior a available_at' USING ERRCODE = 'DLC01';
  END IF;

  -- linhagem (R1-F3): a observação pertence ao run DO LOTE, que está em andamento; fonte e coletor são
  -- os do run; schema_version é o do lote; o payload é o do lote.
  SELECT * INTO v_lote FROM dil_obs.lote WHERE lote_id = j ->> 'lote_id';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'contrato: lote % inexistente', j ->> 'lote_id' USING ERRCODE = 'DLC01';
  END IF;
  IF v_lote.payload_sha256 IS DISTINCT FROM j ->> 'payload_sha256' THEN
    RAISE EXCEPTION 'contrato: payload_sha256 difere do payload do lote' USING ERRCODE = 'DLC01';
  END IF;
  IF v_lote.run_id IS DISTINCT FROM j ->> 'run_id' THEN
    RAISE EXCEPTION 'linhagem: run_id da observação (%) difere do run do lote (%)', j ->> 'run_id', v_lote.run_id
      USING ERRCODE = 'DLC01';
  END IF;
  IF v_lote.schema_version IS DISTINCT FROM j ->> 'schema_version' THEN
    RAISE EXCEPTION 'linhagem: schema_version da observação difere do lote' USING ERRCODE = 'DLC01';
  END IF;
  SELECT * INTO v_run FROM dil_obs.run_coleta WHERE run_id = v_lote.run_id;
  IF v_run.status <> 'running' THEN
    RAISE EXCEPTION 'contrato: run_coleta % já finalizada', v_run.run_id USING ERRCODE = 'DLC01';
  END IF;
  -- trava compartilhada: finalizar_run espera esta transação (R1-H4); a policy de UPDATE só enxerga running
  PERFORM 1 FROM dil_obs.run_coleta WHERE run_id = v_run.run_id AND status = 'running' FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'contrato: run_coleta % já finalizada', v_run.run_id USING ERRCODE = 'DLC01';
  END IF;
  IF (v_run.fonte, v_run.coletor_nome, v_run.coletor_versao)
     IS DISTINCT FROM (j ->> 'fonte', j ->> 'coletor_nome', j ->> 'coletor_versao') THEN
    RAISE EXCEPTION 'linhagem: fonte/coletor da observação diferem do run_coleta' USING ERRCODE = 'DLC01';
  END IF;

  -- nunca retroativo (R1-F1): o VOLC não "soube" antes de o banco receber os bytes
  SELECT recebido_em INTO v_payload_recebido FROM dil_obs.payload_bruto WHERE sha256 = v_lote.payload_sha256;
  IF v_avail < v_payload_recebido OR v_avail < v_lote.recebido_em THEN
    RAISE EXCEPTION 'contrato: available_at anterior ao recebimento dos bytes pelo banco (conhecimento retroativo)'
      USING ERRCODE = 'DLC01';
  END IF;

  v_nat := dil_obs._chave_natural(j ->> 'fonte', j ->> 'conta', j ->> 'entidade_tipo', j ->> 'entidade_id', v_grao,
                                  v_dims, j ->> 'metrica', j ->> 'value_kind', (j ->> 'janela_inicio')::timestamptz,
                                  (j ->> 'janela_fim')::timestamptz, j ->> 'timezone');
  v_base := dil_obs._chave_base(v_nat, j ->> 'payload_sha256', j ->> 'schema_version', j ->> 'coletor_nome',
                                j ->> 'coletor_versao', (j ->> 'observed_at')::timestamptz);
  IF v_nat IS NULL OR v_base IS NULL THEN
    RAISE EXCEPTION 'contrato: campo de identidade nulo' USING ERRCODE = 'DLC01';
  END IF;

  -- serializa escritores concorrentes do mesmo fato
  PERFORM pg_advisory_xact_lock(hashtextextended(v_nat, 0));

  SELECT * INTO v_exist FROM dil_obs.observacao WHERE chave_idempotencia = v_base;
  IF FOUND THEN
    IF (v_exist.status, v_exist.valor, v_exist.unidade, v_exist.moeda::text, v_exist.cobertura_ppm)
       IS DISTINCT FROM (j ->> 'status', v_valor, j ->> 'unidade', j ->> 'moeda', v_cob) THEN
      RAISE EXCEPTION 'conflito_idempotencia: mesma leitura com conteúdo diferente (coletor não determinístico)'
        USING ERRCODE = 'DLI01';
    END IF;
    RETURN 'noop';
  END IF;

  IF EXISTS (SELECT 1 FROM dil_obs.observacao WHERE chave_natural = v_nat AND available_at = v_avail) THEN
    RAISE EXCEPTION 'versao_ambigua: outra leitura do mesmo fato com o mesmo available_at' USING ERRCODE = 'DLV01';
  END IF;

  INSERT INTO dil_obs.observacao (
    chave_idempotencia, chave_natural, fonte, conta, entidade_tipo, entidade_id, grao,
    dimensoes, metrica, value_kind, valor, unidade, moeda, janela_inicio, janela_fim, timezone, observed_at,
    source_updated_at, available_at, ingested_at, run_id, request_id, lote_id, payload_sha256, payload_ref,
    schema_version, coletor_nome, coletor_versao, status, motivo, cobertura_ppm)
  VALUES (
    v_base, v_nat, j ->> 'fonte', j ->> 'conta', j ->> 'entidade_tipo', j ->> 'entidade_id', v_grao,
    v_dims, j ->> 'metrica', j ->> 'value_kind', v_valor, j ->> 'unidade', j ->> 'moeda',
    (j ->> 'janela_inicio')::timestamptz, (j ->> 'janela_fim')::timestamptz, j ->> 'timezone',
    (j ->> 'observed_at')::timestamptz, (j ->> 'source_updated_at')::timestamptz, v_avail,
    dil_obs._agora(),  -- relógio do banco: o escritor não declara quando escreveu
    j ->> 'run_id', j ->> 'request_id', j ->> 'lote_id', j ->> 'payload_sha256', j ->> 'payload_ref',
    j ->> 'schema_version', j ->> 'coletor_nome', j ->> 'coletor_versao', j ->> 'status', j ->> 'motivo', v_cob);
  RETURN 'inserido';
END $$;

-- ---------------------------------------------------------------------------
-- 5. Leitura as_of (SECURITY INVOKER: grants e RLS de quem chama valem)
-- ---------------------------------------------------------------------------
CREATE FUNCTION dil_obs.observacao_as_of(t timestamptz) RETURNS SETOF dil_obs.observacao
LANGUAGE sql STABLE STRICT SECURITY INVOKER SET search_path = ''
AS $$
  SELECT DISTINCT ON (o.chave_natural) o.*
    FROM dil_obs.observacao AS o
   WHERE o.available_at <= t
   ORDER BY o.chave_natural, o.observed_at DESC, o.available_at DESC, o.chave_idempotencia DESC
$$;
COMMENT ON FUNCTION dil_obs.observacao_as_of(timestamptz) IS
  'Estado conhecido em t: por chave_natural, entre as versões com available_at <= t, a de maior observed_at '
  '(empate: maior available_at; depois chave_idempotencia, inalcançável pelo UNIQUE). Status preservado.';

CREATE VIEW dil_obs.observacao_latest WITH (security_invoker = true) AS
  SELECT * FROM dil_obs.observacao_as_of(now());
COMMENT ON VIEW dil_obs.observacao_latest IS 'latest = as_of(now()). Derivada do histórico; não o substitui.';

-- ---------------------------------------------------------------------------
-- 6. RLS habilitado e forçado (o dono também obedece) + policies explícitas
-- ---------------------------------------------------------------------------
ALTER TABLE dil_obs.run_coleta ENABLE ROW LEVEL SECURITY;
ALTER TABLE dil_obs.run_coleta FORCE ROW LEVEL SECURITY;
ALTER TABLE dil_obs.payload_bruto ENABLE ROW LEVEL SECURITY;
ALTER TABLE dil_obs.payload_bruto FORCE ROW LEVEL SECURITY;
ALTER TABLE dil_obs.lote ENABLE ROW LEVEL SECURITY;
ALTER TABLE dil_obs.lote FORCE ROW LEVEL SECURITY;
ALTER TABLE dil_obs.observacao ENABLE ROW LEVEL SECURITY;
ALTER TABLE dil_obs.observacao FORCE ROW LEVEL SECURITY;
ALTER TABLE dil_obs.dead_letter ENABLE ROW LEVEL SECURITY;
ALTER TABLE dil_obs.dead_letter FORCE ROW LEVEL SECURITY;

CREATE POLICY pl_run_leitura ON dil_obs.run_coleta FOR SELECT TO dil_obs_leitor, dil_obs_dono USING (true);
CREATE POLICY pl_run_insercao ON dil_obs.run_coleta FOR INSERT TO dil_obs_dono WITH CHECK (status = 'running');
CREATE POLICY pl_run_fechamento ON dil_obs.run_coleta FOR UPDATE TO dil_obs_dono
  USING (status = 'running') WITH CHECK (status <> 'running');

CREATE POLICY pl_payload_leitura ON dil_obs.payload_bruto FOR SELECT TO dil_obs_leitor, dil_obs_dono USING (true);
CREATE POLICY pl_payload_insercao ON dil_obs.payload_bruto FOR INSERT TO dil_obs_dono WITH CHECK (true);

CREATE POLICY pl_lote_leitura ON dil_obs.lote FOR SELECT TO dil_obs_leitor, dil_obs_dono USING (true);
CREATE POLICY pl_lote_insercao ON dil_obs.lote FOR INSERT TO dil_obs_dono WITH CHECK (true);

CREATE POLICY pl_obs_leitura ON dil_obs.observacao FOR SELECT TO dil_obs_leitor, dil_obs_dono USING (true);
CREATE POLICY pl_obs_insercao ON dil_obs.observacao FOR INSERT TO dil_obs_dono WITH CHECK (true);

CREATE POLICY pl_dl_leitura ON dil_obs.dead_letter FOR SELECT TO dil_obs_leitor, dil_obs_dono USING (true);
CREATE POLICY pl_dl_insercao ON dil_obs.dead_letter FOR INSERT TO dil_obs_dono WITH CHECK (true);
-- Nenhuma policy de UPDATE/DELETE em observacao/payload_bruto/lote/dead_letter: além do trigger, RLS também nega.

-- ---------------------------------------------------------------------------
-- 7. Grants mínimos
-- ---------------------------------------------------------------------------
REVOKE ALL ON ALL TABLES IN SCHEMA dil_obs FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA dil_obs FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA dil_obs FROM PUBLIC;

-- Supabase traz anon/authenticated com default ACL aberto; aqui eles ficam sem nada, explicitamente.
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = r) THEN
      EXECUTE format('REVOKE ALL ON SCHEMA dil_obs FROM %I', r);
      EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA dil_obs FROM %I', r);
      EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA dil_obs FROM %I', r);
      EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA dil_obs FROM %I', r);
    END IF;
  END LOOP;
END $$;

GRANT USAGE ON SCHEMA dil_obs TO dil_obs_escritor, dil_obs_leitor;

GRANT EXECUTE ON FUNCTION
  dil_obs.registrar_run(text, text, text, text, timestamptz),
  dil_obs.finalizar_run(text, text, integer, integer, integer, integer, text),
  dil_obs.registrar_payload(text, bytea, text),
  dil_obs.registrar_lote(text, text, text, text, jsonb, timestamptz),
  dil_obs.registrar_dead_letter(text, text, text, text, jsonb),
  dil_obs.registrar_observacao(json)
TO dil_obs_escritor;

GRANT SELECT ON dil_obs.run_coleta, dil_obs.payload_bruto, dil_obs.lote, dil_obs.observacao, dil_obs.dead_letter,
                dil_obs.observacao_latest
TO dil_obs_leitor;
GRANT EXECUTE ON FUNCTION dil_obs.observacao_as_of(timestamptz) TO dil_obs_leitor;

RESET ROLE;
-- Fim da membresia temporária (R1-F2): quem aplicou não continua podendo agir como dono.
DO $$
BEGIN
  IF current_setting('dil_obs.revogar_dono', true) = 'sim'
     AND EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'dil_obs_dono') THEN
    EXECUTE format('REVOKE dil_obs_dono FROM %I', current_user);
  END IF;
END $$;

COMMIT;
