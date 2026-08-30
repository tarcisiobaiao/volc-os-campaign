-- Script de teste para a nova estrutura daily_project_metrics
-- Execute após aplicar restructure_daily_project_metrics.sql

-- 1. TESTE: Verificar estrutura da tabela
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'daily_project_metrics'
ORDER BY ordinal_position;

-- 2. TESTE: Verificar triggers existentes
SELECT
    trigger_name,
    event_manipulation,
    action_timing,
    action_statement
FROM information_schema.triggers
WHERE event_object_table = 'daily_project_metrics';

-- 3. TESTE: Verificar funções criadas
SELECT
    routine_name,
    routine_type,
    data_type
FROM information_schema.routines
WHERE routine_name IN (
    'get_project_id_by_url',
    'calculate_revshare_discount',
    'trigger_daily_project_metrics_auto_fill'
);

-- 4. TESTE: Inserir dados de exemplo
-- Assumindo que existe um projeto com domain = 'cartaoecredito.org' e revshare = 10%

-- Inserir dados via n8n (simulando)
INSERT INTO daily_project_metrics (url_projeto, date, revenue_converted)
VALUES
    ('cartaoecredito.org', '2025-01-19', 100.00),
    ('cartaoecredito.org', '2025-01-18', 150.50);

-- 5. TESTE: Verificar se automação funcionou
SELECT
    id,
    project_id,
    url_projeto,
    date,
    revenue_converted,
    revenue_converted_revshare,
    updated_at,
    -- Calcular desconto manual para comparar
    revenue_converted * (1 - (
        SELECT COALESCE(revshare, 0) / 100
        FROM projects
        WHERE id = daily_project_metrics.project_id
    )) AS calculated_revshare
FROM daily_project_metrics
ORDER BY date DESC;

-- 6. TESTE: Verificar se busca de project_id funciona
SELECT
    get_project_id_by_url('cartaoecredito.org') as found_project_id,
    (SELECT id FROM projects WHERE domain = 'cartaoecredito.org' OR main_url = 'cartaoecredito.org' LIMIT 1) as expected_project_id;

-- 7. TESTE: Verificar cálculo de revshare
SELECT
    calculate_revshare_discount(100.00, 1) as revshare_100_project_1,
    calculate_revshare_discount(200.00, 1) as revshare_200_project_1;

-- 8. TESTE: Tentar inserir dados inválidos (deve dar erro)
-- INSERT INTO daily_project_metrics (url_projeto, date, revenue_converted)
-- VALUES ('url-inexistente.com', '2025-01-19', 100.00);

-- 9. TESTE: Verificar unique constraint
-- Tentar inserir duplicata (deve dar erro)
-- INSERT INTO daily_project_metrics (url_projeto, date, revenue_converted)
-- VALUES ('cartaoecredito.org', '2025-01-19', 200.00);

-- 10. LIMPEZA dos dados de teste
-- DELETE FROM daily_project_metrics WHERE date >= '2025-01-18';

-- EXPECTED RESULTS:
-- ✅ Estrutura deve ter 7 colunas
-- ✅ 2 triggers devem existir (insert e update)
-- ✅ 3 funções devem existir
-- ✅ project_id deve ser preenchido automaticamente
-- ✅ revenue_converted_revshare deve ser calculado corretamente
-- ✅ updated_at deve ser preenchido automaticamente
-- ❌ URL inexistente deve dar erro
-- ❌ Duplicata deve dar erro (unique constraint)