"""
Tests for the email delivery service.

Covers: EmailService with SendGrid mock, dev mode logging fallback,
HTML template rendering, send_recap_email convenience method.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from services.email import EmailService, _build_recap_html


# =============================================================================
# HTML Template
# =============================================================================


class TestBuildRecapHtml:
    """Tests for the branded HTML email template builder."""

    def test_contains_player_name(self):
        html = _build_recap_html("Alice", "<p>Great week!</p>")
        assert "Hey Alice," in html

    def test_contains_recap_content(self):
        html = _build_recap_html("Bob", "<p>You went 5-2 this week.</p>")
        assert "You went 5-2 this week." in html

    def test_contains_branding(self):
        html = _build_recap_html("Test", "<p>Content</p>")
        assert "BenchGoblins" in html

    def test_contains_settings_link(self):
        html = _build_recap_html("Test", "<p>Content</p>")
        assert "benchgoblins.com/settings" in html

    def test_is_valid_html(self):
        html = _build_recap_html("Test", "<p>Content</p>")
        assert html.startswith("<!DOCTYPE html>")
        assert html.endswith("</html>")

    def test_html_escaping_not_applied(self):
        """Recap HTML should be inserted as-is (already sanitized by Claude)."""
        html = _build_recap_html("Test", "<strong>Bold</strong>")
        assert "<strong>Bold</strong>" in html


# =============================================================================
# Dev Mode (no SendGrid API key)
# =============================================================================


class TestEmailServiceDevMode:
    """Tests for dev mode where emails are logged instead of sent."""

    @pytest.mark.asyncio
    async def test_dev_mode_logs_email(self, caplog):
        """When no API key is set, email is logged instead of sent."""
        service = EmailService()
        service._api_key = ""

        with caplog.at_level(logging.INFO, logger="services.email"):
            result = await service.send_email(
                to="user@example.com",
                subject="Test Subject",
                html_body="<p>Hello</p>",
            )

        assert result is True
        assert "dev mode" in caplog.text.lower()
        assert "user@example.com" in caplog.text

    @pytest.mark.asyncio
    async def test_dev_mode_returns_true(self):
        service = EmailService()
        service._api_key = ""
        result = await service.send_email(
            to="a@b.com", subject="S", html_body="<p>H</p>"
        )
        assert result is True

    def test_is_configured_false_without_key(self):
        service = EmailService()
        service._api_key = ""
        assert service.is_configured is False

    @pytest.mark.asyncio
    async def test_dev_mode_send_recap_email(self, caplog):
        service = EmailService()
        service._api_key = ""

        with caplog.at_level(logging.INFO, logger="services.email"):
            result = await service.send_recap_email(
                to="player@example.com",
                player_name="TestPlayer",
                recap_html="<p>Your recap</p>",
            )

        assert result is True
        assert "player@example.com" in caplog.text


# =============================================================================
# SendGrid Integration (mocked)
# =============================================================================


def _sendgrid_mocks():
    """Create mock sendgrid.helpers.mail module with Email, Mail, Content, To."""
    import types

    mock_mod = types.ModuleType("sendgrid.helpers.mail")
    mock_mod.Email = MagicMock
    mock_mod.To = MagicMock
    mock_mod.Content = MagicMock
    mock_mod.Mail = MagicMock
    return mock_mod


class TestEmailServiceSendGrid:
    """Tests for SendGrid email delivery with mocked client."""

    def _make_configured_service(self):
        """Create an EmailService with a fake API key and mocked HAS_SENDGRID."""
        service = EmailService()
        service._api_key = "SG.fake_key_for_testing"
        return service

    @pytest.mark.asyncio
    @patch("services.email.HAS_SENDGRID", True)
    @patch.dict("sys.modules", {"sendgrid.helpers.mail": _sendgrid_mocks()})
    async def test_send_email_success(self):
        service = self._make_configured_service()

        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_client = MagicMock()
        mock_client.send.return_value = mock_response
        service._client = mock_client

        result = await service.send_email(
            to="user@example.com",
            subject="Weekly Recap",
            html_body="<p>Your recap</p>",
            text_body="Your recap",
        )

        assert result is True
        mock_client.send.assert_called_once()

    @pytest.mark.asyncio
    @patch("services.email.HAS_SENDGRID", True)
    @patch.dict("sys.modules", {"sendgrid.helpers.mail": _sendgrid_mocks()})
    async def test_send_email_failure_status(self):
        service = self._make_configured_service()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client = MagicMock()
        mock_client.send.return_value = mock_response
        service._client = mock_client

        result = await service.send_email(
            to="user@example.com",
            subject="Test",
            html_body="<p>Test</p>",
        )

        assert result is False

    @pytest.mark.asyncio
    @patch("services.email.HAS_SENDGRID", True)
    @patch.dict("sys.modules", {"sendgrid.helpers.mail": _sendgrid_mocks()})
    async def test_send_email_exception(self):
        service = self._make_configured_service()

        mock_client = MagicMock()
        mock_client.send.side_effect = Exception("API error")
        service._client = mock_client

        result = await service.send_email(
            to="user@example.com",
            subject="Test",
            html_body="<p>Test</p>",
        )

        assert result is False

    @pytest.mark.asyncio
    @patch("services.email.HAS_SENDGRID", True)
    @patch.dict("sys.modules", {"sendgrid.helpers.mail": _sendgrid_mocks()})
    async def test_send_recap_email_uses_template(self):
        service = self._make_configured_service()

        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_client = MagicMock()
        mock_client.send.return_value = mock_response
        service._client = mock_client

        result = await service.send_recap_email(
            to="user@example.com",
            player_name="Alice",
            recap_html="<p>Great week!</p>",
        )

        assert result is True
        # Verify send was called with the branded template
        assert mock_client.send.called

    def test_is_configured_true_with_key(self):
        with patch("services.email.HAS_SENDGRID", True):
            service = self._make_configured_service()
            assert service.is_configured is True

    @pytest.mark.asyncio
    @patch("services.email.HAS_SENDGRID", True)
    @patch.dict("sys.modules", {"sendgrid.helpers.mail": _sendgrid_mocks()})
    async def test_send_email_status_200(self):
        service = self._make_configured_service()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.send.return_value = mock_response
        service._client = mock_client

        result = await service.send_email(
            to="user@example.com",
            subject="Test",
            html_body="<p>Test</p>",
        )
        assert result is True

    @pytest.mark.asyncio
    @patch("services.email.HAS_SENDGRID", True)
    @patch.dict("sys.modules", {"sendgrid.helpers.mail": _sendgrid_mocks()})
    async def test_send_email_status_201(self):
        service = self._make_configured_service()

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_client = MagicMock()
        mock_client.send.return_value = mock_response
        service._client = mock_client

        result = await service.send_email(
            to="user@example.com",
            subject="Test",
            html_body="<p>Test</p>",
        )
        assert result is True


# =============================================================================
# Module Singleton
# =============================================================================


class TestEmailServiceSingleton:
    """Test module-level singleton."""

    def test_singleton_exists(self):
        from services.email import email_service

        assert isinstance(email_service, EmailService)

    def test_get_client_returns_none_when_not_configured(self):
        service = EmailService()
        service._api_key = ""
        assert service._get_client() is None


# =============================================================================
# HAS_SENDGRID False Path
# =============================================================================


class TestNoSendGrid:
    """Test behavior when sendgrid package is not installed."""

    @pytest.mark.asyncio
    async def test_not_configured_without_sendgrid(self):
        with patch("services.email.HAS_SENDGRID", False):
            service = EmailService()
            service._api_key = "SG.fake"
            assert service.is_configured is False

    @pytest.mark.asyncio
    async def test_falls_back_to_dev_mode(self, caplog):
        with patch("services.email.HAS_SENDGRID", False):
            service = EmailService()
            service._api_key = "SG.fake"
            with caplog.at_level(logging.INFO, logger="services.email"):
                result = await service.send_email(
                    to="a@b.com", subject="S", html_body="<p>H</p>"
                )
            assert result is True
            assert "dev mode" in caplog.text.lower()
