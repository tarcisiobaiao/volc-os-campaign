-- =====================================================================
-- v7 PAUTADOR PRO — Etapa 8 / FK do cluster (ADITIVO, idempotente)
--
-- Erro do flow n8n (nó "⬆️ Supabase: cluster"):
--   insert or update on "pautador_keyword_clusters" violates foreign key
--   constraint "pautador_keyword_clusters_opportunity_id_fkey"
--
-- Causa: a coluna opportunity_id (v7_01) tem FK -> public.pautador_opportunities
-- (tabela do mundo ANTIGO, opportunity-first). O fluxo ENTITY-FIRST grava o id de
-- public.pautador_entity_opportunities (ex.: o card = 20), que não existe na tabela
-- antiga -> a FK estoura. O código atual já trata cluster.opportunity_id como id da
-- entity-opportunity (o front filtra fetchClusters por ele). Como o cluster é escrito
-- pelos DOIS mundos, uma FK única não serve -> tornamos a referência SOLTA.
--
-- NÃO destrutivo. Só remove a constraint; a coluna e os dados permanecem.
-- >>> Rodar manualmente no Supabase SQL Editor (projeto txvvzpstquqmbhljudfn). <<<
-- =====================================================================

-- 1) remove a FK de opportunity_id (apontava pra tabela errada) --------------
ALTER TABLE public.pautador_keyword_clusters
    DROP CONSTRAINT IF EXISTS pautador_keyword_clusters_opportunity_id_fkey;

COMMENT ON COLUMN public.pautador_keyword_clusters.opportunity_id IS
    'Id da oportunidade (entity-first: pautador_entity_opportunities.id). Referência SOLTA — sem FK, pois o cluster é escrito por dois mundos (legado + entity-first).';

-- 2) recarrega o schema cache do PostgREST ----------------------------------
NOTIFY pgrst, 'reload schema';

-- =====================================================================
-- Verificação (opcional) — não deve retornar a constraint de opportunity_id:
-- SELECT conname FROM pg_constraint
--  WHERE conrelid = 'public.pautador_keyword_clusters'::regclass AND contype = 'f';
-- =====================================================================
