-- ====================================================================
-- Migration: Add automatic commission_operator calculation
-- Description: Creates triggers and functions to automatically calculate
--              commission_operator based on user commission_percentage
--              and net profit (revenue_converted_revshare - spend - tax)
-- Formula: net_profit = revenue_converted_revshare - spend - (revenue_converted_revshare × tax_rate)
-- ====================================================================

BEGIN;

-- 1. Create function to get tax rate for a specific date
CREATE OR REPLACE FUNCTION get_tax_rate_for_date(target_date DATE)
RETURNS NUMERIC AS $$
DECLARE
    tax_rate NUMERIC;
BEGIN
    -- Get the tax percentage for the month of the target date
    SELECT percentage / 100 INTO tax_rate
    FROM tax_history
    WHERE DATE_TRUNC('month', month) = DATE_TRUNC('month', target_date)
    LIMIT 1;

    -- If no tax rate found, default to 0
    RETURN COALESCE(tax_rate, 0);
END;
$$ LANGUAGE plpgsql STABLE;

-- 2. Create function to calculate operator commission
CREATE OR REPLACE FUNCTION calculate_operator_commission(
    revenue_converted_revshare_value NUMERIC,
    spend_value NUMERIC,
    commission_percentage_value NUMERIC,
    target_date DATE
)
RETURNS NUMERIC AS $$
DECLARE
    tax_rate NUMERIC;
    tax_amount NUMERIC;
    net_profit NUMERIC;
BEGIN
    -- If commission percentage is null or zero, return 0
    IF commission_percentage_value IS NULL OR commission_percentage_value = 0 THEN
        RETURN 0;
    END IF;

    -- Get tax rate for the date
    tax_rate := get_tax_rate_for_date(target_date);

    -- Calculate tax amount: revenue_converted_revshare × tax_rate
    tax_amount := COALESCE(revenue_converted_revshare_value, 0) * tax_rate;

    -- Calculate net profit (LUCRO LÍQUIDO)
    -- net_profit = revenue_converted_revshare - spend - tax_amount
    net_profit := COALESCE(revenue_converted_revshare_value, 0)
                  - COALESCE(spend_value, 0)
                  - tax_amount;

    -- Only calculate commission if net profit is positive
    IF net_profit <= 0 THEN
        RETURN 0;
    END IF;

    -- Calculate commission: net_profit × (commission_percentage / 100)
    RETURN net_profit * (commission_percentage_value / 100);
END;
$$ LANGUAGE plpgsql STABLE;

-- 3. Create function to get commission percentage for a campaign
CREATE OR REPLACE FUNCTION get_campaign_operator_commission_percentage(campaign_id_param TEXT)
RETURNS NUMERIC AS $$
DECLARE
    commission_pct NUMERIC;
BEGIN
    -- Get the commission percentage from the operator associated with this campaign
    SELECT COALESCE(u.commission_percentage, 0) INTO commission_pct
    FROM user_campaigns uc
    JOIN users u ON u.id = uc.user_id
    WHERE uc.campaign_id = campaign_id_param
      AND u.role = 'OPERATOR'
    LIMIT 1;

    RETURN COALESCE(commission_pct, 0);
END;
$$ LANGUAGE plpgsql STABLE;

-- 4. Create trigger function to auto-calculate commission when metrics change
CREATE OR REPLACE FUNCTION trigger_calculate_commission_operator()
RETURNS trigger AS $$
DECLARE
    operator_commission_pct NUMERIC;
