-- Script para criar e popular as tabelas de custos operacionais
-- com a estrutura real conforme exemplo fornecido
-- Execute no Supabase SQL Editor

-- Primeiro, criar categorias de exemplo
INSERT INTO operational_cost_categories (id, name) 
VALUES 
    (1, 'Pessoas'),
    (2, 'Infraestrutura'),
    (3, 'Administrativo')
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;

-- Inserir custos de exemplo baseados no INSERT fornecido
INSERT INTO operational_costs (id, name, amount, category_id, month, is_active, created_at, updated_at) 
VALUES 
    (1, 'Salários Equipe', 4500.00, 1, '2025-08-01', true, '2025-08-25 21:54:58.014382', '2025-08-25 21:54:58.014382'),
    (2, 'FGTS', 360.00, 1, '2025-08-01', true, '2025-08-25 21:54:58.014382', '2025-08-25 21:54:58.014382'),
    (3, 'Benefícios', 180.00, 1, '2025-08-01', true, '2025-08-25 21:54:58.014382', '2025-08-25 21:54:58.014382'),
    (4, 'Servidor/Hosting', 89.00, 2, '2025-08-01', true, '2025-08-25 21:54:58.014382', '2025-08-25 21:54:58.014382'),
    (5, 'Domínios', 45.00, 2, '2025-08-01', true, '2025-08-25 21:54:58.014382', '2025-08-25 21:54:58.014382'),
    (6, 'Ferramentas', 197.00, 2, '2025-08-01', true, '2025-08-25 21:54:58.014382', '2025-08-25 21:54:58.014382'),
    (7, 'CDN/Performance', 67.00, 2, '2025-08-01', true, '2025-08-25 21:54:58.014382', '2025-08-25 21:54:58.014382'),
    
    -- Adicionar alguns custos administrativos
    (8, 'Aluguel Escritório', 800.00, 3, '2025-08-01', true, '2025-08-25 21:54:58.014382', '2025-08-25 21:54:58.014382'),
    (9, 'Viagens', 300.00, 3, '2025-08-01', true, '2025-08-25 21:54:58.014382', '2025-08-25 21:54:58.014382'),
    (10, 'Contabilidade', 250.00, 3, '2025-08-01', true, '2025-08-25 21:54:58.014382', '2025-08-25 21:54:58.014382'),
    
    -- Adicionar custos para julho para comparação
    (11, 'Salários Equipe', 4200.00, 1, '2025-07-01', true, '2025-08-25 21:54:58.014382', '2025-08-25 21:54:58.014382'),
    (12, 'FGTS', 336.00, 1, '2025-07-01', true, '2025-08-25 21:54:58.014382', '2025-08-25 21:54:58.014382'),
    (13, 'Servidor/Hosting', 95.00, 2, '2025-07-01', true, '2025-08-25 21:54:58.014382', '2025-08-25 21:54:58.014382'),
    (14, 'Aluguel Escritório', 800.00, 3, '2025-07-01', true, '2025-08-25 21:54:58.014382', '2025-08-25 21:54:58.014382'),
    
    -- Adicionar alguns custos inativos para demonstrar funcionalidade
    (15, 'Custo Antigo', 100.00, 1, '2025-08-01', false, '2025-08-25 21:54:58.014382', '2025-08-25 21:54:58.014382')
ON CONFLICT (id) DO UPDATE SET 
    name = EXCLUDED.name,
    amount = EXCLUDED.amount,
    category_id = EXCLUDED.category_id,
    month = EXCLUDED.month,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- Verificar os dados inseridos
SELECT 
    oc.id,
    oc.name as custo,
    oc.amount as valor,
    c.name as categoria,
    oc.month as mes,
    oc.is_active as ativo
FROM operational_costs oc
JOIN operational_cost_categories c ON oc.category_id = c.id
WHERE oc.month >= '2025-07-01'
ORDER BY oc.month DESC, c.name, oc.name;

-- Consulta de totais por categoria (para teste)
SELECT 
    c.name as categoria,
    COUNT(*) as total_custos,
    SUM(CASE WHEN oc.is_active THEN oc.amount ELSE 0 END) as total_valor_ativo,
    SUM(oc.amount) as total_valor_geral
FROM operational_costs oc
JOIN operational_cost_categories c ON oc.category_id = c.id
WHERE oc.month = '2025-08-01'
GROUP BY c.id, c.name
ORDER BY total_valor_ativo DESC;

