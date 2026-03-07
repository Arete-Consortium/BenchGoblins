"""
Email delivery service for BenchGoblins.

Supports SendGrid for production email delivery with graceful fallback
to logging when the API key is not configured (dev mode).
"""

import logging
import os

logger = logging.getLogger(__name__)

# Optional SendGrid import — graceful fallback if not installed
try:
    from sendgrid import SendGridAPIClient

    HAS_SENDGRID = True
except ImportError:
    HAS_SENDGRID = False

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
FROM_EMAIL = os.environ.get("BENCHGOBLINS_FROM_EMAIL", "noreply@benchgoblins.com")
FROM_NAME = os.environ.get("BENCHGOBLINS_FROM_NAME", "BenchGoblins")


def _build_recap_html(player_name: str, recap_html: str) -> str:
    """Wrap recap content in a branded HTML email template."""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Your Weekly Recap</title>
</head>
<body style="margin:0;padding:0;background-color:#0f0f0f;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#0f0f0f;">
<tr><td align="center" style="padding:20px 0;">
<table width="600" cellpadding="0" cellspacing="0" style="background-color:#1a1a2e;border-radius:8px;overflow:hidden;">
<tr><td style="background-color:#16213e;padding:24px;text-align:center;">
<h1 style="color:#00ff88;margin:0;font-size:24px;">BenchGoblins</h1>
<p style="color:#a0a0a0;margin:8px 0 0;">Weekly Recap</p>
</td></tr>
<tr><td style="padding:24px;color:#e0e0e0;font-size:14px;line-height:1.6;">
<p style="color:#ffffff;font-size:16px;">Hey {player_name},</p>
{recap_html}
</td></tr>
<tr><td style="background-color:#16213e;padding:16px;text-align:center;">
<p style="color:#666;font-size:12px;margin:0;">
You received this because you use BenchGoblins.
<br>Manage preferences at <a href="https://benchgoblins.com/settings" style="color:#00ff88;">benchgoblins.com/settings</a>
</p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


class EmailService:
    """Email delivery via SendGrid with dev-mode logging fallback."""

    def __init__(self) -> None:
        self._client: object | None = None
        self._api_key: str = SENDGRID_API_KEY

    @property
    def is_configured(self) -> bool:
        """True when SendGrid is available and API key is set."""
        return HAS_SENDGRID and bool(self._api_key)

    def _get_client(self) -> object:
        """Lazy-init the SendGrid client."""
        if self._client is None and self.is_configured:
            self._client = SendGridAPIClient(api_key=self._api_key)
        return self._client

    async def send_email(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: str | None = None,
    ) -> bool:
        """
        Send an email via SendGrid, or log it in dev mode.

        Returns True if sent/logged successfully, False on error.
        """
        if not self.is_configured:
            logger.info(
                "Email (dev mode) to=%s subject=%s body_length=%d",
                to,
                subject,
                len(html_body),
            )
            return True

        try:
            # Lazy import to handle cases where sendgrid is optional
            from sendgrid.helpers.mail import Content as SGContent
            from sendgrid.helpers.mail import Email as SGEmail
            from sendgrid.helpers.mail import Mail as SGMail
            from sendgrid.helpers.mail import To as SGTo

            from_email = SGEmail(FROM_EMAIL, FROM_NAME)
            to_email = SGTo(to)
            html_content = SGContent("text/html", html_body)

            mail = SGMail(from_email=from_email, to_emails=to_email, subject=subject)
            mail.add_content(html_content)
            if text_body:
                mail.add_content(SGContent("text/plain", text_body))

            client = self._get_client()
            response = client.send(mail)
            status = response.status_code

            if status in (200, 201, 202):
                logger.info("Email sent to=%s subject=%s status=%d", to, subject, status)
                return True

            logger.warning("Email send unexpected status=%d to=%s", status, to)
            return False

        except Exception:
            logger.exception("Failed to send email to=%s", to)
            return False

    async def send_recap_email(
        self,
        to: str,
        player_name: str,
        recap_html: str,
    ) -> bool:
        """
        Send a weekly recap email wrapped in the branded template.

        Args:
            to: Recipient email address
            player_name: User's display name for greeting
            recap_html: The recap narrative HTML content
        """
        subject = "Your BenchGoblins Weekly Recap"
        html_body = _build_recap_html(player_name, recap_html)
        return await self.send_email(to=to, subject=subject, html_body=html_body)


# Module singleton
email_service = EmailService()
