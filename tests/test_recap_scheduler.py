"""
Tests for the weekly recap scheduler.

Covers: RecapScheduler lifecycle, should_run_now logic,
run loop, recap generation, and constants.
"""

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.recap_scheduler import (
    CHECK_INTERVAL,
    ET,
    RECAP_COOLDOWN,
    RECAP_DAY,
    RECAP_HOUR,
    RecapScheduler,
)


# =============================================================================
# LIFECYCLE
# =============================================================================


class TestRecapSchedulerLifecycle:
    """Test start/stop behavior."""

    def test_initial_state(self):
        scheduler = RecapScheduler()
        assert not scheduler.is_running
        assert scheduler._task is None
        assert scheduler._last_recap_at is None

    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        scheduler = RecapScheduler()
        await scheduler.start()
        assert scheduler.is_running
        assert scheduler._task is not None
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        scheduler = RecapScheduler()
        await scheduler.start()
        await scheduler.stop()
        assert not scheduler.is_running
        assert scheduler._task is None

    @pytest.mark.asyncio
    async def test_double_start_warns(self, caplog):
        scheduler = RecapScheduler()
        await scheduler.start()
        await scheduler.start()
        assert "already running" in caplog.text
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        scheduler = RecapScheduler()
        await scheduler.stop()
        assert not scheduler.is_running


# =============================================================================
# SHOULD_RUN_NOW
# =============================================================================


class TestRecapShouldRunNow:
    """Test the recap window detection logic."""

    def test_returns_true_on_sunday_10am_et(self):
        scheduler = RecapScheduler()
        # 2026-03-08 is a Sunday
        with patch("services.recap_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 8, 10, 30, tzinfo=ET)
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            result = scheduler.should_run_now()
        assert result is True

    def test_returns_false_on_wrong_day(self):
        scheduler = RecapScheduler()
        # 2026-03-05 is a Thursday
        with patch("services.recap_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 5, 10, 30, tzinfo=ET)
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            result = scheduler.should_run_now()
        assert result is False

    def test_returns_false_on_wrong_hour(self):
        scheduler = RecapScheduler()
        # Sunday but 3 PM
        with patch("services.recap_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 8, 15, 0, tzinfo=ET)
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            result = scheduler.should_run_now()
        assert result is False

    def test_returns_false_during_cooldown(self):
        scheduler = RecapScheduler()
        scheduler._last_recap_at = datetime.now(UTC) - timedelta(hours=1)
        with patch("services.recap_scheduler.datetime") as mock_dt:
            mock_dt.now.side_effect = lambda tz=None: (
                datetime.now(tz) if tz else datetime.now()
            )
            mock_dt.now.return_value = datetime(2026, 3, 8, 10, 30, tzinfo=ET)
            result = scheduler.should_run_now()
        assert result is False

    def test_returns_true_after_cooldown(self):
        scheduler = RecapScheduler()
        scheduler._last_recap_at = datetime.now(UTC) - timedelta(hours=21)
        with patch("services.recap_scheduler.datetime") as mock_dt:
            now_utc = datetime.now(UTC)
            mock_dt.now.side_effect = lambda tz=None: (
                datetime(2026, 3, 8, 10, 30, tzinfo=ET) if tz == ET else now_utc
            )
            result = scheduler.should_run_now()
        assert result is True


# =============================================================================
# RUN LOOP
# =============================================================================


class TestRecapRunLoop:
    """Test the background loop behavior."""

    @pytest.mark.asyncio
    async def test_loop_calls_recaps_when_should_run(self):
        scheduler = RecapScheduler()
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
                scheduler, "_run_recaps", new_callable=AsyncMock
            ) as mock_recaps,
            patch("services.recap_scheduler.asyncio.sleep", side_effect=fake_sleep),
        ):
            await scheduler._run_loop()
            mock_recaps.assert_called()

    @pytest.mark.asyncio
    async def test_loop_skips_when_not_time(self):
        scheduler = RecapScheduler()
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
                scheduler, "_run_recaps", new_callable=AsyncMock
            ) as mock_recaps,
            patch("services.recap_scheduler.asyncio.sleep", side_effect=fake_sleep),
        ):
            await scheduler._run_loop()
            mock_recaps.assert_not_called()

    @pytest.mark.asyncio
    async def test_loop_handles_exception(self, caplog):
        scheduler = RecapScheduler()
        scheduler._running = True
        call_count = 0

        async def fake_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                scheduler._running = False

        with (
            patch.object(scheduler, "should_run_now", return_value=True),
            patch.object(scheduler, "_run_recaps", side_effect=RuntimeError("DB down")),
            patch("services.recap_scheduler.asyncio.sleep", side_effect=fake_sleep),
        ):
            await scheduler._run_loop()

        assert "check error" in caplog.text

    @pytest.mark.asyncio
    async def test_loop_exits_on_cancel_in_check(self):
        scheduler = RecapScheduler()
        scheduler._running = True
        call_count = 0

        async def fake_sleep(seconds):
            nonlocal call_count
            call_count += 1

        with (
            patch.object(
                scheduler,
                "should_run_now",
                side_effect=asyncio.CancelledError,
            ),
            patch("services.recap_scheduler.asyncio.sleep", side_effect=fake_sleep),
        ):
            await scheduler._run_loop()

    @pytest.mark.asyncio
    async def test_loop_exits_on_cancel_in_sleep(self):
        scheduler = RecapScheduler()
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
            patch("services.recap_scheduler.asyncio.sleep", side_effect=fake_sleep),
        ):
            await scheduler._run_loop()


