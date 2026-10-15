-- =============================================================================
-- v18_01_identidade_leitura_minima.sql — CANDIDATA (Freedom Lab, 15/10/2026) · prova: tools/freedom-lab/lab.sh recriar
-- NÃO APLICAR EM PRODUÇÃO sem: prova no laboratório, sonda S7 lida, sha256
-- aprovado nominalmente pelo Tarcísio. Autor: Leitor B (handoff, fora do repo).
-- =============================================================================
--
-- O QUE CRIA
--   volc_leitura         NOLOGIN, NOBYPASSRLS — o grupo que carrega os grants
--   volc_leitura_agente  LOGIN SEM SENHA, herda só volc_leitura — a identidade
--                        que os workers usam. A senha é definida fora do
--                        arquivo, pelo operador (\password), e nunca versionada.
--
-- POR QUE NOMES NOVOS, E NÃO "CONSERTAR" volc_leitor / supabase_read_only_user
--   Os dois papéis antigos podem ter consumidores fora do repositório (n8n,
--   Studio, scripts manuais). Alterar BYPASSRLS de um papel com consumidor
--   desconhecido quebra esse consumidor em silêncio: ele passa a ler zero
--   linhas sob RLS forçada, sem erro. Esta migration não toca neles. Aposentá-los
--   é decisão separada, depois de provar ausência de conexões (log_connections).
--   supabase_read_only_user, além disso, é papel da imagem do Supabase.
--
-- O QUE A IDENTIDADE PODE
--   · USAGE em public; SELECT apenas na lista nominal abaixo (allowlist);
--   · em tabela com RLS, uma policy SELECT TO volc_leitura USING (true) — sem
--     ela, RLS forçada sem policy devolve zero linhas (falso "vazio");
--   · nada mais: nenhum INSERT/UPDATE/DELETE/TRUNCATE, nenhum CREATE, nenhuma
--     herança de pg_read_all_data (que atravessaria GRANT e lista).
--
-- O QUE ELA NÃO RESOLVE — dito sem rodeio
--   1. default_transaction_read_only=on é DEFESA EM PROFUNDIDADE, não barreira:
--      a própria sessão pode desligá-lo. A barreira é a ausência de grant.
--   2. Funções SECURITY DEFINER com EXECUTE para PUBLIC continuam executáveis
--      por esta identidade (PUBLIC não se revoga papel a papel). A sonda S9
--      lista quais são; o fechamento é uma v18_02 separada, que troca
--      "PUBLIC" por grants nominais a anon/authenticated/service_role.
--   3. Views sem security_invoker rodam com o privilégio do DONO: liberar uma
--      delas libera tudo que o dono vê por baixo. Por isso views entram na
--      allowlist só depois de lidas uma a uma.
--
-- Papel de aplicação: postgres (dono das tabelas trafego_*/google_ads_*).
-- Tabela de outro dono na allowlist ABORTA com o nome dela.
-- =============================================================================
BEGIN;

-- ---------------------------------------------------------------------------
-- 0. Guardas
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN ('volc_leitura','volc_leitura_agente')) THEN
    RAISE EXCEPTION 'v18_01: volc_leitura ou volc_leitura_agente já existe — esta migration não reaplica por cima (rode o rollback antes)';
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 1. Papéis
-- ---------------------------------------------------------------------------
CREATE ROLE volc_leitura NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOREPLICATION NOBYPASSRLS;
COMMENT ON ROLE volc_leitura IS
  'v18_01 · grupo de leitura mínima do VOLC O.S. · SELECT por allowlist · sem BYPASSRLS';

-- LOGIN sem PASSWORD: ninguém entra até o operador definir a senha fora do
-- repositório. INHERIT para receber os grants de volc_leitura.
CREATE ROLE volc_leitura_agente LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 5 IN ROLE volc_leitura;
COMMENT ON ROLE volc_leitura_agente IS
  'v18_01 · login dos workers · senha só fora do repo · herda volc_leitura e nada mais';

ALTER ROLE volc_leitura_agente SET default_transaction_read_only = on;
ALTER ROLE volc_leitura_agente SET statement_timeout = '30s';
ALTER ROLE volc_leitura_agente SET idle_in_transaction_session_timeout = '60s';
ALTER ROLE volc_leitura_agente SET search_path = public;

GRANT CONNECT ON DATABASE postgres TO volc_leitura;
GRANT USAGE ON SCHEMA public TO volc_leitura;

-- ---------------------------------------------------------------------------
-- 2. Allowlist — domínio aquisição/medição, sem pessoa e sem credencial
-- ---------------------------------------------------------------------------
-- Ausente no banco = pulado com NOTICE (o laboratório e a produção não têm
-- exatamente o mesmo conjunto). A lista é o que o hash aprova; ampliar exige
-- nova migration.
DO $$
DECLARE
  permitidas text[] := ARRAY[
    'google_ads_campanha_dia',
    'google_ads_fato_granular',
    'google_ads_fato_granular_asset',
    'google_ads_fato_granular_geo',
    'google_ads_fato_granular_hora_dispositivo',
    'google_ads_fato_granular_keyword',
    'google_ads_fato_granular_placement',
    'google_ads_fato_granular_termo',
    'google_ads_fato_granular_url',
    'trafego_coleta_execucao',
    'trafego_coleta_execucao_saude',
    'trafego_meta_insight_daily',
    'vw_gads_campanha_dia'
  ];
  -- Fora de propósito (revisão 15/10): trafego_inventario_conta/_campanha,
  -- vw_gads_arbitragem_campanha_dia e vw_gam_attribution_route são
  -- security_invoker sobre tabelas que NÃO estão na lista (trafego_snapshot_conta,
  -- trafego_campanha, trafego_vinculo, gam_metrics, joinads_metrics, campaigns):
  -- liberar a view sem a base daria 42501, e liberar a base amplia a leitura.
  -- Entram numa migration própria, com a base declarada.
  -- Nada que case com isto entra, mesmo que alguém o ponha na lista acima.
  proibido text := '(^users$|users_safe|credential|credencial|token|secret|segredo|private|cofre|auth|senha|password)';
  t text; rel regclass; c record; ignoradas int := 0;
