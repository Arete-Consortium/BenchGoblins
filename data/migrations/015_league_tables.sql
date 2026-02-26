-- League management tables for commissioner/manager features.
-- Tracks leagues, memberships, and commissioner roles.

CREATE TABLE IF NOT EXISTS leagues (
    id SERIAL PRIMARY KEY,
    external_league_id VARCHAR(100) NOT NULL,
    platform VARCHAR(20) NOT NULL CHECK (platform IN ('sleeper', 'espn', 'yahoo')),
    name VARCHAR(200) NOT NULL,
    sport VARCHAR(20) NOT NULL CHECK (sport IN ('nfl', 'nba', 'mlb', 'nhl', 'soccer')),
    season VARCHAR(10) NOT NULL,
    commissioner_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    invite_code VARCHAR(32) UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_leagues_external UNIQUE (external_league_id, platform, season)
);

CREATE INDEX IF NOT EXISTS idx_leagues_commissioner ON leagues (commissioner_user_id);
CREATE INDEX IF NOT EXISTS idx_leagues_invite_code ON leagues (invite_code) WHERE invite_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_leagues_platform_season ON leagues (platform, season);

CREATE TABLE IF NOT EXISTS league_memberships (
    id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL DEFAULT 'member' CHECK (role IN ('commissioner', 'member')),
    external_team_id VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'invited', 'removed')),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_league_memberships UNIQUE (league_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_league_memberships_league ON league_memberships (league_id);
CREATE INDEX IF NOT EXISTS idx_league_memberships_user ON league_memberships (user_id);
CREATE INDEX IF NOT EXISTS idx_league_memberships_status ON league_memberships (status) WHERE status = 'active';
