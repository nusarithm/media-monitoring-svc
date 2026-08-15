-- Media Monitoring Service - full schema for a plain PostgreSQL database.
-- Idempotent: safe to run more than once. Run against an empty `medmon` database:
--   psql "$DATABASE_URL" -f migrations/schema.sql

-- ---------------------------------------------------------------------------
-- subscription_tiers
-- ---------------------------------------------------------------------------
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
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO subscription_tiers
    (name, display_name, description, price_monthly, price_yearly, max_users, max_workspaces, historical_data_days, has_reporting_access, has_api_access, trial_days)
VALUES
    ('free',     'Free Trial', 'Trial version with limited features',            0,        0,   1,   1,   3, FALSE, FALSE, 14),
    ('basic',    'Basic',      'Perfect for small teams',                   500000,  5000000,   3,   1,   7, TRUE,  FALSE,  0),
    ('pro',      'Pro',        'Advanced features for growing teams',      3000000, 30000000,   5,   3,  30, TRUE,  TRUE,   0),
    ('business', 'Business',   'Enterprise solution - Contact admin for pricing', 0,        0, 999, 999, 365, TRUE, TRUE,   0)
ON CONFLICT (name) DO NOTHING;


-- ---------------------------------------------------------------------------
-- workspace (singular - matches app code)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS workspace (
    id SERIAL PRIMARY KEY,
    workspace_name TEXT NOT NULL,
    workspace_type TEXT,
    subscription_tier VARCHAR(50) NOT NULL DEFAULT 'free' REFERENCES subscription_tiers(name),
    subscription_status VARCHAR(20) NOT NULL DEFAULT 'active',
    subscription_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    subscription_expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '14 days',
    is_trial BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workspace_subscription ON workspace(subscription_tier, subscription_status);
CREATE INDEX IF NOT EXISTS idx_workspace_expires_at ON workspace(subscription_expires_at);


-- ---------------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    phone TEXT,
    password TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    workspace_id INTEGER REFERENCES workspace(id) ON DELETE CASCADE,
    role_id INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_workspace_id ON users(workspace_id);


-- ---------------------------------------------------------------------------
-- otp_codes
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS otp_codes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    otp_code TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    is_used BOOLEAN NOT NULL DEFAULT FALSE,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_otp_codes_lookup ON otp_codes(user_id, is_used);


-- ---------------------------------------------------------------------------
-- user_keywords
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_keywords (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    keywords TEXT[] NOT NULL,
    operator VARCHAR(10) NOT NULL DEFAULT 'OR' CHECK (operator IN ('AND', 'OR')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id)
);

CREATE INDEX IF NOT EXISTS idx_user_keywords_user_id ON user_keywords(user_id);

COMMENT ON TABLE user_keywords IS 'Stores user monitoring keywords with AND/OR operator';


-- ---------------------------------------------------------------------------
-- workspace_subscription_info (read model for /subscription/* endpoints)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW workspace_subscription_info AS
SELECT
    w.id AS workspace_id,
    w.workspace_name,
    w.workspace_type,
    w.subscription_tier,
    w.subscription_status,
    w.subscription_started_at,
    w.subscription_expires_at,
    w.is_trial,
    st.display_name AS tier_display_name,
    st.max_users,
    st.max_workspaces,
    st.historical_data_days,
    st.has_reporting_access,
    st.has_api_access,
    st.price_monthly,
    st.price_yearly,
    CASE
        WHEN w.subscription_expires_at IS NOT NULL AND w.subscription_expires_at < NOW() THEN TRUE
        WHEN w.subscription_status <> 'active' THEN TRUE
        ELSE FALSE
    END AS is_expired,
    CASE
        WHEN w.subscription_expires_at IS NOT NULL
            THEN EXTRACT(EPOCH FROM (w.subscription_expires_at - NOW()))::INTEGER
        ELSE NULL
    END AS seconds_until_expiry
FROM workspace w
LEFT JOIN subscription_tiers st ON w.subscription_tier = st.name;
