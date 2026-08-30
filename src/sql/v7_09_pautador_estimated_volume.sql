-- =====================================================================
-- v7 PAUTADOR PRO — Etapa 9 / Estimativa de volume na descoberta (ADITIVO, idempotente)
--
-- A etapa de DESCOBERTA (LLM/gemini) agora estima o volume de busca mensal da
-- entidade (indicativo bruto). O card mostra esse volume no lugar da nota, pra
-- UX mais intuitiva pro operador. A MINERAÇÃO real refina depois.
--
-- NÃO destrutivo. >>> Rodar no Supabase SQL Editor (projeto txvvzpstquqmbhljudfn). <<<
-- =====================================================================

ALTER TABLE public.pautador_entity_opportunities
    ADD COLUMN IF NOT EXISTS estimated_volume bigint;

COMMENT ON COLUMN public.pautador_entity_opportunities.estimated_volume IS
    'Estimativa (LLM) de volume de busca mensal da entidade na descoberta. Indicativo; a mineração traz o real.';

-- =====================================================================
-- Verificação (opcional)
-- SELECT column_name FROM information_schema.columns
--   WHERE table_name='pautador_entity_opportunities' AND column_name='estimated_volume';
-- =====================================================================
