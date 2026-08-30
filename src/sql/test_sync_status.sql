-- =====================================================
-- TESTE - Sincronização de Status com Google Ads
-- =====================================================
-- Script para testar a sincronização automática

-- Verificar estado atual
SELECT
    COUNT(*) as total_campanhas,
    COUNT(CASE WHEN google_ads_status = 'ENABLED' THEN 1 END) as enabled_google,
    COUNT(CASE WHEN google_ads_status = 'PAUSED' THEN 1 END) as paused_google,
    COUNT(CASE WHEN status = 'Active' THEN 1 END) as active_status,
    COUNT(CASE WHEN status = 'Paused' THEN 1 END) as paused_status,
    COUNT(CASE WHEN status_source = 'auto' THEN 1 END) as auto_source,
    COUNT(CASE WHEN status_source = 'user' THEN 1 END) as user_source
FROM campaigns
WHERE google_ads_status IS NOT NULL;

-- Teste 1: Inserir uma nova campanha com google_ads_status = 'ENABLED'
INSERT INTO campaigns (
    utm_campaign_id,
    campaign_name,
    google_ads_status,
    project_id
) VALUES (
    'test_campaign_enabled',
    'Teste Campanha Habilitada',
    'ENABLED',
    (SELECT id FROM projects LIMIT 1)
);

-- Teste 2: Inserir uma nova campanha com google_ads_status = 'PAUSED'
INSERT INTO campaigns (
    utm_campaign_id,
    campaign_name,
    google_ads_status,
    project_id
) VALUES (
    'test_campaign_paused',
    'Teste Campanha Pausada',
    'PAUSED',
    (SELECT id FROM projects LIMIT 1)
);

-- Verificar se os testes foram sincronizados corretamente
SELECT
    utm_campaign_id,
    campaign_name,
    google_ads_status,
    status,
    status_source
FROM campaigns
WHERE utm_campaign_id IN ('test_campaign_enabled', 'test_campaign_paused');

-- Teste 3: Atualizar google_ads_status de uma campanha existente
UPDATE campaigns
SET google_ads_status = 'PAUSED'
WHERE utm_campaign_id = 'test_campaign_enabled';

-- Verificar se a atualização foi sincronizada
SELECT
    utm_campaign_id,
    campaign_name,
    google_ads_status,
    status,
    status_source
FROM campaigns
WHERE utm_campaign_id = 'test_campaign_enabled';

-- Teste 4: Atualizar de volta para ENABLED
UPDATE campaigns
SET google_ads_status = 'ENABLED'
WHERE utm_campaign_id = 'test_campaign_enabled';

-- Verificação final
SELECT
    utm_campaign_id,
    campaign_name,
    google_ads_status,
    status,
    status_source
FROM campaigns
WHERE utm_campaign_id IN ('test_campaign_enabled', 'test_campaign_paused');

-- Limpeza dos dados de teste
DELETE FROM campaigns
WHERE utm_campaign_id IN ('test_campaign_enabled', 'test_campaign_paused');

-- Verificar estado final
SELECT
    COUNT(*) as total_campanhas,
    COUNT(CASE WHEN status = 'Active' AND google_ads_status = 'ENABLED' THEN 1 END) as sincronizadas_ativas,
    COUNT(CASE WHEN status = 'Paused' AND google_ads_status = 'PAUSED' THEN 1 END) as sincronizadas_pausadas,
    COUNT(CASE WHEN status_source = 'auto' THEN 1 END) as auto_source
FROM campaigns
WHERE google_ads_status IS NOT NULL;