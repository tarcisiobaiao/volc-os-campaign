-- =====================================================================
-- v7 PAUTADOR PRO — Etapa 10 / Arbitragem multi-vertical (ADITIVO, idempotente)
--
-- A descoberta (V2) deixou de ser só "benefícios do governo": agora traz qualquer
-- vertical de alto valor (finanças, crédito, seguros, carros, empregos, imóveis,
-- saúde, educação, jurídico...), adaptada ao market_tier do país, priorizando o
-- SPREAD de arbitragem (volume × eCPM ÷ concorrência).
--
--   vertical   (na entidade)     -> linha editorial (financas, carros_transito, gov_beneficios...)
--   ecpm_band  (na oportunidade) -> sinal de monetização da vertical: premium|medio|baixo
--
-- NÃO destrutivo. >>> Rodar no Supabase SQL Editor (projeto txvvzpstquqmbhljudfn). <<<
-- =====================================================================

ALTER TABLE public.pautador_entities
    ADD COLUMN IF NOT EXISTS vertical text;

ALTER TABLE public.pautador_entity_opportunities
    ADD COLUMN IF NOT EXISTS ecpm_band text;

COMMENT ON COLUMN public.pautador_entities.vertical IS
    'Linha editorial da arbitragem: gov_beneficios|financas|credito|seguros|carros_transito|imoveis|educacao|saude|empregos_concursos|juridico|tecnologia|outros.';
COMMENT ON COLUMN public.pautador_entity_opportunities.ecpm_band IS
    'Sinal de monetização (eCPM) da vertical na descoberta: premium|medio|baixo.';

-- =====================================================================
-- Verificação (opcional)
-- SELECT table_name, column_name FROM information_schema.columns
--   WHERE (table_name='pautador_entities' AND column_name='vertical')
--      OR (table_name='pautador_entity_opportunities' AND column_name='ecpm_band');
-- =====================================================================
