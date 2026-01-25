"""
Pytest fixtures for GameSpace tests.
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
