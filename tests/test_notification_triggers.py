"""
Tests for the notification trigger scheduler.

Covers: NotificationScheduler lifecycle, eligible user queries,
cooldown/log helpers, injury checker, lineup lock checker, trending checker,
and graceful degradation.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from services.notification_triggers import (
    INJURY_CACHE_TTL,
    INJURY_CHECK_INTERVAL,
    LINEUP_CHECK_INTERVAL,
    NOTIFICATION_COOLDOWN,
    TRENDING_CACHE_TTL,
    TRENDING_CHECK_INTERVAL,
    NotificationScheduler,
)
from services.sleeper import SleeperPlayer

# Patch targets — lazy imports resolve from the source module, not
# notification_triggers. We must patch at the source.
_REDIS = "services.redis.redis_service"
_DB = "services.database.db_service"
_SLEEPER = "services.sleeper.sleeper_service"
_NOTIF = "services.notifications.notification_service"
_ESPN = "services.espn.espn_service"


# =============================================================================
# FIXTURES
# =============================================================================


def _make_player(
    player_id: str,
    name: str,
    position: str,
    team: str = "NYG",
    injury_status: str | None = None,
) -> SleeperPlayer:
    """Helper to create a SleeperPlayer."""
    return SleeperPlayer(
        player_id=player_id,
        full_name=name,
        first_name=name.split()[0],
        last_name=name.split()[-1],
        team=team,
        position=position,
        sport="nfl",
        status="Active",
        injury_status=injury_status,
        age=25,
        years_exp=3,
    )


def _make_eligible_user(
    user_id: str = "user123",
    league_id: str = "league456",
    sleeper_uid: str = "sleeper789",
    tokens: list[str] | None = None,
) -> dict:
    """Helper to create an eligible user dict."""
    return {
        "user_id": user_id,
        "sleeper_league_id": league_id,
        "sleeper_user_id": sleeper_uid,
        "tokens": tokens or ["ExponentPushToken[abc]"],
    }


# =============================================================================
# SCHEDULER LIFECYCLE
# =============================================================================


class TestSchedulerLifecycle:
    """Tests for start/stop and running state."""

    def test_initial_state(self):
        scheduler = NotificationScheduler()
        assert not scheduler.is_running
        assert scheduler._tasks == []

    @pytest.mark.asyncio
    async def test_start_sets_running(self):
        scheduler = NotificationScheduler()
        await scheduler.start()
        assert scheduler.is_running
        assert len(scheduler._tasks) == 3
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_state(self):
        scheduler = NotificationScheduler()
        await scheduler.start()
        await scheduler.stop()
        assert not scheduler.is_running
        assert scheduler._tasks == []

    @pytest.mark.asyncio
    async def test_double_start_warns(self):
        scheduler = NotificationScheduler()
        await scheduler.start()
        with patch("services.notification_triggers.logger") as mock_logger:
            await scheduler.start()
            mock_logger.warning.assert_called_once()
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        scheduler = NotificationScheduler()
        await scheduler.stop()  # Should not error
        assert not scheduler.is_running


# =============================================================================
# CONSTANTS
# =============================================================================


class TestConstants:
    """Verify interval and TTL constants."""

    def test_injury_interval(self):
        assert INJURY_CHECK_INTERVAL == 15 * 60

    def test_lineup_interval(self):
        assert LINEUP_CHECK_INTERVAL == 30 * 60

    def test_trending_interval(self):
        assert TRENDING_CHECK_INTERVAL == 60 * 60

    def test_cooldown(self):
        assert NOTIFICATION_COOLDOWN == 6 * 60 * 60

    def test_injury_cache_ttl(self):
        assert INJURY_CACHE_TTL == 24 * 60 * 60

    def test_trending_cache_ttl(self):
        assert TRENDING_CACHE_TTL == 2 * 60 * 60


# =============================================================================
# ELIGIBLE USERS
# =============================================================================


class TestEligibleUsers:
    """Tests for _get_eligible_users()."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_db_not_configured(self):
        scheduler = NotificationScheduler()
        with patch(_DB) as mock_db:
            mock_db.is_configured = False
            result = await scheduler._get_eligible_users("injury")
            assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_for_unknown_type(self):
        scheduler = NotificationScheduler()
        with patch(_DB) as mock_db:
            mock_db.is_configured = True
            result = await scheduler._get_eligible_users("unknown_type")
            assert result == []

    @pytest.mark.asyncio
    async def test_groups_tokens_by_user(self):
        scheduler = NotificationScheduler()

        # Simulate DB returning rows: same user, two tokens
        mock_rows = [
            ("user1", "league1", "sleeper1", "token_a", {"injury_alerts": True}),
            ("user1", "league1", "sleeper1", "token_b", {"injury_alerts": True}),
        ]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(_DB) as mock_db:
            mock_db.is_configured = True
            mock_db.session = MagicMock(
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_session),
                    __aexit__=AsyncMock(return_value=False),
                )
            )

            result = await scheduler._get_eligible_users("injury")

        assert len(result) == 1
        assert result[0]["user_id"] == "user1"
        assert result[0]["tokens"] == ["token_a", "token_b"]

    @pytest.mark.asyncio
    async def test_filters_by_preference(self):
        scheduler = NotificationScheduler()

        # User with injury_alerts disabled
        mock_rows = [
            ("user1", "league1", "sleeper1", "token_a", {"injury_alerts": False}),
        ]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(_DB) as mock_db:
            mock_db.is_configured = True
            mock_db.session = MagicMock(
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_session),
                    __aexit__=AsyncMock(return_value=False),
                )
            )

            result = await scheduler._get_eligible_users("injury")

        assert result == []

    @pytest.mark.asyncio
    async def test_default_true_when_no_preferences(self):
        scheduler = NotificationScheduler()

        # Preferences is None -> defaults to True
        mock_rows = [
            ("user1", "league1", "sleeper1", "token_a", None),
        ]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(_DB) as mock_db:
            mock_db.is_configured = True
            mock_db.session = MagicMock(
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_session),
                    __aexit__=AsyncMock(return_value=False),
                )
            )

            result = await scheduler._get_eligible_users("injury")

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_handles_db_error(self):
        scheduler = NotificationScheduler()

        with patch(_DB) as mock_db:
            mock_db.is_configured = True
            mock_db.session = MagicMock(
                return_value=AsyncMock(
                    __aenter__=AsyncMock(side_effect=SQLAlchemyError("DB down")),
                    __aexit__=AsyncMock(return_value=False),
                )
            )

            result = await scheduler._get_eligible_users("injury")

        assert result == []


