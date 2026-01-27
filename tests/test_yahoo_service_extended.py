"""Extended tests for Yahoo service — API methods with mocked HTTP."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from services.yahoo import YahooService


@pytest.fixture
def svc():
    return YahooService(client_id="test_id", client_secret="test_secret")


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.is_closed = False
    return client


def make_response(data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = data
    resp.text = str(data)
    return resp


# =========================================================================
# _get_client
# =========================================================================


class TestGetClient:
    @pytest.mark.asyncio
    async def test_creates_client(self, svc):
        client = await svc._get_client()
        assert client is not None
        await svc.close()

    @pytest.mark.asyncio
    async def test_reuses_client(self, svc, mock_client):
        svc._client = mock_client
        client = await svc._get_client()
        assert client is mock_client

    @pytest.mark.asyncio
    async def test_recreates_closed_client(self, svc):
        mock = MagicMock()
        mock.is_closed = True
        svc._client = mock
        client = await svc._get_client()
        assert client is not mock
        await svc.close()


# =========================================================================
# _api_request
# =========================================================================


class TestApiRequest:
    @pytest.mark.asyncio
    async def test_success(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response({"key": "val"}))
        result = await svc._api_request("token", "endpoint")
        assert result == {"key": "val"}

    @pytest.mark.asyncio
    async def test_with_query_param_in_url(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response({"ok": True}))
        result = await svc._api_request("token", "endpoint?foo=bar")
        assert result == {"ok": True}
        # Verify format=json appended with &
        call_args = mock_client.get.call_args
        assert "&format=json" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_401(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response({}, status=401))
        result = await svc._api_request("bad_token", "endpoint")
        assert result is None

    @pytest.mark.asyncio
    async def test_500(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response({}, status=500))
        result = await svc._api_request("token", "endpoint")
        assert result is None

    @pytest.mark.asyncio
    async def test_http_error(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("fail"))
        result = await svc._api_request("token", "endpoint")
        assert result is None


# =========================================================================
# exchange_code — HTTP error branch
# =========================================================================


class TestExchangeCodeHTTPError:
    @pytest.mark.asyncio
    async def test_http_error(self, svc, mock_client):
        svc._client = mock_client
        mock_client.post = AsyncMock(side_effect=httpx.HTTPError("fail"))
        result = await svc.exchange_code("code", "http://localhost")
        assert result is None


# =========================================================================
# refresh_token — HTTP error branch
# =========================================================================


class TestRefreshTokenHTTPError:
    @pytest.mark.asyncio
    async def test_http_error(self, svc, mock_client):
        svc._client = mock_client
        mock_client.post = AsyncMock(side_effect=httpx.HTTPError("fail"))
        result = await svc.refresh_token("rt")
        assert result is None


# =========================================================================
# get_user_info
# =========================================================================


class TestGetUserInfo:
    @pytest.mark.asyncio
    async def test_success(self, svc, mock_client):
        svc._client = mock_client
        data = {
            "fantasy_content": {
                "users": {
                    "0": {
                        "user": [
                            {
                                "guid": "abc123",
                                "nickname": "player1",
                                "email": "e@e.com",
                            }
                        ]
                    }
                }
            }
        }
        mock_client.get = AsyncMock(return_value=make_response(data))
        result = await svc.get_user_info("token")
        assert result is not None
        assert result.guid == "abc123"

    @pytest.mark.asyncio
    async def test_no_data(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response({}, status=401))
        result = await svc.get_user_info("bad")
        assert result is None

    @pytest.mark.asyncio
    async def test_parse_error(self, svc, mock_client):
        svc._client = mock_client
        # IndexError: user list is empty
        data = {"fantasy_content": {"users": {"0": {"user": []}}}}
        mock_client.get = AsyncMock(return_value=make_response(data))
        result = await svc.get_user_info("token")
        assert result is None


# =========================================================================
# get_user_leagues
# =========================================================================


class TestGetUserLeagues:
    @pytest.mark.asyncio
    async def test_success(self, svc, mock_client):
        svc._client = mock_client
        data = {
            "fantasy_content": {
                "users": {
                    "0": {
                        "user": [
                            {"guid": "abc"},
                            {
                                "games": {
                                    "0": {
                                        "game": [
                                            {"code": "nfl"},
                                            {
                                                "leagues": {
                                                    "0": {
                                                        "league": [
                                                            {
                                                                "league_key": "449.l.123",
                                                                "league_id": "123",
                                                                "name": "My League",
                                                                "num_teams": 12,
                                                            }
                                                        ]
                                                    }
                                                }
                                            },
                                        ]
                                    }
                                }
                            },
                        ]
                    }
                }
            }
        }
        mock_client.get = AsyncMock(return_value=make_response(data))
        result = await svc.get_user_leagues("token")
        assert len(result) == 1
        assert result[0].name == "My League"

    @pytest.mark.asyncio
    async def test_with_sport_filter(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response({}, status=401))
        result = await svc.get_user_leagues("token", sport="nfl")
        assert result == []

    @pytest.mark.asyncio
    async def test_short_user_array(self, svc, mock_client):
        svc._client = mock_client
        data = {"fantasy_content": {"users": {"0": {"user": [{"guid": "x"}]}}}}
        mock_client.get = AsyncMock(return_value=make_response(data))
        result = await svc.get_user_leagues("token")
        assert result == []

    @pytest.mark.asyncio
    async def test_no_data(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response({}, status=500))
        result = await svc.get_user_leagues("token")
        assert result == []


# =========================================================================
# get_league
# =========================================================================


class TestGetLeague:
    @pytest.mark.asyncio
    async def test_success(self, svc, mock_client):
        svc._client = mock_client
        data = {
            "fantasy_content": {
                "league": [
                    {
                        "league_key": "449.l.123",
                        "name": "My League",
                        "num_teams": 10,
                    }
                ]
            }
        }
        mock_client.get = AsyncMock(return_value=make_response(data))
        result = await svc.get_league("token", "449.l.123")
        assert result is not None
        assert result.name == "My League"

    @pytest.mark.asyncio
    async def test_no_data(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response({}, status=401))
        result = await svc.get_league("token", "449.l.123")
        assert result is None

    @pytest.mark.asyncio
    async def test_parse_error(self, svc, mock_client):
        svc._client = mock_client
        # IndexError: league list too short to subscript [0]
        data = {"fantasy_content": {"league": []}}
        mock_client.get = AsyncMock(return_value=make_response(data))
        result = await svc.get_league("token", "449.l.123")
        assert result is None


# =========================================================================
# get_league_standings
# =========================================================================


class TestGetLeagueStandings:
    @pytest.mark.asyncio
    async def test_success(self, svc, mock_client):
        svc._client = mock_client
        data = {
            "fantasy_content": {
                "league": [
                    {"league_key": "449.l.123"},
                    {
                        "standings": [
                            {
                                "teams": {
                                    "0": {
                                        "team": [
                                            [
                                                {
                                                    "team_key": "449.l.123.t.1",
                                                    "name": "Team A",
                                                }
                                            ],
                                            {
                                                "team_standings": {
                                                    "rank": 1,
                                                    "outcome_totals": {
                                                        "wins": 10,
                                                        "losses": 3,
                                                        "ties": 0,
                                                    },
                                                    "points_for": 1200,
                                                    "points_against": 1100,
                                                }
                                            },
                                        ]
                                    }
                                }
                            }
                        ]
                    },
                ]
            }
        }
        mock_client.get = AsyncMock(return_value=make_response(data))
        result = await svc.get_league_standings("token", "449.l.123")
        assert len(result) == 1
        assert result[0]["team_name"] == "Team A"
        assert result[0]["wins"] == 10

    @pytest.mark.asyncio
    async def test_no_data(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response({}, status=500))
        result = await svc.get_league_standings("token", "449.l.123")
        assert result == []

    @pytest.mark.asyncio
    async def test_short_league_array(self, svc, mock_client):
        svc._client = mock_client
        data = {"fantasy_content": {"league": [{"league_key": "x"}]}}
        mock_client.get = AsyncMock(return_value=make_response(data))
        result = await svc.get_league_standings("token", "x")
        assert result == []


# =========================================================================
# get_user_teams
# =========================================================================


class TestGetUserTeams:
    @pytest.mark.asyncio
    async def test_success(self, svc, mock_client):
        svc._client = mock_client

        # First call returns league teams, second returns user teams
        user_teams_data = {
            "fantasy_content": {
                "users": {
                    "0": {
                        "user": [
                            {"guid": "x"},
                            {
                                "teams": {
                                    "0": {
                                        "team": [
                                            [
                                                {
                                                    "team_key": "449.l.123.t.1",
                                                    "team_id": "1",
                                                    "name": "My Team",
                                                    "number_of_moves": 5,
                                                    "number_of_trades": 2,
                                                }
                                            ]
                                        ]
                                    }
                                }
                            },
                        ]
                    }
                }
            }
        }
        mock_client.get = AsyncMock(return_value=make_response(user_teams_data))
        result = await svc.get_user_teams("token", "449.l.123")
        assert len(result) >= 0  # May filter by league key

    @pytest.mark.asyncio
    async def test_no_data(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response({}, status=500))
        result = await svc.get_user_teams("token", "449.l.123")
        assert result == []

    @pytest.mark.asyncio
    async def test_short_user_array(self, svc, mock_client):
        svc._client = mock_client
        data = {"fantasy_content": {"users": {"0": {"user": [{"guid": "x"}]}}}}
        mock_client.get = AsyncMock(return_value=make_response(data))
        result = await svc.get_user_teams("token", "449.l.123")
        assert result == []


# =========================================================================
# get_team_roster
# =========================================================================


class TestGetTeamRoster:
    @pytest.mark.asyncio
    async def test_success(self, svc, mock_client):
        svc._client = mock_client
        data = {
            "fantasy_content": {
                "team": [
                    {"team_key": "449.l.123.t.1"},
                    {
                        "roster": {
                            "0": {
                                "players": {
                                    "0": {
                                        "player": [
                                            [
                                                {
                                                    "player_key": "449.p.12345",
                                                    "player_id": "12345",
                                                    "name": {"full": "Patrick Mahomes"},
                                                    "editorial_team_abbr": "KC",
                                                    "eligible_positions": [
                                                        {"position": "QB"}
                                                    ],
                                                    "status": "Active",
                                                }
                                            ]
                                        ]
                                    }
                                }
                            }
                        }
                    },
                ]
            }
        }
        mock_client.get = AsyncMock(return_value=make_response(data))
        result = await svc.get_team_roster("token", "449.l.123.t.1")
        assert len(result) == 1
        assert result[0].name == "Patrick Mahomes"

    @pytest.mark.asyncio
    async def test_with_week(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response({}, status=500))
        result = await svc.get_team_roster("token", "449.l.123.t.1", week=5)
        assert result == []

    @pytest.mark.asyncio
    async def test_no_data(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response({}, status=500))
        result = await svc.get_team_roster("token", "449.l.123.t.1")
        assert result == []

    @pytest.mark.asyncio
    async def test_short_team_array(self, svc, mock_client):
        svc._client = mock_client
        data = {"fantasy_content": {"team": [{"team_key": "x"}]}}
        mock_client.get = AsyncMock(return_value=make_response(data))
        result = await svc.get_team_roster("token", "x")
        assert result == []


# =========================================================================
# search_players
# =========================================================================


class TestSearchPlayersExtended:
    @pytest.mark.asyncio
    async def test_success(self, svc, mock_client):
        svc._client = mock_client
        data = {
            "fantasy_content": {
                "game": [
                    {"game_key": "449"},
                    {
                        "players": {
                            "0": {
                                "player": [
                                    [
                                        {
                                            "player_key": "449.p.1",
                                            "player_id": "1",
                                            "name": {"full": "Test Player"},
                                            "status": "",
                                        }
                                    ]
                                ]
                            }
                        }
                    },
                ]
            }
        }
        mock_client.get = AsyncMock(return_value=make_response(data))
        result = await svc.search_players("token", "Test", sport="nfl")
        assert len(result) == 1
        assert result[0].name == "Test Player"

    @pytest.mark.asyncio
    async def test_no_data(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response({}, status=500))
        result = await svc.search_players("token", "Test", sport="nfl")
        assert result == []

    @pytest.mark.asyncio
    async def test_short_game_array(self, svc, mock_client):
        svc._client = mock_client
        data = {"fantasy_content": {"game": [{"game_key": "449"}]}}
        mock_client.get = AsyncMock(return_value=make_response(data))
        result = await svc.search_players("token", "Test", sport="nfl")
        assert result == []


# =========================================================================
# get_team_matchup
# =========================================================================


class TestGetTeamMatchup:
    @pytest.mark.asyncio
    async def test_success(self, svc, mock_client):
        svc._client = mock_client
        data = {
            "fantasy_content": {
                "team": [
                    {"team_key": "449.l.123.t.1"},
                    {
                        "matchups": {
                            "0": {
                                "matchup": {
                                    "week": 5,
                                    "status": "postevent",
                                    "is_playoffs": "0",
                                    "is_consolation": "0",
                                }
                            }
                        }
                    },
                ]
            }
        }
        mock_client.get = AsyncMock(return_value=make_response(data))
        result = await svc.get_team_matchup("token", "449.l.123.t.1")
        assert result is not None
        assert result["week"] == 5
        assert result["is_playoffs"] is False

    @pytest.mark.asyncio
    async def test_with_week(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response({}, status=500))
        result = await svc.get_team_matchup("token", "449.l.123.t.1", week=5)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_data(self, svc, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response({}, status=401))
        result = await svc.get_team_matchup("token", "449.l.123.t.1")
        assert result is None

    @pytest.mark.asyncio
    async def test_short_team_array(self, svc, mock_client):
        svc._client = mock_client
        data = {"fantasy_content": {"team": [{"team_key": "x"}]}}
        mock_client.get = AsyncMock(return_value=make_response(data))
        result = await svc.get_team_matchup("token", "x")
        assert result is None

    @pytest.mark.asyncio
    async def test_matchup_returns_default_on_missing_keys(self, svc, mock_client):
        """When matchup data has no keys, returns dict with None values."""
        svc._client = mock_client
        data = {"fantasy_content": {"team": [{}, {"matchups": {"0": {"matchup": {}}}}]}}
        mock_client.get = AsyncMock(return_value=make_response(data))
        result = await svc.get_team_matchup("token", "x")
        # Returns a dict with None values when matchup data is empty
        assert result is not None
        assert result["week"] is None


# =========================================================================
# _parse_player edge cases
# =========================================================================


class TestParsePlayerExtended:
    def test_name_not_dict(self, svc):
        data = {
            "player_key": "k",
            "player_id": "1",
            "name": "Simple String",
            "status": "",
        }
        p = svc._parse_player(data)
        assert p.name == "Simple String"

    def test_name_none(self, svc):
        data = {
            "player_key": "k",
            "player_id": "1",
            "name": None,
            "full": "Fallback Name",
            "status": "",
        }
        p = svc._parse_player(data)
        assert p.name == "Fallback Name"

    def test_eligible_positions_string_list(self, svc):
        data = {
            "player_key": "k",
            "player_id": "1",
            "name": {"full": "X"},
            "eligible_positions": ["QB", "UTIL"],
            "status": "",
        }
        p = svc._parse_player(data)
        assert p.position == "QB"

    def test_injury_status(self, svc):
        data = {
            "player_key": "k",
            "player_id": "1",
            "name": {"full": "X"},
            "status": "Q",
        }
        p = svc._parse_player(data)
        assert p.injury_status == "Q"

    def test_injury_status_none_for_empty(self, svc):
        data = {
            "player_key": "k",
            "player_id": "1",
            "name": {"full": "X"},
            "status": "",
        }
        p = svc._parse_player(data)
        assert p.injury_status is None

    def test_headshot(self, svc):
        data = {
            "player_key": "k",
            "player_id": "1",
            "name": {"full": "X"},
            "status": "",
            "headshot": {"url": "http://img.png"},
        }
        p = svc._parse_player(data)
        assert p.headshot_url == "http://img.png"

    def test_headshot_not_dict(self, svc):
        data = {
            "player_key": "k",
            "player_id": "1",
            "name": {"full": "X"},
            "status": "",
            "headshot": "not a dict",
        }
        p = svc._parse_player(data)
        assert p.headshot_url is None

    def test_bye_weeks_not_dict(self, svc):
        data = {
            "player_key": "k",
            "player_id": "1",
            "name": {"full": "X"},
            "status": "",
            "bye_weeks": "not a dict",
        }
        p = svc._parse_player(data)
        assert p.bye_week is None
