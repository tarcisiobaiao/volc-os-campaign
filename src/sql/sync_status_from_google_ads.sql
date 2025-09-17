-- =====================================================
-- Sincronização Automática de Status com Google Ads
-- =====================================================
-- Este script cria um sistema de sincronização automática da coluna 'status'
-- baseada no valor de 'google_ads_status' sempre que este for inserido ou atualizado.

-- Função que sincroniza o status baseado no google_ads_status
CREATE OR REPLACE FUNCTION sync_status_from_google_ads()
RETURNS TRIGGER AS $$
BEGIN
    -- Só sincroniza se google_ads_status foi preenchido/alterado
    IF NEW.google_ads_status IS NOT NULL THEN
        -- Mapeia google_ads_status para status
        IF NEW.google_ads_status = 'ENABLED' THEN
            NEW.status = 'Active';
            NEW.status_source = 'auto';
        ELSIF NEW.google_ads_status = 'PAUSED' THEN
            NEW.status = 'Paused';
            NEW.status_source = 'auto';
        -- Para outros valores, mantém como pausado por segurança
        ELSE
            NEW.status = 'Paused';
            NEW.status_source = 'auto';
        END IF;

        -- Log da sincronização
        RAISE NOTICE 'Status sincronizado: google_ads_status=% -> status=%',
            NEW.google_ads_status, NEW.status;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Remove triggers existentes se houver (para evitar duplicatas)
DROP TRIGGER IF EXISTS trigger_sync_status_insert ON campaigns;
DROP TRIGGER IF EXISTS trigger_sync_status_update ON campaigns;

-- Trigger para INSERT - executa ANTES da inserção
CREATE TRIGGER trigger_sync_status_insert
    BEFORE INSERT ON campaigns
    FOR EACH ROW
    EXECUTE FUNCTION sync_status_from_google_ads();

-- Trigger para UPDATE - executa ANTES da atualização
-- Só dispara quando google_ads_status é alterado
CREATE TRIGGER trigger_sync_status_update
    BEFORE UPDATE OF google_ads_status ON campaigns
    FOR EACH ROW
    WHEN (OLD.google_ads_status IS DISTINCT FROM NEW.google_ads_status)
    EXECUTE FUNCTION sync_status_from_google_ads();

-- =====================================================
-- Sincronização inicial dos dados existentes
-- =====================================================
-- Atualiza campanhas existentes que já têm google_ads_status preenchido
UPDATE campaigns
SET
    status = CASE
        WHEN google_ads_status = 'ENABLED' THEN 'Active'
        WHEN google_ads_status = 'PAUSED' THEN 'Paused'
        ELSE 'Paused'
    END,
    status_source = 'auto'
WHERE
    google_ads_status IS NOT NULL
    AND google_ads_status != ''
    AND (status_source IS NULL OR status_source = 'auto');

-- Log de quantas campanhas foram atualizadas
SELECT
    COUNT(*) as campanhas_sincronizadas,
    COUNT(CASE WHEN status = 'Active' THEN 1 END) as ativas,
    COUNT(CASE WHEN status = 'Paused' THEN 1 END) as pausadas
FROM campaigns
WHERE status_source = 'auto' AND google_ads_status IS NOT NULL;

-- =====================================================
-- Comentários e Documentação
-- =====================================================
COMMENT ON FUNCTION sync_status_from_google_ads() IS
'Função que sincroniza automaticamente a coluna status baseada no google_ads_status.
Mapeia: ENABLED -> Active, PAUSED -> Paused, outros -> Paused.
Define status_source como auto para indicar sincronização automática.';

COMMENT ON TRIGGER trigger_sync_status_insert ON campaigns IS
'Trigger que executa sincronização de status em inserções de novas campanhas.';

COMMENT ON TRIGGER trigger_sync_status_update ON campaigns IS
'Trigger que executa sincronização de status quando google_ads_status é atualizado.';