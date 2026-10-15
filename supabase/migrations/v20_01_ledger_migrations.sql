-- =============================================================================
-- v20_01_ledger_migrations.sql — CANDIDATA, NÃO APLICADA
--
-- O banco oficial não tem ledger de migrations do VOLC (medido em 15/10/2026,
-- handoffs/freedom-lab-20261015/B-banco.md §0, seção S1 da sonda): tudo foi
-- aplicado à mão e o único registro é supabase/migrations/README.md.
--
-- Esta migration cria o ledger como um LOG DE EVENTOS append-only:
--
--   volc_ops.migracao_evento   uma linha por ato: linha_de_base, aplicar, reverter
--   volc_ops.migracao_estado   view: o último evento de cada versão
--   volc_ops.fingerprint_schema()  o mesmo cálculo de B-fingerprint.sql /
--                              tools/freedom-lab/db/fingerprint_schema.sql
--
-- Por que um schema próprio (volc_ops) e não public:
--   1. o fingerprint de produção (695e913a…) cobre só public + app_auth. Criar o
--      ledger fora deles mantém a âncora válida: o backfill (v20_02) mede o
--      fingerprint DEPOIS desta migration e ele tem de continuar igual;
--   2. o default ACL quebrado de public (S10: tabela nova nasce arwdDxt para
--      anon/authenticated) não alcança outro schema; mesmo assim tudo aqui é
--      fechado por REVOKE nominal, sem depender disso.
--
-- As guardas moram no banco (gatilho), não só no script que aplica:
--   · aplicar/linha_de_base de versão já aplicada            → P0001
--   · aplicar de versão já registrada com OUTRO sha256       → P0001
--   · reverter versão que não está aplicada                   → P0001
--   · reverter com rollback cujo sha256 diverge do aprovado   → P0001
--   · UPDATE, DELETE e TRUNCATE no log                        → P0001
-- Concorrência: pg_advisory_xact_lock por versão serializa dois aplicadores.
--
-- Rollback: v20_01_rollback.sql (recusa se o ledger registrar algo além da
-- própria linha de base).
-- =============================================================================
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

DO $$
BEGIN
  IF to_regnamespace('volc_ops') IS NOT NULL THEN
    RAISE EXCEPTION 'v20_01: schema volc_ops já existe — ledger já criado ou nome em uso; nada feito';
  END IF;
END $$;

CREATE SCHEMA volc_ops;
COMMENT ON SCHEMA volc_ops IS
  'Operação do VOLC O.S. fora de public. Contém o ledger de migrations (v20_01).';
REVOKE ALL ON SCHEMA volc_ops FROM PUBLIC;
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('REVOKE ALL ON SCHEMA volc_ops FROM %I', r);
    END IF;
  END LOOP;
END $$;

CREATE TABLE volc_ops.migracao_evento (
  id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  versao           text        NOT NULL CHECK (versao ~ '^[A-Za-z0-9_.-]{3,120}$'),
  operacao         text        NOT NULL CHECK (operacao IN ('linha_de_base','aplicar','reverter')),
  -- aplicar: o arquivo da migration; reverter: o arquivo de rollback executado;
  -- linha_de_base: o artefato que ancora (ex.: a saída do fingerprint)
  arquivo          text        NOT NULL,
  sha256           text        NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  -- o par de reversão aprovado junto com a aplicação (NULL = sem rollback)
  rollback_arquivo text,
  rollback_sha256  text        CHECK (rollback_sha256 ~ '^[0-9a-f]{64}$'),
  aprovador        text        NOT NULL CHECK (length(btrim(aprovador)) > 0),
  aprovado_em      date,
  -- md5 _TOTAL de fingerprint_schema() medido antes do ato (âncora da linha de base)
  fingerprint      text        CHECK (fingerprint ~ '^[0-9a-f]{32}$'),
  evidencia        text,
  executor         text        NOT NULL DEFAULT session_user,
  registrado_em    timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT migracao_evento_rollback_par
    CHECK ((rollback_arquivo IS NULL) = (rollback_sha256 IS NULL)),
  CONSTRAINT migracao_evento_reverter_sem_par
    CHECK (operacao <> 'reverter' OR rollback_arquivo IS NULL)
);
COMMENT ON TABLE volc_ops.migracao_evento IS
  'Ledger append-only de migrations do VOLC (v20_01). Estado atual: volc_ops.migracao_estado.';
