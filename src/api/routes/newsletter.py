"""
Newsletter API Routes.

Handles email list subscriptions for marketing and pre-launch campaigns.
Self-hosted in Postgres — no external email service required.
"""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select

from models.database import NewsletterSubscriber
from routes.auth import require_admin_key
from services.database import db_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/newsletter", tags=["Newsletter"])

# Simple email regex — loose enough to accept valid emails, strict enough to reject garbage
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

VALID_SPORTS = {"nba", "nfl", "mlb", "nhl", "soccer"}


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class SubscribeRequest(BaseModel):
    """Request to subscribe to the newsletter."""

    email: str = Field(..., min_length=5, max_length=255, description="Email address")
    name: str | None = Field(None, max_length=255, description="Subscriber name")
    sport: str | None = Field(None, max_length=50, description="Favorite sport")
    referrer: str | None = Field(None, max_length=100, description="Referral source")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email address")
        return v

    @field_validator("sport")
    @classmethod
    def validate_sport(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip().lower()
            if v and v not in VALID_SPORTS:
                raise ValueError(f"Sport must be one of: {', '.join(sorted(VALID_SPORTS))}")
        return v or None


class UnsubscribeRequest(BaseModel):
    """Request to unsubscribe from the newsletter."""

    email: str = Field(..., min_length=5, max_length=255, description="Email address")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return v.strip().lower()


class SubscribeResponse(BaseModel):
    """Response after subscribe/unsubscribe."""

    success: bool
    message: str


class CountResponse(BaseModel):
    """Admin-only response with subscriber count."""

    active: int
    total: int


# ---------------------------------------------------------------------------
# Simple IP-based rate limiting for newsletter (no session required)
# ---------------------------------------------------------------------------

_subscribe_timestamps: dict[str, list[float]] = {}
_SUBSCRIBE_LIMIT = 5  # max subscriptions per IP per window
_SUBSCRIBE_WINDOW = 3600  # 1 hour


def _check_subscribe_rate(ip: str) -> bool:
    """Return True if the IP is within rate limits."""
    import time

    now = time.time()
    timestamps = _subscribe_timestamps.get(ip, [])
    # Prune old entries
    timestamps = [t for t in timestamps if now - t < _SUBSCRIBE_WINDOW]
    if len(timestamps) >= _SUBSCRIBE_LIMIT:
        return False
    timestamps.append(now)
    _subscribe_timestamps[ip] = timestamps
    return True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(request: Request, body: SubscribeRequest) -> SubscribeResponse:
    """Subscribe an email to the newsletter.

    Returns 200 for both new and duplicate subscriptions (doesn't leak
    whether an email is already subscribed).
    """
    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")

    # Rate limit by IP
    client_ip = request.client.host if request.client else "unknown"
    if not _check_subscribe_rate(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Try again later.")

    async with db_service.session() as session:
        # Check if already subscribed
        result = await session.execute(
            select(NewsletterSubscriber).where(NewsletterSubscriber.email == body.email)
        )
        existing = result.scalar_one_or_none()

        if existing:
            if existing.unsubscribed_at is not None:
                # Re-subscribe
                existing.unsubscribed_at = None
                existing.name = body.name or existing.name
                existing.sport_interest = body.sport or existing.sport_interest
                existing.ip_address = client_ip if client_ip != "unknown" else existing.ip_address
                logger.info("Re-subscribed email to newsletter")
            else:
                logger.debug("Duplicate newsletter subscription attempt")
            return SubscribeResponse(success=True, message="You're subscribed!")

        # New subscriber
        subscriber = NewsletterSubscriber(
            email=body.email,
            name=body.name,
            sport_interest=body.sport,
            referrer=body.referrer,
            ip_address=client_ip if client_ip != "unknown" else None,
        )
        session.add(subscriber)
        logger.info("New newsletter subscriber added")

    return SubscribeResponse(success=True, message="You're subscribed!")


@router.post("/unsubscribe", response_model=SubscribeResponse)
async def unsubscribe(body: UnsubscribeRequest) -> SubscribeResponse:
    """Unsubscribe an email (soft delete — sets unsubscribed_at)."""
    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")

    async with db_service.session() as session:
        result = await session.execute(
            select(NewsletterSubscriber).where(NewsletterSubscriber.email == body.email)
        )
        existing = result.scalar_one_or_none()

        if existing and existing.unsubscribed_at is None:
            existing.unsubscribed_at = func.now()
            logger.info("Newsletter subscriber unsubscribed")

    # Always return success (don't leak whether email exists)
    return SubscribeResponse(success=True, message="You've been unsubscribed.")


@router.get("/count", response_model=CountResponse)
async def count(_: None = Depends(require_admin_key)) -> CountResponse:
    """Get subscriber counts (admin only)."""
    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")

    async with db_service.session() as session:
        # Active subscribers
        active_result = await session.execute(
            select(func.count(NewsletterSubscriber.id)).where(
                NewsletterSubscriber.unsubscribed_at.is_(None)
            )
        )
        active = active_result.scalar() or 0

        # Total (including unsubscribed)
        total_result = await session.execute(select(func.count(NewsletterSubscriber.id)))
        total = total_result.scalar() or 0

    return CountResponse(active=active, total=total)
