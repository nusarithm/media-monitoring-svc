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
-- payment_history (written by the Saweria payment webhook)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS payment_history (
    id SERIAL PRIMARY KEY,
    transaction_id TEXT UNIQUE NOT NULL,
    payment_type TEXT,
    workspace_id INTEGER NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
    subscription_tier VARCHAR(50) REFERENCES subscription_tiers(name),
    billing_period VARCHAR(20) NOT NULL CHECK (billing_period IN ('monthly', 'yearly')),
    amount_raw BIGINT,
    amount_to_display BIGINT,
    cut BIGINT,
    transaction_fee_policy TEXT,
    donator_name TEXT,
    donator_email TEXT,
    donator_is_user BOOLEAN,
    message TEXT,
    qr_string TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    webhook_payload JSONB,
    payment_created_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payment_history_workspace ON payment_history(workspace_id, created_at DESC);

COMMENT ON TABLE payment_history IS 'Payment records received from the Saweria webhook';


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


-- ---------------------------------------------------------------------------
-- topics - named keyword groups, so a user can compare "our brand" against
-- "competitor" instead of monitoring one flat keyword list
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS topics (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    keywords TEXT[] NOT NULL,
    operator VARCHAR(10) NOT NULL DEFAULT 'OR' CHECK (operator IN ('AND', 'OR')),
    color VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_topics_user_id ON topics(user_id);

COMMENT ON TABLE topics IS 'Named keyword groups compared side by side on the Compare page';


-- ---------------------------------------------------------------------------
-- alert_rules - volume/negative-sentiment spike thresholds per user
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alert_rules (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id BIGINT REFERENCES topics(id) ON DELETE CASCADE,
    -- 'volume': today's article count vs the trailing average
    -- 'negative': share of negative sentiment today
    metric VARCHAR(20) NOT NULL CHECK (metric IN ('volume', 'negative')),
    -- volume: multiple of the baseline (2.0 = double). negative: share 0..1
    threshold NUMERIC(6,2) NOT NULL,
    baseline_days INTEGER NOT NULL DEFAULT 7,
    email_to VARCHAR(255),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    -- set when the rule last fired, so one spike does not send hourly mail
    last_fired_at TIMESTAMPTZ,
    cooldown_hours INTEGER NOT NULL DEFAULT 12,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alert_rules_user_id ON alert_rules(user_id);
CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON alert_rules(enabled) WHERE enabled;

COMMENT ON TABLE alert_rules IS 'Spike thresholds evaluated by the alert sweep; emails via email_service';


-- ---------------------------------------------------------------------------
-- daily_summaries - cached LLM narrative, so opening the page does not call
-- the model again for a period that has already been summarised
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_summaries (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id BIGINT REFERENCES topics(id) ON DELETE CASCADE,
    date_from DATE NOT NULL,
    date_to DATE NOT NULL,
    summary TEXT NOT NULL,
    model VARCHAR(100),
    article_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, topic_id, date_from, date_to)
);

CREATE INDEX IF NOT EXISTS idx_daily_summaries_user ON daily_summaries(user_id, date_to DESC);

COMMENT ON TABLE daily_summaries IS 'Cached LLM coverage summaries keyed by user, topic and period';


-- ---------------------------------------------------------------------------
-- sosmed_keyword - keywords the social scraper searches for.
--
-- System-wide, not per user: the scraper collects for everyone the way the
-- news scraper does, and each user still narrows it down with their own
-- `user_keywords`. Underscored, not "sosmed-keyword": a hyphen would force
-- every query to quote the identifier.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sosmed_keyword (
    id BIGSERIAL PRIMARY KEY,
    keyword VARCHAR(200) NOT NULL,
    platform VARCHAR(30) NOT NULL DEFAULT 'threads',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    -- Written by the scraper after a run, so a scheduler can pick the
    -- least recently scraped keyword instead of always starting at the top.
    last_scraped_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (platform, keyword)
);

CREATE INDEX IF NOT EXISTS idx_sosmed_keyword_enabled
    ON sosmed_keyword (platform, last_scraped_at NULLS FIRST) WHERE enabled;

COMMENT ON TABLE sosmed_keyword IS 'Search terms for the social media scraper (sosmed-scraper)';

INSERT INTO sosmed_keyword (keyword, platform) VALUES ('mrtjkt', 'threads')
    ON CONFLICT (platform, keyword) DO NOTHING;


-- Insight caching reuses daily_summaries: same shape (text keyed by user and
-- period), but keyed by what was asked rather than by topic.
ALTER TABLE daily_summaries ADD COLUMN IF NOT EXISTS model_key VARCHAR(80);

CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_summaries_model_key
    ON daily_summaries (user_id, model_key, date_from, date_to)
    WHERE model_key IS NOT NULL;
