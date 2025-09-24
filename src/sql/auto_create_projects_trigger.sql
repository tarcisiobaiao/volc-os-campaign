-- Modificação do trigger para auto-criação de projetos
-- Quando uma url_projeto não existe, cria automaticamente o projeto

-- 1. FUNÇÃO para criar projeto automaticamente
CREATE OR REPLACE FUNCTION auto_create_project_by_url(url_input TEXT)
RETURNS INTEGER AS $$
DECLARE
    new_project_id INTEGER;
    clean_domain TEXT;
    project_name TEXT;
BEGIN
    -- Limpar a URL para obter o domínio
    clean_domain := LOWER(TRIM(REGEXP_REPLACE(
        REGEXP_REPLACE(
            REGEXP_REPLACE(url_input, '^https?://', '', 'i'),
            '^www\.', '', 'i'
        ),
        '/.*$', ''
    )));

    -- Gerar nome do projeto baseado no domínio
    project_name := INITCAP(REPLACE(SPLIT_PART(clean_domain, '.', 1), '-', ' '));

    -- Inserir novo projeto com valores padrão
    INSERT INTO projects (
        project_name,
        domain,
        main_url,
        start_date,
        status,
        dollar_rate,
        google_ads_status,
        gam_status,
        revshare,
        project_type,
        created_at,
        updated_at
    )
    VALUES (
        project_name,
        clean_domain,
        'https://' || clean_domain,
        CURRENT_DATE,
        'Active',
        5.50, -- Taxa padrão do dólar
        'UNKNOWN',
        'UNKNOWN',
        0, -- Revshare padrão 0%
        'GAM', -- Tipo padrão
        NOW(),
        NOW()
    )
    RETURNING id INTO new_project_id;

    RAISE NOTICE 'Projeto criado automaticamente: ID=%, Nome=%, Domínio=%',
        new_project_id, project_name, clean_domain;

    RETURN new_project_id;
END;
$$ LANGUAGE plpgsql;

-- 2. FUNÇÃO atualizada para buscar ou criar project_id pela URL
CREATE OR REPLACE FUNCTION get_or_create_project_id_by_url(url_input TEXT)
RETURNS INTEGER AS $$
DECLARE
    project_id_result INTEGER;
    cleaned_url TEXT;
BEGIN
    -- Limpar a URL para busca
    cleaned_url := LOWER(TRIM(REGEXP_REPLACE(
        REGEXP_REPLACE(
            REGEXP_REPLACE(url_input, '^https?://', '', 'i'),
            '^www\.', '', 'i'
        ),
        '/.*$', ''
    )));

    -- Tentar busca exata primeiro
    SELECT id INTO project_id_result
    FROM projects
    WHERE LOWER(domain) = cleaned_url
       OR LOWER(main_url) = cleaned_url
       OR LOWER(REPLACE(REPLACE(REPLACE(domain, 'https://', ''), 'http://', ''), 'www.', '')) = cleaned_url
       OR LOWER(REPLACE(REPLACE(REPLACE(main_url, 'https://', ''), 'http://', ''), 'www.', '')) = cleaned_url
    LIMIT 1;

    -- Se não encontrar busca exata, tentar busca com LIKE
    IF project_id_result IS NULL THEN
        SELECT id INTO project_id_result
        FROM projects
        WHERE LOWER(domain) LIKE '%' || cleaned_url || '%'
           OR LOWER(main_url) LIKE '%' || cleaned_url || '%'
        ORDER BY
            -- Priorizar matches mais exatos
            CASE
                WHEN LOWER(domain) = cleaned_url OR LOWER(main_url) = cleaned_url THEN 1
                WHEN LOWER(domain) LIKE cleaned_url || '%' OR LOWER(main_url) LIKE cleaned_url || '%' THEN 2
                ELSE 3
            END
        LIMIT 1;
    END IF;

    -- Se ainda não encontrar, criar projeto automaticamente
    IF project_id_result IS NULL THEN
        project_id_result := auto_create_project_by_url(url_input);
    END IF;

    RETURN project_id_result;
END;
$$ LANGUAGE plpgsql;

-- 3. FUNÇÃO de trigger atualizada
CREATE OR REPLACE FUNCTION trigger_daily_project_metrics_auto_fill()
RETURNS TRIGGER AS $$
DECLARE
    calculated_project_id INTEGER;
BEGIN
    -- Se project_id não foi fornecido, busca ou cria pela URL
    IF NEW.project_id IS NULL OR NEW.project_id = 0 THEN
        calculated_project_id := get_or_create_project_id_by_url(NEW.url_projeto);
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

-- 4. RECRIAR triggers com a nova função
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

-- 5. COMENTÁRIOS para documentação
COMMENT ON FUNCTION auto_create_project_by_url(TEXT) IS 'Cria automaticamente um projeto quando a URL não existe no sistema';
COMMENT ON FUNCTION get_or_create_project_id_by_url(TEXT) IS 'Busca project_id pela URL ou cria automaticamente se não existir';

-- 6. EXEMPLOS de uso (dados de teste)
--
-- -- Este exemplo criará automaticamente um projeto se "novosite.com" não existir
-- INSERT INTO daily_project_metrics (url_projeto, date, revenue_converted)
-- VALUES ('novosite.com', '2025-01-19', 125.50);
--
-- -- O trigger irá automaticamente:
-- -- 1. Verificar se existe projeto para "novosite.com"
-- -- 2. Se não existir, criar um novo projeto com:
-- --    - project_name: "Novosite"
-- --    - domain: "novosite.com"
-- --    - main_url: "https://novosite.com"
-- --    - status: "Active"
-- --    - outros campos com valores padrão
-- -- 3. Definir project_id no registro daily_project_metrics
-- -- 4. Calcular revenue_converted_revshare com base no revshare do projeto
-- -- 5. Definir updated_at para NOW()

-- 7. TESTE da funcionalidade
SELECT 'Testando criação automática de projeto...' as info;

-- Verificar se função está funcionando (sem inserir dados)
SELECT
    'teste-auto-create.com' as url_teste,
    get_or_create_project_id_by_url('teste-auto-create.com') as project_id_criado;

-- Para reverter a criação do teste:
-- DELETE FROM projects WHERE domain = 'teste-auto-create.com';