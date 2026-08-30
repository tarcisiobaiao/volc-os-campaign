-- =====================================================================
-- v7 PAUTADOR PRO — Etapa 7 / BLINDAGEM da mineração (n8n) — ADITIVO, idempotente
--
-- Corrige os erros do flow n8n de mineração (webhook -> Supabase):
--
--   #1  "Could not find the 'content_seo_queue' column ... in the schema cache"
--       -> as colunas RICAS do cluster não existiam (a v7_02 não tinha sido
--          rodada). Este bloco recria TODAS elas (idempotente), cobrindo isso.
--
--   #2  "numeric field overflow" (nó seed queries)
--       -> score era numeric(10,4) (máx 999.999,9999) e recebe o VOLUME de busca,
--          que passa de 1 milhão em termos amplos. Alarga score (e os numéricos
--          do cluster) para numeric SEM limite -> nunca mais estoura.
--
--   (#3 "401 No API key" é auth no n8n, não no banco — ver instruções à parte.)
--
-- Ao final, recarrega o schema cache do PostgREST (senão, mesmo após criar as
-- colunas, o erro "schema cache" pode persistir por alguns segundos).
--
-- NÃO destrutivo. Alargar numeric é sempre seguro (não há perda de dado).
-- >>> Rodar manualmente no Supabase SQL Editor (projeto txvvzpstquqmbhljudfn). <<<
-- =====================================================================

-- 1) colunas ricas do cluster (cobre quem pulou a v7_02) --------------------
--    Espelha exatamente o payload do nó "Build Supabase Payload" do n8n.
ALTER TABLE public.pautador_keyword_clusters
    ADD COLUMN IF NOT EXISTS raw_keywords         jsonb,
    ADD COLUMN IF NOT EXISTS production_ads_queue jsonb,
    ADD COLUMN IF NOT EXISTS content_seo_queue    jsonb,
    ADD COLUMN IF NOT EXISTS funis_sugeridos      jsonb,
    ADD COLUMN IF NOT EXISTS factory_output       jsonb,
    ADD COLUMN IF NOT EXISTS summary              jsonb,
    ADD COLUMN IF NOT EXISTS metrics              jsonb,
    ADD COLUMN IF NOT EXISTS services_used        jsonb,
    ADD COLUMN IF NOT EXISTS warnings             jsonb,
    ADD COLUMN IF NOT EXISTS engine               text;

-- 2) blindagem contra overflow numérico (volumes/scores altos) --------------
--    numeric SEM precisão/escala = sem teto (só limitado pela memória).
ALTER TABLE public.pautador_entity_seed_queries ALTER COLUMN score         TYPE numeric;
ALTER TABLE public.pautador_keyword_clusters    ALTER COLUMN total_volume  TYPE numeric;
ALTER TABLE public.pautador_keyword_clusters    ALTER COLUMN avg_cpc_local TYPE numeric;

-- 3) recarrega o cache de schema do PostgREST -------------------------------
NOTIFY pgrst, 'reload schema';

-- =====================================================================
-- Verificação (opcional)
-- SELECT column_name, data_type, numeric_precision
--   FROM information_schema.columns
--  WHERE table_name IN ('pautador_keyword_clusters','pautador_entity_seed_queries')
--    AND column_name IN ('content_seo_queue','production_ads_queue','summary',
--                        'services_used','engine','score','total_volume','avg_cpc_local')
--  ORDER BY table_name, column_name;
-- =====================================================================
