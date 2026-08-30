-- ====================================================================
-- Query para visualizar comissões dos operadores
-- ====================================================================

-- 1. Comissões por operador (sumarizado)
SELECT
  u.name AS operador,
  u.commission_percentage AS "comissão_%",
  COUNT(DISTINCT dcm.campaign_id) AS total_campanhas,
  COUNT(dcm.id) AS total_dias,
  SUM(dcm.revenue_converted_revshare) AS revenue_total,
  SUM(dcm.spend) AS spend_total,
  SUM(dcm.commission_operator) AS comissao_total,
  TO_CHAR(MIN(dcm.date), 'DD/MM/YYYY') AS primeira_data,
  TO_CHAR(MAX(dcm.date), 'DD/MM/YYYY') AS ultima_data
FROM users u
JOIN user_campaigns uc ON uc.user_id = u.id
JOIN daily_campaign_metrics dcm ON dcm.campaign_id = uc.campaign_id
WHERE u.role = 'OPERADOR'
  AND dcm.commission_operator > 0
GROUP BY u.id, u.name, u.commission_percentage
ORDER BY comissao_total DESC;

-- 2. Comissões por operador e campanha (detalhado)
SELECT
  u.name AS operador,
  u.commission_percentage AS "comissão_%",
  c.campaign_name,
  c.project_id,
  p.project_name,
  COUNT(dcm.id) AS total_dias,
  SUM(dcm.revenue_converted_revshare) AS revenue_total,
  SUM(dcm.spend) AS spend_total,
  SUM(dcm.revenue_converted_revshare) - SUM(dcm.spend) - SUM(dcm.revenue_converted_revshare * COALESCE((SELECT percentage/100 FROM tax_history WHERE DATE_TRUNC('month', month) = DATE_TRUNC('month', dcm.date) LIMIT 1), 0)) AS lucro_liquido,
  SUM(dcm.commission_operator) AS comissao_total,
  TO_CHAR(MIN(dcm.date), 'DD/MM/YYYY') AS primeira_data,
  TO_CHAR(MAX(dcm.date), 'DD/MM/YYYY') AS ultima_data
FROM users u
JOIN user_campaigns uc ON uc.user_id = u.id
JOIN daily_campaign_metrics dcm ON dcm.campaign_id = uc.campaign_id
JOIN campaigns c ON c.campaign_id = dcm.campaign_id
JOIN projects p ON p.id = c.project_id
WHERE u.role = 'OPERADOR'
  AND dcm.commission_operator > 0
GROUP BY u.id, u.name, u.commission_percentage, c.campaign_id, c.campaign_name, c.project_id, p.project_name
ORDER BY u.name, comissao_total DESC;

-- 3. Comissões diárias por operador (últimos 30 dias)
SELECT
  u.name AS operador,
  dcm.date AS data,
  COUNT(DISTINCT dcm.campaign_id) AS campanhas,
  SUM(dcm.revenue_converted_revshare) AS revenue,
  SUM(dcm.spend) AS spend,
  SUM(dcm.commission_operator) AS comissao_dia
FROM users u
JOIN user_campaigns uc ON uc.user_id = u.id
JOIN daily_campaign_metrics dcm ON dcm.campaign_id = uc.campaign_id
WHERE u.role = 'OPERADOR'
  AND dcm.date >= CURRENT_DATE - INTERVAL '30 days'
  AND dcm.commission_operator > 0
GROUP BY u.id, u.name, dcm.date
ORDER BY dcm.date DESC, u.name;

-- 4. Comissões do mês atual
SELECT
  u.name AS operador,
  u.commission_percentage AS "comissão_%",
  TO_CHAR(DATE_TRUNC('month', CURRENT_DATE), 'MM/YYYY') AS mes,
  COUNT(DISTINCT dcm.campaign_id) AS total_campanhas,
  SUM(dcm.revenue_converted_revshare) AS revenue_mes,
  SUM(dcm.spend) AS spend_mes,
  SUM(dcm.commission_operator) AS comissao_mes
FROM users u
JOIN user_campaigns uc ON uc.user_id = u.id
JOIN daily_campaign_metrics dcm ON dcm.campaign_id = uc.campaign_id
WHERE u.role = 'OPERADOR'
  AND DATE_TRUNC('month', dcm.date) = DATE_TRUNC('month', CURRENT_DATE)
  AND dcm.commission_operator > 0
GROUP BY u.id, u.name, u.commission_percentage
ORDER BY comissao_mes DESC;

-- 5. Verificar cálculo de comissão para uma campanha específica (exemplo)
-- Substitua 'CAMPAIGN_ID_AQUI' pelo ID real da campanha
/*
SELECT
  dcm.date,
  dcm.campaign_id,
  dcm.revenue_converted_revshare,
  dcm.spend,
  (SELECT percentage FROM tax_history WHERE DATE_TRUNC('month', month) = DATE_TRUNC('month', dcm.date) LIMIT 1) AS tax_rate,
  dcm.revenue_converted_revshare * COALESCE((SELECT percentage/100 FROM tax_history WHERE DATE_TRUNC('month', month) = DATE_TRUNC('month', dcm.date) LIMIT 1), 0) AS tax_amount,
  dcm.revenue_converted_revshare - dcm.spend - (dcm.revenue_converted_revshare * COALESCE((SELECT percentage/100 FROM tax_history WHERE DATE_TRUNC('month', month) = DATE_TRUNC('month', dcm.date) LIMIT 1), 0)) AS net_profit,
  u.commission_percentage,
  dcm.commission_operator AS comissao_calculada,
  (dcm.revenue_converted_revshare - dcm.spend - (dcm.revenue_converted_revshare * COALESCE((SELECT percentage/100 FROM tax_history WHERE DATE_TRUNC('month', month) = DATE_TRUNC('month', dcm.date) LIMIT 1), 0))) * (u.commission_percentage / 100) AS comissao_manual
FROM daily_campaign_metrics dcm
JOIN user_campaigns uc ON uc.campaign_id = dcm.campaign_id
JOIN users u ON u.id = uc.user_id
WHERE dcm.campaign_id = 'CAMPAIGN_ID_AQUI'
  AND u.role = 'OPERADOR'
ORDER BY dcm.date DESC
LIMIT 10;
*/