CREATE INDEX migracao_evento_versao_id ON volc_ops.migracao_evento (versao, id DESC);

CREATE FUNCTION volc_ops.migracao_evento_guarda() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $f$
DECLARE
  ult      volc_ops.migracao_evento;
  ult_apl  volc_ops.migracao_evento;
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'volc_ops.migracao_evento é append-only: % recusado', TG_OP
      USING ERRCODE = 'P0001';
  END IF;

  -- dois aplicadores da mesma versão não passam juntos pela checagem abaixo
  PERFORM pg_advisory_xact_lock(hashtextextended('volc_ops.migracao:' || NEW.versao, 0));

  SELECT * INTO ult FROM volc_ops.migracao_evento
   WHERE versao = NEW.versao ORDER BY id DESC LIMIT 1;

  IF NEW.operacao IN ('aplicar','linha_de_base') THEN
    IF ult.operacao IN ('aplicar','linha_de_base') THEN
      RAISE EXCEPTION 'migração % já aplicada (evento %, %, sha256 %): reaplicação recusada',
        NEW.versao, ult.id, ult.operacao, ult.sha256 USING ERRCODE = 'P0001';
    END IF;
    -- o nome é a identidade: outro conteúdo com o mesmo nome é outra migration
    SELECT * INTO ult_apl FROM volc_ops.migracao_evento
     WHERE versao = NEW.versao AND operacao IN ('aplicar','linha_de_base')
     ORDER BY id DESC LIMIT 1;
    IF ult_apl.id IS NOT NULL AND ult_apl.sha256 <> NEW.sha256 THEN
      RAISE EXCEPTION 'migração % já foi registrada com sha256 % e agora chega com %: hash divergente recusado',
        NEW.versao, ult_apl.sha256, NEW.sha256 USING ERRCODE = 'P0001';
    END IF;
  ELSE -- reverter
    IF ult.id IS NULL OR ult.operacao = 'reverter' THEN
      RAISE EXCEPTION 'migração % não está aplicada: reversão recusada', NEW.versao
        USING ERRCODE = 'P0001';
    END IF;
    IF ult.rollback_sha256 IS NOT NULL AND ult.rollback_sha256 <> NEW.sha256 THEN
      RAISE EXCEPTION 'rollback de % chega com sha256 %, mas o aprovado na aplicação (evento %) é %: recusado',
        NEW.versao, NEW.sha256, ult.id, ult.rollback_sha256 USING ERRCODE = 'P0001';
    END IF;
  END IF;
  RETURN NEW;
END $f$;

CREATE TRIGGER migracao_evento_guarda
  BEFORE INSERT OR UPDATE OR DELETE ON volc_ops.migracao_evento
  FOR EACH ROW EXECUTE FUNCTION volc_ops.migracao_evento_guarda();
CREATE TRIGGER migracao_evento_sem_truncate
  BEFORE TRUNCATE ON volc_ops.migracao_evento
  FOR EACH STATEMENT EXECUTE FUNCTION volc_ops.migracao_evento_guarda();

