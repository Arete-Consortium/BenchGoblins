"""
Targeted tests to cover remaining gaps in verdict_scheduler (line 83),
stats_enricher (lines 68, 77), espn (lines 483-484, 488-489),
sleeper (lines 372-373), and drip_scheduler (line 64).
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.verdict_scheduler import (
    ET,
    PREGEN_HOUR,
    VerdictPregenScheduler,
)


# =============================================================================
# verdict_scheduler line 83 — cooldown returns False
# =============================================================================


class TestVerdictSchedulerCooldownBranch:
    """Cover the cooldown return-False path (line 83)."""

    def test_cooldown_prevents_rerun(self):
        """When last pregen was recent, should_run_now returns False via cooldown."""
        scheduler = VerdictPregenScheduler()
        # Set last pregen to 1 hour ago (well within 20h cooldown)
        scheduler._last_pregen_at = datetime.now(UTC) - timedelta(hours=1)

        # Thursday 8 AM ET = PREGEN_DAY at PREGEN_HOUR
        fake_thursday_8am = datetime(2026, 3, 5, PREGEN_HOUR, 0, tzinfo=ET)
        fake_utc_now = datetime.now(UTC)

        with patch("services.verdict_scheduler.datetime") as mock_dt:
            # Route datetime.now(tz) to controlled values
            def controlled_now(tz=None):
                if tz == ET:
                    return fake_thursday_8am
                return fake_utc_now

            mock_dt.now = MagicMock(side_effect=controlled_now)
            result = scheduler.should_run_now()

        # Should pass day/hour checks but fail on cooldown
        assert result is False


# =============================================================================
# stats_enricher lines 68, 77 — slug found but no stats
# =============================================================================


class TestStatsEnricherNoStats:
    """Cover branches where slug resolves but get_advanced_stats returns None."""

    @pytest.mark.asyncio
    async def test_nba_slug_found_no_stats(self):
        from services.stats_enricher import _fetch_nba_context

        with (
            patch(
                "services.stats_enricher.bball_ref_service.search_player_slug",
                new_callable=AsyncMock,
                return_value="lebron-james",
            ),
            patch(
                "services.stats_enricher.bball_ref_service.get_advanced_stats",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await _fetch_nba_context("LeBron James")
        assert result is None

    @pytest.mark.asyncio
    async def test_nfl_slug_found_no_stats(self):
        from services.stats_enricher import _fetch_nfl_context

        with (
            patch(
                "services.stats_enricher.pfr_service.search_player_slug",
                new_callable=AsyncMock,
                return_value="patrick-mahomes",
            ),
            patch(
                "services.stats_enricher.pfr_service.get_advanced_stats",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await _fetch_nfl_context("Patrick Mahomes")
        assert result is None


# =============================================================================
# espn lines 483-484, 488-489 — invalid spread/over_under conversion
# =============================================================================


class TestESPNOddsConversionErrors:
    """Cover ValueError/TypeError branches for spread and over_under parsing."""

    @pytest.mark.asyncio
    async def test_invalid_spread_string(self):
        """spread='N/A' should be caught and set to None."""
        from services.espn import ESPNService, _schedule_cache

        svc = ESPNService()

        # Build a future date so the game passes the `game_date < now` filter
        future = "2099-01-01T20:00"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "events": [
                {
                    "id": "401",
                    "date": future,
                    "competitions": [
                        {
                            "competitors": [
                                {
                                    "homeAway": "home",
                                    "team": {
                                        "displayName": "Home Team",
                                        "abbreviation": "HME",
                                    },
                                },
                                {
                                    "homeAway": "away",
                                    "team": {
                                        "displayName": "Away Team",
                                        "abbreviation": "AWY",
                                    },
                                },
                            ],
                            "odds": [
                                {
                                    "spread": "N/A",
                                    "overUnder": "not-a-number",
                                }
                            ],
                        }
                    ],
                }
            ]
        }

        # Clear schedule cache to avoid hitting cached data
        _schedule_cache.clear()

        with patch.object(
            svc.client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            games = await svc.get_team_schedule("TST1", "nfl")

        assert len(games) == 1
        assert games[0].spread is None
        assert games[0].over_under is None

    @pytest.mark.asyncio
    async def test_spread_type_error(self):
        """spread=[] should trigger TypeError and set to None."""
        from services.espn import ESPNService, _schedule_cache

        svc = ESPNService()
        future = "2099-01-02T20:00"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "events": [
                {
                    "id": "402",
                    "date": future,
                    "competitions": [
                        {
                            "competitors": [
                                {
                                    "homeAway": "home",
                                    "team": {
                                        "displayName": "Home Team",
                                        "abbreviation": "HME",
                                    },
                                },
                                {
                                    "homeAway": "away",
                                    "team": {
                                        "displayName": "Away Team",
                                        "abbreviation": "AWY",
                                    },
                                },
                            ],
                            "odds": [
                                {
                                    "spread": [],
                                    "overUnder": {"bad": "data"},
                                }
                            ],
                        }
                    ],
                }
            ]
        }

        _schedule_cache.clear()

        with patch.object(
            svc.client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            games = await svc.get_team_schedule("TST2", "nfl")

        assert len(games) == 1
        assert games[0].spread is None
        assert games[0].over_under is None


# =============================================================================
# sleeper lines 372-373 — stale cache on HTTP error
# =============================================================================


class TestSleeperStaleCache:
    """Cover the stale-cache-on-HTTP-error fallback path."""

    @pytest.mark.asyncio
    async def test_returns_stale_cache_on_http_error(self):
        from services.sleeper import SleeperService

        svc = SleeperService()

        # Pre-populate cache with stale data
        cached_data = {"12345": {"player_id": "12345", "full_name": "Cached Player"}}
        svc._players_cache["nfl"] = cached_data
        # Set cache timestamp to expired (so it doesn't return from TTL check)
        svc._players_cache_ts["nfl"] = 0

        # Create a mock client that raises HTTPError
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("connection failed"))

        with patch.object(
            svc, "_get_client", new_callable=AsyncMock, return_value=mock_client
        ):
            result = await svc.get_all_players("nfl")

        assert result == cached_data


# =============================================================================
# drip_scheduler line 64 — CancelledError breaks run loop
# =============================================================================


class TestDripSchedulerCancelledError:
    """Cover the CancelledError break path in _run_loop."""

    @pytest.mark.asyncio
    async def test_cancelled_error_breaks_loop(self):
        from services.drip_scheduler import DripScheduler

        scheduler = DripScheduler()

        # Mock _process to raise CancelledError (simulates task cancellation)
        with patch.object(
            scheduler,
            "_process",
            new_callable=AsyncMock,
            side_effect=asyncio.CancelledError,
        ):
            # Patch the initial sleep to not wait
            with patch("services.drip_scheduler.asyncio.sleep", new_callable=AsyncMock):
                # Run the loop directly — it should break on CancelledError
                scheduler._running = True
                await scheduler._run_loop()

        # Loop should have exited
        assert scheduler._running is True  # _running not cleared by break


# =============================================================================
# email_drip line 230 — template_fn not found for drip
# =============================================================================


class TestEmailDripNoTemplate:
    """Cover the continue path when template not found."""

    @pytest.mark.asyncio
    async def test_skips_drip_with_no_template(self):
        from services.email_drip import process_pending_drips

        # Create a fake user
        fake_user = MagicMock()
        fake_user.id = 1
        fake_user.email = "test@example.com"
        fake_user.name = "Test User"
        fake_user.created_at = datetime.now(UTC)

        # Mock DB session context manager
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [fake_user]
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("services.email_drip.is_configured", return_value=True):
            with patch("services.email_drip.db_service") as mock_db:
                mock_db.session.return_value = mock_session_ctx
                with (
                    patch(
                        "services.email_drip.check_user_drip",
                        new_callable=AsyncMock,
                        return_value="nonexistent_drip",
                    ),
                    patch(
                        "services.email_drip.DRIP_SEQUENCE",
                        [("nonexistent_drip", 0, "Test Subject", "desc")],
                    ),
                    patch("services.email_drip.TEMPLATES", {}),
                ):
                    result = await process_pending_drips()

        assert result == 0
