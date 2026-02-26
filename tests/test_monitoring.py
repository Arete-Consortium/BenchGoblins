"""Tests for the monitoring module (Prometheus metrics, middleware, decorators)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import Response

from monitoring import (
    MetricsMiddleware,
    metrics_endpoint,
    normalize_path,
    track_cache_operation,
    track_claude_request,
    track_database_operation,
    track_decision,
    track_external_api,
    track_subscription_event,
    update_active_users,
    update_engagement_metrics,
)


# ---------------------------------------------------------------------------
# normalize_path
# ---------------------------------------------------------------------------


class TestNormalizePath:
    def test_replaces_uuid(self):
        path = "/users/550e8400-e29b-41d4-a716-446655440000/profile"
        assert normalize_path(path) == "/users/{id}/profile"

    def test_replaces_numeric_id(self):
        assert normalize_path("/players/12345") == "/players/{id}"

    def test_replaces_numeric_id_mid_path(self):
        assert normalize_path("/teams/99/roster") == "/teams/{id}/roster"

    def test_replaces_team_key(self):
        assert normalize_path("/fantasy/449.l.123456.t.1") == "/fantasy/{team_key}"

    def test_replaces_league_key(self):
        assert normalize_path("/leagues/449.l.123456") == "/leagues/{league_key}"

    def test_no_replacement_needed(self):
        assert normalize_path("/health") == "/health"


# ---------------------------------------------------------------------------
# MetricsMiddleware
# ---------------------------------------------------------------------------


class TestMetricsMiddleware:
    """Tests for MetricsMiddleware.dispatch."""

    async def _build_request(self, path: str, method: str = "GET") -> Request:
        """Build a minimal Starlette Request for testing."""
        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": b"",
            "headers": [],
            "root_path": "",
            "scheme": "http",
            "server": ("testserver", 80),
        }
        return Request(scope)

    async def test_dispatch_skips_metrics_endpoint(self):
        """GET /metrics passes through without recording request metrics."""
        middleware = MetricsMiddleware(app=AsyncMock())
        request = await self._build_request("/metrics")
        inner_response = Response(content="ok", status_code=200)
        call_next = AsyncMock(return_value=inner_response)

        response = await middleware.dispatch(request, call_next)

        call_next.assert_awaited_once_with(request)
        assert response is inner_response

    @patch("monitoring.REQUESTS_IN_PROGRESS")
    @patch("monitoring.REQUEST_LATENCY")
    @patch("monitoring.REQUEST_COUNT")
    async def test_dispatch_success_records_metrics(
        self, mock_count, mock_latency, mock_in_progress
    ):
        """Successful request records count, latency, and in-progress gauge."""
        middleware = MetricsMiddleware(app=AsyncMock())
        request = await self._build_request("/api/players/42", method="POST")
        inner_response = Response(content="created", status_code=201)
        call_next = AsyncMock(return_value=inner_response)

        response = await middleware.dispatch(request, call_next)

        assert response.status_code == 201
        # in-progress incremented then decremented
        mock_in_progress.labels.return_value.inc.assert_called()
        mock_in_progress.labels.return_value.dec.assert_called()
        # count and latency recorded
        mock_count.labels.assert_called_with(
            method="POST", endpoint="/api/players/{id}", status_code=201
        )
        mock_count.labels.return_value.inc.assert_called_once()
        mock_latency.labels.assert_called_with(
            method="POST", endpoint="/api/players/{id}"
        )
        mock_latency.labels.return_value.observe.assert_called_once()

    @patch("monitoring.REQUESTS_IN_PROGRESS")
    @patch("monitoring.REQUEST_LATENCY")
    @patch("monitoring.REQUEST_COUNT")
    async def test_dispatch_exception_sets_500_and_reraises(
        self, mock_count, mock_latency, mock_in_progress
    ):
        """When call_next raises, status_code defaults to 500 and exception propagates."""
        middleware = MetricsMiddleware(app=AsyncMock())
        request = await self._build_request("/api/boom")
        call_next = AsyncMock(side_effect=RuntimeError("server broke"))

        with pytest.raises(RuntimeError, match="server broke"):
            await middleware.dispatch(request, call_next)

        # Metrics still recorded in finally block with status 500
        mock_count.labels.assert_called_with(
            method="GET", endpoint="/api/boom", status_code=500
        )
        mock_count.labels.return_value.inc.assert_called_once()
        mock_latency.labels.return_value.observe.assert_called_once()
        mock_in_progress.labels.return_value.dec.assert_called()


# ---------------------------------------------------------------------------
# metrics_endpoint
# ---------------------------------------------------------------------------


class TestMetricsEndpoint:
    @patch("monitoring.generate_latest", return_value=b"# HELP fake metric\n")
    async def test_returns_prometheus_response(self, mock_gen):
        """metrics_endpoint returns a Response with generate_latest content."""
        request = MagicMock(spec=Request)
        response = await metrics_endpoint(request)

        assert isinstance(response, Response)
        assert response.body == b"# HELP fake metric\n"
        assert (
            "text/plain" in response.media_type or "openmetrics" in response.media_type
        )
        mock_gen.assert_called_once()


# ---------------------------------------------------------------------------
# track_decision decorator
# ---------------------------------------------------------------------------


class TestTrackDecision:
    @patch("monitoring.DECISION_LATENCY")
    @patch("monitoring.DECISION_REQUESTS")
    async def test_decorator_calls_function_and_records_metrics(
        self, mock_requests, mock_latency
    ):
        """Decorated async function executes, returns result, and records metrics."""

        @track_decision(
            sport="nba", query_type="start_sit", risk_mode="bold", routed_to="local"
        )
        async def my_decision(player_name: str) -> str:
            return f"start {player_name}"

        result = await my_decision("LeBron")

        assert result == "start LeBron"
        mock_requests.labels.assert_called_once_with(
            sport="nba", query_type="start_sit", risk_mode="bold"
        )
        mock_requests.labels.return_value.inc.assert_called_once()
        mock_latency.labels.assert_called_once_with(sport="nba", routed_to="local")
        mock_latency.labels.return_value.observe.assert_called_once()

    @patch("monitoring.DECISION_LATENCY")
    @patch("monitoring.DECISION_REQUESTS")
    async def test_decorator_records_latency_even_on_exception(
        self, mock_requests, mock_latency
    ):
        """Latency is observed in the finally block even if the function raises."""

        @track_decision(
            sport="nfl", query_type="waiver", risk_mode="safe", routed_to="claude"
        )
        async def failing_decision():
            raise ValueError("bad input")

        with pytest.raises(ValueError, match="bad input"):
            await failing_decision()

        mock_requests.labels.return_value.inc.assert_called_once()
        mock_latency.labels.return_value.observe.assert_called_once()

    @patch("monitoring.DECISION_LATENCY")
    @patch("monitoring.DECISION_REQUESTS")
    async def test_decorator_preserves_function_name(self, mock_requests, mock_latency):
        """@wraps preserves the original function's __name__."""

        @track_decision(
            sport="mlb", query_type="trade", risk_mode="median", routed_to="local"
        )
        async def original_name():
            return True

        assert original_name.__name__ == "original_name"


