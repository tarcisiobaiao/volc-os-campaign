-- Fix user_campaigns table to reference campaigns.campaign_id instead of campaigns.id
-- This ensures we're storing the Google Ads campaign identifier, not the internal PK

-- 1. Drop the existing foreign key constraint
ALTER TABLE user_campaigns
DROP CONSTRAINT IF EXISTS user_campaigns_campaign_id_fkey;

-- 2. Change the column type to match campaigns.campaign_id (varchar)
ALTER TABLE user_campaigns
ALTER COLUMN campaign_id TYPE VARCHAR(255);

-- 3. Add new foreign key constraint referencing campaigns.campaign_id
ALTER TABLE user_campaigns
ADD CONSTRAINT user_campaigns_campaign_id_fkey
FOREIGN KEY (campaign_id)
REFERENCES campaigns(campaign_id)
ON DELETE CASCADE;

-- 4. Update the unique constraint to use the new reference
ALTER TABLE user_campaigns
DROP CONSTRAINT IF EXISTS user_campaigns_user_id_campaign_id_key;

ALTER TABLE user_campaigns
ADD CONSTRAINT user_campaigns_user_id_campaign_id_key
UNIQUE(user_id, campaign_id);

-- 5. Recreate indexes
DROP INDEX IF EXISTS idx_user_campaigns_campaign_id;
CREATE INDEX idx_user_campaigns_campaign_id ON user_campaigns(campaign_id);

-- Update comments
COMMENT ON COLUMN user_campaigns.campaign_id IS 'Google Ads campaign identifier (referência a campaigns.campaign_id)';
