-- Migration 008: Add composite indexes on hot query paths
-- Date: 2026-02-18
--
-- These indexes target the most common query patterns in the API:
-- listing decisions by sport, type, or variant with time ordering,
-- session lookups by status+time, and filtering paid users.

-- Decisions: filter by sport, order by created_at DESC
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decisions_sport_created
    ON decisions (sport, created_at DESC);

-- Decisions: filter by decision_type, order by created_at DESC
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decisions_type_created
    ON decisions (decision_type, created_at DESC);

-- Decisions: filter by prompt_variant (A/B testing), order by created_at DESC
-- Partial index: only rows where prompt_variant is set
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decisions_variant
    ON decisions (prompt_variant, created_at DESC)
    WHERE prompt_variant IS NOT NULL;

-- Sessions: order by created_at DESC with status filter
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sessions_created_status
    ON sessions (created_at DESC, status);

-- Users: partial index for paid subscribers (skip the majority 'free' rows)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_subscription_tier
    ON users (subscription_tier)
    WHERE subscription_tier != 'free';
