-- Script para debugar o problema do projeto eleicoes.org
-- Execute este script no Supabase para identificar o problema

-- 1. VERIFICAR se o projeto eleicoes.org existe na tabela projects
SELECT
    id,
    domain,
    main_url,
    project_name,
    revshare,
    project_type
FROM projects
WHERE domain ILIKE '%eleicoes%'
   OR main_url ILIKE '%eleicoes%'
   OR project_name ILIKE '%eleicoes%'
ORDER BY id;

-- 2. TESTAR a função get_project_id_by_url com eleicoes.org
SELECT
    'eleicoes.org' as input_url,
    get_project_id_by_url('eleicoes.org') as found_project_id,
    CASE
        WHEN get_project_id_by_url('eleicoes.org') IS NOT NULL
        THEN 'PROJETO ENCONTRADO'
        ELSE 'PROJETO NÃO ENCONTRADO'
    END as status;

-- 3. VERIFICAR registros existentes para eleicoes.org em daily_project_metrics
SELECT
    id,
    project_id,
    url_projeto,
    date,
    revenue_converted,
    revenue_converted_revshare,
    updated_at
FROM daily_project_metrics
WHERE url_projeto ILIKE '%eleicoes%'
ORDER BY date DESC;

-- 4. VERIFICAR registros para project_id = 32
SELECT
    id,
    project_id,
    url_projeto,
    date,
    revenue_converted,
    revenue_converted_revshare,
    updated_at
FROM daily_project_metrics
WHERE project_id = 32
ORDER BY date DESC;

-- 5. VERIFICAR registros para a data específica 2025-09-22
SELECT
    id,
    project_id,
    url_projeto,
    date,
    revenue_converted,
    revenue_converted_revshare,
    updated_at
FROM daily_project_metrics
WHERE date = '2025-09-22'
ORDER BY project_id;

-- 6. TESTAR diferentes variações da URL eleicoes.org
SELECT
    test_url,
    get_project_id_by_url(test_url) as found_project_id
FROM (
    VALUES
        ('eleicoes.org'),
        ('www.eleicoes.org'),
        ('https://eleicoes.org'),
        ('https://www.eleicoes.org'),
        ('eleicoes'),
        ('ELEICOES.ORG')
) AS test_urls(test_url);

-- 7. VERIFICAR se há problema na constraint unique
SELECT
    project_id,
    date,
    COUNT(*) as count_records
FROM daily_project_metrics
WHERE date = '2025-09-22'
GROUP BY project_id, date
HAVING COUNT(*) > 1;

-- 8. SIMULAÇÃO: Tentar inserir com UPSERT para ver se resolve
-- DESCOMENTE AS LINHAS ABAIXO PARA TESTAR:

-- INSERT INTO daily_project_metrics (url_projeto, date, revenue_converted)
-- VALUES ('eleicoes.org', '2025-09-22', 5.81)
-- ON CONFLICT (project_id, date)
-- DO UPDATE SET
--     revenue_converted = EXCLUDED.revenue_converted,
--     updated_at = NOW()
-- RETURNING *;

-- 9. VERIFICAR a função interna do trigger para debug
SELECT
    trigger_name,
    action_statement
FROM information_schema.triggers
WHERE event_object_table = 'daily_project_metrics';

-- 10. VERIFICAR se há algum registro "órfão" sem project_id válido
SELECT
    id,
    project_id,
    url_projeto,
    date
FROM daily_project_metrics
WHERE project_id NOT IN (SELECT id FROM projects)
   OR project_id IS NULL;