# =============================================================================
# COOLDOWN
# =============================================================================


class TestCooldown:
    """Tests for _check_cooldown() and _set_cooldown()."""

    @pytest.mark.asyncio
    async def test_cooldown_returns_false_when_no_redis(self):
        scheduler = NotificationScheduler()
        with patch(_REDIS) as mock_redis:
            mock_redis.is_connected = False
            result = await scheduler._check_cooldown("user1", "injury", "player1")
            assert result is False

    @pytest.mark.asyncio
    async def test_cooldown_returns_true_when_key_exists(self):
        scheduler = NotificationScheduler()
        mock_client = AsyncMock()
        mock_client.exists = AsyncMock(return_value=1)

        with patch(_REDIS) as mock_redis:
            mock_redis.is_connected = True
            mock_redis._client = mock_client
            result = await scheduler._check_cooldown("user1", "injury", "player1")
            assert result is True

    @pytest.mark.asyncio
    async def test_cooldown_returns_false_when_key_missing(self):
        scheduler = NotificationScheduler()
        mock_client = AsyncMock()
        mock_client.exists = AsyncMock(return_value=0)

        with patch(_REDIS) as mock_redis:
            mock_redis.is_connected = True
            mock_redis._client = mock_client
            result = await scheduler._check_cooldown("user1", "injury", "player1")
            assert result is False

    @pytest.mark.asyncio
    async def test_set_cooldown_calls_setex(self):
        scheduler = NotificationScheduler()
        mock_client = AsyncMock()

        with patch(_REDIS) as mock_redis:
            mock_redis.is_connected = True
            mock_redis._client = mock_client
            await scheduler._set_cooldown("user1", "injury", "player1")

        mock_client.setex.assert_called_once_with(
            "notif:cooldown:user1:injury:player1",
            NOTIFICATION_COOLDOWN,
            "1",
        )

    @pytest.mark.asyncio
    async def test_set_cooldown_noop_when_no_redis(self):
        scheduler = NotificationScheduler()
        with patch(_REDIS) as mock_redis:
            mock_redis.is_connected = False
            await scheduler._set_cooldown("user1", "injury", "player1")
            # Should not error


# =============================================================================
# NOTIFICATION LOG
# =============================================================================


class TestNotificationLog:
    """Tests for _log_notification()."""

    @pytest.mark.asyncio
    async def test_log_inserts_to_db(self):
        scheduler = NotificationScheduler()
        mock_session = AsyncMock()

        with patch(_DB) as mock_db:
            mock_db.is_configured = True
            mock_db.session = MagicMock(
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_session),
                    __aexit__=AsyncMock(return_value=False),
                )
            )

            await scheduler._log_notification("user1", "injury", "player1")

        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_noop_when_db_not_configured(self):
        scheduler = NotificationScheduler()
        with patch(_DB) as mock_db:
            mock_db.is_configured = False
            await scheduler._log_notification("user1", "injury")
            # Should not error

    @pytest.mark.asyncio
    async def test_log_handles_db_error(self):
        scheduler = NotificationScheduler()

        with patch(_DB) as mock_db:
            mock_db.is_configured = True
            mock_db.session = MagicMock(
                return_value=AsyncMock(
                    __aenter__=AsyncMock(side_effect=SQLAlchemyError("DB write error")),
                    __aexit__=AsyncMock(return_value=False),
                )
            )

            await scheduler._log_notification("user1", "injury")
            # Should not raise


# =============================================================================
# INJURY CHECKER
# =============================================================================


