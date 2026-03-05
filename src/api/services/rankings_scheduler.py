"""
Power Rankings Scheduler — Monday pre-generation of league power rankings.

Runs inside the FastAPI lifespan as an asyncio task. Checks hourly
whether it's time to generate rankings (Monday 9 AM ET after NFL Sunday).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Check every hour
CHECK_INTERVAL = 60 * 60  # 1 hour

# Power rankings: Monday 9 AM Eastern (morning after NFL Sunday)
RANKINGS_DAY = 0  # Monday (Monday=0)
RANKINGS_HOUR = 9  # 9 AM
ET = timezone(timedelta(hours=-5))  # US Eastern (standard time)

# Cooldown: don't re-run within this window
RANKINGS_COOLDOWN = 20 * 60 * 60  # 20 hours

# Redis cache TTL for rankings: 24 hours
RANKINGS_CACHE_TTL = 24 * 60 * 60


class RankingsScheduler:
    """
    Background scheduler for weekly power rankings pre-generation.

    Checks hourly if it's the right time (Monday 9 AM ET) and
    triggers rankings generation for all active leagues.
    """

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_rankings_at: datetime | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Launch the rankings check background task."""
        if self._running:
            logger.warning("Rankings scheduler already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Rankings scheduler started")

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
        logger.info("Rankings scheduler stopped")

    def should_run_now(self) -> bool:
        """Check if it's time to run rankings generation."""
        now_et = datetime.now(ET)

        if now_et.weekday() != RANKINGS_DAY:
            return False
        if now_et.hour != RANKINGS_HOUR:
            return False

        if self._last_rankings_at:
            elapsed = (datetime.now(UTC) - self._last_rankings_at).total_seconds()
            if elapsed < RANKINGS_COOLDOWN:
                return False

        return True

    async def _run_loop(self) -> None:
        """Check hourly whether to run rankings generation."""
        await asyncio.sleep(30)

        while self._running:
            try:
                if self.should_run_now():
                    logger.info("Rankings generation window — starting")
                    await self._run_rankings()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Rankings scheduler check error")

            try:
                await asyncio.sleep(CHECK_INTERVAL)
            except asyncio.CancelledError:
                break

    async def _run_rankings(self) -> None:
        """Generate and cache power rankings for all active leagues."""
        from services.redis import redis_service
        from services.sleeper import sleeper_service

        self._last_rankings_at = datetime.now(UTC)

        leagues = await self._get_active_leagues()
        generated = 0
        failed = 0

        for league_id, external_id in leagues:
            try:
                rosters = await sleeper_service.get_league_rosters(external_id)
                if not rosters:
                    continue

                rankings = []
                for roster in rosters:
                    player_count = len(roster.players) if roster.players else 0
                    starter_count = len(roster.starters) if roster.starters else 0
                    strength = starter_count * 10 + (player_count - starter_count) * 3

                    rankings.append(
                        {
                            "owner_id": roster.owner_id,
                            "roster_size": player_count,
                            "strength_score": round(strength, 1),
                        }
                    )

                rankings.sort(key=lambda r: r["strength_score"], reverse=True)
                for i, r in enumerate(rankings):
                    r["rank"] = i + 1

                # Cache in Redis
                if redis_service.is_connected:
                    cache_key = f"rankings:league:{league_id}"
                    cache_data = {
                        "league_id": league_id,
                        "rankings": rankings,
                        "generated_at": datetime.now(UTC).isoformat(),
                    }
                    try:
                        await redis_service._client.setex(
                            cache_key,
                            RANKINGS_CACHE_TTL,
                            json.dumps(cache_data),
                        )
                    except Exception:
                        logger.debug("Failed to cache rankings for league %s", league_id)

                generated += 1

            except Exception:
                logger.exception("Rankings generation failed for league %s", league_id)
                failed += 1

        logger.info(
            "Rankings generation complete: %d generated, %d failed (%d leagues)",
            generated,
            failed,
            len(leagues),
        )

    async def _get_active_leagues(self) -> list[tuple[int, str]]:
        """Get all leagues with Sleeper integration (id, external_league_id pairs)."""
        from sqlalchemy import text

        from services.database import db_service

        if not db_service.is_configured:
            return []

        try:
            async with db_service.session() as session:
                result = await session.execute(
                    text("""
                        SELECT DISTINCT l.id, l.external_league_id
                        FROM leagues l
                        JOIN league_memberships lm ON lm.league_id = l.id
                        WHERE l.external_league_id IS NOT NULL
                          AND lm.status = 'active'
                    """)
                )
                return [(row[0], row[1]) for row in result.all()]
        except Exception:
            logger.exception("Failed to fetch active leagues for rankings")
            return []

    async def run_now(self) -> dict:
        """Manually trigger rankings generation."""
        self._last_rankings_at = datetime.now(UTC)
        await self._run_rankings()
        return {"status": "complete", "triggered_at": self._last_rankings_at.isoformat()}


# Singleton
rankings_scheduler = RankingsScheduler()
