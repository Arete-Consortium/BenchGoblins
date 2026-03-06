"""
Tests for the power rankings scheduler.

Covers: RankingsScheduler lifecycle, should_run_now logic,
run loop, rankings generation, and constants.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.rankings_scheduler import (
    CHECK_INTERVAL,
    ET,
    RANKINGS_COOLDOWN,
    RANKINGS_DAY,
    RANKINGS_HOUR,
    RankingsScheduler,
)


# =============================================================================
# LIFECYCLE
# =============================================================================


class TestRankingsSchedulerLifecycle:
    """Test start/stop behavior."""

    def test_initial_state(self):
        scheduler = RankingsScheduler()
        assert not scheduler.is_running
        assert scheduler._task is None
        assert scheduler._last_rankings_at is None

    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        scheduler = RankingsScheduler()
        await scheduler.start()
        assert scheduler.is_running
        assert scheduler._task is not None
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        scheduler = RankingsScheduler()
        await scheduler.start()
        await scheduler.stop()
        assert not scheduler.is_running
        assert scheduler._task is None

    @pytest.mark.asyncio
    async def test_double_start_warns(self, caplog):
        scheduler = RankingsScheduler()
        await scheduler.start()
        await scheduler.start()
        assert "already running" in caplog.text
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        scheduler = RankingsScheduler()
        await scheduler.stop()
        assert not scheduler.is_running


# =============================================================================
# SHOULD_RUN_NOW
# =============================================================================


class TestRankingsShouldRunNow:
    """Test the rankings window detection logic."""

    def test_returns_true_on_monday_9am_et(self):
        scheduler = RankingsScheduler()
        # 2026-03-09 is a Monday
        with patch("services.rankings_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 9, 9, 30, tzinfo=ET)
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            result = scheduler.should_run_now()
        assert result is True

    def test_returns_false_on_wrong_day(self):
        scheduler = RankingsScheduler()
        # 2026-03-05 is a Thursday
        with patch("services.rankings_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 5, 9, 30, tzinfo=ET)
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            result = scheduler.should_run_now()
        assert result is False

    def test_returns_false_on_wrong_hour(self):
        scheduler = RankingsScheduler()
        # Monday but 3 PM
        with patch("services.rankings_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 9, 15, 0, tzinfo=ET)
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            result = scheduler.should_run_now()
        assert result is False

    def test_returns_false_during_cooldown(self):
        scheduler = RankingsScheduler()
        now_utc = datetime.now(UTC)
        scheduler._last_rankings_at = now_utc - timedelta(hours=1)

        monday_9am_et = datetime(2026, 3, 9, 9, 30, tzinfo=ET)

        def fake_now(tz=None):
            if tz == ET:
                return monday_9am_et
            return now_utc

        with patch("services.rankings_scheduler.datetime") as mock_dt:
            mock_dt.now.side_effect = fake_now
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            result = scheduler.should_run_now()
        assert result is False

    def test_returns_true_after_cooldown(self):
        scheduler = RankingsScheduler()
        scheduler._last_rankings_at = datetime.now(UTC) - timedelta(hours=21)
        with patch("services.rankings_scheduler.datetime") as mock_dt:
            now_utc = datetime.now(UTC)
            mock_dt.now.side_effect = lambda tz=None: (
                datetime(2026, 3, 9, 9, 30, tzinfo=ET) if tz == ET else now_utc
            )
            result = scheduler.should_run_now()
        assert result is True


# =============================================================================
# RUN LOOP
# =============================================================================


class TestRankingsRunLoop:
    """Test the background loop behavior."""

    @pytest.mark.asyncio
    async def test_loop_calls_rankings_when_should_run(self):
        scheduler = RankingsScheduler()
        scheduler._running = True
        call_count = 0

        async def fake_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                scheduler._running = False

        with (
            patch.object(scheduler, "should_run_now", return_value=True),
            patch.object(
                scheduler, "_run_rankings", new_callable=AsyncMock
            ) as mock_rankings,
            patch("services.rankings_scheduler.asyncio.sleep", side_effect=fake_sleep),
        ):
            await scheduler._run_loop()
            mock_rankings.assert_called()

    @pytest.mark.asyncio
    async def test_loop_skips_when_not_time(self):
        scheduler = RankingsScheduler()
        scheduler._running = True
        call_count = 0

        async def fake_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                scheduler._running = False

        with (
            patch.object(scheduler, "should_run_now", return_value=False),
            patch.object(
                scheduler, "_run_rankings", new_callable=AsyncMock
            ) as mock_rankings,
            patch("services.rankings_scheduler.asyncio.sleep", side_effect=fake_sleep),
        ):
            await scheduler._run_loop()
            mock_rankings.assert_not_called()

    @pytest.mark.asyncio
    async def test_loop_handles_exception(self, caplog):
        scheduler = RankingsScheduler()
        scheduler._running = True
        call_count = 0

        async def fake_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                scheduler._running = False

        with (
            patch.object(scheduler, "should_run_now", return_value=True),
            patch.object(
                scheduler, "_run_rankings", side_effect=RuntimeError("Sleeper down")
            ),
            patch("services.rankings_scheduler.asyncio.sleep", side_effect=fake_sleep),
        ):
            await scheduler._run_loop()

        assert "check error" in caplog.text

    @pytest.mark.asyncio
    async def test_loop_exits_on_cancel(self):
        scheduler = RankingsScheduler()
        scheduler._running = True
        call_count = 0

        async def fake_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return  # Initial delay
            raise asyncio.CancelledError

        with (
            patch.object(scheduler, "should_run_now", return_value=False),
            patch("services.rankings_scheduler.asyncio.sleep", side_effect=fake_sleep),
        ):
            await scheduler._run_loop()


# =============================================================================
# RUN RANKINGS
# =============================================================================


class TestRunRankings:
    """Test the rankings generation execution."""

    @pytest.mark.asyncio
    async def test_run_rankings_sets_timestamp(self):
        scheduler = RankingsScheduler()
        assert scheduler._last_rankings_at is None

        with patch.object(
            scheduler, "_get_active_leagues", new_callable=AsyncMock, return_value=[]
        ):
            await scheduler._run_rankings()

        assert scheduler._last_rankings_at is not None

    @pytest.mark.asyncio
    async def test_run_now_manual_trigger(self):
        scheduler = RankingsScheduler()

        with patch.object(
            scheduler, "_run_rankings", new_callable=AsyncMock
        ) as mock_run:
            result = await scheduler.run_now()
            mock_run.assert_called_once()
            assert "status" in result
            assert scheduler._last_rankings_at is not None


# =============================================================================
# GET ACTIVE LEAGUES
# =============================================================================


class TestGetActiveLeagues:
    """Test active league fetching."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_db_not_configured(self):
        scheduler = RankingsScheduler()
        with patch("services.database.db_service") as mock_db:
            mock_db.is_configured = False
            result = await scheduler._get_active_leagues()
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_db_error(self, caplog):
        scheduler = RankingsScheduler()
        with patch("services.database.db_service") as mock_db:
            mock_db.is_configured = True
            mock_session = AsyncMock()
            mock_session.execute.side_effect = RuntimeError("DB error")
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await scheduler._get_active_leagues()
        assert result == []
        assert "Failed to fetch active leagues" in caplog.text


