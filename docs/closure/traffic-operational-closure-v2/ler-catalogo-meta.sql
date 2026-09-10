-- =============================================================================
-- Leitura COMPLETA do catálogo do trilho Meta, para classificação de perfil
-- =============================================================================
-- Produz o JSON que `scripts/verificar_perfil_schema_meta.py --catalogo` lê.
--
-- ⚠️ SÓ LÊ. Nenhum `CREATE`, `ALTER`, `DROP`, `INSERT` ou `UPDATE` aparece aqui,
-- e nenhuma linha de dado sai: o que ele coleta são NOMES (relação, coluna,
-- constraint, índice, gatilho, política) mais assinaturas e ACLs. Rodá-lo
-- contra um catálogo oficial exige a autorização de leitura própria — este
-- arquivo não a concede.
--
-- ⚠️ E ele NÃO pergunta "a tabela existe". Uma instalação com o CREATE_ONLY
-- antigo e uma com o perfil atual têm exatamente as mesmas três tabelas; o que
-- as separa são COLUNA, CONSTRAINT, ASSINATURA e GRANT. Classificar por
-- existência de tabela foi o defeito que R0-A01 mediu.
--
-- ## O que mudou nesta versão, e por quê
--
-- A versão anterior tinha 45 linhas e DIGITAVA o conjunto a inspecionar: duas
-- tabelas, `trafego_meta_create_step` e `trafego_meta_create_approval`. Com
-- isso ela era cega para:
--
--   * `trafego_meta_validation_receipt`, a TERCEIRA tabela do CREATE_ONLY
--     (20260904183418_meta_create_paused_executor.sql:51);
--   * as NOVE tabelas do read model (v15_01_meta_ads_read_model.sql:46,61,93,
--     117,140,163,185,206,219) — entre elas `trafego_meta_project_binding`,
--     que a guarda de 20260907210000:141-147 também omite;
--   * as três tabelas de insight (v15_02_meta_ads_insights.sql:29,82,100) e as
--     colunas de grão que 20260907210000:231-239 acrescenta a elas;
--   * functions com retorno/`prosecdef`, grants de TABELA, índices e RLS.
--
-- Uma lista digitada envelhece em silêncio a cada migration nova — é o mesmo
-- defeito que o manifesto existe para não repetir. Aqui o conjunto é DERIVADO
-- do próprio catálogo, por prefixo do trilho Meta. As duas únicas exceções são
-- `public.cofre_ativo` e `public.cofre_cadastrar_ativo`, nomeadas porque as
-- guardas as nomeiam (v15_01 exige a primeira; 20260907210000:135-138 exige as
-- duas) — citar uma guarda não é digitar uma lista.
--
-- ⚠️ `LIKE 'trafego_meta%'` está SEM escapar o `_` de propósito: `_` casa um
-- caractere qualquer, o que aqui só alarga o casamento para nomes que não
-- existem, e escapar exigiria uma barra invertida que o `psql` pode confundir
-- com meta-comando quando ela cai no início de uma linha.
--
-- Uso:  psql "$CONEXAO" -Atq -f ler-catalogo-meta.sql > catalogo.json
-- =============================================================================
\set ON_ERROR_STOP on

