-- Migration 001: Add missing indexes on hot query paths
--
-- The decisions table is queried frequently by created_at + sport (history, usage,
-- engagement) and by decision_type (experiment results). These composite indexes
-- eliminate sequential scans on the most common access patterns.

-- Composite index for /history and /usage queries that filter by sport + date range
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decisions_sport_created
    ON decisions (sport, created_at DESC);

-- Composite index for decision_type + created_at (experiment and accuracy queries)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decisions_type_created
    ON decisions (decision_type, created_at DESC);

-- Composite index for prompt_variant analytics (/experiments/results)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decisions_variant
    ON decisions (prompt_variant, created_at DESC)
    WHERE prompt_variant IS NOT NULL;

-- Sessions: composite index for engagement queries that scan by created_at + status
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sessions_created_status
    ON sessions (created_at DESC, status);

-- Users: index on subscription_tier for billing/tier queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_subscription_tier
    ON users (subscription_tier)
    WHERE subscription_tier != 'free';
