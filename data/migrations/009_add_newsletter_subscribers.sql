-- Migration 009: Add newsletter subscribers table for email capture
-- Date: 2026-02-19
--
-- Self-hosted email list for pre-launch marketing (NFL Draft 2026).
-- Can export to Mailchimp/Buttondown later when the list grows.

CREATE TABLE IF NOT EXISTS newsletter_subscribers (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255),
    sport_interest VARCHAR(50),
    referrer VARCHAR(100),
    subscribed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    unsubscribed_at TIMESTAMPTZ,
    ip_address INET
);

-- Fast lookup by email (subscribe/unsubscribe)
CREATE INDEX IF NOT EXISTS idx_newsletter_email
    ON newsletter_subscribers (email);

-- Active subscribers ordered by signup date
CREATE INDEX IF NOT EXISTS idx_newsletter_subscribed
    ON newsletter_subscribers (subscribed_at DESC)
    WHERE unsubscribed_at IS NULL;
