-- Add webhook support to budget_configs for Slack/Discord alerts
ALTER TABLE budget_configs
    ADD COLUMN IF NOT EXISTS alerts_enabled BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS slack_webhook_url TEXT,
    ADD COLUMN IF NOT EXISTS discord_webhook_url TEXT,
    ADD COLUMN IF NOT EXISTS last_alert_time TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS last_alert_percent INTEGER;

-- Add comment for documentation
COMMENT ON COLUMN budget_configs.alerts_enabled IS 'Master switch to enable/disable all webhook alerts';
COMMENT ON COLUMN budget_configs.slack_webhook_url IS 'Slack incoming webhook URL for budget alerts';
COMMENT ON COLUMN budget_configs.discord_webhook_url IS 'Discord webhook URL for budget alerts';
COMMENT ON COLUMN budget_configs.last_alert_time IS 'Timestamp of last webhook alert sent (prevents duplicates)';
COMMENT ON COLUMN budget_configs.last_alert_percent IS 'Percentage threshold at which last alert was sent';
