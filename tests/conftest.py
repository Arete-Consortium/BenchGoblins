"""
Pytest fixtures for BenchGoblins tests.
"""

import sys
from pathlib import Path

import pytest

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))
sys.path.insert(0, str(src_path / "api"))
sys.path.insert(0, str(src_path / "core"))


# =============================================================================
# SCORING FIXTURES
# =============================================================================


@pytest.fixture
def nba_starter_stats():
    """Sample NBA starter player stats."""
    from core.scoring import PlayerStats

    return PlayerStats(
        player_id="12345",
        name="Test Player A",
        team="LAL",
        position="PG",
        sport="nba",
        minutes_per_game=34.5,
        usage_rate=28.5,
        points_per_game=26.3,
        assists_per_game=8.2,
        rebounds_per_game=4.5,
        field_goal_pct=0.485,
        three_point_pct=0.378,
        is_starter=True,
        games_started_pct=1.0,
        games_played=45,
        minutes_trend=2.5,
        usage_trend=1.2,
        points_trend=3.1,
    )


@pytest.fixture
def nba_bench_stats():
    """Sample NBA bench player stats."""
    from core.scoring import PlayerStats

    return PlayerStats(
        player_id="67890",
        name="Test Player B",
        team="BOS",
        position="SG",
        sport="nba",
        minutes_per_game=22.3,
        usage_rate=18.5,
        points_per_game=12.8,
        assists_per_game=2.1,
        rebounds_per_game=3.2,
        field_goal_pct=0.445,
        three_point_pct=0.352,
        is_starter=False,
        games_started_pct=0.2,
        games_played=48,
        minutes_trend=-1.5,
        usage_trend=-0.8,
        points_trend=-2.1,
    )


@pytest.fixture
def nfl_wr_stats():
    """Sample NFL wide receiver stats."""
    from core.scoring import PlayerStats

    return PlayerStats(
        player_id="11111",
        name="Test WR",
        team="KC",
        position="WR",
        sport="nfl",
        targets=8.5,
        receptions=5.8,
        receiving_yards=78.4,
        snap_pct=85.0,
        is_starter=True,
        games_started_pct=1.0,
        games_played=12,
    )


@pytest.fixture
def nfl_rb_stats():
    """Sample NFL running back stats."""
    from core.scoring import PlayerStats

    return PlayerStats(
        player_id="22222",
        name="Test RB",
        team="SF",
        position="RB",
        sport="nfl",
        rush_yards=65.3,
        targets=4.2,
        receptions=3.5,
        receiving_yards=28.5,
        snap_pct=62.0,
        is_starter=True,
        games_started_pct=0.9,
        games_played=14,
    )


@pytest.fixture
def nba_stats_with_matchup():
    """NBA stats with matchup context."""
    from core.scoring import PlayerStats

    return PlayerStats(
        player_id="33333",
        name="Matchup Test",
        team="MIA",
        position="SF",
        sport="nba",
        minutes_per_game=32.0,
        usage_rate=24.0,
        points_per_game=20.5,
        assists_per_game=4.5,
        rebounds_per_game=6.2,
        field_goal_pct=0.465,
        three_point_pct=0.365,
        is_starter=True,
        games_started_pct=1.0,
        games_played=40,
        opponent_def_rating=115.5,  # Bad defense
        opponent_pace=102.5,  # Fast pace
        opponent_vs_position=38.5,  # High FP allowed
    )


# =============================================================================
# ESPN FIXTURES
# =============================================================================


@pytest.fixture
def mock_espn_player_response():
    """Mock ESPN player API response."""
    return {
        "athlete": {
            "id": "12345",
            "displayName": "LeBron James",
            "team": {"displayName": "Los Angeles Lakers", "abbreviation": "LAL"},
            "position": {"abbreviation": "SF"},
            "jersey": "23",
            "displayHeight": "6'9\"",
            "displayWeight": "250 lbs",
            "age": 39,
            "experience": {"years": 21},
            "headshot": {"href": "https://example.com/lebron.png"},
        }
    }


@pytest.fixture
def mock_espn_stats_response():
    """Mock ESPN player stats API response."""
    return {
        "statistics": {
            "names": [
                "gamesPlayed",
                "avgMinutes",
                "avgPoints",
                "avgRebounds",
                "avgAssists",
                "fieldGoalPct",
                "threePointPct",
            ],
            "splits": [{"stats": ["50", "35.2", "25.8", "7.5", "8.1", "54.2", "41.0"]}],
        }
    }


