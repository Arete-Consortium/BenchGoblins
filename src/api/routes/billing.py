"""
Billing, budget, and history routes.
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from models.database import BudgetConfig, User
from models.database import Decision as DecisionModel
from models.schemas import (
    DecisionHistoryItem,
    PaginatedHistory,
    Sport,
)
from routes.auth import get_current_user
from services import stripe_billing
from services.budget_alerts import send_test_webhook
from services.database import db_service

logger = logging.getLogger("benchgoblins")

router = APIRouter()


# ---------------------------------------------------------------------------
# Tier Constants (shared with decisions router)
# ---------------------------------------------------------------------------

FREE_TIER_WEEKLY_LIMIT = 5


# ---------------------------------------------------------------------------
# Budget Models
# ---------------------------------------------------------------------------


class BudgetConfigRequest(BaseModel):
    """Request to set budget configuration."""

    monthly_limit_usd: float = Field(..., ge=0, description="Monthly spending cap in USD")
    alert_threshold_pct: int = Field(
        default=80, ge=0, le=100, description="Alert when spending reaches this percentage"
    )
    alerts_enabled: bool = Field(default=True, description="Enable webhook alerts")
    slack_webhook_url: str | None = Field(default=None, description="Slack webhook URL for alerts")
    discord_webhook_url: str | None = Field(
        default=None, description="Discord webhook URL for alerts"
    )


class BudgetConfigResponse(BaseModel):
    """Budget configuration and current status."""

    monthly_limit_usd: float
    alert_threshold_pct: int
    alerts_enabled: bool
    slack_webhook_url: str | None
    discord_webhook_url: str | None
    current_month_spent_usd: float
    percent_used: float
    budget_exceeded: bool
    alert_triggered: bool
    updated_at: str | None


class BudgetAlertResponse(BaseModel):
    """Active budget alert information."""

    alert_active: bool
    alert_type: str | None  # "threshold" or "exceeded"
    message: str | None
    current_spend_usd: float
    monthly_limit_usd: float
    percent_used: float


class WebhookTestRequest(BaseModel):
    """Request to test a webhook URL."""

    webhook_type: str = Field(..., description="Either 'slack' or 'discord'")
    webhook_url: str = Field(..., description="The webhook URL to test")


# ---------------------------------------------------------------------------
# Billing Models
# ---------------------------------------------------------------------------


class CheckoutRequest(BaseModel):
    """Request to create a Stripe checkout session."""

    price_id: str = Field(
        default=stripe_billing.PRICE_IDS["pro_monthly"],
        description="Stripe Price ID for the subscription",
    )
    success_url: str = Field(
        ..., max_length=500, description="URL to redirect to after successful checkout"
    )
    cancel_url: str = Field(
        ..., max_length=500, description="URL to redirect to if checkout is cancelled"
    )


class CheckoutResponse(BaseModel):
    """Response with checkout session URL."""

    checkout_url: str


class PortalRequest(BaseModel):
    """Request to create a Stripe billing portal session."""

    return_url: str = Field(
        ..., max_length=500, description="URL to return to after portal session"
    )


class PortalResponse(BaseModel):
    """Response with billing portal URL."""

    portal_url: str


class BillingStatusResponse(BaseModel):
    """Current billing status for user."""

    tier: str
    status: str
    queries_today: int
    weekly_limit: int
    queries_remaining: int | None  # None if unlimited
    subscription_id: str | None = None
    current_period_end: str | None = None
    cancel_at_period_end: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Cost per million tokens (Sonnet pricing)
INPUT_COST_PER_MTOK = 3.0
OUTPUT_COST_PER_MTOK = 15.0


async def _get_user_by_id(user_id: int) -> User | None:
    """Get user from database by ID."""
    if not db_service.is_configured:
        return None

    async with db_service.session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


async def _get_current_month_spend(session) -> tuple[float, int, int]:
    """Calculate current month's token spend. Returns (spend_usd, input_tokens, output_tokens)."""
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    usage_q = select(
        func.coalesce(func.sum(DecisionModel.input_tokens), 0).label("input"),
        func.coalesce(func.sum(DecisionModel.output_tokens), 0).label("output"),
    ).where(DecisionModel.created_at >= month_start)
    usage_row = (await session.execute(usage_q)).one()

    input_tokens = int(usage_row.input)
    output_tokens = int(usage_row.output)
    current_spend = (
        input_tokens / 1_000_000 * INPUT_COST_PER_MTOK
        + output_tokens / 1_000_000 * OUTPUT_COST_PER_MTOK
    )
    return current_spend, input_tokens, output_tokens


