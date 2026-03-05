"""
Weekly Recap Scheduler — Auto-generates recaps for all active users.

Runs inside the FastAPI lifespan as an asyncio task. Checks hourly
whether it's time to generate recaps (Sunday 10 AM ET after NFL games).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Check every hour
CHECK_INTERVAL = 60 * 60  # 1 hour

# NFL recap: Sunday 10 AM Eastern (after Sunday games wrap up)
RECAP_DAY = 6  # Sunday (Monday=0)
RECAP_HOUR = 10  # 10 AM
ET = timezone(timedelta(hours=-5))  # US Eastern (standard time)

# Cooldown: don't re-run within this window
RECAP_COOLDOWN = 20 * 60 * 60  # 20 hours


class RecapScheduler:
    """
    Background scheduler for weekly recap auto-generation.

    Checks hourly if it's the right time (Sunday 10 AM ET) and
    triggers recap generation for all active users with decisions.
    """

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_recap_at: datetime | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Launch the recap check background task."""
        if self._running:
            logger.warning("Recap scheduler already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Recap scheduler started")

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
        logger.info("Recap scheduler stopped")

    def should_run_now(self) -> bool:
        """Check if it's time to run recap generation."""
        now_et = datetime.now(ET)

        if now_et.weekday() != RECAP_DAY:
            return False
        if now_et.hour != RECAP_HOUR:
            return False

        if self._last_recap_at:
            elapsed = (datetime.now(UTC) - self._last_recap_at).total_seconds()
            if elapsed < RECAP_COOLDOWN:
                return False

        return True

    async def _run_loop(self) -> None:
        """Check hourly whether to run recap generation."""
        await asyncio.sleep(30)

        while self._running:
            try:
                if self.should_run_now():
                    logger.info("Recap generation window — starting")
                    await self._run_recaps()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Recap scheduler check error")

            try:
                await asyncio.sleep(CHECK_INTERVAL)
            except asyncio.CancelledError:
                break

    async def _run_recaps(self) -> None:
        """Execute recap generation for all users with decisions."""
        from services.database import db_service
        from services.weekly_recap import generate_weekly_recap

        self._last_recap_at = datetime.now(UTC)

        if not db_service.is_configured:
            logger.warning("DB not configured, skipping recap generation")
            return

        generated = 0
        skipped = 0
        failed = 0

        try:
            users = await self._get_active_users()

            for user_id, user_name in users:
                try:
                    async with db_service.session() as session:
                        recap = await generate_weekly_recap(
                            session=session,
                            user_id=user_id,
                            user_name=user_name,
                        )
                        if recap:
                            generated += 1
                        else:
                            skipped += 1
                except Exception:
                    logger.exception("Recap generation failed for user=%s", str(user_id)[:8])
                    failed += 1

        except Exception:
            logger.exception("Recap batch generation failed")

        logger.info(
            "Recap generation complete: %d generated, %d skipped, %d failed",
            generated,
            skipped,
            failed,
        )

    async def _get_active_users(self) -> list[tuple[int, str]]:
        """Get all users who have made decisions (id, name pairs)."""
        from sqlalchemy import text

        from services.database import db_service

        if not db_service.is_configured:
            return []

        try:
            async with db_service.session() as session:
                result = await session.execute(
                    text("""
                        SELECT DISTINCT u.id, u.name
                        FROM users u
                        JOIN decisions d ON d.user_id = CAST(u.id AS TEXT)
                        WHERE d.created_at > NOW() - INTERVAL '7 days'
                    """)
                )
                return [(row[0], row[1] or "Fantasy Manager") for row in result.all()]
        except Exception:
            logger.exception("Failed to fetch active users for recap generation")
            return []

    async def run_now(self) -> dict:
        """Manually trigger recap generation (for admin/testing)."""
        self._last_recap_at = datetime.now(UTC)
        await self._run_recaps()
        return {"status": "complete", "triggered_at": self._last_recap_at.isoformat()}


# Singleton
recap_scheduler = RecapScheduler()