@pytest.fixture
def mock_espn_gamelog_response():
    """Mock ESPN game log API response."""
    return {
        "events": [
            {
                "id": "game1",
                "date": "2024-01-15",
                "opponent": {"abbreviation": "BOS"},
                "homeAway": "home",
                "gameResult": "W",
                "statNames": [
                    "MIN",
                    "PTS",
                    "REB",
                    "AST",
                    "STL",
                    "BLK",
                    "TO",
                    "FGM",
                    "FGA",
                ],
                "stats": ["38", "32", "8", "10", "2", "1", "3", "12", "22"],
            },
            {
                "id": "game2",
                "date": "2024-01-12",
                "opponent": {"abbreviation": "MIA"},
                "homeAway": "away",
                "gameResult": "L",
                "statNames": [
                    "MIN",
                    "PTS",
                    "REB",
                    "AST",
                    "STL",
                    "BLK",
                    "TO",
                    "FGM",
                    "FGA",
                ],
                "stats": ["35", "28", "6", "7", "1", "0", "4", "10", "20"],
            },
        ]
    }


@pytest.fixture
def mock_espn_search_response():
    """Mock ESPN search API response."""
    return {
        "items": [
            {
                "id": "12345",
                "displayName": "LeBron James",
                "league": "nba",
            },
            {
                "id": "67890",
                "displayName": "Anthony Davis",
                "league": "nba",
            },
        ]
    }


# =============================================================================
# API FIXTURES
# =============================================================================


# =============================================================================
# ESPN-FORMAT FIXTURES (for scoring adapter tests)
# =============================================================================


@pytest.fixture
def espn_nba_player_info():
    """ESPN PlayerInfo for an NBA starter."""
    from services.espn import PlayerInfo

    return PlayerInfo(
        id="12345",
        name="Test Player A",
        team="Los Angeles Lakers",
        team_abbrev="LAL",
        position="PG",
        jersey="1",
        height="6'3\"",
        weight="190 lbs",
        age=27,
        experience=5,
        headshot_url=None,
    )


@pytest.fixture
def espn_nba_player_stats():
    """ESPN PlayerStats for an NBA starter."""
    from services.espn import PlayerStats

    return PlayerStats(
        player_id="12345",
        sport="nba",
        games_played=50,
        games_started=48,
        minutes_per_game=34.5,
        points_per_game=26.3,
        rebounds_per_game=4.5,
        assists_per_game=8.2,
        usage_rate=28.5,
        field_goal_pct=0.485,
        three_point_pct=0.378,
    )


@pytest.fixture
def espn_nba_bench_info():
    """ESPN PlayerInfo for an NBA bench player."""
    from services.espn import PlayerInfo

    return PlayerInfo(
        id="67890",
        name="Test Player B",
        team="Boston Celtics",
        team_abbrev="BOS",
        position="SG",
        jersey="7",
        height="6'5\"",
        weight="205 lbs",
        age=24,
        experience=3,
        headshot_url=None,
    )


@pytest.fixture
def espn_nba_bench_stats():
    """ESPN PlayerStats for an NBA bench player."""
    from services.espn import PlayerStats

    return PlayerStats(
        player_id="67890",
        sport="nba",
        games_played=48,
        games_started=5,
        minutes_per_game=22.3,
        points_per_game=12.8,
        rebounds_per_game=3.2,
        assists_per_game=2.1,
        usage_rate=18.5,
        field_goal_pct=0.445,
        three_point_pct=0.352,
    )


@pytest.fixture
def espn_nfl_wr_info():
    """ESPN PlayerInfo for an NFL WR."""
    from services.espn import PlayerInfo

    return PlayerInfo(
        id="11111",
        name="Test WR",
        team="Kansas City Chiefs",
        team_abbrev="KC",
        position="WR",
        jersey="11",
        height="6'1\"",
        weight="195 lbs",
        age=26,
        experience=4,
        headshot_url=None,
    )


