"""Tests for integration/feature routes in api.main."""

from unittest.mock import AsyncMock, MagicMock, patch


# ---- helpers ---------------------------------------------------------------


def _mock_db_session():
    mock_session = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_session


def _override_admin():
    from api.main import app
    from routes.auth import require_admin_key

    app.dependency_overrides[require_admin_key] = lambda: "admin"


def _override_user(user_id=1, email="test@example.com"):
    from api.main import app
    from routes.auth import get_current_user, require_pro

    user = {"user_id": user_id, "email": email}
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_pro] = lambda: user


def _clear_overrides():
    from api.main import app

    app.dependency_overrides.clear()


# =============================================================================
# SLEEPER ROUTES
# =============================================================================


class TestSleeperUser:
    @patch("api.main.sleeper_service.get_user", new_callable=AsyncMock)
    def test_user_found(self, mock_get, test_client):
        user = MagicMock()
        user.user_id = "123"
        user.username = "testuser"
        user.display_name = "Test"
        user.avatar = "https://img.png"
        mock_get.return_value = user

        resp = test_client.get("/integrations/sleeper/user/testuser")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "123"
        assert data["username"] == "testuser"

    @patch("api.main.sleeper_service.get_user", new_callable=AsyncMock)
    def test_user_not_found(self, mock_get, test_client):
        mock_get.return_value = None
        resp = test_client.get("/integrations/sleeper/user/nobody")
        assert resp.status_code == 404


class TestSleeperLeagues:
    @patch("api.main.sleeper_service.get_user_leagues", new_callable=AsyncMock)
    def test_returns_leagues(self, mock_leagues, test_client):
        league = MagicMock()
        league.league_id = "L1"
        league.name = "My League"
        league.sport = "nfl"
        league.season = "2024"
        league.status = "in_season"
        league.total_rosters = 12
        mock_leagues.return_value = [league]

        resp = test_client.get("/integrations/sleeper/user/abc/leagues")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["league_id"] == "L1"


class TestSleeperRoster:
    @patch("api.main.sleeper_service.get_players_by_ids", new_callable=AsyncMock)
    @patch("api.main.sleeper_service.get_user_roster", new_callable=AsyncMock)
    def test_success(self, mock_roster, mock_players, test_client):
        roster = MagicMock()
        roster.roster_id = 1
        roster.owner_id = "u1"
        roster.players = ["p1"]
        roster.starters = ["p1"]
        mock_roster.return_value = roster

        player = MagicMock()
        player.player_id = "p1"
        player.full_name = "Player One"
        player.team = "NYG"
        player.position = "WR"
        player.status = "Active"
        player.injury_status = None
        mock_players.return_value = [player]

        resp = test_client.get("/integrations/sleeper/league/L1/roster/u1?sport=nfl")
        assert resp.status_code == 200
        data = resp.json()
        assert data["roster_id"] == 1
        assert len(data["players"]) == 1

    @patch("api.main.sleeper_service.get_user_roster", new_callable=AsyncMock)
    def test_not_found(self, mock_roster, test_client):
        mock_roster.return_value = None
        resp = test_client.get("/integrations/sleeper/league/L1/roster/u1")
        assert resp.status_code == 404


class TestSleeperTrending:
    @patch("api.main.sleeper_service.get_players_by_ids", new_callable=AsyncMock)
    @patch("api.main.sleeper_service.get_trending_players", new_callable=AsyncMock)
    def test_returns_enriched(self, mock_trend, mock_players, test_client):
        mock_trend.return_value = [
            {"player_id": "p1", "count": 500},
        ]
        player = MagicMock()
        player.player_id = "p1"
        player.full_name = "Trending Guy"
        player.team = "DAL"
        player.position = "RB"
        mock_players.return_value = [player]

        resp = test_client.get("/integrations/sleeper/trending/nfl")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["count"] == 500
        assert data[0]["player"]["full_name"] == "Trending Guy"


# =============================================================================
# NOTIFICATION ROUTES
# =============================================================================


class TestNotificationRegister:
    @patch(
        "routes.notifications.notification_service.register_token",
        new_callable=AsyncMock,
    )
    @patch("routes.notifications.db_service")
    def test_register_token(self, mock_db, mock_reg, test_client):
        _override_user()
        try:
            mock_ctx, mock_session = _mock_db_session()
            mock_db.session.return_value = mock_ctx
            mock_session.commit = AsyncMock()

            resp = test_client.post(
                "/notifications/register", json={"token": "ExponentPushToken[xxx]"}
            )
            assert resp.status_code == 200
            assert resp.json()["registered"] is True
        finally:
            _clear_overrides()


