"""Tests for Sleeper Fantasy API service."""

import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from services.sleeper import (
    SleeperLeague,
    SleeperPlayer,
    SleeperRoster,
    SleeperService,
    SleeperSport,
    SleeperUser,
)


def _seed_players_cache(svc: SleeperService, sport: str, data: dict) -> None:
    """Seed the players cache with data and a fresh timestamp."""
    svc._players_cache[sport] = data
    svc._players_cache_ts[sport] = time.monotonic()


@pytest.fixture
def svc():
    return SleeperService()


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.is_closed = False
    return client


def make_response(data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = data
    return resp


class TestSleeperDataclasses:
    def test_sport_enum(self):
        assert SleeperSport.NFL == "nfl"
        assert SleeperSport.NBA == "nba"

    def test_user(self):
        u = SleeperUser(user_id="1", username="test", display_name="Test", avatar=None)
        assert u.user_id == "1"

    def test_league(self):
        lg = SleeperLeague(
            league_id="1",
            name="L",
            sport="nfl",
            season="2024",
            season_type="regular",
            status="in_season",
            total_rosters=12,
            roster_positions=["QB"],
            scoring_settings={},
        )
        assert lg.total_rosters == 12

    def test_roster(self):
        r = SleeperRoster(
            roster_id=1, owner_id="o1", players=["p1"], starters=["p1"], reserve=None
        )
        assert r.players == ["p1"]


class TestParseLeague:
    def test_parse(self, svc):
        data = {
            "league_id": "123",
            "name": "My League",
            "sport": "nfl",
            "season": "2024",
            "season_type": "regular",
            "status": "in_season",
            "total_rosters": 10,
            "roster_positions": ["QB", "RB"],
            "scoring_settings": {"pass_td": 4},
        }
        league = svc._parse_league(data)
        assert league.league_id == "123"
        assert league.name == "My League"
        assert league.total_rosters == 10

    def test_parse_defaults(self, svc):
        league = svc._parse_league({})
        assert league.league_id == ""
        assert league.name == "Unknown League"


class TestGetClient:
    """Tests for _get_client — line 113."""

    @pytest.mark.asyncio
    async def test_creates_new_client_when_none(self, svc):
        """Line 113: creates httpx.AsyncClient when _client is None."""
        assert svc._client is None
        client = await svc._get_client()
        assert client is not None
        assert isinstance(client, httpx.AsyncClient)
        assert svc._client is client
        await client.aclose()

    @pytest.mark.asyncio
    async def test_creates_new_client_when_closed(self, svc):
        """Line 113: creates new client when existing one is closed."""
        old_client = AsyncMock()
        old_client.is_closed = True
        svc._client = old_client
        client = await svc._get_client()
        assert client is not old_client
        assert isinstance(client, httpx.AsyncClient)
        await client.aclose()

    @pytest.mark.asyncio
    async def test_reuses_open_client(self, svc, mock_client):
        """Reuses existing open client."""
        svc._client = mock_client
        client = await svc._get_client()
        assert client is mock_client


class TestGetUser:
    @pytest.mark.asyncio
    async def test_success(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(
            return_value=make_response(
                {
                    "user_id": "123",
                    "username": "testuser",
                    "display_name": "Test User",
                    "avatar": "abc",
                }
            )
        )
        result = await svc.get_user("testuser")
        assert result is not None
        assert result.user_id == "123"
        assert result.username == "testuser"

    @pytest.mark.asyncio
    async def test_not_found(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response(None))
        result = await svc.get_user("nobody")
        assert result is None

    @pytest.mark.asyncio
    async def test_404(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response({}, status=404))
        result = await svc.get_user("nobody")
        assert result is None

    @pytest.mark.asyncio
    async def test_http_error(self, svc, mock_client):
        """Lines 157-158: HTTPError is caught and logged, returns None."""
        svc._client = mock_client
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("connection timeout"))
        result = await svc.get_user("testuser")
        assert result is None


class TestGetUserById:
    @pytest.mark.asyncio
    async def test_success(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(
            return_value=make_response(
                {
                    "user_id": "123",
                    "username": "u",
                    "display_name": "U",
                    "avatar": None,
                }
            )
        )
        result = await svc.get_user_by_id("123")
        assert result.user_id == "123"

    @pytest.mark.asyncio
    async def test_http_error_returns_none(self, svc, mock_client):
        """Lines 178-179: HTTPError is caught with pass, returns None."""
        svc._client = mock_client
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("fail"))
        result = await svc.get_user_by_id("123")
        assert result is None

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self, svc, mock_client):
        """Line 181: return None when status != 200."""
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response({}, status=404))
        result = await svc.get_user_by_id("123")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_data_returns_none(self, svc, mock_client):
        """Line 181: return None when data is falsy."""
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response(None))
        result = await svc.get_user_by_id("123")
        assert result is None


