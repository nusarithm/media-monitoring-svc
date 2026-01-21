-- Create user_keywords table in Supabase
-- Run this in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS user_keywords (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    keywords TEXT[] NOT NULL,
    operator VARCHAR(10) NOT NULL DEFAULT 'OR' CHECK (operator IN ('AND', 'OR')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id)
);

-- Add indexes for better performance
CREATE INDEX IF NOT EXISTS idx_user_keywords_user_id ON user_keywords(user_id);

-- Add RLS (Row Level Security) policies
ALTER TABLE user_keywords ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own keywords
CREATE POLICY "Users can view own keywords" ON user_keywords
    FOR SELECT
    USING (auth.uid()::text = user_id::text);

-- Policy: Users can insert their own keywords
CREATE POLICY "Users can insert own keywords" ON user_keywords
    FOR INSERT
    WITH CHECK (auth.uid()::text = user_id::text);

-- Policy: Users can update their own keywords
CREATE POLICY "Users can update own keywords" ON user_keywords
    FOR UPDATE
    USING (auth.uid()::text = user_id::text);

-- Policy: Users can delete their own keywords
CREATE POLICY "Users can delete own keywords" ON user_keywords
    FOR DELETE
    USING (auth.uid()::text = user_id::text);

-- Add comment
COMMENT ON TABLE user_keywords IS 'Stores user monitoring keywords with AND/OR operator';
