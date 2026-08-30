-- =====================================================================
-- v7 PAUTADOR PRO — Etapa 5 / EXTRAS do card de entidade (ADITIVO, idempotente)
--   1. coluna `insights` (texto livre do usuário, salvo por card)
--   2. (opcional) limpeza automática de cards REJEITADOS com > 21 dias via pg_cron
--
-- NÃO destrutivo. Preserva RLS de v7_03. Roda DEPOIS de v7_03.
-- >>> Rodar manualmente no Supabase SQL Editor (projeto txvvzpstquqmbhljudfn). <<<
-- =====================================================================

-- 1) Insights livres por card
ALTER TABLE public.pautador_entity_opportunities
    ADD COLUMN IF NOT EXISTS insights text;

COMMENT ON COLUMN public.pautador_entity_opportunities.insights IS
    'Anotações livres do usuário (aba Insights). Persistidas por card.';

-- =====================================================================
-- 2) (OPCIONAL) Limpeza automática dos rejeitados > 21 dias — pg_cron
--    O backend JÁ faz essa limpeza a cada nova descoberta do país (garantido).
--    Este cron dá a garantia por TEMPO mesmo sem novas descobertas.
--    Requer a extensão pg_cron habilitada (Supabase: Database → Extensions).
--
--    Descomente para ativar:
-- -------------------------------------------------------------------
-- create extension if not exists pg_cron with schema extensions;
--
-- select cron.schedule(
--   'pautador-clean-rejected-21d',
--   '0 3 * * *',   -- todo dia às 03:00 UTC
--   $$
--     DELETE FROM public.pautador_entities e
--     USING public.pautador_entity_opportunities o
--     WHERE o.entity_id = e.id
--       AND o.status = 'rejected'
--       AND o.updated_at < now() - interval '21 days'
--   $$
-- );
-- -------------------------------------------------------------------
-- Para remover o job depois:  select cron.unschedule('pautador-clean-rejected-21d');

-- =====================================================================
-- Verificação (opcional)
-- SELECT column_name FROM information_schema.columns
--   WHERE table_name='pautador_entity_opportunities' AND column_name='insights';
-- =====================================================================
