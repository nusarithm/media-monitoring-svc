-- Create subscription tiers table
CREATE TABLE IF NOT EXISTS subscription_tiers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    description TEXT,
    price_monthly INTEGER NOT NULL DEFAULT 0,
    price_yearly INTEGER NOT NULL DEFAULT 0,
    max_users INTEGER NOT NULL DEFAULT 1,
    max_workspaces INTEGER NOT NULL DEFAULT 1,
    historical_data_days INTEGER NOT NULL DEFAULT 3,
    has_reporting_access BOOLEAN NOT NULL DEFAULT FALSE,
    has_api_access BOOLEAN NOT NULL DEFAULT FALSE,
    trial_days INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Insert default tiers
INSERT INTO subscription_tiers (name, display_name, description, price_monthly, price_yearly, max_users, max_workspaces, historical_data_days, has_reporting_access, has_api_access, trial_days) VALUES
    ('free', 'Free Trial', 'Trial version with limited features', 0, 0, 1, 1, 3, FALSE, FALSE, 14),
    ('basic', 'Basic', 'Perfect for small teams', 500000, 5000000, 3, 1, 7, TRUE, FALSE, 0),
    ('pro', 'Pro', 'Advanced features for growing teams', 3000000, 30000000, 5, 3, 30, TRUE, TRUE, 0),
    ('business', 'Business', 'Enterprise solution - Contact admin for pricing', 0, 0, 999, 999, 365, TRUE, TRUE, 0)
ON CONFLICT (name) DO NOTHING;

-- Add subscription fields to workspaces table
ALTER TABLE workspaces 
    ADD COLUMN IF NOT EXISTS subscription_tier VARCHAR(50) DEFAULT 'free' REFERENCES subscription_tiers(name),
    ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(20) DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS subscription_started_at TIMESTAMP DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS subscription_expires_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS is_trial BOOLEAN DEFAULT TRUE;

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_workspaces_subscription ON workspaces(subscription_tier, subscription_status);
CREATE INDEX IF NOT EXISTS idx_workspaces_expires_at ON workspaces(subscription_expires_at);

-- Update existing workspaces to have expiry date (14 days from created_at)
UPDATE workspaces 
SET 
    subscription_tier = 'free',
    is_trial = TRUE,
    subscription_started_at = created_at,
    subscription_expires_at = created_at + INTERVAL '14 days'
WHERE subscription_expires_at IS NULL;

-- Create function to check if workspace is expired
CREATE OR REPLACE FUNCTION is_workspace_expired(workspace_id INTEGER)
RETURNS BOOLEAN AS $$
DECLARE
    expires_at TIMESTAMP;
    is_active BOOLEAN;
BEGIN
    SELECT subscription_expires_at, subscription_status = 'active'
    INTO expires_at, is_active
    FROM workspaces
    WHERE id = workspace_id;
    
    IF NOT is_active THEN
        RETURN TRUE;
    END IF;
    
    IF expires_at IS NOT NULL AND expires_at < NOW() THEN
        RETURN TRUE;
    END IF;
    
    RETURN FALSE;
END;
$$ LANGUAGE plpgsql;

-- Create view for workspace subscription info
CREATE OR REPLACE VIEW workspace_subscription_info AS
SELECT 
    w.id as workspace_id,
    w.workspace_name,
    w.subscription_tier,
    w.subscription_status,
    w.subscription_started_at,
    w.subscription_expires_at,
    w.is_trial,
    st.display_name as tier_display_name,
    st.max_users,
    st.max_workspaces,
    st.historical_data_days,
    st.has_reporting_access,
    st.has_api_access,
    st.price_monthly,
    st.price_yearly,
    CASE 
        WHEN w.subscription_expires_at IS NOT NULL AND w.subscription_expires_at < NOW() THEN TRUE
        WHEN w.subscription_status != 'active' THEN TRUE
        ELSE FALSE
    END as is_expired,
    CASE 
        WHEN w.subscription_expires_at IS NOT NULL THEN 
            EXTRACT(EPOCH FROM (w.subscription_expires_at - NOW()))::INTEGER
        ELSE NULL
    END as seconds_until_expiry
FROM workspaces w
LEFT JOIN subscription_tiers st ON w.subscription_tier = st.name;
