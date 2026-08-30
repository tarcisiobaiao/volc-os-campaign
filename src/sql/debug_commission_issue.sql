-- Debug commission calculation for marliseac@gmail.com
-- Execute this in Supabase SQL Editor

-- 1. Check user commission percentage
SELECT id, email, role, commission_percentage
FROM users
WHERE email = 'marliseac@gmail.com';

-- 2. Check if trigger exists and is enabled
SELECT
    tgname AS trigger_name,
    tgenabled AS enabled,
    pg_get_triggerdef(oid) AS trigger_definition
FROM pg_trigger
WHERE tgname = 'trigger_daily_campaign_commission_calculation';

-- 3. Check user_campaigns for marliseac
SELECT uc.user_id, uc.campaign_id, c.name as campaign_name, u.email
FROM user_campaigns uc
JOIN campaigns c ON c.id = uc.campaign_id
JOIN users u ON u.id = uc.user_id
WHERE u.email = 'marliseac@gmail.com'
LIMIT 10;

-- 4. Check daily_campaign_metrics for today with commission details
SELECT
    dcm.date,
    dcm.campaign_id,
    c.name as campaign_name,
    dcm.revenue_converted_revshare,
    dcm.spend,
    dcm.commission_operator,
    u.email as operator_email,
    u.commission_percentage
FROM daily_campaign_metrics dcm
JOIN campaigns c ON c.id = dcm.campaign_id
LEFT JOIN user_campaigns uc ON uc.campaign_id = dcm.campaign_id
LEFT JOIN users u ON u.id = uc.user_id AND u.role = 'OPERATOR'
WHERE dcm.date = CURRENT_DATE
  AND u.email = 'marliseac@gmail.com'
ORDER BY dcm.revenue_converted_revshare DESC NULLS LAST
LIMIT 10;

-- 5. Check tax rate for current month
SELECT month, percentage
FROM tax_history
WHERE DATE_TRUNC('month', month) = DATE_TRUNC('month', CURRENT_DATE);

-- 6. Manual commission calculation test for one campaign
SELECT
    dcm.campaign_id,
    c.name,
    dcm.revenue_converted_revshare,
    dcm.spend,
    (SELECT percentage / 100 FROM tax_history WHERE DATE_TRUNC('month', month) = DATE_TRUNC('month', dcm.date) LIMIT 1) as tax_rate,
    u.commission_percentage,
    -- Net profit = revenue - spend - tax
    (dcm.revenue_converted_revshare - dcm.spend - (dcm.revenue_converted_revshare * (SELECT percentage / 100 FROM tax_history WHERE DATE_TRUNC('month', month) = DATE_TRUNC('month', dcm.date) LIMIT 1))) as net_profit,
    -- Commission = net_profit * (commission_percentage / 100)
    ((dcm.revenue_converted_revshare - dcm.spend - (dcm.revenue_converted_revshare * (SELECT percentage / 100 FROM tax_history WHERE DATE_TRUNC('month', month) = DATE_TRUNC('month', dcm.date) LIMIT 1))) * (u.commission_percentage / 100)) as calculated_commission,
    dcm.commission_operator as stored_commission
FROM daily_campaign_metrics dcm
JOIN campaigns c ON c.id = dcm.campaign_id
JOIN user_campaigns uc ON uc.campaign_id = dcm.campaign_id
JOIN users u ON u.id = uc.user_id AND u.role = 'OPERATOR'
WHERE dcm.date = CURRENT_DATE
  AND u.email = 'marliseac@gmail.com'
  AND dcm.revenue_converted_revshare > 0
ORDER BY dcm.revenue_converted_revshare DESC
LIMIT 5;
