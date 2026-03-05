"""
Tests for the verdict pre-generation scheduler.

Covers: VerdictPregenScheduler lifecycle, should_run_now logic,
run loop, manual trigger, and constants.
"""

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from services.verdict_scheduler import (
    CHECK_INTERVAL,
    ET,
    PREGEN_COOLDOWN,
    PREGEN_DAY,
    PREGEN_HOUR,
    VerdictPregenScheduler,
)

_PREGEN = "services.goblin_verdict.goblin_verdict_service.pregenerate_all_verdicts"


# =============================================================================
# LIFECYCLE
# =============================================================================


class TestVerdictSchedulerLifecycle:
    """Test start/stop behavior."""

    def test_initial_state(self):
        scheduler = VerdictPregenScheduler()
        assert not scheduler.is_running
        assert scheduler._task is None
        assert scheduler._last_pregen_at is None

    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        scheduler = VerdictPregenScheduler()
        await scheduler.start()
        assert scheduler.is_running
        assert scheduler._task is not None
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        scheduler = VerdictPregenScheduler()
        await scheduler.start()
        await scheduler.stop()
        assert not scheduler.is_running
        assert scheduler._task is None

    @pytest.mark.asyncio
    async def test_double_start_warns(self, caplog):
        scheduler = VerdictPregenScheduler()
        await scheduler.start()
        await scheduler.start()  # Should warn, not crash
        assert "already running" in caplog.text
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        scheduler = VerdictPregenScheduler()
        await scheduler.stop()  # Should not crash
        assert not scheduler.is_running


# =============================================================================
# SHOULD_RUN_NOW
# =============================================================================


class TestShouldRunNow:
    """Test the pre-gen window detection logic."""

    def test_returns_true_on_thursday_8am_et(self):
        scheduler = VerdictPregenScheduler()
        # 2026-03-05 is a Thursday
        with patch("services.verdict_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 5, 8, 30, tzinfo=ET)
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            result = scheduler.should_run_now()
        assert result is True

    def test_returns_false_on_wrong_day(self):
        scheduler = VerdictPregenScheduler()
        # 2026-03-04 is a Wednesday
        with patch("services.verdict_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 4, 8, 30, tzinfo=ET)
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            result = scheduler.should_run_now()
        assert result is False

    def test_returns_false_on_wrong_hour(self):
        scheduler = VerdictPregenScheduler()
        # Thursday but 10 AM
        with patch("services.verdict_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 5, 10, 0, tzinfo=ET)
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            result = scheduler.should_run_now()
        assert result is False

    def test_returns_false_during_cooldown(self):
        scheduler = VerdictPregenScheduler()
        # Set last pregen to 1 hour ago (within 20h cooldown)
        scheduler._last_pregen_at = datetime.now(UTC) - timedelta(hours=1)
        with patch("services.verdict_scheduler.datetime") as mock_dt:
            mock_dt.now.side_effect = lambda tz=None: (
                datetime.now(tz) if tz else datetime.now()
            )
            # Make it Thursday 8 AM
            mock_dt.now.return_value = datetime(2026, 3, 5, 8, 30, tzinfo=ET)
            result = scheduler.should_run_now()
        assert result is False

    def test_returns_true_after_cooldown(self):
        scheduler = VerdictPregenScheduler()
        # Set last pregen to 21 hours ago (past 20h cooldown)
        scheduler._last_pregen_at = datetime.now(UTC) - timedelta(hours=21)
        with patch("services.verdict_scheduler.datetime") as mock_dt:
            now_utc = datetime.now(UTC)
            mock_dt.now.side_effect = lambda tz=None: (
                datetime(2026, 3, 5, 8, 30, tzinfo=ET) if tz == ET else now_utc
            )
            result = scheduler.should_run_now()
        assert result is True


# =============================================================================
# RUN LOOP
# =============================================================================


class TestVerdictRunLoop:
    """Test the background loop behavior."""

    @pytest.mark.asyncio
    async def test_loop_calls_pregen_when_should_run(self, caplog):
        scheduler = VerdictPregenScheduler()
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
                scheduler, "_run_pregen", new_callable=AsyncMock
            ) as mock_pregen,
            patch(
                "services.verdict_scheduler.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            await scheduler._run_loop()
            mock_pregen.assert_called()

    @pytest.mark.asyncio
    async def test_loop_skips_when_not_time(self):
        scheduler = VerdictPregenScheduler()
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
                scheduler, "_run_pregen", new_callable=AsyncMock
            ) as mock_pregen,
            patch(
                "services.verdict_scheduler.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            await scheduler._run_loop()
            mock_pregen.assert_not_called()

    @pytest.mark.asyncio
    async def test_loop_handles_exception(self, caplog):
        scheduler = VerdictPregenScheduler()
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
                scheduler,
                "_run_pregen",
                side_effect=RuntimeError("Redis down"),
            ),
            patch(
                "services.verdict_scheduler.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            await scheduler._run_loop()

        assert "pre-gen check error" in caplog.text

    @pytest.mark.asyncio
    async def test_loop_exits_on_cancel_in_check(self):
        scheduler = VerdictPregenScheduler()
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
            patch(
                "services.verdict_scheduler.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            await scheduler._run_loop()
        # Exited cleanly

    @pytest.mark.asyncio
    async def test_loop_exits_on_cancel_in_sleep(self):
        scheduler = VerdictPregenScheduler()
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
            patch(
                "services.verdict_scheduler.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            await scheduler._run_loop()
        # Exited cleanly


# =============================================================================
# RUN PREGEN
# =============================================================================


class TestRunPregen:
    """Test the pre-generation execution."""

    @pytest.mark.asyncio
    async def test_run_pregen_sets_timestamp(self):
        scheduler = VerdictPregenScheduler()
        assert scheduler._last_pregen_at is None

        mock_result = {"week": 1, "users": 1, "generated": 3, "failed": 0}
        with patch(_PREGEN, new_callable=AsyncMock, return_value=mock_result):
            await scheduler._run_pregen()

        assert scheduler._last_pregen_at is not None

    @pytest.mark.asyncio
    async def test_run_pregen_calls_service(self):
        scheduler = VerdictPregenScheduler()
        mock_result = {"week": 1, "users": 2, "generated": 6, "failed": 0}

        with patch(
            _PREGEN, new_callable=AsyncMock, return_value=mock_result
        ) as mock_pregen:
            await scheduler._run_pregen()
            mock_pregen.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_now_manual_trigger(self):
        scheduler = VerdictPregenScheduler()
        mock_result = {"week": 5, "users": 3, "generated": 9, "failed": 0}

        with patch(
            _PREGEN, new_callable=AsyncMock, return_value=mock_result
        ) as mock_pregen:
            result = await scheduler.run_now()
            mock_pregen.assert_called_once()
            assert result == mock_result
            assert scheduler._last_pregen_at is not None


# =============================================================================
# CONSTANTS
# =============================================================================


class TestVerdictSchedulerConstants:
    """Verify configuration values."""

    def test_check_interval_is_1_hour(self):
        assert CHECK_INTERVAL == 3600

    def test_pregen_day_is_thursday(self):
        assert PREGEN_DAY == 3

    def test_pregen_hour_is_8am(self):
        assert PREGEN_HOUR == 8

    def test_cooldown_is_20_hours(self):
        assert PREGEN_COOLDOWN == 20 * 3600

    def test_et_timezone(self):
        assert ET == timezone(timedelta(hours=-5))
