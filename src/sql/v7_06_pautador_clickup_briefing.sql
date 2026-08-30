-- =====================================================================
-- v7 PAUTADOR PRO — Etapa 6 / Entrega do briefing no ClickUp (ADITIVO, idempotente)
--   1. funnel_architecture jsonb -> guarda a saída RICA do arquiteto
--      (funnel_strategy + pages c/ H2 + writing_jobs), pra regenerar o DOCX
--      na hora que o card vai pra "Pronto" (o DOCX precisa dos H2/fichas).
--   2. clickup_task_id / clickup_task_url -> linkagem + idempotência
--      (não recria a task se o card voltar pra "Pronto").
--   3. funnel_completed / funnel_completed_at -> "dar baixa": o admin marca que o
--      funil foi de fato criado pelo redator. O card some da coluna Pronto por
--      padrão (NÃO é excluído) e pode ser reexibido por um toggle no Kanban.
--
-- NÃO destrutivo. Preserva RLS de v7_03. Roda DEPOIS de v7_03/v7_05.
-- >>> Rodar manualmente no Supabase SQL Editor (projeto txvvzpstquqmbhljudfn). <<<
-- =====================================================================

ALTER TABLE public.pautador_entity_opportunities
    ADD COLUMN IF NOT EXISTS funnel_architecture  jsonb,
    ADD COLUMN IF NOT EXISTS clickup_task_id       text,
    ADD COLUMN IF NOT EXISTS clickup_task_url      text,
    ADD COLUMN IF NOT EXISTS funnel_completed      boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS funnel_completed_at   timestamptz;

COMMENT ON COLUMN public.pautador_entity_opportunities.funnel_architecture IS
    'Saída rica do arquiteto do funil {funnel_strategy, pages(H2), writing_jobs}. Fonte do DOCX de briefing.';
COMMENT ON COLUMN public.pautador_entity_opportunities.clickup_task_id IS
    'ID da task criada no ClickUp ao mover o card p/ Pronto (idempotência).';
COMMENT ON COLUMN public.pautador_entity_opportunities.clickup_task_url IS
    'URL da task no ClickUp (link de volta).';
COMMENT ON COLUMN public.pautador_entity_opportunities.funnel_completed IS
    'Baixa do admin: funil criado pelo redator. Oculta o card da coluna Pronto por padrão.';
COMMENT ON COLUMN public.pautador_entity_opportunities.funnel_completed_at IS
    'Quando o admin deu baixa no funil (funnel_completed=true).';

-- =====================================================================
-- Verificação (opcional)
-- SELECT column_name FROM information_schema.columns
--   WHERE table_name='pautador_entity_opportunities'
--     AND column_name IN ('funnel_architecture','clickup_task_id','clickup_task_url',
--                         'funnel_completed','funnel_completed_at');
-- =====================================================================
