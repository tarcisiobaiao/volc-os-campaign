-- Migration: Add automatic revenue_converted_revshare calculation
-- This migration creates triggers and functions to automatically calculate
-- revenue_converted_revshare based on project revshare values

-- 1. Create function to calculate revenue after revshare
CREATE OR REPLACE FUNCTION calculate_revenue_after_revshare(
    revenue_converted_value NUMERIC,
    project_revshare NUMERIC
)
RETURNS NUMERIC AS $$
BEGIN
    -- If revshare is null, default to 0.1 (10%)
    IF project_revshare IS NULL THEN
        project_revshare := 0.1;
    END IF;

    -- Calculate revenue after discounting revshare
    RETURN revenue_converted_value * (1 - project_revshare);
END;
$$ LANGUAGE plpgsql;

-- 2. Create function to update revenue_converted_revshare for a campaign
CREATE OR REPLACE FUNCTION update_campaign_revshare(campaign_id_param TEXT)
RETURNS void AS $$
DECLARE
    project_revshare_value NUMERIC;
    affected_rows INTEGER;
BEGIN
    -- Get the project revshare for this campaign
    SELECT p.revshare INTO project_revshare_value
    FROM campaigns c
    JOIN projects p ON c.project_id = p.id
    WHERE c.campaign_id = campaign_id_param;

    -- Default to 10% if not found
    IF project_revshare_value IS NULL THEN
        project_revshare_value := 0.1;
    END IF;

    -- Update daily_campaign_metrics for this campaign
    UPDATE daily_campaign_metrics
    SET revenue_converted_revshare = calculate_revenue_after_revshare(revenue_converted, project_revshare_value),
        updated_at = NOW()
    WHERE campaign_id = campaign_id_param;

    GET DIAGNOSTICS affected_rows = ROW_COUNT;
    RAISE NOTICE 'Updated % rows for campaign % with revshare %', affected_rows, campaign_id_param, project_revshare_value;
END;
$$ LANGUAGE plpgsql;

-- 3. Create function to update all campaigns for a specific project
CREATE OR REPLACE FUNCTION update_project_campaigns_revshare(project_id_param INTEGER)
RETURNS void AS $$
DECLARE
    campaign_record RECORD;
    project_revshare_value NUMERIC;
    total_affected INTEGER := 0;
BEGIN
    -- Get the project revshare
    SELECT revshare INTO project_revshare_value
    FROM projects
    WHERE id = project_id_param;

    -- Default to 10% if not found
    IF project_revshare_value IS NULL THEN
        project_revshare_value := 0.1;
    END IF;

    -- Update all campaigns for this project
    UPDATE daily_campaign_metrics dcm
    SET revenue_converted_revshare = calculate_revenue_after_revshare(dcm.revenue_converted, project_revshare_value),
        updated_at = NOW()
    FROM campaigns c
    WHERE dcm.campaign_id = c.campaign_id
    AND c.project_id = project_id_param;

    GET DIAGNOSTICS total_affected = ROW_COUNT;
    RAISE NOTICE 'Updated % rows for project % with revshare %', total_affected, project_id_param, project_revshare_value;
END;
$$ LANGUAGE plpgsql;

-- 4. Create function to update all revenue_converted_revshare values
CREATE OR REPLACE FUNCTION update_all_revshare_calculations()
RETURNS void AS $$
DECLARE
    total_affected INTEGER := 0;
BEGIN
    -- Update all daily_campaign_metrics with correct revshare calculation
    UPDATE daily_campaign_metrics dcm
    SET revenue_converted_revshare = calculate_revenue_after_revshare(
        dcm.revenue_converted,
        COALESCE(p.revshare, 0.1)
    ),
    updated_at = NOW()
    FROM campaigns c
    JOIN projects p ON c.project_id = p.id
    WHERE dcm.campaign_id = c.campaign_id;

    GET DIAGNOSTICS total_affected = ROW_COUNT;
    RAISE NOTICE 'Updated % total rows with revshare calculations', total_affected;
END;
$$ LANGUAGE plpgsql;

-- 5. Create trigger function for when revenue_converted changes in daily_campaign_metrics
CREATE OR REPLACE FUNCTION trigger_calculate_revshare_daily_campaign()
RETURNS trigger AS $$
DECLARE
    project_revshare_value NUMERIC;
BEGIN
    -- Get the project revshare for this campaign
    SELECT p.revshare INTO project_revshare_value
    FROM campaigns c
    JOIN projects p ON c.project_id = p.id
    WHERE c.campaign_id = NEW.campaign_id;

    -- Default to 10% if not found
    IF project_revshare_value IS NULL THEN
        project_revshare_value := 0.1;
    END IF;

    -- Calculate revenue_converted_revshare automatically
    NEW.revenue_converted_revshare := calculate_revenue_after_revshare(NEW.revenue_converted, project_revshare_value);

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 6. Create trigger function for when project revshare changes
CREATE OR REPLACE FUNCTION trigger_update_project_revshare()
RETURNS trigger AS $$
BEGIN
    -- Only trigger if revshare value changed
    IF NEW.revshare IS DISTINCT FROM OLD.revshare THEN
        -- Update all campaigns for this project
        PERFORM update_project_campaigns_revshare(NEW.id);
        RAISE NOTICE 'Project % revshare updated from % to %, recalculating all campaign revshares',
                     NEW.id, OLD.revshare, NEW.revshare;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 7. Create triggers

-- Trigger for daily_campaign_metrics - calculates revshare on insert/update
DROP TRIGGER IF EXISTS trigger_daily_campaign_revshare_calculation ON daily_campaign_metrics;
CREATE TRIGGER trigger_daily_campaign_revshare_calculation
    BEFORE INSERT OR UPDATE OF revenue_converted ON daily_campaign_metrics
    FOR EACH ROW
    EXECUTE FUNCTION trigger_calculate_revshare_daily_campaign();

-- Trigger for projects - updates all campaigns when project revshare changes
DROP TRIGGER IF EXISTS trigger_project_revshare_update ON projects;
CREATE TRIGGER trigger_project_revshare_update
    AFTER UPDATE OF revshare ON projects
    FOR EACH ROW
    EXECUTE FUNCTION trigger_update_project_revshare();

-- 8. Update existing data with correct revshare calculations
SELECT update_all_revshare_calculations();

-- 9. Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_daily_campaign_metrics_revenue_converted_revshare
ON daily_campaign_metrics(revenue_converted_revshare);

CREATE INDEX IF NOT EXISTS idx_campaigns_project_id_campaign_id
ON campaigns(project_id, campaign_id);

CREATE INDEX IF NOT EXISTS idx_projects_revshare
ON projects(revshare);

-- 10. Add comments for documentation
COMMENT ON FUNCTION calculate_revenue_after_revshare(NUMERIC, NUMERIC) IS 'Calculates revenue after discounting project revshare percentage';
COMMENT ON FUNCTION update_campaign_revshare(TEXT) IS 'Updates revenue_converted_revshare for a specific campaign based on project revshare';
COMMENT ON FUNCTION update_project_campaigns_revshare(INTEGER) IS 'Updates revenue_converted_revshare for all campaigns of a project';
COMMENT ON FUNCTION update_all_revshare_calculations() IS 'Updates all revenue_converted_revshare values in the database';

COMMIT;