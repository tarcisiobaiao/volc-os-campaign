-- db/suites/v19_10_apoio.sql — apoio da suíte v19_10 (authenticated mínimo).
-- Vive só no schema volc_lab do container do laboratório (fora do fingerprint
-- de public+app_auth) e morre com ele. Nunca vai para produção.
--
-- volc_lab.sql_minimo(rel, op) monta um comando que exercita o PRIVILÉGIO de
-- uma operação numa relação: INSERT de uma linha mínima (cada coluna NOT NULL
-- sem default recebe um valor do seu tipo), UPDATE/DELETE que casam 0 linhas e
-- SELECT limitado. A suíte roda o mesmo comando como service_role (referência:
-- o backend) e como authenticated; o veredito compara os SQLSTATE. Igual =
-- o papel do browser se comporta como o backend; 42501 só no authenticated =
-- privilégio faltando.
CREATE SCHEMA IF NOT EXISTS volc_lab;

CREATE OR REPLACE FUNCTION volc_lab.valor_minimo(t oid, tm int) RETURNS text
LANGUAGE plpgsql STABLE AS $$
DECLARE r text; tipo text := format_type(t, tm); base oid;
BEGIN
  SELECT typbasetype INTO base FROM pg_type WHERE oid = t AND typtype = 'd';
  IF base IS NOT NULL AND base <> 0 THEN RETURN volc_lab.valor_minimo(base, tm); END IF;
  IF EXISTS (SELECT 1 FROM pg_type WHERE oid = t AND typtype = 'e') THEN
    SELECT quote_literal(enumlabel) || '::' || tipo INTO r FROM pg_enum WHERE enumtypid = t ORDER BY enumsortorder LIMIT 1;
    RETURN r;
  END IF;
  RETURN CASE
    WHEN tipo IN ('integer','bigint','smallint','numeric','real','double precision') OR tipo LIKE 'numeric(%' THEN '1'
    WHEN tipo IN ('boolean') THEN 'false'
    WHEN tipo = 'uuid' THEN 'gen_random_uuid()'
    WHEN tipo = 'date' THEN 'current_date'
    WHEN tipo LIKE 'timestamp%' THEN 'now()'
    WHEN tipo LIKE 'time%' THEN 'now()::time'
    WHEN tipo IN ('json','jsonb') THEN quote_literal('{}') || '::' || tipo
    WHEN tipo LIKE '%[]' THEN quote_literal('{}') || '::' || tipo
    WHEN tipo LIKE 'character(%' OR tipo = 'character' THEN quote_literal('w')
    ELSE quote_literal('w4') || '::' || tipo
  END;
END $$;

CREATE OR REPLACE FUNCTION volc_lab.sql_minimo(rel regclass, op text) RETURNS text
LANGUAGE plpgsql STABLE AS $$
DECLARE cols text; vals text;
BEGIN
  IF op = 'select' THEN RETURN format('SELECT count(*) FROM (SELECT 1 FROM %s LIMIT 1) x', rel); END IF;
  IF op = 'update' THEN
    SELECT format('UPDATE %s SET %I = %I WHERE false', rel, attname, attname) INTO cols
      FROM pg_attribute WHERE attrelid = rel AND attnum > 0 AND NOT attisdropped AND attgenerated = '' AND attidentity = ''
     ORDER BY attnum LIMIT 1;
    RETURN cols;
  END IF;
  IF op = 'delete' THEN RETURN format('DELETE FROM %s WHERE false', rel); END IF;
  IF op = 'insert' THEN
    SELECT string_agg(quote_ident(a.attname), ', ' ORDER BY a.attnum),
           string_agg(volc_lab.valor_minimo(a.atttypid, a.atttypmod), ', ' ORDER BY a.attnum)
      INTO cols, vals
      FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
     WHERE a.attrelid = rel AND a.attnum > 0 AND NOT a.attisdropped
       AND a.attnotnull AND d.adbin IS NULL AND a.attidentity = '' AND a.attgenerated = '';
    IF cols IS NULL THEN RETURN format('INSERT INTO %s DEFAULT VALUES', rel); END IF;
    RETURN format('INSERT INTO %s (%s) VALUES (%s)', rel, cols, vals);
  END IF;
  RAISE EXCEPTION 'op desconhecida: %', op;
END $$;

GRANT USAGE ON SCHEMA volc_lab TO postgres;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA volc_lab TO postgres;

-- volc_lab.sql_rpc(nome): chamada de uma RPC de public com argumentos plausíveis
-- por tipo (datas = últimos 30 dias, inteiros = 1, texto = 'w4'), como o
-- frontend faria. Funções sobrecarregadas: usa a de mais argumentos.
CREATE OR REPLACE FUNCTION volc_lab.sql_rpc(nome text) RETURNS text
LANGUAGE plpgsql STABLE AS $$
DECLARE p record; args text := ''; i int; t oid; n int;
BEGIN
  SELECT pr.oid, pr.proargtypes, pr.pronargs, pr.proname, pr.proretset INTO p
    FROM pg_proc pr WHERE pr.pronamespace = 'public'::regnamespace AND pr.proname = nome
   ORDER BY pr.pronargs DESC LIMIT 1;
  IF p.oid IS NULL THEN RETURN NULL; END IF;
  n := 0;
  FOR i IN 0 .. p.pronargs - 1 LOOP
    t := p.proargtypes[i];
    n := n + 1;
    args := args || CASE WHEN i > 0 THEN ', ' ELSE '' END ||
      CASE format_type(t, NULL)
        WHEN 'date' THEN CASE WHEN n = 1 THEN '(current_date - 30)' ELSE 'current_date' END
        ELSE volc_lab.valor_minimo(t, -1) || '::' || format_type(t, NULL) END;
  END LOOP;
  RETURN format('SELECT count(*) FROM (SELECT %s public.%I(%s)) x',
                CASE WHEN p.proretset THEN '* FROM' ELSE '' END, nome, args);
END $$;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA volc_lab TO postgres;
