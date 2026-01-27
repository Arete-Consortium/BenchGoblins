"""Tests for Yahoo Fantasy API service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.yahoo import (
    YahooLeague,
    YahooService,
    YahooSport,
    YahooToken,
    YahooUser,
)


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


class TestDataclasses:
    def test_sport_enum(self):
        assert YahooSport.NFL == "nfl"
        assert YahooSport.NBA == "nba"

    def test_token(self):
        t = YahooToken(
            access_token="at",
            refresh_token="rt",
            token_type="bearer",
            expires_in=3600,
            expires_at=1000.0,
        )
        assert t.access_token == "at"

    def test_user(self):
        u = YahooUser(guid="g1", nickname="nick", email="e@e.com")
        assert u.guid == "g1"

    def test_league(self):
        lg = YahooLeague(
            league_key="k",
            league_id="1",
            name="L",
            sport="nfl",
            season="2024",
            num_teams=12,
            scoring_type="head",
            current_week=5,
            start_week=1,
            end_week=17,
            draft_status="postdraft",
        )
        assert lg.num_teams == 12


class TestGetAuthUrl:
    def test_basic(self, svc):
        url = svc.get_auth_url("http://localhost/callback")
        assert "client_id=test_id" in url
        assert "redirect_uri=http" in url
        assert "response_type=code" in url

    def test_with_state(self, svc):
        url = svc.get_auth_url("http://localhost/callback", state="abc123")
        assert "state=abc123" in url


class TestParseLeague:
    def test_parse(self, svc):
        data = {
            "league_key": "449.l.123",
            "league_id": "123",
            "name": "My League",
            "season": "2024",
            "num_teams": 10,
            "scoring_type": "head",
            "current_week": 5,
        }
        league = svc._parse_league(data, "nfl")
        assert league.league_key == "449.l.123"
        assert league.sport == "nfl"

    def test_parse_defaults(self, svc):
        league = svc._parse_league({}, "")
        assert league.name == "Unknown League"
        assert league.num_teams == 0


class TestParseTeam:
    def test_parse(self, svc):
        data = {
            "team_key": "449.l.123.t.1",
            "team_id": "1",
            "name": "My Team",
            "number_of_moves": 5,
            "number_of_trades": 2,
        }
        team = svc._parse_team(data)
        assert team.team_key == "449.l.123.t.1"
        assert team.number_of_moves == 5

    def test_parse_with_logo(self, svc):
        data = {
            "team_key": "k",
            "team_id": "1",
            "name": "T",
            "team_logos": [{"url": "http://logo.png"}],
            "number_of_moves": 0,
            "number_of_trades": 0,
        }
        team = svc._parse_team(data)
        assert team.logo_url == "http://logo.png"

    def test_parse_no_logo(self, svc):
        data = {
            "team_key": "k",
            "team_id": "1",
            "name": "T",
            "number_of_moves": 0,
            "number_of_trades": 0,
        }
        team = svc._parse_team(data)
        assert team.logo_url is None


class TestParsePlayer:
    def test_parse_with_name_dict(self, svc):
        data = {
            "player_key": "449.p.12345",
            "player_id": "12345",
            "name": {"full": "Patrick Mahomes"},
            "editorial_team_abbr": "KC",
            "eligible_positions": [{"position": "QB"}],
            "status": "Active",
        }
        player = svc._parse_player(data)
        assert player.name == "Patrick Mahomes"
        assert player.position == "QB"

    def test_parse_with_display_position(self, svc):
        data = {
            "player_key": "k",
            "player_id": "1",
            "name": {"full": "Test"},
            "display_position": "RB",
            "eligible_positions": [],
            "status": "",
        }
        player = svc._parse_player(data)
        assert player.position == "RB"

    def test_parse_with_bye_week(self, svc):
        data = {
            "player_key": "k",
            "player_id": "1",
            "name": {"full": "Test"},
            "status": "",
            "bye_weeks": {"week": 10},
        }
        player = svc._parse_player(data)
        assert player.bye_week == 10


class TestExchangeCode:
    @pytest.mark.asyncio
    async def test_success(self, svc, mock_client):
        svc._client = mock_client
        mock_client.post = AsyncMock(
            return_value=make_response(
                {
                    "access_token": "at",
                    "refresh_token": "rt",
                    "token_type": "bearer",
                    "expires_in": 3600,
                }
            )
        )
        result = await svc.exchange_code("code123", "http://localhost/callback")
        assert result is not None
        assert result.access_token == "at"

    @pytest.mark.asyncio
    async def test_failure(self, svc, mock_client):
        svc._client = mock_client
        mock_client.post = AsyncMock(return_value=make_response({}, status=400))
        result = await svc.exchange_code("bad", "http://localhost/callback")
        assert result is None


class TestRefreshToken:
    @pytest.mark.asyncio
    async def test_success(self, svc, mock_client):
        svc._client = mock_client
        mock_client.post = AsyncMock(
            return_value=make_response(
                {
                    "access_token": "new_at",
                    "refresh_token": "new_rt",
                    "token_type": "bearer",
                    "expires_in": 3600,
                }
            )
        )
        result = await svc.refresh_token("old_rt")
        assert result is not None
        assert result.access_token == "new_at"

    @pytest.mark.asyncio
    async def test_failure(self, svc, mock_client):
        svc._client = mock_client
        mock_client.post = AsyncMock(return_value=make_response({}, status=401))
        result = await svc.refresh_token("bad")
        assert result is None


class TestSearchPlayers:
    @pytest.mark.asyncio
    async def test_unknown_sport(self, svc):
        result = await svc.search_players("token", "test", sport="cricket")
        assert result == []


class TestClose:
    @pytest.mark.asyncio
    async def test_close(self, svc, mock_client):
        svc._client = mock_client
        await svc.close()
        mock_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_no_client(self, svc):
        await svc.close()
