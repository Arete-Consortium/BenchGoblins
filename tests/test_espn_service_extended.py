"""Extended tests for ESPN service — covers async methods and remaining gaps."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.espn import (
    ESPNService,
    PlayerInfo,
    PlayerStats,
    TeamDefense,
    _player_cache,
    _schedule_cache,
    _team_cache,
    format_player_context,
)


@pytest.fixture(autouse=True)
def clear_caches():
    _player_cache.clear()
    _schedule_cache.clear()
    _team_cache.clear()
    yield
    _player_cache.clear()
    _schedule_cache.clear()
    _team_cache.clear()


@pytest.fixture
def svc():
    return ESPNService()


def mock_response(data, status=200, raise_exc=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = data
    if raise_exc:
        resp.raise_for_status.side_effect = raise_exc
    else:
        resp.raise_for_status.return_value = None
    return resp


# =========================================================================
# search_players
# =========================================================================


class TestSearchPlayers:
    @pytest.mark.asyncio
    async def test_unknown_sport(self, svc):
        result = await svc.search_players("test", "cricket")
        assert result == []

    @pytest.mark.asyncio
    async def test_cache_hit(self, svc):
        cached = [PlayerInfo("1", "A", "T", "T", "PG", "1", "", "", None, None, None)]
        _player_cache["search:nba:lebron"] = cached
        result = await svc.search_players("LeBron", "nba", limit=5)
        assert result == cached

    @pytest.mark.asyncio
    async def test_success(self, svc):
        search_data = {
            "items": [
                {"id": "100", "displayName": "LeBron James", "league": "nba"},
            ]
        }
        player_data = {
            "athlete": {
                "id": "100",
                "displayName": "LeBron James",
                "team": {"displayName": "Lakers", "abbreviation": "LAL"},
                "position": {"abbreviation": "SF"},
                "jersey": "23",
            }
        }

        call_count = [0]

        async def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_response(search_data)
            return mock_response(player_data)

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.search_players("LeBron", "nba", limit=1)
            assert len(result) == 1
            assert result[0].name == "LeBron James"

    @pytest.mark.asyncio
    async def test_http_error(self, svc):
        async def mock_get(*args, **kwargs):
            return mock_response({}, raise_exc=Exception("fail"))

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.search_players("test", "nba")
            assert result == []

    @pytest.mark.asyncio
    async def test_no_player_id(self, svc):
        search_data = {"items": [{"displayName": "X", "league": "nba"}]}

        async def mock_get(*args, **kwargs):
            return mock_response(search_data)

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.search_players("X", "nba")
            assert result == []

    @pytest.mark.asyncio
    async def test_filters_by_league(self, svc):
        search_data = {
            "items": [
                {"id": "1", "displayName": "A", "league": "nfl"},
            ]
        }

        async def mock_get(*args, **kwargs):
            return mock_response(search_data)

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.search_players("A", "nba")
            assert result == []


# =========================================================================
# get_player
# =========================================================================


class TestGetPlayer:
    @pytest.mark.asyncio
    async def test_cache_hit(self, svc):
        p = PlayerInfo("1", "A", "T", "T", "PG", "1", "", "", None, None, None)
        _player_cache["player:nba:1"] = p
        result = await svc.get_player("1", "nba")
        assert result is p

    @pytest.mark.asyncio
    async def test_invalid_sport(self, svc):
        result = await svc.get_player("1", "cricket")
        assert result is None


# =========================================================================
# get_player_stats
# =========================================================================


class TestGetPlayerStats:
    @pytest.mark.asyncio
    async def test_cache_hit(self, svc):
        s = PlayerStats("1", "nba", 50, 50)
        _player_cache["stats:nba:1"] = s
        result = await svc.get_player_stats("1", "nba")
        assert result is s

    @pytest.mark.asyncio
    async def test_invalid_sport(self, svc):
        result = await svc.get_player_stats("1", "cricket")
        assert result is None

    @pytest.mark.asyncio
    async def test_success(self, svc):
        data = {
            "statistics": {
                "names": ["gamesPlayed", "avgPoints"],
                "splits": [{"stats": ["40", "22.5"]}],
            }
        }

        async def mock_get(*args, **kwargs):
            return mock_response(data)

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.get_player_stats("1", "nba")
            assert result is not None
            assert result.games_played == 40
            assert result.points_per_game == 22.5

    @pytest.mark.asyncio
    async def test_error(self, svc):
        async def mock_get(*args, **kwargs):
            return mock_response({}, raise_exc=Exception("fail"))

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.get_player_stats("1", "nba")
            assert result is None


# =========================================================================
# _parse_overview_stats — all sport branches
# =========================================================================


class TestParseOverviewStats:
    def test_nfl(self, svc):
        data = {
            "statistics": {
                "names": [
                    "gamesPlayed",
                    "passingYards",
                    "passingTouchdowns",
                    "rushingYards",
                ],
                "splits": [{"stats": ["16", "4500", "35", "200"]}],
            }
        }
        result = svc._parse_overview_stats(data, "1", "nfl")
        assert result.games_played == 16
        assert result.pass_yards == 4500
        assert result.pass_tds == 35
        assert result.rush_yards == 200

    def test_mlb(self, svc):
        data = {
            "statistics": {
                "names": [
                    "gamesPlayed",
                    "avg",
                    "homeRuns",
                    "rbi",
                    "stolenBases",
                    "ops",
                    "era",
                    "wins",
                    "strikeouts",
                ],
                "splits": [
                    {
                        "stats": [
                            "140",
                            "0.290",
                            "30",
                            "90",
                            "15",
                            "0.880",
                            "3.50",
                            "12",
                            "180",
                        ]
                    }
                ],
            }
        }
        result = svc._parse_overview_stats(data, "1", "mlb")
        assert result.games_played == 140
        assert result.batting_avg == 0.290
        assert result.home_runs == 30
        assert result.wins == 12

    def test_nhl(self, svc):
        data = {
            "statistics": {
                "names": [
                    "gamesPlayed",
                    "goals",
                    "assists",
                    "plusMinus",
                    "shots",
                    "savePct",
                ],
                "splits": [{"stats": ["70", "30", "40", "10", "200", "0.920"]}],
            }
        }
        result = svc._parse_overview_stats(data, "1", "nhl")
        assert result.goals == 30
        assert result.assists_nhl == 40
        assert result.save_pct == 0.920

    def test_no_splits(self, svc):
        data = {"statistics": {"names": ["gamesPlayed"], "splits": []}}
        result = svc._parse_overview_stats(data, "1", "nba")
        assert result is None

    def test_value_error_in_stats(self, svc):
        data = {
            "statistics": {
                "names": ["gamesPlayed", "avgPoints"],
                "splits": [{"stats": ["N/A", "abc"]}],
            }
        }
        result = svc._parse_overview_stats(data, "1", "nba")
        assert result is not None
        assert result.games_played == 0

    def test_exception_returns_none(self, svc):
        result = svc._parse_overview_stats(None, "1", "nba")
        assert result is None


# =========================================================================
# find_player_by_name
# =========================================================================


class TestFindPlayerByName:
    @pytest.mark.asyncio
    async def test_cache_hit(self, svc):
        p = PlayerInfo("1", "A", "T", "T", "PG", "1", "", "", None, None, None)
        _player_cache["find:nba:lebron"] = (p, None)
        result = await svc.find_player_by_name("LeBron", "nba")
        assert result[0] is p

    @pytest.mark.asyncio
    async def test_cache_hit_none(self, svc):
        _player_cache["find:nba:nobody"] = None
        result = await svc.find_player_by_name("Nobody", "nba")
        assert result is None

    @pytest.mark.asyncio
    async def test_exact_match(self, svc):
        search_data = {
            "items": [{"id": "10", "displayName": "LeBron James", "league": "nba"}]
        }
        player_data = {
            "athlete": {
                "id": "10",
                "displayName": "LeBron James",
                "team": {"displayName": "Lakers", "abbreviation": "LAL"},
                "position": {"abbreviation": "SF"},
            }
        }
        stats_data = {
            "statistics": {
                "names": ["gamesPlayed", "avgPoints"],
                "splits": [{"stats": ["50", "25.0"]}],
            }
        }

        call_count = [0]

        async def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_response(search_data)
            elif call_count[0] == 2:
                return mock_response(player_data)
            else:
                return mock_response(stats_data)

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.find_player_by_name("LeBron James", "nba")
            assert result is not None
            assert result[0].name == "LeBron James"

    @pytest.mark.asyncio
    async def test_no_match(self, svc):
        search_data = {"items": []}

        async def mock_get(*args, **kwargs):
            return mock_response(search_data)

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.find_player_by_name("Nobody", "nba")
            assert result is None

    @pytest.mark.asyncio
    async def test_fallback_first_in_sport(self, svc):
        """When no exact name match, takes first result in correct sport."""
        search_data = {
            "items": [{"id": "20", "displayName": "Some Player", "league": "nba"}]
        }
        player_data = {
            "athlete": {
                "id": "20",
                "displayName": "Some Player",
                "team": {"displayName": "T", "abbreviation": "T"},
                "position": {"abbreviation": "C"},
            }
        }
        stats_data = {"statistics": {"names": [], "splits": []}}

        call_count = [0]

        async def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_response(search_data)
            elif call_count[0] == 2:
                return mock_response(player_data)
            else:
                return mock_response(stats_data)

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.find_player_by_name("Unrelated Query", "nba")
            assert result is not None

    @pytest.mark.asyncio
    async def test_error(self, svc):
        async def mock_get(*args, **kwargs):
            raise Exception("network")

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.find_player_by_name("test", "nba")
            assert result is None

    @pytest.mark.asyncio
    async def test_player_not_found_after_search(self, svc):
        search_data = {"items": [{"id": "99", "displayName": "X", "league": "nba"}]}

        call_count = [0]

        async def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_response(search_data)
            return mock_response({}, raise_exc=Exception("404"))

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.find_player_by_name("X", "nba")
            assert result is None


# =========================================================================
# get_team_schedule
# =========================================================================


class TestGetTeamSchedule:
    @pytest.mark.asyncio
    async def test_cache_hit(self, svc):
        _schedule_cache["schedule:nba:LAL"] = []
        result = await svc.get_team_schedule("LAL", "nba")
        assert result == []

    @pytest.mark.asyncio
    async def test_invalid_sport(self, svc):
        result = await svc.get_team_schedule("LAL", "cricket")
        assert result == []

    @pytest.mark.asyncio
    async def test_success(self, svc):
        future_date = "2099-01-15T00:00:00"
        data = {
            "events": [
                {
                    "id": "g1",
                    "date": future_date,
                    "competitions": [
                        {
                            "competitors": [
                                {
                                    "homeAway": "home",
                                    "team": {
                                        "displayName": "Lakers",
                                        "abbreviation": "LAL",
                                    },
                                },
                                {
                                    "homeAway": "away",
                                    "team": {
                                        "displayName": "Celtics",
                                        "abbreviation": "BOS",
                                    },
                                },
                            ]
                        }
                    ],
                }
            ]
        }

        async def mock_get(*args, **kwargs):
            return mock_response(data)

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.get_team_schedule("LAL", "nba")
            assert len(result) == 1
            assert result[0].home_abbrev == "LAL"
            assert result[0].away_abbrev == "BOS"

    @pytest.mark.asyncio
    async def test_past_games_filtered(self, svc):
        past_date = "2000-01-01T00:00:00Z"
        data = {
            "events": [
                {
                    "id": "g1",
                    "date": past_date,
                    "competitions": [
                        {
                            "competitors": [
                                {
                                    "homeAway": "home",
                                    "team": {"displayName": "A", "abbreviation": "A"},
                                },
                                {
                                    "homeAway": "away",
                                    "team": {"displayName": "B", "abbreviation": "B"},
                                },
                            ]
                        }
                    ],
                }
            ]
        }

        async def mock_get(*args, **kwargs):
            return mock_response(data)

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.get_team_schedule("A", "nba")
            assert result == []

    @pytest.mark.asyncio
    async def test_empty_competitions(self, svc):
        data = {
            "events": [{"id": "g1", "date": "2099-01-01T00:00:00Z", "competitions": []}]
        }

        async def mock_get(*args, **kwargs):
            return mock_response(data)

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.get_team_schedule("A", "nba")
            assert result == []

    @pytest.mark.asyncio
    async def test_error(self, svc):
        async def mock_get(*args, **kwargs):
            return mock_response({}, raise_exc=Exception("fail"))

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.get_team_schedule("LAL", "nba")
            assert result == []


# =========================================================================
# get_next_opponent
# =========================================================================


class TestGetNextOpponent:
    @pytest.mark.asyncio
    async def test_no_games(self, svc):
        with patch.object(
            svc, "get_team_schedule", new_callable=AsyncMock, return_value=[]
        ):
            result = await svc.get_next_opponent("LAL", "nba")
            assert result is None

    @pytest.mark.asyncio
    async def test_home_game(self, svc):
        from services.espn import GameInfo

        game = GameInfo("g1", datetime.now(), "Lakers", "Celtics", "LAL", "BOS")
        with patch.object(
            svc, "get_team_schedule", new_callable=AsyncMock, return_value=[game]
        ):
            result = await svc.get_next_opponent("LAL", "nba")
            assert result == "BOS"

    @pytest.mark.asyncio
    async def test_away_game(self, svc):
        from services.espn import GameInfo

        game = GameInfo("g1", datetime.now(), "Celtics", "Lakers", "BOS", "LAL")
        with patch.object(
            svc, "get_team_schedule", new_callable=AsyncMock, return_value=[game]
        ):
            result = await svc.get_next_opponent("LAL", "nba")
            assert result == "BOS"


# =========================================================================
# get_team_defense
# =========================================================================


class TestGetTeamDefense:
    @pytest.mark.asyncio
    async def test_cache_hit(self, svc):
        d = TeamDefense("LAL", "nba")
        _team_cache["defense:nba:LAL"] = d
        result = await svc.get_team_defense("LAL", "nba")
        assert result is d

    @pytest.mark.asyncio
    async def test_invalid_sport(self, svc):
        result = await svc.get_team_defense("LAL", "cricket")
        assert result is None

    @pytest.mark.asyncio
    async def test_success_nba(self, svc):
        team_data = {"team": {"id": "13"}}
        stats_data = {
            "splits": {
                "categories": [
                    {
                        "stats": [
                            {"name": "defensiveRating", "value": 110.5},
                            {"name": "opponentPointsPerGame", "value": 105.2},
                            {"name": "pace", "value": 100.3},
                        ]
                    }
                ]
            }
        }

        call_count = [0]

        async def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_response(team_data)
            return mock_response(stats_data)

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.get_team_defense("LAL", "nba")
            assert result is not None
            assert result.defensive_rating == 110.5
            assert result.points_allowed == 105.2
            assert result.pace == 100.3

    @pytest.mark.asyncio
    async def test_success_nfl(self, svc):
        team_data = {"team": {"id": "1"}}
        stats_data = {
            "splits": {
                "categories": [{"stats": [{"name": "pointsAllowed", "value": 320}]}]
            }
        }

        call_count = [0]

        async def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_response(team_data)
            return mock_response(stats_data)

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.get_team_defense("KC", "nfl")
            assert result.points_allowed == 320

    @pytest.mark.asyncio
    async def test_no_team_id(self, svc):
        team_data = {"team": {}}

        async def mock_get(*args, **kwargs):
            return mock_response(team_data)

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.get_team_defense("LAL", "nba")
            assert result is None

    @pytest.mark.asyncio
    async def test_error(self, svc):
        async def mock_get(*args, **kwargs):
            return mock_response({}, raise_exc=Exception("fail"))

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.get_team_defense("LAL", "nba")
            assert result is None

    @pytest.mark.asyncio
    async def test_invalid_stat_value(self, svc):
        team_data = {"team": {"id": "1"}}
        stats_data = {
            "splits": {
                "categories": [{"stats": [{"name": "defensiveRating", "value": "N/A"}]}]
            }
        }

        call_count = [0]

        async def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_response(team_data)
            return mock_response(stats_data)

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.get_team_defense("LAL", "nba")
            assert result is not None
            # Invalid value skipped
            assert result.defensive_rating is None


# =========================================================================
# _search_rosters
# =========================================================================


class TestSearchRosters:
    @pytest.mark.asyncio
    async def test_invalid_sport(self, svc):
        result = await svc._search_rosters("test", "cricket")
        assert result is None

    @pytest.mark.asyncio
    async def test_success(self, svc):
        teams_data = {
            "sports": [
                {
                    "leagues": [
                        {
                            "teams": [
                                {"team": {"id": "1", "displayName": "Lakers"}},
                            ]
                        }
                    ]
                }
            ]
        }
        roster_data = {
            "athletes": [
                {
                    "id": "100",
                    "displayName": "LeBron James",
                    "team": {"displayName": "Lakers", "abbreviation": "LAL"},
                    "position": {"abbreviation": "SF"},
                }
            ]
        }

        call_count = [0]

        async def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_response(teams_data)
            r = mock_response(roster_data)
            r.status_code = 200
            return r

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc._search_rosters("LeBron", "nba")
            assert result is not None
            assert result.name == "LeBron James"

    @pytest.mark.asyncio
    async def test_not_found(self, svc):
        teams_data = {"sports": [{"leagues": [{"teams": [{"team": {"id": "1"}}]}]}]}
        roster_data = {"athletes": [{"displayName": "Other Player"}]}

        call_count = [0]

        async def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_response(teams_data)
            r = mock_response(roster_data)
            r.status_code = 200
            return r

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc._search_rosters("Nobody", "nba")
            assert result is None

    @pytest.mark.asyncio
    async def test_error(self, svc):
        async def mock_get(*args, **kwargs):
            raise Exception("network")

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc._search_rosters("test", "nba")
            assert result is None

    @pytest.mark.asyncio
    async def test_roster_404(self, svc):
        teams_data = {"sports": [{"leagues": [{"teams": [{"team": {"id": "1"}}]}]}]}

        call_count = [0]

        async def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_response(teams_data)
            r = mock_response({})
            r.status_code = 404
            return r

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc._search_rosters("test", "nba")
            assert result is None

    @pytest.mark.asyncio
    async def test_no_team_id(self, svc):
        teams_data = {"sports": [{"leagues": [{"teams": [{"team": {}}]}]}]}

        async def mock_get(*args, **kwargs):
            return mock_response(teams_data)

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc._search_rosters("test", "nba")
            assert result is None


# =========================================================================
# _parse_player edge cases
# =========================================================================


class TestParsePlayerEdge:
    def test_team_not_dict(self, svc):
        data = {"id": "1", "displayName": "X", "team": "string team"}
        p = svc._parse_player(data, "nba")
        assert p.team == "Unknown"

    def test_position_not_dict(self, svc):
        data = {"id": "1", "displayName": "X", "position": "PG"}
        p = svc._parse_player(data, "nba")
        assert p.position == "PG"

    def test_headshot_not_dict(self, svc):
        data = {"id": "1", "displayName": "X", "headshot": "url"}
        p = svc._parse_player(data, "nba")
        assert p.headshot_url is None

    def test_experience_not_dict(self, svc):
        data = {"id": "1", "displayName": "X", "experience": 5}
        p = svc._parse_player(data, "nba")
        assert p.experience is None

    def test_fullname_fallback(self, svc):
        data = {"id": "1", "fullName": "John Doe"}
        p = svc._parse_player(data, "nba")
        assert p.name == "John Doe"


# =========================================================================
# _parse_stats
# =========================================================================


class TestParseStats:
    def test_nba(self, svc):
        data = {
            "splits": {
                "categories": [
                    {
                        "stats": [
                            {"name": "gamesPlayed", "value": 50},
                            {"name": "pointsPerGame", "value": 25.5},
                        ]
                    }
                ]
            }
        }
        result = svc._parse_stats(data, "1", "nba")
        assert result is not None
        assert result.points_per_game == 25.5

    def test_nfl(self, svc):
        data = {
            "splits": {
                "categories": [{"stats": [{"name": "passingYards", "value": 4000}]}]
            }
        }
        result = svc._parse_stats(data, "1", "nfl")
        assert result.pass_yards == 4000

    def test_mlb(self, svc):
        data = {
            "splits": {"categories": [{"stats": [{"name": "homeRuns", "value": 30}]}]}
        }
        result = svc._parse_stats(data, "1", "mlb")
        assert result.home_runs == 30

    def test_nhl(self, svc):
        data = {"splits": {"categories": [{"stats": [{"name": "goals", "value": 40}]}]}}
        result = svc._parse_stats(data, "1", "nhl")
        assert result.goals == 40

    def test_error(self, svc):
        result = svc._parse_stats(None, "1", "nba")
        assert result is None


# =========================================================================
# _map_*_stat methods
# =========================================================================


class TestMapStats:
    def test_nba_unmapped(self, svc):
        s = PlayerStats("1", "nba", 0, 0)
        svc._map_nba_stat(s, "unknown_stat", 99)
        # Should not crash

    def test_nfl_unmapped(self, svc):
        s = PlayerStats("1", "nfl", 0, 0)
        svc._map_nfl_stat(s, "unknown_stat", 99)

    def test_mlb_unmapped(self, svc):
        s = PlayerStats("1", "mlb", 0, 0)
        svc._map_mlb_stat(s, "unknown_stat", 99)

    def test_nhl_unmapped(self, svc):
        s = PlayerStats("1", "nhl", 0, 0)
        svc._map_nhl_stat(s, "unknown_stat", 99)

    def test_nba_all_mappings(self, svc):
        s = PlayerStats("1", "nba", 0, 0)
        svc._map_nba_stat(s, "gamesplayed", 50)
        svc._map_nba_stat(s, "avgminutes", 35.0)
        svc._map_nba_stat(s, "avgpoints", 25.0)
        svc._map_nba_stat(s, "avgrebounds", 7.0)
        svc._map_nba_stat(s, "avgassists", 8.0)
        svc._map_nba_stat(s, "fieldgoalpct", 0.5)
        svc._map_nba_stat(s, "threepointpct", 0.4)
        assert s.games_played == 50
        assert s.minutes_per_game == 35.0

    def test_nfl_all_mappings(self, svc):
        s = PlayerStats("1", "nfl", 0, 0)
        svc._map_nfl_stat(s, "passingYards", 4000)
        svc._map_nfl_stat(s, "passingTouchdowns", 30)
        svc._map_nfl_stat(s, "rushingYards", 300)
        svc._map_nfl_stat(s, "rushingTouchdowns", 5)
        svc._map_nfl_stat(s, "receptions", 80)
        svc._map_nfl_stat(s, "receivingYards", 1000)
        svc._map_nfl_stat(s, "receivingTouchdowns", 8)
        svc._map_nfl_stat(s, "targets", 100)
        assert s.pass_yards == 4000
        assert s.targets == 100

    def test_mlb_all_mappings(self, svc):
        s = PlayerStats("1", "mlb", 0, 0)
        svc._map_mlb_stat(s, "avg", 0.300)
        svc._map_mlb_stat(s, "homeRuns", 30)
        svc._map_mlb_stat(s, "rbi", 90)
        svc._map_mlb_stat(s, "stolenBases", 15)
        svc._map_mlb_stat(s, "ops", 0.900)
        svc._map_mlb_stat(s, "era", 3.5)
        svc._map_mlb_stat(s, "wins", 12)
        svc._map_mlb_stat(s, "strikeouts", 200)
        assert s.batting_avg == 0.300

    def test_nhl_all_mappings(self, svc):
        s = PlayerStats("1", "nhl", 0, 0)
        svc._map_nhl_stat(s, "goals", 30)
        svc._map_nhl_stat(s, "assists", 40)
        svc._map_nhl_stat(s, "plusMinus", 10)
        svc._map_nhl_stat(s, "shots", 200)
        svc._map_nhl_stat(s, "savePct", 0.920)
        assert s.goals == 30
        assert s.save_pct == 0.920


# =========================================================================
# game log parsing — NFL, MLB, NHL
# =========================================================================


class TestParseGameLogVariants:
    def test_nfl_game_log(self, svc):
        event = {
            "id": "g1",
            "date": "2024-10-01",
            "opponent": {"abbreviation": "BUF"},
            "homeAway": "away",
            "gameResult": "L",
            "statNames": [
                "passYds",
                "passTD",
                "int",
                "rushYds",
                "rushTD",
                "rec",
                "recYds",
                "recTD",
                "tar",
                "snaps",
            ],
            "stats": ["300", "2", "1", "50", "1", "3", "30", "0", "5", "60"],
        }
        result = svc._parse_game_log(event, "nfl")
        assert result["pass_yards"] == 300
        assert result["home_away"] == "A"
        assert result["result"] == "L"

    def test_mlb_game_log(self, svc):
        event = {
            "id": "g1",
            "date": "2024-07-01",
            "opponent": {"abbreviation": "NYM"},
            "homeAway": "home",
            "gameResult": "W",
            "statNames": ["AB", "H", "HR", "RBI", "SB", "BB", "SO", "IP", "ER"],
            "stats": ["4", "2", "1", "3", "0", "1", "1", "0", "0"],
        }
        result = svc._parse_game_log(event, "mlb")
        assert result["at_bats"] == 4
        assert result["home_runs"] == 1

    def test_nhl_game_log(self, svc):
        event = {
            "id": "g1",
            "date": "2024-11-01",
            "opponent": {"abbreviation": "MTL"},
            "homeAway": "home",
            "gameResult": "W",
            "statNames": ["G", "A", "+/-", "SOG", "TOI", "SV", "GA"],
            "stats": ["2", "1", "1", "5", "20", "0", "0"],
        }
        result = svc._parse_game_log(event, "nhl")
        assert result["goals"] == 2
        assert result["assists"] == 1

    def test_parse_game_log_exception(self, svc):
        result = svc._parse_game_log(None, "nba")
        assert result is None


# =========================================================================
# get_player_game_logs
# =========================================================================


class TestGetPlayerGameLogs:
    @pytest.mark.asyncio
    async def test_cache_hit(self, svc):
        _player_cache["gamelog:nba:1:10"] = [{"x": 1}]
        result = await svc.get_player_game_logs("1", "nba")
        assert result == [{"x": 1}]

    @pytest.mark.asyncio
    async def test_invalid_sport(self, svc):
        result = await svc.get_player_game_logs("1", "cricket")
        assert result == []

    @pytest.mark.asyncio
    async def test_error(self, svc):
        async def mock_get(*args, **kwargs):
            raise Exception("fail")

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.get_player_game_logs("1", "nba")
            assert result == []


# =========================================================================
# calculate_trends — all sports
# =========================================================================


class TestCalculateTrendsAllSports:
    def _make_logs(self, count, **fields):
        return [{k: v for k, v in fields.items()} for _ in range(count)]

    def test_nfl(self, svc):
        logs = self._make_logs(10, snaps=50, targets=8)
        result = svc.calculate_trends(logs, "nfl")
        assert "minutes_trend" in result
        assert result["minutes_trend"] == 0  # All same

    def test_mlb(self, svc):
        logs = self._make_logs(10, at_bats=4, home_runs=1, hits=2)
        result = svc.calculate_trends(logs, "mlb")
        assert "minutes_trend" in result

    def test_nhl(self, svc):
        logs = self._make_logs(10, time_on_ice=20, goals=1, shots=5)
        result = svc.calculate_trends(logs, "nhl")
        assert "minutes_trend" in result

    def test_unknown_sport(self, svc):
        logs = self._make_logs(10)
        result = svc.calculate_trends(logs, "cricket")
        assert result == {"minutes_trend": 0, "points_trend": 0, "usage_trend": 0}


# =========================================================================
# format_player_context — MLB and NHL
# =========================================================================


class TestFormatContextExtended:
    def test_mlb_batter(self):
        p = PlayerInfo("1", "X", "T", "NYY", "RF", "99", "", "", None, None, None)
        s = PlayerStats(
            "1", "mlb", 100, 100, batting_avg=0.300, home_runs=30, rbis=90, ops=0.900
        )
        ctx = format_player_context(p, s, "mlb")
        assert ".300 AVG" in ctx
        assert "OPS" in ctx

    def test_mlb_pitcher(self):
        p = PlayerInfo("1", "X", "T", "LAD", "SP", "22", "", "", None, None, None)
        s = PlayerStats("1", "mlb", 30, 30, era=3.5, wins=12, strikeouts=200)
        ctx = format_player_context(p, s, "mlb")
        assert "ERA" in ctx
        assert "12 W" in ctx

    def test_nhl(self):
        p = PlayerInfo("1", "X", "T", "TOR", "C", "34", "", "", None, None, None)
        s = PlayerStats("1", "nhl", 70, 70, goals=30, assists_nhl=40, plus_minus=10)
        ctx = format_player_context(p, s, "nhl")
        assert "30 G" in ctx
        assert "40 A" in ctx

    def test_nhl_goalie(self):
        p = PlayerInfo("1", "X", "T", "BOS", "G", "1", "", "", None, None, None)
        s = PlayerStats("1", "nhl", 50, 50, save_pct=0.920)
        ctx = format_player_context(p, s, "nhl")
        assert "Save %" in ctx

    def test_no_stats(self):
        p = PlayerInfo("1", "X", "T", "T", "PG", "1", "", "", None, None, None)
        ctx = format_player_context(p, None, "nba")
        assert "X" in ctx

    def test_nfl_pass_yards(self):
        p = PlayerInfo("1", "X", "T", "KC", "QB", "15", "", "", None, None, None)
        s = PlayerStats("1", "nfl", 16, 16, pass_yards=4500, pass_tds=35)
        ctx = format_player_context(p, s, "nfl")
        assert "Passing" in ctx

    def test_nfl_rush_yards(self):
        p = PlayerInfo("1", "X", "T", "SF", "RB", "8", "", "", None, None, None)
        s = PlayerStats("1", "nfl", 16, 16, rush_yards=1200, rush_tds=10)
        ctx = format_player_context(p, s, "nfl")
        assert "Rushing" in ctx


# =========================================================================
# close
# =========================================================================


class TestClose:
    @pytest.mark.asyncio
    async def test_close(self, svc):
        with patch.object(svc.client, "aclose", new_callable=AsyncMock) as m:
            await svc.close()
            m.assert_called_once()
