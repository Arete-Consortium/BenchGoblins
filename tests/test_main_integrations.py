"""Tests for integration endpoints and misc routes in api.main.

Covers Yahoo integration, WebSocket, accuracy sport filter, billing edge cases,
weekly recap league-pro exception, unhandled exception handler, engagement sport
filter, webhook validators, and the __main__ block.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# ---- helpers ---------------------------------------------------------------


def _mock_db_session():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_session


def _override_user(user_id=1, email="test@example.com"):
    from api.main import app
    from routes.auth import get_current_user, require_pro

    user = {"user_id": user_id, "email": email}
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_pro] = lambda: user


def _clear_overrides():
    from api.main import app

    app.dependency_overrides.clear()


def _mock_resolve_session(mock_db=None, mock_session_obj=None):
    """Return a mock that replaces ``_resolve_session`` async context manager."""
    if mock_db is None:
        mock_db = AsyncMock()
    if mock_session_obj is None:
        mock_session_obj = MagicMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=(mock_db, mock_session_obj))
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx


# =============================================================================
# GROUP 1: Yahoo Integration Routes
# =============================================================================


class TestYahooCallbackTokensNone:
    """POST /integrations/yahoo/token — tokens is None → 400."""

    @patch("api.main._resolve_session")
    @patch("api.main.yahoo_service.exchange_code", new_callable=AsyncMock)
    def test_exchange_code_returns_none(self, mock_exchange, mock_resolve, test_client):
        mock_exchange.return_value = None
        # _resolve_session won't be reached because we bail before it
        resp = test_client.post(
            "/integrations/yahoo/token",
            json={"code": "badcode", "redirect_uri": "https://app.com/cb"},
        )
        assert resp.status_code == 400
        assert "Failed to exchange" in resp.json()["detail"]


class TestYahooRefreshFailed:
    """POST /integrations/yahoo/refresh — refresh returns None → 401."""

    @patch("api.main._resolve_session")
    @patch("api.main.yahoo_service.refresh_token", new_callable=AsyncMock)
    @patch("api.main.session_service.get_credential", new_callable=AsyncMock)
    def test_refresh_returns_none(
        self, mock_get_cred, mock_refresh, mock_resolve, test_client
    ):
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_session_obj = MagicMock()
        mock_resolve.return_value = _mock_resolve_session(mock_db, mock_session_obj)

        mock_get_cred.return_value = {
            "access_token": "old",
            "refresh_token": "rt_old",
        }
        mock_refresh.return_value = None

        resp = test_client.post("/integrations/yahoo/refresh")
        assert resp.status_code == 401
        assert "Failed to refresh" in resp.json()["detail"]


class TestYahooGetTokenExpiredRefreshFails:
    """_get_yahoo_token — token expired, refresh returns None → 401."""

    async def test_expired_token_refresh_fails(self):
        import time

        from api.main import _get_yahoo_token

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_session_obj = MagicMock()
        resolve_ctx = _mock_resolve_session(mock_db, mock_session_obj)

        stored_creds = {
            "access_token": "expired_tok",
            "refresh_token": "rt_val",
            "expires_at": time.time() - 100,  # expired
        }

        with (
            patch("api.main._resolve_session", return_value=resolve_ctx),
            patch(
                "api.main.session_service.get_credential",
                new_callable=AsyncMock,
                return_value=stored_creds,
            ),
            patch(
                "api.main.yahoo_service.refresh_token",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await _get_yahoo_token("default")
            assert exc_info.value.status_code == 401
            assert "refresh" in exc_info.value.detail.lower()


class TestYahooLeagues:
    """GET /integrations/yahoo/leagues — success path."""

    @patch("api.main._get_yahoo_token", new_callable=AsyncMock)
    @patch("api.main.yahoo_service.get_user_leagues", new_callable=AsyncMock)
    def test_returns_leagues(self, mock_leagues, mock_token, test_client):
        mock_token.return_value = "valid_tok"
        league = MagicMock()
        league.league_key = "lk1"
        league.league_id = "lid1"
        league.name = "My League"
        league.sport = "nba"
        league.season = "2025"
        league.num_teams = 12
        league.scoring_type = "head"
        mock_leagues.return_value = [league]

        resp = test_client.get("/integrations/yahoo/leagues")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["league_key"] == "lk1"
        assert data[0]["sport"] == "nba"


class TestYahooTeams:
    """GET /integrations/yahoo/teams — success path."""

    @patch("api.main._get_yahoo_token", new_callable=AsyncMock)
    @patch("api.main.yahoo_service.get_user_teams", new_callable=AsyncMock)
    def test_returns_teams(self, mock_teams, mock_token, test_client):
        mock_token.return_value = "valid_tok"
        team = MagicMock()
        team.team_key = "tk1"
        team.team_id = "tid1"
        team.name = "My Team"
        team.logo_url = "https://img.png"
        mock_teams.return_value = [team]

        resp = test_client.get("/integrations/yahoo/teams")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["team_key"] == "tk1"


class TestYahooRoster:
    """GET /integrations/yahoo/roster/{team_key} — success path."""

    @patch("api.main._get_yahoo_token", new_callable=AsyncMock)
    @patch("api.main.yahoo_service.get_team_roster", new_callable=AsyncMock)
    def test_returns_roster(self, mock_roster, mock_token, test_client):
        mock_token.return_value = "valid_tok"
        player = MagicMock()
        player.player_key = "pk1"
        player.player_id = "pid1"
        player.name = "Player One"
        player.team_abbrev = "LAL"
        player.position = "PG"
        player.status = "Active"
        player.injury_status = None
        mock_roster.return_value = [player]

        resp = test_client.get("/integrations/yahoo/roster/tk1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["player_key"] == "pk1"
        assert data[0]["name"] == "Player One"


class TestYahooStandings:
    """GET /integrations/yahoo/standings/{league_key} — success path."""

    @patch("api.main._get_yahoo_token", new_callable=AsyncMock)
    @patch("api.main.yahoo_service.get_league_standings", new_callable=AsyncMock)
    def test_returns_standings(self, mock_standings, mock_token, test_client):
        mock_token.return_value = "valid_tok"
        mock_standings.return_value = [{"rank": 1, "team": "Eagles"}]

        resp = test_client.get("/integrations/yahoo/standings/lk1")
        assert resp.status_code == 200
        data = resp.json()
        assert "standings" in data
        assert len(data["standings"]) == 1


# =============================================================================
# GROUP 2: WebSocket Endpoint
# =============================================================================


class TestWebSocketEndpoint:
    """WS /ws — connect, receive, disconnect."""

    @patch("api.main.connection_manager.disconnect", new_callable=AsyncMock)
    @patch("api.main.connection_manager.handle_message", new_callable=AsyncMock)
    def test_websocket_lifecycle(self, mock_handle, mock_disconnect, test_client):
        # Let the real connect() run so websocket.accept() is called,
        # but mock handle_message and disconnect to verify the flow.
        with test_client.websocket_connect("/ws") as ws:
            ws.send_text('{"type": "ping"}')
        # After the block exits, the client disconnects triggering
        # the WebSocketDisconnect exception path.
        mock_disconnect.assert_called_once()


# =============================================================================
# GROUP 3: Accuracy Metrics — sport filter & exception path
# =============================================================================


class TestAccuracyMetricsSportFilter:
    """GET /accuracy/metrics?sport=nba — line 3383."""

    @patch("api.main.accuracy_tracker.compute_metrics")
    @patch("api.main.db_service")
    def test_sport_filter_applied(self, mock_db, mock_compute, test_client):
        mock_db.is_configured = True
        mock_ctx, mock_session = _mock_db_session()
        mock_db.session.return_value = mock_ctx

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

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

        resp = test_client.get("/accuracy/metrics?sport=nba")
        assert resp.status_code == 200
        # The sport filter is applied on the query; we just ensure it doesn't crash
        mock_session.execute.assert_called_once()


class TestAccuracyMetricsException:
    """GET /accuracy/metrics — DB exception → decisions = [] (lines 3404-3405)."""

    @patch("api.main.accuracy_tracker.compute_metrics")
    @patch("api.main.db_service")
    def test_db_exception_falls_back(self, mock_db, mock_compute, test_client):
        mock_db.is_configured = True
        # Make the session context manager raise
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db fail"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_db.session.return_value = mock_ctx

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
        # compute_metrics was called with empty list (fallback)
        mock_compute.assert_called_once_with([])


# =============================================================================
# GROUP 4: Billing Edge Cases
# =============================================================================


class TestCheckoutWithLeagueId:
    """POST /billing/create-checkout with league_id → extra_metadata (line 3853)."""

    @patch("api.main.stripe_billing")
    def test_league_id_sets_extra_metadata(self, mock_stripe, test_client):
        _override_user()
        try:
            mock_stripe.is_configured.return_value = True
            mock_stripe.create_checkout_session = AsyncMock(
                return_value="https://checkout.stripe.com/sess"
            )
            resp = test_client.post(
                "/billing/create-checkout",
                json={
                    "price_id": "price_123",
                    "success_url": "https://app.com/ok",
                    "cancel_url": "https://app.com/cancel",
                    "league_id": 42,
                },
            )
            assert resp.status_code == 200
            # Verify extra_metadata was passed
            call_kwargs = mock_stripe.create_checkout_session.call_args
            assert call_kwargs.kwargs["extra_metadata"]["league_id"] == "42"
            assert call_kwargs.kwargs["extra_metadata"]["plan_type"] == "pro_league"
        finally:
            _clear_overrides()


class TestPortalSessionException:
    """POST /billing/create-portal — create_portal_session raises → 500."""

    @patch("api.main._get_user_by_id", new_callable=AsyncMock)
    @patch("api.main.stripe_billing")
    def test_portal_exception(self, mock_stripe, mock_get_user, test_client):
        _override_user()
        try:
            mock_stripe.is_configured.return_value = True
            mock_stripe.create_portal_session = AsyncMock(
                side_effect=RuntimeError("Stripe down")
            )
            user = MagicMock()
            user.stripe_customer_id = "cus_123"
            mock_get_user.return_value = user

            resp = test_client.post(
                "/billing/create-portal",
                json={"return_url": "https://app.com/settings"},
            )
            assert resp.status_code == 500
            assert "Failed to create portal" in resp.json()["detail"]
        finally:
            _clear_overrides()


class TestBillingStatusTzNaiveResetAt:
    """GET /billing/status — tz-naive reset_at (line 3960-3961)."""

    @patch("api.main.stripe_billing")
    @patch("api.main._get_user_by_id", new_callable=AsyncMock)
    def test_tz_naive_reset_at_handled(self, mock_get_user, mock_stripe, test_client):
        _override_user()
        try:
            user = MagicMock()
            user.id = 1
            user.subscription_tier = "free"
            user.queries_today = 3
            # tz-naive datetime — should be handled without error
            user.queries_reset_at = datetime(2026, 2, 25, 0, 0, 0)  # noqa: DTZ001
            user.stripe_customer_id = None
            user.stripe_subscription_id = None
            mock_get_user.return_value = user
            mock_stripe.is_league_pro = AsyncMock(return_value=False)

            resp = test_client.get("/billing/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["tier"] == "free"
        finally:
            _clear_overrides()


class TestBillingStatusLeagueProException:
    """GET /billing/status — is_league_pro throws → is_pro stays False (line 3970-3971)."""

    @patch("api.main.stripe_billing")
    @patch("api.main._get_user_by_id", new_callable=AsyncMock)
    def test_league_pro_exception_swallowed(
        self, mock_get_user, mock_stripe, test_client
    ):
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
            mock_stripe.is_league_pro = AsyncMock(
                side_effect=RuntimeError("stripe err")
            )

            resp = test_client.get("/billing/status")
            assert resp.status_code == 200
            data = resp.json()
            # Should remain free because exception was swallowed
            assert data["tier"] == "free"
            assert data["weekly_limit"] == 5
        finally:
            _clear_overrides()


# =============================================================================
# GROUP 5: Weekly Recap — league pro exception
# =============================================================================


class TestGenerateRecapLeagueProException:
    """POST /recaps/weekly/generate — is_league_pro throws → is_pro False → 403."""

    def test_league_pro_exception_stays_false(self, test_client):
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
                mock_ctx, _ = _mock_db_session()
                mock_db.session.return_value = mock_ctx
                user = MagicMock()
                user.id = 1
                user.subscription_tier = "free"
                user.referral_pro_expires_at = None
                mock_get_user.return_value = user
                mock_league_pro.side_effect = RuntimeError("stripe broken")

                resp = test_client.post("/recaps/weekly/generate")
                assert resp.status_code == 403
                assert "Pro feature" in resp.json()["detail"]
        finally:
            _clear_overrides()


# =============================================================================
# GROUP 6: Unhandled Exception Handler
# =============================================================================


class TestUnhandledExceptionHandler:
    """Global exception handler — returns safe 500 (lines 274-275)."""

    def test_unhandled_exception_returns_500(self):
        """Trigger unhandled exception via a route that raises unexpectedly.

        We need raise_server_exceptions=False so the TestClient returns the
        response instead of raising the exception into the test.
        """
        from fastapi.testclient import TestClient

        from api.main import app

        # Register a temporary route that raises an unhandled exception
        @app.get("/test-unhandled-error")
        async def _raise_unhandled():
            raise RuntimeError("kaboom")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/test-unhandled-error")
        assert resp.status_code == 500
        assert resp.json()["detail"] == "Internal server error"


# =============================================================================
# GROUP 7: Engagement Analytics — sport filter
# =============================================================================


class TestEngagementSportFilter:
    """GET /engagement?sport=nba — line 3649."""

    @patch("api.main.update_engagement_metrics")
    @patch("api.main.engagement_tracker.compute_metrics")
    @patch("api.main.db_service")
    def test_sport_filter_applied(
        self, mock_db, mock_compute, mock_update, test_client
    ):
        mock_db.is_configured = True
        mock_ctx, mock_session = _mock_db_session()
        mock_db.session.return_value = mock_ctx

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        m = MagicMock()
        m.sessions.active_count = 0
        m.sessions.avg_duration_minutes = 0
        m.sessions.by_platform = {}
        m.sessions.total = 0
        m.queries.total_queries = 0
        m.queries.avg_queries_per_day = 0
        m.queries.by_date = {}
        m.queries.popular_sports = {}
        m.queries.popular_decision_types = {}
        m.queries.popular_risk_modes = {}
        m.retention.new_users = 0
        m.retention.returning_users = 0
        m.retention.dau = 0
        m.retention.wau = 0
        m.retention.mau = 0
        m.features.local_routing_count = 0
        m.features.local_routing_pct = 0
        m.features.claude_routing_count = 0
        m.features.claude_routing_pct = 0
        m.features.cache_hits = 0
        m.features.cache_misses = 0
        m.features.cache_hit_rate = 0
        m.depth.avg_queries_per_session = 0
        m.depth.avg_queries_per_user_per_day = 0
        m.depth.active_users = 0
        m.depth.active_sessions = 0
        mock_compute.return_value = m

        resp = test_client.get("/engagement?period=month&sport=nba")
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == "month"


# =============================================================================
# GROUP 8: __main__ block
# =============================================================================


class TestMainBlock:
    """if __name__ == '__main__' — line 4131-4133."""

    @patch("uvicorn.run")
    def test_main_block(self, mock_run):
        import runpy

        runpy.run_module("api.main", run_name="__main__")
        mock_run.assert_called_once()


# =============================================================================
# GROUP 9: Webhook Validators on Models
# =============================================================================


class TestBudgetConfigRequestValidator:
    """BudgetConfigRequest.check_webhook_url — line 2160."""

    def test_valid_url_passes(self):
        from api.main import BudgetConfigRequest

        req = BudgetConfigRequest(
            monthly_limit_usd=100.0,
            slack_webhook_url="https://hooks.slack.com/services/abc",
        )
        assert req.slack_webhook_url == "https://hooks.slack.com/services/abc"

    def test_none_url_passes(self):
        from api.main import BudgetConfigRequest

        req = BudgetConfigRequest(monthly_limit_usd=50.0)
        assert req.slack_webhook_url is None
        assert req.discord_webhook_url is None

    def test_invalid_url_rejected(self):
        from pydantic import ValidationError

        from api.main import BudgetConfigRequest

        with pytest.raises(ValidationError, match="localhost"):
            BudgetConfigRequest(
                monthly_limit_usd=100.0,
                slack_webhook_url="https://localhost/hook",
            )


class TestWebhookTestRequestValidator:
    """WebhookTestRequest.check_webhook_url — line 2387 (required URL)."""

    def test_valid_url_passes(self):
        from api.main import WebhookTestRequest

        req = WebhookTestRequest(
            webhook_type="slack",
            webhook_url="https://hooks.slack.com/services/abc",
        )
        assert req.webhook_url == "https://hooks.slack.com/services/abc"

    def test_invalid_url_rejected(self):
        from pydantic import ValidationError

        from api.main import WebhookTestRequest

        with pytest.raises(ValidationError, match="localhost"):
            WebhookTestRequest(
                webhook_type="slack",
                webhook_url="https://localhost/hook",
            )
