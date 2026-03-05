"""
Tests for the outcome sync scheduler.

Covers: OutcomeScheduler lifecycle, sync execution, error handling,
and lifespan integration.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from services.outcome_scheduler import (
    OUTCOME_SYNC_DAYS_BACK,
    OUTCOME_SYNC_INTERVAL,
    OutcomeScheduler,
)

_SYNC = "services.outcome_recorder.sync_recent_outcomes"


# =============================================================================
# LIFECYCLE
# =============================================================================


class TestOutcomeSchedulerLifecycle:
    """Test start/stop behavior."""

    def test_initial_state(self):
        scheduler = OutcomeScheduler()
        assert not scheduler.is_running
        assert scheduler._task is None

    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        scheduler = OutcomeScheduler()
        await scheduler.start()
        assert scheduler.is_running
        assert scheduler._task is not None
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        scheduler = OutcomeScheduler()
        await scheduler.start()
        await scheduler.stop()
        assert not scheduler.is_running
        assert scheduler._task is None

    @pytest.mark.asyncio
    async def test_double_start_warns(self, caplog):
        scheduler = OutcomeScheduler()
        await scheduler.start()
        await scheduler.start()  # Should warn, not crash
        assert "already running" in caplog.text
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        scheduler = OutcomeScheduler()
        await scheduler.stop()  # Should not crash
        assert not scheduler.is_running


# =============================================================================
# SYNC EXECUTION
# =============================================================================


class TestOutcomeSyncExecution:
    """Test the actual sync logic."""

    @pytest.mark.asyncio
    async def test_sync_calls_outcome_recorder(self):
        scheduler = OutcomeScheduler()
        mock_result = {
            "total_decisions_processed": 5,
            "total_outcomes_recorded": 3,
            "errors": [],
        }

        with patch(
            _SYNC, new_callable=AsyncMock, return_value=mock_result
        ) as mock_sync:
            result = await scheduler._sync_outcomes()
            mock_sync.assert_called_once_with(days_back=OUTCOME_SYNC_DAYS_BACK)
            assert result == mock_result

    @pytest.mark.asyncio
    async def test_sync_returns_none_on_import_error(self):
        """If outcome_recorder can't be imported, should raise."""
        scheduler = OutcomeScheduler()
        with patch(_SYNC, side_effect=ImportError("no module")):
            with pytest.raises(ImportError):
                await scheduler._sync_outcomes()


# =============================================================================
# RUN LOOP
# =============================================================================


class TestOutcomeRunLoop:
    """Test the background loop behavior."""

    @pytest.mark.asyncio
    async def test_loop_handles_sync_exception(self, caplog):
        """Exceptions in sync should be caught and logged."""
        scheduler = OutcomeScheduler()
        scheduler._running = True
        call_count = 0

        async def failing_sync(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("ESPN down")
            # Stop the loop after one error
            scheduler._running = False
            return None

        async def fake_sleep(seconds):
            # On the interval sleep after error, just return
            pass

        with (
            patch.object(scheduler, "_sync_outcomes", side_effect=failing_sync),
            patch("services.outcome_scheduler.asyncio.sleep", side_effect=fake_sleep),
        ):
            await scheduler._run_loop()

        assert "Outcome sync error" in caplog.text

    @pytest.mark.asyncio
    async def test_loop_exits_on_cancel(self):
        """CancelledError should break the loop cleanly."""
        scheduler = OutcomeScheduler()
        scheduler._running = True

        with patch.object(
            scheduler, "_sync_outcomes", side_effect=asyncio.CancelledError
        ):
            with patch(
                "services.outcome_scheduler.asyncio.sleep",
                new_callable=AsyncMock,
                return_value=None,
            ):
                # Should exit without raising
                await scheduler._run_loop()

        # Loop exited cleanly


# =============================================================================
# CONSTANTS
# =============================================================================


class TestOutcomeSchedulerConstants:
    """Verify configuration values."""

    def test_interval_is_6_hours(self):
        assert OUTCOME_SYNC_INTERVAL == 6 * 60 * 60

    def test_days_back_is_2(self):
        assert OUTCOME_SYNC_DAYS_BACK == 2
