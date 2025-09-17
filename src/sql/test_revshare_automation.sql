-- Test script for revshare automation
-- Execute these queries to test the implementation

-- 1. Test the calculation function
SELECT
    'Test calculation function' as test_description,
    calculate_revenue_after_revshare(1000, 0.1) as result_10_percent,
    calculate_revenue_after_revshare(1000, 0.15) as result_15_percent,
    calculate_revenue_after_revshare(1000, NULL) as result_null_revshare;

-- 2. Check current state before testing
SELECT
    'Current state check' as test_description,
    COUNT(*) as total_daily_metrics,
    COUNT(CASE WHEN revenue_converted_revshare IS NOT NULL THEN 1 END) as with_revshare,
    COUNT(CASE WHEN revenue_converted_revshare IS NULL THEN 1 END) as without_revshare
FROM daily_campaign_metrics;

-- 3. Check project revshare values
SELECT
    'Project revshare check' as test_description,
    id,
    project_name,
    revshare,
    CASE
        WHEN revshare IS NULL THEN 'NULL (will default to 10%)'
        ELSE CONCAT(revshare * 100, '%')
    END as revshare_display
FROM projects
ORDER BY id;

-- 4. Test sample calculation for specific campaigns
SELECT
    'Sample campaign calculations' as test_description,
    dcm.campaign_id,
    c.project_id,
    p.project_name,
    p.revshare as project_revshare,
    dcm.revenue_converted,
    dcm.revenue_converted_revshare as current_revshare_value,
    calculate_revenue_after_revshare(dcm.revenue_converted, COALESCE(p.revshare, 0.1)) as calculated_revshare_value,
    CASE
        WHEN dcm.revenue_converted_revshare = calculate_revenue_after_revshare(dcm.revenue_converted, COALESCE(p.revshare, 0.1))
        THEN 'CORRECT'
        ELSE 'NEEDS UPDATE'
    END as status
FROM daily_campaign_metrics dcm
JOIN campaigns c ON dcm.campaign_id = c.campaign_id
JOIN projects p ON c.project_id = p.id
WHERE dcm.revenue_converted > 0
LIMIT 10;

-- 5. Test update function for a specific project
-- (Uncomment to run actual update test)
-- SELECT update_project_campaigns_revshare(1);

-- 6. Verify trigger is working by simulating an insert
-- (This will test the trigger function)
BEGIN;
-- Create a temporary test record (will be rolled back)
INSERT INTO daily_campaign_metrics (
    campaign_id,
    date,
    spend,
    revenue_converted,
    clicks,
    impressions,
    conversions
) VALUES (
    (SELECT campaign_id FROM campaigns LIMIT 1),
    CURRENT_DATE,
    100.00,
    500.00,
    50,
    1000,
    5
);

-- Check if revenue_converted_revshare was calculated automatically
SELECT
    'Trigger test result' as test_description,
    campaign_id,
    revenue_converted,
    revenue_converted_revshare,
    CASE
        WHEN revenue_converted_revshare IS NOT NULL
        THEN 'TRIGGER WORKING'
        ELSE 'TRIGGER NOT WORKING'
    END as trigger_status
FROM daily_campaign_metrics
WHERE date = CURRENT_DATE
ORDER BY created_at DESC
LIMIT 1;

ROLLBACK;

-- 7. Check for any inconsistencies
SELECT
    'Inconsistency check' as test_description,
    COUNT(*) as inconsistent_records
FROM daily_campaign_metrics dcm
JOIN campaigns c ON dcm.campaign_id = c.campaign_id
JOIN projects p ON c.project_id = p.id
WHERE dcm.revenue_converted > 0
AND ABS(
    dcm.revenue_converted_revshare -
    calculate_revenue_after_revshare(dcm.revenue_converted, COALESCE(p.revshare, 0.1))
) > 0.01;