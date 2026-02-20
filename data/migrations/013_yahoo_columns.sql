-- Migration 013: Add Yahoo Fantasy integration columns to users table
-- Stores Yahoo OAuth tokens and league connection for roster-aware AI decisions

ALTER TABLE users ADD COLUMN IF NOT EXISTS yahoo_access_token TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS yahoo_refresh_token TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS yahoo_token_expires_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS yahoo_user_guid VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS yahoo_league_key VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS yahoo_team_key VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS yahoo_sport VARCHAR(10);
ALTER TABLE users ADD COLUMN IF NOT EXISTS yahoo_roster_snapshot JSONB;
ALTER TABLE users ADD COLUMN IF NOT EXISTS yahoo_synced_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_users_yahoo
    ON users(yahoo_league_key) WHERE yahoo_league_key IS NOT NULL;