-- estado = último evento; sha256/rollback = os da última aplicação (ou linha de
-- base), mesmo quando o último evento é uma reversão.
CREATE VIEW volc_ops.migracao_estado AS
  SELECT DISTINCT ON (e.versao)
         e.versao,
         CASE WHEN e.operacao = 'reverter' THEN 'revertida' ELSE 'aplicada' END AS estado,
         e.operacao AS ultimo_evento, e.id AS evento_id,
         a.arquivo, a.sha256, a.rollback_arquivo, a.rollback_sha256,
         e.aprovador, e.registrado_em
    FROM volc_ops.migracao_evento e
    LEFT JOIN LATERAL (
      SELECT x.arquivo, x.sha256, x.rollback_arquivo, x.rollback_sha256
        FROM volc_ops.migracao_evento x
       WHERE x.versao = e.versao AND x.operacao <> 'reverter'
       ORDER BY x.id DESC LIMIT 1) a ON true
   ORDER BY e.versao, e.id DESC;

-- Mesmo cálculo de tools/freedom-lab/db/fingerprint_schema.sql (= B-fingerprint.sql),
-- como função para o protocolo medir antes/depois sem copiar SQL. Lê só catálogo.
-- Corpos de função entram como md5, nunca em claro.
--
-- search_path: o MESMO da sessão em que o script é medido (psql -U postgres na
-- imagem supabase/postgres 15.8, onde pg_db_role_setting dá ao papel postgres
-- "$user", public, extensions). pg_get_viewdef, pg_get_triggerdef,
-- pg_get_indexdef, pg_get_constraintdef, pg_get_expr e format_type qualificam
-- todo nome que não está visível no search_path; com pg_catalog só, views,
-- gatilhos, índices, FKs e defaults saíam como "public.x"/"extensions.f()" e o
-- md5 nunca batia com o 695e913a… medido pelo script — a v20_02 recusaria sempre.
-- Fixo (e não herdado do chamador) para que dois eventos do ledger medidos em
-- sessões diferentes sejam comparáveis.
CREATE FUNCTION volc_ops.fingerprint_schema()
RETURNS TABLE (categoria text, itens bigint, md5 text)
LANGUAGE sql STABLE SET search_path = "$user", public, extensions AS $f$
WITH esquemas AS (
  SELECT oid, nspname FROM pg_namespace
   WHERE nspname IN ('public','app_auth')
), cat AS (
  SELECT 'tabelas' AS k, format('%s.%s|%s|rls=%s|force=%s|opts=%s', n.nspname, c.relname, c.relkind,
                                c.relrowsecurity, c.relforcerowsecurity, coalesce(array_to_string(c.reloptions, ','), '')) AS v
    FROM pg_class c JOIN esquemas n ON n.oid = c.relnamespace
   WHERE c.relkind IN ('r','p','v','m','f','S')
  UNION ALL
  SELECT 'colunas', format('%s.%s.%s|%s|nn=%s|def=%s', n.nspname, c.relname, a.attname,
                           format_type(a.atttypid, a.atttypmod), a.attnotnull, md5(coalesce(pg_get_expr(d.adbin, d.adrelid), '')))
    FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN esquemas n ON n.oid = c.relnamespace
    LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
   WHERE a.attnum > 0 AND NOT a.attisdropped AND c.relkind IN ('r','p','v','m','f')
  UNION ALL
  SELECT 'constraints', format('%s.%s.%s|%s', n.nspname, c.relname, k.conname, pg_get_constraintdef(k.oid))
    FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid JOIN esquemas n ON n.oid = c.relnamespace
  UNION ALL
  SELECT 'indices', format('%s|%s', n.nspname, regexp_replace(pg_get_indexdef(i.indexrelid), '\s+', ' ', 'g'))
    FROM pg_index i JOIN pg_class c ON c.oid = i.indrelid JOIN esquemas n ON n.oid = c.relnamespace
  UNION ALL
  SELECT 'views', format('%s.%s|%s', n.nspname, c.relname, md5(pg_get_viewdef(c.oid, true)))
    FROM pg_class c JOIN esquemas n ON n.oid = c.relnamespace WHERE c.relkind IN ('v','m')
  UNION ALL
  SELECT 'funcoes', format('%s.%s(%s)|ret=%s|definer=%s|vol=%s|cfg=%s|src=%s', n.nspname, p.proname,
                           pg_get_function_identity_arguments(p.oid), pg_get_function_result(p.oid),
                           p.prosecdef, p.provolatile, coalesce(array_to_string(p.proconfig, ','), ''), md5(p.prosrc))
    FROM pg_proc p JOIN esquemas n ON n.oid = p.pronamespace
  UNION ALL
  SELECT 'gatilhos', format('%s.%s.%s|%s', n.nspname, c.relname, t.tgname, md5(pg_get_triggerdef(t.oid)))
    FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid JOIN esquemas n ON n.oid = c.relnamespace
   WHERE NOT t.tgisinternal
  UNION ALL
  SELECT 'policies', format('%s.%s.%s|cmd=%s|perm=%s|roles=%s|q=%s|c=%s', n.nspname, c.relname, p.polname,
                            p.polcmd, p.polpermissive,
                            (SELECT string_agg(CASE WHEN r = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(r) END, ',' ORDER BY 1)
                               FROM unnest(p.polroles) r),
                            md5(coalesce(pg_get_expr(p.polqual, p.polrelid), '')),
                            md5(coalesce(pg_get_expr(p.polwithcheck, p.polrelid), '')))
    FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid JOIN esquemas n ON n.oid = c.relnamespace
  UNION ALL
  SELECT 'grants', format('%s.%s|%s', n.nspname, c.relname,
                          (SELECT string_agg(x::text, ',' ORDER BY x::text) FROM unnest(c.relacl) x))
    FROM pg_class c JOIN esquemas n ON n.oid = c.relnamespace
   WHERE c.relkind IN ('r','p','v','m','f','S')
  UNION ALL
  SELECT 'grants_funcao', format('%s.%s(%s)|%s', n.nspname, p.proname, pg_get_function_identity_arguments(p.oid),
                                 coalesce((SELECT string_agg(x::text, ',' ORDER BY x::text) FROM unnest(p.proacl) x), 'default'))
    FROM pg_proc p JOIN esquemas n ON n.oid = p.pronamespace
  UNION ALL
  SELECT 'extensoes', format('%s|%s', e.extname, e.extversion) FROM pg_extension e
)
SELECT k, count(*), md5(string_agg(v, E'\n' ORDER BY v)) FROM cat GROUP BY k
UNION ALL
SELECT '_TOTAL', count(*), md5(string_agg(k || '=' || v, E'\n' ORDER BY k, v)) FROM cat
ORDER BY 1;
$f$;

