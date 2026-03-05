"""
Outcome Sync Scheduler — Background job for automatic accuracy tracking.

Runs inside the FastAPI lifespan as an asyncio task. Calls
sync_recent_outcomes() daily at a configurable interval to fetch actual
game results from ESPN and record outcomes for past decisions.

Requires DB (for decision queries and updates). Redis not required.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# Default: run every 6 hours (catches morning stats, afternoon updates, evening finalization)
OUTCOME_SYNC_INTERVAL = 6 * 60 * 60  # 6 hours

# How many days back to check for unresolved decisions
OUTCOME_SYNC_DAYS_BACK = 2


class OutcomeScheduler:
    """
    Background scheduler for automatic outcome recording.

    Periodically calls sync_recent_outcomes() to fetch actual fantasy
    points from ESPN and update decision records with outcomes.
    """

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Launch the outcome sync background task."""
        if self._running:
            logger.warning("Outcome scheduler already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Outcome scheduler started (interval=%ds, days_back=%d)",
            OUTCOME_SYNC_INTERVAL,
            OUTCOME_SYNC_DAYS_BACK,
        )

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
        logger.info("Outcome scheduler stopped")

    async def _run_loop(self) -> None:
        """Run outcome sync on a fixed interval."""
        # Initial delay: 60 seconds after startup to let DB settle
        await asyncio.sleep(60)

        while self._running:
            try:
                result = await self._sync_outcomes()
                if result:
                    processed = result.get("total_decisions_processed", 0)
                    recorded = result.get("total_outcomes_recorded", 0)
                    if recorded:
                        logger.info(
                            "Outcome sync: %d processed, %d recorded",
                            processed,
                            recorded,
                        )
                    else:
                        logger.debug(
                            "Outcome sync: %d processed, 0 new outcomes",
                            processed,
                        )
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Outcome sync error")

            try:
                await asyncio.sleep(OUTCOME_SYNC_INTERVAL)
            except asyncio.CancelledError:
                break

    async def _sync_outcomes(self) -> dict | None:
        """Run the actual outcome sync. Returns result dict or None."""
        from services.outcome_recorder import sync_recent_outcomes

        return await sync_recent_outcomes(days_back=OUTCOME_SYNC_DAYS_BACK)


# Singleton instance
outcome_scheduler = OutcomeScheduler()
