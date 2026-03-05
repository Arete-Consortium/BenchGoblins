"""
Referral API Routes — Invite leaguemates, earn free Pro access.

Both the referrer and referred user get 7 days of free Pro access.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routes.auth import get_current_user
from services.referral import apply_referral, get_or_create_referral_code, get_referral_stats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/referral", tags=["Referral"])


# -------------------------------------------------------------------------
# Response Models
# -------------------------------------------------------------------------


class ReferralCodeResponse(BaseModel):
    """User's referral code and share URL."""

    referral_code: str
    share_url: str


class ApplyReferralRequest(BaseModel):
    """Request to apply a referral code."""

    code: str = Field(..., min_length=6, max_length=12)


class ApplyReferralResponse(BaseModel):
    """Result of applying a referral code."""

    success: bool
    message: str
    pro_days: int = 0


class ReferralStatsResponse(BaseModel):
    """Referral stats for the current user."""

    referral_code: str | None
    total_referrals: int
    pro_days_remaining: int
    max_referrals: int


# -------------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------------


@router.get("/code", response_model=ReferralCodeResponse)
async def get_my_referral_code(
    current_user: dict = Depends(get_current_user),
):
    """Get or generate the current user's referral code."""
    code = await get_or_create_referral_code(current_user["user_id"])
    return ReferralCodeResponse(
        referral_code=code,
        share_url=f"https://benchgoblins.com/auth/login?ref={code}",
    )


@router.post("/apply", response_model=ApplyReferralResponse)
async def apply_referral_code(
    request: ApplyReferralRequest,
    current_user: dict = Depends(get_current_user),
):
    """Apply a referral code to get free Pro access."""
    result = await apply_referral(
        referred_user_id=current_user["user_id"],
        referral_code=request.code,
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    return ApplyReferralResponse(
        success=True,
        message=f"Referred by {result['referrer_name']}! You both get {result['pro_days']} days of Pro.",
        pro_days=result["pro_days"],
    )


@router.get("/stats", response_model=ReferralStatsResponse)
async def get_my_referral_stats(
    current_user: dict = Depends(get_current_user),
):
    """Get referral stats for the current user."""
    stats = await get_referral_stats(current_user["user_id"])
    return ReferralStatsResponse(**stats)
