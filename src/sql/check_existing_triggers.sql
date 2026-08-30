-- Query para verificar triggers existentes relacionados a gam_metrics e daily_campaign_metrics

-- 1. Listar todos os triggers em gam_metrics
SELECT
    trigger_name,
    event_manipulation,
    event_object_table,
    action_statement,
    action_timing
FROM information_schema.triggers
WHERE event_object_table IN ('gam_metrics', 'daily_campaign_metrics')
ORDER BY event_object_table, trigger_name;

-- 2. Listar funções que mencionam essas tabelas
SELECT
    routine_name,
    routine_definition
FROM information_schema.routines
WHERE routine_type = 'FUNCTION'
  AND (
    routine_definition ILIKE '%gam_metrics%'
    OR routine_definition ILIKE '%daily_campaign_metrics%'
  )
ORDER BY routine_name;

-- 3. Ver código completo de uma função específica (caso exista)
-- Substitua 'nome_da_funcao' pelo nome encontrado acima
-- SELECT pg_get_functiondef(oid)
-- FROM pg_proc
-- WHERE proname = 'nome_da_funcao';