class TestGetUserLeagues:
    @pytest.mark.asyncio
    async def test_success(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(
            return_value=make_response(
                [
                    {
                        "league_id": "1",
                        "name": "L1",
                        "sport": "nfl",
                        "season": "2024",
                        "season_type": "regular",
                        "status": "in_season",
                        "total_rosters": 10,
                        "roster_positions": [],
                        "scoring_settings": {},
                    },
                ]
            )
        )
        result = await svc.get_user_leagues("123")
        assert len(result) == 1
        assert result[0].league_id == "1"

    @pytest.mark.asyncio
    async def test_empty(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response(None))
        result = await svc.get_user_leagues("123")
        assert result == []

    @pytest.mark.asyncio
    async def test_http_error(self, svc, mock_client):
        """Lines 215-216: HTTPError is caught and logged, returns empty list."""
        svc._client = mock_client
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("timeout"))
        result = await svc.get_user_leagues("123")
        assert result == []


class TestGetLeague:
    @pytest.mark.asyncio
    async def test_success(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(
            return_value=make_response(
                {
                    "league_id": "456",
                    "name": "Test",
                    "sport": "nfl",
                    "season": "2024",
                    "total_rosters": 12,
                    "roster_positions": [],
                    "scoring_settings": {},
                }
            )
        )
        result = await svc.get_league("456")
        assert result.league_id == "456"

    @pytest.mark.asyncio
    async def test_not_found(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response(None))
        result = await svc.get_league("999")
        assert result is None

    @pytest.mark.asyncio
    async def test_http_error(self, svc, mock_client):
        """Lines 250-251: HTTPError is caught with pass, returns None."""
        svc._client = mock_client
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("fail"))
        result = await svc.get_league("456")
        assert result is None


class TestGetLeagueUsers:
    @pytest.mark.asyncio
    async def test_success(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(
            return_value=make_response(
                [
                    {
                        "user_id": "u1",
                        "username": "user1",
                        "display_name": "User 1",
                        "avatar": None,
                    },
                    {
                        "user_id": "u2",
                        "username": "user2",
                        "display_name": "User 2",
                        "avatar": None,
                    },
                ]
            )
        )
        result = await svc.get_league_users("123")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_http_error(self, svc, mock_client):
        """Lines 277-278: HTTPError is caught with pass, returns empty list."""
        svc._client = mock_client
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("fail"))
        result = await svc.get_league_users("123")
        assert result == []


class TestGetLeagueRosters:
    @pytest.mark.asyncio
    async def test_success(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(
            return_value=make_response(
                [
                    {
                        "roster_id": 1,
                        "owner_id": "o1",
                        "players": ["p1", "p2"],
                        "starters": ["p1"],
                        "reserve": None,
                    },
                ]
            )
        )
        result = await svc.get_league_rosters("123")
        assert len(result) == 1
        assert result[0].players == ["p1", "p2"]

    @pytest.mark.asyncio
    async def test_http_error(self, svc, mock_client):
        """Lines 307-308: HTTPError is caught with pass, returns empty list."""
        svc._client = mock_client
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("fail"))
        result = await svc.get_league_rosters("123")
        assert result == []