class TestNotificationUnregister:
    @patch("api.main.notification_service.unregister_token", new_callable=AsyncMock)
    @patch("api.main.db_service")
    def test_unregister(self, mock_db, mock_unreg, test_client):
        mock_db.is_configured = True
        mock_ctx, _ = _mock_db_session()
        mock_db.session.return_value = mock_ctx

        resp = test_client.post("/notifications/unregister", json={"token": "tok"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "unregistered"


class TestNotificationSend:
    @patch("api.main.notification_service.send_notification", new_callable=AsyncMock)
    def test_send(self, mock_send, test_client):
        _override_admin()
        try:
            mock_send.return_value = {"status": "ok"}
            resp = test_client.post(
                "/notifications/send?token=tok123",
                json={"title": "Hello", "body": "World"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"
        finally:
            _clear_overrides()


class TestNotificationBroadcast:
    @patch("api.main.notification_service.send_to_all", new_callable=AsyncMock)
    @patch("api.main.db_service")
    def test_broadcast_success(self, mock_db, mock_send, test_client):
        _override_admin()
        try:
            mock_db.is_configured = True
            mock_ctx, _ = _mock_db_session()
            mock_db.session.return_value = mock_ctx
            mock_send.return_value = [{"status": "ok"}]

            resp = test_client.post(
                "/notifications/broadcast",
                json={"title": "Alert", "body": "Msg"},
            )
            assert resp.status_code == 200
            assert resp.json()["sent"] == 1
        finally:
            _clear_overrides()

    @patch("api.main.db_service")
    def test_broadcast_db_not_configured(self, mock_db, test_client):
        _override_admin()
        try:
            mock_db.is_configured = False
            resp = test_client.post(
                "/notifications/broadcast",
                json={"title": "Alert", "body": "Msg"},
            )
            assert resp.status_code == 503
        finally:
            _clear_overrides()


class TestNotificationTokens:
    @patch("api.main.notification_service.get_all_tokens", new_callable=AsyncMock)
    @patch("api.main.db_service")
    def test_list_tokens(self, mock_db, mock_tokens, test_client):
        _override_admin()
        try:
            mock_db.is_configured = True
            mock_ctx, _ = _mock_db_session()
            mock_db.session.return_value = mock_ctx
            mock_tokens.return_value = ["tok1", "tok2"]

            resp = test_client.get("/notifications/tokens")
            assert resp.status_code == 200
            assert resp.json()["count"] == 2
        finally:
            _clear_overrides()

    @patch("api.main.db_service")
    def test_list_tokens_db_not_configured(self, mock_db, test_client):
        _override_admin()
        try:
            mock_db.is_configured = False
            resp = test_client.get("/notifications/tokens")
            assert resp.status_code == 503
        finally:
            _clear_overrides()


# =============================================================================
# ACCURACY ROUTES
# =============================================================================


class TestRecordOutcome:
    @patch("api.main.accuracy_tracker.record_outcome", new_callable=AsyncMock)
    @patch("api.main.db_service")
    def test_recorded(self, mock_db, mock_record, test_client):
        mock_db.is_configured = True
        mock_ctx, _ = _mock_db_session()
        mock_db.session.return_value = mock_ctx
        mock_record.return_value = True

        resp = test_client.post(
            "/accuracy/outcomes",
            json={"decision_id": "d1", "actual_points_a": 25.0},
        )
        assert resp.status_code == 200
        assert resp.json()["decision_id"] == "d1"

    @patch("api.main.accuracy_tracker.record_outcome", new_callable=AsyncMock)
    @patch("api.main.db_service")
    def test_decision_not_found(self, mock_db, mock_record, test_client):
        mock_db.is_configured = True
        mock_ctx, _ = _mock_db_session()
        mock_db.session.return_value = mock_ctx
        mock_record.return_value = False

        resp = test_client.post(
            "/accuracy/outcomes",
            json={"decision_id": "missing"},
        )
        assert resp.status_code == 404


class TestAccuracyMetrics:
    @patch("api.main.accuracy_tracker.compute_metrics")
    @patch("api.main.db_service")
    def test_metrics_db_configured(self, mock_db, mock_compute, test_client):
        mock_db.is_configured = True
        mock_ctx, mock_session = _mock_db_session()
        mock_db.session.return_value = mock_ctx

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        metrics = MagicMock()
        metrics.total_decisions = 10
        metrics.decisions_with_outcomes = 8
        metrics.correct_decisions = 6
        metrics.incorrect_decisions = 2
        metrics.pushes = 0
        metrics.accuracy_pct = 75.0
        metrics.coverage_pct = 80.0
        metrics.high_confidence_total = 5
        metrics.high_confidence_correct = 4
        metrics.medium_confidence_total = 3
        metrics.medium_confidence_correct = 2
        metrics.low_confidence_total = 2
        metrics.low_confidence_correct = 0
        metrics.local_total = 4
        metrics.local_correct = 3
        metrics.claude_total = 6
        metrics.claude_correct = 3
        metrics.by_sport = {}
        metrics.by_variant = {}
        metrics.confidence_accuracy.return_value = 80.0
        mock_compute.return_value = metrics

        resp = test_client.get("/accuracy/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_decisions"] == 10
        assert data["accuracy_pct"] == 75.0

    @patch("api.main.accuracy_tracker.compute_metrics")
    @patch("api.main.db_service")
    def test_metrics_db_not_configured(self, mock_db, mock_compute, test_client):
        mock_db.is_configured = False
        metrics = MagicMock()
        metrics.total_decisions = 0
        metrics.decisions_with_outcomes = 0
        metrics.correct_decisions = 0
        metrics.incorrect_decisions = 0
        metrics.pushes = 0
        metrics.accuracy_pct = 0.0
        metrics.coverage_pct = 0.0
        metrics.high_confidence_total = 0
        metrics.high_confidence_correct = 0
        metrics.medium_confidence_total = 0
        metrics.medium_confidence_correct = 0
        metrics.low_confidence_total = 0
        metrics.low_confidence_correct = 0
        metrics.local_total = 0
        metrics.local_correct = 0
        metrics.claude_total = 0
        metrics.claude_correct = 0
        metrics.by_sport = {}
        metrics.by_variant = {}
        metrics.confidence_accuracy.return_value = 0.0
        mock_compute.return_value = metrics

        resp = test_client.get("/accuracy/metrics")
        assert resp.status_code == 200
        assert resp.json()["total_decisions"] == 0


class TestGetOutcome:
    @patch("api.main.accuracy_tracker.get_outcome", new_callable=AsyncMock)
    @patch("api.main.db_service")
    def test_found(self, mock_db, mock_get, test_client):
        mock_db.is_configured = True
        mock_ctx, _ = _mock_db_session()
        mock_db.session.return_value = mock_ctx

        outcome = MagicMock()
        outcome.decision_id = "d1"
        outcome.actual_points_a = 30.0
        outcome.actual_points_b = 20.0
        mock_get.return_value = outcome

        resp = test_client.get("/accuracy/outcome/d1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["decision_id"] == "d1"
        assert data["actual_points_a"] == 30.0

    @patch("api.main.accuracy_tracker.get_outcome", new_callable=AsyncMock)
    @patch("api.main.db_service")
    def test_not_found(self, mock_db, mock_get, test_client):
        mock_db.is_configured = True
        mock_ctx, _ = _mock_db_session()
        mock_db.session.return_value = mock_ctx
        mock_get.return_value = None

        resp = test_client.get("/accuracy/outcome/missing")
        assert resp.status_code == 404

    @patch("api.main.db_service")
    def test_db_not_configured(self, mock_db, test_client):
        mock_db.is_configured = False
        resp = test_client.get("/accuracy/outcome/d1")
        assert resp.status_code == 503


class TestSyncOutcomes:
    @patch("services.outcome_recorder.sync_recent_outcomes", new_callable=AsyncMock)
    def test_success(self, mock_sync, test_client):
        mock_sync.return_value = {"matched": 5, "recorded": 3}
        resp = test_client.post("/accuracy/sync", json={"days_back": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["matched"] == 5

    def test_invalid_sport(self, test_client):
        resp = test_client.post("/accuracy/sync", json={"sport": "curling"})
        assert resp.status_code == 400

    @patch("services.outcome_recorder.sync_recent_outcomes", new_callable=AsyncMock)
    def test_sync_failure(self, mock_sync, test_client):
        mock_sync.side_effect = RuntimeError("ESPN down")
        resp = test_client.post("/accuracy/sync", json={"days_back": 1})
        assert resp.status_code == 500
        assert "Sync failed" in resp.json()["detail"]


class TestAccuracyReset:
    @patch("api.main.db_service")
    def test_reset_success(self, mock_db, test_client):
        _override_user(user_id=42)
        try:
            mock_db.is_configured = True
            mock_ctx, mock_session = _mock_db_session()
            mock_db.session.return_value = mock_ctx
            mock_result = MagicMock()
            mock_result.rowcount = 7
            mock_session.execute = AsyncMock(return_value=mock_result)

            resp = test_client.delete("/accuracy/reset")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "reset"
            assert data["deleted"] == 7
        finally:
            _clear_overrides()

    @patch("api.main.db_service")
    def test_reset_db_not_configured(self, mock_db, test_client):
        _override_user(user_id=42)
        try:
            mock_db.is_configured = False
            resp = test_client.delete("/accuracy/reset")
            assert resp.status_code == 503
        finally:
            _clear_overrides()

    def test_reset_unauthenticated(self, test_client):
        _clear_overrides()
        resp = test_client.delete("/accuracy/reset")
        assert resp.status_code in (401, 403)


# =============================================================================
# BILLING ROUTES
# =============================================================================


class TestBillingPrices:
    @patch("api.main.stripe_billing")
    def test_returns_prices(self, mock_stripe, test_client):
        mock_stripe.PRICE_IDS = {
            "pro_monthly": "price_123",
            "pro_annual": None,
        }
        resp = test_client.get("/billing/prices")
        assert resp.status_code == 200
        data = resp.json()
        assert "pro_monthly" in data["prices"]
        assert "pro_annual" not in data["prices"]


class TestCreateCheckout:
    @patch("api.main.stripe_billing")
    def test_success(self, mock_stripe, test_client):
        _override_user()
        try:
            mock_stripe.is_configured.return_value = True
            mock_stripe.create_checkout_session = AsyncMock(
                return_value="https://checkout.stripe.com/abc"
            )
            resp = test_client.post(
                "/billing/create-checkout",
                json={
                    "price_id": "price_123",
                    "success_url": "https://app.com/ok",
                    "cancel_url": "https://app.com/cancel",
                },
            )
            assert resp.status_code == 200
            assert resp.json()["checkout_url"] == "https://checkout.stripe.com/abc"
        finally:
            _clear_overrides()

    @patch("api.main.stripe_billing")
    def test_not_configured(self, mock_stripe, test_client):
        _override_user()
        try:
            mock_stripe.is_configured.return_value = False
            resp = test_client.post(
                "/billing/create-checkout",
                json={
                    "price_id": "price_123",
                    "success_url": "https://app.com/ok",
                    "cancel_url": "https://app.com/cancel",
                },
            )
            assert resp.status_code == 503
        finally:
            _clear_overrides()

    @patch("api.main.stripe_billing")
    def test_value_error(self, mock_stripe, test_client):
        _override_user()
        try:
            mock_stripe.is_configured.return_value = True
            mock_stripe.create_checkout_session = AsyncMock(
                side_effect=ValueError("Invalid price ID")
            )
            resp = test_client.post(
                "/billing/create-checkout",
                json={
                    "price_id": "bad",
                    "success_url": "https://app.com/ok",
                    "cancel_url": "https://app.com/cancel",
                },
            )
            assert resp.status_code == 400
        finally:
            _clear_overrides()

    @patch("api.main.stripe_billing")
    def test_generic_error(self, mock_stripe, test_client):
        _override_user()
        try:
            mock_stripe.is_configured.return_value = True
            mock_stripe.create_checkout_session = AsyncMock(
                side_effect=RuntimeError("boom")
            )
            resp = test_client.post(
                "/billing/create-checkout",
                json={
                    "price_id": "price_123",
                    "success_url": "https://app.com/ok",
                    "cancel_url": "https://app.com/cancel",
                },
            )
            assert resp.status_code == 500
        finally:
            _clear_overrides()


class TestCreatePortal:
    @patch("api.main._get_user_by_id", new_callable=AsyncMock)
    @patch("api.main.stripe_billing")
    def test_success(self, mock_stripe, mock_get_user, test_client):
        _override_user()
        try:
            mock_stripe.is_configured.return_value = True
            mock_stripe.create_portal_session = AsyncMock(
                return_value="https://billing.stripe.com/portal"
            )
            user = MagicMock()
            user.stripe_customer_id = "cus_123"
            mock_get_user.return_value = user

            resp = test_client.post(
                "/billing/create-portal",
                json={"return_url": "https://app.com/settings"},
            )
            assert resp.status_code == 200
            assert "portal" in resp.json()["portal_url"]
        finally:
            _clear_overrides()

    @patch("api.main.stripe_billing")
    def test_not_configured(self, mock_stripe, test_client):
        _override_user()
        try:
            mock_stripe.is_configured.return_value = False
            resp = test_client.post(
                "/billing/create-portal",
                json={"return_url": "https://app.com/settings"},
            )
            assert resp.status_code == 503
        finally:
            _clear_overrides()

    @patch("api.main._get_user_by_id", new_callable=AsyncMock)
    @patch("api.main.stripe_billing")
    def test_user_not_found(self, mock_stripe, mock_get_user, test_client):
        _override_user()
        try:
            mock_stripe.is_configured.return_value = True
            mock_get_user.return_value = None
            resp = test_client.post(
                "/billing/create-portal",
                json={"return_url": "https://app.com/settings"},
            )
            assert resp.status_code == 404
        finally:
            _clear_overrides()

    @patch("api.main._get_user_by_id", new_callable=AsyncMock)
    @patch("api.main.stripe_billing")
    def test_no_stripe_customer(self, mock_stripe, mock_get_user, test_client):
        _override_user()
        try:
            mock_stripe.is_configured.return_value = True
            user = MagicMock()
            user.stripe_customer_id = None
            mock_get_user.return_value = user
            resp = test_client.post(
                "/billing/create-portal",
                json={"return_url": "https://app.com/settings"},
            )
            assert resp.status_code == 404
        finally:
            _clear_overrides()


class TestBillingWebhook:
    @patch("api.main.stripe_billing.handle_webhook", new_callable=AsyncMock)
    def test_success(self, mock_hook, test_client):
        mock_hook.return_value = {"received": True}
        resp = test_client.post(
            "/billing/webhook",
            content=b'{"type":"checkout.session.completed"}',
            headers={"stripe-signature": "sig_123"},
        )
        assert resp.status_code == 200

    def test_missing_signature(self, test_client):
        resp = test_client.post(
            "/billing/webhook",
            content=b"{}",
        )
        assert resp.status_code == 400
        assert "Missing" in resp.json()["detail"]

    @patch("api.main.stripe_billing.handle_webhook", new_callable=AsyncMock)
    def test_value_error(self, mock_hook, test_client):
        mock_hook.side_effect = ValueError("bad sig")
        resp = test_client.post(
            "/billing/webhook",
            content=b"{}",
            headers={"stripe-signature": "sig_bad"},
        )
        assert resp.status_code == 400

    @patch("api.main.stripe_billing.handle_webhook", new_callable=AsyncMock)
    def test_generic_error(self, mock_hook, test_client):
        mock_hook.side_effect = RuntimeError("boom")
        resp = test_client.post(
            "/billing/webhook",
            content=b"{}",
            headers={"stripe-signature": "sig_ok"},
        )
        assert resp.status_code == 500


class TestBillingStatus:
    @patch("api.main._get_user_by_id", new_callable=AsyncMock)
    def test_user_not_found_returns_free(self, mock_get_user, test_client):
        _override_user()
        try:
            mock_get_user.return_value = None
            resp = test_client.get("/billing/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["tier"] == "free"
            assert data["weekly_limit"] == 5
        finally:
            _clear_overrides()

    @patch("api.main.stripe_billing")
    @patch("api.main._get_user_by_id", new_callable=AsyncMock)
    def test_pro_user(self, mock_get_user, mock_stripe, test_client):
        _override_user()
        try:
            user = MagicMock()
            user.id = 1
            user.subscription_tier = "pro"
            user.queries_today = 50
            user.queries_reset_at = None
            user.stripe_customer_id = None
            user.stripe_subscription_id = None
            mock_get_user.return_value = user
            mock_stripe.is_league_pro = AsyncMock(return_value=False)

            resp = test_client.get("/billing/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["tier"] == "pro"
            assert data["weekly_limit"] == -1
            assert data["queries_remaining"] is None
        finally:
            _clear_overrides()

    @patch("api.main.stripe_billing")
    @patch("api.main._get_user_by_id", new_callable=AsyncMock)
    def test_league_pro_check(self, mock_get_user, mock_stripe, test_client):
        _override_user()
        try:
            user = MagicMock()
            user.id = 1
            user.subscription_tier = "free"
            user.queries_today = 2
            user.queries_reset_at = None
            user.stripe_customer_id = None
            user.stripe_subscription_id = None
            mock_get_user.return_value = user
            mock_stripe.is_league_pro = AsyncMock(return_value=True)

            resp = test_client.get("/billing/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["weekly_limit"] == -1
        finally:
            _clear_overrides()

    @patch("api.main.stripe_billing")
    @patch("api.main._get_user_by_id", new_callable=AsyncMock)
    def test_stripe_subscription_status(self, mock_get_user, mock_stripe, test_client):
        _override_user()
        try:
            user = MagicMock()
            user.id = 1
            user.subscription_tier = "pro"
            user.queries_today = 0
            user.queries_reset_at = None
            user.stripe_customer_id = "cus_abc"
            user.stripe_subscription_id = "sub_xyz"
            mock_get_user.return_value = user
            mock_stripe.is_league_pro = AsyncMock(return_value=False)
            mock_stripe.get_subscription_status.return_value = {
                "status": "active",
                "current_period_end": "2026-03-01",
                "cancel_at_period_end": False,
            }

            resp = test_client.get("/billing/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "active"
            assert data["current_period_end"] == "2026-03-01"
        finally:
            _clear_overrides()


# =============================================================================
# WEEKLY RECAP ROUTES
# =============================================================================


class TestGetWeeklyRecaps:
    @patch("services.weekly_recap.get_user_recaps", new_callable=AsyncMock)
    @patch("api.main.db_service")
    def test_success(self, mock_db, mock_get_recaps, test_client):
        _override_user()
        try:
            mock_db.is_configured = True
            mock_ctx, _ = _mock_db_session()
            mock_db.session.return_value = mock_ctx

            recap = MagicMock()
            recap.id = 1
            recap.week_start = MagicMock()
            recap.week_start.isoformat.return_value = "2026-02-17"
            recap.week_end = MagicMock()
            recap.week_end.isoformat.return_value = "2026-02-23"
            recap.total_decisions = 10
            recap.correct_decisions = 7
            recap.incorrect_decisions = 2
            recap.pending_decisions = 1
            recap.accuracy_pct = 77.8
            recap.avg_confidence = "high"
            recap.most_asked_sport = "nba"
            recap.narrative = "Great week!"
            recap.highlights = "3-game win streak"
            recap.created_at = MagicMock()
            recap.created_at.isoformat.return_value = "2026-02-23T12:00:00"
            mock_get_recaps.return_value = [recap]

            resp = test_client.get("/recaps/weekly")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["total_decisions"] == 10
        finally:
            _clear_overrides()

    @patch("api.main.db_service")
    def test_db_not_configured(self, mock_db, test_client):
        _override_user()
        try:
            mock_db.is_configured = False
            resp = test_client.get("/recaps/weekly")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            _clear_overrides()

    @patch("services.weekly_recap.get_user_recaps", new_callable=AsyncMock)
    @patch("api.main.db_service")
    def test_exception_returns_empty(self, mock_db, mock_get_recaps, test_client):
        _override_user()
        try:
            mock_db.is_configured = True
            mock_ctx, _ = _mock_db_session()
            mock_db.session.return_value = mock_ctx
            mock_get_recaps.side_effect = RuntimeError("db error")

            resp = test_client.get("/recaps/weekly")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            _clear_overrides()


class TestGenerateRecap:
    @patch("services.weekly_recap.generate_weekly_recap", new_callable=AsyncMock)
    @patch("api.main.stripe_billing")
    @patch("api.main._get_user_by_id", new_callable=AsyncMock)
    @patch("api.main.db_service")
    def test_success(self, mock_db, mock_get_user, mock_stripe, mock_gen, test_client):
        _override_user()
        try:
            mock_db.is_configured = True
            mock_ctx, _ = _mock_db_session()
            mock_db.session.return_value = mock_ctx

            user = MagicMock()
            user.id = 1
            user.name = "Test"
            user.subscription_tier = "pro"
            mock_get_user.return_value = user

            recap = MagicMock()
            recap.id = 42
            recap.week_start = MagicMock()
            recap.week_start.isoformat.return_value = "2026-02-17"
            recap.week_end = MagicMock()
            recap.week_end.isoformat.return_value = "2026-02-23"
            recap.total_decisions = 5
            recap.correct_decisions = 4
            recap.incorrect_decisions = 1
            recap.pending_decisions = 0
            recap.accuracy_pct = 80.0
            recap.avg_confidence = "medium"
            recap.most_asked_sport = "nfl"
            recap.narrative = "Solid week."
            recap.highlights = None
            recap.created_at = MagicMock()
            recap.created_at.isoformat.return_value = "2026-02-23T12:00:00"
            mock_gen.return_value = recap

            resp = test_client.post("/recaps/weekly/generate")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_decisions"] == 5
        finally:
            _clear_overrides()

    @patch("api.main.db_service")
    def test_db_not_configured(self, mock_db, test_client):
        _override_user()
        try:
            mock_db.is_configured = False
            resp = test_client.post("/recaps/weekly/generate")
            assert resp.status_code == 503
        finally:
            _clear_overrides()

    @patch("api.main._get_user_by_id", new_callable=AsyncMock)
    @patch("api.main.db_service")
    def test_user_not_found(self, mock_db, mock_get_user, test_client):
        _override_user()
        try:
            mock_db.is_configured = True
            mock_get_user.return_value = None
            resp = test_client.post("/recaps/weekly/generate")
            assert resp.status_code == 404
        finally:
            _clear_overrides()

    def test_not_pro(self, test_client):
        from api.main import app
        from routes.auth import get_current_user, require_pro

        # Override get_current_user but NOT require_pro so the pro gate runs
        app.dependency_overrides[get_current_user] = lambda: {
            "user_id": 1,
            "email": "test@example.com",
        }
        app.dependency_overrides.pop(require_pro, None)
        try:
            with (
                patch("routes.auth.db_service") as mock_db,
                patch("routes.auth.get_user_by_id", new_callable=AsyncMock) as mock_get_user,
                patch("services.stripe_billing.is_league_pro", new_callable=AsyncMock) as mock_league_pro,
            ):
                mock_db.is_configured = True
                mock_ctx, mock_session = _mock_db_session()
                mock_db.session.return_value = mock_ctx
                user = MagicMock()
                user.id = 1
                user.subscription_tier = "free"
                user.referral_pro_expires_at = None
                mock_get_user.return_value = user
                mock_league_pro.return_value = False

                resp = test_client.post("/recaps/weekly/generate")
                assert resp.status_code == 403
        finally:
            _clear_overrides()

    @patch("services.weekly_recap.generate_weekly_recap", new_callable=AsyncMock)
    @patch("api.main.stripe_billing")
    @patch("api.main._get_user_by_id", new_callable=AsyncMock)
    @patch("api.main.db_service")
    def test_no_decisions_returns_null(
        self, mock_db, mock_get_user, mock_stripe, mock_gen, test_client
    ):
        _override_user()
        try:
            mock_db.is_configured = True
            mock_ctx, _ = _mock_db_session()
            mock_db.session.return_value = mock_ctx

            user = MagicMock()
            user.id = 1
            user.name = "Test"
            user.subscription_tier = "pro"
            mock_get_user.return_value = user
            mock_gen.return_value = None

            resp = test_client.post("/recaps/weekly/generate")
            assert resp.status_code == 200
            assert resp.json() is None
        finally:
            _clear_overrides()

    @patch("services.weekly_recap.generate_weekly_recap", new_callable=AsyncMock)
    @patch("api.main.stripe_billing")
    @patch("api.main._get_user_by_id", new_callable=AsyncMock)
    @patch("api.main.db_service")
    def test_exception(
        self, mock_db, mock_get_user, mock_stripe, mock_gen, test_client
    ):
        _override_user()
        try:
            mock_db.is_configured = True
            mock_ctx, _ = _mock_db_session()
            mock_db.session.return_value = mock_ctx

            user = MagicMock()
            user.id = 1
            user.name = "Test"
            user.subscription_tier = "pro"
            mock_get_user.return_value = user
            mock_gen.side_effect = RuntimeError("recap engine down")

            resp = test_client.post("/recaps/weekly/generate")
            assert resp.status_code == 500
        finally:
            _clear_overrides()


# =============================================================================
# ENGAGEMENT ROUTES
# =============================================================================


def _mock_engagement_metrics():
    m = MagicMock()
    m.sessions.active_count = 5
    m.sessions.avg_duration_minutes = 12.5
    m.sessions.by_platform = {"ios": 3, "android": 2}
    m.sessions.total = 5
    m.queries.total_queries = 42
    m.queries.avg_queries_per_day = 6.0
    m.queries.by_date = {}
    m.queries.popular_sports = {"nba": 20}
    m.queries.popular_decision_types = {}
    m.queries.popular_risk_modes = {}
    m.retention.new_users = 2
    m.retention.returning_users = 3
    m.retention.dau = 4
    m.retention.wau = 5
    m.retention.mau = 10
    m.features.local_routing_count = 10
    m.features.local_routing_pct = 25.0
    m.features.claude_routing_count = 30
    m.features.claude_routing_pct = 75.0
    m.features.cache_hits = 5
    m.features.cache_misses = 35
    m.features.cache_hit_rate = 12.5
    m.depth.avg_queries_per_session = 8.4
    m.depth.avg_queries_per_user_per_day = 5.0
    m.depth.active_users = 4
    m.depth.active_sessions = 5
    return m


class TestEngagement:
    @patch("api.main.update_engagement_metrics")
    @patch("api.main.engagement_tracker.compute_metrics")
    @patch("api.main.db_service")
    def test_period_today(self, mock_db, mock_compute, mock_update, test_client):
        mock_db.is_configured = True
        mock_ctx, mock_session = _mock_db_session()
        mock_db.session.return_value = mock_ctx

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_compute.return_value = _mock_engagement_metrics()

        resp = test_client.get("/engagement?period=today")
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == "today"
        assert "sessions" in data

    @patch("api.main.update_engagement_metrics")
    @patch("api.main.engagement_tracker.compute_metrics")
    @patch("api.main.db_service")
    def test_period_week(self, mock_db, mock_compute, mock_update, test_client):
        mock_db.is_configured = True
        mock_ctx, mock_session = _mock_db_session()
        mock_db.session.return_value = mock_ctx

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_compute.return_value = _mock_engagement_metrics()

        resp = test_client.get("/engagement?period=week")
        assert resp.status_code == 200
        assert resp.json()["period"] == "week"

    @patch("api.main.db_service")
    def test_db_not_configured(self, mock_db, test_client):
        mock_db.is_configured = False
        resp = test_client.get("/engagement")
        assert resp.status_code == 200
        assert resp.json() == {"error": "Database not configured"}

    @patch("api.main.db_service")
    def test_exception(self, mock_db, test_client):
        mock_db.is_configured = True
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db fail"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_db.session.return_value = mock_ctx

        resp = test_client.get("/engagement")
        assert resp.status_code == 200
        assert "error" in resp.json()


# =============================================================================
# CRON SYNC
# =============================================================================


class TestCronSync:
    def setup_method(self):
        _override_admin()

    def teardown_method(self):
        _clear_overrides()

    @patch("api.main.redis_service")
    @patch("api.main.db_service")
    def test_db_not_configured(self, mock_db, mock_redis, test_client):
        mock_db.is_configured = False
        mock_redis.is_connected = False
        resp = test_client.post("/cron/sync")
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"]["outcomes"]["status"] == "skipped"
        assert data["results"]["rankings"]["status"] == "skipped"

    @patch("api.main.redis_service")
    @patch("api.main.db_service")
    def test_outcome_sync_success(self, mock_db, mock_redis, test_client):
        mock_db.is_configured = True
        mock_redis.is_connected = False
        with patch(
            "services.outcome_recorder.sync_recent_outcomes",
            new_callable=AsyncMock,
            return_value={"total_decisions_processed": 5, "total_outcomes_recorded": 2},
        ):
            resp = test_client.post("/cron/sync")
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"]["outcomes"]["total_outcomes_recorded"] == 2

    @patch("api.main.redis_service")
    @patch("api.main.db_service")
    def test_outcome_sync_returns_none(self, mock_db, mock_redis, test_client):
        mock_db.is_configured = True
        mock_redis.is_connected = False
        with patch(
            "services.outcome_recorder.sync_recent_outcomes",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = test_client.post("/cron/sync")
        assert resp.status_code == 200
        assert resp.json()["results"]["outcomes"]["status"] == "no_results"

    @patch("api.main.redis_service")
    @patch("api.main.db_service")
    def test_outcome_sync_error(self, mock_db, mock_redis, test_client):
        mock_db.is_configured = True
        mock_redis.is_connected = False
        with patch(
            "services.outcome_recorder.sync_recent_outcomes",
            new_callable=AsyncMock,
            side_effect=RuntimeError("ESPN down"),
        ):
            resp = test_client.post("/cron/sync")
        assert resp.status_code == 200
        assert "error" in resp.json()["results"]["outcomes"]

    @patch("api.main.redis_service")
    @patch("api.main.db_service")
    def test_rankings_sync_success(self, mock_db, mock_redis, test_client):
        mock_db.is_configured = True
        mock_redis.is_connected = True
        with patch(
            "services.outcome_recorder.sync_recent_outcomes",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.rankings_scheduler.rankings_scheduler._run_rankings",
            new_callable=AsyncMock,
        ):
            resp = test_client.post("/cron/sync")
        assert resp.status_code == 200
        assert resp.json()["results"]["rankings"]["status"] == "completed"

    @patch("api.main.redis_service")
    @patch("api.main.db_service")
    def test_rankings_sync_error(self, mock_db, mock_redis, test_client):
        mock_db.is_configured = True
        mock_redis.is_connected = True
        with patch(
            "services.outcome_recorder.sync_recent_outcomes",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.rankings_scheduler.rankings_scheduler._run_rankings",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Rankings fail"),
        ):
            resp = test_client.post("/cron/sync")
        assert resp.status_code == 200
        assert "error" in resp.json()["results"]["rankings"]
