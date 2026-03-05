"""
Referral Service — Viral growth loop for BenchGoblins.

Users get a unique referral code. When a new user signs up with it,
both the referrer and referred user get 7 days of free Pro access.
"""

import logging
import secrets
import string
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Referral, User
from services.database import db_service

logger = logging.getLogger(__name__)

REWARD_DAYS = 7  # Days of free Pro for both parties
MAX_REFERRALS_PER_USER = 50  # Cap to prevent abuse


def generate_referral_code() -> str:
    """Generate a unique 8-char alphanumeric referral code."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


async def get_or_create_referral_code(user_id: int) -> str:
    """Get user's referral code, creating one if needed."""
    async with db_service.session() as session:
        result = await session.execute(select(User.referral_code).where(User.id == user_id))
        code = result.scalar_one_or_none()

        if code:
            return code

        # Generate unique code
        for _ in range(10):
            code = generate_referral_code()
            existing = await session.execute(select(User.id).where(User.referral_code == code))
            if not existing.scalar_one_or_none():
                break

        await session.execute(update(User).where(User.id == user_id).values(referral_code=code))
        await session.commit()
        return code


async def get_referrer_by_code(code: str, session: AsyncSession) -> User | None:
    """Look up the user who owns a referral code."""
    result = await session.execute(select(User).where(User.referral_code == code.upper()))
    return result.scalar_one_or_none()


async def apply_referral(
    referred_user_id: int,
    referral_code: str,
) -> dict:
    """Apply a referral code for a newly signed-up user.

    Returns status dict with success/error info.
    """
    async with db_service.session() as session:
        # Find referrer
        referrer = await get_referrer_by_code(referral_code, session)
        if not referrer:
            return {"success": False, "error": "Invalid referral code"}

        if referrer.id == referred_user_id:
            return {"success": False, "error": "Cannot refer yourself"}

        # Check for existing referral
        existing = await session.execute(
            select(Referral).where(
                Referral.referrer_user_id == referrer.id,
                Referral.referred_user_id == referred_user_id,
            )
        )
        if existing.scalar_one_or_none():
            return {"success": False, "error": "Referral already applied"}

        # Check referral cap
        count_result = await session.execute(
            select(Referral).where(
                Referral.referrer_user_id == referrer.id,
                Referral.status == "completed",
            )
        )
        completed = count_result.scalars().all()
        if len(completed) >= MAX_REFERRALS_PER_USER:
            return {"success": False, "error": "Referrer has reached maximum referrals"}

        # Create referral record
        now = datetime.now(UTC)
        pro_expires = now + timedelta(days=REWARD_DAYS)

        referral = Referral(
            referrer_user_id=referrer.id,
            referred_user_id=referred_user_id,
            status="completed",
            referrer_reward_applied=True,
            referred_reward_applied=True,
            completed_at=now,
        )
        session.add(referral)

        # Grant Pro to referred user
        await session.execute(
            update(User)
            .where(User.id == referred_user_id)
            .values(
                referred_by_user_id=referrer.id,
                referral_pro_expires_at=pro_expires,
            )
        )

        # Grant/extend Pro for referrer
        referrer_expires = referrer.referral_pro_expires_at
        if referrer_expires and referrer_expires > now:
            new_expires = referrer_expires + timedelta(days=REWARD_DAYS)
        else:
            new_expires = pro_expires

        await session.execute(
            update(User).where(User.id == referrer.id).values(referral_pro_expires_at=new_expires)
        )

        await session.commit()

        logger.info(
            "Referral completed: user %d referred by user %d (code: %s)",
            referred_user_id,
            referrer.id,
            referral_code,
        )

        return {
            "success": True,
            "referrer_name": referrer.name,
            "pro_days": REWARD_DAYS,
        }


async def get_referral_stats(user_id: int) -> dict:
    """Get referral stats for a user."""
    async with db_service.session() as session:
        result = await session.execute(
            select(User.referral_code, User.referral_pro_expires_at).where(User.id == user_id)
        )
        row = result.one_or_none()
        if not row:
            return {"referral_code": None, "total_referrals": 0, "pro_days_remaining": 0}

        code, pro_expires = row

        # Count completed referrals
        referrals_result = await session.execute(
            select(Referral).where(
                Referral.referrer_user_id == user_id,
                Referral.status == "completed",
            )
        )
        referrals = referrals_result.scalars().all()

        pro_days = 0
        if pro_expires:
            remaining = pro_expires - datetime.now(UTC)
            pro_days = max(0, remaining.days)

        return {
            "referral_code": code,
            "total_referrals": len(referrals),
            "pro_days_remaining": pro_days,
            "max_referrals": MAX_REFERRALS_PER_USER,
        }
