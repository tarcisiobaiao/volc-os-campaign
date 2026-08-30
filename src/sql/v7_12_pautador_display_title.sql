-- =====================================================================
-- v7 PAUTADOR PRO — Etapa 12 / Nome de exibição do card (ADITIVO, idempotente)
--
-- Permite duplicar uma entidade JÁ minerada para rodar o funil da mesma
-- entidade em sites diferentes. Cada cópia é um card próprio (o banco exige:
-- uq_pautador_entity_opportunities_entity é UNIQUE por entity_id), e o
-- `display_title` é o que diferencia as cópias na tela e no ClickUp.
--
-- Por que uma coluna nova em vez de sufixo no canonical_name: o canonical_name
-- alimenta o TEMA do agente de funil e o título do briefing DOCX — sujar ele
-- com "(Site B)" vazaria para o conteúdo gerado.
--
-- NÃO destrutivo. >>> Rodar no Supabase SQL Editor (projeto txvvzpstquqmbhljudfn). <<<
-- =====================================================================

ALTER TABLE public.pautador_entity_opportunities
    ADD COLUMN IF NOT EXISTS display_title text;

COMMENT ON COLUMN public.pautador_entity_opportunities.display_title IS
    'Nome de exibição do card, escrito pelo admin (ex.: "Site XPTO"). Diferencia cópias da mesma entidade na tela e no título da task do ClickUp. Não altera canonical_name.';

-- Verificação rápida (opcional):
-- SELECT id, entity_id, display_title FROM public.pautador_entity_opportunities LIMIT 5;
