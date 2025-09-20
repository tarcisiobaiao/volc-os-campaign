-- Script para agregar revenue das URLs do funil ADSENSE em daily_campaign_metrics
-- Este script implementa a lógica que estava funcionando no layout antigo

-- 1. Função para agregar revenue de funnel URLs para uma campanha específica
CREATE OR REPLACE FUNCTION aggregate_adsense_funnel_revenue(
    campaign_id_param TEXT,
    target_date DATE DEFAULT NULL
)
RETURNS void AS $$
DECLARE
    total_revenue_converted NUMERIC DEFAULT 0;
    funnel_urls_count INTEGER DEFAULT 0;
BEGIN
    -- Se não especificar data, usar hoje
    IF target_date IS NULL THEN
        target_date := CURRENT_DATE;
    END IF;

    -- Log de debug
    RAISE NOTICE 'Aggregating ADSENSE funnel revenue for campaign % on date %', campaign_id_param, target_date;

    -- Buscar todas as URLs ativas do funil para esta campanha
    SELECT COUNT(*) INTO funnel_urls_count
    FROM campaign_funnel_urls
    WHERE campaign_id = campaign_id_param AND Active = true;

    RAISE NOTICE 'Found % active funnel URLs for campaign %', funnel_urls_count, campaign_id_param;

    -- Se não há URLs do funil, sair
    IF funnel_urls_count = 0 THEN
        RAISE NOTICE 'No funnel URLs found for campaign %, skipping aggregation', campaign_id_param;
        RETURN;
    END IF;

    -- Agregar revenue das URLs do funil na data específica
    SELECT COALESCE(SUM(am.revenue_converted), 0)
    INTO total_revenue_converted
    FROM adsense_metrics am
    INNER JOIN campaign_funnel_urls cfu ON cfu.url = am.url
    WHERE cfu.campaign_id = campaign_id_param
      AND cfu.Active = true
      AND am.date = target_date;

    RAISE NOTICE 'Total aggregated revenue for campaign % on %: %', campaign_id_param, target_date, total_revenue_converted;

    -- Inserir ou atualizar daily_campaign_metrics
    INSERT INTO daily_campaign_metrics (
        campaign_id,
        date,
        revenue_converted,
        updated_at
    )
    VALUES (
        campaign_id_param,
        target_date,
        total_revenue_converted,
        NOW()
    )
    ON CONFLICT (campaign_id, date)
    DO UPDATE SET
        revenue_converted = EXCLUDED.revenue_converted,
        updated_at = NOW();

    RAISE NOTICE 'Updated daily_campaign_metrics for campaign % on % with revenue %',
                 campaign_id_param, target_date, total_revenue_converted;

EXCEPTION
    WHEN OTHERS THEN
        RAISE WARNING 'Error aggregating funnel revenue for campaign %: %', campaign_id_param, SQLERRM;
END;
$$ LANGUAGE plpgsql;

-- 2. Função para agregar revenue de todas as campanhas ADSENSE de um projeto
CREATE OR REPLACE FUNCTION aggregate_project_adsense_revenue(
    project_id_param INTEGER,
    target_date DATE DEFAULT NULL
)
RETURNS void AS $$
DECLARE
    campaign_record RECORD;
    campaigns_count INTEGER DEFAULT 0;
BEGIN
    -- Se não especificar data, usar hoje
    IF target_date IS NULL THEN
        target_date := CURRENT_DATE;
    END IF;

    RAISE NOTICE 'Aggregating ADSENSE revenue for project % on date %', project_id_param, target_date;

    -- Verificar se é projeto ADSENSE
    IF NOT EXISTS (
        SELECT 1 FROM projects
        WHERE id = project_id_param AND project_type = 'ADSENSE'
    ) THEN
        RAISE NOTICE 'Project % is not ADSENSE type, skipping', project_id_param;
        RETURN;
    END IF;

    -- Buscar todas as campanhas do projeto que têm URLs do funil
    FOR campaign_record IN
        SELECT DISTINCT c.campaign_id
        FROM campaigns c
        INNER JOIN campaign_funnel_urls cfu ON cfu.campaign_id = c.campaign_id
        WHERE c.project_id = project_id_param
          AND cfu.Active = true
    LOOP
        campaigns_count := campaigns_count + 1;
        PERFORM aggregate_adsense_funnel_revenue(campaign_record.campaign_id, target_date);
    END LOOP;

    RAISE NOTICE 'Processed % campaigns for ADSENSE project %', campaigns_count, project_id_param;

EXCEPTION
    WHEN OTHERS THEN
        RAISE WARNING 'Error aggregating project ADSENSE revenue for project %: %', project_id_param, SQLERRM;
END;
$$ LANGUAGE plpgsql;

