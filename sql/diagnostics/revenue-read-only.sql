-- Script SQL para debug de dados de revenue
-- DIAGNÓSTICO READ-ONLY: somente SELECTs; seguro para inspeção, sem prova de schema atual.
-- Execute no Supabase SQL Editor

-- 1. Verificar se a coluna revenue_converted_revshare existe
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns 
WHERE table_name = 'daily_campaign_metrics' 
AND column_name LIKE '%revenue%'
ORDER BY column_name;

-- 2. Verificar dados recentes na tabela daily_campaign_metrics
SELECT 
    date,
    spend,
    revenue,
    revenue_converted,
    revenue_converted_revshare,
    campaign_id
FROM daily_campaign_metrics 
ORDER BY date DESC 
LIMIT 10;

-- 3. Verificar se há dados para hoje
SELECT 
    COUNT(*) as total_records,
    SUM(spend) as total_spend,
    SUM(revenue_converted) as total_revenue_converted,
    SUM(revenue_converted_revshare) as total_revenue_converted_revshare
FROM daily_campaign_metrics 
WHERE date = CURRENT_DATE;

-- 4. Verificar projetos e seus revshare
SELECT 
    id,
    project_name,
    revshare,
    status
FROM projects 
ORDER BY project_name;

-- 5. Verificar campanhas e seus projetos
SELECT 
    c.id,
    c.campaign_id,
    c.project_id,
    c.campaign_name,
    p.project_name,
    p.revshare
FROM campaigns c
JOIN projects p ON c.project_id = p.id
ORDER BY c.created_at DESC
LIMIT 10;

-- 6. Verificar se há dados de GAM
SELECT 
    date,
    revenue,
    revenue_converted,
    utm_campaign_value
FROM gam_metrics 
ORDER BY date DESC 
LIMIT 10;

-- 7. Verificar se a função de cálculo de revenue share está funcionando
SELECT 
    dcm.date,
    dcm.campaign_id,
    dcm.revenue_converted,
    dcm.revenue_converted_revshare,
    c.project_id,
    p.revshare,
    p.project_name
FROM daily_campaign_metrics dcm
JOIN campaigns c ON dcm.campaign_id = c.campaign_id
JOIN projects p ON c.project_id = p.id
WHERE dcm.date >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY dcm.date DESC
LIMIT 20;
