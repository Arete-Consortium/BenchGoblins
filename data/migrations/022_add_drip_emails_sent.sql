-- Add drip_emails_sent JSONB column to users for tracking onboarding email sequences.
-- Stores {"welcome": "2026-03-05T...", "connect_league": "2026-03-06T...", ...}

ALTER TABLE users ADD COLUMN IF NOT EXISTS drip_emails_sent JSONB;
