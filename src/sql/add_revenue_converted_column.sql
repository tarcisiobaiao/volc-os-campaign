-- Migration: Add revenue_converted column to daily_campaign_metrics
-- This migration adds a column for BRL conversion of USD revenue values

-- 1. Add revenue_converted column to daily_campaign_metrics table
ALTER TABLE daily_campaign_metrics 
ADD COLUMN IF NOT EXISTS revenue_converted NUMERIC(12,2) DEFAULT 0;

-- 2. Add revenue_converted column to gam_metrics table (if it doesn't exist)
ALTER TABLE gam_metrics 
ADD COLUMN IF NOT EXISTS revenue_converted NUMERIC(12,2) DEFAULT 0;

-- 3. Create function to get current exchange rate
CREATE OR REPLACE FUNCTION get_current_usd_brl_rate()
RETURNS NUMERIC AS $$
DECLARE
    current_rate NUMERIC := 5.50; -- Default fallback rate
BEGIN
    -- Try to get rate from system_settings table
    SELECT COALESCE(
        (SELECT value::NUMERIC 
         FROM system_settings 
         WHERE key = 'dollar_exchange_rate' 
         ORDER BY updated_at DESC 
         LIMIT 1), 
        5.50
    ) INTO current_rate;
    
    RETURN current_rate;
END;
$$ LANGUAGE plpgsql;

-- 4. Create function to update all revenue conversions
CREATE OR REPLACE FUNCTION update_all_revenue_conversions()
RETURNS void AS $$
DECLARE
    current_rate NUMERIC;
    affected_rows INTEGER;
BEGIN
    -- Get current exchange rate
    SELECT get_current_usd_brl_rate() INTO current_rate;
    
    -- Update daily_campaign_metrics table
    UPDATE daily_campaign_metrics 
    SET revenue_converted = revenue * current_rate,
        updated_at = NOW()
    WHERE ABS(COALESCE(revenue_converted, 0) - (revenue * current_rate)) > 0.01;
    
    GET DIAGNOSTICS affected_rows = ROW_COUNT;
    RAISE NOTICE 'Updated % rows in daily_campaign_metrics with rate: %', affected_rows, current_rate;
    
    -- Update gam_metrics table  
    UPDATE gam_metrics 
    SET revenue_converted = revenue * current_rate,
        updated_at = NOW()
    WHERE ABS(COALESCE(revenue_converted, 0) - (revenue * current_rate)) > 0.01;
    
    GET DIAGNOSTICS affected_rows = ROW_COUNT;
    RAISE NOTICE 'Updated % rows in gam_metrics with rate: %', affected_rows, current_rate;
END;
$$ LANGUAGE plpgsql;

-- 5. Create trigger function for automatic updates when system_settings changes
CREATE OR REPLACE FUNCTION trigger_update_revenue_conversions()
RETURNS trigger AS $$
BEGIN
    -- Only trigger if the dollar_exchange_rate setting was updated
    IF NEW.key = 'dollar_exchange_rate' AND NEW.value::NUMERIC != OLD.value::NUMERIC THEN
        PERFORM update_all_revenue_conversions();
        RAISE NOTICE 'Exchange rate updated to %, all revenue conversions recalculated', NEW.value;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 6. Create trigger on system_settings table for rate changes
DROP TRIGGER IF EXISTS trigger_exchange_rate_update ON system_settings;
CREATE TRIGGER trigger_exchange_rate_update
    AFTER UPDATE ON system_settings
    FOR EACH ROW
    WHEN (NEW.key = 'dollar_exchange_rate')
    EXECUTE FUNCTION trigger_update_revenue_conversions();

-- 7. Create trigger for new revenue data in daily_campaign_metrics
CREATE OR REPLACE FUNCTION trigger_new_revenue_conversion_daily_campaign()
RETURNS trigger AS $$
DECLARE
    current_rate NUMERIC;
BEGIN
    -- Get current exchange rate
    SELECT get_current_usd_brl_rate() INTO current_rate;
    
    -- Set revenue_converted for new/updated records
    NEW.revenue_converted = NEW.revenue * current_rate;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 8. Create trigger for new revenue data in gam_metrics
CREATE OR REPLACE FUNCTION trigger_new_revenue_conversion_gam()
RETURNS trigger AS $$
DECLARE
    current_rate NUMERIC;
BEGIN
    -- Get current exchange rate
    SELECT get_current_usd_brl_rate() INTO current_rate;
    
    -- Set revenue_converted for new/updated records
    NEW.revenue_converted = NEW.revenue * current_rate;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 9. Add triggers to automatically convert revenue on insert/update
DROP TRIGGER IF EXISTS trigger_daily_campaign_metrics_revenue_conversion ON daily_campaign_metrics;
CREATE TRIGGER trigger_daily_campaign_metrics_revenue_conversion
    BEFORE INSERT OR UPDATE OF revenue ON daily_campaign_metrics
    FOR EACH ROW
    EXECUTE FUNCTION trigger_new_revenue_conversion_daily_campaign();

DROP TRIGGER IF EXISTS trigger_gam_metrics_revenue_conversion ON gam_metrics;
CREATE TRIGGER trigger_gam_metrics_revenue_conversion
    BEFORE INSERT OR UPDATE OF revenue ON gam_metrics
    FOR EACH ROW
    EXECUTE FUNCTION trigger_new_revenue_conversion_gam();

-- 10. Update existing data with current exchange rate
SELECT update_all_revenue_conversions();

-- 11. Create helpful indexes for performance
CREATE INDEX IF NOT EXISTS idx_daily_campaign_metrics_revenue_converted 
ON daily_campaign_metrics(revenue_converted);

CREATE INDEX IF NOT EXISTS idx_gam_metrics_revenue_converted 
ON gam_metrics(revenue_converted);

CREATE INDEX IF NOT EXISTS idx_system_settings_dollar_rate 
ON system_settings(key, updated_at) WHERE key = 'dollar_exchange_rate';

-- 12. Add comments for documentation
COMMENT ON COLUMN daily_campaign_metrics.revenue_converted IS 'Revenue converted from USD to BRL using current exchange rate';
COMMENT ON COLUMN gam_metrics.revenue_converted IS 'Revenue converted from USD to BRL using current exchange rate';
COMMENT ON FUNCTION get_current_usd_brl_rate() IS 'Returns current USD to BRL exchange rate from system_settings';
COMMENT ON FUNCTION update_all_revenue_conversions() IS 'Updates all revenue_converted columns with current exchange rate';

-- 13. Insert default exchange rate if it doesn't exist
INSERT INTO system_settings (key, value, description, created_at, updated_at)
VALUES (
    'dollar_exchange_rate', 
    '5.50', 
    'Taxa de câmbio USD para BRL para conversão automática de revenue',
    NOW(),
    NOW()
) ON CONFLICT (key) DO NOTHING;

COMMIT;




