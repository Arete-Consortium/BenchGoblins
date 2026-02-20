-- Migration 011: Add Sleeper integration columns to users table
-- Stores Sleeper league connection data for roster-aware AI decisions

ALTER TABLE users ADD COLUMN IF NOT EXISTS sleeper_username VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS sleeper_user_id VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS sleeper_league_id VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS roster_snapshot JSONB;
ALTER TABLE users ADD COLUMN IF NOT EXISTS sleeper_synced_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_users_sleeper
    ON users(sleeper_username) WHERE sleeper_username IS NOT NULL;
