-- Migration: Add token usage tracking to decisions table
-- Date: 2026-01-27

ALTER TABLE decisions ADD COLUMN input_tokens INTEGER;
ALTER TABLE decisions ADD COLUMN output_tokens INTEGER;
ALTER TABLE decisions ADD COLUMN cache_hit BOOLEAN DEFAULT FALSE;