# ---------------------------------------------------------------------------
# Budget Routes
# ---------------------------------------------------------------------------


@router.get("/budget", response_model=BudgetConfigResponse)
async def get_budget(current_user: dict = Depends(get_current_user)):
    """Get current budget configuration and spending status (requires authentication)."""
    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        async with db_service.session() as session:
            config_q = select(BudgetConfig).order_by(BudgetConfig.id.desc()).limit(1)
            result = await session.execute(config_q)
            config = result.scalar_one_or_none()

            if not config:
                return BudgetConfigResponse(
                    monthly_limit_usd=0,
                    alert_threshold_pct=80,
                    alerts_enabled=True,
                    slack_webhook_url=None,
                    discord_webhook_url=None,
                    current_month_spent_usd=0,
                    percent_used=0,
                    budget_exceeded=False,
                    alert_triggered=False,
                    updated_at=None,
                )

            current_spend, _, _ = await _get_current_month_spend(session)

            limit = float(config.monthly_limit_usd)
            percent_used = (current_spend / limit * 100) if limit > 0 else 0
            budget_exceeded = limit > 0 and current_spend >= limit
            alert_triggered = limit > 0 and percent_used >= config.alert_threshold_pct

            return BudgetConfigResponse(
                monthly_limit_usd=limit,
                alert_threshold_pct=config.alert_threshold_pct,
                alerts_enabled=config.alerts_enabled,
                slack_webhook_url=config.slack_webhook_url,
                discord_webhook_url=config.discord_webhook_url,
                current_month_spent_usd=round(current_spend, 4),
                percent_used=round(percent_used, 2),
                budget_exceeded=budget_exceeded,
                alert_triggered=alert_triggered,
                updated_at=config.updated_at.isoformat() if config.updated_at else None,
            )
    except Exception as e:
        logger.error("Failed to fetch budget: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch budget configuration")


@router.put("/budget", response_model=BudgetConfigResponse)
async def set_budget(request: BudgetConfigRequest, current_user: dict = Depends(get_current_user)):
    """Set monthly spending limit, alert threshold, and webhook URLs (requires authentication)."""
    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        async with db_service.session() as session:
            config_q = select(BudgetConfig).order_by(BudgetConfig.id.desc()).limit(1)
            result = await session.execute(config_q)
            config = result.scalar_one_or_none()

            now = datetime.now(UTC)
            if config:
                config.monthly_limit_usd = request.monthly_limit_usd  # type: ignore[assignment]
                config.alert_threshold_pct = request.alert_threshold_pct
                config.alerts_enabled = request.alerts_enabled
                config.slack_webhook_url = request.slack_webhook_url
                config.discord_webhook_url = request.discord_webhook_url
                config.updated_at = now
            else:
                config = BudgetConfig(
                    monthly_limit_usd=request.monthly_limit_usd,  # type: ignore[arg-type]
                    alert_threshold_pct=request.alert_threshold_pct,
                    alerts_enabled=request.alerts_enabled,
                    slack_webhook_url=request.slack_webhook_url,
                    discord_webhook_url=request.discord_webhook_url,
                    created_at=now,
                    updated_at=now,
                )
                session.add(config)

        # Return updated status
        return await get_budget(current_user)
    except Exception as e:
        logger.error("Failed to set budget: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update budget configuration")


