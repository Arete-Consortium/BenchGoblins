-- Add budget configuration table for cost monitoring
CREATE TABLE IF NOT EXISTS budget_configs (
    id SERIAL PRIMARY KEY,
    monthly_limit_usd NUMERIC(10, 2) NOT NULL,
    alert_threshold_pct INTEGER NOT NULL DEFAULT 80,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT check_monthly_limit_positive CHECK (monthly_limit_usd >= 0),
    CONSTRAINT check_alert_threshold_range CHECK (alert_threshold_pct >= 0 AND alert_threshold_pct <= 100)
);

-- Insert default budget config (no limit by default)
INSERT INTO budget_configs (monthly_limit_usd, alert_threshold_pct)
VALUES (0, 80);
