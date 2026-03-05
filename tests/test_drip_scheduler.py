"""
Tests for the drip email scheduler.

Covers: start/stop lifecycle, run_now, and process delegation.
"""

from unittest.mock import AsyncMock, patch

import pytest

from services.drip_scheduler import DripScheduler


class TestDripScheduler:
    def test_initial_state(self):
        sched = DripScheduler()
        assert sched.is_running is False
        assert sched._last_run_at is None

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        sched = DripScheduler()
        with patch.object(sched, "_run_loop", new_callable=AsyncMock):
            await sched.start()
            assert sched.is_running is True
            await sched.stop()
            assert sched.is_running is False

    @pytest.mark.asyncio
    async def test_double_start_is_noop(self):
        sched = DripScheduler()
        with patch.object(sched, "_run_loop", new_callable=AsyncMock):
            await sched.start()
            await sched.start()  # Should not raise
            assert sched.is_running is True
            await sched.stop()

    @pytest.mark.asyncio
    async def test_run_now(self):
        sched = DripScheduler()
        with patch(
            "services.drip_scheduler.DripScheduler._process",
            new_callable=AsyncMock,
            return_value=3,
        ):
            result = await sched.run_now()
            assert result["status"] == "complete"
            assert result["sent"] == 3
            assert sched._last_run_at is not None

    @pytest.mark.asyncio
    async def test_process_delegates_to_email_drip(self):
        sched = DripScheduler()
        with patch(
            "services.email_drip.process_pending_drips",
            new_callable=AsyncMock,
            return_value=5,
        ):
            result = await sched._process()
            assert result == 5
