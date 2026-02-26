-- Cached weekly matchup results from Sleeper for rivalry tracking
CREATE TABLE IF NOT EXISTS league_matchups (
    id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    season VARCHAR(10) NOT NULL,
    week INTEGER NOT NULL,
    roster_id_a INTEGER NOT NULL,
    roster_id_b INTEGER NOT NULL,
    owner_id_a VARCHAR(100) NOT NULL,
    owner_id_b VARCHAR(100) NOT NULL,
    points_a NUMERIC(8, 2),
    points_b NUMERIC(8, 2),
    winner_owner_id VARCHAR(100),
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_league_matchup UNIQUE (league_id, season, week, roster_id_a, roster_id_b)
);

CREATE INDEX IF NOT EXISTS idx_league_matchups_league ON league_matchups (league_id, season);
CREATE INDEX IF NOT EXISTS idx_league_matchups_owners ON league_matchups (owner_id_a, owner_id_b);
