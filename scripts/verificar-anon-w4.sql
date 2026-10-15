-- =============================================================================
-- verificar-anon-w4.sql — o anon alcança dado em public? SOMENTE LEITURA.
-- Pacote do incidente anon (W4). Usado ANTES (tem de dar ABERTO: prova que o
-- instrumento enxerga o buraco) e DEPOIS do passo 1 (tem de dar FECHADO).
--
-- Roda como postgres (membro de anon, como na sonda autorizada de 15/10), com
-- default_transaction_read_only=on na conexão e BEGIN READ ONLY … ROLLBACK.
-- Testa como anon DE VERDADE: SET LOCAL ROLE anon e SELECT real em cada relação
-- que o catálogo diz legível, sob a RLS de anon. Devolve só contagens.
-- Por que não supabase_read_only_user: ele não é membro de anon — o SET ROLE
-- falha e uma sonda ingênua mostra "zero" no estado inseguro (revisão de 15/10).
-- Veredito (quem chama decide): FECHADO ⇔ V1 = V2 = V4 = 0 (e V3 = 0 depois da
-- v19_02). Qualquer outro resultado é ABERTO.
-- =============================================================================
BEGIN READ ONLY;
SET LOCAL statement_timeout = '30s';
SET LOCAL search_path = pg_catalog;

WITH legiveis AS (
  SELECT c.oid
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','f')
     AND has_table_privilege('anon', c.oid, 'SELECT')
)
SELECT 'V1' AS item, 'relacoes_com_privilegio_de_anon' AS medida,
       (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','f')
           AND has_table_privilege('anon', c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'))::text AS valor
UNION ALL
SELECT 'V2', 'colunas_com_privilegio_de_anon',
       (SELECT count(*) FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','f')
           AND a.attnum > 0 AND NOT a.attisdropped
           AND has_column_privilege('anon', c.oid, a.attnum, 'SELECT,INSERT,UPDATE,REFERENCES'))::text
UNION ALL
SELECT 'V3', 'default_acl_de_public_com_anon',
       (SELECT count(*) FROM pg_default_acl d, aclexplode(d.defaclacl) x
         WHERE d.defaclnamespace = 'public'::regnamespace AND x.grantee = 'anon'::regrole)::text
UNION ALL
SELECT 'V0', 'relacoes_legiveis_por_anon_no_catalogo', (SELECT count(*) FROM legiveis)::text;

-- V4: SELECT real como anon. Só nas relações que o catálogo diz legíveis (as
-- outras dariam 42501 e abortariam a transação); a RLS de anon decide o resto.
SET LOCAL ROLE anon;
SELECT 'V4' AS item, 'relacoes_onde_anon_ve_linha' AS medida,
       count(*) FILTER (WHERE (xpath('/row/e/text()',
         query_to_xml(format('SELECT EXISTS (SELECT 1 FROM %s) AS e', c.oid::regclass), false, true, '')))[1]::text = 'true')::text AS valor
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','f')
   AND has_table_privilege('anon', c.oid, 'SELECT');
RESET ROLE;

ROLLBACK;