# =============================================================================
# CONSTANTS
# =============================================================================


class TestRankingsSchedulerConstants:
    """Verify configuration values."""

    def test_check_interval_is_1_hour(self):
        assert CHECK_INTERVAL == 3600

    def test_rankings_day_is_monday(self):
        assert RANKINGS_DAY == 0

    def test_rankings_hour_is_9am(self):
        assert RANKINGS_HOUR == 9

    def test_cooldown_is_20_hours(self):
        assert RANKINGS_COOLDOWN == 20 * 3600

    def test_et_timezone(self):
        assert ET == timezone(timedelta(hours=-5))


# =============================================================================
# RUN LOOP — CancelledError during should_run_now/rankings (line 97)
# =============================================================================


class TestRunLoopCancelledError:
    """Cover CancelledError break in the try around should_run_now."""

    async def test_cancelled_error_during_should_run_breaks_loop(self):
        """Line 97: CancelledError raised inside should_run_now breaks loop."""
        scheduler = RankingsScheduler()
        scheduler._running = True

        call_count = 0

        async def fake_sleep(seconds):
            nonlocal call_count
            call_count += 1

        with (
            patch.object(
                scheduler, "should_run_now", side_effect=asyncio.CancelledError
            ),
            patch(
                "services.rankings_scheduler.asyncio.sleep", side_effect=fake_sleep
            ),
        ):
            await scheduler._run_loop()
        # Loop exited via the break on CancelledError
        assert call_count == 1  # only the initial 30s sleep

    async def test_cancelled_error_during_run_rankings_breaks_loop(self):
        """Line 97: CancelledError raised inside _run_rankings breaks loop."""
        scheduler = RankingsScheduler()
        scheduler._running = True

        call_count = 0

        async def fake_sleep(seconds):
            nonlocal call_count
            call_count += 1

        with (
            patch.object(scheduler, "should_run_now", return_value=True),
            patch.object(
                scheduler,
                "_run_rankings",
                new_callable=AsyncMock,
                side_effect=asyncio.CancelledError,
            ),
            patch(
                "services.rankings_scheduler.asyncio.sleep", side_effect=fake_sleep
            ),
        ):
            await scheduler._run_loop()
        assert call_count == 1


