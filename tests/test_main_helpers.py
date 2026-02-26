"""Tests for helper functions and utility routes in api.main."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_db_session():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_session


def _admin_overrides():
    from api.main import app
    from routes.auth import require_admin_key

    app.dependency_overrides[require_admin_key] = lambda: "admin"


def _clear_overrides():
    from api.main import app

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 1. _validate_production_env
# ---------------------------------------------------------------------------


class TestValidateProductionEnv:
    def test_missing_vars_raises(self):
        from api.main import _validate_production_env

        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(
                RuntimeError, match="Missing required environment variables"
            ):
                _validate_production_env()

    def test_all_vars_present_passes(self):
        from api.main import _validate_production_env

        env = {
            "ADMIN_API_KEY": "k",
            "ANTHROPIC_API_KEY": "k",
            "DATABASE_URL": "k",
            "JWT_SECRET_KEY": "k",
            "SESSION_ENCRYPTION_KEY": "k",
        }
        with patch.dict("os.environ", env, clear=True):
            _validate_production_env()

    def test_partial_missing_lists_only_missing(self):
        from api.main import _validate_production_env

        env = {"ADMIN_API_KEY": "k", "ANTHROPIC_API_KEY": "k"}
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(RuntimeError, match="DATABASE_URL"):
                _validate_production_env()


# ---------------------------------------------------------------------------
# 2. _validate_webhook_url
# ---------------------------------------------------------------------------


class TestValidateWebhookUrl:
    def test_none_returns_none(self):
        from api.main import _validate_webhook_url

        assert _validate_webhook_url(None) is None

    def test_valid_https_url(self):
        from api.main import _validate_webhook_url

        url = "https://hooks.slack.com/services/abc"
        assert _validate_webhook_url(url) == url

    def test_valid_http_url(self):
        from api.main import _validate_webhook_url

        url = "http://example.com/webhook"
        assert _validate_webhook_url(url) == url

    def test_localhost_rejected(self):
        from api.main import _validate_webhook_url

        with pytest.raises(ValueError, match="localhost"):
            _validate_webhook_url("https://localhost/hook")

    def test_loopback_ip_rejected(self):
        from api.main import _validate_webhook_url

        with pytest.raises(ValueError, match="localhost"):
            _validate_webhook_url("https://127.0.0.1/hook")

    def test_private_ip_rejected(self):
        from api.main import _validate_webhook_url

        with pytest.raises(ValueError, match="private"):
            _validate_webhook_url("https://192.168.1.1/hook")

    def test_non_http_scheme_rejected(self):
        from api.main import _validate_webhook_url

        with pytest.raises(ValueError, match="http:// or https://"):
            _validate_webhook_url("ftp://example.com/hook")

    def test_missing_hostname_rejected(self):
        from api.main import _validate_webhook_url

        with pytest.raises(ValueError, match="valid hostname"):
            _validate_webhook_url("https:///path")

    def test_too_long_url_rejected(self):
        from api.main import _validate_webhook_url

        url = "https://example.com/" + "a" * 2000
        with pytest.raises(ValueError, match="too long"):
            _validate_webhook_url(url)

    def test_domain_name_accepted(self):
        from api.main import _validate_webhook_url

        url = "https://hooks.slack.com/services/T00/B00/xxx"
        assert _validate_webhook_url(url) == url


# ---------------------------------------------------------------------------
# 3. _get_user_by_id
# ---------------------------------------------------------------------------


class TestGetUserById:
    @pytest.mark.asyncio
    async def test_db_not_configured_returns_none(self):
        from api.main import _get_user_by_id

        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = False
            result = await _get_user_by_id(1)
            assert result is None

    @pytest.mark.asyncio
    async def test_success_returns_user(self):
        from api.main import _get_user_by_id

        mock_ctx, mock_session = _mock_db_session()
        mock_user = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx
            result = await _get_user_by_id(1)
            assert result is mock_user


# ---------------------------------------------------------------------------
# 4. _store_decision
# ---------------------------------------------------------------------------


class TestStoreDecision:
    def _make_request_response(self):
        from api.main import Confidence, DecisionRequest, DecisionResponse

        req = DecisionRequest(
            sport="nba",
            risk_mode="median",
            decision_type="start_sit",
            query="Start Player A or B?",
        )
        resp = DecisionResponse(
            decision="Start Player A",
            confidence=Confidence.HIGH,
            rationale="Better matchup",
            details={
                "player_a": {"score": 80},
                "player_b": {"score": 70},
                "margin": 10,
            },
            source="local",
        )
        return req, resp

    @pytest.mark.asyncio
    async def test_db_not_configured_returns_early(self):
        from api.main import _store_decision

        req, resp = self._make_request_response()
        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = False
            await _store_decision(req, resp)
            mock_db.session.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_stores_decision(self):
        from api.main import _store_decision

        req, resp = self._make_request_response()
        mock_ctx, mock_session = _mock_db_session()

        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx
            await _store_decision(req, resp, player_a_name="A", player_b_name="B")
            mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_logged(self):
        from api.main import _store_decision

        req, resp = self._make_request_response()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db boom"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.logger") as mock_logger,
        ):
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx
            await _store_decision(req, resp)
            mock_logger.error.assert_called_once()


# ---------------------------------------------------------------------------
# 5. _claude_decision
# ---------------------------------------------------------------------------


class TestClaudeDecision:
    @pytest.mark.asyncio
    async def test_claude_unavailable_raises_503(self):
        from fastapi import HTTPException

        from api.main import _claude_decision

        req = MagicMock()
        with patch("api.main.claude_service") as mock_cs:
            mock_cs.is_available = False
            with pytest.raises(HTTPException) as exc_info:
                await _claude_decision(req, "A", "B", None)
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_success_returns_response(self):
        from api.main import Confidence, DecisionRequest, _claude_decision

        req = DecisionRequest(
            sport="nba",
            risk_mode="median",
            decision_type="start_sit",
            query="Start A or B?",
        )

        with patch("api.main.claude_service") as mock_cs:
            mock_cs.is_available = True
            mock_cs.make_decision = AsyncMock(
                return_value={
                    "decision": "Start A",
                    "confidence": "high",
                    "rationale": "Better stats",
                    "details": None,
                    "input_tokens": 100,
                    "output_tokens": 50,
                }
            )
            resp, inp, out = await _claude_decision(req, "A", "B", None)
            assert resp.decision == "Start A"
            assert resp.confidence == Confidence.HIGH
            assert resp.source == "claude"
            assert inp == 100
            assert out == 50

    @pytest.mark.asyncio
    async def test_exception_raises_500(self):
        from fastapi import HTTPException

        from api.main import _claude_decision

        req = MagicMock()
        req.query = "test"
        req.sport.value = "nba"
        req.risk_mode.value = "median"
        req.decision_type.value = "start_sit"
        req.league_type = None

        with patch("api.main.claude_service") as mock_cs:
            mock_cs.is_available = True
            mock_cs.make_decision = AsyncMock(side_effect=ValueError("API down"))
            with pytest.raises(HTTPException) as exc_info:
                await _claude_decision(req, "A", "B", None)
            assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# 6. _store_draft_decision
# ---------------------------------------------------------------------------


class TestStoreDraftDecision:
    def _make_draft_request_response(self):
        from api.main import Confidence, DraftRequest, DraftResponse

        req = DraftRequest(
            sport="nba",
            risk_mode="median",
            query="Draft A or B?",
        )
        resp = DraftResponse(
            recommended_pick="Player A",
            confidence=Confidence.HIGH,
            rationale="Higher ceiling",
            details={
                "ranked_players": [
                    {"name": "Player A", "score": 90},
                    {"name": "Player B", "score": 80},
                ]
            },
            source="local",
        )
        return req, resp

    @pytest.mark.asyncio
    async def test_db_not_configured_returns_early(self):
        from api.main import _store_draft_decision

        req, resp = self._make_draft_request_response()
        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = False
            await _store_draft_decision(req, resp, ["Player A", "Player B"])
            mock_db.session.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_stores_decision(self):
        from api.main import _store_draft_decision

        req, resp = self._make_draft_request_response()
        mock_ctx, mock_session = _mock_db_session()

        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx
            await _store_draft_decision(req, resp, ["Player A", "Player B"])
            mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_logged(self):
        from api.main import _store_draft_decision

        req, resp = self._make_draft_request_response()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db boom"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.logger") as mock_logger,
        ):
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx
            await _store_draft_decision(req, resp, ["A", "B"])
            mock_logger.error.assert_called_once()


# ---------------------------------------------------------------------------
# 7. GET /cache/stats
# ---------------------------------------------------------------------------


class TestCacheStats:
    def test_returns_claude_and_redis_stats(self, test_client):
        with (
            patch("api.main.claude_service") as mock_cs,
            patch("api.main.redis_service") as mock_rs,
        ):
            mock_cs.get_cache_stats.return_value = {"hits": 5, "misses": 2}
            mock_rs.get_stats = AsyncMock(return_value={"keys": 10})

            resp = test_client.get("/cache/stats")
            assert resp.status_code == 200
            data = resp.json()
            assert data["claude_memory_cache"] == {"hits": 5, "misses": 2}
            assert data["redis_cache"] == {"keys": 10}


# ---------------------------------------------------------------------------
# 8. POST /cache/clear
# ---------------------------------------------------------------------------


class TestCacheClear:
    def setup_method(self):
        _admin_overrides()

    def teardown_method(self):
        _clear_overrides()

    def test_clears_caches_redis_connected(self, test_client):
        with (
            patch("api.main.claude_service") as mock_cs,
            patch("api.main.redis_service") as mock_rs,
        ):
            mock_rs.is_connected = True
            mock_rs.clear_all = AsyncMock()

            resp = test_client.post("/cache/clear")
            assert resp.status_code == 200
            assert resp.json()["status"] == "cleared"
            mock_cs.clear_cache.assert_called_once()
            mock_rs.clear_all.assert_awaited_once()

    def test_clears_caches_redis_disconnected(self, test_client):
        with (
            patch("api.main.claude_service") as mock_cs,
            patch("api.main.redis_service") as mock_rs,
        ):
            mock_rs.is_connected = False

            resp = test_client.post("/cache/clear")
            assert resp.status_code == 200
            mock_cs.clear_cache.assert_called_once()


# ---------------------------------------------------------------------------
# 9. POST /cache/invalidate/{sport}
# ---------------------------------------------------------------------------


class TestCacheInvalidate:
    def setup_method(self):
        _admin_overrides()

    def teardown_method(self):
        _clear_overrides()

    def test_redis_not_connected_skips(self, test_client):
        with patch("api.main.redis_service") as mock_rs:
            mock_rs.is_connected = False

            resp = test_client.post("/cache/invalidate/nba")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "skipped"
            assert data["keys_deleted"] == 0

    def test_invalidates_sport_caches(self, test_client):
        with patch("api.main.redis_service") as mock_rs:
            mock_rs.is_connected = True
            mock_rs.clear_pattern = AsyncMock(return_value=3)
            mock_rs.bump_stats_version = AsyncMock(return_value=2)

            resp = test_client.post("/cache/invalidate/nba")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "invalidated"
            assert data["sport"] == "nba"
            assert data["keys_deleted"] == 9  # 3 patterns * 3 each
            assert data["stats_version"] == 2


# ---------------------------------------------------------------------------
# 10. GET /rate-limit/status
# ---------------------------------------------------------------------------


class TestRateLimitStatus:
    def test_returns_status(self, test_client):
        with patch("api.main.rate_limiter") as mock_rl:
            mock_rl.get_status = AsyncMock(
                return_value={"used": 3, "remaining": 7, "reset": "2026-01-01"}
            )

            resp = test_client.get("/rate-limit/status?session_id=abc")
            assert resp.status_code == 200
            data = resp.json()
            assert data["used"] == 3

    def test_anonymous_session_default(self, test_client):
        with patch("api.main.rate_limiter") as mock_rl:
            mock_rl.get_status = AsyncMock(return_value={"used": 0})

            resp = test_client.get("/rate-limit/status")
            assert resp.status_code == 200
            mock_rl.get_status.assert_awaited_once_with("anonymous")


# ---------------------------------------------------------------------------
# 11. GET /usage
# ---------------------------------------------------------------------------


class TestUsageEndpoint:
    def test_db_not_configured(self, test_client):
        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = False

            resp = test_client.get("/usage")
            assert resp.status_code == 200
            assert resp.json()["error"] == "Database not configured"

    def test_success_returns_usage(self, test_client):
        mock_ctx, mock_session = _mock_db_session()

        usage_row = MagicMock()
        usage_row.input = 1000
        usage_row.output = 500
        usage_row.total = 10
        usage_row.cache_hits = 2

        sport_row = MagicMock()
        sport_row.sport = "nba"
        sport_row.input = 800
        sport_row.output = 400
        sport_row.total = 8

        call_count = 0

        async def _execute_side_effect(_q):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                mock_result = MagicMock()
                mock_result.one.return_value = usage_row
                return mock_result
            else:
                mock_result = MagicMock()
                mock_result.all.return_value = [sport_row]
                return mock_result

        mock_session.execute = AsyncMock(side_effect=_execute_side_effect)

        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            resp = test_client.get("/usage")
            assert resp.status_code == 200
            data = resp.json()
            assert "today" in data
            assert "this_week" in data
            assert "this_month" in data
            assert "by_sport" in data
            assert data["today"]["total_decisions"] == 10

    def test_with_sport_filter(self, test_client):
        mock_ctx, mock_session = _mock_db_session()

        usage_row = MagicMock()
        usage_row.input = 500
        usage_row.output = 200
        usage_row.total = 5
        usage_row.cache_hits = 1

        mock_result = MagicMock()
        mock_result.one.return_value = usage_row
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            resp = test_client.get("/usage?sport=nba")
            assert resp.status_code == 200
            data = resp.json()
            assert "today" in data
            assert "by_sport" not in data

    def test_exception_returns_error(self, test_client):
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db fail"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            resp = test_client.get("/usage")
            assert resp.status_code == 200
            assert "error" in resp.json()


# ---------------------------------------------------------------------------
# 12. GET /budget — db not configured + exception paths
# ---------------------------------------------------------------------------


class TestGetBudget:
    def setup_method(self):
        _admin_overrides()

    def teardown_method(self):
        _clear_overrides()

    def test_db_not_configured_returns_503(self, test_client):
        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = False

            resp = test_client.get("/budget")
            assert resp.status_code == 503

    def test_exception_returns_500(self, test_client):
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db exploded"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            resp = test_client.get("/budget")
            assert resp.status_code == 500


# ---------------------------------------------------------------------------
# 13. PUT /budget
# ---------------------------------------------------------------------------


class TestSetBudget:
    def setup_method(self):
        _admin_overrides()

    def teardown_method(self):
        _clear_overrides()

    def test_db_not_configured_returns_503(self, test_client):
        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = False

            resp = test_client.put(
                "/budget",
                json={"monthly_limit_usd": 50.0},
            )
            assert resp.status_code == 503

    def test_update_existing_config(self, test_client):
        mock_ctx, mock_session = _mock_db_session()

        existing_config = MagicMock()
        existing_config.monthly_limit_usd = Decimal("25")
        existing_config.alert_threshold_pct = 80
        existing_config.alerts_enabled = True
        existing_config.slack_webhook_url = None
        existing_config.discord_webhook_url = None
        existing_config.updated_at = datetime.now(UTC)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_config
        mock_session.execute = AsyncMock(return_value=mock_result)

        # get_budget is called after set_budget; mock it to avoid a second DB trip
        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.get_budget", new_callable=AsyncMock) as mock_get,
        ):
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx
            mock_get.return_value = {
                "monthly_limit_usd": 50.0,
                "alert_threshold_pct": 80,
                "alerts_enabled": True,
                "slack_webhook_url": None,
                "discord_webhook_url": None,
                "current_month_spent_usd": 0,
                "percent_used": 0,
                "budget_exceeded": False,
                "alert_triggered": False,
                "updated_at": None,
            }

            resp = test_client.put(
                "/budget",
                json={"monthly_limit_usd": 50.0},
            )
            assert resp.status_code == 200

    def test_create_new_config(self, test_client):
        mock_ctx, mock_session = _mock_db_session()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.get_budget", new_callable=AsyncMock) as mock_get,
        ):
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx
            mock_get.return_value = {
                "monthly_limit_usd": 100.0,
                "alert_threshold_pct": 80,
                "alerts_enabled": True,
                "slack_webhook_url": None,
                "discord_webhook_url": None,
                "current_month_spent_usd": 0,
                "percent_used": 0,
                "budget_exceeded": False,
                "alert_triggered": False,
                "updated_at": None,
            }

            resp = test_client.put(
                "/budget",
                json={"monthly_limit_usd": 100.0},
            )
            assert resp.status_code == 200
            mock_session.add.assert_called_once()

    def test_exception_returns_500(self, test_client):
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("boom"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            resp = test_client.put(
                "/budget",
                json={"monthly_limit_usd": 50.0},
            )
            assert resp.status_code == 500


# ---------------------------------------------------------------------------
# 14. GET /budget/alerts
# ---------------------------------------------------------------------------


class TestBudgetAlerts:
    def setup_method(self):
        _admin_overrides()

    def teardown_method(self):
        _clear_overrides()

    def test_db_not_configured_returns_503(self, test_client):
        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = False

            resp = test_client.get("/budget/alerts")
            assert resp.status_code == 503

    def test_no_config_no_alert(self, test_client):
        mock_ctx, mock_session = _mock_db_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            resp = test_client.get("/budget/alerts")
            assert resp.status_code == 200
            data = resp.json()
            assert data["alert_active"] is False
            assert data["alert_type"] is None

    def test_budget_exceeded_alert(self, test_client):
        mock_ctx, mock_session = _mock_db_session()

        config = MagicMock()
        config.monthly_limit_usd = Decimal("1")
        config.alert_threshold_pct = 80
        config.alerts_enabled = True

        usage_row = MagicMock()
        usage_row.input = 1_000_000  # $3
        usage_row.output = 0

        call_count = 0

        async def _exec(_q):
            nonlocal call_count
            call_count += 1
            r = MagicMock()
            if call_count == 1:
                r.scalar_one_or_none.return_value = config
            else:
                r.one.return_value = usage_row
            return r

        mock_session.execute = AsyncMock(side_effect=_exec)

        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            resp = test_client.get("/budget/alerts")
            assert resp.status_code == 200
            data = resp.json()
            assert data["alert_active"] is True
            assert data["alert_type"] == "exceeded"

    def test_threshold_alert(self, test_client):
        mock_ctx, mock_session = _mock_db_session()

        config = MagicMock()
        config.monthly_limit_usd = Decimal("100")
        config.alert_threshold_pct = 80
        config.alerts_enabled = True

        # ~$27 spend = 27% of $100 would be below. Let's do 85%: need spend ~$85
        # input 28_333_333 tokens * $3/M = $85.00
        usage_row = MagicMock()
        usage_row.input = 28_333_333
        usage_row.output = 0

        call_count = 0

        async def _exec(_q):
            nonlocal call_count
            call_count += 1
            r = MagicMock()
            if call_count == 1:
                r.scalar_one_or_none.return_value = config
            else:
                r.one.return_value = usage_row
            return r

        mock_session.execute = AsyncMock(side_effect=_exec)

        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            resp = test_client.get("/budget/alerts")
            assert resp.status_code == 200
            data = resp.json()
            assert data["alert_active"] is True
            assert data["alert_type"] == "threshold"

    def test_no_alert_under_threshold(self, test_client):
        mock_ctx, mock_session = _mock_db_session()

        config = MagicMock()
        config.monthly_limit_usd = Decimal("100")
        config.alert_threshold_pct = 80
        config.alerts_enabled = True

        usage_row = MagicMock()
        usage_row.input = 1000
        usage_row.output = 0

        call_count = 0

        async def _exec(_q):
            nonlocal call_count
            call_count += 1
            r = MagicMock()
            if call_count == 1:
                r.scalar_one_or_none.return_value = config
            else:
                r.one.return_value = usage_row
            return r

        mock_session.execute = AsyncMock(side_effect=_exec)

        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            resp = test_client.get("/budget/alerts")
            assert resp.status_code == 200
            data = resp.json()
            assert data["alert_active"] is False
            assert data["alert_type"] is None

    def test_exception_returns_500(self, test_client):
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db fail"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            resp = test_client.get("/budget/alerts")
            assert resp.status_code == 500


# ---------------------------------------------------------------------------
# 15. POST /budget/webhooks/test
# ---------------------------------------------------------------------------


class TestBudgetWebhookTest:
    def setup_method(self):
        _admin_overrides()

    def teardown_method(self):
        _clear_overrides()

    def test_invalid_type_returns_400(self, test_client):
        resp = test_client.post(
            "/budget/webhooks/test",
            json={
                "webhook_type": "teams",
                "webhook_url": "https://hooks.example.com/abc",
            },
        )
        assert resp.status_code == 400

    def test_success(self, test_client):
        with patch("api.main.send_test_webhook", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True

            resp = test_client.post(
                "/budget/webhooks/test",
                json={
                    "webhook_type": "slack",
                    "webhook_url": "https://hooks.slack.com/services/T00/B00/xxx",
                },
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "success"

    def test_failure_returns_400(self, test_client):
        with patch("api.main.send_test_webhook", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = False

            resp = test_client.post(
                "/budget/webhooks/test",
                json={
                    "webhook_type": "discord",
                    "webhook_url": "https://discord.com/api/webhooks/123/abc",
                },
            )
            assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 16. GET /history
# ---------------------------------------------------------------------------


class TestHistoryEndpoint:
    def test_db_not_configured_returns_empty(self, test_client):
        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = False

            resp = test_client.get("/history")
            assert resp.status_code == 200
            assert resp.json() == []

    def test_success_returns_decisions(self, test_client):
        mock_ctx, mock_session = _mock_db_session()

        decision = MagicMock()
        decision.id = 1
        decision.sport = "nba"
        decision.risk_mode = "median"
        decision.decision_type = "start_sit"
        decision.query = "Start A or B?"
        decision.player_a_name = "Player A"
        decision.player_b_name = "Player B"
        decision.decision = "Start A"
        decision.confidence = "high"
        decision.rationale = "Better matchup"
        decision.source = "local"
        decision.score_a = 85.0
        decision.score_b = 72.0
        decision.margin = 13.0
        decision.created_at = datetime(2026, 1, 15, tzinfo=UTC)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [decision]
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            resp = test_client.get("/history?limit=10")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["sport"] == "nba"
            assert data[0]["decision"] == "Start A"

    def test_exception_returns_empty(self, test_client):
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db fail"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            resp = test_client.get("/history")
            assert resp.status_code == 200
            assert resp.json() == []


# ---------------------------------------------------------------------------
# 17. GET /experiments/results
# ---------------------------------------------------------------------------


class TestExperimentResults:
    def test_db_not_configured(self, test_client):
        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = False

            resp = test_client.get("/experiments/results")
            assert resp.status_code == 200
            assert resp.json()["error"] == "Database not configured"

    def test_success_returns_variants(self, test_client):
        mock_ctx, mock_session = _mock_db_session()

        variant_row = MagicMock()
        variant_row.prompt_variant = "control"
        variant_row.total = 10
        variant_row.input_tokens = 5000
        variant_row.output_tokens = 2000
        variant_row.cache_hits = 3

        conf_row = MagicMock()
        conf_row.prompt_variant = "control"
        conf_row.confidence = "high"
        conf_row.count = 7

        call_count = 0

        async def _exec(_q):
            nonlocal call_count
            call_count += 1
            r = MagicMock()
            if call_count == 1:
                r.all.return_value = [variant_row]
            else:
                r.all.return_value = [conf_row]
            return r

        mock_session.execute = AsyncMock(side_effect=_exec)

        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            resp = test_client.get("/experiments/results")
            assert resp.status_code == 200
            data = resp.json()
            assert "variants" in data
            assert "control" in data["variants"]
            assert data["variants"]["control"]["total_decisions"] == 10

    def test_exception_returns_error(self, test_client):
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db fail"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            resp = test_client.get("/experiments/results")
            assert resp.status_code == 200
            assert "error" in resp.json()


# ---------------------------------------------------------------------------
# 18. POST /experiments/end
# ---------------------------------------------------------------------------


class TestEndExperiment:
    def test_no_active_experiment_returns_404(self, test_client):
        with patch("api.main.experiment_registry") as mock_er:
            mock_er.end_experiment.return_value = None

            resp = test_client.post("/experiments/end")
            assert resp.status_code == 404

    def test_success_returns_ended(self, test_client):
        with patch("api.main.experiment_registry") as mock_er:
            ended = MagicMock()
            ended.name = "test_exp"
            ended.variants = {"control": 50, "variant_a": 50}
            ended.started_at = datetime(2026, 1, 1, tzinfo=UTC)
            ended.ended_at = datetime(2026, 1, 2, tzinfo=UTC)
            ended.duration_hours = 24.0
            mock_er.end_experiment.return_value = ended

            resp = test_client.post("/experiments/end")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ended"
            assert data["experiment"]["name"] == "test_exp"


# ---------------------------------------------------------------------------
# 19. GET /ws/stats
# ---------------------------------------------------------------------------


class TestWsStats:
    def test_returns_connection_stats(self, test_client):
        with patch("api.main.connection_manager") as mock_cm:
            mock_cm.get_stats.return_value = {
                "active_connections": 5,
                "total_connected": 42,
            }

            resp = test_client.get("/ws/stats")
            assert resp.status_code == 200
            data = resp.json()
            assert data["active_connections"] == 5
            assert data["total_connected"] == 42
