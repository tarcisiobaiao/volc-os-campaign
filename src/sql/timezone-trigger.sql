-- SQL Trigger para forçar timezone de São Paulo em todas as inserções/updates
-- Execute este script no Supabase SQL Editor para garantir timestamps corretos

-- Função para converter timestamps para timezone de São Paulo
CREATE OR REPLACE FUNCTION convert_to_sao_paulo_timezone()
RETURNS TRIGGER AS $$
BEGIN
    -- Para operações INSERT
    IF TG_OP = 'INSERT' THEN
        -- Se created_at não foi definido ou é UTC, converte para São Paulo
        IF NEW.created_at IS NULL OR NEW.created_at AT TIME ZONE 'UTC' = NEW.created_at THEN
            NEW.created_at = (NOW() AT TIME ZONE 'America/Sao_Paulo') AT TIME ZONE 'UTC';
        END IF;
        
        -- Se updated_at não foi definido ou é UTC, converte para São Paulo  
        IF NEW.updated_at IS NULL OR NEW.updated_at AT TIME ZONE 'UTC' = NEW.updated_at THEN
            NEW.updated_at = (NOW() AT TIME ZONE 'America/Sao_Paulo') AT TIME ZONE 'UTC';
        END IF;
        
        RETURN NEW;
    END IF;
    
    -- Para operações UPDATE
    IF TG_OP = 'UPDATE' THEN
        -- Sempre atualiza updated_at para São Paulo
        NEW.updated_at = (NOW() AT TIME ZONE 'America/Sao_Paulo') AT TIME ZONE 'UTC';
        RETURN NEW;
    END IF;
    
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Aplica o trigger na tabela daily_campaign_metrics
DROP TRIGGER IF EXISTS trigger_sao_paulo_timezone_daily_campaign_metrics ON daily_campaign_metrics;

CREATE TRIGGER trigger_sao_paulo_timezone_daily_campaign_metrics
    BEFORE INSERT OR UPDATE ON daily_campaign_metrics
    FOR EACH ROW
    EXECUTE FUNCTION convert_to_sao_paulo_timezone();

-- Aplica o trigger em outras tabelas importantes (opcional)
DROP TRIGGER IF EXISTS trigger_sao_paulo_timezone_projects ON projects;
CREATE TRIGGER trigger_sao_paulo_timezone_projects
    BEFORE INSERT OR UPDATE ON projects
    FOR EACH ROW
    EXECUTE FUNCTION convert_to_sao_paulo_timezone();

DROP TRIGGER IF EXISTS trigger_sao_paulo_timezone_campaigns ON campaigns;
CREATE TRIGGER trigger_sao_paulo_timezone_campaigns
    BEFORE INSERT OR UPDATE ON campaigns
    FOR EACH ROW
    EXECUTE FUNCTION convert_to_sao_paulo_timezone();

DROP TRIGGER IF EXISTS trigger_sao_paulo_timezone_gam_metrics ON gam_metrics;
CREATE TRIGGER trigger_sao_paulo_timezone_gam_metrics
    BEFORE INSERT OR UPDATE ON gam_metrics
    FOR EACH ROW
    EXECUTE FUNCTION convert_to_sao_paulo_timezone();

-- Opcional: Corrigir timestamps existentes para São Paulo
-- CUIDADO: Execute apenas se necessário, pode demorar
-- UPDATE daily_campaign_metrics 
-- SET updated_at = (updated_at AT TIME ZONE 'UTC') AT TIME ZONE 'America/Sao_Paulo' AT TIME ZONE 'UTC'
-- WHERE updated_at IS NOT NULL;

-- Comentários sobre o funcionamento:
-- 1. O trigger intercepta todas as inserções/atualizações
-- 2. Converte automaticamente UTC para horário de São Paulo
-- 3. O n8n pode continuar inserindo em UTC que será corrigido automaticamente
-- 4. O horário será salvo como UTC mas com o valor correto de São Paulo