@router.get("/budget/alerts", response_model=BudgetAlertResponse)
async def get_budget_alerts(current_user: dict = Depends(get_current_user)):
    """Get any active budget warnings or alerts (requires authentication)."""
    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        async with db_service.session() as session:
            config_q = select(BudgetConfig).order_by(BudgetConfig.id.desc()).limit(1)
            result = await session.execute(config_q)
            config = result.scalar_one_or_none()

            if not config or float(config.monthly_limit_usd) == 0:
                return BudgetAlertResponse(
                    alert_active=False,
                    alert_type=None,
                    message=None,
                    current_spend_usd=0,
                    monthly_limit_usd=0,
                    percent_used=0,
                )

            current_spend, _, _ = await _get_current_month_spend(session)

            limit = float(config.monthly_limit_usd)
            percent_used = (current_spend / limit * 100) if limit > 0 else 0

            alert_active = False
            alert_type = None
            message = None

            if current_spend >= limit:
                alert_active = True
                alert_type = "exceeded"
                message = f"Budget exceeded! Spent ${current_spend:.2f} of ${limit:.2f} limit."
            elif percent_used >= config.alert_threshold_pct:
                alert_active = True
                alert_type = "threshold"
                message = f"Budget warning: {percent_used:.1f}% of monthly limit used (${current_spend:.2f} of ${limit:.2f})."

            return BudgetAlertResponse(
                alert_active=alert_active,
                alert_type=alert_type,
                message=message,
                current_spend_usd=round(current_spend, 4),
                monthly_limit_usd=limit,
                percent_used=round(percent_used, 2),
            )
    except Exception as e:
        logger.error("Failed to fetch budget alerts: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch budget alerts")


@router.post("/budget/webhooks/test")
async def test_budget_webhook(request: WebhookTestRequest, current_user: dict = Depends(get_current_user)):
    """Send a test notification to verify webhook configuration (requires authentication)."""
    if request.webhook_type.lower() not in ("slack", "discord"):
        raise HTTPException(
            status_code=400,
            detail="webhook_type must be 'slack' or 'discord'",
        )

    success = await send_test_webhook(request.webhook_type, request.webhook_url)

    if success:
        return {"status": "success", "message": "Test notification sent successfully"}
    else:
        raise HTTPException(
            status_code=400,
            detail="Failed to send test notification. Check the webhook URL.",
        )


# ---------------------------------------------------------------------------
# History Route (with cursor pagination)
# ---------------------------------------------------------------------------


