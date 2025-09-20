-- Exemplos de como o n8n deve inserir dados na nova daily_project_metrics
-- O n8n só precisa fornecer: url_projeto, date, revenue_converted
-- O sistema automaticamente preenche: project_id, revenue_converted_revshare, updated_at

-- EXEMPLO 1: Inserção simples (recomendado para n8n)
INSERT INTO daily_project_metrics (url_projeto, date, revenue_converted)
VALUES ('cartaoecredito.org', '2025-01-19', 125.50);

-- O que acontece automaticamente:
-- 1. project_id = busca automática pela URL na tabela projects
-- 2. revenue_converted_revshare = 125.50 * (1 - revshare_projeto/100)
-- 3. updated_at = timestamp atual

-- EXEMPLO 2: Inserção em lote (para múltiplas URLs/datas)
INSERT INTO daily_project_metrics (url_projeto, date, revenue_converted)
VALUES
    ('cartaoecredito.org', '2025-01-19', 125.50),
    ('exemplo.com', '2025-01-19', 89.30),
    ('outrosite.com', '2025-01-19', 200.75);

-- EXEMPLO 3: Upsert (recomendado para evitar duplicatas)
INSERT INTO daily_project_metrics (url_projeto, date, revenue_converted)
VALUES ('cartaoecredito.org', '2025-01-19', 130.00)
ON CONFLICT (project_id, date)
DO UPDATE SET
    revenue_converted = EXCLUDED.revenue_converted,
    updated_at = NOW();
-- revenue_converted_revshare será recalculado automaticamente pelo trigger

-- EXEMPLO 4: Para n8n - Template de inserção
-- Use este template no n8n workflow:
/*
INSERT INTO daily_project_metrics (url_projeto, date, revenue_converted)
VALUES ('{{ $json["url"] }}', '{{ $json["date"] }}', {{ $json["revenue"] }})
ON CONFLICT (project_id, date)
DO UPDATE SET
    revenue_converted = EXCLUDED.revenue_converted;
*/

-- EXEMPLO 5: Verificar se inserção funcionou
SELECT
    project_id,
    url_projeto,
    date,
    revenue_converted,
    revenue_converted_revshare,
    -- Verificar cálculo manual
    revenue_converted * (1 - (SELECT COALESCE(revshare, 0) / 100 FROM projects WHERE id = daily_project_metrics.project_id)) as manual_calc,
    updated_at
FROM daily_project_metrics
WHERE date = '2025-01-19'
ORDER BY updated_at DESC;

-- EXEMPLO 6: Para debugging - verificar se URL encontra projeto
SELECT
    url_input,
    get_project_id_by_url(url_input) as found_project_id,
    CASE
        WHEN get_project_id_by_url(url_input) IS NOT NULL THEN 'PROJETO ENCONTRADO'
        ELSE 'PROJETO NÃO ENCONTRADO - VERIFICAR URL'
    END as status
FROM (
    VALUES
        ('cartaoecredito.org'),
        ('exemplo.com'),
        ('url-inexistente.com')
) AS test_urls(url_input);

-- IMPORTANTE PARA N8N:
-- 1. Use sempre o formato de data: 'YYYY-MM-DD'
-- 2. revenue_converted deve ser numérico (sem vírgulas, use ponto decimal)
-- 3. url_projeto deve corresponder exatamente ao domain ou main_url na tabela projects
-- 4. Use UPSERT (ON CONFLICT) para evitar erros em re-execuções
-- 5. Não tente preencher project_id, revenue_converted_revshare ou updated_at - são automáticos