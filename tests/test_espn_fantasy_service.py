"""Tests for ESPN Fantasy API service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.espn_fantasy import (
    ESPNCredentials,
    ESPNFantasyService,
    FantasyLeague,
    RosterPlayer,
)


@pytest.fixture
def svc():
    return ESPNFantasyService()


@pytest.fixture
def creds():
    return ESPNCredentials(swid="{ABC-123}", espn_s2="session_token_here")


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


class TestDataclasses:
    def test_credentials(self, creds):
        assert creds.swid == "{ABC-123}"
        assert creds.expires_at is None

    def test_fantasy_league(self):
        lg = FantasyLeague(
            id="1",
            name="L",
            sport="nba",
            season=2025,
            team_count=10,
            scoring_type="STANDARD",
        )
        assert lg.user_team_id is None

    def test_roster_player(self):
        p = RosterPlayer(
            player_id="1",
            espn_id="1",
            name="Test",
            position="PG",
            team="LAL",
            lineup_slot="STARTER",
            acquisition_type="DRAFT",
        )
        assert p.projected_points is None


class TestAuthCookies:
    def test_cookies(self, svc, creds):
        cookies = svc._auth_cookies(creds)
        assert cookies["SWID"] == "{ABC-123}"
        assert cookies["espn_s2"] == "session_token_here"


class TestParseLeague:
    def test_parse(self, svc):
        data = {
            "id": 12345,
            "seasonId": 2025,
            "settings": {
                "name": "My League",
                "size": 10,
                "scoringSettings": {"scoringType": "PPR"},
            },
        }
        result = svc._parse_league(data, "nfl")
        assert result.id == "12345"
        assert result.name == "My League"
        assert result.scoring_type == "PPR"

    def test_parse_defaults(self, svc):
        result = svc._parse_league({}, "nba")
        assert result.name == "Unknown League"

    def test_parse_invalid(self, svc):
        # Missing settings entirely triggers TypeError -> returns None
        result = svc._parse_league({"id": 1}, "nba")
        # No settings key means settings={} via .get default, should still work
        assert result is not None
        assert result.name == "Unknown League"


class TestGetPrimaryPosition:
    def test_nba(self, svc):
        assert svc._get_primary_position([0], "nba") == "PG"
        assert svc._get_primary_position([4], "nba") == "C"
        assert svc._get_primary_position([7], "nba") == "UTIL"

    def test_nfl(self, svc):
        assert svc._get_primary_position([0], "nfl") == "QB"
        assert svc._get_primary_position([2], "nfl") == "RB"
        assert svc._get_primary_position([4], "nfl") == "WR"

    def test_mlb(self, svc):
        assert svc._get_primary_position([14], "mlb") == "SP"

    def test_nhl(self, svc):
        assert svc._get_primary_position([0], "nhl") == "C"
        assert svc._get_primary_position([4], "nhl") == "G"

    def test_unknown_slot(self, svc):
        assert svc._get_primary_position([999], "nba") == "UTIL"

    def test_unknown_sport(self, svc):
        assert svc._get_primary_position([0], "cricket") == "UTIL"

    def test_first_match(self, svc):
        # Should return first matching position
        assert svc._get_primary_position([0, 5], "nba") == "PG"


class TestSlotToName:
    def test_bench(self, svc):
        assert svc._slot_to_name(20, "nba") == "BENCH"
        assert svc._slot_to_name(21, "nfl") == "BENCH"

    def test_ir(self, svc):
        assert svc._slot_to_name(13, "nba") == "IR"

    def test_position_slot(self, svc):
        assert svc._slot_to_name(0, "nba") == "PG"


class TestParseRoster:
    def test_parse(self, svc):
        data = {
            "teams": [
                {
                    "id": 1,
                    "roster": {
                        "entries": [
                            {
                                "playerPoolEntry": {
                                    "player": {
                                        "id": 123,
                                        "fullName": "LeBron James",
                                        "eligibleSlots": [2, 6, 7],
                                        "proTeamId": "LAL",
                                    }
                                },
                                "lineupSlotId": 2,
                                "acquisitionType": "DRAFT",
                            }
                        ]
                    },
                }
            ]
        }
        result = svc._parse_roster(data, 1, "nba")
        assert len(result) == 1
        assert result[0].name == "LeBron James"

    def test_parse_wrong_team(self, svc):
        data = {"teams": [{"id": 1, "roster": {"entries": []}}]}
        result = svc._parse_roster(data, 99, "nba")
        assert result == []

    def test_parse_no_teams(self, svc):
        result = svc._parse_roster({}, 1, "nba")
        assert result == []


class TestGetRoster:
    @pytest.mark.asyncio
    async def test_invalid_sport(self, svc, creds):
        result = await svc.get_roster(creds, "1", 1, "cricket")
        assert result == []


class TestGetLeagueDetails:
    @pytest.mark.asyncio
    async def test_invalid_sport(self, svc, creds):
        result = await svc.get_league_details(creds, "1", "cricket")
        assert result is None


class TestVerifyCredentials:
    @pytest.mark.asyncio
    async def test_valid(self, svc, creds, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response({}, status=200))
        assert await svc.verify_credentials(creds) is True

    @pytest.mark.asyncio
    async def test_invalid(self, svc, creds, mock_client):
        svc._client = mock_client
        mock_client.get = AsyncMock(return_value=make_response({}, status=401))
        assert await svc.verify_credentials(creds) is False


class TestGetUserId:
    @pytest.mark.asyncio
    async def test_extract(self, svc, creds):
        result = await svc.get_user_id(creds)
        assert result == "ABC-123"

    @pytest.mark.asyncio
    async def test_empty_swid(self, svc):
        creds = ESPNCredentials(swid="{}", espn_s2="s")
        result = await svc.get_user_id(creds)
        assert result is None


class TestClose:
    @pytest.mark.asyncio
    async def test_close(self, svc, mock_client):
        svc._client = mock_client
        await svc.close()
        mock_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_no_client(self, svc):
        await svc.close()
