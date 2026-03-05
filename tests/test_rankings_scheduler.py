"""
Tests for the power rankings scheduler.

Covers: RankingsScheduler lifecycle, should_run_now logic,
run loop, rankings generation, and constants.
"""

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

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
        scheduler._last_rankings_at = datetime.now(UTC) - timedelta(hours=1)
        with patch("services.rankings_scheduler.datetime") as mock_dt:
            mock_dt.now.side_effect = lambda tz=None: (
                datetime.now(tz) if tz else datetime.now()
            )
            mock_dt.now.return_value = datetime(2026, 3, 9, 9, 30, tzinfo=ET)
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