# ---------------------------------------------------------------------------
# track_external_api context manager
# ---------------------------------------------------------------------------


class TestTrackExternalApi:
    @patch("monitoring.EXTERNAL_API_LATENCY")
    @patch("monitoring.EXTERNAL_API_REQUESTS")
    async def test_success_path(self, mock_requests, mock_latency):
        """On success, labels status='success' and records latency."""
        async with track_external_api("espn"):
            pass  # simulate successful API call

        mock_requests.labels.assert_called_once_with(service="espn", status="success")
        mock_requests.labels.return_value.inc.assert_called_once()
        mock_latency.labels.assert_called_once_with(service="espn")
        mock_latency.labels.return_value.observe.assert_called_once()

    @patch("monitoring.EXTERNAL_API_LATENCY")
    @patch("monitoring.EXTERNAL_API_REQUESTS")
    async def test_error_path(self, mock_requests, mock_latency):
        """On exception, labels status='error', records latency, and re-raises."""
        with pytest.raises(ConnectionError, match="timeout"):
            async with track_external_api("yahoo"):
                raise ConnectionError("timeout")

        mock_requests.labels.assert_called_once_with(service="yahoo", status="error")
        mock_requests.labels.return_value.inc.assert_called_once()
        mock_latency.labels.assert_called_once_with(service="yahoo")
        mock_latency.labels.return_value.observe.assert_called_once()


# ---------------------------------------------------------------------------
# track_database_operation context manager
# ---------------------------------------------------------------------------


class TestTrackDatabaseOperation:
    @patch("monitoring.DATABASE_LATENCY")
    @patch("monitoring.DATABASE_OPERATIONS")
    async def test_success_path(self, mock_ops, mock_latency):
        """On success, labels status='success' and records latency."""
        async with track_database_operation("select", table="users"):
            pass  # simulate successful DB query

        mock_ops.labels.assert_called_once_with(
            operation="select", table="users", status="success"
        )
        mock_ops.labels.return_value.inc.assert_called_once()
        mock_latency.labels.assert_called_once_with(operation="select")
        mock_latency.labels.return_value.observe.assert_called_once()

    @patch("monitoring.DATABASE_LATENCY")
    @patch("monitoring.DATABASE_OPERATIONS")
    async def test_error_path(self, mock_ops, mock_latency):
        """On exception, labels status='error', records latency, and re-raises."""
        with pytest.raises(RuntimeError, match="deadlock"):
            async with track_database_operation("insert", table="decisions"):
                raise RuntimeError("deadlock")

        mock_ops.labels.assert_called_once_with(
            operation="insert", table="decisions", status="error"
        )
        mock_ops.labels.return_value.inc.assert_called_once()
        mock_latency.labels.assert_called_once_with(operation="insert")
        mock_latency.labels.return_value.observe.assert_called_once()

    @patch("monitoring.DATABASE_LATENCY")
    @patch("monitoring.DATABASE_OPERATIONS")
    async def test_default_table_is_unknown(self, mock_ops, mock_latency):
        """When table is not specified, defaults to 'unknown'."""
        async with track_database_operation("delete"):
            pass

        mock_ops.labels.assert_called_once_with(
            operation="delete", table="unknown", status="success"
        )


