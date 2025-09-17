-- Configuração da tabela system_settings para timestamps de atualização
-- Execute este script no Supabase SQL Editor
-- A tabela já existe com a estrutura: id, key, value, description, data_type, category, is_editable, created_at, updated_at

-- Inserir as configurações de timestamp usando a estrutura existente
INSERT INTO system_settings (key, value, description, data_type, category, is_editable) 
VALUES 
    ('gam_last_update', NULL, 'Timestamp da última atualização do Google Ad Manager (GAM)', 'string', 'system', 'false')
ON CONFLICT (key) 
DO UPDATE SET 
    description = EXCLUDED.description,
    data_type = EXCLUDED.data_type,
    category = EXCLUDED.category,
    updated_at = NOW();

INSERT INTO system_settings (key, value, description, data_type, category, is_editable) 
VALUES 
    ('google_ads_last_update', NULL, 'Timestamp da última atualização do Google Ads', 'string', 'system', 'false')
ON CONFLICT (key) 
DO UPDATE SET 
    description = EXCLUDED.description,
    data_type = EXCLUDED.data_type,
    category = EXCLUDED.category,
    updated_at = NOW();

-- Função para atualizar timestamp de GAM
CREATE OR REPLACE FUNCTION update_gam_timestamp()
RETURNS void AS $$
BEGIN
    UPDATE system_settings 
    SET 
        value = (NOW() AT TIME ZONE 'America/Sao_Paulo')::text,
        updated_at = NOW()
    WHERE key = 'gam_last_update';
END;
$$ LANGUAGE plpgsql;

-- Função para atualizar timestamp de Google Ads
CREATE OR REPLACE FUNCTION update_google_ads_timestamp()
RETURNS void AS $$
BEGIN
    UPDATE system_settings 
    SET 
        value = (NOW() AT TIME ZONE 'America/Sao_Paulo')::text,
        updated_at = NOW()
    WHERE key = 'google_ads_last_update';
END;
$$ LANGUAGE plpgsql;

-- Função para buscar o último timestamp de atualização (GAM ou Google Ads)
CREATE OR REPLACE FUNCTION get_last_data_update()
RETURNS TABLE(
    gam_last_update TIMESTAMP WITH TIME ZONE,
    google_ads_last_update TIMESTAMP WITH TIME ZONE,
    most_recent TIMESTAMP WITH TIME ZONE
) AS $$
DECLARE
    gam_timestamp TIMESTAMP WITH TIME ZONE;
    ads_timestamp TIMESTAMP WITH TIME ZONE;
    latest_timestamp TIMESTAMP WITH TIME ZONE;
BEGIN
    -- Buscar timestamp do GAM
    SELECT CASE 
        WHEN value IS NOT NULL AND value != ''
        THEN value::TIMESTAMP WITH TIME ZONE 
        ELSE NULL 
    END INTO gam_timestamp
    FROM system_settings 
    WHERE key = 'gam_last_update';

    -- Buscar timestamp do Google Ads
    SELECT CASE 
        WHEN value IS NOT NULL AND value != ''
        THEN value::TIMESTAMP WITH TIME ZONE 
        ELSE NULL 
    END INTO ads_timestamp
    FROM system_settings 
    WHERE key = 'google_ads_last_update';

    -- Determinar o mais recente
    latest_timestamp := GREATEST(gam_timestamp, ads_timestamp);

    RETURN QUERY SELECT gam_timestamp, ads_timestamp, latest_timestamp;
END;
$$ LANGUAGE plpgsql;

-- Exemplo de como o n8n pode chamar as funções:
-- Para GAM: SELECT update_gam_timestamp();
-- Para Google Ads: SELECT update_google_ads_timestamp();
-- Para buscar: SELECT * FROM get_last_data_update();