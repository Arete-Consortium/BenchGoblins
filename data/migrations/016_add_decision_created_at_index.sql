-- Index on decisions.created_at for budget check aggregation queries
CREATE INDEX IF NOT EXISTS idx_decisions_created_at ON decisions (created_at);
