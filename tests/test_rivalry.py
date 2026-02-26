"""
Tests for rivalry tracking service and routes.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from routes.rivalries import _parse_week_range
from services.sleeper import SleeperMatchup, SleeperRoster


class TestParseWeekRange:
    """Tests for week range parsing utility."""

    def test_simple_range(self):
        assert _parse_week_range("1-4") == [1, 2, 3, 4]

    def test_single_week(self):
        assert _parse_week_range("5") == [5]

    def test_comma_separated(self):
        assert _parse_week_range("1,3,5") == [1, 3, 5]

    def test_mixed(self):
        assert _parse_week_range("1-3,7,10-12") == [1, 2, 3, 7, 10, 11, 12]

    def test_deduplicates(self):
        assert _parse_week_range("1-3,2-4") == [1, 2, 3, 4]

    def test_full_season(self):
        weeks = _parse_week_range("1-18")
        assert len(weeks) == 18
        assert weeks[0] == 1
        assert weeks[-1] == 18


class TestSyncMatchups:
    """Tests for syncing matchup data from Sleeper."""

    @pytest.mark.asyncio
    async def test_sync_pairs_matchups(self):
        """Should pair rosters by matchup_id and upsert."""
        from services.rivalry import sync_matchups

        # Mock rosters
        mock_rosters = [
            SleeperRoster(
                roster_id=1, owner_id="owner_a", players=[], starters=[], reserve=None
            ),
            SleeperRoster(
                roster_id=2, owner_id="owner_b", players=[], starters=[], reserve=None
            ),
        ]

        # Mock matchups for week 1: roster 1 vs roster 2
        mock_matchups = [
            SleeperMatchup(matchup_id=1, roster_id=1, points=120.5),
            SleeperMatchup(matchup_id=1, roster_id=2, points=105.3),
        ]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        with patch("services.rivalry.sleeper_service") as mock_sleeper:
            mock_sleeper.get_league_rosters = AsyncMock(return_value=mock_rosters)
            mock_sleeper.get_league_matchups = AsyncMock(return_value=mock_matchups)

            count = await sync_matchups(
                mock_session,
                league_id=1,
                sleeper_league_id="12345",
                season="2025",
                weeks=[1],
            )

        assert count == 1
        mock_session.execute.assert_called()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_skips_incomplete_matchups(self):
        """Should skip matchup groups without exactly 2 rosters."""
        from services.rivalry import sync_matchups

        mock_rosters = [
            SleeperRoster(
                roster_id=1, owner_id="owner_a", players=[], starters=[], reserve=None
            ),
        ]

        # Only one roster in matchup group
        mock_matchups = [
            SleeperMatchup(matchup_id=1, roster_id=1, points=100.0),
        ]

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        with patch("services.rivalry.sleeper_service") as mock_sleeper:
            mock_sleeper.get_league_rosters = AsyncMock(return_value=mock_rosters)
            mock_sleeper.get_league_matchups = AsyncMock(return_value=mock_matchups)

            count = await sync_matchups(
                mock_session,
                league_id=1,
                sleeper_league_id="12345",
                season="2025",
                weeks=[1],
            )

        assert count == 0

    @pytest.mark.asyncio
    async def test_sync_multiple_weeks(self):
        """Should process all requested weeks."""
        from services.rivalry import sync_matchups

        mock_rosters = [
            SleeperRoster(
                roster_id=1, owner_id="owner_a", players=[], starters=[], reserve=None
            ),
            SleeperRoster(
                roster_id=2, owner_id="owner_b", players=[], starters=[], reserve=None
            ),
        ]

        mock_matchups = [
            SleeperMatchup(matchup_id=1, roster_id=1, points=100.0),
            SleeperMatchup(matchup_id=1, roster_id=2, points=90.0),
        ]

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        with patch("services.rivalry.sleeper_service") as mock_sleeper:
            mock_sleeper.get_league_rosters = AsyncMock(return_value=mock_rosters)
            mock_sleeper.get_league_matchups = AsyncMock(return_value=mock_matchups)

            count = await sync_matchups(
                mock_session,
                league_id=1,
                sleeper_league_id="12345",
                season="2025",
                weeks=[1, 2, 3],
            )

        # 1 matchup per week × 3 weeks
        assert count == 3
        assert mock_sleeper.get_league_matchups.call_count == 3


class TestGetH2HRecord:
    """Tests for head-to-head record retrieval."""

    @pytest.mark.asyncio
    async def test_computes_record(self):
        """Should compute wins, losses, ties from matchup data."""
        from services.rivalry import get_h2h_record

        m1 = MagicMock()
        m1.owner_id_a = "owner_a"
        m1.owner_id_b = "owner_b"
        m1.points_a = Decimal("120.50")
        m1.points_b = Decimal("100.00")
        m1.winner_owner_id = "owner_a"
        m1.season = "2025"
        m1.week = 1

        m2 = MagicMock()
        m2.owner_id_a = "owner_a"
        m2.owner_id_b = "owner_b"
        m2.points_a = Decimal("90.00")
        m2.points_b = Decimal("110.00")
        m2.winner_owner_id = "owner_b"
        m2.season = "2025"
        m2.week = 2

        m3 = MagicMock()
        m3.owner_id_a = "owner_a"
        m3.owner_id_b = "owner_b"
        m3.points_a = Decimal("100.00")
        m3.points_b = Decimal("100.00")
        m3.winner_owner_id = None
        m3.season = "2025"
        m3.week = 3

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [m1, m2, m3]
        mock_session.execute = AsyncMock(return_value=mock_result)

        record = await get_h2h_record(mock_session, 1, "owner_a", "owner_b")

        assert record["wins_a"] == 1
        assert record["wins_b"] == 1
        assert record["ties"] == 1
        assert record["total_points_a"] == 310.5
        assert record["total_points_b"] == 310.0
        assert len(record["matchups"]) == 3

    @pytest.mark.asyncio
    async def test_empty_record(self):
        """Should return zeros when no matchups found."""
        from services.rivalry import get_h2h_record

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        record = await get_h2h_record(mock_session, 1, "owner_a", "owner_b")

        assert record["wins_a"] == 0
        assert record["wins_b"] == 0
        assert record["ties"] == 0
        assert record["matchups"] == []

    @pytest.mark.asyncio
    async def test_handles_reversed_owner_order(self):
        """Should correctly attribute points when owners are in DB order B→A."""
        from services.rivalry import get_h2h_record

        # In DB, owner_b is in position A
        m1 = MagicMock()
        m1.owner_id_a = "owner_b"
        m1.owner_id_b = "owner_a"
        m1.points_a = Decimal("110.00")
        m1.points_b = Decimal("90.00")
        m1.winner_owner_id = "owner_b"
        m1.season = "2025"
        m1.week = 1

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [m1]
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Querying with owner_a first
        record = await get_h2h_record(mock_session, 1, "owner_a", "owner_b")

        assert record["wins_a"] == 0
        assert record["wins_b"] == 1
        assert record["total_points_a"] == 90.0
        assert record["total_points_b"] == 110.0


class TestGetLeagueRivalries:
    """Tests for league-wide rivalry listing."""

    @pytest.mark.asyncio
    async def test_groups_by_owner_pairs(self):
        """Should group matchups by owner pairs and compute stats."""
        from services.rivalry import get_league_rivalries

        m1 = MagicMock()
        m1.owner_id_a = "alpha"
        m1.owner_id_b = "beta"
        m1.points_a = Decimal("100")
        m1.points_b = Decimal("90")
        m1.winner_owner_id = "alpha"

        m2 = MagicMock()
        m2.owner_id_a = "alpha"
        m2.owner_id_b = "beta"
        m2.points_a = Decimal("80")
        m2.points_b = Decimal("110")
        m2.winner_owner_id = "beta"

        m3 = MagicMock()
        m3.owner_id_a = "alpha"
        m3.owner_id_b = "gamma"
        m3.points_a = Decimal("95")
        m3.points_b = Decimal("85")
        m3.winner_owner_id = "alpha"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [m1, m2, m3]
        mock_session.execute = AsyncMock(return_value=mock_result)

        rivalries = await get_league_rivalries(mock_session, 1)

        # alpha vs beta has 2 games, alpha vs gamma has 1
        assert len(rivalries) == 2
        assert rivalries[0]["games_played"] == 2  # Sorted by most games
        assert rivalries[1]["games_played"] == 1


class TestGetUserRivalries:
    """Tests for user-specific rivalry listing."""

    @pytest.mark.asyncio
    async def test_returns_per_opponent_stats(self):
        """Should compute win/loss/tie per opponent."""
        from services.rivalry import get_user_rivalries

        m1 = MagicMock()
        m1.owner_id_a = "me"
        m1.owner_id_b = "opp1"
        m1.winner_owner_id = "me"

        m2 = MagicMock()
        m2.owner_id_a = "me"
        m2.owner_id_b = "opp1"
        m2.winner_owner_id = "opp1"

        m3 = MagicMock()
        m3.owner_id_a = "opp2"
        m3.owner_id_b = "me"
        m3.winner_owner_id = "me"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [m1, m2, m3]
        mock_session.execute = AsyncMock(return_value=mock_result)

        rivalries = await get_user_rivalries(mock_session, 1, "me")

        assert len(rivalries) == 2

        opp1 = next(r for r in rivalries if r["opponent"] == "opp1")
        assert opp1["wins"] == 1
        assert opp1["losses"] == 1
        assert opp1["games_played"] == 2

        opp2 = next(r for r in rivalries if r["opponent"] == "opp2")
        assert opp2["wins"] == 1
        assert opp2["losses"] == 0


class TestSleeperMatchupAPI:
    """Tests for the Sleeper matchup API method."""

    @pytest.mark.asyncio
    async def test_get_league_matchups(self):
        """Should parse matchup data from Sleeper API."""
        from services.sleeper import SleeperService

        service = SleeperService()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"matchup_id": 1, "roster_id": 1, "points": 120.5},
            {"matchup_id": 1, "roster_id": 2, "points": 105.3},
            {"matchup_id": 2, "roster_id": 3, "points": 95.0},
            {"matchup_id": 2, "roster_id": 4, "points": 110.8},
        ]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        service._client = mock_client

        matchups = await service.get_league_matchups("12345", 1)

        assert len(matchups) == 4
        assert matchups[0].matchup_id == 1
        assert matchups[0].roster_id == 1
        assert matchups[0].points == 120.5
        assert matchups[2].matchup_id == 2

    @pytest.mark.asyncio
    async def test_get_league_matchups_empty(self):
        """Should return empty list for no matchups."""
        from services.sleeper import SleeperService

        service = SleeperService()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        service._client = mock_client

        matchups = await service.get_league_matchups("12345", 1)
        assert matchups == []

    @pytest.mark.asyncio
    async def test_get_league_matchups_api_error(self):
        """Should return empty list on API error."""
        import httpx

        from services.sleeper import SleeperService

        service = SleeperService()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("timeout"))
        mock_client.is_closed = False
        service._client = mock_client

        matchups = await service.get_league_matchups("12345", 1)
        assert matchups == []
