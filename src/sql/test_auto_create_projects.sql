-- Teste da funcionalidade de auto-criação de projetos
-- Este script testa se o trigger está criando projetos automaticamente

-- 1. VERIFICAR estrutura atual
SELECT 'Estado inicial - Contagem de projetos' as teste;
SELECT COUNT(*) as total_projetos_antes FROM projects;

-- 2. TESTE 1: Tentar inserir daily_project_metrics para URL inexistente
SELECT 'TESTE 1: Inserindo métricas para URL inexistente (site-teste-automatico.com)' as teste;

-- Verificar se o projeto já existe (deve retornar 0)
SELECT COUNT(*) as projetos_existentes
FROM projects
WHERE domain LIKE '%site-teste-automatico%'
   OR main_url LIKE '%site-teste-automatico%';

-- Inserir dados para URL que não existe
INSERT INTO daily_project_metrics (url_projeto, date, revenue_converted)
VALUES ('site-teste-automatico.com', '2025-01-19', 999.99);

-- Verificar se projeto foi criado automaticamente
SELECT 'Resultado TESTE 1: Verificando se projeto foi criado' as teste;
SELECT
    id,
    project_name,
    domain,
    main_url,
    status,
    revshare,
    project_type,
    created_at
FROM projects
WHERE domain LIKE '%site-teste-automatico%'
   OR main_url LIKE '%site-teste-automatico%';

-- Verificar se a inserção na daily_project_metrics funcionou
SELECT 'Resultado TESTE 1: Verificando se métrica foi inserida com project_id correto' as teste;
SELECT
    dpm.id,
    dpm.project_id,
    dpm.url_projeto,
    dpm.date,
    dpm.revenue_converted,
    dpm.revenue_converted_revshare,
    p.project_name,
    p.domain
FROM daily_project_metrics dpm
JOIN projects p ON dpm.project_id = p.id
WHERE dpm.url_projeto = 'site-teste-automatico.com';

-- 3. TESTE 2: Tentar inserir novamente para a mesma URL (deve encontrar o projeto existente)
SELECT 'TESTE 2: Inserindo novamente para mesma URL (deve usar projeto existente)' as teste;

INSERT INTO daily_project_metrics (url_projeto, date, revenue_converted)
VALUES ('site-teste-automatico.com', '2025-01-20', 1234.56);

-- Verificar se apenas uma entrada foi criada na tabela projects
SELECT 'Resultado TESTE 2: Deve ter apenas 1 projeto para esta URL' as teste;
SELECT COUNT(*) as total_projetos_para_url
FROM projects
WHERE domain LIKE '%site-teste-automatico%'
   OR main_url LIKE '%site-teste-automatico%';

-- Verificar se temos 2 entradas na daily_project_metrics com mesmo project_id
SELECT 'Resultado TESTE 2: Deve ter 2 métricas com mesmo project_id' as teste;
SELECT
    dpm.id,
    dpm.project_id,
    dpm.url_projeto,
    dpm.date,
    dpm.revenue_converted,
    dpm.revenue_converted_revshare
FROM daily_project_metrics dpm
WHERE dpm.url_projeto = 'site-teste-automatico.com'
ORDER BY dpm.date;

-- 4. TESTE 3: Testar diferentes formatos de URL
SELECT 'TESTE 3: Testando diferentes formatos de URL' as teste;

-- Inserir com https://
INSERT INTO daily_project_metrics (url_projeto, date, revenue_converted)
VALUES ('https://outro-teste.org', '2025-01-19', 500.00);

-- Inserir com www.
INSERT INTO daily_project_metrics (url_projeto, date, revenue_converted)
VALUES ('www.terceiro-teste.net', '2025-01-19', 750.25);

-- Verificar se foram criados projetos para cada formato
SELECT 'Resultado TESTE 3: Projetos criados para diferentes formatos' as teste;
SELECT
    id,
    project_name,
    domain,
    main_url,
    created_at
FROM projects
WHERE domain LIKE '%outro-teste%'
   OR main_url LIKE '%outro-teste%'
   OR domain LIKE '%terceiro-teste%'
   OR main_url LIKE '%terceiro-teste%'
ORDER BY created_at DESC;

-- 5. VERIFICAR estado final
SELECT 'Estado final - Contagem total de projetos' as teste;
SELECT COUNT(*) as total_projetos_depois FROM projects;

-- 6. RESUMO dos testes
SELECT 'RESUMO DOS TESTES' as teste;
SELECT
    'Projetos de teste criados:' as info,
    COUNT(*) as quantidade
FROM projects
WHERE domain LIKE '%teste%'
   OR project_name LIKE '%Teste%'
   OR domain LIKE '%outro-teste%'
   OR domain LIKE '%terceiro-teste%';

SELECT
    'Métricas de teste inseridas:' as info,
    COUNT(*) as quantidade
FROM daily_project_metrics
WHERE url_projeto LIKE '%teste%';

-- 7. LIMPEZA (opcional - descomente para remover dados de teste)
/*
-- Remover dados de teste
DELETE FROM daily_project_metrics
WHERE url_projeto IN (
    'site-teste-automatico.com',
    'https://outro-teste.org',
    'www.terceiro-teste.net'
);

DELETE FROM projects
WHERE domain IN (
    'site-teste-automatico.com',
    'outro-teste.org',
    'terceiro-teste.net'
)
OR project_name LIKE '%Teste%';

SELECT 'Dados de teste removidos' as limpeza;
*/