class TestInjuryChecker:
    """Tests for _check_injuries()."""

    @pytest.mark.asyncio
    async def test_skips_when_redis_not_connected(self):
        scheduler = NotificationScheduler()
        with patch(_REDIS) as mock_redis:
            mock_redis.is_connected = False
            result = await scheduler._check_injuries()
            assert result == 0

    @pytest.mark.asyncio
    async def test_skips_when_no_eligible_users(self):
        scheduler = NotificationScheduler()
        with (
            patch(_REDIS) as mock_redis,
            patch.object(scheduler, "_get_eligible_users", return_value=[]),
        ):
            mock_redis.is_connected = True
            result = await scheduler._check_injuries()
            assert result == 0

    @pytest.mark.asyncio
    async def test_sends_alert_on_new_injury(self):
        scheduler = NotificationScheduler()
        user = _make_eligible_user()
        player = _make_player(
            "p1", "Saquon Barkley", "RB", injury_status="Questionable"
        )

        mock_redis_client = AsyncMock()
        mock_redis_client.get = AsyncMock(return_value="")  # No previous status
        mock_redis_client.setex = AsyncMock()
        mock_redis_client.exists = AsyncMock(return_value=0)  # No cooldown

        with (
            patch(_REDIS) as mock_redis,
            patch(_SLEEPER) as mock_sleeper,
            patch(_NOTIF) as mock_notif,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
            patch.object(scheduler, "_log_notification", new_callable=AsyncMock),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_sleeper.get_roster_with_players = AsyncMock(return_value=[player])
            mock_notif.send_injury_alert = AsyncMock(return_value=[])

            result = await scheduler._check_injuries()

        assert result == 1
        mock_notif.send_injury_alert.assert_called_once_with(
            tokens=["ExponentPushToken[abc]"],
            player_name="Saquon Barkley",
            injury_status="Questionable",
            player_id="p1",
        )

    @pytest.mark.asyncio
    async def test_skips_when_status_unchanged(self):
        scheduler = NotificationScheduler()
        user = _make_eligible_user()
        player = _make_player(
            "p1", "Saquon Barkley", "RB", injury_status="Questionable"
        )

        mock_redis_client = AsyncMock()
        mock_redis_client.get = AsyncMock(return_value="Questionable")  # Same status
        mock_redis_client.setex = AsyncMock()

        with (
            patch(_REDIS) as mock_redis,
            patch(_SLEEPER) as mock_sleeper,
            patch(_NOTIF) as mock_notif,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_sleeper.get_roster_with_players = AsyncMock(return_value=[player])

            result = await scheduler._check_injuries()

        assert result == 0
        mock_notif.send_injury_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_cooldown_active(self):
        scheduler = NotificationScheduler()
        user = _make_eligible_user()
        player = _make_player("p1", "Saquon Barkley", "RB", injury_status="Out")

        mock_redis_client = AsyncMock()
        mock_redis_client.get = AsyncMock(return_value="")  # Status changed
        mock_redis_client.setex = AsyncMock()
        mock_redis_client.exists = AsyncMock(return_value=1)  # Cooldown active

        with (
            patch(_REDIS) as mock_redis,
            patch(_SLEEPER) as mock_sleeper,
            patch(_NOTIF) as mock_notif,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_sleeper.get_roster_with_players = AsyncMock(return_value=[player])

            result = await scheduler._check_injuries()

        assert result == 0
        mock_notif.send_injury_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_player_with_no_injury(self):
        scheduler = NotificationScheduler()
        user = _make_eligible_user()
        player = _make_player("p1", "Healthy Player", "WR", injury_status=None)

        mock_redis_client = AsyncMock()
        mock_redis_client.get = AsyncMock(return_value="")
        mock_redis_client.setex = AsyncMock()

        with (
            patch(_REDIS) as mock_redis,
            patch(_SLEEPER) as mock_sleeper,
            patch(_NOTIF) as mock_notif,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_sleeper.get_roster_with_players = AsyncMock(return_value=[player])

            result = await scheduler._check_injuries()

        assert result == 0
        mock_notif.send_injury_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_sleeper_api_error(self):
        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        with (
            patch(_REDIS) as mock_redis,
            patch(_SLEEPER) as mock_sleeper,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
        ):
            mock_redis.is_connected = True
            mock_redis._client = AsyncMock()
            mock_sleeper.get_roster_with_players = AsyncMock(
                side_effect=RuntimeError("API down")
            )

            result = await scheduler._check_injuries()

        assert result == 0  # Should not crash

    @pytest.mark.asyncio
    async def test_updates_cache_even_when_no_change(self):
        scheduler = NotificationScheduler()
        user = _make_eligible_user()
        player = _make_player("p1", "Player", "QB", injury_status=None)

        mock_redis_client = AsyncMock()
        mock_redis_client.get = AsyncMock(return_value="")
        mock_redis_client.setex = AsyncMock()

        with (
            patch(_REDIS) as mock_redis,
            patch(_SLEEPER) as mock_sleeper,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_sleeper.get_roster_with_players = AsyncMock(return_value=[player])

            await scheduler._check_injuries()

        # Should have called setex to update cache
        mock_redis_client.setex.assert_called_once()


# =============================================================================
# LINEUP LOCK CHECKER
# =============================================================================


class TestLineupLockChecker:
    """Tests for _check_lineup_locks()."""

    @pytest.mark.asyncio
    async def test_skips_when_redis_not_connected(self):
        scheduler = NotificationScheduler()
        with patch(_REDIS) as mock_redis:
            mock_redis.is_connected = False
            result = await scheduler._check_lineup_locks()
            assert result == 0

    @pytest.mark.asyncio
    async def test_skips_when_no_eligible_users(self):
        scheduler = NotificationScheduler()
        with (
            patch(_REDIS) as mock_redis,
            patch.object(scheduler, "_get_eligible_users", return_value=[]),
        ):
            mock_redis.is_connected = True
            result = await scheduler._check_lineup_locks()
            assert result == 0

    @pytest.mark.asyncio
    async def test_skips_when_already_reminded_today(self):
        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        mock_redis_client = AsyncMock()
        mock_redis_client.exists = AsyncMock(return_value=1)  # Already sent

        with (
            patch(_REDIS) as mock_redis,
            patch(_NOTIF) as mock_notif,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client

            result = await scheduler._check_lineup_locks()

        assert result == 0
        mock_notif.send_lineup_reminder.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_reminder_when_game_within_60_min(self):
        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        # Game starting in 30 minutes
        now = datetime.now(UTC)
        game_time = (now + timedelta(minutes=30)).isoformat()

        mock_redis_client = AsyncMock()
        mock_redis_client.exists = AsyncMock(return_value=0)
        mock_redis_client.setex = AsyncMock()

        with (
            patch(_REDIS) as mock_redis,
            patch(_ESPN) as mock_espn,
            patch(_NOTIF) as mock_notif,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
            patch.object(scheduler, "_log_notification", new_callable=AsyncMock),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_espn.get_team_schedule = AsyncMock(return_value=[{"date": game_time}])
            mock_notif.send_lineup_reminder = AsyncMock(return_value=[])

            result = await scheduler._check_lineup_locks()

        assert result == 1
        mock_notif.send_lineup_reminder.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_when_no_upcoming_games(self):
        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        # Game starting in 3 hours (outside 60-min window)
        now = datetime.now(UTC)
        game_time = (now + timedelta(hours=3)).isoformat()

        mock_redis_client = AsyncMock()
        mock_redis_client.exists = AsyncMock(return_value=0)

        with (
            patch(_REDIS) as mock_redis,
            patch(_ESPN) as mock_espn,
            patch(_NOTIF) as mock_notif,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_espn.get_team_schedule = AsyncMock(return_value=[{"date": game_time}])

            result = await scheduler._check_lineup_locks()

        assert result == 0
        mock_notif.send_lineup_reminder.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_empty_schedule(self):
        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        mock_redis_client = AsyncMock()
        mock_redis_client.exists = AsyncMock(return_value=0)

        with (
            patch(_REDIS) as mock_redis,
            patch(_ESPN) as mock_espn,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_espn.get_team_schedule = AsyncMock(return_value=[])

            result = await scheduler._check_lineup_locks()

        assert result == 0

    @pytest.mark.asyncio
    async def test_handles_espn_error(self):
        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        mock_redis_client = AsyncMock()
        mock_redis_client.exists = AsyncMock(return_value=0)

        with (
            patch(_REDIS) as mock_redis,
            patch(_ESPN) as mock_espn,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_espn.get_team_schedule = AsyncMock(
                side_effect=RuntimeError("ESPN down")
            )

            result = await scheduler._check_lineup_locks()

        assert result == 0


# =============================================================================
# TRENDING CHECKER
# =============================================================================


class TestTrendingChecker:
    """Tests for _check_trending()."""

    @pytest.mark.asyncio
    async def test_skips_when_redis_not_connected(self):
        scheduler = NotificationScheduler()
        with patch(_REDIS) as mock_redis:
            mock_redis.is_connected = False
            result = await scheduler._check_trending()
            assert result == 0

    @pytest.mark.asyncio
    async def test_skips_when_no_eligible_users(self):
        scheduler = NotificationScheduler()
        with (
            patch(_REDIS) as mock_redis,
            patch.object(scheduler, "_get_eligible_users", return_value=[]),
        ):
            mock_redis.is_connected = True
            result = await scheduler._check_trending()
            assert result == 0

    @pytest.mark.asyncio
    async def test_skips_first_run_no_previous_list(self):
        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        mock_redis_client = AsyncMock()
        mock_redis_client.get = AsyncMock(return_value=None)  # No previous list
        mock_redis_client.setex = AsyncMock()
        mock_redis_client.exists = AsyncMock(return_value=0)

        with (
            patch(_REDIS) as mock_redis,
            patch(_SLEEPER) as mock_sleeper,
            patch(_NOTIF),
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_sleeper.get_trending_players = AsyncMock(
                return_value=[{"player_id": "p1"}, {"player_id": "p2"}]
            )

            result = await scheduler._check_trending()

        assert result == 0  # First run, no notifications
        # But should cache the current list
        mock_redis_client.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_sends_notification_on_new_trending(self):
        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        mock_redis_client = AsyncMock()
        mock_redis_client.get = AsyncMock(
            return_value=json.dumps(["p1", "p2"])  # Previous list
        )
        mock_redis_client.setex = AsyncMock()
        mock_redis_client.exists = AsyncMock(return_value=0)  # No cooldown

        player = _make_player("p3", "New Trending Guy", "WR")

        with (
            patch(_REDIS) as mock_redis,
            patch(_SLEEPER) as mock_sleeper,
            patch(_NOTIF) as mock_notif,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
            patch.object(scheduler, "_log_notification", new_callable=AsyncMock),
            patch.object(scheduler, "_set_cooldown", new_callable=AsyncMock),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_sleeper.get_trending_players = AsyncMock(
                return_value=[{"player_id": "p1"}, {"player_id": "p3"}]
            )
            mock_sleeper.get_players_by_ids = AsyncMock(return_value=[player])
            mock_notif.send_batch = AsyncMock(return_value=[])

            result = await scheduler._check_trending()

        assert result == 1
        mock_notif.send_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_when_no_new_trending(self):
        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        mock_redis_client = AsyncMock()
        mock_redis_client.get = AsyncMock(return_value=json.dumps(["p1", "p2"]))
        mock_redis_client.setex = AsyncMock()

        with (
            patch(_REDIS) as mock_redis,
            patch(_SLEEPER) as mock_sleeper,
            patch(_NOTIF),
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_sleeper.get_trending_players = AsyncMock(
                return_value=[{"player_id": "p1"}, {"player_id": "p2"}]  # Same list
            )

            result = await scheduler._check_trending()

        assert result == 0

    @pytest.mark.asyncio
    async def test_skips_when_cooldown_active(self):
        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        mock_redis_client = AsyncMock()
        mock_redis_client.get = AsyncMock(return_value=json.dumps(["p1"]))
        mock_redis_client.setex = AsyncMock()
        mock_redis_client.exists = AsyncMock(return_value=1)  # Cooldown active

        player = _make_player("p2", "New Player", "QB")

        with (
            patch(_REDIS) as mock_redis,
            patch(_SLEEPER) as mock_sleeper,
            patch(_NOTIF),
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_sleeper.get_trending_players = AsyncMock(
                return_value=[{"player_id": "p1"}, {"player_id": "p2"}]
            )
            mock_sleeper.get_players_by_ids = AsyncMock(return_value=[player])

            result = await scheduler._check_trending()

        assert result == 0

    @pytest.mark.asyncio
    async def test_handles_sleeper_error(self):
        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        with (
            patch(_REDIS) as mock_redis,
            patch(_SLEEPER) as mock_sleeper,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
        ):
            mock_redis.is_connected = True
            mock_redis._client = AsyncMock()
            mock_sleeper.get_trending_players = AsyncMock(
                side_effect=RuntimeError("Sleeper API down")
            )

            result = await scheduler._check_trending()

        assert result == 0

    @pytest.mark.asyncio
    async def test_skips_when_trending_empty(self):
        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        with (
            patch(_REDIS) as mock_redis,
            patch(_SLEEPER) as mock_sleeper,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
        ):
            mock_redis.is_connected = True
            mock_redis._client = AsyncMock()
            mock_sleeper.get_trending_players = AsyncMock(return_value=[])

            result = await scheduler._check_trending()

        assert result == 0


# =============================================================================
# RUN LOOP
# =============================================================================


class TestRunLoop:
    """Tests for _run_loop() error handling."""

    @pytest.mark.asyncio
    async def test_run_loop_handles_checker_exception(self):
        """Verify _run_loop continues after checker raises."""
        scheduler = NotificationScheduler()
        scheduler._running = True

        call_count = 0
        real_sleep = asyncio.sleep

        async def failing_checker():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Boom")
            scheduler._running = False
            return 0

        async def fast_sleep(_seconds):
            await real_sleep(0)

        with patch(
            "services.notification_triggers.asyncio.sleep", side_effect=fast_sleep
        ):
            task = asyncio.create_task(
                scheduler._run_loop("test", 0.01, failing_checker)
            )
            # Wait for task to complete (checker stops loop on 2nd call)
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()

        assert call_count >= 2  # Ran twice despite exception on first

    @pytest.mark.asyncio
    async def test_run_loop_logs_sent_count(self):
        """Verify _run_loop logs notification count."""
        scheduler = NotificationScheduler()
        scheduler._running = True

        real_sleep = asyncio.sleep

        async def checker_with_results():
            scheduler._running = False
            return 5

        async def fast_sleep(_seconds):
            await real_sleep(0)

        with (
            patch(
                "services.notification_triggers.asyncio.sleep", side_effect=fast_sleep
            ),
            patch("services.notification_triggers.logger") as mock_logger,
        ):
            task = asyncio.create_task(
                scheduler._run_loop("test", 0.01, checker_with_results)
            )
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()

        mock_logger.info.assert_any_call(
            "Trigger [%s]: sent %d notification(s)", "test", 5
        )

    @pytest.mark.asyncio
    async def test_run_loop_stops_on_cancel(self):
        """Verify _run_loop exits cleanly on CancelledError."""
        scheduler = NotificationScheduler()
        scheduler._running = True

        real_sleep = asyncio.sleep

        async def slow_checker():
            await real_sleep(10)  # Block forever
            return 0

        async def fast_sleep(seconds):
            if seconds >= 1:
                # Let initial delay pass but block on checker's sleep
                raise asyncio.CancelledError
            await real_sleep(0)

        with patch(
            "services.notification_triggers.asyncio.sleep", side_effect=fast_sleep
        ):
            task = asyncio.create_task(scheduler._run_loop("test", 60, slow_checker))
            await asyncio.sleep(0.01)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # If we get here without hanging, the test passes


# =============================================================================
# IMPORT FALLBACK (Lines 25-26)
# =============================================================================


class TestImportFallback:
    """Test the ImportError fallback for redis.exceptions.RedisError."""

    def test_redis_import_fallback(self):
        """When redis is not installed, RedisError falls back to Exception."""
        import importlib
        import sys

        # Temporarily block the redis package
        with patch.dict(sys.modules, {"redis": None, "redis.exceptions": None}):
            mod = importlib.import_module("services.notification_triggers")
            importlib.reload(mod)
            assert mod.RedisError is Exception

        # Restore the module to normal state
        importlib.reload(mod)


# =============================================================================
# RUN LOOP — CancelledError branches (Lines 102, 108-109)
# =============================================================================


class TestRunLoopCancelledError:
    """Tests for CancelledError handling in _run_loop."""

    @pytest.mark.asyncio
    async def test_run_loop_breaks_on_checker_cancelled_error(self):
        """CancelledError from checker breaks the loop (line 102)."""
        scheduler = NotificationScheduler()
        scheduler._running = True

        async def cancelling_checker():
            raise asyncio.CancelledError

        real_sleep = asyncio.sleep

        async def fast_sleep(_seconds):
            await real_sleep(0)

        with patch(
            "services.notification_triggers.asyncio.sleep", side_effect=fast_sleep
        ):
            task = asyncio.create_task(
                scheduler._run_loop("test", 1, cancelling_checker)
            )
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()

        # Task should have completed (broke out of loop)

    @pytest.mark.asyncio
    async def test_run_loop_breaks_on_sleep_cancelled_error(self):
        """CancelledError from interval sleep breaks the loop (lines 108-109)."""
        scheduler = NotificationScheduler()
        scheduler._running = True

        call_count = 0
        sleep_call_count = 0
        real_sleep = asyncio.sleep

        async def checker():
            nonlocal call_count
            call_count += 1
            return 0

        async def sleep_with_cancel(seconds):
            nonlocal sleep_call_count
            sleep_call_count += 1
            if sleep_call_count == 1:
                # First call is the initial stagger delay — let it through
                await real_sleep(0)
            else:
                # Second call is the interval sleep — cancel here
                raise asyncio.CancelledError

        with patch(
            "services.notification_triggers.asyncio.sleep",
            side_effect=sleep_with_cancel,
        ):
            task = asyncio.create_task(scheduler._run_loop("test", 60, checker))
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()

        assert call_count >= 1


# =============================================================================
# COOLDOWN — RedisError branches (Lines 193-194, 206-207)
# =============================================================================


class TestCooldownRedisErrors:
    """Tests for RedisError handling in cooldown methods."""

    @pytest.mark.asyncio
    async def test_check_cooldown_returns_false_on_redis_error(self):
        """RedisError in _check_cooldown returns False (lines 193-194)."""
        from redis.exceptions import RedisError as RealRedisError

        scheduler = NotificationScheduler()
        mock_client = AsyncMock()
        mock_client.exists = AsyncMock(side_effect=RealRedisError("connection lost"))

        with patch(_REDIS) as mock_redis:
            mock_redis.is_connected = True
            mock_redis._client = mock_client
            result = await scheduler._check_cooldown("user1", "injury", "player1")
            assert result is False

    @pytest.mark.asyncio
    async def test_set_cooldown_swallows_redis_error(self):
        """RedisError in _set_cooldown is silently caught (lines 206-207)."""
        from redis.exceptions import RedisError as RealRedisError

        scheduler = NotificationScheduler()
        mock_client = AsyncMock()
        mock_client.setex = AsyncMock(side_effect=RealRedisError("connection lost"))

        with patch(_REDIS) as mock_redis:
            mock_redis.is_connected = True
            mock_redis._client = mock_client
            # Should not raise
            await scheduler._set_cooldown("user1", "injury", "player1")


# =============================================================================
# INJURY CHECKER — RedisError branches (Lines 273-274, 296-297)
# =============================================================================


class TestInjuryCheckerRedisErrors:
    """Tests for RedisError handling within _check_injuries."""

    @pytest.mark.asyncio
    async def test_redis_error_on_get_cached_status(self):
        """RedisError when reading cached injury status defaults to '' (lines 273-274)."""
        from redis.exceptions import RedisError as RealRedisError

        scheduler = NotificationScheduler()
        user = _make_eligible_user()
        player = _make_player("p1", "Test Player", "RB", injury_status="Doubtful")

        mock_redis_client = AsyncMock()
        # Redis get fails -> cached_status defaults to ""
        mock_redis_client.get = AsyncMock(side_effect=RealRedisError("read error"))
        mock_redis_client.setex = AsyncMock()
        mock_redis_client.exists = AsyncMock(return_value=0)  # No cooldown

        with (
            patch(_REDIS) as mock_redis,
            patch(_SLEEPER) as mock_sleeper,
            patch(_NOTIF) as mock_notif,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
            patch.object(scheduler, "_log_notification", new_callable=AsyncMock),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_sleeper.get_roster_with_players = AsyncMock(return_value=[player])
            mock_notif.send_injury_alert = AsyncMock(return_value=[])

            result = await scheduler._check_injuries()

        # Should still send because cached_status="" != current_status="Doubtful"
        assert result == 1
        mock_notif.send_injury_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_error_on_cache_update_setex(self):
        """RedisError when updating injury cache is silently caught (lines 296-297)."""
        from redis.exceptions import RedisError as RealRedisError

        scheduler = NotificationScheduler()
        user = _make_eligible_user()
        # Player with no injury — won't trigger notification but will try cache update
        player = _make_player("p1", "Healthy Player", "QB", injury_status=None)

        mock_redis_client = AsyncMock()
        mock_redis_client.get = AsyncMock(return_value="")
        # Cache update setex fails
        mock_redis_client.setex = AsyncMock(side_effect=RealRedisError("write error"))

        with (
            patch(_REDIS) as mock_redis,
            patch(_SLEEPER) as mock_sleeper,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_sleeper.get_roster_with_players = AsyncMock(return_value=[player])

            # Should not raise despite RedisError on setex
            result = await scheduler._check_injuries()

        assert result == 0


# =============================================================================
# LINEUP LOCK CHECKER — RedisError + edge cases (Lines 340-341, 358, 363, 368-369, 381-382)
# =============================================================================


class TestLineupLockRedisErrors:
    """Tests for RedisError and edge-case handling in _check_lineup_locks."""

    @pytest.mark.asyncio
    async def test_redis_error_on_exists_check(self):
        """RedisError when checking already_sent defaults to False (lines 340-341)."""
        from redis.exceptions import RedisError as RealRedisError

        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        # Game starting in 30 minutes
        now = datetime.now(UTC)
        game_time = (now + timedelta(minutes=30)).isoformat()

        mock_redis_client = AsyncMock()
        # exists() raises RedisError -> already_sent defaults to False, continues
        mock_redis_client.exists = AsyncMock(side_effect=RealRedisError("read error"))
        mock_redis_client.setex = AsyncMock()

        with (
            patch(_REDIS) as mock_redis,
            patch(_ESPN) as mock_espn,
            patch(_NOTIF) as mock_notif,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
            patch.object(scheduler, "_log_notification", new_callable=AsyncMock),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_espn.get_team_schedule = AsyncMock(return_value=[{"date": game_time}])
            mock_notif.send_lineup_reminder = AsyncMock(return_value=[])

            result = await scheduler._check_lineup_locks()

        # Should send because already_sent defaults to False
        assert result == 1

    @pytest.mark.asyncio
    async def test_skips_game_with_no_date(self):
        """Games with no 'date' key are skipped (line 358)."""
        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        mock_redis_client = AsyncMock()
        mock_redis_client.exists = AsyncMock(return_value=0)

        with (
            patch(_REDIS) as mock_redis,
            patch(_ESPN) as mock_espn,
            patch(_NOTIF) as mock_notif,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            # Schedule entry with no 'date' key
            mock_espn.get_team_schedule = AsyncMock(
                return_value=[{"name": "Game 1"}, {"date": None}]
            )

            result = await scheduler._check_lineup_locks()

        assert result == 0
        mock_notif.send_lineup_reminder.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_datetime_object_game_time(self):
        """When game_time is already a datetime object, not a string (line 363)."""
        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        now = datetime.now(UTC)
        game_dt = now + timedelta(minutes=30)  # datetime object, not string

        mock_redis_client = AsyncMock()
        mock_redis_client.exists = AsyncMock(return_value=0)
        mock_redis_client.setex = AsyncMock()

        with (
            patch(_REDIS) as mock_redis,
            patch(_ESPN) as mock_espn,
            patch(_NOTIF) as mock_notif,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
            patch.object(scheduler, "_log_notification", new_callable=AsyncMock),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            # Return a datetime object, not a string
            mock_espn.get_team_schedule = AsyncMock(return_value=[{"date": game_dt}])
            mock_notif.send_lineup_reminder = AsyncMock(return_value=[])

            result = await scheduler._check_lineup_locks()

        assert result == 1
        mock_notif.send_lineup_reminder.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_invalid_date_format(self):
        """Invalid date string triggers ValueError -> continue (lines 368-369)."""
        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        mock_redis_client = AsyncMock()
        mock_redis_client.exists = AsyncMock(return_value=0)

        with (
            patch(_REDIS) as mock_redis,
            patch(_ESPN) as mock_espn,
            patch(_NOTIF) as mock_notif,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_espn.get_team_schedule = AsyncMock(
                return_value=[{"date": "not-a-real-date"}]
            )

            result = await scheduler._check_lineup_locks()

        assert result == 0
        mock_notif.send_lineup_reminder.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_non_subtractable_game_time(self):
        """TypeError on datetime subtraction -> continue (lines 368-369)."""
        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        mock_redis_client = AsyncMock()
        mock_redis_client.exists = AsyncMock(return_value=0)

        with (
            patch(_REDIS) as mock_redis,
            patch(_ESPN) as mock_espn,
            patch(_NOTIF) as mock_notif,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            # An integer is not a string and not a datetime — causes TypeError
            # in (gt - now).total_seconds()
            mock_espn.get_team_schedule = AsyncMock(return_value=[{"date": 12345}])

            result = await scheduler._check_lineup_locks()

        assert result == 0
        mock_notif.send_lineup_reminder.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_error_on_setex_after_send(self):
        """RedisError when marking reminder as sent is caught (lines 381-382)."""
        from redis.exceptions import RedisError as RealRedisError

        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        now = datetime.now(UTC)
        game_time = (now + timedelta(minutes=30)).isoformat()

        mock_redis_client = AsyncMock()
        mock_redis_client.exists = AsyncMock(return_value=0)
        # setex raises after notification is sent
        mock_redis_client.setex = AsyncMock(side_effect=RealRedisError("write error"))

        with (
            patch(_REDIS) as mock_redis,
            patch(_ESPN) as mock_espn,
            patch(_NOTIF) as mock_notif,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
            patch.object(scheduler, "_log_notification", new_callable=AsyncMock),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_espn.get_team_schedule = AsyncMock(return_value=[{"date": game_time}])
            mock_notif.send_lineup_reminder = AsyncMock(return_value=[])

            # Should not raise despite RedisError on setex
            result = await scheduler._check_lineup_locks()

        assert result == 1
        mock_notif.send_lineup_reminder.assert_called_once()


# =============================================================================
# TRENDING CHECKER — RedisError branches (Lines 432-433, 478-479)
# =============================================================================


class TestTrendingCheckerRedisErrors:
    """Tests for RedisError handling within _check_trending."""

    @pytest.mark.asyncio
    async def test_redis_error_on_get_previous_list(self):
        """RedisError when reading cached trending list defaults to [] (lines 432-433)."""
        from redis.exceptions import RedisError as RealRedisError

        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        mock_redis_client = AsyncMock()
        mock_redis_client.get = AsyncMock(side_effect=RealRedisError("read error"))
        mock_redis_client.setex = AsyncMock()

        with (
            patch(_REDIS) as mock_redis,
            patch(_SLEEPER) as mock_sleeper,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_sleeper.get_trending_players = AsyncMock(
                return_value=[{"player_id": "p1"}]
            )

            result = await scheduler._check_trending()

        # previous_ids defaults to [] so no notifications (first-run guard)
        assert result == 0

    @pytest.mark.asyncio
    async def test_json_decode_error_on_cached_trending(self):
        """JSONDecodeError when parsing cached trending list defaults to [] (lines 432-433)."""
        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        mock_redis_client = AsyncMock()
        mock_redis_client.get = AsyncMock(return_value="not-valid-json{{{")
        mock_redis_client.setex = AsyncMock()

        with (
            patch(_REDIS) as mock_redis,
            patch(_SLEEPER) as mock_sleeper,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_sleeper.get_trending_players = AsyncMock(
                return_value=[{"player_id": "p1"}]
            )

            result = await scheduler._check_trending()

        # previous_ids defaults to [] so no notifications (first-run guard)
        assert result == 0

    @pytest.mark.asyncio
    async def test_redis_error_on_trending_cache_update(self):
        """RedisError when updating trending cache is caught (lines 478-479)."""
        from redis.exceptions import RedisError as RealRedisError

        scheduler = NotificationScheduler()
        user = _make_eligible_user()

        mock_redis_client = AsyncMock()
        mock_redis_client.get = AsyncMock(return_value=json.dumps(["p1"]))
        # setex for cache update fails
        mock_redis_client.setex = AsyncMock(side_effect=RealRedisError("write error"))
        mock_redis_client.exists = AsyncMock(return_value=0)

        player = _make_player("p2", "New Player", "WR")

        with (
            patch(_REDIS) as mock_redis,
            patch(_SLEEPER) as mock_sleeper,
            patch(_NOTIF) as mock_notif,
            patch.object(scheduler, "_get_eligible_users", return_value=[user]),
            patch.object(scheduler, "_log_notification", new_callable=AsyncMock),
            patch.object(scheduler, "_set_cooldown", new_callable=AsyncMock),
        ):
            mock_redis.is_connected = True
            mock_redis._client = mock_redis_client
            mock_sleeper.get_trending_players = AsyncMock(
                return_value=[{"player_id": "p1"}, {"player_id": "p2"}]
            )
            mock_sleeper.get_players_by_ids = AsyncMock(return_value=[player])
            mock_notif.send_batch = AsyncMock(return_value=[])

            # Should not raise despite RedisError on setex
            result = await scheduler._check_trending()

        # Notification still sent, just cache update failed
        assert result == 1
