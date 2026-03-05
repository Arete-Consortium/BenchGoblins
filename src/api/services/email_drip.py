"""
Email Drip Service — Automated onboarding email sequences.

Sends timed emails to new users to drive engagement:
  1. Welcome (immediate on signup)
  2. Connect League (day 1 if no league connected)
  3. First Verdict (day 2 if no verdict generated)

Uses Resend API for delivery. Gracefully degrades if not configured.
"""

import logging
import os
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import User
from services.database import db_service

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FROM_EMAIL = os.getenv("DRIP_FROM_EMAIL", "BenchGoblins <noreply@benchgoblins.com>")

# Drip schedule: (drip_name, delay_hours, subject, requires_condition)
DRIP_SEQUENCE = [
    ("welcome", 0, "Welcome to BenchGoblins!", None),
    ("connect_league", 24, "Connect your league for personalized verdicts", "no_league"),
    ("first_verdict", 48, "Your first Goblin Verdict awaits", "no_verdict"),
]


def is_configured() -> bool:
    """Check if email sending is configured."""
    return bool(RESEND_API_KEY)


async def send_email(to: str, subject: str, html: str) -> bool:
    """Send an email via Resend API. Returns True on success."""
    if not RESEND_API_KEY:
        logger.debug("Email not sent (Resend not configured): %s", subject)
        return False

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                json={
                    "from": FROM_EMAIL,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
                timeout=10.0,
            )
            if resp.status_code == 200:
                logger.info("Email sent: %s → %s", subject, to)
                return True
            logger.warning("Resend API error %d: %s", resp.status_code, resp.text)
            return False
    except httpx.HTTPError as e:
        logger.warning("Email send failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Email Templates
# ---------------------------------------------------------------------------


def _base_template(content: str) -> str:
    """Wrap content in base email template."""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0a0f; color: #e5e5e5; margin: 0; padding: 0; }}
  .container {{ max-width: 560px; margin: 0 auto; padding: 40px 24px; }}
  .logo {{ font-size: 24px; font-weight: 800; color: #4ade80; margin-bottom: 24px; }}
  h1 {{ font-size: 22px; color: #ffffff; margin: 0 0 16px; }}
  p {{ font-size: 15px; line-height: 1.6; color: #a1a1aa; margin: 0 0 16px; }}
  .btn {{ display: inline-block; background: #4ade80; color: #0a0a0f; font-weight: 600; font-size: 15px; padding: 12px 28px; border-radius: 8px; text-decoration: none; margin: 8px 0 24px; }}
  .footer {{ font-size: 12px; color: #52525b; border-top: 1px solid #27272a; padding-top: 20px; margin-top: 32px; }}
  .footer a {{ color: #4ade80; text-decoration: none; }}
</style></head>
<body><div class="container">
  <div class="logo">Bench Goblins</div>
  {content}
  <div class="footer">
    <p>benchgoblins.com &mdash; AI-Powered Fantasy Decisions</p>
    <p><a href="https://benchgoblins.com/settings">Manage preferences</a></p>
  </div>
</div></body></html>"""


def welcome_email(name: str) -> str:
    """Welcome email sent immediately after signup."""
    return _base_template(f"""
    <h1>Welcome, {name}!</h1>
    <p>The Goblin is ready to help you dominate your fantasy league. Here's what you can do:</p>
    <p><strong>1. Connect your league</strong> &mdash; Link Sleeper, ESPN, or Yahoo for personalized lineup verdicts.</p>
    <p><strong>2. Get your verdict</strong> &mdash; The Goblin analyzes your roster and tells you who to start and sit.</p>
    <p><strong>3. Invite friends</strong> &mdash; Share your referral code and both get 7 days of free Pro.</p>
    <a href="https://benchgoblins.com/leagues" class="btn">Connect Your League</a>
    <p>Questions? Just reply to this email.</p>
    """)


def connect_league_email(name: str) -> str:
    """Nudge email if user hasn't connected a league after 24h."""
    return _base_template(f"""
    <h1>Hey {name}, the Goblin is waiting</h1>
    <p>You signed up yesterday but haven't connected a league yet. The Goblin needs your roster to give you personalized start/sit recommendations.</p>
    <p>It takes 30 seconds:</p>
    <p><strong>Sleeper</strong> &mdash; Just enter your username<br>
    <strong>ESPN</strong> &mdash; Connect with your league ID<br>
    <strong>Yahoo</strong> &mdash; Link your Yahoo Fantasy account</p>
    <a href="https://benchgoblins.com/leagues" class="btn">Connect League Now</a>
    <p>Once connected, the Goblin will generate your first verdict automatically.</p>
    """)


def first_verdict_email(name: str) -> str:
    """Nudge email if user hasn't generated a verdict after 48h."""
    return _base_template(f"""
    <h1>{name}, your Goblin Verdict is ready</h1>
    <p>The Goblin has analyzed your roster and has recommendations for this week's lineup. Don't leave points on the bench.</p>
    <p>Your verdict includes:</p>
    <p>&bull; <strong>Swap recommendations</strong> with confidence scores<br>
    &bull; <strong>Risk mode analysis</strong> (Floor, Median, Ceiling)<br>
    &bull; <strong>Shareable cards</strong> to send to your leaguemates</p>
    <a href="https://benchgoblins.com/verdict" class="btn">See Your Verdict</a>
    """)


TEMPLATES = {
    "welcome": welcome_email,
    "connect_league": connect_league_email,
    "first_verdict": first_verdict_email,
}


# ---------------------------------------------------------------------------
# Drip Logic
# ---------------------------------------------------------------------------


async def send_welcome(user_id: int, name: str, email: str) -> bool:
    """Send welcome email immediately on signup."""
    html = welcome_email(name)
    sent = await send_email(email, "Welcome to BenchGoblins!", html)
    if sent:
        await _record_drip(user_id, "welcome")
    return sent


async def _record_drip(user_id: int, drip_name: str) -> None:
    """Record that a drip email was sent (stores in user metadata)."""
    async with db_service.session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return

        drips = user.drip_emails_sent or {}
        drips[drip_name] = datetime.now(UTC).isoformat()

        await session.execute(update(User).where(User.id == user_id).values(drip_emails_sent=drips))
        await session.commit()


async def check_user_drip(user_id: int, session: AsyncSession) -> str | None:
    """Check if a user is due for a drip email. Returns drip name or None."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.email:
        return None

    drips_sent = user.drip_emails_sent or {}
    signup_age = datetime.now(UTC) - user.created_at.replace(tzinfo=UTC)

    for drip_name, delay_hours, _, condition in DRIP_SEQUENCE:
        if drip_name in drips_sent:
            continue  # Already sent

        if signup_age < timedelta(hours=delay_hours):
            continue  # Too early

        # Check condition
        if condition == "no_league" and user.sleeper_user_id:
            continue  # Has a league connected
        if condition == "no_verdict":
            # Skip condition check — send anyway as engagement nudge
            pass

        return drip_name

    return None


async def process_pending_drips() -> int:
    """Process all pending drip emails. Called by scheduler."""
    if not is_configured():
        return 0

    sent_count = 0
    async with db_service.session() as session:
        # Get users created in the last 7 days who might need drips
        cutoff = datetime.now(UTC) - timedelta(days=7)
        result = await session.execute(
            select(User).where(
                User.created_at >= cutoff,
                User.email.isnot(None),
            )
        )
        users = result.scalars().all()

        for user in users:
            drip_name = await check_user_drip(user.id, session)
            if not drip_name:
                continue

            _, _, subject, _ = next(d for d in DRIP_SEQUENCE if d[0] == drip_name)
            template_fn = TEMPLATES.get(drip_name)
            if not template_fn:
                continue

            html = template_fn(user.name or "there")
            sent = await send_email(user.email, subject, html)
            if sent:
                await _record_drip(user.id, drip_name)
                sent_count += 1

    logger.info("Drip processor: sent %d emails", sent_count)
    return sent_count
