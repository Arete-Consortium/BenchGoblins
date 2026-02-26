-- Commissioner dispute resolution system
CREATE TABLE IF NOT EXISTS league_disputes (
    id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    filed_by_user_id INTEGER NOT NULL REFERENCES users(id),
    against_user_id INTEGER REFERENCES users(id),
    category VARCHAR(50) NOT NULL,  -- trade, roster, scoring, conduct, other
    subject VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'open',  -- open, under_review, resolved, dismissed
    resolution TEXT,
    resolved_by_user_id INTEGER REFERENCES users(id),
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_league_disputes_league ON league_disputes (league_id, status);
CREATE INDEX IF NOT EXISTS idx_league_disputes_user ON league_disputes (filed_by_user_id);