# =============================================================================
# RUN RECAPS
# =============================================================================


class TestRunRecaps:
    """Test the recap generation execution."""

    @pytest.mark.asyncio
    async def test_run_recaps_sets_timestamp(self):
        scheduler = RecapScheduler()
        assert scheduler._last_recap_at is None

        with (
            patch.object(
                scheduler, "_get_active_users", new_callable=AsyncMock, return_value=[]
            ),
            patch("services.database.db_service") as mock_db,
        ):
            mock_db.is_configured = True
            await scheduler._run_recaps()

        assert scheduler._last_recap_at is not None

    @pytest.mark.asyncio
    async def test_run_recaps_generates_for_users(self):
        scheduler = RecapScheduler()
        users = [(1, "Alice"), (2, "Bob")]
        mock_recap = MagicMock()

        with (
            patch.object(
                scheduler,
                "_get_active_users",
                new_callable=AsyncMock,
                return_value=users,
            ),
            patch("services.database.db_service") as mock_db,
            patch(
                "services.weekly_recap.generate_weekly_recap",
                new_callable=AsyncMock,
                return_value=mock_recap,
            ) as mock_gen,
        ):
            mock_db.is_configured = True
            mock_session = AsyncMock()
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)
            await scheduler._run_recaps()

        assert mock_gen.call_count == 2

    @pytest.mark.asyncio
    async def test_run_recaps_skips_when_db_not_configured(self, caplog):
        scheduler = RecapScheduler()

        with patch("services.database.db_service") as mock_db:
            mock_db.is_configured = False
            await scheduler._run_recaps()

        assert "DB not configured" in caplog.text

    @pytest.mark.asyncio
    async def test_run_recaps_handles_per_user_error(self, caplog):
        scheduler = RecapScheduler()
        users = [(1, "Alice")]

        with (
            patch.object(
                scheduler,
                "_get_active_users",
                new_callable=AsyncMock,
                return_value=users,
            ),
            patch("services.database.db_service") as mock_db,
            patch(
                "services.weekly_recap.generate_weekly_recap",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Generation error"),
            ),
        ):
            mock_db.is_configured = True
            mock_session = AsyncMock()
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)
            await scheduler._run_recaps()

        assert "Recap generation failed for user" in caplog.text

    @pytest.mark.asyncio
    async def test_run_now_manual_trigger(self):
        scheduler = RecapScheduler()

        with (
            patch.object(scheduler, "_run_recaps", new_callable=AsyncMock) as mock_run,
        ):
            result = await scheduler.run_now()
            mock_run.assert_called_once()
            assert "status" in result
            assert scheduler._last_recap_at is not None


# =============================================================================
# GET ACTIVE USERS
# =============================================================================


class TestGetActiveUsers:
    """Test active user fetching."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_db_not_configured(self):
        scheduler = RecapScheduler()
        with patch("services.database.db_service") as mock_db:
            mock_db.is_configured = False
            result = await scheduler._get_active_users()
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_db_error(self, caplog):
        scheduler = RecapScheduler()
        with patch("services.database.db_service") as mock_db:
            mock_db.is_configured = True
            mock_session = AsyncMock()
            mock_session.execute.side_effect = RuntimeError("DB error")
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await scheduler._get_active_users()
        assert result == []
        assert "Failed to fetch active users" in caplog.text


# =============================================================================
# CONSTANTS
# =============================================================================


class TestRecapSchedulerConstants:
    """Verify configuration values."""

    def test_check_interval_is_1_hour(self):
        assert CHECK_INTERVAL == 3600

    def test_recap_day_is_sunday(self):
        assert RECAP_DAY == 6

    def test_recap_hour_is_10am(self):
        assert RECAP_HOUR == 10

    def test_cooldown_is_20_hours(self):
        assert RECAP_COOLDOWN == 20 * 3600

    def test_et_timezone(self):
        assert ET == timezone(timedelta(hours=-5))
