-- Add referral code to users and create referrals tracking table
ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code VARCHAR(12) UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by_user_id INTEGER REFERENCES users(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_pro_expires_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS referrals (
    id SERIAL PRIMARY KEY,
    referrer_user_id INTEGER NOT NULL REFERENCES users(id),
    referred_user_id INTEGER NOT NULL REFERENCES users(id),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, completed, expired
    referrer_reward_applied BOOLEAN NOT NULL DEFAULT FALSE,
    referred_reward_applied BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    UNIQUE(referrer_user_id, referred_user_id)
);

CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_user_id);
CREATE INDEX IF NOT EXISTS idx_referrals_status ON referrals(status);
CREATE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code);
