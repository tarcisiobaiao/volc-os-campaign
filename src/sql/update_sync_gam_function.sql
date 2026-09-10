-- Legacy compatibility installer.
--
-- IMPORTANT: `utm_campaign_value` is not universally a campaign id. Meta Ads
-- emits `{{adset.id}}`, so this file must preserve the same fail-closed router
-- installed by 20260910143000_gam_attribution_grain_router.sql. Do not restore
-- the old "insert a campaign for every GAM key" behavior here.

-- 1. Add new columns to daily_campaign_metrics (if not exist)
ALTER TABLE daily_campaign_metrics
ADD COLUMN IF NOT EXISTS gam_cpc NUMERIC(12,4) DEFAULT 0,
ADD COLUMN IF NOT EXISTS match_rate NUMERIC(5,2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS unfilled_impressions BIGINT DEFAULT 0,
ADD COLUMN IF NOT EXISTS viewable_impressions NUMERIC DEFAULT 0,
ADD COLUMN IF NOT EXISTS fill_rate NUMERIC(5,2) DEFAULT 0;

-- 2. Update existing sync function to include new columns
CREATE OR REPLACE FUNCTION sync_gam_revenue_to_daily_metrics()
RETURNS TRIGGER AS $$
DECLARE
  v_meta_matches bigint;
  v_google_matches bigint;
BEGIN
  SELECT count(DISTINCT s.meta_adset_id)
    INTO v_meta_matches
    FROM public.trafego_meta_adset s
   WHERE s.external_id = NEW.utm_campaign_value
     AND s.ausente_desde IS NULL;

  -- Meta revenue belongs to adset/day and is read directly from gam_metrics.
  IF v_meta_matches > 0 THEN
    RETURN NEW;
  END IF;

  SELECT count(*)
    INTO v_google_matches
    FROM public.campaigns c
   WHERE c.campaign_id = NEW.utm_campaign_value
     AND (NEW.project_id IS NULL OR c.project_id = NEW.project_id);

  -- Unknown/ambiguous keys remain visible in gam_metrics. Never invent a
  -- campaign-grain row from a transport key.
  IF v_google_matches <> 1 THEN
    RETURN NEW;
  END IF;

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
    viewable_impressions = NEW.viewable_impressions,
    updated_at = NOW()
  WHERE
    campaign_id = NEW.utm_campaign_value
    AND date = NEW.date;

  -- A compatible row may be created only after the real legacy campaign has
  -- resolved uniquely above.
  IF NOT FOUND THEN
    INSERT INTO daily_campaign_metrics (
      campaign_id, date, revenue, gam_impressions, gam_clicks, gam_ctr, gam_ecpm,
      gam_cpc, match_rate, unfilled_impressions, viewable_impressions,
      spend, clicks, impressions, conversions, cpc, ctr, roas, cost_per_conversion,
      page_views, ecpm, viewability, pmr, rps
    ) VALUES (
      NEW.utm_campaign_value, NEW.date, NEW.revenue, NEW.gam_impressions, NEW.gam_clicks, NEW.gam_ctr, NEW.gam_ecpm,
      NEW.gam_cpc, NEW.match_rate, NEW.unfilled_impressions, NEW.viewable_impressions,
      0, 0, 0, 0, 0, 0, 0, 0,  -- Métricas Google Ads zeradas
      0, 0, 0, 0, 0             -- Outras métricas GAM zeradas
    );

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
    viewable_impressions = COALESCE(gm.viewable_impressions, 0),
    updated_at = NOW()
FROM gam_metrics gm
WHERE dcm.campaign_id = gm.utm_campaign_value
  AND dcm.date = gm.date
  AND EXISTS (
    SELECT 1 FROM public.campaigns c
     WHERE c.campaign_id = gm.utm_campaign_value
       AND (gm.project_id IS NULL OR c.project_id = gm.project_id)
  )
  AND NOT EXISTS (
    SELECT 1 FROM public.trafego_meta_adset s
     WHERE s.external_id = gm.utm_campaign_value
       AND s.ausente_desde IS NULL
  )
  AND (
    gm.gam_cpc IS NOT NULL AND gm.gam_cpc > 0 OR
    gm.match_rate IS NOT NULL AND gm.match_rate > 0 OR
    gm.unfilled_impressions IS NOT NULL AND gm.unfilled_impressions > 0 OR
    gm.viewable_impressions IS NOT NULL AND gm.viewable_impressions > 0
  );

-- 4. Add comments for documentation
COMMENT ON COLUMN daily_campaign_metrics.gam_cpc IS 'GAM Cost Per Click (synced from gam_metrics)';
COMMENT ON COLUMN daily_campaign_metrics.match_rate IS 'Match rate percentage (synced from gam_metrics)';
COMMENT ON COLUMN daily_campaign_metrics.unfilled_impressions IS 'Unfilled impressions (synced from gam_metrics)';
COMMENT ON COLUMN daily_campaign_metrics.fill_rate IS 'Fill rate percentage (synced from gam_metrics)';

COMMIT;