@pytest.fixture
def espn_nfl_wr_stats():
    """ESPN PlayerStats for an NFL WR."""
    from services.espn import PlayerStats

    return PlayerStats(
        player_id="11111",
        sport="nfl",
        games_played=12,
        games_started=12,
        targets=8.5,
        receptions=5.8,
        receiving_yards=78.4,
        snap_pct=85.0,
    )


# =============================================================================
# MLB FIXTURES
# =============================================================================


@pytest.fixture
def mlb_hitter_stats():
    """Sample MLB hitter stats."""
    from core.scoring import PlayerStats

    return PlayerStats(
        player_id="30001",
        name="Test Hitter",
        team="NYY",
        position="RF",
        sport="mlb",
        batting_avg=0.285,
        home_runs=32.0,
        rbis=95.0,
        stolen_bases=12.0,
        ops=0.875,
        is_starter=True,
        games_started_pct=0.95,
        games_played=148,
        minutes_trend=0.5,
        usage_trend=0.2,
        points_trend=0.3,
    )


@pytest.fixture
def mlb_pitcher_stats():
    """Sample MLB pitcher stats."""
    from core.scoring import PlayerStats

    return PlayerStats(
        player_id="30002",
        name="Test Pitcher",
        team="LAD",
        position="SP",
        sport="mlb",
        era=3.25,
        wins=14,
        strikeouts=210.0,
        is_starter=True,
        games_started_pct=1.0,
        games_played=30,
    )


@pytest.fixture
def nhl_forward_stats():
    """Sample NHL forward stats."""
    from core.scoring import PlayerStats

    return PlayerStats(
        player_id="40001",
        name="Test Forward",
        team="TOR",
        position="C",
        sport="nhl",
        goals=35.0,
        assists_nhl=45.0,
        plus_minus=15.0,
        shots=250.0,
        is_starter=True,
        games_started_pct=0.95,
        games_played=78,
        minutes_trend=1.0,
        usage_trend=0.5,
        points_trend=0.8,
    )


@pytest.fixture
def nhl_goalie_stats():
    """Sample NHL goalie stats."""
    from core.scoring import PlayerStats

    return PlayerStats(
        player_id="40002",
        name="Test Goalie",
        team="BOS",
        position="G",
        sport="nhl",
        save_pct=0.920,
        is_starter=True,
        games_started_pct=0.85,
        games_played=55,
    )


@pytest.fixture
def espn_mlb_hitter_info():
    """ESPN PlayerInfo for an MLB hitter."""
    from services.espn import PlayerInfo

    return PlayerInfo(
        id="30001",
        name="Test Hitter",
        team="New York Yankees",
        team_abbrev="NYY",
        position="RF",
        jersey="99",
        height="6'7\"",
        weight="282 lbs",
        age=31,
        experience=9,
        headshot_url=None,
    )


@pytest.fixture
def espn_mlb_hitter_stats():
    """ESPN PlayerStats for an MLB hitter."""
    from services.espn import PlayerStats

    return PlayerStats(
        player_id="30001",
        sport="mlb",
        games_played=148,
        games_started=145,
        batting_avg=0.285,
        home_runs=32.0,
        rbis=95.0,
        stolen_bases=12.0,
        ops=0.875,
    )


@pytest.fixture
def espn_nhl_forward_info():
    """ESPN PlayerInfo for an NHL forward."""
    from services.espn import PlayerInfo

    return PlayerInfo(
        id="40001",
        name="Test Forward",
        team="Toronto Maple Leafs",
        team_abbrev="TOR",
        position="C",
        jersey="34",
        height="6'1\"",
        weight="195 lbs",
        age=27,
        experience=7,
        headshot_url=None,
    )


@pytest.fixture
def espn_nhl_forward_stats():
    """ESPN PlayerStats for an NHL forward."""
    from services.espn import PlayerStats

    return PlayerStats(
        player_id="40001",
        sport="nhl",
        games_played=78,
        games_started=75,
        goals=35.0,
        assists_nhl=45.0,
        plus_minus=15.0,
        shots=250.0,
    )


@pytest.fixture
def test_client():
    """FastAPI test client."""
    from fastapi.testclient import TestClient

    from api.main import app

    return TestClient(app)


@pytest.fixture
def async_test_client():
    """Async HTTP test client for async tests."""
    import httpx

    from api.main import app

    return httpx.AsyncClient(app=app, base_url="http://test")