class TestGetUserRoster:
    @pytest.mark.asyncio
    async def test_found(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(
            return_value=make_response(
                [
                    {
                        "roster_id": 1,
                        "owner_id": "o1",
                        "players": ["p1"],
                        "starters": ["p1"],
                        "reserve": None,
                    },
                    {
                        "roster_id": 2,
                        "owner_id": "o2",
                        "players": ["p2"],
                        "starters": ["p2"],
                        "reserve": None,
                    },
                ]
            )
        )
        result = await svc.get_user_roster("123", "o1")
        assert result is not None
        assert result.owner_id == "o1"

    @pytest.mark.asyncio
    async def test_not_found(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(
            return_value=make_response(
                [
                    {
                        "roster_id": 1,
                        "owner_id": "o1",
                        "players": [],
                        "starters": [],
                        "reserve": None,
                    },
                ]
            )
        )
        result = await svc.get_user_roster("123", "o99")
        assert result is None


class TestGetAllPlayers:
    @pytest.mark.asyncio
    async def test_cached(self, svc, mock_client):
        _seed_players_cache(svc, "nfl", {"p1": {"full_name": "Test"}})
        result = await svc.get_all_players("nfl")
        assert result == {"p1": {"full_name": "Test"}}

    @pytest.mark.asyncio
    async def test_fetch(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(
            return_value=make_response({"p1": {"full_name": "Player1"}})
        )
        result = await svc.get_all_players("nfl")
        assert "p1" in result
        # Should be cached now
        assert "nfl" in svc._players_cache

    @pytest.mark.asyncio
    async def test_http_error_returns_stale_cache(self, svc):
        """Lines 365-370: HTTPError with stale cache returns stale data."""
        stale_data = {"stale": {"full_name": "Old Player"}}
        svc._players_cache["nfl"] = stale_data
        svc._players_cache_ts["nfl"] = 0  # expired

        error_client = AsyncMock()
        error_client.get = AsyncMock(side_effect=httpx.ConnectError("api down"))
        svc._get_client = AsyncMock(return_value=error_client)

        result = await svc.get_all_players("nfl")
        assert result is stale_data

    @pytest.mark.asyncio
    async def test_http_error_no_cache_returns_empty(self, svc):
        """Lines 365-372: HTTPError with no stale cache returns {}."""
        error_client = AsyncMock()
        error_client.get = AsyncMock(side_effect=httpx.ConnectError("api down"))
        svc._get_client = AsyncMock(return_value=error_client)

        result = await svc.get_all_players("nfl")
        assert result == {}


class TestGetPlayer:
    @pytest.mark.asyncio
    async def test_found(self, svc):
        _seed_players_cache(
            svc,
            "nfl",
            {
                "p1": {
                    "full_name": "Patrick Mahomes",
                    "first_name": "Patrick",
                    "last_name": "Mahomes",
                    "team": "KC",
                    "position": "QB",
                    "status": "Active",
                    "injury_status": None,
                    "age": 28,
                    "years_exp": 7,
                }
            },
        )
        result = await svc.get_player("p1", "nfl")
        assert result is not None
        assert result.full_name == "Patrick Mahomes"
        assert result.position == "QB"

    @pytest.mark.asyncio
    async def test_not_found(self, svc):
        _seed_players_cache(svc, "nfl", {})
        result = await svc.get_player("missing", "nfl")
        assert result is None


class TestGetPlayersByIds:
    @pytest.mark.asyncio
    async def test_multiple(self, svc):
        _seed_players_cache(
            svc,
            "nfl",
            {
                "p1": {
                    "full_name": "A",
                    "first_name": "A",
                    "last_name": "A",
                    "team": "KC",
                    "position": "QB",
                    "status": "Active",
                },
                "p2": {
                    "full_name": "B",
                    "first_name": "B",
                    "last_name": "B",
                    "team": "SF",
                    "position": "RB",
                    "status": "Active",
                },
            },
        )
        result = await svc.get_players_by_ids(["p1", "p2", "missing"], "nfl")
        assert len(result) == 2


class TestGetTrendingPlayers:
    @pytest.mark.asyncio
    async def test_success(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(
            return_value=make_response(
                [
                    {"player_id": "p1", "count": 100},
                    {"player_id": "p2", "count": 80},
                ]
            )
        )
        result = await svc.get_trending_players("nfl", "add", 10)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response(None))
        result = await svc.get_trending_players()
        assert result == []

    @pytest.mark.asyncio
    async def test_http_error(self, svc, mock_client):
        """Lines 502-505: HTTPError is caught with pass, returns []."""
        svc._client = mock_client
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("fail"))
        result = await svc.get_trending_players()
        assert result == []


class TestGetRosterWithPlayers:
    """Tests for get_roster_with_players — lines 522-527."""

    @pytest.mark.asyncio
    async def test_no_roster_returns_empty(self, svc):
        """Lines 524-525: no roster found -> return []."""
        svc.get_user_roster = AsyncMock(return_value=None)
        result = await svc.get_roster_with_players("lg1", "u999")
        assert result == []
        svc.get_user_roster.assert_awaited_once_with("lg1", "u999")

    @pytest.mark.asyncio
    async def test_has_roster_returns_players(self, svc):
        """Line 527: roster exists -> delegates to get_players_by_ids."""
        roster = SleeperRoster(
            roster_id=1,
            owner_id="u123",
            players=["p1", "p2"],
            starters=["p1"],
            reserve=None,
        )
        player = SleeperPlayer(
            player_id="p1",
            full_name="Patrick Mahomes",
            first_name="Patrick",
            last_name="Mahomes",
            team="KC",
            position="QB",
            sport="nfl",
            status="Active",
            injury_status=None,
            age=28,
            years_exp=7,
        )
        svc.get_user_roster = AsyncMock(return_value=roster)
        svc.get_players_by_ids = AsyncMock(return_value=[player])
        result = await svc.get_roster_with_players("lg1", "u123")
        assert len(result) == 1
        assert result[0].full_name == "Patrick Mahomes"
        svc.get_players_by_ids.assert_awaited_once_with(["p1", "p2"], "nfl")

    @pytest.mark.asyncio
    async def test_custom_sport_forwarded(self, svc):
        """Sport kwarg is forwarded to get_players_by_ids."""
        roster = SleeperRoster(
            roster_id=1,
            owner_id="u123",
            players=["p1"],
            starters=["p1"],
            reserve=None,
        )
        svc.get_user_roster = AsyncMock(return_value=roster)
        svc.get_players_by_ids = AsyncMock(return_value=[])
        await svc.get_roster_with_players("lg1", "u123", sport="nba")
        svc.get_players_by_ids.assert_awaited_once_with(["p1"], "nba")


class TestGetLeagueMatchups:
    @pytest.mark.asyncio
    async def test_success(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(
            return_value=make_response(
                [
                    {"matchup_id": 1, "roster_id": 1, "points": 105.5},
                    {"matchup_id": 1, "roster_id": 2, "points": 98.2},
                ]
            )
        )
        result = await svc.get_league_matchups("123", 1)
        assert len(result) == 2
        assert result[0].matchup_id == 1
        assert result[0].points == 105.5

    @pytest.mark.asyncio
    async def test_empty(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response(None))
        result = await svc.get_league_matchups("123", 1)
        assert result == []

    @pytest.mark.asyncio
    async def test_http_error(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("fail"))
        result = await svc.get_league_matchups("123", 1)
        assert result == []


class TestClose:
    @pytest.mark.asyncio
    async def test_close(self, svc, mock_client):
        svc._client = mock_client
        await svc.close()
        mock_client.aclose.assert_called_once()
        assert svc._client is None

    @pytest.mark.asyncio
    async def test_close_no_client(self, svc):
        await svc.close()  # Should not raise
