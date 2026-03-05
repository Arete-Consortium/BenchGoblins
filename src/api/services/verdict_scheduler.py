"""
Verdict Pre-generation Scheduler — Weekly pre-gen of Goblin Verdicts.

Runs inside the FastAPI lifespan as an asyncio task. Checks hourly
whether it's time to pre-generate verdicts (Thursday 8 AM ET for NFL).

Pre-generation ensures users see instant verdicts when they open the app.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Check every hour whether it's time to pre-generate
CHECK_INTERVAL = 60 * 60  # 1 hour

# NFL pre-gen: Thursday at 8 AM Eastern (before Thursday Night Football)
PREGEN_DAY = 3  # Thursday (Monday=0)
PREGEN_HOUR = 8  # 8 AM
ET = timezone(timedelta(hours=-5))  # US Eastern (standard time)

# Cooldown: don't re-run pre-gen within this window
PREGEN_COOLDOWN = 20 * 60 * 60  # 20 hours


class VerdictPregenScheduler:
    """
    Background scheduler for weekly verdict pre-generation.

    Checks hourly if it's the right time (Thursday 8 AM ET) and
    triggers pre-generation for all active users.
    """

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_pregen_at: datetime | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Launch the pre-gen check background task."""
        if self._running:
            logger.warning("Verdict pre-gen scheduler already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Verdict pre-gen scheduler started")

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
        logger.info("Verdict pre-gen scheduler stopped")

    def should_run_now(self) -> bool:
        """Check if it's time to run pre-generation."""
        now_et = datetime.now(ET)

        # Must be the right day and hour
        if now_et.weekday() != PREGEN_DAY:
            return False
        if now_et.hour != PREGEN_HOUR:
            return False

        # Must not have run recently (cooldown)
        if self._last_pregen_at:
            elapsed = (datetime.now(UTC) - self._last_pregen_at).total_seconds()
            if elapsed < PREGEN_COOLDOWN:
                return False

        return True

    async def _run_loop(self) -> None:
        """Check hourly whether to run pre-generation."""
        # Initial delay: 30 seconds
        await asyncio.sleep(30)

        while self._running:
            try:
                if self.should_run_now():
                    logger.info("Verdict pre-generation window — starting")
                    await self._run_pregen()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Verdict pre-gen check error")

            try:
                await asyncio.sleep(CHECK_INTERVAL)
            except asyncio.CancelledError:
                break

    async def _run_pregen(self) -> None:
        """Execute the pre-generation job."""
        from services.goblin_verdict import goblin_verdict_service

        self._last_pregen_at = datetime.now(UTC)
        result = await goblin_verdict_service.pregenerate_all_verdicts()

        logger.info(
            "Verdict pre-gen results: week=%s, users=%d, generated=%d, failed=%d",
            result.get("week"),
            result.get("users", 0),
            result.get("generated", 0),
            result.get("failed", 0),
        )

    async def run_now(self) -> dict:
        """Manually trigger pre-generation (for admin/testing)."""
        from services.goblin_verdict import goblin_verdict_service

        self._last_pregen_at = datetime.now(UTC)
        return await goblin_verdict_service.pregenerate_all_verdicts()


# Singleton
verdict_pregen_scheduler = VerdictPregenScheduler()
