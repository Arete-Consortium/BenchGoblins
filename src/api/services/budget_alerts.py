"""
Budget Alert Service - Sends webhook notifications to Slack/Discord when spending thresholds are hit.

Integrates with budget configuration to send alerts when:
1. Spending reaches the configured alert_threshold_pct
2. Spending exceeds the monthly limit
"""

import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import func, select

from models.database import BudgetConfig
from models.database import Decision as DecisionModel
from services.database import db_service

logger = logging.getLogger(__name__)

# Cost per million tokens (Claude Sonnet pricing)
INPUT_COST_PER_MTOK = 3.0
OUTPUT_COST_PER_MTOK = 15.0

# Minimum hours between duplicate alerts at the same threshold level
ALERT_COOLDOWN_HOURS = 1


async def send_slack_alert(
    webhook_url: str,
    message: str,
    spend: float,
    limit: float,
    percent: float,
) -> bool:
    """Send a budget alert to Slack via incoming webhook.

    Args:
        webhook_url: Slack incoming webhook URL
        message: Alert message text
        spend: Current spending amount in USD
        limit: Monthly spending limit in USD
        percent: Percentage of budget used

    Returns:
        True if alert was sent successfully, False otherwise
    """
    if not webhook_url:
        return False

    # Build Slack message with rich formatting
    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "BenchGoblin Budget Alert",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message,
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Current Spend:*\n${spend:.2f}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Monthly Limit:*\n${limit:.2f}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Usage:*\n{percent:.1f}%",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Timestamp:*\n{datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
                    },
                ],
            },
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=payload)
            if response.status_code == 200:
                logger.info(f"Slack alert sent successfully: {message}")
                return True
            else:
                logger.error(f"Slack webhook failed: {response.status_code} - {response.text}")
                return False
    except httpx.HTTPError as e:
        logger.error(f"Slack webhook error: {e}")
        return False