BEGIN
  FOREACH t IN ARRAY permitidas LOOP
    IF t ~* proibido THEN
      RAISE EXCEPTION 'v18_01: % casa com o padrão proibido; a allowlist foi adulterada', t;
    END IF;
    rel := to_regclass('public.' || quote_ident(t));
    IF rel IS NULL THEN
      RAISE NOTICE 'v18_01: public.% ausente — pulada', t; ignoradas := ignoradas + 1; CONTINUE;
    END IF;
    SELECT cl.relkind, cl.relrowsecurity, cl.relowner,
           coalesce(array_to_string(cl.reloptions, ','), '') LIKE '%security_invoker=true%' AS invoker
      INTO c FROM pg_class cl WHERE cl.oid = rel;
    IF NOT pg_has_role(current_user, c.relowner, 'USAGE') THEN
      RAISE EXCEPTION 'v18_01: public.% é de %, não de %; aplique com o dono ou tire da lista',
        t, pg_get_userbyid(c.relowner), current_user;
    END IF;
    IF c.relkind IN ('v','m') AND NOT c.invoker THEN
      RAISE WARNING 'v18_01: view public.% roda como o DONO (sem security_invoker) — leitura atravessa RLS de baixo', t;
    END IF;
    EXECUTE format('GRANT SELECT ON public.%I TO volc_leitura', t);
    IF c.relkind IN ('r','p') AND c.relrowsecurity THEN
      EXECUTE format('CREATE POLICY volc_leitura_le ON public.%I FOR SELECT TO volc_leitura USING (true)', t);
    END IF;
  END LOOP;
  RAISE NOTICE 'v18_01: allowlist aplicada (% de % ausentes)', ignoradas, array_length(permitidas, 1);
END $$;

-- ---------------------------------------------------------------------------
-- 3. Postflight dentro da transação — falha = nada fica
-- ---------------------------------------------------------------------------
DO $$
DECLARE n int;
BEGIN
  IF (SELECT rolbypassrls OR rolsuper FROM pg_roles WHERE rolname = 'volc_leitura_agente') THEN
    RAISE EXCEPTION 'v18_01 postflight: volc_leitura_agente com BYPASSRLS/SUPERUSER';
  END IF;
  SELECT count(*) INTO n FROM pg_auth_members am JOIN pg_roles m ON m.oid = am.member
   WHERE m.rolname IN ('volc_leitura','volc_leitura_agente')
     AND am.roleid <> 'volc_leitura'::regrole;
  IF n > 0 THEN RAISE EXCEPTION 'v18_01 postflight: herança além de volc_leitura (%)', n; END IF;

  SELECT count(*) INTO n FROM pg_class cl JOIN pg_namespace ns ON ns.oid = cl.relnamespace
   WHERE ns.nspname NOT IN ('pg_catalog','information_schema') AND cl.relkind IN ('r','p','v','m','f')
     AND (has_table_privilege('volc_leitura_agente', cl.oid, 'INSERT')
       OR has_table_privilege('volc_leitura_agente', cl.oid, 'UPDATE')
       OR has_table_privilege('volc_leitura_agente', cl.oid, 'DELETE')
       OR has_table_privilege('volc_leitura_agente', cl.oid, 'TRUNCATE'));
  IF n > 0 THEN RAISE EXCEPTION 'v18_01 postflight: % objeto(s) graváveis pela identidade de leitura', n; END IF;

  -- SELECT só na allowlist: qualquer relação legível fora dela (PUBLIC, herança,
  -- default ACL) aborta a migration inteira.
  SELECT count(*) INTO n FROM pg_class cl JOIN pg_namespace ns ON ns.oid = cl.relnamespace
   WHERE ns.nspname NOT IN ('pg_catalog','information_schema') AND cl.relkind IN ('r','p','v','m','f')
     AND has_table_privilege('volc_leitura_agente', cl.oid, 'SELECT')
     AND has_schema_privilege('volc_leitura_agente', ns.oid, 'USAGE')
     -- Exceção nominal: a extensão concede SELECT a PUBLIC; sem pg_read_all_stats
     -- um papel comum vê só as próprias consultas (medido na imagem 15.8.1.085).
     AND NOT (ns.nspname = 'extensions' AND cl.relname IN ('pg_stat_statements','pg_stat_statements_info'))
     AND NOT (ns.nspname = 'public' AND cl.relname = ANY (ARRAY[
       'google_ads_campanha_dia','google_ads_fato_granular','google_ads_fato_granular_asset',
       'google_ads_fato_granular_geo','google_ads_fato_granular_hora_dispositivo',
       'google_ads_fato_granular_keyword','google_ads_fato_granular_placement',
       'google_ads_fato_granular_termo','google_ads_fato_granular_url','trafego_coleta_execucao',
       'trafego_coleta_execucao_saude','trafego_meta_insight_daily','vw_gads_campanha_dia']));
  IF n > 0 THEN RAISE EXCEPTION 'v18_01 postflight: % relação(ões) legíveis fora da allowlist', n; END IF;

  IF has_schema_privilege('volc_leitura_agente', 'public', 'CREATE') THEN
    RAISE EXCEPTION 'v18_01 postflight: identidade de leitura pode CREATE em public';
  END IF;
END $$;

COMMIT;