# =============================================================================
# RUN RANKINGS — full league processing (lines 118-162)
# =============================================================================


class TestRunRankingsLeagueProcessing:
    """Cover the league iteration loop in _run_rankings."""

    def _make_roster(self, owner_id, players, starters):
        """Helper to create a mock roster."""
        roster = MagicMock()
        roster.owner_id = owner_id
        roster.players = players
        roster.starters = starters
        return roster

    async def test_generates_rankings_for_league(self, caplog):
        """Lines 118-158: full path with rosters, ranking, Redis cache."""
        scheduler = RankingsScheduler()
        rosters = [
            self._make_roster("owner_a", ["p1", "p2", "p3"], ["p1", "p2"]),
            self._make_roster("owner_b", ["p1", "p2", "p3", "p4"], ["p1"]),
        ]

        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_redis._client = AsyncMock()
        mock_redis._client.setex = AsyncMock()

        mock_sleeper = MagicMock()
        mock_sleeper.get_league_rosters = AsyncMock(return_value=rosters)

        with (
            caplog.at_level(logging.INFO),
            patch.object(
                scheduler,
                "_get_active_leagues",
                new_callable=AsyncMock,
                return_value=[(1, "ext_123")],
            ),
            patch(
                "services.redis.redis_service", mock_redis,
            ),
            patch(
                "services.sleeper.sleeper_service", mock_sleeper,
            ),
        ):
            await scheduler._run_rankings()

        # Verify Redis was called with correct cache key and data
        mock_redis._client.setex.assert_called_once()
        call_args = mock_redis._client.setex.call_args
        assert call_args[0][0] == "rankings:league:1"
        cached = json.loads(call_args[0][2])
        assert cached["league_id"] == 1
        assert len(cached["rankings"]) == 2
        # owner_a: 2*10 + 1*3 = 23, owner_b: 1*10 + 3*3 = 19
        assert cached["rankings"][0]["owner_id"] == "owner_a"
        assert cached["rankings"][0]["rank"] == 1
        assert cached["rankings"][1]["rank"] == 2
        assert "1 generated" in caplog.text

    async def test_skips_league_with_no_rosters(self, caplog):
        """Line 120-121: empty rosters → continue."""
        scheduler = RankingsScheduler()

        mock_sleeper = MagicMock()
        mock_sleeper.get_league_rosters = AsyncMock(return_value=[])

        mock_redis = MagicMock()
        mock_redis.is_connected = False

        with (
            caplog.at_level(logging.INFO),
            patch.object(
                scheduler,
                "_get_active_leagues",
                new_callable=AsyncMock,
                return_value=[(1, "ext_123")],
            ),
            patch(
                "services.sleeper.sleeper_service", mock_sleeper,
            ),
            patch(
                "services.redis.redis_service", mock_redis,
            ),
        ):
            await scheduler._run_rankings()

        assert "0 generated" in caplog.text

    async def test_skips_league_with_none_rosters(self, caplog):
        """Line 120-121: None rosters → continue."""
        scheduler = RankingsScheduler()

        mock_sleeper = MagicMock()
        mock_sleeper.get_league_rosters = AsyncMock(return_value=None)

        mock_redis = MagicMock()
        mock_redis.is_connected = False

        with (
            caplog.at_level(logging.INFO),
            patch.object(
                scheduler,
                "_get_active_leagues",
                new_callable=AsyncMock,
                return_value=[(1, "ext_123")],
            ),
            patch(
                "services.sleeper.sleeper_service", mock_sleeper,
            ),
            patch(
                "services.redis.redis_service", mock_redis,
            ),
        ):
            await scheduler._run_rankings()

        assert "0 generated" in caplog.text

    async def test_handles_roster_with_none_players(self, caplog):
        """Line 125-126: roster.players is None → player_count=0."""
        scheduler = RankingsScheduler()
        roster = self._make_roster("owner_a", None, None)

        mock_sleeper = MagicMock()
        mock_sleeper.get_league_rosters = AsyncMock(return_value=[roster])

        mock_redis = MagicMock()
        mock_redis.is_connected = False

        with (
            caplog.at_level(logging.INFO),
            patch.object(
                scheduler,
                "_get_active_leagues",
                new_callable=AsyncMock,
                return_value=[(1, "ext_123")],
            ),
            patch(
                "services.sleeper.sleeper_service", mock_sleeper,
            ),
            patch(
                "services.redis.redis_service", mock_redis,
            ),
        ):
            await scheduler._run_rankings()

        assert "1 generated" in caplog.text

    async def test_redis_not_connected_skips_cache(self, caplog):
        """Line 142: redis not connected → skip cache, still counts generated."""
        scheduler = RankingsScheduler()
        rosters = [self._make_roster("owner_a", ["p1"], ["p1"])]

        mock_sleeper = MagicMock()
        mock_sleeper.get_league_rosters = AsyncMock(return_value=rosters)

        mock_redis = MagicMock()
        mock_redis.is_connected = False

        with (
            caplog.at_level(logging.INFO),
            patch.object(
                scheduler,
                "_get_active_leagues",
                new_callable=AsyncMock,
                return_value=[(1, "ext_123")],
            ),
            patch(
                "services.sleeper.sleeper_service", mock_sleeper,
            ),
            patch(
                "services.redis.redis_service", mock_redis,
            ),
        ):
            await scheduler._run_rankings()

        assert "1 generated" in caplog.text

    async def test_redis_cache_error_logs_debug(self, caplog):
        """Lines 155-156: Redis setex raises → logs debug, still counts generated."""
        scheduler = RankingsScheduler()
        rosters = [self._make_roster("owner_a", ["p1"], ["p1"])]

        mock_sleeper = MagicMock()
        mock_sleeper.get_league_rosters = AsyncMock(return_value=rosters)

        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_redis._client = AsyncMock()
        mock_redis._client.setex = AsyncMock(
            side_effect=RuntimeError("Redis down")
        )

        with (
            patch.object(
                scheduler,
                "_get_active_leagues",
                new_callable=AsyncMock,
                return_value=[(1, "ext_123")],
            ),
            patch(
                "services.sleeper.sleeper_service", mock_sleeper,
            ),
            patch(
                "services.redis.redis_service", mock_redis,
            ),
            caplog.at_level("DEBUG"),
        ):
            await scheduler._run_rankings()

        assert "Failed to cache rankings" in caplog.text
        assert "1 generated" in caplog.text

    async def test_league_exception_increments_failed(self, caplog):
        """Lines 160-162: exception during league processing → failed += 1."""
        scheduler = RankingsScheduler()

        mock_sleeper = MagicMock()
        mock_sleeper.get_league_rosters = AsyncMock(
            side_effect=RuntimeError("Sleeper API error")
        )

        mock_redis = MagicMock()
        mock_redis.is_connected = False

        with (
            caplog.at_level(logging.INFO),
            patch.object(
                scheduler,
                "_get_active_leagues",
                new_callable=AsyncMock,
                return_value=[(1, "ext_123"), (2, "ext_456")],
            ),
            patch(
                "services.sleeper.sleeper_service", mock_sleeper,
            ),
            patch(
                "services.redis.redis_service", mock_redis,
            ),
        ):
            await scheduler._run_rankings()

        assert "Rankings generation failed for league" in caplog.text
        assert "0 generated, 2 failed" in caplog.text


# =============================================================================
# GET ACTIVE LEAGUES — success path (line 191)
# =============================================================================


class TestGetActiveLeaguesSuccess:
    """Cover the successful DB query path."""

    async def test_returns_league_tuples_from_db(self):
        """Line 191: successful query returns list of (id, external_id) tuples."""
        scheduler = RankingsScheduler()

        mock_result = MagicMock()
        mock_result.all.return_value = [(1, "ext_abc"), (2, "ext_def")]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db = MagicMock()
        mock_db.is_configured = True
        mock_db.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.database.db_service", mock_db,
        ):
            result = await scheduler._get_active_leagues()

        assert result == [(1, "ext_abc"), (2, "ext_def")]
        mock_session.execute.assert_called_once()
