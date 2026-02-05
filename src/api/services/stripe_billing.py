"""
Stripe Billing Service - Handles subscription management for BenchGoblin.

Provides:
- Checkout session creation for Pro upgrades
- Billing portal session for subscription management
- Webhook handling for subscription lifecycle events
- Subscription status queries
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any

import stripe
from sqlalchemy import select, update

from models.database import User
from services.database import db_service

logger = logging.getLogger(__name__)

# Initialize Stripe from environment
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# Price IDs for subscription tiers
PRICE_IDS = {
    "pro_monthly": os.getenv("STRIPE_PRO_MONTHLY_PRICE_ID", "price_xxx"),
}


def is_configured() -> bool:
    """Check if Stripe is properly configured."""
    return bool(stripe.api_key)


async def create_checkout_session(
    user_id: int,
    user_email: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """Create a Stripe Checkout session for subscription purchase.

    Args:
        user_id: Database user ID to associate with subscription
        user_email: User's email address
        price_id: Stripe Price ID for the subscription
        success_url: URL to redirect to on successful checkout
        cancel_url: URL to redirect to on cancelled checkout

    Returns:
        Checkout session URL for redirecting the user

    Raises:
        ValueError: If Stripe is not configured or price_id is invalid
        stripe.error.StripeError: If Stripe API call fails
    """
    if not is_configured():
        raise ValueError("Stripe is not configured. Set STRIPE_SECRET_KEY environment variable.")

    if price_id not in PRICE_IDS.values():
        raise ValueError(f"Invalid price_id: {price_id}")

    try:
        # Check if user already has a Stripe customer ID
        customer_id = await _get_or_create_customer(user_id, user_email)

        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[
                {
                    "price": price_id,
                    "quantity": 1,
                }
            ],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "user_id": str(user_id),
            },
            subscription_data={
                "metadata": {
                    "user_id": str(user_id),
                }
            },
        )

        logger.info(f"Created checkout session for user {user_id}: {session.id}")
        return session.url

    except stripe.error.StripeError as e:
        logger.error(f"Stripe checkout session creation failed: {e}")
        raise


async def create_portal_session(customer_id: str, return_url: str) -> str:
    """Create a Stripe Billing Portal session for subscription management.

    Args:
        customer_id: Stripe Customer ID
        return_url: URL to return to after portal session

    Returns:
        Billing portal URL for redirecting the user

    Raises:
        ValueError: If Stripe is not configured
        stripe.error.StripeError: If Stripe API call fails
    """
    if not is_configured():
        raise ValueError("Stripe is not configured. Set STRIPE_SECRET_KEY environment variable.")

    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )

        logger.info(f"Created portal session for customer {customer_id}")
        return session.url

    except stripe.error.StripeError as e:
        logger.error(f"Stripe portal session creation failed: {e}")
        raise


async def handle_webhook(payload: bytes, sig_header: str) -> dict[str, Any]:
    """Handle Stripe webhook events.

    Processes:
    - checkout.session.completed: User completed checkout
    - customer.subscription.updated: Subscription status changed
    - customer.subscription.deleted: Subscription cancelled

    Args:
        payload: Raw webhook payload bytes
        sig_header: Stripe signature header for verification

    Returns:
        Dict with event type and processing status

    Raises:
        ValueError: If webhook signature verification fails
    """
    if not WEBHOOK_SECRET:
        raise ValueError("Webhook secret not configured. Set STRIPE_WEBHOOK_SECRET.")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Webhook signature verification failed: {e}")
        raise ValueError("Invalid webhook signature")

    event_type = event["type"]
    data = event["data"]["object"]

    logger.info(f"Processing webhook event: {event_type}")

    result = {"event_type": event_type, "processed": False}

    if event_type == "checkout.session.completed":
        result = await _handle_checkout_completed(data)

    elif event_type == "customer.subscription.updated":
        result = await _handle_subscription_updated(data)

    elif event_type == "customer.subscription.deleted":
        result = await _handle_subscription_deleted(data)

    elif event_type == "invoice.payment_failed":
        result = await _handle_payment_failed(data)

    else:
        logger.debug(f"Unhandled webhook event type: {event_type}")
        result = {"event_type": event_type, "processed": False, "reason": "unhandled_event"}

    return result


def get_subscription_status(customer_id: str) -> dict[str, Any]:
    """Get current subscription status from Stripe.

    Args:
        customer_id: Stripe Customer ID

    Returns:
        Dict containing subscription details or empty status if no subscription
    """
    if not is_configured():
        return {"status": "error", "reason": "stripe_not_configured"}

    try:
        subscriptions = stripe.Subscription.list(customer=customer_id, status="all", limit=1)

        if not subscriptions.data:
            return {
                "status": "none",
                "tier": "free",
                "customer_id": customer_id,
            }

        sub = subscriptions.data[0]
        return {
            "status": sub.status,
            "tier": "pro" if sub.status == "active" else "free",
            "subscription_id": sub.id,
            "customer_id": customer_id,
            "current_period_start": datetime.fromtimestamp(sub.current_period_start, tz=UTC).isoformat(),
            "current_period_end": datetime.fromtimestamp(sub.current_period_end, tz=UTC).isoformat(),
            "cancel_at_period_end": sub.cancel_at_period_end,
        }

    except stripe.error.StripeError as e:
        logger.error(f"Failed to get subscription status: {e}")
        return {"status": "error", "reason": str(e)}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_or_create_customer(user_id: int, email: str) -> str:
    """Get existing Stripe customer ID or create a new customer.

    Args:
        user_id: Database user ID
        email: User's email address

    Returns:
        Stripe Customer ID
    """
    if not db_service.is_configured:
        # Create customer without database storage
        customer = stripe.Customer.create(
            email=email,
            metadata={"user_id": str(user_id)},
        )
        return customer.id

    async with db_service.session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user and user.stripe_customer_id:
            return user.stripe_customer_id

        # Create new Stripe customer
        customer = stripe.Customer.create(
            email=email,
            metadata={"user_id": str(user_id)},
        )

        # Store customer ID
        if user:
            user.stripe_customer_id = customer.id
        else:
            logger.warning(f"User {user_id} not found in database")

        return customer.id


async def _handle_checkout_completed(data: dict) -> dict[str, Any]:
    """Handle checkout.session.completed event.

    Updates user's subscription tier to 'pro'.
    """
    user_id_str = data.get("metadata", {}).get("user_id")
    customer_id = data.get("customer")
    subscription_id = data.get("subscription")

    if not user_id_str:
        logger.warning("Checkout completed without user_id in metadata")
        return {"event_type": "checkout.session.completed", "processed": False, "reason": "no_user_id"}

    user_id = int(user_id_str)

    if db_service.is_configured:
        async with db_service.session() as session:
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(
                    subscription_tier="pro",
                    stripe_customer_id=customer_id,
                    stripe_subscription_id=subscription_id,
                )
            )
            await session.execute(stmt)

    logger.info(f"User {user_id} upgraded to Pro via checkout")
    return {
        "event_type": "checkout.session.completed",
        "processed": True,
        "user_id": user_id,
        "tier": "pro",
    }


async def _handle_subscription_updated(data: dict) -> dict[str, Any]:
    """Handle customer.subscription.updated event.

    Updates user's subscription tier based on subscription status.
    """
    subscription_id = data.get("id")
    status = data.get("status")
    user_id_str = data.get("metadata", {}).get("user_id")

    # Map Stripe status to tier
    tier = "pro" if status in ("active", "trialing") else "free"

    if user_id_str and db_service.is_configured:
        user_id = int(user_id_str)
        async with db_service.session() as session:
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(subscription_tier=tier)
            )
            await session.execute(stmt)
        logger.info(f"User {user_id} subscription updated: status={status}, tier={tier}")
    else:
        logger.warning(f"Subscription {subscription_id} updated but no user_id found")

    return {
        "event_type": "customer.subscription.updated",
        "processed": True,
        "subscription_id": subscription_id,
        "status": status,
        "tier": tier,
    }


async def _handle_subscription_deleted(data: dict) -> dict[str, Any]:
    """Handle customer.subscription.deleted event.

    Downgrades user to free tier.
    """
    subscription_id = data.get("id")
    user_id_str = data.get("metadata", {}).get("user_id")

    if user_id_str and db_service.is_configured:
        user_id = int(user_id_str)
        async with db_service.session() as session:
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(
                    subscription_tier="free",
                    stripe_subscription_id=None,
                )
            )
            await session.execute(stmt)
        logger.info(f"User {user_id} subscription cancelled, downgraded to free")
    else:
        logger.warning(f"Subscription {subscription_id} deleted but no user_id found")

    return {
        "event_type": "customer.subscription.deleted",
        "processed": True,
        "subscription_id": subscription_id,
        "tier": "free",
    }


async def _handle_payment_failed(data: dict) -> dict[str, Any]:
    """Handle invoice.payment_failed event.

    Logs payment failure but doesn't immediately downgrade
    (Stripe handles retry logic).
    """
    customer_id = data.get("customer")
    subscription_id = data.get("subscription")
    attempt_count = data.get("attempt_count", 0)

    logger.warning(
        f"Payment failed for customer {customer_id}, "
        f"subscription {subscription_id}, attempt {attempt_count}"
    )

    return {
        "event_type": "invoice.payment_failed",
        "processed": True,
        "customer_id": customer_id,
        "subscription_id": subscription_id,
        "attempt_count": attempt_count,
    }
