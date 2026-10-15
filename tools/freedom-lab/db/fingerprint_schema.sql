-- =============================================================================
-- tools/freedom-lab/db/fingerprint_schema.sql — impressão digital do SCHEMA (nunca dos dados)
-- Mesmo arquivo roda na produção (leitura) e no laboratório: duas saídas iguais
-- = mesmo schema. Cada categoria tem seu md5, para a divergência dizer ONDE.
-- Lê só catálogo. Corpos de função entram como md5(prosrc), nunca em claro —
-- um corpo pode carregar URL ou cabeçalho de webhook.
-- =============================================================================
BEGIN READ ONLY;
SET LOCAL statement_timeout = '15s';

WITH esquemas AS (
  SELECT oid, nspname FROM pg_namespace
   WHERE nspname IN ('public','app_auth')          -- os do VOLC; auth/storage são da imagem
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
SELECT k AS categoria, count(*) AS itens, md5(string_agg(v, E'\n' ORDER BY v)) AS md5
  FROM cat GROUP BY k
UNION ALL
SELECT '_TOTAL', count(*), md5(string_agg(k || '=' || v, E'\n' ORDER BY k, v)) FROM cat
ORDER BY 1;

ROLLBACK;