-- Fechado para todo papel de API. Quem aplica migration é o dono (postgres).
REVOKE ALL ON ALL TABLES    IN SCHEMA volc_ops FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA volc_ops FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA volc_ops FROM PUBLIC;
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('REVOKE ALL ON ALL TABLES    IN SCHEMA volc_ops FROM %I', r);
      EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA volc_ops FROM %I', r);
      EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA volc_ops FROM %I', r);
    END IF;
  END LOOP;
END $$;

-- Postflight dentro da transação: nada aqui pode estar aberto a papel de API.
DO $$
DECLARE r text; n int;
BEGIN
  FOREACH r IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
    CONTINUE WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r);
    IF has_schema_privilege(r, 'volc_ops', 'USAGE') THEN
      RAISE EXCEPTION 'v20_01 postflight: % tem USAGE em volc_ops', r;
    END IF;
    SELECT count(*) INTO n FROM pg_class c
     WHERE c.relnamespace = 'volc_ops'::regnamespace AND c.relkind IN ('r','v','S')
       AND (has_table_privilege(r, c.oid, 'SELECT') OR has_table_privilege(r, c.oid, 'INSERT')
            OR has_table_privilege(r, c.oid, 'UPDATE') OR has_table_privilege(r, c.oid, 'DELETE'));
    IF n > 0 THEN
      RAISE EXCEPTION 'v20_01 postflight: % alcança % objeto(s) de volc_ops', r, n;
    END IF;
  END LOOP;
END $$;

COMMIT;
