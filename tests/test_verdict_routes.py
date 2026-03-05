"""Tests for verdict API routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.espn import PlayerInfo, PlayerStats as ESPNPlayerStats
from services.sleeper import SleeperLeague

VALID_USER = {
    "user_id": 1,
    "email": "test@example.com",
    "name": "Test User",
    "tier": "pro",
    "exp": 9999999999,
}


@pytest.fixture
def authed_client(test_client):
    """Test client with auth bypassed (pro tier)."""
    from api.main import app
    from routes.auth import require_pro

    app.dependency_overrides[require_pro] = lambda: VALID_USER
    yield test_client
    app.dependency_overrides.pop(require_pro, None)


def _make_player_info(name="Patrick Mahomes", team="KC", position="QB"):
    return PlayerInfo(
        id="12345",
        name=name,
        team=f"{team} Team",
        team_abbrev=team,
        position=position,
        jersey="15",
        height="6-2",
        weight="225",
        age=29,
        experience=8,
        headshot_url=None,
    )


def _make_espn_stats(sport="nfl", **overrides):
    defaults = {
        "player_id": "12345",
        "sport": sport,
        "games_played": 15,
        "games_started": 15,
        "minutes_per_game": 60.0,
        "points_per_game": 22.0,
        "assists_per_game": 0.0,
        "rebounds_per_game": 0.0,
        "usage_rate": 25.0,
        "field_goal_pct": 0.65,
        "three_point_pct": 0.0,
        "targets": 0.0,
        "receptions": 0.0,
        "receiving_yards": 0.0,
        "rush_yards": 50.0,
        "snap_pct": 100.0,
        "batting_avg": 0.0,
        "home_runs": 0.0,
        "rbis": 0.0,
        "stolen_bases": 0.0,
        "ops": 0.0,
        "era": 0.0,
        "wins": 0,
        "strikeouts": 0.0,
        "goals": 0.0,
        "assists_nhl": 0.0,
        "plus_minus": 0.0,
        "shots": 0.0,
        "save_pct": 0.0,
        "soccer_goals": 0.0,
        "soccer_assists": 0.0,
        "soccer_minutes": 0.0,
        "soccer_shots": 0.0,
        "soccer_shots_on_target": 0.0,
        "soccer_key_passes": 0.0,
        "soccer_tackles": 0.0,
        "soccer_interceptions": 0.0,
        "soccer_clean_sheets": 0.0,
        "soccer_saves": 0.0,
        "soccer_goals_conceded": 0.0,
        "soccer_xg": 0.0,
        "soccer_xa": 0.0,
    }
    defaults.update(overrides)
    return ESPNPlayerStats(**defaults)


def _mock_espn_service():
    """Create a mock ESPN service with find_player_by_name, game_logs, etc."""
    mock = MagicMock()

    info_a = _make_player_info("Patrick Mahomes", "KC", "QB")
    info_b = _make_player_info("Josh Allen", "BUF", "QB")
    stats_a = _make_espn_stats(points_per_game=24.0, usage_rate=30.0)
    stats_b = _make_espn_stats(points_per_game=20.0, usage_rate=25.0)

    async def find_player(name, sport):
        if "mahomes" in name.lower():
            return (info_a, stats_a)
        if "allen" in name.lower():
            return (info_b, stats_b)
        return None

    mock.find_player_by_name = AsyncMock(side_effect=find_player)
    mock.get_player_game_logs = AsyncMock(return_value=[])
    mock.calculate_trends = MagicMock(return_value={})
    mock.get_next_opponent = AsyncMock(return_value=None)
    mock.get_team_defense = AsyncMock(return_value=None)

    return mock


class TestStartSitVerdict:
    @patch("routes.verdicts.claude_service")
    @patch("routes.verdicts.espn_service")
    def test_success_local_only(self, mock_espn, mock_claude, authed_client):
        """Verdict returns full response when Claude is unavailable."""
        espn = _mock_espn_service()
        mock_espn.find_player_by_name = espn.find_player_by_name
        mock_espn.get_player_game_logs = espn.get_player_game_logs
        mock_espn.calculate_trends = espn.calculate_trends
        mock_espn.get_next_opponent = espn.get_next_opponent
        mock_espn.get_team_defense = espn.get_team_defense
        mock_claude.is_available = False

        response = authed_client.post(
            "/verdicts/start-sit",
            json={
                "player_a": "Patrick Mahomes",
                "player_b": "Josh Allen",
                "sport": "nfl",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["verdict"].startswith("Start ")
        assert 0 <= data["confidence"] <= 100
        assert data["reasoning"] is None
        assert data["source"] == "local"

        # Breakdown has all 3 modes
        assert "floor" in data["breakdown"]
        assert "median" in data["breakdown"]
        assert "ceiling" in data["breakdown"]
        for mode in ("floor", "median", "ceiling"):
            bd = data["breakdown"][mode]
            assert "player_a" in bd
            assert "player_b" in bd
            assert "winner" in bd
            assert "margin" in bd

        # Indices for both players
        assert "player_a" in data["indices"]
        assert "player_b" in data["indices"]
        for key in ("sci", "rmi", "gis", "od", "msf"):
            assert key in data["indices"]["player_a"]
            assert key in data["indices"]["player_b"]

    @patch("routes.verdicts.claude_service")
    @patch("routes.verdicts.espn_service")
    def test_success_with_claude(self, mock_espn, mock_claude, authed_client):
        """Verdict includes Claude reasoning when available."""
        espn = _mock_espn_service()
        mock_espn.find_player_by_name = espn.find_player_by_name
        mock_espn.get_player_game_logs = espn.get_player_game_logs
        mock_espn.calculate_trends = espn.calculate_trends
        mock_espn.get_next_opponent = espn.get_next_opponent
        mock_espn.get_team_defense = espn.get_team_defense
        mock_claude.is_available = True
        mock_claude.make_decision = AsyncMock(
            return_value={
                "decision": "Start Mahomes",
                "rationale": "Mahomes dominates the ceiling projection with elite SCI.",
                "confidence": "high",
            }
        )

        response = authed_client.post(
            "/verdicts/start-sit",
            json={"player_a": "Patrick Mahomes", "player_b": "Josh Allen"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["reasoning"] is not None
        assert "Mahomes" in data["reasoning"]
        assert data["source"] == "local+claude"

    @patch("routes.verdicts.espn_service")
    def test_player_not_found(self, mock_espn, authed_client):
        """Returns 404 when a player can't be resolved."""
        mock_espn.find_player_by_name = AsyncMock(return_value=None)

        response = authed_client.post(
            "/verdicts/start-sit",
            json={"player_a": "Nonexistent Player", "player_b": "Josh Allen"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @patch("routes.verdicts.sleeper_service")
    @patch("routes.verdicts.claude_service")
    @patch("routes.verdicts.espn_service")
    def test_with_league_context(
        self, mock_espn, mock_claude, mock_sleeper, authed_client
    ):
        """League settings are included when league_id is provided."""
        espn = _mock_espn_service()
        mock_espn.find_player_by_name = espn.find_player_by_name
        mock_espn.get_player_game_logs = espn.get_player_game_logs
        mock_espn.calculate_trends = espn.calculate_trends
        mock_espn.get_next_opponent = espn.get_next_opponent
        mock_espn.get_team_defense = espn.get_team_defense
        mock_claude.is_available = False

        mock_sleeper.get_league = AsyncMock(
            return_value=SleeperLeague(
                league_id="lg_123",
                name="Test League",
                sport="nfl",
                season="2025",
                season_type="regular",
                status="in_season",
                total_rosters=12,
                roster_positions=["QB", "RB"],
                scoring_settings={"pass_td": 6, "rush_td": 6, "rec": 1},
            )
        )

        response = authed_client.post(
            "/verdicts/start-sit",
            json={
                "player_a": "Patrick Mahomes",
                "player_b": "Josh Allen",
                "league_id": "lg_123",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["league_context"] is not None
        assert data["league_context"]["pass_td"] == 6

    def test_requires_auth(self, test_client):
        """Endpoint requires authentication."""
        response = test_client.post(
            "/verdicts/start-sit",
            json={"player_a": "A", "player_b": "B"},
        )
        assert response.status_code in (401, 403)

    @patch("routes.verdicts.claude_service")
    @patch("routes.verdicts.espn_service")
    def test_claude_failure_graceful(self, mock_espn, mock_claude, authed_client):
        """If Claude fails, verdict still returns with reasoning=null."""
        espn = _mock_espn_service()
        mock_espn.find_player_by_name = espn.find_player_by_name
        mock_espn.get_player_game_logs = espn.get_player_game_logs
        mock_espn.calculate_trends = espn.calculate_trends
        mock_espn.get_next_opponent = espn.get_next_opponent
        mock_espn.get_team_defense = espn.get_team_defense
        mock_claude.is_available = True
        mock_claude.make_decision = AsyncMock(side_effect=RuntimeError("API down"))

        response = authed_client.post(
            "/verdicts/start-sit",
            json={"player_a": "Patrick Mahomes", "player_b": "Josh Allen"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["reasoning"] is None
        assert data["source"] == "local"
        assert data["verdict"].startswith("Start ")

    @patch("routes.verdicts.espn_service")
    def test_player_found_but_no_stats(self, mock_espn, authed_client):
        """Returns 404 when player is found but has no stats (line 92)."""
        info = _make_player_info("Patrick Mahomes", "KC", "QB")
        # Return (info, None) — player found but no stats
        mock_espn.find_player_by_name = AsyncMock(return_value=(info, None))

        response = authed_client.post(
            "/verdicts/start-sit",
            json={"player_a": "Patrick Mahomes", "player_b": "Josh Allen"},
        )

        assert response.status_code == 404
        assert "No stats available" in response.json()["detail"]


class TestBuildReasoningPrompt:
    """Tests for _build_reasoning_prompt helper — lines 128-129."""

    def test_league_settings_included_in_prompt(self):
        """When league_settings is provided, prompt uses those settings."""
        from core.scoring import IndexScores
        from core.verdicts import Verdict, RiskBreakdown
        from routes.verdicts import _build_reasoning_prompt

        idx = IndexScores(sci=80.0, rmi=70.0, gis=60.0, od=50.0, msf=40.0)
        bd = RiskBreakdown(score_a=75.0, score_b=60.0, winner="Mahomes", margin=15.0)
        verdict = Verdict(
            player_a_name="Mahomes",
            player_b_name="Allen",
            decision="Start Mahomes",
            confidence=80,
            margin=15.0,
            floor=bd,
            median=bd,
            ceiling=bd,
            indices_a=idx,
            indices_b=idx,
        )
        league_settings = {"pass_td": 6, "rush_td": 6, "rec": 1, "ppr": 1.0}

        prompt = _build_reasoning_prompt(verdict, league_settings)

        # Lines 128-129: league settings formatted into the prompt
        assert "pass_td: 6" in prompt
        assert "rush_td: 6" in prompt
        # Standard scoring should NOT appear
        assert "standard scoring" not in prompt

    def test_no_league_settings_uses_standard(self):
        """When league_settings is None, prompt uses 'standard scoring'."""
        from core.scoring import IndexScores
        from core.verdicts import Verdict, RiskBreakdown
        from routes.verdicts import _build_reasoning_prompt

        idx = IndexScores(sci=80.0, rmi=70.0, gis=60.0, od=50.0, msf=40.0)
        bd = RiskBreakdown(score_a=75.0, score_b=60.0, winner="Mahomes", margin=15.0)
        verdict = Verdict(
            player_a_name="Mahomes",
            player_b_name="Allen",
            decision="Start Mahomes",
            confidence=80,
            margin=15.0,
            floor=bd,
            median=bd,
            ceiling=bd,
            indices_a=idx,
            indices_b=idx,
        )

        prompt = _build_reasoning_prompt(verdict, None)

        assert "standard scoring" in prompt
