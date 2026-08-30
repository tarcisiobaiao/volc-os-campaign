-- Update existing sync function to include new GAM metrics columns
-- Adds: gam_cpc, match_rate, unfilled_impressions, fill_rate

-- 1. Add new columns to daily_campaign_metrics (if not exist)
ALTER TABLE daily_campaign_metrics
ADD COLUMN IF NOT EXISTS gam_cpc NUMERIC(12,4) DEFAULT 0,
ADD COLUMN IF NOT EXISTS match_rate NUMERIC(5,2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS unfilled_impressions BIGINT DEFAULT 0,
ADD COLUMN IF NOT EXISTS fill_rate NUMERIC(5,2) DEFAULT 0;

-- 2. Update existing sync function to include new columns
CREATE OR REPLACE FUNCTION sync_gam_revenue_to_daily_metrics()
RETURNS TRIGGER AS $$
BEGIN
  -- Quando dados GAM são inseridos/atualizados, atualizar dados na daily_campaign_metrics
  UPDATE daily_campaign_metrics
  SET
    revenue = NEW.revenue,
    gam_impressions = NEW.gam_impressions,
    gam_clicks = NEW.gam_clicks,
    gam_ctr = NEW.gam_ctr,
    gam_ecpm = NEW.gam_ecpm,
    gam_cpc = NEW.gam_cpc,
    match_rate = NEW.match_rate,
    unfilled_impressions = NEW.unfilled_impressions,
    fill_rate = NEW.fill_rate,
    updated_at = NOW()
  WHERE
    campaign_id = NEW.utm_campaign_value
    AND date = NEW.date;

  -- Se não encontrou linha na daily_campaign_metrics, criar uma nova
  IF NOT FOUND THEN
    INSERT INTO daily_campaign_metrics (
      campaign_id, date, revenue, gam_impressions, gam_clicks, gam_ctr, gam_ecpm,
      gam_cpc, match_rate, unfilled_impressions, fill_rate,
      spend, clicks, impressions, conversions, cpc, ctr, roas, cost_per_conversion,
      page_views, ecpm, viewability, pmr, rps
    ) VALUES (
      NEW.utm_campaign_value, NEW.date, NEW.revenue, NEW.gam_impressions, NEW.gam_clicks, NEW.gam_ctr, NEW.gam_ecpm,
      NEW.gam_cpc, NEW.match_rate, NEW.unfilled_impressions, NEW.fill_rate,
      0, 0, 0, 0, 0, 0, 0, 0,  -- Métricas Google Ads zeradas
      0, 0, 0, 0, 0             -- Outras métricas GAM zeradas
    );

    RAISE NOTICE 'Criada linha daily_campaign_metrics para campanha % na data %', NEW.utm_campaign_value, NEW.date;
  ELSE
    RAISE NOTICE 'Atualizado dados GAM para campanha % na data % - Revenue: %.2f, Impressions: %, Clicks: %, CTR: %.6f, eCPM: %.6f, CPC: %.4f, Match Rate: %.2f%%, Fill Rate: %.2f%%',
                 NEW.utm_campaign_value, NEW.date, NEW.revenue, NEW.gam_impressions, NEW.gam_clicks, NEW.gam_ctr, NEW.gam_ecpm, NEW.gam_cpc, NEW.match_rate, NEW.fill_rate;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 3. Sync existing data from gam_metrics to daily_campaign_metrics
UPDATE daily_campaign_metrics dcm
SET
    gam_cpc = COALESCE(gm.gam_cpc, 0),
    match_rate = COALESCE(gm.match_rate, 0),
    unfilled_impressions = COALESCE(gm.unfilled_impressions, 0),
    fill_rate = COALESCE(gm.fill_rate, 0),
    updated_at = NOW()
FROM gam_metrics gm
WHERE dcm.campaign_id = gm.utm_campaign_value
  AND dcm.date = gm.date
  AND (
    gm.gam_cpc IS NOT NULL AND gm.gam_cpc > 0 OR
    gm.match_rate IS NOT NULL AND gm.match_rate > 0 OR
    gm.unfilled_impressions IS NOT NULL AND gm.unfilled_impressions > 0 OR
    gm.fill_rate IS NOT NULL AND gm.fill_rate > 0
  );

-- 4. Add comments for documentation
COMMENT ON COLUMN daily_campaign_metrics.gam_cpc IS 'GAM Cost Per Click (synced from gam_metrics)';
COMMENT ON COLUMN daily_campaign_metrics.match_rate IS 'Match rate percentage (synced from gam_metrics)';
COMMENT ON COLUMN daily_campaign_metrics.unfilled_impressions IS 'Unfilled impressions (synced from gam_metrics)';
COMMENT ON COLUMN daily_campaign_metrics.fill_rate IS 'Fill rate percentage (synced from gam_metrics)';

COMMIT;