BEGIN
    -- Get the operator commission percentage for this campaign
    operator_commission_pct := get_campaign_operator_commission_percentage(NEW.campaign_id);

    -- Calculate commission_operator automatically (now includes date parameter)
    NEW.commission_operator := calculate_operator_commission(
        NEW.revenue_converted_revshare,
        NEW.spend,
        operator_commission_pct,
        NEW.date
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 5. Create trigger function when user commission changes
CREATE OR REPLACE FUNCTION trigger_update_user_commission()
RETURNS trigger AS $$
DECLARE
    affected_rows INTEGER := 0;
BEGIN
    -- Only trigger if commission_percentage changed
    IF NEW.commission_percentage IS DISTINCT FROM OLD.commission_percentage THEN
        -- Update all daily_campaign_metrics for campaigns associated with this operator
        UPDATE daily_campaign_metrics dcm
        SET commission_operator = calculate_operator_commission(
                dcm.revenue_converted_revshare,
                dcm.spend,
                NEW.commission_percentage,
                dcm.date
            ),
            updated_at = NOW()
        FROM user_campaigns uc
        WHERE uc.campaign_id = dcm.campaign_id
          AND uc.user_id = NEW.id;

        GET DIAGNOSTICS affected_rows = ROW_COUNT;

        RAISE NOTICE 'User % commission updated from % to %, recalculated % campaign metrics',
                     NEW.id, OLD.commission_percentage, NEW.commission_percentage, affected_rows;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 6. Create function to recalculate all commissions
CREATE OR REPLACE FUNCTION recalculate_all_operator_commissions()
RETURNS void AS $$
DECLARE
    total_affected INTEGER := 0;
BEGIN
    -- Update all daily_campaign_metrics with correct commission calculation
    UPDATE daily_campaign_metrics dcm
    SET commission_operator = calculate_operator_commission(
            dcm.revenue_converted_revshare,
            dcm.spend,
            COALESCE(u.commission_percentage, 0),
            dcm.date
        ),
        updated_at = NOW()
    FROM user_campaigns uc
    JOIN users u ON u.id = uc.user_id
    WHERE dcm.campaign_id = uc.campaign_id
      AND u.role = 'OPERATOR';

    GET DIAGNOSTICS total_affected = ROW_COUNT;
    RAISE NOTICE 'Recalculated % campaign metrics with operator commissions', total_affected;
END;
$$ LANGUAGE plpgsql;

-- 7. Create triggers

-- Trigger for daily_campaign_metrics - calculates commission on insert/update
DROP TRIGGER IF EXISTS trigger_daily_campaign_commission_calculation ON daily_campaign_metrics;
CREATE TRIGGER trigger_daily_campaign_commission_calculation
    BEFORE INSERT OR UPDATE OF revenue_converted_revshare, spend ON daily_campaign_metrics
    FOR EACH ROW
    EXECUTE FUNCTION trigger_calculate_commission_operator();

-- Trigger for users - updates all campaigns when operator commission changes
DROP TRIGGER IF EXISTS trigger_user_commission_update ON users;
CREATE TRIGGER trigger_user_commission_update
    AFTER UPDATE OF commission_percentage ON users
    FOR EACH ROW
    WHEN (NEW.role = 'OPERATOR')
    EXECUTE FUNCTION trigger_update_user_commission();

-- 8. Update existing data with correct commission calculations
SELECT recalculate_all_operator_commissions();

-- 9. Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_daily_campaign_metrics_commission_operator
ON daily_campaign_metrics(commission_operator) WHERE commission_operator > 0;

CREATE INDEX IF NOT EXISTS idx_users_commission_percentage
ON users(commission_percentage, role) WHERE role = 'OPERATOR';

-- 10. Add comments for documentation
COMMENT ON FUNCTION get_tax_rate_for_date(DATE) IS
'Gets the tax rate from tax_history for a specific date based on month';

COMMENT ON FUNCTION calculate_operator_commission(NUMERIC, NUMERIC, NUMERIC, DATE) IS
'Calculates operator commission: net_profit × commission_percentage, where net_profit = revenue_converted_revshare - spend - (revenue_converted_revshare × tax_rate)';

COMMENT ON FUNCTION get_campaign_operator_commission_percentage(TEXT) IS
'Gets the commission percentage for the operator associated with a campaign';

COMMENT ON FUNCTION recalculate_all_operator_commissions() IS
'Recalculates all commission_operator values for all campaigns with operators';

COMMENT ON COLUMN users.commission_percentage IS
'Operator commission percentage (0-100%). Changes apply from D0, not retroactive.';

COMMENT ON COLUMN daily_campaign_metrics.commission_operator IS
'Calculated operator commission: net_profit × (commission_percentage / 100), where net_profit includes tax deduction';

-- 11. Verification query
DO $$
DECLARE
    total_operators INTEGER;
    total_commissions INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_operators
    FROM users
    WHERE role = 'OPERATOR' AND commission_percentage > 0;

    SELECT COUNT(*) INTO total_commissions
    FROM daily_campaign_metrics
    WHERE commission_operator > 0;

    RAISE NOTICE '✅ Commission automation system installed successfully';
    RAISE NOTICE '📊 Operators with commission: %', total_operators;
    RAISE NOTICE '📊 Campaign metrics with commission: %', total_commissions;
END $$;

COMMIT;

-- 12. Example queries for verification
-- View commissions by operator:
-- SELECT
--   u.name,
--   u.commission_percentage,
--   COUNT(dcm.id) as total_days,
--   SUM(dcm.commission_operator) as total_commission
-- FROM users u
-- JOIN user_campaigns uc ON uc.user_id = u.id
-- JOIN daily_campaign_metrics dcm ON dcm.campaign_id = uc.campaign_id
-- WHERE u.role = 'OPERATOR'
-- GROUP BY u.id, u.name, u.commission_percentage;
