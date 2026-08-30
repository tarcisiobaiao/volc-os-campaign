-- =====================================================================
-- v7 PAUTADOR PRO — Etapa 14 / Descrição da tarefa (ADITIVO, idempotente)
--
-- Separa dois textos do admin que hoje estavam confundidos num campo só:
--
--   · insights          -> DIRECIONAMENTO DO AGENTE (user prompt do arquiteto
--                          de funil). Texto de bastidor, escrito para a máquina.
--   · task_description  -> CORPO DA TASK no ClickUp. Texto escrito para a
--                          pessoa que vai executar.
--
-- Nenhum dos dois entra no DOCX do briefing. Até a v7_13, o `insights` era
-- impresso num box "Registrado pelo admin" no fim do documento — ou seja, o
-- prompt do agente vazava para dentro do material entregue ao redator.
--
-- NÃO destrutivo. >>> Rodar no Supabase SQL Editor (projeto txvvzpstquqmbhljudfn). <<<
-- =====================================================================

ALTER TABLE public.pautador_entity_opportunities
    ADD COLUMN IF NOT EXISTS task_description text;

COMMENT ON COLUMN public.pautador_entity_opportunities.task_description IS
    'Descrição da tarefa, escrita pelo admin. Vai para a description da task do ClickUp quando o card é movido para Pronto. NÃO aparece no DOCX do briefing.';

COMMENT ON COLUMN public.pautador_entity_opportunities.insights IS
    'Direcionamento do admin para o AGENTE de funil (entra no prompt do arquiteto). NÃO aparece no DOCX nem na task do ClickUp.';

-- Verificação rápida (opcional):
-- SELECT id, entity_id, task_description IS NOT NULL AS tem_descricao FROM public.pautador_entity_opportunities LIMIT 5;
