"""Tests for user engagement metrics."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.engagement import (
    EngagementDepthMetrics,
    EngagementTracker,
    FeatureUsageMetrics,
    QueryPatternMetrics,
    RetentionMetrics,
    SessionMetrics,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 2, 9, 12, 0, 0, tzinfo=timezone.utc)
_PERIOD_START = datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc)


def _make_decision(
    id="d1",
    user_id="1",
    session_id="s1",
    sport="nba",
    risk_mode="median",
    decision_type="start_sit",
    source="local",
    cache_hit=False,
    created_at=None,
):
    return {
        "id": id,
        "user_id": user_id,
        "session_id": session_id,
        "sport": sport,
        "risk_mode": risk_mode,
        "decision_type": decision_type,
        "source": source,
        "cache_hit": cache_hit,
        "created_at": created_at or _NOW,
    }


def _make_session(
    id="s1",
    platform="ios",
    status="active",
    created_at=None,
    last_active_at=None,
    user_id="1",
):
    return {
        "id": id,
        "session_id": id,
        "platform": platform,
        "status": status,
        "created_at": created_at or _NOW - timedelta(hours=1),
        "last_active_at": last_active_at or _NOW,
        "user_id": user_id,
    }


def _make_user(id="1", created_at=None):
    return {
        "id": id,
        "created_at": created_at or _PERIOD_START - timedelta(days=10),
    }


# ---------------------------------------------------------------------------
# SessionMetrics
# ---------------------------------------------------------------------------


class TestSessionMetrics:
    def test_defaults(self):
        m = SessionMetrics()
        assert m.active_count == 0
        assert m.avg_duration_minutes == 0.0
        assert m.total == 0

    def test_total_from_by_platform(self):
        m = SessionMetrics(by_platform={"ios": 3, "android": 2})
        assert m.total == 5

    def test_total_falls_back_to_active_count(self):
        m = SessionMetrics(active_count=7, by_platform={})
        assert m.total == 7


# ---------------------------------------------------------------------------
# QueryPatternMetrics
# ---------------------------------------------------------------------------


class TestQueryPatternMetrics:
    def test_defaults(self):
        m = QueryPatternMetrics()
        assert m.total_queries == 0
        assert m.avg_queries_per_day == 0.0

    def test_totals(self):
        m = QueryPatternMetrics(by_date={"2026-02-01": 10, "2026-02-02": 20})
        assert m.total_queries == 30
        assert m.avg_queries_per_day == 15.0

    def test_single_day(self):
        m = QueryPatternMetrics(by_date={"2026-02-09": 5})
        assert m.total_queries == 5
        assert m.avg_queries_per_day == 5.0


# ---------------------------------------------------------------------------
# FeatureUsageMetrics
# ---------------------------------------------------------------------------


class TestFeatureUsageMetrics:
    def test_defaults(self):
        m = FeatureUsageMetrics()
        assert m.local_routing_pct == 0.0
        assert m.claude_routing_pct == 0.0
        assert m.cache_hit_rate == 0.0

    def test_routing_pct(self):
        m = FeatureUsageMetrics(local_routing_count=7, claude_routing_count=3)
        assert m.local_routing_pct == 70.0
        assert m.claude_routing_pct == 30.0

    def test_cache_rate(self):
        m = FeatureUsageMetrics(cache_hits=3, cache_misses=7)
        assert m.cache_hit_rate == 30.0

    def test_all_local(self):
        m = FeatureUsageMetrics(local_routing_count=10, claude_routing_count=0)
        assert m.local_routing_pct == 100.0
        assert m.claude_routing_pct == 0.0

    def test_zero_division_safety(self):
        m = FeatureUsageMetrics()
        assert m.local_routing_pct == 0.0
        assert m.cache_hit_rate == 0.0


# ---------------------------------------------------------------------------
# RetentionMetrics
# ---------------------------------------------------------------------------


class TestRetentionMetrics:
    def test_defaults(self):
        m = RetentionMetrics()
        assert m.total_users == 0

    def test_total_users(self):
        m = RetentionMetrics(new_users=5, returning_users=10)
        assert m.total_users == 15


# ---------------------------------------------------------------------------
# EngagementDepthMetrics
# ---------------------------------------------------------------------------


class TestEngagementDepthMetrics:
    def test_defaults(self):
        m = EngagementDepthMetrics()
        assert m.avg_queries_per_session == 0.0
        assert m.avg_queries_per_user_per_day == 0.0
        assert m.active_users == 0
        assert m.active_sessions == 0


# ---------------------------------------------------------------------------
# EngagementTracker
# ---------------------------------------------------------------------------


class TestEngagementTracker:
    def test_empty_data(self):
        tracker = EngagementTracker()
        metrics = tracker.compute_metrics(
            decisions=[],
            sessions=[],
            users=[],
            period_start=_PERIOD_START,
            period_end=_NOW,
        )
        assert metrics.sessions.active_count == 0
        assert metrics.queries.total_queries == 0
        assert metrics.retention.new_users == 0
        assert metrics.features.local_routing_count == 0
        assert metrics.depth.active_users == 0

    def test_session_metrics(self):
        tracker = EngagementTracker()
        sessions = [
            _make_session("s1", platform="ios", status="active"),
            _make_session("s2", platform="android", status="active"),
            _make_session("s3", platform="ios", status="expired"),
        ]
        metrics = tracker.compute_metrics(
            decisions=[],
            sessions=sessions,
            users=[],
            period_start=_PERIOD_START,
            period_end=_NOW,
        )
        assert metrics.sessions.active_count == 2
        assert metrics.sessions.by_platform == {"ios": 2, "android": 1}
        assert metrics.sessions.avg_duration_minutes == 60.0

    def test_query_metrics(self):
        tracker = EngagementTracker()
        day1 = datetime(2026, 2, 5, 10, 0, tzinfo=timezone.utc)
        day2 = datetime(2026, 2, 6, 10, 0, tzinfo=timezone.utc)
        decisions = [
            _make_decision(
                "d1",
                sport="nba",
                decision_type="start_sit",
                risk_mode="floor",
                created_at=day1,
            ),
            _make_decision(
                "d2",
                sport="nba",
                decision_type="start_sit",
                risk_mode="median",
                created_at=day1,
            ),
            _make_decision(
                "d3",
                sport="nfl",
                decision_type="trade",
                risk_mode="ceiling",
                created_at=day2,
            ),
        ]
        metrics = tracker.compute_metrics(
            decisions=decisions,
            sessions=[],
            users=[],
            period_start=_PERIOD_START,
            period_end=_NOW,
        )
        assert metrics.queries.total_queries == 3
        assert metrics.queries.avg_queries_per_day == 1.5
        assert metrics.queries.popular_sports["nba"] == 2
        assert metrics.queries.popular_sports["nfl"] == 1
        assert "start_sit" in metrics.queries.popular_decision_types

    def test_retention_metrics(self):
        tracker = EngagementTracker()
        users = [
            _make_user("1", created_at=_PERIOD_START - timedelta(days=30)),  # returning
            _make_user("2", created_at=_PERIOD_START + timedelta(days=1)),  # new
            _make_user("3", created_at=_PERIOD_START + timedelta(days=5)),  # new
        ]
        day1 = datetime(2026, 2, 5, 10, 0, tzinfo=timezone.utc)
        day2 = datetime(2026, 2, 6, 10, 0, tzinfo=timezone.utc)
        decisions = [
            _make_decision("d1", user_id="1", created_at=day1),
            _make_decision("d2", user_id="2", created_at=day1),
            _make_decision("d3", user_id="1", created_at=day2),
            _make_decision("d4", user_id="3", created_at=day2),
        ]
        metrics = tracker.compute_metrics(
            decisions=decisions,
            sessions=[],
            users=users,
            period_start=_PERIOD_START,
            period_end=_NOW,
        )
        assert metrics.retention.new_users == 2
        assert metrics.retention.returning_users == 1
        assert metrics.retention.mau == 3
        assert metrics.retention.wau == 3  # all within 7 days

    def test_feature_metrics(self):
        tracker = EngagementTracker()
        decisions = [
            _make_decision("d1", source="local", cache_hit=False),
            _make_decision("d2", source="local", cache_hit=True),
            _make_decision("d3", source="claude", cache_hit=False),
            _make_decision("d4", source="claude", cache_hit=True),
        ]
        metrics = tracker.compute_metrics(
            decisions=decisions,
            sessions=[],
            users=[],
            period_start=_PERIOD_START,
            period_end=_NOW,
        )
        assert metrics.features.local_routing_count == 2
        assert metrics.features.claude_routing_count == 2
        assert metrics.features.local_routing_pct == 50.0
        assert metrics.features.cache_hits == 2
        assert metrics.features.cache_hit_rate == 50.0

    def test_depth_metrics(self):
        tracker = EngagementTracker()
        day1 = datetime(2026, 2, 5, 10, 0, tzinfo=timezone.utc)
        decisions = [
            _make_decision("d1", user_id="1", session_id="s1", created_at=day1),
            _make_decision("d2", user_id="1", session_id="s1", created_at=day1),
            _make_decision("d3", user_id="2", session_id="s2", created_at=day1),
        ]
        sessions = [_make_session("s1"), _make_session("s2")]
        metrics = tracker.compute_metrics(
            decisions=decisions,
            sessions=sessions,
            users=[],
            period_start=_PERIOD_START,
            period_end=_NOW,
        )
        assert metrics.depth.active_sessions == 2
        assert metrics.depth.active_users == 2
        assert metrics.depth.avg_queries_per_session == 1.5
        assert metrics.depth.avg_queries_per_user_per_day == 1.5

    def test_multi_user_multi_session(self):
        tracker = EngagementTracker()
        day1 = datetime(2026, 2, 5, 10, 0, tzinfo=timezone.utc)
        day2 = datetime(2026, 2, 6, 14, 0, tzinfo=timezone.utc)
        decisions = [
            _make_decision("d1", user_id="1", session_id="s1", created_at=day1),
            _make_decision("d2", user_id="1", session_id="s1", created_at=day1),
            _make_decision("d3", user_id="2", session_id="s2", created_at=day1),
            _make_decision("d4", user_id="1", session_id="s3", created_at=day2),
            _make_decision("d5", user_id="2", session_id="s4", created_at=day2),
            _make_decision("d6", user_id="3", session_id="s5", created_at=day2),
        ]
        sessions = [
            _make_session("s1", platform="ios"),
            _make_session("s2", platform="android"),
            _make_session("s3", platform="ios"),
            _make_session("s4", platform="android"),
            _make_session("s5", platform="web"),
        ]
        users = [
            _make_user("1", created_at=_PERIOD_START - timedelta(days=30)),
            _make_user("2", created_at=_PERIOD_START + timedelta(days=1)),
            _make_user("3", created_at=_PERIOD_START + timedelta(days=3)),
        ]
        metrics = tracker.compute_metrics(
            decisions=decisions,
            sessions=sessions,
            users=users,
            period_start=_PERIOD_START,
            period_end=_NOW,
        )
        assert metrics.queries.total_queries == 6
        assert metrics.retention.new_users == 2
        assert metrics.retention.returning_users == 1
        assert metrics.retention.mau == 3
        assert metrics.depth.active_users == 3
        assert metrics.depth.active_sessions == 5
        assert metrics.features.local_routing_count == 6

    def test_period_timestamps(self):
        tracker = EngagementTracker()
        metrics = tracker.compute_metrics(
            decisions=[],
            sessions=[],
            users=[],
            period_start=_PERIOD_START,
            period_end=_NOW,
        )
        assert metrics.period_start == _PERIOD_START
        assert metrics.period_end == _NOW

    def test_dau_averaging(self):
        """DAU should average unique users per day."""
        tracker = EngagementTracker()
        day1 = datetime(2026, 2, 5, 10, 0, tzinfo=timezone.utc)
        day2 = datetime(2026, 2, 6, 10, 0, tzinfo=timezone.utc)
        # Day 1: 2 unique users, Day 2: 1 unique user => avg DAU = 2
        decisions = [
            _make_decision("d1", user_id="1", created_at=day1),
            _make_decision("d2", user_id="2", created_at=day1),
            _make_decision("d3", user_id="1", created_at=day2),
        ]
        users = [
            _make_user("1"),
            _make_user("2"),
        ]
        metrics = tracker.compute_metrics(
            decisions=decisions,
            sessions=[],
            users=users,
            period_start=_PERIOD_START,
            period_end=_NOW,
        )
        # (2 + 1) / 2 = 1.5 → rounds to 2
        assert metrics.retention.dau == 2


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class TestEngagementEndpoint:
    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        return session

    @pytest.mark.asyncio
    async def test_db_not_configured(self):
        """Returns error when DB not configured."""
        from main import get_engagement_metrics

        with patch("main.db_service") as mock_db:
            mock_db.is_configured = False
            response = await get_engagement_metrics()
            assert response == {"error": "Database not configured"}

    @pytest.mark.asyncio
    async def test_engagement_endpoint_returns_structure(self, mock_db_session):
        """Test GET /engagement returns full response structure."""
        from main import get_engagement_metrics

        # Mock empty results for all three queries
        mock_dec_result = MagicMock()
        mock_dec_result.scalars.return_value.all.return_value = []

        mock_sess_result = MagicMock()
        mock_sess_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(
            side_effect=[mock_dec_result, mock_sess_result]
        )

        with (
            patch("main.db_service") as mock_db,
            patch("main.update_engagement_metrics"),
        ):
            mock_db.is_configured = True
            mock_db.session.return_value = mock_db_session

            response = await get_engagement_metrics(period="month")

            assert "period" in response
            assert response["period"] == "month"
            assert "sessions" in response
            assert "queries" in response
            assert "retention" in response
            assert "features" in response
            assert "depth" in response
            assert response["sessions"]["active_count"] == 0
            assert response["queries"]["total"] == 0

    @pytest.mark.asyncio
    async def test_engagement_endpoint_with_data(self, mock_db_session):
        """Test endpoint with mocked decision and session rows."""
        from main import get_engagement_metrics

        now = datetime.now(timezone.utc)

        # Mock decision row
        mock_dec = MagicMock()
        mock_dec.id = "d1"
        mock_dec.user_id = "1"
        mock_dec.session_id = "s1"
        mock_dec.sport = "nba"
        mock_dec.risk_mode = "median"
        mock_dec.decision_type = "start_sit"
        mock_dec.source = "local"
        mock_dec.cache_hit = False
        mock_dec.created_at = now

        mock_dec_result = MagicMock()
        mock_dec_result.scalars.return_value.all.return_value = [mock_dec]

        # Mock session row
        mock_sess = MagicMock()
        mock_sess.id = "s1"
        mock_sess.platform = "ios"
        mock_sess.status = "active"
        mock_sess.created_at = now - timedelta(hours=1)
        mock_sess.last_active_at = now
        mock_sess.user_id = "1"

        mock_sess_result = MagicMock()
        mock_sess_result.scalars.return_value.all.return_value = [mock_sess]

        # Mock user row
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.created_at = now - timedelta(days=30)

        mock_user_result = MagicMock()
        mock_user_result.scalars.return_value.all.return_value = [mock_user]

        mock_db_session.execute = AsyncMock(
            side_effect=[mock_dec_result, mock_sess_result, mock_user_result]
        )

        with (
            patch("main.db_service") as mock_db,
            patch("main.update_engagement_metrics"),
        ):
            mock_db.is_configured = True
            mock_db.session.return_value = mock_db_session

            response = await get_engagement_metrics(period="month")

            assert response["queries"]["total"] == 1
            assert response["sessions"]["active_count"] == 1
            assert response["features"]["local_routing"]["count"] == 1
            assert response["retention"]["returning_users"] == 1

    @pytest.mark.asyncio
    async def test_engagement_updates_prometheus(self, mock_db_session):
        """Test that endpoint calls update_engagement_metrics."""
        from main import get_engagement_metrics

        mock_dec_result = MagicMock()
        mock_dec_result.scalars.return_value.all.return_value = []
        mock_sess_result = MagicMock()
        mock_sess_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(
            side_effect=[mock_dec_result, mock_sess_result]
        )

        with (
            patch("main.db_service") as mock_db,
            patch("main.update_engagement_metrics") as mock_update,
        ):
            mock_db.is_configured = True
            mock_db.session.return_value = mock_db_session

            await get_engagement_metrics(period="today")

            mock_update.assert_called_once()