@router.get("/history", response_model=PaginatedHistory)
async def get_decision_history(
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0, description="Number of items to skip for pagination"),
    sport: Sport | None = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Get recent decision history (requires authentication).

    Supports pagination via `skip` and `limit` parameters.
    Optionally filter by sport.
    """
    if not db_service.is_configured:
        return PaginatedHistory(items=[], total=0, skip=skip, limit=limit)

    try:
        async with db_service.session() as session:
            # Base filter
            base_filter = DecisionModel.sport == sport.value if sport else True

            # Count total
            count_q = select(func.count(DecisionModel.id)).where(base_filter)
            total = (await session.execute(count_q)).scalar() or 0

            # Fetch page
            query = (
                select(DecisionModel)
                .where(base_filter)
                .order_by(DecisionModel.created_at.desc())
                .offset(skip)
                .limit(limit)
            )

            result = await session.execute(query)
            decisions = result.scalars().all()

            items = [
                DecisionHistoryItem(
                    id=str(d.id),
                    sport=d.sport,
                    risk_mode=d.risk_mode,
                    decision_type=d.decision_type,
                    query=d.query,
                    player_a_name=d.player_a_name,
                    player_b_name=d.player_b_name,
                    decision=d.decision,
                    confidence=d.confidence,
                    rationale=d.rationale,
                    source=d.source,
                    score_a=float(d.score_a) if d.score_a else None,
                    score_b=float(d.score_b) if d.score_b else None,
                    margin=float(d.margin) if d.margin else None,
                    created_at=d.created_at.isoformat(),
                )
                for d in decisions
            ]

            return PaginatedHistory(items=items, total=total, skip=skip, limit=limit)
    except Exception as e:
        logger.error("Failed to fetch history: %s", e, exc_info=True)
        return PaginatedHistory(items=[], total=0, skip=skip, limit=limit)


# ---------------------------------------------------------------------------
# Stripe Billing Routes
# ---------------------------------------------------------------------------


@router.post("/billing/create-checkout", response_model=CheckoutResponse)
async def create_checkout(
    request: CheckoutRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Create a Stripe Checkout session for Pro subscription upgrade.

    Redirects user to Stripe-hosted checkout page. Requires authentication.
    """
    if not stripe_billing.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Stripe billing is not configured. Set STRIPE_SECRET_KEY.",
        )

    user_id = current_user["user_id"]
    user_email = current_user["email"]

    try:
        checkout_url = await stripe_billing.create_checkout_session(
            user_id=user_id,
            user_email=user_email,
            price_id=request.price_id,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
        )
        return CheckoutResponse(checkout_url=checkout_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to create checkout session: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create checkout session")


@router.post("/billing/create-portal", response_model=PortalResponse)
async def create_portal(
    request: PortalRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Create a Stripe Billing Portal session for subscription management.

    Allows users to update payment method, cancel subscription, etc. Requires authentication.
    """
    if not stripe_billing.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Stripe billing is not configured. Set STRIPE_SECRET_KEY.",
        )

    user = await _get_user_by_id(current_user["user_id"])
    if not user or not user.stripe_customer_id:
        raise HTTPException(
            status_code=404,
            detail="User has no active subscription. Subscribe first.",
        )

    try:
        portal_url = await stripe_billing.create_portal_session(
            customer_id=user.stripe_customer_id,
            return_url=request.return_url,
        )
        return PortalResponse(portal_url=portal_url)
    except Exception as e:
        logger.error("Failed to create portal session: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create portal session")


@router.post("/billing/webhook")
async def handle_stripe_webhook(request: Request):
    """
    Handle Stripe webhook events.

    Processes subscription lifecycle events:
    - checkout.session.completed
    - customer.subscription.updated
    - customer.subscription.deleted
    - invoice.payment_failed
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing Stripe signature header")

    try:
        result = await stripe_billing.handle_webhook(payload, sig_header)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Webhook processing failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Webhook processing failed")


@router.get("/billing/status", response_model=BillingStatusResponse)
async def get_billing_status(
    current_user: dict = Depends(get_current_user),
):
    """
    Get current billing status for a user.

    Returns subscription tier, usage, and limits. Requires authentication.
    """
    user = await _get_user_by_id(current_user["user_id"])

    if not user:
        return BillingStatusResponse(
            tier="free",
            status="none",
            queries_today=0,
            weekly_limit=FREE_TIER_WEEKLY_LIMIT,
            queries_remaining=FREE_TIER_WEEKLY_LIMIT,
        )

    # Check if queries_reset_at needs update for new week
    now = datetime.now(UTC)
    queries_today = user.queries_today
    if user.queries_reset_at is None or (now - user.queries_reset_at) >= timedelta(days=7):
        queries_today = 0

    # Determine limits
    if user.subscription_tier == "pro":
        weekly_limit = -1  # Unlimited
        queries_remaining = None
    else:
        weekly_limit = FREE_TIER_WEEKLY_LIMIT
        queries_remaining = max(0, weekly_limit - queries_today)

    # Get Stripe subscription details if available
    subscription_status = "none"
    current_period_end = None
    cancel_at_period_end = False

    if user.stripe_customer_id:
        stripe_status = stripe_billing.get_subscription_status(user.stripe_customer_id)
        subscription_status = stripe_status.get("status", "none")
        current_period_end = stripe_status.get("current_period_end")
        cancel_at_period_end = stripe_status.get("cancel_at_period_end", False)

    return BillingStatusResponse(
        tier=user.subscription_tier,
        status=subscription_status,
        queries_today=queries_today,
        weekly_limit=weekly_limit,
        queries_remaining=queries_remaining,
        subscription_id=user.stripe_subscription_id,
        current_period_end=current_period_end,
        cancel_at_period_end=cancel_at_period_end,
    )
