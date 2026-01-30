"""
Tests for the budget alerts webhook service.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import from services
from services.budget_alerts import (
    ALERT_COOLDOWN_HOURS,
    INPUT_COST_PER_MTOK,
    OUTPUT_COST_PER_MTOK,
    _get_current_spend,
    _should_send_alert,
    check_and_send_alerts,
    send_discord_alert,
    send_slack_alert,
)
from services.budget_alerts import send_test_webhook


class TestSendSlackAlert:
    """Tests for send_slack_alert function."""

    @pytest.mark.asyncio
    async def test_send_slack_alert_success(self):
        """Test successful Slack alert delivery."""
        with patch("services.budget_alerts.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await send_slack_alert(
                webhook_url="https://hooks.slack.com/services/test",
                message="Budget warning: Spending at 80%",
                spend=80.0,
                limit=100.0,
                percent=80.0,
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_send_slack_alert_empty_url(self):
        """Test that empty webhook URL returns False."""
        result = await send_slack_alert(
            webhook_url="",
            message="Test",
            spend=50.0,
            limit=100.0,
            percent=50.0,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_send_slack_alert_none_url(self):
        """Test that None webhook URL returns False."""
        result = await send_slack_alert(
            webhook_url=None,  # type: ignore
            message="Test",
            spend=50.0,
            limit=100.0,
            percent=50.0,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_send_slack_alert_http_error(self):
        """Test handling of HTTP errors."""
        import httpx

        with patch("services.budget_alerts.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.HTTPError("Connection failed")
            )

            result = await send_slack_alert(
                webhook_url="https://hooks.slack.com/services/test",
                message="Budget warning",
                spend=80.0,
                limit=100.0,
                percent=80.0,
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_slack_alert_non_200_response(self):
        """Test handling of non-200 response from Slack."""
        with patch("services.budget_alerts.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = "Bad request"
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await send_slack_alert(
                webhook_url="https://hooks.slack.com/services/test",
                message="Budget warning",
                spend=80.0,
                limit=100.0,
                percent=80.0,
            )

            assert result is False


class TestSendDiscordAlert:
    """Tests for send_discord_alert function."""

    @pytest.mark.asyncio
    async def test_send_discord_alert_success(self):
        """Test successful Discord alert delivery."""
        with patch("services.budget_alerts.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 204  # Discord returns 204 on success
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await send_discord_alert(
                webhook_url="https://discord.com/api/webhooks/test",
                message="Budget warning: Spending at 80%",
                spend=80.0,
                limit=100.0,
                percent=80.0,
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_send_discord_alert_empty_url(self):
        """Test that empty webhook URL returns False."""
        result = await send_discord_alert(
            webhook_url="",
            message="Test",
            spend=50.0,
            limit=100.0,
            percent=50.0,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_send_discord_alert_http_error(self):
        """Test handling of HTTP errors."""
        import httpx

        with patch("services.budget_alerts.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.HTTPError("Connection failed")
            )

            result = await send_discord_alert(
                webhook_url="https://discord.com/api/webhooks/test",
                message="Budget warning",
                spend=80.0,
                limit=100.0,
                percent=80.0,
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_discord_alert_color_codes(self):
        """Test Discord embed color based on severity."""
        with patch("services.budget_alerts.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 204
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            # Test exceeded (should be red)
            await send_discord_alert(
                webhook_url="https://discord.com/api/webhooks/test",
                message="Budget exceeded",
                spend=110.0,
                limit=100.0,
                percent=110.0,
            )

            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert payload["embeds"][0]["color"] == 0xFF0000  # Red

    @pytest.mark.asyncio
    async def test_send_discord_alert_warning_color(self):
        """Test Discord embed color for warning level."""
        with patch("services.budget_alerts.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 204
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            # Test warning level (should be yellow)
            await send_discord_alert(
                webhook_url="https://discord.com/api/webhooks/test",
                message="Budget warning",
                spend=80.0,
                limit=100.0,
                percent=80.0,
            )

            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert payload["embeds"][0]["color"] == 0xFFFF00  # Yellow


class TestShouldSendAlert:
    """Tests for _should_send_alert function."""

    @pytest.mark.asyncio
    async def test_alerts_disabled(self):
        """Test that disabled alerts return False."""
        config = MagicMock()
        config.alerts_enabled = False
        config.monthly_limit_usd = 100

        should_send, message = await _should_send_alert(config, 85)
        assert should_send is False
        assert message is None

    @pytest.mark.asyncio
    async def test_no_limit_set(self):
        """Test that zero limit returns False."""
        config = MagicMock()
        config.alerts_enabled = True
        config.monthly_limit_usd = 0

        should_send, message = await _should_send_alert(config, 85)
        assert should_send is False
        assert message is None

    @pytest.mark.asyncio
    async def test_no_webhooks_configured(self):
        """Test that missing webhooks return False."""
        config = MagicMock()
        config.alerts_enabled = True
        config.monthly_limit_usd = 100
        config.slack_webhook_url = None
        config.discord_webhook_url = None

        should_send, message = await _should_send_alert(config, 85)
        assert should_send is False
        assert message is None

    @pytest.mark.asyncio
    async def test_first_threshold_hit(self):
        """Test alert is sent on first threshold hit."""
        config = MagicMock()
        config.alerts_enabled = True
        config.monthly_limit_usd = 100
        config.alert_threshold_pct = 80
        config.slack_webhook_url = "https://hooks.slack.com/test"
        config.discord_webhook_url = None
        config.last_alert_percent = 0
        config.last_alert_time = None

        should_send, message = await _should_send_alert(config, 85)
        assert should_send is True
        assert "80%" in message or "85%" in message

    @pytest.mark.asyncio
    async def test_budget_exceeded(self):
        """Test alert is sent when budget exceeded."""
        config = MagicMock()
        config.alerts_enabled = True
        config.monthly_limit_usd = 100
        config.alert_threshold_pct = 80
        config.slack_webhook_url = "https://hooks.slack.com/test"
        config.discord_webhook_url = None
        config.last_alert_percent = 90
        config.last_alert_time = None

        should_send, message = await _should_send_alert(config, 105)
        assert should_send is True
        assert "exceeded" in message.lower()

    @pytest.mark.asyncio
    async def test_no_duplicate_at_same_level(self):
        """Test no duplicate alert at same percentage level."""
        config = MagicMock()
        config.alerts_enabled = True
        config.monthly_limit_usd = 100
        config.alert_threshold_pct = 80
        config.slack_webhook_url = "https://hooks.slack.com/test"
        config.discord_webhook_url = None
        config.last_alert_percent = 85
        config.last_alert_time = datetime.now(UTC) - timedelta(minutes=30)

        # Same bucket (80-89%)
        should_send, message = await _should_send_alert(config, 86)
        assert should_send is False

    @pytest.mark.asyncio
    async def test_alert_at_next_10_percent_bucket(self):
        """Test alert is sent when crossing to next 10% bucket."""
        config = MagicMock()
        config.alerts_enabled = True
        config.monthly_limit_usd = 100
        config.alert_threshold_pct = 80
        config.slack_webhook_url = "https://hooks.slack.com/test"
        config.discord_webhook_url = None
        config.last_alert_percent = 85
        config.last_alert_time = datetime.now(UTC) - timedelta(hours=2)

        # New bucket (90%)
        should_send, message = await _should_send_alert(config, 92)
        assert should_send is True
        assert "92%" in message


class TestCheckAndSendAlerts:
    """Tests for check_and_send_alerts function."""

    @pytest.mark.asyncio
    async def test_database_not_configured(self):
        """Test handling when database is not configured."""
        with patch("services.budget_alerts.db_service") as mock_db:
            mock_db.is_configured = False

            result = await check_and_send_alerts()

            assert result["alerts_sent"] is False
            assert result["reason"] == "database_not_configured"

    @pytest.mark.asyncio
    async def test_no_budget_config(self):
        """Test handling when no budget config exists."""
        with patch("services.budget_alerts.db_service") as mock_db:
            mock_db.is_configured = True

            # Create a proper async context manager mock
            mock_execute_result = MagicMock()
            mock_execute_result.scalar_one_or_none.return_value = None

            mock_session_obj = AsyncMock()
            mock_session_obj.execute = AsyncMock(return_value=mock_execute_result)

            mock_context_manager = AsyncMock()
            mock_context_manager.__aenter__.return_value = mock_session_obj
            mock_context_manager.__aexit__.return_value = None

            mock_db.session.return_value = mock_context_manager

            result = await check_and_send_alerts()

            assert result["alerts_sent"] is False
            assert result["reason"] == "no_budget_config"

    @pytest.mark.asyncio
    async def test_below_threshold(self):
        """Test when spending is below threshold."""
        mock_config = MagicMock()
        mock_config.alerts_enabled = True
        mock_config.monthly_limit_usd = 100
        mock_config.alert_threshold_pct = 80
        mock_config.slack_webhook_url = "https://hooks.slack.com/test"
        mock_config.discord_webhook_url = None
        mock_config.last_alert_percent = 0
        mock_config.last_alert_time = None

        with (
            patch("services.budget_alerts.db_service") as mock_db,
            patch(
                "services.budget_alerts._get_current_spend", new_callable=AsyncMock
            ) as mock_spend,
        ):
            mock_db.is_configured = True

            # Create a proper async context manager mock
            mock_execute_result = MagicMock()
            mock_execute_result.scalar_one_or_none.return_value = mock_config

            mock_session_obj = AsyncMock()
            mock_session_obj.execute = AsyncMock(return_value=mock_execute_result)

            mock_context_manager = AsyncMock()
            mock_context_manager.__aenter__.return_value = mock_session_obj
            mock_context_manager.__aexit__.return_value = None

            mock_db.session.return_value = mock_context_manager
            mock_spend.return_value = 50.0  # 50% of limit

            result = await check_and_send_alerts()

            assert result["alerts_sent"] is False
            assert result["reason"] == "below_threshold"

    @pytest.mark.asyncio
    async def test_sends_to_both_webhooks(self):
        """Test alerts are sent to both Slack and Discord when configured."""
        mock_config = MagicMock()
        mock_config.alerts_enabled = True
        mock_config.monthly_limit_usd = 100
        mock_config.alert_threshold_pct = 80
        mock_config.slack_webhook_url = "https://hooks.slack.com/test"
        mock_config.discord_webhook_url = "https://discord.com/api/webhooks/test"
        mock_config.last_alert_percent = 0
        mock_config.last_alert_time = None

        with (
            patch("services.budget_alerts.db_service") as mock_db,
            patch(
                "services.budget_alerts._get_current_spend", new_callable=AsyncMock
            ) as mock_spend,
            patch(
                "services.budget_alerts.send_slack_alert", new_callable=AsyncMock
            ) as mock_slack,
            patch(
                "services.budget_alerts.send_discord_alert", new_callable=AsyncMock
            ) as mock_discord,
        ):
            mock_db.is_configured = True

            # Create a proper async context manager mock
            mock_execute_result = MagicMock()
            mock_execute_result.scalar_one_or_none.return_value = mock_config

            mock_session_obj = AsyncMock()
            mock_session_obj.execute = AsyncMock(return_value=mock_execute_result)

            mock_context_manager = AsyncMock()
            mock_context_manager.__aenter__.return_value = mock_session_obj
            mock_context_manager.__aexit__.return_value = None

            mock_db.session.return_value = mock_context_manager
            mock_spend.return_value = 85.0  # 85% of limit
            mock_slack.return_value = True
            mock_discord.return_value = True

            result = await check_and_send_alerts()

            assert result["alerts_sent"] is True
            assert "slack" in result["destinations"]
            assert "discord" in result["destinations"]
            mock_slack.assert_called_once()
            mock_discord.assert_called_once()


class TestTestWebhookFunc:
    """Tests for test_webhook function."""

    @pytest.mark.asyncio
    async def test_slack_webhook(self):
        """Test Slack webhook test."""
        with patch(
            "services.budget_alerts.send_slack_alert", new_callable=AsyncMock
        ) as mock_send:
            mock_send.return_value = True

            result = await send_test_webhook("slack", "https://hooks.slack.com/test")

            assert result is True
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_discord_webhook(self):
        """Test Discord webhook test."""
        with patch(
            "services.budget_alerts.send_discord_alert", new_callable=AsyncMock
        ) as mock_send:
            mock_send.return_value = True

            result = await send_test_webhook(
                "discord", "https://discord.com/api/webhooks/test"
            )

            assert result is True
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_webhook_type(self):
        """Test unknown webhook type returns False."""
        result = await send_test_webhook("unknown", "https://example.com/webhook")
        assert result is False

    @pytest.mark.asyncio
    async def test_case_insensitive_webhook_type(self):
        """Test webhook type is case insensitive."""
        with patch(
            "services.budget_alerts.send_slack_alert", new_callable=AsyncMock
        ) as mock_send:
            mock_send.return_value = True

            result = await send_test_webhook("SLACK", "https://hooks.slack.com/test")

            assert result is True
            mock_send.assert_called_once()


class TestGetCurrentSpend:
    """Tests for _get_current_spend function."""

    @pytest.mark.asyncio
    async def test_database_not_configured(self):
        """Test returns 0 when database not configured."""
        with patch("services.budget_alerts.db_service") as mock_db:
            mock_db.is_configured = False

            result = await _get_current_spend()

            assert result == 0.0

    @pytest.mark.asyncio
    async def test_calculates_spend_from_tokens(self):
        """Test correct calculation of spend from token usage."""
        with patch("services.budget_alerts.db_service") as mock_db:
            mock_db.is_configured = True

            # Mock the query result
            mock_result = MagicMock()
            mock_result.input = 1_000_000  # 1M input tokens
            mock_result.output = 100_000  # 100K output tokens

            mock_session_obj = AsyncMock()
            mock_execute_result = MagicMock()
            mock_execute_result.one.return_value = mock_result
            mock_session_obj.execute = AsyncMock(return_value=mock_execute_result)

            mock_context_manager = AsyncMock()
            mock_context_manager.__aenter__.return_value = mock_session_obj
            mock_context_manager.__aexit__.return_value = None

            mock_db.session.return_value = mock_context_manager

            result = await _get_current_spend()

            # Expected: (1M / 1M * $3) + (100K / 1M * $15) = $3 + $1.5 = $4.5
            expected = (1_000_000 / 1_000_000 * INPUT_COST_PER_MTOK) + (
                100_000 / 1_000_000 * OUTPUT_COST_PER_MTOK
            )
            assert result == expected

    @pytest.mark.asyncio
    async def test_handles_exception(self):
        """Test returns 0 on database error."""
        with patch("services.budget_alerts.db_service") as mock_db:
            mock_db.is_configured = True

            mock_context_manager = AsyncMock()
            mock_context_manager.__aenter__.side_effect = Exception("DB error")

            mock_db.session.return_value = mock_context_manager

            result = await _get_current_spend()

            assert result == 0.0


class TestConstants:
    """Tests for module constants."""

    def test_cost_constants(self):
        """Test that cost constants are set correctly for Sonnet."""
        assert INPUT_COST_PER_MTOK == 3.0
        assert OUTPUT_COST_PER_MTOK == 15.0

    def test_cooldown_constant(self):
        """Test alert cooldown is set."""
        assert ALERT_COOLDOWN_HOURS == 1
