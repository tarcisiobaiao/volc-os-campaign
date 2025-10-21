-- Force recalculation of commissions for all campaigns today (2025-10-20)
-- This updates commission_operator for all daily_campaign_metrics records

-- First, let's see what we're about to update
SELECT
    dcm.id,
    dcm.date,
    dcm.campaign_id,
    c.name as campaign_name,
    u.email as operator_email,
    u.commission_percentage,
    dcm.revenue_converted_revshare,
    dcm.spend,
    dcm.commission_operator as current_commission,
    -- Calculate what it should be
    calculate_operator_commission(
        dcm.revenue_converted_revshare,
        dcm.spend,
        COALESCE(u.commission_percentage, 0),
        dcm.date
    ) as calculated_commission
FROM daily_campaign_metrics dcm
JOIN campaigns c ON c.id = dcm.campaign_id
LEFT JOIN user_campaigns uc ON uc.campaign_id = dcm.campaign_id
LEFT JOIN users u ON u.id = uc.user_id AND u.role = 'OPERATOR' AND u.commission_percentage > 0
WHERE dcm.date >= '2025-10-20'
  AND u.id IS NOT NULL
  AND dcm.revenue_converted_revshare IS NOT NULL
  AND dcm.spend IS NOT NULL
ORDER BY dcm.date DESC, u.email, dcm.revenue_converted_revshare DESC
LIMIT 20;

-- Now update the commission_operator values
-- This recalculates for all campaigns that have an operator assigned with commission > 0
UPDATE daily_campaign_metrics dcm
SET commission_operator = calculate_operator_commission(
    dcm.revenue_converted_revshare,
    dcm.spend,
    COALESCE(u.commission_percentage, 0),
    dcm.date
)
FROM campaigns c
JOIN user_campaigns uc ON uc.campaign_id = c.id
JOIN users u ON u.id = uc.user_id AND u.role = 'OPERATOR' AND u.commission_percentage > 0
WHERE dcm.campaign_id = c.id
  AND dcm.date >= '2025-10-20'
  AND dcm.revenue_converted_revshare IS NOT NULL
  AND dcm.spend IS NOT NULL;

-- Verify the update
SELECT
    dcm.date,
    u.email as operator_email,
    COUNT(*) as campaigns_count,
    SUM(dcm.commission_operator) as total_commission,
    SUM(dcm.revenue_converted_revshare) as total_revenue,
    SUM(dcm.spend) as total_spend
FROM daily_campaign_metrics dcm
JOIN campaigns c ON c.id = dcm.campaign_id
JOIN user_campaigns uc ON uc.campaign_id = dcm.campaign_id
JOIN users u ON u.id = uc.user_id AND u.role = 'OPERATOR' AND u.commission_percentage > 0
WHERE dcm.date >= '2025-10-20'
  AND dcm.commission_operator > 0
GROUP BY dcm.date, u.email
ORDER BY dcm.date DESC, u.email;
