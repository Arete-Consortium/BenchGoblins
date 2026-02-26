-- Weekly AI-generated recap storage
CREATE TABLE IF NOT EXISTS weekly_recaps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    sport VARCHAR(10),
    -- Aggregated stats for the week
    total_decisions INTEGER NOT NULL DEFAULT 0,
    correct_decisions INTEGER NOT NULL DEFAULT 0,
    incorrect_decisions INTEGER NOT NULL DEFAULT 0,
    pending_decisions INTEGER NOT NULL DEFAULT 0,
    accuracy_pct NUMERIC(5, 2),
    avg_confidence VARCHAR(10),
    most_asked_sport VARCHAR(10),
    -- AI-generated narrative
    narrative TEXT NOT NULL,
    highlights TEXT,
    -- Token tracking
    input_tokens INTEGER,
    output_tokens INTEGER,
    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_weekly_recaps_user_week UNIQUE (user_id, week_start, sport)
);

CREATE INDEX IF NOT EXISTS idx_weekly_recaps_user ON weekly_recaps (user_id, week_start DESC);
CREATE INDEX IF NOT EXISTS idx_weekly_recaps_created ON weekly_recaps (created_at DESC);
