-- =====================================================
-- ROLLBACK - Sincronização de Status com Google Ads
-- =====================================================
-- Script para desfazer as alterações da sincronização automática
-- Execute este script se precisar reverter as mudanças

-- Remove os triggers
DROP TRIGGER IF EXISTS trigger_sync_status_insert ON campaigns;
DROP TRIGGER IF EXISTS trigger_sync_status_update ON campaigns;

-- Remove a função
DROP FUNCTION IF EXISTS sync_status_from_google_ads();

-- Remove os comentários
COMMENT ON TRIGGER trigger_sync_status_insert ON campaigns IS NULL;
COMMENT ON TRIGGER trigger_sync_status_update ON campaigns IS NULL;

-- =====================================================
-- Opcional: Restaurar status_source para campanhas automáticas
-- =====================================================
-- Descomente as linhas abaixo se quiser resetar o status_source
-- UPDATE campaigns
-- SET status_source = NULL
-- WHERE status_source = 'auto';

RAISE NOTICE 'Rollback concluído: triggers e função removidos.';

-- Verificação
SELECT
    COUNT(*) as total_campanhas,
    COUNT(CASE WHEN status_source = 'auto' THEN 1 END) as campanhas_auto,
    COUNT(CASE WHEN status_source = 'user' THEN 1 END) as campanhas_user
FROM campaigns;