# ---------------------------------------------------------------------------
# track_claude_request
# ---------------------------------------------------------------------------


class TestTrackClaudeRequest:
    @patch("monitoring.CLAUDE_TOKENS")
    @patch("monitoring.CLAUDE_REQUESTS")
    def test_success_request(self, mock_requests, mock_tokens):
        track_claude_request(input_tokens=100, output_tokens=50, success=True)

        mock_requests.labels.assert_called_once_with(
            status="success", prompt_variant="control"
        )
        mock_requests.labels.return_value.inc.assert_called_once()
        token_calls = mock_tokens.labels.call_args_list
        assert len(token_calls) == 2
        mock_tokens.labels.assert_any_call(type="input")
        mock_tokens.labels.assert_any_call(type="output")

    @patch("monitoring.CLAUDE_TOKENS")
    @patch("monitoring.CLAUDE_REQUESTS")
    def test_error_request_with_variant(self, mock_requests, mock_tokens):
        track_claude_request(
            input_tokens=200, output_tokens=0, success=False, variant="v2"
        )

        mock_requests.labels.assert_called_once_with(
            status="error", prompt_variant="v2"
        )
        mock_requests.labels.return_value.inc.assert_called_once()


# ---------------------------------------------------------------------------
# track_cache_operation
# ---------------------------------------------------------------------------


class TestTrackCacheOperation:
    @patch("monitoring.CACHE_OPERATIONS")
    def test_cache_hit(self, mock_ops):
        track_cache_operation(operation="get", hit=True)

        mock_ops.labels.assert_called_once_with(operation="get", result="hit")
        mock_ops.labels.return_value.inc.assert_called_once()

    @patch("monitoring.CACHE_OPERATIONS")
    def test_cache_miss(self, mock_ops):
        track_cache_operation(operation="get", hit=False)

        mock_ops.labels.assert_called_once_with(operation="get", result="miss")
        mock_ops.labels.return_value.inc.assert_called_once()


# ---------------------------------------------------------------------------
# update_active_users
# ---------------------------------------------------------------------------


class TestUpdateActiveUsers:
    @patch("monitoring.ACTIVE_USERS")
    def test_sets_free_and_premium_gauges(self, mock_gauge):
        update_active_users(free_count=150, premium_count=42)

        calls = mock_gauge.labels.call_args_list
        assert len(calls) == 2
        mock_gauge.labels.assert_any_call(tier="free")
        mock_gauge.labels.assert_any_call(tier="premium")
        # .set() called with correct values — check via the mock chain
        set_calls = mock_gauge.labels.return_value.set.call_args_list
        assert set_calls[0].args == (150,)
        assert set_calls[1].args == (42,)


# ---------------------------------------------------------------------------
# track_subscription_event
# ---------------------------------------------------------------------------


class TestTrackSubscriptionEvent:
    @patch("monitoring.SUBSCRIPTION_EVENTS")
    def test_increments_counter_with_event_type(self, mock_counter):
        track_subscription_event("cancelled")

        mock_counter.labels.assert_called_once_with(event_type="cancelled")
        mock_counter.labels.return_value.inc.assert_called_once()

    @patch("monitoring.SUBSCRIPTION_EVENTS")
    def test_different_event_types(self, mock_counter):
        for event_type in ("started", "renewed", "expired"):
            mock_counter.reset_mock()
            track_subscription_event(event_type)
            mock_counter.labels.assert_called_once_with(event_type=event_type)


# ---------------------------------------------------------------------------
# update_engagement_metrics
# ---------------------------------------------------------------------------


class TestUpdateEngagementMetrics:
    @patch("monitoring.ENGAGEMENT_LOCAL_ROUTING_PCT")
    @patch("monitoring.ENGAGEMENT_QUERIES_PER_DAY")
    @patch("monitoring.ENGAGEMENT_MAU")
    @patch("monitoring.ENGAGEMENT_WAU")
    @patch("monitoring.ENGAGEMENT_DAU")
    def test_sets_all_engagement_gauges(
        self, mock_dau, mock_wau, mock_mau, mock_qpd, mock_lrp
    ):
        """All five engagement gauges are set from the nested metrics object."""
        retention = MagicMock()
        retention.dau = 500
        retention.wau = 2000
        retention.mau = 8000

        queries = MagicMock()
        queries.avg_queries_per_day = 3.5

        features = MagicMock()
        features.local_routing_pct = 72.1

        metrics = MagicMock()
        metrics.retention = retention
        metrics.queries = queries
        metrics.features = features

        update_engagement_metrics(metrics)

        mock_dau.set.assert_called_once_with(500)
        mock_wau.set.assert_called_once_with(2000)
        mock_mau.set.assert_called_once_with(8000)
        mock_qpd.set.assert_called_once_with(3.5)
        mock_lrp.set.assert_called_once_with(72.1)
