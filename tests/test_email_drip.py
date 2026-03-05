"""
Tests for the email drip service.

Covers: configuration check, email sending, templates, welcome flow,
drip recording, drip condition checking, and batch processing.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.email_drip import (
    DRIP_SEQUENCE,
    TEMPLATES,
    _base_template,
    _record_drip,
    check_user_drip,
    connect_league_email,
    first_verdict_email,
    is_configured,
    process_pending_drips,
    send_email,
    send_welcome,
    welcome_email,
)

_DB = "services.email_drip.db_service"


def _mock_db_session():
    mock_session = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_session


def _make_user(
    id_=1,
    name="Test",
    email="test@example.com",
    created_at=None,
    sleeper_user_id=None,
    drip_emails_sent=None,
):
    user = MagicMock()
    user.id = id_
    user.name = name
    user.email = email
    user.created_at = created_at or datetime.now(UTC)
    user.sleeper_user_id = sleeper_user_id
    user.drip_emails_sent = drip_emails_sent
    return user


# =============================================================================
# CONFIGURATION
# =============================================================================


class TestConfiguration:
    def test_not_configured_without_key(self):
        with patch("services.email_drip.RESEND_API_KEY", None):
            assert is_configured() is False

    def test_configured_with_key(self):
        with patch("services.email_drip.RESEND_API_KEY", "re_test_123"):
            assert is_configured() is True


# =============================================================================
# TEMPLATES
# =============================================================================


class TestTemplates:
    def test_base_template_has_branding(self):
        html = _base_template("<p>Test</p>")
        assert "Bench Goblins" in html
        assert "benchgoblins.com" in html
        assert "<p>Test</p>" in html

    def test_welcome_email_has_name(self):
        html = welcome_email("Alice")
        assert "Alice" in html
        assert "Connect Your League" in html

    def test_connect_league_email(self):
        html = connect_league_email("Bob")
        assert "Bob" in html
        assert "Sleeper" in html
        assert "ESPN" in html

    def test_first_verdict_email(self):
        html = first_verdict_email("Charlie")
        assert "Charlie" in html
        assert "verdict" in html.lower()

    def test_all_drip_names_have_templates(self):
        for drip_name, _, _, _ in DRIP_SEQUENCE:
            assert drip_name in TEMPLATES

    def test_drip_sequence_order(self):
        delays = [delay for _, delay, _, _ in DRIP_SEQUENCE]
        assert delays == sorted(delays)


# =============================================================================
# SEND EMAIL
# =============================================================================


class TestSendEmail:
    @pytest.mark.asyncio
    async def test_returns_false_when_not_configured(self):
        with patch("services.email_drip.RESEND_API_KEY", None):
            result = await send_email("test@example.com", "Subject", "<p>Hi</p>")
            assert result is False

    @pytest.mark.asyncio
    async def test_sends_via_resend(self):
        with patch("services.email_drip.RESEND_API_KEY", "re_test_123"):
            mock_response = MagicMock()
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)

            with patch(
                "services.email_drip.httpx.AsyncClient", return_value=mock_client
            ):
                result = await send_email("test@example.com", "Welcome!", "<p>Hi</p>")
                assert result is True
                mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_on_api_error(self):
        with patch("services.email_drip.RESEND_API_KEY", "re_test_123"):
            mock_response = MagicMock()
            mock_response.status_code = 422
            mock_response.text = "Invalid email"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)

            with patch(
                "services.email_drip.httpx.AsyncClient", return_value=mock_client
            ):
                result = await send_email("bad@", "Welcome!", "<p>Hi</p>")
                assert result is False


# =============================================================================
# SEND WELCOME
# =============================================================================


class TestSendWelcome:
    @pytest.mark.asyncio
    async def test_sends_and_records(self):
        with (
            patch(
                "services.email_drip.send_email", new_callable=AsyncMock
            ) as mock_send,
            patch(
                "services.email_drip._record_drip", new_callable=AsyncMock
            ) as mock_record,
        ):
            mock_send.return_value = True
            result = await send_welcome(1, "Test", "test@example.com")
            assert result is True
            mock_send.assert_called_once()
            mock_record.assert_called_once_with(1, "welcome")

    @pytest.mark.asyncio
    async def test_does_not_record_on_failure(self):
        with (
            patch(
                "services.email_drip.send_email", new_callable=AsyncMock
            ) as mock_send,
            patch(
                "services.email_drip._record_drip", new_callable=AsyncMock
            ) as mock_record,
        ):
            mock_send.return_value = False
            result = await send_welcome(1, "Test", "test@example.com")
            assert result is False
            mock_record.assert_not_called()


# =============================================================================
# RECORD DRIP
# =============================================================================


class TestRecordDrip:
    @pytest.mark.asyncio
    async def test_records_drip_timestamp(self):
        with patch(_DB) as mock_db:
            mock_ctx, mock_session = _mock_db_session()
            mock_db.session.return_value = mock_ctx

            user = _make_user(drip_emails_sent={})
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = user
            mock_session.execute = AsyncMock(return_value=mock_result)

            await _record_drip(1, "welcome")
            # Should have been called (execute for select + execute for update + commit)
            assert mock_session.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_handles_missing_user(self):
        with patch(_DB) as mock_db:
            mock_ctx, mock_session = _mock_db_session()
            mock_db.session.return_value = mock_ctx

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)

            # Should not raise
            await _record_drip(999, "welcome")


# =============================================================================
# CHECK USER DRIP
# =============================================================================


class TestCheckUserDrip:
    @pytest.mark.asyncio
    async def test_returns_welcome_for_new_user(self):
        session = AsyncMock()
        user = _make_user(drip_emails_sent={})
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=mock_result)

        drip = await check_user_drip(1, session)
        assert drip == "welcome"

    @pytest.mark.asyncio
    async def test_returns_connect_league_after_24h(self):
        session = AsyncMock()
        user = _make_user(
            created_at=datetime.now(UTC) - timedelta(hours=25),
            drip_emails_sent={"welcome": "2026-03-04T00:00:00"},
            sleeper_user_id=None,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=mock_result)

        drip = await check_user_drip(1, session)
        assert drip == "connect_league"

    @pytest.mark.asyncio
    async def test_skips_connect_league_if_has_league(self):
        session = AsyncMock()
        user = _make_user(
            created_at=datetime.now(UTC) - timedelta(hours=25),
            drip_emails_sent={"welcome": "2026-03-04T00:00:00"},
            sleeper_user_id="user123",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=mock_result)

        drip = await check_user_drip(1, session)
        # Should skip connect_league and go to first_verdict (if 48h passed)
        assert drip != "connect_league"

    @pytest.mark.asyncio
    async def test_returns_none_when_all_sent(self):
        session = AsyncMock()
        user = _make_user(
            created_at=datetime.now(UTC) - timedelta(days=3),
            drip_emails_sent={
                "welcome": "2026-03-02T00:00:00",
                "connect_league": "2026-03-03T00:00:00",
                "first_verdict": "2026-03-04T00:00:00",
            },
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=mock_result)

        drip = await check_user_drip(1, session)
        assert drip is None

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_user(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        drip = await check_user_drip(999, session)
        assert drip is None

    @pytest.mark.asyncio
    async def test_returns_none_for_too_new_user(self):
        session = AsyncMock()
        user = _make_user(
            created_at=datetime.now(UTC) - timedelta(minutes=5),
            drip_emails_sent={"welcome": "2026-03-05T00:00:00"},
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=mock_result)

        drip = await check_user_drip(1, session)
        # Too early for connect_league (needs 24h)
        assert drip is None


# =============================================================================
# PROCESS PENDING DRIPS
# =============================================================================


class TestProcessPendingDrips:
    @pytest.mark.asyncio
    async def test_returns_zero_when_not_configured(self):
        with patch("services.email_drip.RESEND_API_KEY", None):
            result = await process_pending_drips()
            assert result == 0

    @pytest.mark.asyncio
    async def test_processes_eligible_users(self):
        with (
            patch("services.email_drip.RESEND_API_KEY", "re_test_123"),
            patch(_DB) as mock_db,
            patch(
                "services.email_drip.send_email", new_callable=AsyncMock
            ) as mock_send,
            patch("services.email_drip._record_drip", new_callable=AsyncMock),
            patch(
                "services.email_drip.check_user_drip", new_callable=AsyncMock
            ) as mock_check,
        ):
            mock_ctx, mock_session = _mock_db_session()
            mock_db.session.return_value = mock_ctx

            user = _make_user()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [user]
            mock_session.execute = AsyncMock(return_value=mock_result)

            mock_check.return_value = "welcome"
            mock_send.return_value = True

            result = await process_pending_drips()
            assert result == 1
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_users_with_no_pending_drip(self):
        with (
            patch("services.email_drip.RESEND_API_KEY", "re_test_123"),
            patch(_DB) as mock_db,
            patch(
                "services.email_drip.send_email", new_callable=AsyncMock
            ) as mock_send,
            patch(
                "services.email_drip.check_user_drip", new_callable=AsyncMock
            ) as mock_check,
        ):
            mock_ctx, mock_session = _mock_db_session()
            mock_db.session.return_value = mock_ctx

            user = _make_user()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [user]
            mock_session.execute = AsyncMock(return_value=mock_result)

            mock_check.return_value = None

            result = await process_pending_drips()
            assert result == 0
            mock_send.assert_not_called()
