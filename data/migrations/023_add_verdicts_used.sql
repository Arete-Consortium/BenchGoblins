-- Add verdicts_used column to track free Goblin Verdict usage
ALTER TABLE users ADD COLUMN IF NOT EXISTS verdicts_used INTEGER NOT NULL DEFAULT 0;
