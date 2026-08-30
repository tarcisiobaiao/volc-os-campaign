-- Migration: Add GAM metrics columns and sync to daily_campaign_metrics
-- Adds: gam_cpc, match_rate, unfilled_impressions, fill_rate
-- Auto-syncs from gam_metrics to daily_campaign_metrics

-- 1. Add columns to gam_metrics table
ALTER TABLE gam_metrics
ADD COLUMN IF NOT EXISTS gam_cpc NUMERIC(12,4) DEFAULT 0,
ADD COLUMN IF NOT EXISTS match_rate NUMERIC(5,2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS unfilled_impressions BIGINT DEFAULT 0,
ADD COLUMN IF NOT EXISTS fill_rate NUMERIC(5,2) DEFAULT 0;

-- 2. Add columns to daily_campaign_metrics table
ALTER TABLE daily_campaign_metrics
ADD COLUMN IF NOT EXISTS gam_cpc NUMERIC(12,4) DEFAULT 0,
ADD COLUMN IF NOT EXISTS match_rate NUMERIC(5,2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS unfilled_impressions BIGINT DEFAULT 0,
ADD COLUMN IF NOT EXISTS fill_rate NUMERIC(5,2) DEFAULT 0;

-- 3. Create function to sync GAM metrics to daily_campaign_metrics
CREATE OR REPLACE FUNCTION sync_gam_metrics_to_daily_campaign()
RETURNS TRIGGER AS $$
BEGIN
    -- Update daily_campaign_metrics when gam_metrics is inserted/updated
    -- Match by utm_campaign_value (from gam_metrics) = campaign_id (in daily_campaign_metrics)
    -- and by date
    UPDATE daily_campaign_metrics
    SET
        gam_cpc = NEW.gam_cpc,
        match_rate = NEW.match_rate,
        unfilled_impressions = NEW.unfilled_impressions,
        fill_rate = NEW.fill_rate,
        updated_at = NOW()
    WHERE campaign_id = NEW.utm_campaign_value
      AND date = NEW.date;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 4. Create trigger on gam_metrics to auto-sync
DROP TRIGGER IF EXISTS trigger_sync_gam_to_daily_campaign ON gam_metrics;
CREATE TRIGGER trigger_sync_gam_to_daily_campaign
    AFTER INSERT OR UPDATE OF gam_cpc, match_rate, unfilled_impressions, fill_rate ON gam_metrics
    FOR EACH ROW
    EXECUTE FUNCTION sync_gam_metrics_to_daily_campaign();

-- 5. Sync existing data from gam_metrics to daily_campaign_metrics
UPDATE daily_campaign_metrics dcm
SET
    gam_cpc = gm.gam_cpc,
    match_rate = gm.match_rate,
    unfilled_impressions = gm.unfilled_impressions,
    fill_rate = gm.fill_rate,
    updated_at = NOW()
FROM gam_metrics gm
WHERE dcm.campaign_id = gm.utm_campaign_value
  AND dcm.date = gm.date
  AND (
    gm.gam_cpc IS NOT NULL OR
    gm.match_rate IS NOT NULL OR
    gm.unfilled_impressions IS NOT NULL OR
    gm.fill_rate IS NOT NULL
  );

-- 6. Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_gam_metrics_gam_cpc
ON gam_metrics(gam_cpc) WHERE gam_cpc > 0;

CREATE INDEX IF NOT EXISTS idx_gam_metrics_match_rate
ON gam_metrics(match_rate) WHERE match_rate > 0;

CREATE INDEX IF NOT EXISTS idx_gam_metrics_fill_rate
ON gam_metrics(fill_rate) WHERE fill_rate > 0;

CREATE INDEX IF NOT EXISTS idx_daily_campaign_metrics_gam_cpc
ON daily_campaign_metrics(gam_cpc) WHERE gam_cpc > 0;

CREATE INDEX IF NOT EXISTS idx_daily_campaign_metrics_match_rate
ON daily_campaign_metrics(match_rate) WHERE match_rate > 0;

CREATE INDEX IF NOT EXISTS idx_daily_campaign_metrics_fill_rate
ON daily_campaign_metrics(fill_rate) WHERE fill_rate > 0;

-- Index for the sync lookup (utm_campaign_value + date)
CREATE INDEX IF NOT EXISTS idx_gam_metrics_utm_campaign_date
ON gam_metrics(utm_campaign_value, date);

-- 7. Add comments for documentation
COMMENT ON COLUMN gam_metrics.gam_cpc IS 'GAM Cost Per Click';
COMMENT ON COLUMN gam_metrics.match_rate IS 'Match rate percentage (0-100)';
COMMENT ON COLUMN gam_metrics.unfilled_impressions IS 'Number of unfilled impressions';
COMMENT ON COLUMN gam_metrics.fill_rate IS 'Fill rate percentage (0-100)';

COMMENT ON COLUMN daily_campaign_metrics.gam_cpc IS 'GAM Cost Per Click (synced from gam_metrics)';
COMMENT ON COLUMN daily_campaign_metrics.match_rate IS 'Match rate percentage (synced from gam_metrics)';
COMMENT ON COLUMN daily_campaign_metrics.unfilled_impressions IS 'Unfilled impressions (synced from gam_metrics)';
COMMENT ON COLUMN daily_campaign_metrics.fill_rate IS 'Fill rate percentage (synced from gam_metrics)';

COMMENT ON FUNCTION sync_gam_metrics_to_daily_campaign() IS 'Auto-syncs GAM metrics columns from gam_metrics to daily_campaign_metrics';

COMMIT;
