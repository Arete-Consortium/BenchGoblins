"""
Notification Trigger Scheduler — Background jobs for push notifications.

Runs inside the FastAPI lifespan as asyncio tasks. Three trigger checkers:
- Injury checker: monitors roster injury status changes (every 15 min)
- Lineup lock checker: reminds users before game lock times (every 30 min)
- Trending checker: alerts about trending waiver wire players (every 60 min)

Requires both DB (for user/token queries) and Redis (for state tracking).
Gracefully degrades if either is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

try:
    from redis.exceptions import RedisError
except ImportError:  # redis not installed locally
    RedisError = Exception  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

# Interval constants (seconds)
INJURY_CHECK_INTERVAL = 15 * 60  # 15 minutes
LINEUP_CHECK_INTERVAL = 30 * 60  # 30 minutes
TRENDING_CHECK_INTERVAL = 60 * 60  # 60 minutes

# Cooldown: don't re-send same notification within this window
NOTIFICATION_COOLDOWN = 6 * 60 * 60  # 6 hours

# Redis TTLs
INJURY_CACHE_TTL = 24 * 60 * 60  # 24 hours
LINEUP_SENT_TTL = 24 * 60 * 60  # 24 hours
TRENDING_CACHE_TTL = 2 * 60 * 60  # 2 hours


class NotificationScheduler:
    """
    Background scheduler for notification triggers.

    Launches asyncio tasks that periodically check for notification-worthy
    events and dispatch push notifications to eligible users.
    """

    def __init__(self):
        self._tasks: list[asyncio.Task] = []
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Launch background trigger tasks."""
        if self._running:
            logger.warning("Notification scheduler already running")
            return

        self._running = True
        self._tasks = [
            asyncio.create_task(
                self._run_loop("injury", INJURY_CHECK_INTERVAL, self._check_injuries)
            ),
            asyncio.create_task(
                self._run_loop("lineup", LINEUP_CHECK_INTERVAL, self._check_lineup_locks)
            ),
            asyncio.create_task(
                self._run_loop("trending", TRENDING_CHECK_INTERVAL, self._check_trending)
            ),
        ]
        logger.info("Notification scheduler started (3 trigger tasks)")

    async def stop(self) -> None:
        """Cancel all background tasks."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        logger.info("Notification scheduler stopped")

    async def _run_loop(self, name: str, interval: int, checker) -> None:
        """Run a checker function on a fixed interval."""
        # Initial delay to stagger checks
        delays = {"injury": 10, "lineup": 20, "trending": 30}
        await asyncio.sleep(delays.get(name, 10))

        while self._running:
            try:
                count = await checker()
                if count:
                    logger.info("Trigger [%s]: sent %d notification(s)", name, count)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Trigger [%s] error", name)

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

    # =========================================================================
    # Eligible User Queries
    # =========================================================================

    async def _get_eligible_users(self, notification_type: str) -> list[dict]:
        """
        Get users with device tokens and matching notification preference enabled.

        Returns list of dicts with keys: user_id, google_id, sleeper_league_id,
        sleeper_user_id, tokens (list of push tokens).
        """
        from services.database import db_service

        if not db_service.is_configured:
            return []

        pref_key = {
            "injury": "injury_alerts",
            "lineup": "lineup_reminders",
            "trending": "trending_players",
        }.get(notification_type)

        if not pref_key:
            return []

        try:
            async with db_service.session() as session:
                # Query users who have device tokens with the preference enabled
                result = await session.execute(
                    text("""
                        SELECT
                            u.google_id,
                            u.sleeper_league_id,
                            u.sleeper_user_id,
                            dt.token,
                            dt.preferences
                        FROM users u
                        JOIN device_tokens dt ON dt.user_id = u.google_id
                        WHERE u.sleeper_league_id IS NOT NULL
                          AND u.sleeper_user_id IS NOT NULL
                          AND dt.token IS NOT NULL
                    """)
                )
                rows = result.all()
        except (SQLAlchemyError, AttributeError):
            logger.exception("Failed to query eligible users for %s", notification_type)
            return []

        # Group by user, filter by preference
        user_map: dict[str, dict] = {}
        for row in rows:
            google_id, league_id, sleeper_uid, token, prefs = row

            # Check preference (default True if no preferences set)
            if prefs and not prefs.get(pref_key, True):
                continue

            if google_id not in user_map:
                user_map[google_id] = {
                    "user_id": google_id,
                    "sleeper_league_id": league_id,
                    "sleeper_user_id": sleeper_uid,
                    "tokens": [],
                }
            user_map[google_id]["tokens"].append(token)

        return list(user_map.values())

    # =========================================================================
    # Cooldown Check (Redis)
    # =========================================================================

    async def _check_cooldown(self, user_id: str, notif_type: str, reference_id: str) -> bool:
        """Check if a notification was recently sent (within cooldown window)."""
        from services.redis import redis_service

        if not redis_service.is_connected:
            return False  # No Redis = no cooldown tracking, allow send

        key = f"notif:cooldown:{user_id}:{notif_type}:{reference_id}"
        try:
            return await redis_service._client.exists(key) > 0
        except RedisError:
            return False

    async def _set_cooldown(self, user_id: str, notif_type: str, reference_id: str) -> None:
        """Mark a notification as sent (set cooldown)."""
        from services.redis import redis_service

        if not redis_service.is_connected:
            return

        key = f"notif:cooldown:{user_id}:{notif_type}:{reference_id}"
        try:
            await redis_service._client.setex(key, NOTIFICATION_COOLDOWN, "1")
        except RedisError:
            pass

    # =========================================================================
    # Notification Log (DB)
    # =========================================================================

    async def _log_notification(
        self, user_id: str, notification_type: str, reference_id: str | None = None
    ) -> None:
        """Record a sent notification in the DB log."""
        from services.database import db_service

        if not db_service.is_configured:
            return

        try:
            async with db_service.session() as session:
                await session.execute(
                    text("""
                        INSERT INTO notification_log (user_id, notification_type, reference_id)
                        VALUES (:user_id, :type, :ref_id)
                    """),
                    {"user_id": user_id, "type": notification_type, "ref_id": reference_id},
                )
        except (SQLAlchemyError, AttributeError):
            logger.exception("Failed to log notification")

    # =========================================================================
    # Trigger: Injury Checker
    # =========================================================================

    async def _check_injuries(self) -> int:
        """
        Check for injury status changes on rostered players.

        Compares current injury_status against Redis cache.
        Sends alert when status changes (new injury, upgrade, downgrade).
        """
        from services.notifications import notification_service
        from services.redis import redis_service
        from services.sleeper import sleeper_service

        if not redis_service.is_connected:
            logger.debug("Injury check skipped: Redis not connected")
            return 0

        users = await self._get_eligible_users("injury")
        if not users:
            return 0

        sent_count = 0

        for user in users:
            try:
                players = await sleeper_service.get_roster_with_players(
                    user["sleeper_league_id"],
                    user["sleeper_user_id"],
                    sport="nfl",
                )

                for player in players:
                    cache_key = f"notif:injury:{user['user_id']}:{player.player_id}"
                    current_status = player.injury_status or ""

                    try:
                        cached_status = await redis_service._client.get(cache_key) or ""
                    except RedisError:
                        cached_status = ""

                    if current_status != cached_status and current_status:
                        # Status changed and player is now injured
                        if await self._check_cooldown(user["user_id"], "injury", player.player_id):
                            continue

                        await notification_service.send_injury_alert(
                            tokens=user["tokens"],
                            player_name=player.full_name,
                            injury_status=current_status,
                            player_id=player.player_id,
                        )
                        await self._set_cooldown(user["user_id"], "injury", player.player_id)
                        await self._log_notification(user["user_id"], "injury", player.player_id)
                        sent_count += 1

                    # Update cache with current status
                    try:
                        await redis_service._client.setex(
                            cache_key, INJURY_CACHE_TTL, current_status
                        )
                    except RedisError:
                        pass

            except Exception:
                logger.exception(
                    "Injury check failed for user %s",
                    user["user_id"][:8] + "...",
                )

        return sent_count

    # =========================================================================
    # Trigger: Lineup Lock Checker
    # =========================================================================

    async def _check_lineup_locks(self) -> int:
        """
        Remind users when lineups are about to lock.

        Checks ESPN schedule for upcoming game times. Sends reminder
        if a game starts within 60 minutes and no reminder sent today.
        """
        from services.espn import espn_service
        from services.notifications import notification_service
        from services.redis import redis_service

        if not redis_service.is_connected:
            logger.debug("Lineup check skipped: Redis not connected")
            return 0

        users = await self._get_eligible_users("lineup")
        if not users:
            return 0

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        sent_count = 0

        for user in users:
            try:
                sent_key = f"notif:lineup:{user['user_id']}:{today}"

                # Check if already reminded today
                try:
                    already_sent = await redis_service._client.exists(sent_key) > 0
                except RedisError:
                    already_sent = False

                if already_sent:
                    continue

                # Check upcoming games via ESPN
                schedule = await espn_service.get_team_schedule("nfl")
                if not schedule:
                    continue

                # Find nearest game time
                now = datetime.now(UTC)
                upcoming_lock = None

                for game in schedule:
                    game_time = game.get("date")
                    if not game_time:
                        continue
                    try:
                        if isinstance(game_time, str):
                            gt = datetime.fromisoformat(game_time.replace("Z", "+00:00"))
                        else:
                            gt = game_time
                        minutes_until = (gt - now).total_seconds() / 60
                        if 0 < minutes_until <= 60:
                            upcoming_lock = gt.strftime("%I:%M %p %Z")
                            break
                    except (ValueError, TypeError):
                        continue

                if upcoming_lock:
                    await notification_service.send_lineup_reminder(
                        tokens=user["tokens"],
                        sport="nfl",
                        lock_time=upcoming_lock,
                    )
                    await self._log_notification(user["user_id"], "lineup_reminder")

                    try:
                        await redis_service._client.setex(sent_key, LINEUP_SENT_TTL, "1")
                    except RedisError:
                        pass

                    sent_count += 1

            except Exception:
                logger.exception(
                    "Lineup check failed for user %s",
                    user["user_id"][:8] + "...",
                )

        return sent_count

    # =========================================================================
    # Trigger: Trending Players Checker
    # =========================================================================

    async def _check_trending(self) -> int:
        """
        Notify users about newly trending waiver wire players.

        Compares current trending list against cached previous list.
        Sends notification about new entries in the top 10.
        """
        from services.notifications import notification_service
        from services.redis import redis_service
        from services.sleeper import sleeper_service

        if not redis_service.is_connected:
            logger.debug("Trending check skipped: Redis not connected")
            return 0

        users = await self._get_eligible_users("trending")
        if not users:
            return 0

        sent_count = 0
        sport = "nfl"

        try:
            trending = await sleeper_service.get_trending_players(sport, "add", 10)
            if not trending:
                return 0

            current_ids = [str(t.get("player_id", "")) for t in trending]
            cache_key = f"notif:trending:{sport}"

            # Get previous trending list
            try:
                cached = await redis_service._client.get(cache_key)
                previous_ids = json.loads(cached) if cached else []
            except (RedisError, json.JSONDecodeError):
                previous_ids = []

            # Find new entries
            new_trending = [pid for pid in current_ids if pid and pid not in previous_ids]

            if new_trending and previous_ids:
                # Only notify if we had a previous list (avoid first-run flood)
                # Enrich with player names
                players = await sleeper_service.get_players_by_ids(new_trending, sport)
                player_names = [p.full_name for p in players[:3]]  # Top 3 names

                if player_names:
                    title = f"Trending in {sport.upper()}"
                    body = f"New trending pickups: {', '.join(player_names)}"

                    for user in users:
                        if await self._check_cooldown(user["user_id"], "trending", sport):
                            continue

                        from services.notifications import PushNotification

                        notifications = [
                            PushNotification(
                                to=token,
                                title=title,
                                body=body,
                                data={
                                    "type": "trending_player",
                                    "sport": sport,
                                    "playerIds": new_trending[:5],
                                },
                                channel_id="trending",
                            )
                            for token in user["tokens"]
                        ]
                        await notification_service.send_batch(notifications)
                        await self._set_cooldown(user["user_id"], "trending", sport)
                        await self._log_notification(user["user_id"], "trending", sport)
                        sent_count += 1

            # Update cache with current list
            try:
                await redis_service._client.setex(
                    cache_key, TRENDING_CACHE_TTL, json.dumps(current_ids)
                )
            except RedisError:
                pass

        except Exception:
            logger.exception("Trending check failed")

        return sent_count


# Singleton instance
notification_scheduler = NotificationScheduler()
