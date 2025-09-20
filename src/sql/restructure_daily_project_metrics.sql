-- Reestruturação da tabela daily_project_metrics para WebgoV2
-- Nova estrutura simplificada para dados do n8n

-- 1. BACKUP da tabela atual (se necessário)
CREATE TABLE daily_project_metrics_backup AS
SELECT * FROM daily_project_metrics;

-- 2. DROPAR tabela atual
DROP TABLE IF EXISTS daily_project_metrics;

-- 3. CRIAR nova estrutura da tabela
CREATE TABLE daily_project_metrics (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL,
    url_projeto TEXT NOT NULL,
    date DATE NOT NULL,
    revenue_converted NUMERIC(10,2) NOT NULL DEFAULT 0,
    revenue_converted_revshare NUMERIC(10,2) NOT NULL DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    CONSTRAINT fk_daily_project_metrics_project
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,

    -- Unique constraint para evitar duplicatas
    CONSTRAINT unique_project_date
        UNIQUE (project_id, date)
);

-- 4. ÍNDICES para performance
CREATE INDEX idx_daily_project_metrics_project_id ON daily_project_metrics(project_id);
CREATE INDEX idx_daily_project_metrics_date ON daily_project_metrics(date);
CREATE INDEX idx_daily_project_metrics_url ON daily_project_metrics(url_projeto);
CREATE INDEX idx_daily_project_metrics_project_date ON daily_project_metrics(project_id, date);

-- 5. FUNÇÃO para buscar project_id pela URL
CREATE OR REPLACE FUNCTION get_project_id_by_url(url_input TEXT)
RETURNS INTEGER AS $$
DECLARE
    project_id_result INTEGER;
BEGIN
    -- Busca project_id pela URL (assumindo que domain na tabela projects corresponde à URL)
    SELECT id INTO project_id_result
    FROM projects
    WHERE domain = url_input
       OR main_url = url_input
       OR domain LIKE '%' || url_input || '%'
       OR main_url LIKE '%' || url_input || '%'
    LIMIT 1;

    -- Se não encontrar, retorna NULL
    RETURN project_id_result;
END;
$$ LANGUAGE plpgsql;

-- 6. FUNÇÃO para calcular revenue_converted_revshare
CREATE OR REPLACE FUNCTION calculate_revshare_discount(revenue_value NUMERIC, project_id_param INTEGER)
RETURNS NUMERIC AS $$
DECLARE
    revshare_percentage NUMERIC;
    result_value NUMERIC;
BEGIN
    -- Busca a porcentagem de revshare do projeto
    SELECT COALESCE(revshare, 0) INTO revshare_percentage
    FROM projects
    WHERE id = project_id_param;

    -- Se não encontrar projeto ou revshare for NULL, retorna o valor original
    IF revshare_percentage IS NULL THEN
        RETURN revenue_value;
    END IF;

    -- Calcula o valor após desconto do revshare
    -- Ex: revenue_converted * (1 - revshare/100)
    result_value := revenue_value * (1 - (revshare_percentage / 100));

    RETURN ROUND(result_value, 2);
END;
$$ LANGUAGE plpgsql;

-- 7. TRIGGER para preenchimento automático
CREATE OR REPLACE FUNCTION trigger_daily_project_metrics_auto_fill()
RETURNS TRIGGER AS $$
DECLARE
    calculated_project_id INTEGER;