async def send_discord_alert(
    webhook_url: str,
    message: str,
    spend: float,
    limit: float,
    percent: float,
) -> bool:
    """Send a budget alert to Discord via webhook.

    Args:
        webhook_url: Discord webhook URL
        message: Alert message text
        spend: Current spending amount in USD
        limit: Monthly spending limit in USD
        percent: Percentage of budget used

    Returns:
        True if alert was sent successfully, False otherwise
    """
    if not webhook_url:
        return False

    # Determine color based on severity
    if percent >= 100:
        color = 0xFF0000  # Red - exceeded
    elif percent >= 90:
        color = 0xFFA500  # Orange - critical
    else:
        color = 0xFFFF00  # Yellow - warning

    # Build Discord embed
    payload = {
        "embeds": [
            {
                "title": "BenchGoblin Budget Alert",
                "description": message,
                "color": color,
                "fields": [
                    {
                        "name": "Current Spend",
                        "value": f"${spend:.2f}",
                        "inline": True,
                    },
                    {
                        "name": "Monthly Limit",
                        "value": f"${limit:.2f}",
                        "inline": True,
                    },
                    {
                        "name": "Usage",
                        "value": f"{percent:.1f}%",
                        "inline": True,
                    },
                ],
                "timestamp": datetime.now(UTC).isoformat(),
            }
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=payload)
            # Discord returns 204 No Content on success
            if response.status_code in (200, 204):
                logger.info(f"Discord alert sent successfully: {message}")
                return True
            else:
                logger.error(f"Discord webhook failed: {response.status_code} - {response.text}")
                return False
    except httpx.HTTPError as e:
        logger.error(f"Discord webhook error: {e}")
        return False


async def _get_current_spend() -> float:
    """Get current month's spending from decisions table.

    Returns:
        Total spending in USD for the current month.
    """
    if not db_service.is_configured:
        return 0.0

    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    try:
        async with db_service.session() as session:
            usage_q = select(
                func.coalesce(func.sum(DecisionModel.input_tokens), 0).label("input"),
                func.coalesce(func.sum(DecisionModel.output_tokens), 0).label("output"),
            ).where(DecisionModel.created_at >= month_start)
            usage_row = (await session.execute(usage_q)).one()

            input_tokens = int(usage_row.input)
            output_tokens = int(usage_row.output)
            return (
                input_tokens / 1_000_000 * INPUT_COST_PER_MTOK
                + output_tokens / 1_000_000 * OUTPUT_COST_PER_MTOK
            )
    except Exception as e:
        logger.error(f"Failed to get current spend: {e}")
        return 0.0


async def _should_send_alert(
    config: BudgetConfig,
    current_percent: int,
) -> tuple[bool, str | None]:
    """Check if we should send an alert based on cooldown and threshold.

    Args:
        config: Budget configuration with last alert info
        current_percent: Current spending percentage

    Returns:
        Tuple of (should_send, message) where message is the alert text if applicable.
    """
    # No alerts if disabled or no limit set
    if not config.alerts_enabled:
        return False, None

    limit = float(config.monthly_limit_usd)
    if limit == 0:
        return False, None

    # No webhooks configured
    if not config.slack_webhook_url and not config.discord_webhook_url:
        return False, None

    # Determine if we're at a new threshold level
    threshold = config.alert_threshold_pct
    last_percent = config.last_alert_percent or 0
    last_alert_time = config.last_alert_time

    # Check if budget exceeded (always alert on first exceed)
    if current_percent >= 100 and last_percent < 100:
        return (
            True,
            f"Budget exceeded! Spending has reached {current_percent}% of the monthly limit.",
        )

    # Check if we hit the threshold (and haven't alerted at this level)
    if current_percent >= threshold and last_percent < threshold:
        return (
            True,
            f"Budget warning: Spending has reached {current_percent}% of the monthly limit (threshold: {threshold}%).",
        )

    # Check cooldown for repeated alerts at same threshold level
    if last_alert_time:
        hours_since_last = (datetime.now(UTC) - last_alert_time).total_seconds() / 3600
        if hours_since_last < ALERT_COOLDOWN_HOURS:
            return False, None

    # Alert every 10% after threshold, if enough time has passed
    if current_percent >= threshold:
        # Calculate current 10% bucket
        current_bucket = (current_percent // 10) * 10
        last_bucket = (last_percent // 10) * 10

        if current_bucket > last_bucket:
            if current_percent >= 100:
                return (
                    True,
                    f"Budget exceeded! Spending is now at {current_percent}% of the monthly limit.",
                )
            else:
                return (
                    True,
                    f"Budget alert: Spending has reached {current_percent}% of the monthly limit.",
                )

    return False, None


async def check_and_send_alerts() -> dict:
    """Check current spending and send webhook alerts if thresholds are hit.

    This should be called after each Claude API request.

    Returns:
        Dict with alert status information.
    """
    if not db_service.is_configured:
        return {"alerts_sent": False, "reason": "database_not_configured"}

    try:
        async with db_service.session() as session:
            # Get budget config
            config_q = select(BudgetConfig).order_by(BudgetConfig.id.desc()).limit(1)
            result = await session.execute(config_q)
            config = result.scalar_one_or_none()

            if not config:
                return {"alerts_sent": False, "reason": "no_budget_config"}

            # Calculate current spend
            spend = await _get_current_spend()
            limit = float(config.monthly_limit_usd)

            if limit == 0:
                return {"alerts_sent": False, "reason": "no_limit_set"}

            percent = (spend / limit * 100) if limit > 0 else 0
            current_percent = int(percent)

            # Check if we should send alert
            should_send, message = await _should_send_alert(config, current_percent)

            if not should_send or not message:
                return {
                    "alerts_sent": False,
                    "reason": "below_threshold",
                    "current_percent": current_percent,
                    "threshold_percent": config.alert_threshold_pct,
                }

            # Send alerts to configured webhooks
            alerts_sent = []

            if config.slack_webhook_url:
                success = await send_slack_alert(
                    webhook_url=config.slack_webhook_url,
                    message=message,
                    spend=spend,
                    limit=limit,
                    percent=percent,
                )
                if success:
                    alerts_sent.append("slack")

            if config.discord_webhook_url:
                success = await send_discord_alert(
                    webhook_url=config.discord_webhook_url,
                    message=message,
                    spend=spend,
                    limit=limit,
                    percent=percent,
                )
                if success:
                    alerts_sent.append("discord")

            # Update last alert time and percent if any alerts were sent
            if alerts_sent:
                config.last_alert_time = datetime.now(UTC)
                config.last_alert_percent = current_percent
                # Session will commit on exit

            return {
                "alerts_sent": bool(alerts_sent),
                "destinations": alerts_sent,
                "message": message,
                "current_spend_usd": round(spend, 4),
                "monthly_limit_usd": limit,
                "percent_used": round(percent, 2),
            }

    except Exception as e:
        logger.error(f"Budget alert check failed: {e}")
        return {"alerts_sent": False, "reason": f"error: {str(e)}"}


async def send_test_webhook(
    webhook_type: str,
    webhook_url: str,
) -> bool:
    """Send a test notification to verify webhook configuration.

    Args:
        webhook_type: Either "slack" or "discord"
        webhook_url: The webhook URL to test

    Returns:
        True if test notification was sent successfully.
    """
    message = "This is a test notification from BenchGoblin budget alerts."
    spend = 0.0
    limit = 100.0
    percent = 0.0

    if webhook_type.lower() == "slack":
        return await send_slack_alert(webhook_url, message, spend, limit, percent)
    elif webhook_type.lower() == "discord":
        return await send_discord_alert(webhook_url, message, spend, limit, percent)
    else:
        logger.error(f"Unknown webhook type: {webhook_type}")
        return False


# Alias for backward compatibility
test_webhook = send_test_webhook
