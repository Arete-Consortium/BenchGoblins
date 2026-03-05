"""
Drip Email Scheduler — Runs hourly to process pending onboarding emails.

Checks all users created in the last 7 days and sends any due drip emails
(welcome, connect league, first verdict).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 60 * 60  # 1 hour


class DripScheduler:
    """Background scheduler for drip email processing."""

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_run_at: datetime | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Launch the drip check background task."""
        if self._running:
            logger.warning("Drip scheduler already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Drip scheduler started")

    async def stop(self) -> None:
        """Cancel the background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Drip scheduler stopped")

    async def _run_loop(self) -> None:
        """Check hourly and process pending drip emails."""
        await asyncio.sleep(60)  # Wait 1 min after startup

        while self._running:
            try:
                sent = await self._process()
                self._last_run_at = datetime.now(UTC)
                if sent > 0:
                    logger.info("Drip scheduler: sent %d emails", sent)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Drip scheduler error")

            try:
                await asyncio.sleep(CHECK_INTERVAL)
            except asyncio.CancelledError:
                break

    async def _process(self) -> int:
        """Run the drip email processor."""
        from services.email_drip import process_pending_drips

        return await process_pending_drips()

    async def run_now(self) -> dict:
        """Manually trigger drip processing (for admin/testing)."""
        sent = await self._process()
        self._last_run_at = datetime.now(UTC)
        return {"status": "complete", "sent": sent, "triggered_at": self._last_run_at.isoformat()}


# Singleton
drip_scheduler = DripScheduler()