BEGIN
    -- Se project_id não foi fornecido, busca pela URL
    IF NEW.project_id IS NULL OR NEW.project_id = 0 THEN
        calculated_project_id := get_project_id_by_url(NEW.url_projeto);

        -- Se não encontrar projeto, gera erro
        IF calculated_project_id IS NULL THEN
            RAISE EXCEPTION 'Projeto não encontrado para URL: %', NEW.url_projeto;
        END IF;

        NEW.project_id := calculated_project_id;
    END IF;

    -- Sempre atualiza o timestamp
    NEW.updated_at := NOW();

    -- Calcula revenue_converted_revshare automaticamente
    NEW.revenue_converted_revshare := calculate_revshare_discount(
        NEW.revenue_converted,
        NEW.project_id
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 8. CRIAR triggers
DROP TRIGGER IF EXISTS trigger_daily_project_metrics_insert ON daily_project_metrics;
DROP TRIGGER IF EXISTS trigger_daily_project_metrics_update ON daily_project_metrics;

CREATE TRIGGER trigger_daily_project_metrics_insert
    BEFORE INSERT ON daily_project_metrics
    FOR EACH ROW
    EXECUTE FUNCTION trigger_daily_project_metrics_auto_fill();

CREATE TRIGGER trigger_daily_project_metrics_update
    BEFORE UPDATE ON daily_project_metrics
    FOR EACH ROW
    EXECUTE FUNCTION trigger_daily_project_metrics_auto_fill();

-- 9. TRIGGER para recalcular quando projeto muda revshare
CREATE OR REPLACE FUNCTION trigger_recalculate_project_revshare()
RETURNS TRIGGER AS $$
BEGIN
    -- Se o revshare mudou, recalcula todos os registros deste projeto
    IF OLD.revshare IS DISTINCT FROM NEW.revshare THEN
        UPDATE daily_project_metrics
        SET revenue_converted_revshare = calculate_revshare_discount(revenue_converted, NEW.id),
            updated_at = NOW()
        WHERE project_id = NEW.id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_project_revshare_update ON projects;
CREATE TRIGGER trigger_project_revshare_update
    AFTER UPDATE ON projects
    FOR EACH ROW
    WHEN (OLD.revshare IS DISTINCT FROM NEW.revshare)
    EXECUTE FUNCTION trigger_recalculate_project_revshare();

-- 10. COMENTÁRIOS para documentação
COMMENT ON TABLE daily_project_metrics IS 'Métricas diárias por projeto - populada pelo n8n com automação de cálculos';
COMMENT ON COLUMN daily_project_metrics.project_id IS 'ID do projeto - preenchido automaticamente pela URL';
COMMENT ON COLUMN daily_project_metrics.url_projeto IS 'URL do projeto - vem do n8n';
COMMENT ON COLUMN daily_project_metrics.date IS 'Data da métrica - vem do n8n';
COMMENT ON COLUMN daily_project_metrics.revenue_converted IS 'Receita convertida - vem do n8n';
COMMENT ON COLUMN daily_project_metrics.revenue_converted_revshare IS 'Receita após desconto revshare - calculado automaticamente';
COMMENT ON COLUMN daily_project_metrics.updated_at IS 'Timestamp de atualização - sempre atualizado automaticamente';

COMMENT ON FUNCTION get_project_id_by_url(TEXT) IS 'Busca project_id pela URL do projeto';
COMMENT ON FUNCTION calculate_revshare_discount(NUMERIC, INTEGER) IS 'Calcula valor após desconto de revshare do projeto';
COMMENT ON FUNCTION trigger_daily_project_metrics_auto_fill() IS 'Preenche automaticamente project_id, updated_at e revenue_converted_revshare';
COMMENT ON FUNCTION trigger_recalculate_project_revshare() IS 'Recalcula revenue_converted_revshare quando revshare do projeto muda';

-- 11. EXEMPLO de uso (dados de teste)
-- INSERT INTO daily_project_metrics (url_projeto, date, revenue_converted)
-- VALUES ('cartaoecredito.org', '2025-01-19', 125.50);
--
-- -- O trigger irá automaticamente:
-- -- 1. Buscar project_id pela URL
-- -- 2. Calcular revenue_converted_revshare com base no revshare do projeto
-- -- 3. Definir updated_at para NOW()

-- ROLLBACK SCRIPT (se necessário):
-- DROP TABLE daily_project_metrics;
-- ALTER TABLE daily_project_metrics_backup RENAME TO daily_project_metrics;