WITH relacoes AS (
  -- 'r' tabela, 'p' particionada, 'v' view, 'm' view materializada. A view
  -- entra porque `vw_trafego_meta_insight_latest` (20260907210000:398) é o
  -- objeto que distingue um catálogo com a projeção do atual de um sem ela.
  SELECT c.oid,
         c.relname,
         c.relkind,
         c.relrowsecurity,
         c.relforcerowsecurity,
         c.relacl
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public'
     AND c.relkind IN ('r', 'p', 'v', 'm')
     AND (c.relname LIKE 'trafego_meta%'
          OR c.relname LIKE 'vw_trafego_meta%'
          OR c.relname = 'cofre_ativo')
),
funcoes AS (
  -- ⚠️ ASSINATURA DE IDENTIDADE, e não só o nome. Uma sobrecarga antiga viva ao
  -- lado da nova deixa o PostgREST sem conseguir escolher (PGRST203) e as duas
  -- param de responder — sintoma que "a função existe" nunca detecta.
  SELECT p.oid,
         p.proname,
         p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')' AS assinatura,
         pg_get_function_result(p.oid) AS retorno,
         p.prosecdef,
         l.lanname,
         p.proacl
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    JOIN pg_language l ON l.oid = p.prolang
   WHERE n.nspname = 'public'
     AND (p.proname LIKE 'trafego_meta%' OR p.proname = 'cofre_cadastrar_ativo')
)
SELECT jsonb_pretty(jsonb_build_object(

  -- Proveniência da própria leitura. Sem isto, dois catálogos lidos em momentos
  -- diferentes ficam indistinguíveis dentro de um recibo.
  'lido_em', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
  'server_version', current_setting('server_version'),
  'derivacao', 'relacoes: public.trafego_meta% | public.vw_trafego_meta% | public.cofre_ativo; funcoes: public.trafego_meta% | public.cofre_cadastrar_ativo',

  -- Existência de relação NÃO classifica nada sozinha (é o invariante do
  -- R0-A01). Ela vai no JSON só para o recibo dizer o que foi visto.
  'relations', (SELECT coalesce(jsonb_agg(r.relname::text || ':' || r.relkind::text ORDER BY r.relname), '[]'::jsonb)
                  FROM relacoes r),

  'columns', (SELECT coalesce(jsonb_agg(r.relname || '.' || a.attname ORDER BY r.relname, a.attnum), '[]'::jsonb)
                FROM relacoes r
                JOIN pg_attribute a ON a.attrelid = r.oid
               WHERE a.attnum > 0 AND NOT a.attisdropped),

  'constraints', (SELECT coalesce(jsonb_agg(k.conname ORDER BY k.conname), '[]'::jsonb)
                    FROM relacoes r
                    JOIN pg_constraint k ON k.conrelid = r.oid),

  -- Índices são fato de schema, não detalhe: `trafego_meta_project_binding_ativo_ux`
  -- (v15_01:113) é o que impede duas ligações vivas da MESMA conta, e
  -- `trafego_meta_insight_grao_corrente_ix` (20260907210000:386) é o que torna
  -- a projeção do atual barata. Nenhum dos dois aparece em `constraints`.
  'indexes', (SELECT coalesce(jsonb_agg(r.relname || '.' || ic.relname ORDER BY r.relname, ic.relname), '[]'::jsonb)
                FROM relacoes r
                JOIN pg_index i ON i.indrelid = r.oid
                JOIN pg_class ic ON ic.oid = i.indexrelid),

  -- Gatilhos internos (os de FK) ficam de fora: eles são consequência da
  -- constraint, e já estão em `constraints`. O que interessa são os declarados
  -- — `_sem_delete` (v15_01:278) e `_sem_truncate` (20260907210000:511), que é
  -- o único que separa v15_02 aplicada de 20260907210000 aplicada.
  'triggers', (SELECT coalesce(jsonb_agg(r.relname || '.' || t.tgname ORDER BY r.relname, t.tgname), '[]'::jsonb)
                 FROM relacoes r
                 JOIN pg_trigger t ON t.tgrelid = r.oid
                WHERE NOT t.tgisinternal),

  -- `FORCE ROW LEVEL SECURITY` sujeita o DONO à RLS, e nenhuma destas tabelas
  -- tem policy. Ler `enabled` sem `forced` não distingue um schema contido de
  -- um em que o dono atravessa tudo.
  'rls', jsonb_build_object(
    'enabled', (SELECT coalesce(jsonb_agg(r.relname ORDER BY r.relname), '[]'::jsonb)
                  FROM relacoes r WHERE r.relrowsecurity),
    'forced', (SELECT coalesce(jsonb_agg(r.relname ORDER BY r.relname), '[]'::jsonb)
                 FROM relacoes r WHERE r.relforcerowsecurity),
    'policies', (SELECT coalesce(jsonb_agg(r.relname || '.' || pol.polname ORDER BY r.relname, pol.polname), '[]'::jsonb)
                   FROM relacoes r
                   JOIN pg_policy pol ON pol.polrelid = r.oid)),

  -- Contrato consumido pelo verificador: lista de assinaturas, texto puro.
  'functions', (SELECT coalesce(jsonb_agg(f.assinatura ORDER BY f.assinatura), '[]'::jsonb)
                  FROM funcoes f),

  -- ⚠️ `functions` continua sendo LISTA DE STRING porque
  -- `conferir_contrato_no_catalogo` compara assinatura contra assinatura.
  -- Retorno, linguagem e `prosecdef` vão em campo separado para não quebrar
  -- esse contrato — e porque um retorno trocado (jsonb -> void) é uma
  -- divergência que a assinatura de identidade não enxerga.
  'functions_detail', (SELECT coalesce(jsonb_agg(jsonb_build_object(
         'name', f.proname,
         'signature', f.assinatura,
         'returns', f.retorno,
         'language', f.lanname,
         'security_definer', f.prosecdef) ORDER BY f.assinatura), '[]'::jsonb)
       FROM funcoes f),

  'security_definer', (SELECT coalesce(jsonb_agg(f.assinatura ORDER BY f.assinatura), '[]'::jsonb)
                         FROM funcoes f WHERE f.prosecdef),

  -- EXECUTE efetivo para service_role, respeitando herança de papel e o que foi
  -- concedido a PUBLIC. Se o papel não existir, a subconsulta é NULL,
  -- `has_function_privilege` é estrita e a lista sai vazia — que é a resposta
  -- correta para "um banco sem os papéis Supabase".
  'granted', (SELECT coalesce(jsonb_agg(f.assinatura ORDER BY f.assinatura), '[]'::jsonb)
                FROM funcoes f
               WHERE has_function_privilege(
                       (SELECT oid FROM pg_roles WHERE rolname = 'service_role'),
                       f.oid, 'EXECUTE')),

  -- ACL explícita, achatada em "<objeto>:<papel>:<PRIVILEGIO>", de TABELA e de
  -- FUNÇÃO no mesmo formato. É isto que distingue v15_02 aplicada (INSERT e
  -- UPDATE para service_role nas tabelas de insight, v15_02:123-125) de
  -- 20260907210000 aplicada (REVOKE ALL e só SELECT, linhas 486-489) — duas
  -- instalações com exatamente as mesmas tabelas e as mesmas colunas.
  --
  -- ⚠️ `relacl`/`proacl` NULO significa "privilégios default": o dono tem tudo
  -- e nada foi concedido nominalmente. `coalesce` para array vazio traduz isso
  -- como AUSÊNCIA de grant, que é o que ele é.
  'grants', (SELECT coalesce(jsonb_agg(g ORDER BY g), '[]'::jsonb) FROM (
       SELECT r.relname || ':'
              || CASE WHEN acl.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(acl.grantee) END
              || ':' || acl.privilege_type AS g
         FROM relacoes r,
              LATERAL aclexplode(coalesce(r.relacl, '{}'::aclitem[])) AS acl
       UNION ALL
       SELECT f.assinatura || ':'
              || CASE WHEN acl.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(acl.grantee) END
              || ':' || acl.privilege_type
         FROM funcoes f,
              LATERAL aclexplode(coalesce(f.proacl, '{}'::aclitem[])) AS acl) AS todos)
));
