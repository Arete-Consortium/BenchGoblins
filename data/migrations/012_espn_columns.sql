-- Migration 012: Add ESPN Fantasy integration columns to users table
-- Stores ESPN credentials and league connection for roster-aware AI decisions

ALTER TABLE users ADD COLUMN IF NOT EXISTS espn_swid VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS espn_s2 TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS espn_league_id VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS espn_team_id VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS espn_sport VARCHAR(10);
ALTER TABLE users ADD COLUMN IF NOT EXISTS espn_roster_snapshot JSONB;
ALTER TABLE users ADD COLUMN IF NOT EXISTS espn_synced_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_users_espn
    ON users(espn_league_id) WHERE espn_league_id IS NOT NULL;
