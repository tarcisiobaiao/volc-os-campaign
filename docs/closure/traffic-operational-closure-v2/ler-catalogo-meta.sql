-- =============================================================================
-- Leitura do catálogo do perfil CREATE_ONLY, para classificação
-- =============================================================================
-- Produz o JSON que `scripts/verificar_perfil_schema_meta.py --catalogo` lê.
--
-- ⚠️ SÓ LÊ. Nenhum `CREATE`, `ALTER`, `DROP`, `INSERT` ou `UPDATE` aparece aqui,
-- e nenhuma linha de dado sai: o que ele coleta são NOMES de coluna, constraint
-- e função, mais os grants. Rodá-lo contra um catálogo oficial exige a
-- autorização de leitura própria — este arquivo não a concede.
--
-- ⚠️ E ele NÃO pergunta "a tabela existe". Uma instalação com o CREATE_ONLY
-- antigo e uma com o perfil atual têm exatamente as mesmas três tabelas; o que
-- as separa são colunas, constraints, assinaturas e grants. Classificar por
-- existência de tabela foi o defeito que R0-A01 mediu.
--
-- Uso:  psql "$CONEXAO" -Atq -f ler-catalogo-meta.sql > catalogo.json
-- =============================================================================
SELECT jsonb_pretty(jsonb_build_object(
  'columns', (SELECT coalesce(jsonb_agg(c.rel || '.' || c.att), '[]'::jsonb) FROM (
      SELECT a.attrelid::regclass::text AS rel, a.attname AS att
        FROM pg_attribute a
       WHERE a.attrelid IN (to_regclass('public.trafego_meta_create_step'),
                            to_regclass('public.trafego_meta_create_approval'))
         AND a.attnum > 0 AND NOT a.attisdropped) c),
  'constraints', (SELECT coalesce(jsonb_agg(conname), '[]'::jsonb) FROM pg_constraint
     WHERE conrelid IN (to_regclass('public.trafego_meta_create_step'),
                        to_regclass('public.trafego_meta_create_approval'))),
  -- ⚠️ ASSINATURA DE IDENTIDADE, e não só o nome. Uma sobrecarga antiga viva ao
  -- lado da nova deixa o PostgREST sem conseguir escolher e as duas param de
  -- responder — sintoma que "a função existe" nunca detecta.
  'functions', (SELECT coalesce(jsonb_agg(
       p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')'), '[]'::jsonb)
     FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname LIKE 'trafego_meta%'),
  'security_definer', (SELECT coalesce(jsonb_agg(
       p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')'), '[]'::jsonb)
     FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname LIKE 'trafego_meta%' AND p.prosecdef),
  'granted', (SELECT coalesce(jsonb_agg(
       p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')'), '[]'::jsonb)
     FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname LIKE 'trafego_meta%'
      AND has_function_privilege(
        (SELECT oid FROM pg_roles WHERE rolname = 'service_role'), p.oid, 'EXECUTE'))
));