-- 3. Função para agregar revenue de todas as campanhas ADSENSE (todos os projetos)
CREATE OR REPLACE FUNCTION aggregate_all_adsense_revenue(
    target_date DATE DEFAULT NULL
)
RETURNS void AS $$
DECLARE
    project_record RECORD;
    projects_count INTEGER DEFAULT 0;
BEGIN
    -- Se não especificar data, usar hoje
    IF target_date IS NULL THEN
        target_date := CURRENT_DATE;
    END IF;

    RAISE NOTICE 'Aggregating ADSENSE revenue for all projects on date %', target_date;

    -- Buscar todos os projetos ADSENSE
    FOR project_record IN
        SELECT id FROM projects WHERE project_type = 'ADSENSE'
    LOOP
        projects_count := projects_count + 1;
        PERFORM aggregate_project_adsense_revenue(project_record.id, target_date);
    END LOOP;

    RAISE NOTICE 'Processed % ADSENSE projects', projects_count;

EXCEPTION
    WHEN OTHERS THEN
        RAISE WARNING 'Error aggregating all ADSENSE revenue: %', SQLERRM;
END;
$$ LANGUAGE plpgsql;

-- 4. Trigger para quando URLs do funil são adicionadas/removidas
CREATE OR REPLACE FUNCTION trigger_funnel_url_change()
RETURNS trigger AS $$
BEGIN
    -- Quando URL do funil é adicionada, modificada ou removida
    IF TG_OP = 'INSERT' OR TG_OP = 'UPDATE' THEN
        RAISE NOTICE 'Funnel URL change detected for campaign %, triggering aggregation', NEW.campaign_id;
        PERFORM aggregate_adsense_funnel_revenue(NEW.campaign_id, CURRENT_DATE);
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        RAISE NOTICE 'Funnel URL deletion detected for campaign %, triggering aggregation', OLD.campaign_id;
        PERFORM aggregate_adsense_funnel_revenue(OLD.campaign_id, CURRENT_DATE);
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- 5. Trigger para quando novos dados AdSense chegam
CREATE OR REPLACE FUNCTION trigger_adsense_metrics_change()
RETURNS trigger AS $$
DECLARE
    affected_campaign RECORD;
BEGIN
    -- Quando novos dados AdSense chegam, atualizar campanhas que usam essa URL
    IF TG_OP = 'INSERT' OR TG_OP = 'UPDATE' THEN
        RAISE NOTICE 'AdSense metrics change detected for URL % on date %, checking campaigns', NEW.url, NEW.date;

        -- Buscar campanhas que usam esta URL
        FOR affected_campaign IN
            SELECT campaign_id
            FROM campaign_funnel_urls
            WHERE url = NEW.url AND Active = true
        LOOP
            RAISE NOTICE 'Updating campaign % due to AdSense data change', affected_campaign.campaign_id;
            PERFORM aggregate_adsense_funnel_revenue(affected_campaign.campaign_id, NEW.date);
        END LOOP;

        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- 6. Criar triggers
DROP TRIGGER IF EXISTS trigger_funnel_url_change ON campaign_funnel_urls;
CREATE TRIGGER trigger_funnel_url_change
    AFTER INSERT OR UPDATE OR DELETE ON campaign_funnel_urls
    FOR EACH ROW
    EXECUTE FUNCTION trigger_funnel_url_change();

DROP TRIGGER IF EXISTS trigger_adsense_metrics_change ON adsense_metrics;
CREATE TRIGGER trigger_adsense_metrics_change
    AFTER INSERT OR UPDATE ON adsense_metrics
    FOR EACH ROW
    EXECUTE FUNCTION trigger_adsense_metrics_change();

-- 7. Comentários para documentação
COMMENT ON FUNCTION aggregate_adsense_funnel_revenue(TEXT, DATE) IS
'Agrega revenue das URLs do funil AdSense para uma campanha específica em uma data';

COMMENT ON FUNCTION aggregate_project_adsense_revenue(INTEGER, DATE) IS
'Agrega revenue de todas as campanhas AdSense de um projeto em uma data';

COMMENT ON FUNCTION aggregate_all_adsense_revenue(DATE) IS
'Agrega revenue de todas as campanhas AdSense de todos os projetos em uma data';

-- 8. Executar agregação inicial para dados existentes (hoje)
-- DESCOMENTE APENAS SE QUISER PROCESSAR DADOS EXISTENTES:
-- SELECT aggregate_all_adsense_revenue(CURRENT_DATE);

-- 9. Criar índices para performance
CREATE INDEX IF NOT EXISTS idx_campaign_funnel_urls_campaign_id_active
ON campaign_funnel_urls(campaign_id, Active);

CREATE INDEX IF NOT EXISTS idx_adsense_metrics_url_date
ON adsense_metrics(url, date);

CREATE INDEX IF NOT EXISTS idx_daily_campaign_metrics_campaign_date
ON daily_campaign_metrics(campaign_id, date);

RAISE NOTICE 'ADSENSE funnel aggregation system installed successfully!';