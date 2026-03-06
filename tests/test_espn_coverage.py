"""Tests targeting remaining coverage gaps in services/espn.py.

Missing lines: 342-358, 396, 455, 459, 464, 628-630, 661-662, 740-763,
825-826, 842-843, 869-870, 893-894, 916-917, 931-940, 1023-1037, 1093-1104
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.espn import (
    ESPNService,
    PlayerInfo,
    PlayerStats,
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
# Lines 342-358: _parse_overview_stats — soccer branch
# =========================================================================


class TestParseOverviewStatsSoccer:
    """Cover the soccer branch in _parse_overview_stats (lines 342-358)."""

    def test_soccer_stats_basic(self, svc):
        data = {
            "statistics": {
                "names": [
                    "gamesPlayed",
                    "goals",
                    "assists",
                    "minutesPlayed",
                    "totalShots",
                    "shotsOnTarget",
                    "keyPasses",
                    "tackles",
                    "interceptions",
                    "cleanSheets",
                    "saves",
                    "goalsConceded",
                ],
                "splits": [
                    {
                        "stats": [
                            "33",
                            "15",
                            "8",
                            "2800",
                            "85",
                            "42",
                            "35",
                            "12",
                            "5",
                            "0",
                            "0",
                            "0",
                        ]
                    }
                ],
            }
        }
        result = svc._parse_overview_stats(data, "50001", "soccer")
        assert result is not None
        assert result.games_played == 33
        assert result.soccer_goals == 15
        assert result.soccer_assists == 8
        assert result.soccer_minutes == 2800
        assert result.soccer_shots == 85
        assert result.soccer_shots_on_target == 42
        assert result.soccer_key_passes == 35
        assert result.soccer_tackles == 12
        assert result.soccer_interceptions == 5
        assert result.soccer_clean_sheets == 0
        assert result.soccer_saves == 0
        assert result.soccer_goals_conceded == 0

    def test_soccer_stats_alternate_names(self, svc):
        """Cover fallback stat names like 'appearances', 'totalGoals', etc."""
        data = {
            "statistics": {
                "names": [
                    "appearances",
                    "totalGoals",
                    "goalAssists",
                    "minutes",
                    "shotOnTarget",
                    "shotOnGoal",
                    "totalTackles",
                    "goalAgainst",
                ],
                "splits": [
                    {
                        "stats": [
                            "30",
                            "10",
                            "6",
                            "2500",
                            "40",
                            "38",
                            "20",
                            "15",
                        ]
                    }
                ],
            }
        }
        result = svc._parse_overview_stats(data, "50002", "soccer")
        assert result is not None
        assert result.games_played == 30
        assert result.soccer_goals == 10
        assert result.soccer_assists == 6
        assert result.soccer_minutes == 2500
        assert result.soccer_goals_conceded == 15


# =========================================================================
# Line 396: find_player_by_name — league mismatch continue
# =========================================================================


class TestFindPlayerByNameLeagueFilter:
    """Cover the league != league continue on line 396."""

    @pytest.mark.asyncio
    async def test_skips_wrong_league_items(self, svc):
        """Items with wrong league should be skipped, then fallback loop runs."""
        search_data = {
            "items": [
                {
                    "id": "1",
                    "displayName": "Soccer Player",
                    "league": "eng.1",
                },
                {
                    "id": "2",
                    "displayName": "NBA Player",
                    "league": "nba",
                },
            ]
        }
        player_data = {
            "athlete": {
                "id": "2",
                "displayName": "NBA Player",
                "team": {"displayName": "Lakers", "abbreviation": "LAL"},
                "position": {"abbreviation": "PG"},
            }
        }
        stats_data = {
            "statistics": {
                "names": ["gamesPlayed"],
                "splits": [{"stats": ["40"]}],
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
            result = await svc.find_player_by_name("NBA Player", "nba")
            assert result is not None
            assert result[0].name == "NBA Player"

    @pytest.mark.asyncio
    async def test_all_wrong_league_items_no_name_match(self, svc):
        """All items have wrong league in both loops -> no match -> None."""
        search_data = {
            "items": [
                {"id": "1", "displayName": "X", "league": "eng.1"},
                {"id": "2", "displayName": "Y", "league": "nfl"},
            ]
        }

        async def mock_get(*args, **kwargs):
            return mock_response(search_data)

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.find_player_by_name("X", "nba")
            assert result is None


# =========================================================================
# Lines 455, 459, 464: get_team_schedule edge cases
# =========================================================================


class TestGetTeamScheduleEdgeCases:
    @pytest.mark.asyncio
    async def test_past_game_skipped_naive_datetime(self, svc):
        """Line 455: past game with naive datetime -> continue.

        Uses a naive datetime string (no 'Z' suffix) so comparison
        with datetime.now() (also naive) doesn't raise TypeError.
        Includes a future game to prove only past games are skipped.
        """
        data = {
            "events": [
                {
                    "id": "past_game",
                    "date": "2000-01-01T00:00:00",
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
                },
                {
                    "id": "future_game",
                    "date": "2099-06-15T00:00:00",
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
                                        "displayName": "Heat",
                                        "abbreviation": "MIA",
                                    },
                                },
                            ]
                        }
                    ],
                },
            ]
        }

        async def mock_get(*args, **kwargs):
            return mock_response(data)

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.get_team_schedule("LAL", "nba")
            # Past game skipped, only future game returned
            assert len(result) == 1
            assert result[0].game_id == "future_game"
            assert result[0].away_abbrev == "MIA"

    @pytest.mark.asyncio
    async def test_insufficient_competitors(self, svc):
        """Line 464: less than 2 competitors -> continue."""
        data = {
            "events": [
                {
                    "id": "g1",
                    "date": "2099-01-15T00:00:00",
                    "competitions": [
                        {
                            "competitors": [
                                {
                                    "homeAway": "home",
                                    "team": {
                                        "displayName": "Lakers",
                                        "abbreviation": "LAL",
                                    },
                                }
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
            assert result == []

    @pytest.mark.asyncio
    async def test_no_competitions_key(self, svc):
        """Line 459: competitions list with empty first entry."""
        data = {
            "events": [
                {
                    "id": "g1",
                    "date": "2099-01-15T00:00:00",
                    "competitions": [],
                }
            ]
        }

        async def mock_get(*args, **kwargs):
            return mock_response(data)

        with patch.object(svc.client, "get", side_effect=mock_get):
            result = await svc.get_team_schedule("LAL", "nba")
            assert result == []


# =========================================================================
# Lines 628-630: _parse_player exception branch
# =========================================================================


class TestParsePlayerException:
    """Cover the except block in _parse_player (lines 628-630)."""

    def test_parse_player_raises_internally(self, svc):
        """Force an exception inside _parse_player to hit lines 628-630."""

        # Pass data that will cause an error during parsing.
        # The 'experience' key triggers .get("years") but if we
        # make data.get raise we can hit the except block.
        # Simplest: override data.get to raise on certain keys.
        class BadDict(dict):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._call_count = 0

            def get(self, key, default=None):
                self._call_count += 1
                # Fail on the 'experience' check which is late in the method
                if key == "experience":
                    raise RuntimeError("boom")
                return super().get(key, default)

        bad_data = BadDict({"id": "1", "displayName": "X"})
        result = svc._parse_player(bad_data, "nba")
        assert result is None


# =========================================================================
# Lines 661-662: _parse_stats — soccer branch
# =========================================================================


class TestParseStatsSoccer:
    """Cover the soccer elif branch in _parse_stats (lines 661-662)."""

    def test_soccer_stats_via_parse_stats(self, svc):
        data = {
            "splits": {
                "categories": [
                    {
                        "stats": [
                            {"name": "goals", "value": 15},
                            {"name": "assists", "value": 8},
                            {"name": "appearances", "value": 33},
                            {"name": "minutesPlayed", "value": 2800},
                        ]
                    }
                ]
            }
        }
        result = svc._parse_stats(data, "50001", "soccer")
        assert result is not None
        assert result.soccer_goals == 15
        assert result.soccer_assists == 8
        assert result.games_played == 33
        assert result.soccer_minutes == 2800


# =========================================================================
# Lines 740-763: _map_soccer_stat method
# =========================================================================


class TestMapSoccerStat:
    """Cover the entire _map_soccer_stat method (lines 740-763)."""

    def test_all_soccer_mappings(self, svc):
        s = PlayerStats("1", "soccer", 0, 0)
        svc._map_soccer_stat(s, "gamesPlayed", 33)
        assert s.games_played == 33

        svc._map_soccer_stat(s, "appearances", 30)
        assert s.games_played == 30

        svc._map_soccer_stat(s, "goals", 15)
        assert s.soccer_goals == 15

        svc._map_soccer_stat(s, "totalGoals", 12)
        assert s.soccer_goals == 12

        svc._map_soccer_stat(s, "assists", 8)
        assert s.soccer_assists == 8

        svc._map_soccer_stat(s, "goalAssists", 6)
        assert s.soccer_assists == 6

        svc._map_soccer_stat(s, "minutesPlayed", 2800)
        assert s.soccer_minutes == 2800

        svc._map_soccer_stat(s, "minutes", 2700)
        assert s.soccer_minutes == 2700

        svc._map_soccer_stat(s, "totalShots", 85)
        assert s.soccer_shots == 85

        svc._map_soccer_stat(s, "shotsOnTarget", 42)
        assert s.soccer_shots_on_target == 42

        svc._map_soccer_stat(s, "shotsOnGoal", 40)
        assert s.soccer_shots_on_target == 40

        svc._map_soccer_stat(s, "keyPasses", 35)
        assert s.soccer_key_passes == 35

        svc._map_soccer_stat(s, "tackles", 12)
        assert s.soccer_tackles == 12

        svc._map_soccer_stat(s, "totalTackles", 10)
        assert s.soccer_tackles == 10

        svc._map_soccer_stat(s, "interceptions", 5)
        assert s.soccer_interceptions == 5

        svc._map_soccer_stat(s, "cleanSheets", 14)
        assert s.soccer_clean_sheets == 14

        svc._map_soccer_stat(s, "saves", 95)
        assert s.soccer_saves == 95

        svc._map_soccer_stat(s, "goalsConceded", 28)
        assert s.soccer_goals_conceded == 28

        svc._map_soccer_stat(s, "goalAgainst", 25)
        assert s.soccer_goals_conceded == 25

    def test_unmapped_stat(self, svc):
        s = PlayerStats("1", "soccer", 0, 0)
        svc._map_soccer_stat(s, "unknownStat", 99)
        # Should not crash, no field changed


# =========================================================================
# Lines 825-826: _parse_game_log — soccer branch
# =========================================================================


class TestParseGameLogSoccer:
    """Cover the soccer branch in _parse_game_log (lines 825-826)."""

    def test_soccer_game_log(self, svc):
        event = {
            "id": "g1",
            "date": "2024-09-15",
            "opponent": {"abbreviation": "LIV"},
            "homeAway": "home",
            "gameResult": "W",
            "statNames": [
                "G",
                "A",
                "MIN",
                "SH",
                "SOT",
                "KP",
                "TK",
                "INT",
                "SV",
                "GC",
            ],
            "stats": ["2", "1", "90", "5", "3", "4", "2", "1", "0", "0"],
        }
        result = svc._parse_game_log(event, "soccer")
        assert result is not None
        assert result["goals"] == 2
        assert result["assists"] == 1
        assert result["minutes"] == 90
        assert result["shots"] == 5
        assert result["shots_on_target"] == 3
        assert result["key_passes"] == 4
        assert result["tackles"] == 2
        assert result["interceptions"] == 1
        assert result["saves"] == 0
        assert result["goals_conceded"] == 0
        assert result["home_away"] == "H"
        assert result["result"] == "W"


# =========================================================================
# Lines 842-843: _parse_nba_game_log ValueError/TypeError
# =========================================================================


class TestParseNbaGameLogValueError:
    """Cover ValueError/TypeError in _parse_nba_game_log (lines 842-843)."""

    def test_non_numeric_stat_value(self, svc):
        event = {
            "id": "g1",
            "date": "2024-01-15",
            "opponent": {"abbreviation": "BOS"},
            "homeAway": "home",
            "gameResult": "W",
            "statNames": ["MIN", "PTS"],
            "stats": ["not_a_number", None],
        }
        result = svc._parse_game_log(event, "nba")
        assert result is not None
        # Invalid values should default to 0
        assert result["minutes"] == 0
        assert result["points"] == 0


# =========================================================================
# Lines 869-870: _parse_nfl_game_log ValueError/TypeError
# =========================================================================


class TestParseNflGameLogValueError:
    """Cover ValueError/TypeError in _parse_nfl_game_log (lines 869-870)."""

    def test_non_numeric_stat_value(self, svc):
        event = {
            "id": "g1",
            "date": "2024-10-01",
            "opponent": {"abbreviation": "BUF"},
            "homeAway": "away",
            "gameResult": "L",
            "statNames": ["passYds", "passTD"],
            "stats": ["abc", None],
        }
        result = svc._parse_game_log(event, "nfl")
        assert result is not None
        assert result["pass_yards"] == 0
        assert result["pass_tds"] == 0


# =========================================================================
# Lines 893-894: _parse_mlb_game_log ValueError/TypeError
# =========================================================================


class TestParseMlbGameLogValueError:
    """Cover ValueError/TypeError in _parse_mlb_game_log (lines 893-894)."""

    def test_non_numeric_stat_value(self, svc):
        event = {
            "id": "g1",
            "date": "2024-07-01",
            "opponent": {"abbreviation": "NYM"},
            "homeAway": "home",
            "gameResult": "W",
            "statNames": ["AB", "H"],
            "stats": ["bad", None],
        }
        result = svc._parse_game_log(event, "mlb")
        assert result is not None
        assert result["at_bats"] == 0
        assert result["hits"] == 0


# =========================================================================
# Lines 916-917: _parse_nhl_game_log ValueError/TypeError
# =========================================================================


class TestParseNhlGameLogValueError:
    """Cover ValueError/TypeError in _parse_nhl_game_log (lines 916-917)."""

    def test_non_numeric_stat_value(self, svc):
        event = {
            "id": "g1",
            "date": "2024-11-01",
            "opponent": {"abbreviation": "MTL"},
            "homeAway": "home",
            "gameResult": "W",
            "statNames": ["G", "A"],
            "stats": ["bad", None],
        }
        result = svc._parse_game_log(event, "nhl")
        assert result is not None
        assert result["goals"] == 0
        assert result["assists"] == 0


# =========================================================================
# Lines 931-940: _parse_soccer_game_log stat_map building
# =========================================================================


class TestParseSoccerGameLogStatMap:
    """Cover the stat_map loop in _parse_soccer_game_log (lines 931-940)."""

    def test_soccer_game_log_with_value_error(self, svc):
        """Test ValueError/TypeError fallback in soccer game log parsing."""
        event = {
            "id": "g1",
            "date": "2024-09-15",
            "opponent": {"abbreviation": "LIV"},
            "homeAway": "away",
            "gameResult": "L",
            "statNames": ["G", "A", "MIN"],
            "stats": ["bad", None, "90"],
        }
        result = svc._parse_game_log(event, "soccer")
        assert result is not None
        assert result["goals"] == 0
        assert result["assists"] == 0
        assert result["minutes"] == 90
        assert result["home_away"] == "A"
        assert result["result"] == "L"

    def test_soccer_game_log_full_stats(self, svc):
        """Full soccer game log with all stat names using alternate keys."""
        event = {
            "id": "g2",
            "date": "2024-09-20",
            "opponent": {"abbreviation": "ARS"},
            "homeAway": "home",
            "gameResult": "W",
            "statNames": [
                "goals",
                "assists",
                "minutes",
                "shots",
                "shotsOnTarget",
                "keyPasses",
                "tackles",
                "interceptions",
                "saves",
                "goalsConceded",
            ],
            "stats": ["1", "2", "85", "4", "2", "5", "3", "2", "0", "1"],
        }
        result = svc._parse_game_log(event, "soccer")
        assert result is not None
        assert result["goals"] == 1
        assert result["assists"] == 2
        assert result["minutes"] == 85
        assert result["shots"] == 4
        assert result["shots_on_target"] == 2
        assert result["key_passes"] == 5
        assert result["tackles"] == 3
        assert result["interceptions"] == 2
        assert result["saves"] == 0
        assert result["goals_conceded"] == 1


# =========================================================================
# Lines 1023-1037: calculate_trends — soccer branch
# =========================================================================


class TestCalculateTrendsSoccer:
    """Cover the soccer branch in calculate_trends (lines 1023-1037)."""

    def test_soccer_trends_flat(self, svc):
        """All same values -> zero trends."""
        logs = [
            {"minutes": 90, "goals": 1, "assists": 0, "shots": 3} for _ in range(10)
        ]
        result = svc.calculate_trends(logs, "soccer")
        assert result["minutes_trend"] == 0
        assert result["points_trend"] == 0
        assert result["usage_trend"] == 0

    def test_soccer_trends_increasing(self, svc):
        """Recent games trending up."""
        logs = [
            # Recent 5 - higher values
            {"minutes": 90, "goals": 2, "assists": 1, "shots": 5},
            {"minutes": 88, "goals": 1, "assists": 2, "shots": 4},
            {"minutes": 90, "goals": 1, "assists": 1, "shots": 6},
            {"minutes": 85, "goals": 2, "assists": 0, "shots": 5},
            {"minutes": 87, "goals": 1, "assists": 1, "shots": 4},
            # Older 5 - lower values
            {"minutes": 70, "goals": 0, "assists": 0, "shots": 2},
            {"minutes": 65, "goals": 0, "assists": 1, "shots": 1},
            {"minutes": 60, "goals": 0, "assists": 0, "shots": 1},
            {"minutes": 55, "goals": 0, "assists": 0, "shots": 2},
            {"minutes": 50, "goals": 0, "assists": 0, "shots": 0},
        ]
        result = svc.calculate_trends(logs, "soccer")
        assert result["minutes_trend"] > 0
        assert result["points_trend"] > 0  # goals + assists
        assert result["usage_trend"] > 0  # shots

    def test_soccer_trends_decreasing(self, svc):
        """Recent games trending down."""
        logs = [
            # Recent 5 - lower values
            {"minutes": 45, "goals": 0, "assists": 0, "shots": 1},
            {"minutes": 50, "goals": 0, "assists": 0, "shots": 1},
            {"minutes": 55, "goals": 0, "assists": 0, "shots": 0},
            {"minutes": 45, "goals": 0, "assists": 0, "shots": 1},
            {"minutes": 50, "goals": 0, "assists": 0, "shots": 0},
            # Older 5 - higher values
            {"minutes": 90, "goals": 2, "assists": 1, "shots": 5},
            {"minutes": 90, "goals": 1, "assists": 2, "shots": 4},
            {"minutes": 85, "goals": 1, "assists": 1, "shots": 3},
            {"minutes": 90, "goals": 2, "assists": 0, "shots": 6},
            {"minutes": 88, "goals": 1, "assists": 1, "shots": 4},
        ]
        result = svc.calculate_trends(logs, "soccer")
        assert result["minutes_trend"] < 0
        assert result["points_trend"] < 0
        assert result["usage_trend"] < 0

    def test_soccer_trends_with_fewer_than_10_games(self, svc):
        """Between 5 and 10 games: baseline = all games."""
        logs = [
            {"minutes": 90, "goals": 2, "assists": 1, "shots": 5},
            {"minutes": 88, "goals": 1, "assists": 0, "shots": 4},
            {"minutes": 85, "goals": 0, "assists": 1, "shots": 3},
            {"minutes": 80, "goals": 1, "assists": 0, "shots": 2},
            {"minutes": 75, "goals": 0, "assists": 0, "shots": 1},
            {"minutes": 70, "goals": 0, "assists": 0, "shots": 1},
            {"minutes": 65, "goals": 0, "assists": 0, "shots": 0},
        ]
        result = svc.calculate_trends(logs, "soccer")
        # Recent 5 avg minutes: (90+88+85+80+75)/5 = 83.6
        # All 7 avg minutes: (90+88+85+80+75+70+65)/7 = 79.0
        assert result["minutes_trend"] > 0
        assert "points_trend" in result
        assert "usage_trend" in result


# =========================================================================
# Lines 1093-1104: format_player_context — soccer branch
# =========================================================================


class TestFormatPlayerContextSoccer:
    """Cover the soccer branch in format_player_context (lines 1093-1104)."""

    def test_soccer_full_context(self):
        """Format soccer player with all optional fields."""
        player = PlayerInfo(
            id="50001",
            name="Test Forward",
            team="Arsenal",
            team_abbrev="ARS",
            position="FW",
            jersey="7",
            height="5'10\"",
            weight="154 lbs",
            age=25,
            experience=6,
            headshot_url=None,
        )
        stats = PlayerStats(
            player_id="50001",
            sport="soccer",
            games_played=33,
            games_started=31,
            soccer_goals=15.0,
            soccer_assists=8.0,
            soccer_minutes=2800.0,
            soccer_key_passes=35.0,
            soccer_clean_sheets=14.0,
            soccer_saves=95.0,
        )
        ctx = format_player_context(player, stats, "soccer")
        assert "Test Forward" in ctx
        assert "ARS" in ctx
        assert "15 G" in ctx
        assert "8 A" in ctx
        assert "Minutes: 2800" in ctx
        assert "Key Passes: 35.0" in ctx
        assert "Clean Sheets: 14" in ctx
        assert "Saves: 95" in ctx

    def test_soccer_no_optional_stats(self):
        """Soccer player without optional minutes/key_passes/clean_sheets/saves."""
        player = PlayerInfo(
            id="50002",
            name="Min Player",
            team="Chelsea",
            team_abbrev="CHE",
            position="MF",
            jersey="10",
            height="5'9\"",
            weight="150 lbs",
            age=22,
            experience=3,
            headshot_url=None,
        )
        stats = PlayerStats(
            player_id="50002",
            sport="soccer",
            games_played=20,
            games_started=15,
            soccer_goals=3.0,
            soccer_assists=5.0,
            # All optional fields left as None (default)
        )
        ctx = format_player_context(player, stats, "soccer")
        assert "3 G" in ctx
        assert "5 A" in ctx
        # These should NOT appear since the stats are None
        assert "Minutes:" not in ctx
        assert "Key Passes:" not in ctx
        assert "Clean Sheets:" not in ctx
        assert "Saves:" not in ctx

    def test_soccer_only_minutes(self):
        """Soccer player with only minutes set."""
        player = PlayerInfo(
            id="50003",
            name="Solo Min",
            team="T",
            team_abbrev="T",
            position="DF",
            jersey="5",
            height="",
            weight="",
            age=None,
            experience=None,
            headshot_url=None,
        )
        stats = PlayerStats(
            player_id="50003",
            sport="soccer",
            games_played=10,
            games_started=10,
            soccer_goals=0.0,
            soccer_assists=0.0,
            soccer_minutes=900.0,
        )
        ctx = format_player_context(player, stats, "soccer")
        assert "Minutes: 900" in ctx
        assert "Key Passes:" not in ctx
        assert "Clean Sheets:" not in ctx
        assert "Saves:" not in ctx

    def test_soccer_only_key_passes(self):
        """Soccer player with only key_passes set."""
        player = PlayerInfo(
            id="50004",
            name="Passer",
            team="T",
            team_abbrev="T",
            position="MF",
            jersey="8",
            height="",
            weight="",
            age=None,
            experience=None,
            headshot_url=None,
        )
        stats = PlayerStats(
            player_id="50004",
            sport="soccer",
            games_played=10,
            games_started=10,
            soccer_key_passes=50.0,
        )
        ctx = format_player_context(player, stats, "soccer")
        assert "Key Passes: 50.0" in ctx

    def test_soccer_only_clean_sheets(self):
        """Soccer player with only clean_sheets set."""
        player = PlayerInfo(
            id="50005",
            name="Keeper",
            team="T",
            team_abbrev="T",
            position="GK",
            jersey="1",
            height="",
            weight="",
            age=None,
            experience=None,
            headshot_url=None,
        )
        stats = PlayerStats(
            player_id="50005",
            sport="soccer",
            games_played=34,
            games_started=34,
            soccer_clean_sheets=14.0,
        )
        ctx = format_player_context(player, stats, "soccer")
        assert "Clean Sheets: 14" in ctx

    def test_soccer_only_saves(self):
        """Soccer player with only saves set."""
        player = PlayerInfo(
            id="50006",
            name="SaveMaker",
            team="T",
            team_abbrev="T",
            position="GK",
            jersey="1",
            height="",
            weight="",
            age=None,
            experience=None,
            headshot_url=None,
        )
        stats = PlayerStats(
            player_id="50006",
            sport="soccer",
            games_played=30,
            games_started=30,
            soccer_saves=80.0,
        )
        ctx = format_player_context(player, stats, "soccer")
        assert "Saves: 80" in ctx


# -------------------------------------------------------------------------
# Gamelog nested seasonTypes fallback + type guards
# -------------------------------------------------------------------------


class TestGamelogNestedSeasonTypes:
    """Tests for ESPN gamelog API response format changes."""

    @pytest.mark.asyncio
    async def test_events_not_a_list_falls_back(self):
        """If events is a string/dict instead of list, treat as empty."""
        svc = ESPNService()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"events": "not-a-list"}

        with patch.object(svc, "client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_resp)
            result = await svc.get_player_game_logs("123", "nba", limit=5)

        assert result == []

    @pytest.mark.asyncio
    async def test_nested_season_types_extraction(self):
        """Events nested under seasonTypes[].categories[].events[] are extracted."""
        svc = ESPNService()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "events": [],
            "seasonTypes": [
                {
                    "categories": [
                        {
                            "events": [
                                {
                                    "id": "g1",
                                    "date": "2026-03-01",
                                    "opponent": {"abbreviation": "LAL"},
                                    "homeAway": "home",
                                    "gameResult": "W",
                                    "stats": [30, 5, 7, 2, 1, 3],
                                    "statNames": ["PTS", "REB", "AST", "STL", "BLK", "TO"],
                                }
                            ]
                        }
                    ]
                }
            ],
        }

        with patch.object(svc, "client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_resp)
            result = await svc.get_player_game_logs("123", "nba", limit=5)

        assert len(result) == 1
        assert result[0]["game_id"] == "g1"
        assert result[0]["points"] == 30

    @pytest.mark.asyncio
    async def test_season_types_with_non_dict_entries(self):
        """Non-dict entries in seasonTypes/categories are skipped."""
        svc = ESPNService()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "events": [],
            "seasonTypes": [
                "not-a-dict",
                {"categories": ["also-not-a-dict"]},
                {"categories": [{"events": "not-a-list"}]},
            ],
        }

        with patch.object(svc, "client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_resp)
            result = await svc.get_player_game_logs("123", "nba", limit=5)

        assert result == []

    @pytest.mark.asyncio
    async def test_non_dict_event_skipped(self):
        """Non-dict items in the events list are skipped."""
        svc = ESPNService()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "events": ["not-a-dict", 42, None],
        }

        with patch.object(svc, "client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_resp)
            result = await svc.get_player_game_logs("123", "nba", limit=5)

        assert result == []

    @pytest.mark.asyncio
    async def test_stats_data_not_list_becomes_empty(self):
        """If event.stats is not a list, parsing still succeeds with zeros."""
        svc = ESPNService()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "events": [
                {
                    "id": "g2",
                    "date": "2026-03-01",
                    "opponent": {"abbreviation": "BOS"},
                    "homeAway": "away",
                    "gameResult": "L",
                    "stats": "not-a-list",
                    "statNames": ["PTS"],
                }
            ],
        }

        with patch.object(svc, "client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_resp)
            result = await svc.get_player_game_logs("123", "nba", limit=5)

        assert len(result) == 1
        assert result[0]["points"] == 0

    @pytest.mark.asyncio
    async def test_opponent_not_dict_becomes_empty(self):
        """If event.opponent is not a dict, abbreviation defaults to empty."""
        svc = ESPNService()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "events": [
                {
                    "id": "g3",
                    "date": "2026-03-01",
                    "opponent": "not-a-dict",
                    "homeAway": "home",
                    "gameResult": "W",
                    "stats": [],
                    "statNames": [],
                }
            ],
        }

        with patch.object(svc, "client") as mock_client:
            mock_client.get = AsyncMock(return_value=mock_resp)
            result = await svc.get_player_game_logs("123", "nba", limit=5)

        assert len(result) == 1
        assert result[0]["opponent"] == ""
