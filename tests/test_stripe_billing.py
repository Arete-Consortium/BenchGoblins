"""Tests for Stripe billing service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import stripe

from services.stripe_billing import (
    _handle_checkout_completed,
    _handle_payment_failed,
    _handle_subscription_deleted,
    _handle_subscription_updated,
    create_checkout_session,
    create_portal_session,
    get_subscription_status,
    handle_webhook,
    is_configured,
)


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------


class TestIsLeaguePro:
    async def test_db_not_configured(self):
        from services.stripe_billing import is_league_pro

        with patch("services.stripe_billing.db_service") as mock_db:
            mock_db.is_configured = False
            result = await is_league_pro(1)
            assert result is False

    async def test_league_without_commissioner_continues(self):
        """Line 67: league.commissioner_user_id is None -> continue."""
        from services.stripe_billing import is_league_pro

        mock_league = MagicMock()
        mock_league.commissioner_user_id = None

        mock_session = AsyncMock()
        # First execute returns the leagues query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_league]
        mock_session.execute.return_value = mock_result

        with patch("services.stripe_billing.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await is_league_pro(1)
            assert result is False


class TestCreateCheckoutSessionWithMetadata:
    async def test_extra_metadata_included(self):
        """Line 120: extra_metadata dict gets merged into metadata."""
        mock_session = MagicMock()
        mock_session.id = "cs_test_123"
        mock_session.url = "https://checkout.stripe.com/session"

        with (
            patch("services.stripe_billing.is_configured", return_value=True),
            patch.dict(
                "services.stripe_billing.PRICE_IDS", {"pro_monthly": "price_xxx"}
            ),
            patch(
                "services.stripe_billing._get_or_create_customer",
                new_callable=AsyncMock,
                return_value="cus_123",
            ),
            patch("services.stripe_billing.stripe") as mock_stripe,
        ):
            mock_stripe.checkout.Session.create.return_value = mock_session
            mock_stripe.error = stripe.error

            url = await create_checkout_session(
                1,
                "a@b.com",
                "price_xxx",
                "http://ok",
                "http://no",
                extra_metadata={"league_id": "42"},
            )

            assert url == "https://checkout.stripe.com/session"
            call_kwargs = mock_stripe.checkout.Session.create.call_args
            metadata = call_kwargs[1]["metadata"]
            assert metadata["league_id"] == "42"
            assert metadata["user_id"] == "1"


class TestIsConfigured:
    def test_configured_when_api_key_set(self):
        with patch("services.stripe_billing.stripe") as mock_stripe:
            mock_stripe.api_key = "sk_test_123"
            assert is_configured() is True

    def test_not_configured_when_api_key_empty(self):
        with patch("services.stripe_billing.stripe") as mock_stripe:
            mock_stripe.api_key = ""
            assert is_configured() is False

    def test_not_configured_when_api_key_none(self):
        with patch("services.stripe_billing.stripe") as mock_stripe:
            mock_stripe.api_key = None
            assert is_configured() is False


# ---------------------------------------------------------------------------
# create_checkout_session
# ---------------------------------------------------------------------------


class TestCreateCheckoutSession:
    async def test_raises_when_not_configured(self):
        with patch("services.stripe_billing.is_configured", return_value=False):
            with pytest.raises(ValueError, match="Stripe is not configured"):
                await create_checkout_session(
                    1, "a@b.com", "price_xxx", "http://ok", "http://no"
                )

    async def test_raises_on_invalid_price_id(self):
        with (
            patch("services.stripe_billing.is_configured", return_value=True),
            patch.dict(
                "services.stripe_billing.PRICE_IDS", {"pro_monthly": "price_xxx"}
            ),
        ):
            with pytest.raises(ValueError, match="Invalid price_id"):
                await create_checkout_session(
                    1, "a@b.com", "price_bad", "http://ok", "http://no"
                )

    async def test_success(self):
        mock_session = MagicMock()
        mock_session.id = "cs_test_123"
        mock_session.url = "https://checkout.stripe.com/session"

        with (
            patch("services.stripe_billing.is_configured", return_value=True),
            patch.dict(
                "services.stripe_billing.PRICE_IDS", {"pro_monthly": "price_xxx"}
            ),
            patch(
                "services.stripe_billing._get_or_create_customer",
                new_callable=AsyncMock,
                return_value="cus_123",
            ),
            patch("services.stripe_billing.stripe") as mock_stripe,
        ):
            mock_stripe.checkout.Session.create.return_value = mock_session
            mock_stripe.error = stripe.error

            url = await create_checkout_session(
                1, "a@b.com", "price_xxx", "http://ok", "http://no"
            )

            assert url == "https://checkout.stripe.com/session"
            mock_stripe.checkout.Session.create.assert_called_once()

    async def test_stripe_error_propagates(self):
        with (
            patch("services.stripe_billing.is_configured", return_value=True),
            patch.dict(
                "services.stripe_billing.PRICE_IDS", {"pro_monthly": "price_xxx"}
            ),
            patch(
                "services.stripe_billing._get_or_create_customer",
                new_callable=AsyncMock,
                return_value="cus_123",
            ),
            patch("services.stripe_billing.stripe") as mock_stripe,
        ):
            mock_stripe.error = stripe.error
            mock_stripe.checkout.Session.create.side_effect = stripe.error.StripeError(
                "fail"
            )

            with pytest.raises(stripe.error.StripeError):
                await create_checkout_session(
                    1, "a@b.com", "price_xxx", "http://ok", "http://no"
                )


# ---------------------------------------------------------------------------
# create_portal_session
# ---------------------------------------------------------------------------


class TestCreatePortalSession:
    async def test_raises_when_not_configured(self):
        with patch("services.stripe_billing.is_configured", return_value=False):
            with pytest.raises(ValueError, match="Stripe is not configured"):
                await create_portal_session("cus_123", "http://return")

    async def test_success(self):
        mock_session = MagicMock()
        mock_session.url = "https://billing.stripe.com/portal"

        with (
            patch("services.stripe_billing.is_configured", return_value=True),
            patch("services.stripe_billing.stripe") as mock_stripe,
        ):
            mock_stripe.billing_portal.Session.create.return_value = mock_session
            mock_stripe.error = stripe.error

            url = await create_portal_session("cus_123", "http://return")

            assert url == "https://billing.stripe.com/portal"
            mock_stripe.billing_portal.Session.create.assert_called_once_with(
                customer="cus_123", return_url="http://return"
            )

    async def test_stripe_error_propagates(self):
        with (
            patch("services.stripe_billing.is_configured", return_value=True),
            patch("services.stripe_billing.stripe") as mock_stripe,
        ):
            mock_stripe.error = stripe.error
            mock_stripe.billing_portal.Session.create.side_effect = (
                stripe.error.StripeError("fail")
            )

            with pytest.raises(stripe.error.StripeError):
                await create_portal_session("cus_123", "http://return")


# ---------------------------------------------------------------------------
# handle_webhook
# ---------------------------------------------------------------------------


class TestHandleWebhook:
    async def test_raises_when_no_webhook_secret(self):
        with patch("services.stripe_billing.WEBHOOK_SECRET", ""):
            with pytest.raises(ValueError, match="Webhook secret not configured"):
                await handle_webhook(b"payload", "sig_header")

    async def test_raises_on_invalid_signature(self):
        with (
            patch("services.stripe_billing.WEBHOOK_SECRET", "whsec_test"),
            patch("services.stripe_billing.stripe") as mock_stripe,
        ):
            mock_stripe.error = stripe.error
            mock_stripe.Webhook.construct_event.side_effect = (
                stripe.error.SignatureVerificationError("bad sig", "sig")
            )

            with pytest.raises(ValueError, match="Invalid webhook signature"):
                await handle_webhook(b"payload", "bad_sig")

    async def test_checkout_completed_event(self):
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"metadata": {"user_id": "1"}, "customer": "cus_1"}},
        }

        with (
            patch("services.stripe_billing.WEBHOOK_SECRET", "whsec_test"),
            patch("services.stripe_billing.stripe") as mock_stripe,
            patch(
                "services.stripe_billing._handle_checkout_completed",
                new_callable=AsyncMock,
                return_value={"processed": True},
            ) as mock_handler,
        ):
            mock_stripe.error = stripe.error
            mock_stripe.Webhook.construct_event.return_value = event

            result = await handle_webhook(b"payload", "sig")

            assert result == {"processed": True}
            mock_handler.assert_called_once_with(event["data"]["object"])

    async def test_subscription_updated_event(self):
        event = {
            "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_1", "status": "active"}},
        }

        with (
            patch("services.stripe_billing.WEBHOOK_SECRET", "whsec_test"),
            patch("services.stripe_billing.stripe") as mock_stripe,
            patch(
                "services.stripe_billing._handle_subscription_updated",
                new_callable=AsyncMock,
                return_value={"processed": True},
            ) as mock_handler,
        ):
            mock_stripe.error = stripe.error
            mock_stripe.Webhook.construct_event.return_value = event

            result = await handle_webhook(b"payload", "sig")

            assert result == {"processed": True}
            mock_handler.assert_called_once()

    async def test_subscription_deleted_event(self):
        event = {
            "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_1"}},
        }

        with (
            patch("services.stripe_billing.WEBHOOK_SECRET", "whsec_test"),
            patch("services.stripe_billing.stripe") as mock_stripe,
            patch(
                "services.stripe_billing._handle_subscription_deleted",
                new_callable=AsyncMock,
                return_value={"processed": True},
            ) as mock_handler,
        ):
            mock_stripe.error = stripe.error
            mock_stripe.Webhook.construct_event.return_value = event

            result = await handle_webhook(b"payload", "sig")

            assert result == {"processed": True}
            mock_handler.assert_called_once()

    async def test_payment_failed_event(self):
        event = {
            "type": "invoice.payment_failed",
            "data": {"object": {"customer": "cus_1", "subscription": "sub_1"}},
        }

        with (
            patch("services.stripe_billing.WEBHOOK_SECRET", "whsec_test"),
            patch("services.stripe_billing.stripe") as mock_stripe,
            patch(
                "services.stripe_billing._handle_payment_failed",
                new_callable=AsyncMock,
                return_value={"processed": True},
            ) as mock_handler,
        ):
            mock_stripe.error = stripe.error
            mock_stripe.Webhook.construct_event.return_value = event

            result = await handle_webhook(b"payload", "sig")

            assert result == {"processed": True}
            mock_handler.assert_called_once()

    async def test_unhandled_event_type(self):
        event = {
            "type": "some.unknown.event",
            "data": {"object": {}},
        }

        with (
            patch("services.stripe_billing.WEBHOOK_SECRET", "whsec_test"),
            patch("services.stripe_billing.stripe") as mock_stripe,
        ):
            mock_stripe.error = stripe.error
            mock_stripe.Webhook.construct_event.return_value = event

            result = await handle_webhook(b"payload", "sig")

            assert result["processed"] is False
            assert result["reason"] == "unhandled_event"
            assert result["event_type"] == "some.unknown.event"


# ---------------------------------------------------------------------------
# get_subscription_status
# ---------------------------------------------------------------------------


class TestGetSubscriptionStatus:
    def test_not_configured(self):
        with patch("services.stripe_billing.is_configured", return_value=False):
            result = get_subscription_status("cus_123")
            assert result["status"] == "error"
            assert result["reason"] == "stripe_not_configured"

    def test_no_subscriptions(self):
        mock_list = MagicMock()
        mock_list.data = []

        with (
            patch("services.stripe_billing.is_configured", return_value=True),
            patch("services.stripe_billing.stripe") as mock_stripe,
        ):
            mock_stripe.Subscription.list.return_value = mock_list
            mock_stripe.error = stripe.error

            result = get_subscription_status("cus_123")

            assert result["status"] == "none"
            assert result["tier"] == "free"
            assert result["customer_id"] == "cus_123"

    def test_active_subscription(self):
        mock_sub = MagicMock()
        mock_sub.status = "active"
        mock_sub.id = "sub_123"
        mock_sub.current_period_start = 1700000000
        mock_sub.current_period_end = 1702592000
        mock_sub.cancel_at_period_end = False

        mock_list = MagicMock()
        mock_list.data = [mock_sub]

        with (
            patch("services.stripe_billing.is_configured", return_value=True),
            patch("services.stripe_billing.stripe") as mock_stripe,
        ):
            mock_stripe.Subscription.list.return_value = mock_list
            mock_stripe.error = stripe.error

            result = get_subscription_status("cus_123")

            assert result["status"] == "active"
            assert result["tier"] == "pro"
            assert result["subscription_id"] == "sub_123"
            assert result["cancel_at_period_end"] is False
            assert "current_period_start" in result
            assert "current_period_end" in result

    def test_cancelled_subscription_maps_to_free(self):
        mock_sub = MagicMock()
        mock_sub.status = "canceled"
        mock_sub.id = "sub_123"
        mock_sub.current_period_start = 1700000000
        mock_sub.current_period_end = 1702592000
        mock_sub.cancel_at_period_end = False

        mock_list = MagicMock()
        mock_list.data = [mock_sub]

        with (
            patch("services.stripe_billing.is_configured", return_value=True),
            patch("services.stripe_billing.stripe") as mock_stripe,
        ):
            mock_stripe.Subscription.list.return_value = mock_list
            mock_stripe.error = stripe.error

            result = get_subscription_status("cus_123")

            assert result["tier"] == "free"

    def test_stripe_error_returns_error_status(self):
        with (
            patch("services.stripe_billing.is_configured", return_value=True),
            patch("services.stripe_billing.stripe") as mock_stripe,
        ):
            mock_stripe.error = stripe.error
            mock_stripe.Subscription.list.side_effect = stripe.error.StripeError(
                "API down"
            )

            result = get_subscription_status("cus_123")

            assert result["status"] == "error"
            assert "API down" in result["reason"]


# ---------------------------------------------------------------------------
# _get_or_create_customer
# ---------------------------------------------------------------------------


class TestGetOrCreateCustomer:
    async def test_no_db_creates_stripe_only(self):
        mock_customer = MagicMock()
        mock_customer.id = "cus_new"

        with (
            patch("services.stripe_billing.db_service") as mock_db,
            patch("services.stripe_billing.stripe") as mock_stripe,
        ):
            mock_db.is_configured = False
            mock_stripe.Customer.create.return_value = mock_customer

            from services.stripe_billing import _get_or_create_customer

            result = await _get_or_create_customer(1, "a@b.com")

            assert result == "cus_new"
            mock_stripe.Customer.create.assert_called_once_with(
                email="a@b.com", metadata={"user_id": "1"}
            )

    async def test_existing_user_with_customer_id(self):
        mock_user = MagicMock()
        mock_user.stripe_customer_id = "cus_existing"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        with patch("services.stripe_billing.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

            from services.stripe_billing import _get_or_create_customer

            result = await _get_or_create_customer(1, "a@b.com")

            assert result == "cus_existing"

    async def test_existing_user_without_customer_id(self):
        mock_user = MagicMock()
        mock_user.stripe_customer_id = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_customer = MagicMock()
        mock_customer.id = "cus_new"

        with (
            patch("services.stripe_billing.db_service") as mock_db,
            patch("services.stripe_billing.stripe") as mock_stripe,
        ):
            mock_db.is_configured = True
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_stripe.Customer.create.return_value = mock_customer

            from services.stripe_billing import _get_or_create_customer

            result = await _get_or_create_customer(1, "a@b.com")

            assert result == "cus_new"
            assert mock_user.stripe_customer_id == "cus_new"

    async def test_user_not_in_db_logs_warning(self):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_customer = MagicMock()
        mock_customer.id = "cus_new"

        with (
            patch("services.stripe_billing.db_service") as mock_db,
            patch("services.stripe_billing.stripe") as mock_stripe,
            patch("services.stripe_billing.logger") as mock_logger,
        ):
            mock_db.is_configured = True
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_stripe.Customer.create.return_value = mock_customer

            from services.stripe_billing import _get_or_create_customer

            result = await _get_or_create_customer(99, "a@b.com")

            assert result == "cus_new"
            mock_logger.warning.assert_called_once()


# ---------------------------------------------------------------------------
# Webhook handlers
# ---------------------------------------------------------------------------


class TestHandleCheckoutCompleted:
    async def test_no_user_id_in_metadata(self):
        result = await _handle_checkout_completed({"metadata": {}, "customer": "cus_1"})
        assert result["processed"] is False
        assert result["reason"] == "no_user_id"

    async def test_empty_metadata(self):
        result = await _handle_checkout_completed({"customer": "cus_1"})
        assert result["processed"] is False
        assert result["reason"] == "no_user_id"

    async def test_db_configured_updates_user(self):
        mock_session = AsyncMock()

        with patch("services.stripe_billing.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _handle_checkout_completed(
                {
                    "metadata": {"user_id": "42"},
                    "customer": "cus_1",
                    "subscription": "sub_1",
                }
            )

            assert result["processed"] is True
            assert result["user_id"] == 42
            assert result["tier"] == "pro"
            mock_session.execute.assert_called_once()

    async def test_db_not_configured_still_returns_success(self):
        with patch("services.stripe_billing.db_service") as mock_db:
            mock_db.is_configured = False

            result = await _handle_checkout_completed(
                {
                    "metadata": {"user_id": "42"},
                    "customer": "cus_1",
                    "subscription": "sub_1",
                }
            )

            assert result["processed"] is True
            assert result["user_id"] == 42


class TestHandleSubscriptionUpdated:
    async def test_active_maps_to_pro(self):
        mock_session = AsyncMock()

        with patch("services.stripe_billing.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _handle_subscription_updated(
                {"id": "sub_1", "status": "active", "metadata": {"user_id": "1"}}
            )

            assert result["tier"] == "pro"
            assert result["processed"] is True

    async def test_trialing_maps_to_pro(self):
        mock_session = AsyncMock()

        with patch("services.stripe_billing.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _handle_subscription_updated(
                {"id": "sub_1", "status": "trialing", "metadata": {"user_id": "1"}}
            )

            assert result["tier"] == "pro"

    async def test_past_due_maps_to_free(self):
        mock_session = AsyncMock()

        with patch("services.stripe_billing.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _handle_subscription_updated(
                {"id": "sub_1", "status": "past_due", "metadata": {"user_id": "1"}}
            )

            assert result["tier"] == "free"

    async def test_no_user_id_logs_warning(self):
        with (
            patch("services.stripe_billing.db_service") as mock_db,
            patch("services.stripe_billing.logger") as mock_logger,
        ):
            mock_db.is_configured = True

            result = await _handle_subscription_updated(
                {"id": "sub_1", "status": "active", "metadata": {}}
            )

            assert result["processed"] is True
            mock_logger.warning.assert_called_once()


class TestHandleSubscriptionDeleted:
    async def test_db_configured_downgrades_user(self):
        mock_session = AsyncMock()

        with patch("services.stripe_billing.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _handle_subscription_deleted(
                {"id": "sub_1", "metadata": {"user_id": "1"}}
            )

            assert result["tier"] == "free"
            assert result["processed"] is True
            mock_session.execute.assert_called_once()

    async def test_no_user_id_logs_warning(self):
        with (
            patch("services.stripe_billing.db_service") as mock_db,
            patch("services.stripe_billing.logger") as mock_logger,
        ):
            mock_db.is_configured = True

            result = await _handle_subscription_deleted({"id": "sub_1", "metadata": {}})

            assert result["processed"] is True
            mock_logger.warning.assert_called_once()

    async def test_db_not_configured_still_returns_success(self):
        with patch("services.stripe_billing.db_service") as mock_db:
            mock_db.is_configured = False

            result = await _handle_subscription_deleted(
                {"id": "sub_1", "metadata": {"user_id": "1"}}
            )

            assert result["processed"] is True
            assert result["tier"] == "free"


class TestHandlePaymentFailed:
    async def test_returns_event_details(self):
        result = await _handle_payment_failed(
            {"customer": "cus_1", "subscription": "sub_1", "attempt_count": 3}
        )

        assert result["processed"] is True
        assert result["event_type"] == "invoice.payment_failed"
        assert result["customer_id"] == "cus_1"
        assert result["subscription_id"] == "sub_1"
        assert result["attempt_count"] == 3

    async def test_missing_fields_default(self):
        result = await _handle_payment_failed({})

        assert result["processed"] is True
        assert result["customer_id"] is None
        assert result["subscription_id"] is None
        assert result["attempt_count"] == 0
