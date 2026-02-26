"""Tests for the player dossier endpoint."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from routes.dossier import (
    _extract_game_log_stats,
)


# -------------------------------------------------------------------------
# Unit tests for stat extraction
# -------------------------------------------------------------------------


class TestExtractGameLogStats:
    """Tests for _extract_game_log_stats helper."""

    def test_nba_stats(self):
        gl = MagicMock()
        gl.minutes = 35
        gl.points = 28
        gl.rebounds = 7
        gl.assists = 10
        gl.steals = 2
        gl.blocks = 1
        gl.turnovers = 3
        gl.fg_made = 11
        gl.fg_attempted = 20
        gl.three_made = 4
        gl.three_attempted = 9
        gl.ft_made = 2
        gl.ft_attempted = 3

        stats = _extract_game_log_stats(gl, "nba")
        assert stats["points"] == 28
        assert stats["assists"] == 10
        assert stats["rebounds"] == 7
        assert "pass_yards_game" not in stats

    def test_nfl_stats(self):
        gl = MagicMock()
        gl.pass_yards_game = 312
        gl.pass_tds_game = 3
        gl.pass_ints_game = 1
        gl.rush_yards_game = 15
        gl.rush_tds_game = 0
        gl.receptions_game = None
        gl.receiving_yards_game = None
        gl.receiving_tds_game = None
        gl.targets_game = None
        gl.snaps = 65
        gl.snap_pct_game = Decimal("95.50")

        stats = _extract_game_log_stats(gl, "nfl")
        assert stats["pass_yards_game"] == 312
        assert stats["snap_pct_game"] == 95.50
        assert "receptions_game" not in stats  # None values excluded
        assert "points" not in stats  # NBA field excluded

    def test_mlb_stats(self):
        gl = MagicMock()
        gl.at_bats = 4
        gl.hits = 2
        gl.home_runs_game = 1
        gl.rbis_game = 3
        gl.stolen_bases_game = 0
        gl.walks = 1
        gl.strikeouts_game = 1
        gl.innings_pitched = None
        gl.earned_runs = None

        stats = _extract_game_log_stats(gl, "mlb")
        assert stats["at_bats"] == 4
        assert stats["home_runs_game"] == 1
        assert stats["stolen_bases_game"] == 0
        assert "innings_pitched" not in stats

    def test_nhl_stats(self):
        gl = MagicMock()
        gl.goals_game = 2
        gl.assists_game = 1
        gl.plus_minus_game = 3
        gl.shots_game = 5
        gl.time_on_ice = 1200
        gl.saves = None
        gl.goals_against = None

        stats = _extract_game_log_stats(gl, "nhl")
        assert stats["goals_game"] == 2
        assert stats["time_on_ice"] == 1200
        assert "saves" not in stats

    def test_soccer_stats(self):
        gl = MagicMock()
        gl.soccer_goals_game = 1
        gl.soccer_assists_game = 0
        gl.soccer_minutes_game = 90
        gl.soccer_shots_game = 4
        gl.soccer_shots_on_target_game = 2
        gl.soccer_key_passes_game = 3
        gl.soccer_tackles_game = 1
        gl.soccer_interceptions_game = 0
        gl.soccer_clean_sheet = False
        gl.soccer_saves_game = None
        gl.soccer_goals_conceded_game = None
        gl.soccer_xg_game = Decimal("0.85")
        gl.soccer_xa_game = Decimal("0.12")

        stats = _extract_game_log_stats(gl, "soccer")
        assert stats["soccer_goals_game"] == 1
        assert stats["soccer_xg_game"] == 0.85
        assert stats["soccer_clean_sheet"] is False
        assert "soccer_saves_game" not in stats

    def test_unknown_sport_falls_back_to_nba(self):
        gl = MagicMock()
        gl.minutes = 30
        gl.points = 20
        gl.rebounds = 5
        gl.assists = 4
        gl.steals = None
        gl.blocks = None
        gl.turnovers = None
        gl.fg_made = None
        gl.fg_attempted = None
        gl.three_made = None
        gl.three_attempted = None
        gl.ft_made = None
        gl.ft_attempted = None

        stats = _extract_game_log_stats(gl, "curling")
        assert stats["minutes"] == 30
        assert stats["points"] == 20

    def test_string_stat_value_passthrough(self):
        """Values without __float__ (e.g., strings) pass through unchanged."""
        gl = MagicMock()
        gl.minutes = "DNP"
        gl.points = None
        gl.rebounds = None
        gl.assists = None
        gl.steals = None
        gl.blocks = None
        gl.turnovers = None
        gl.fg_made = None
        gl.fg_attempted = None
        gl.three_made = None
        gl.three_attempted = None
        gl.ft_made = None
        gl.ft_attempted = None

        stats = _extract_game_log_stats(gl, "nba")
        assert stats["minutes"] == "DNP"

    def test_decimal_conversion(self):
        gl = MagicMock()
        gl.minutes = None
        gl.points = None
        gl.rebounds = None
        gl.assists = None
        gl.steals = None
        gl.blocks = None
        gl.turnovers = None
        gl.fg_made = None
        gl.fg_attempted = None
        gl.three_made = None
        gl.three_attempted = None
        gl.ft_made = None
        gl.ft_attempted = None
        gl.fantasy_points = Decimal("25.50")

        # All None = empty dict
        stats = _extract_game_log_stats(gl, "nba")
        assert stats == {}


# -------------------------------------------------------------------------
# Endpoint tests
# -------------------------------------------------------------------------


class TestDossierEndpoint:
    """Tests for GET /dossier/{sport}/{player_id}."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from main import app

        return TestClient(app)

    @pytest.fixture
    def mock_espn_player(self):
        player = MagicMock()
        player.id = "12345"
        player.name = "LeBron James"
        player.team = "Los Angeles Lakers"
        player.team_abbrev = "LAL"
        player.position = "SF"
        player.headshot_url = "https://example.com/lebron.png"
        return player

    @pytest.fixture
    def mock_espn_stats(self):
        from types import SimpleNamespace

        return SimpleNamespace(
            player_id="12345",
            sport="nba",
            points_per_game=25.8,
            rebounds_per_game=7.5,
            assists_per_game=8.1,
        )

    @patch("routes.dossier.rate_limiter")
    @patch("routes.dossier.db_service")
    @patch("routes.dossier.espn_service")
    def test_player_not_found(self, mock_espn, mock_db, mock_rl, client):
        mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
        mock_espn.get_player = AsyncMock(return_value=None)

        resp = client.get("/dossier/nba/99999")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Player not found"

    @patch("routes.dossier.rate_limiter")
    @patch("routes.dossier.db_service")
    @patch("routes.dossier.espn_service")
    def test_rate_limited(self, mock_espn, mock_db, mock_rl, client):
        mock_rl.check_rate_limit = AsyncMock(return_value=(False, 30))

        resp = client.get("/dossier/nba/12345")
        assert resp.status_code == 429
        assert "Rate limit exceeded" in resp.json()["detail"]
        assert resp.headers["Retry-After"] == "30"

    @patch("routes.dossier.rate_limiter")
    @patch("routes.dossier.db_service")
    @patch("routes.dossier.espn_service")
    def test_happy_path_no_db(
        self, mock_espn, mock_db, mock_rl, client, mock_espn_player, mock_espn_stats
    ):
        mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
        mock_espn.get_player = AsyncMock(return_value=mock_espn_player)
        mock_espn.get_player_stats = AsyncMock(return_value=mock_espn_stats)
        mock_db.is_configured = False

        resp = client.get("/dossier/nba/12345")
        assert resp.status_code == 200
        data = resp.json()

        assert data["player"]["name"] == "LeBron James"
        assert data["player"]["sport"] == "nba"
        assert data["player"]["stats"]["points_per_game"] == 25.8
        assert data["indices"] == []
        assert data["game_logs"] == []
        assert data["decisions"] == []
        assert data["summary"]["games_played"] == 0
        assert data["summary"]["latest_median"] is None

    @patch("routes.dossier.rate_limiter")
    @patch("routes.dossier.db_service")
    @patch("routes.dossier.espn_service")
    def test_happy_path_with_db_player_not_in_db(
        self, mock_espn, mock_db, mock_rl, client, mock_espn_player, mock_espn_stats
    ):
        mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
        mock_espn.get_player = AsyncMock(return_value=mock_espn_player)
        mock_espn.get_player_stats = AsyncMock(return_value=mock_espn_stats)
        mock_db.is_configured = True

        # Mock the session context manager
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db.session = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        resp = client.get("/dossier/nba/12345")
        assert resp.status_code == 200
        data = resp.json()
        assert data["player"]["name"] == "LeBron James"
        assert data["indices"] == []
        assert data["game_logs"] == []
        assert data["decisions"] == []

    @patch("routes.dossier.rate_limiter")
    @patch("routes.dossier.db_service")
    @patch("routes.dossier.espn_service")
    def test_happy_path_with_db_data(
        self, mock_espn, mock_db, mock_rl, client, mock_espn_player, mock_espn_stats
    ):
        mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
        mock_espn.get_player = AsyncMock(return_value=mock_espn_player)
        mock_espn.get_player_stats = AsyncMock(return_value=mock_espn_stats)
        mock_db.is_configured = True

        db_player_id = uuid.uuid4()
        mock_db_player = MagicMock()
        mock_db_player.id = db_player_id
        mock_db_player.name = "LeBron James"
        mock_db_player.espn_id = "12345"

        # Mock index row
        mock_index = MagicMock()
        mock_index.sci = Decimal("75.50")
        mock_index.rmi = Decimal("82.30")
        mock_index.gis = Decimal("68.10")
        mock_index.od = Decimal("71.90")
        mock_index.msf = Decimal("79.40")
        mock_index.floor_score = Decimal("62.00")
        mock_index.median_score = Decimal("75.50")
        mock_index.ceiling_score = Decimal("88.20")
        mock_index.calculated_at = datetime(2026, 2, 26, tzinfo=UTC)
        mock_index.opponent = "BOS"
        mock_index.game_date = datetime(2026, 2, 27)

        # Mock game log row
        mock_gl = MagicMock()
        mock_gl.game_date = datetime(2026, 2, 25)
        mock_gl.opponent = "MIA"
        mock_gl.home_away = "H"
        mock_gl.result = "W"
        mock_gl.fantasy_points = Decimal("42.50")
        mock_gl.minutes = 36
        mock_gl.points = 32
        mock_gl.rebounds = 8
        mock_gl.assists = 10
        mock_gl.steals = 2
        mock_gl.blocks = 1
        mock_gl.turnovers = 3
        mock_gl.fg_made = 12
        mock_gl.fg_attempted = 22
        mock_gl.three_made = 4
        mock_gl.three_attempted = 9
        mock_gl.ft_made = 4
        mock_gl.ft_attempted = 4

        # Mock decision row
        mock_decision = MagicMock()
        mock_decision.id = uuid.uuid4()
        mock_decision.decision_type = "start_sit"
        mock_decision.query = "Should I start LeBron?"
        mock_decision.decision = "Start LeBron"
        mock_decision.confidence = "high"
        mock_decision.risk_mode = "median"
        mock_decision.source = "claude"
        mock_decision.created_at = datetime(2026, 2, 24, tzinfo=UTC)
        mock_decision.actual_outcome = "correct"
        mock_decision.sport = "nba"

        # Build mock session that returns different results per query
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # Player lookup
                result.scalar_one_or_none.return_value = mock_db_player
            elif call_count == 2:
                # Indices
                result.scalars.return_value.all.return_value = [mock_index]
            elif call_count == 3:
                # Game logs
                result.scalars.return_value.all.return_value = [mock_gl]
            elif call_count == 4:
                # Decisions
                result.scalars.return_value.all.return_value = [mock_decision]
            return result

        mock_session = AsyncMock()
        mock_session.execute = mock_execute

        mock_db.session = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        resp = client.get("/dossier/nba/12345")
        assert resp.status_code == 200
        data = resp.json()

        # Player
        assert data["player"]["name"] == "LeBron James"

        # Indices
        assert len(data["indices"]) == 1
        assert data["indices"][0]["sci"] == 75.50
        assert data["indices"][0]["median_score"] == 75.50
        assert data["indices"][0]["opponent"] == "BOS"

        # Game logs
        assert len(data["game_logs"]) == 1
        assert data["game_logs"][0]["fantasy_points"] == 42.50
        assert data["game_logs"][0]["stats"]["points"] == 32
        assert data["game_logs"][0]["home_away"] == "H"
        assert data["game_logs"][0]["result"] == "W"

        # Decisions
        assert len(data["decisions"]) == 1
        assert data["decisions"][0]["query"] == "Should I start LeBron?"
        assert data["decisions"][0]["outcome"] == "correct"

        # Summary
        assert data["summary"]["games_played"] == 1
        assert data["summary"]["total_indices"] == 1
        assert data["summary"]["total_decisions"] == 1
        assert data["summary"]["latest_median"] == 75.50

    @patch("routes.dossier.rate_limiter")
    @patch("routes.dossier.db_service")
    @patch("routes.dossier.espn_service")
    def test_db_error_graceful_degradation(
        self, mock_espn, mock_db, mock_rl, client, mock_espn_player, mock_espn_stats
    ):
        mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
        mock_espn.get_player = AsyncMock(return_value=mock_espn_player)
        mock_espn.get_player_stats = AsyncMock(return_value=mock_espn_stats)
        mock_db.is_configured = True

        from sqlalchemy.exc import OperationalError

        mock_db.session = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(
                    side_effect=OperationalError("conn", {}, Exception("timeout"))
                ),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        resp = client.get("/dossier/nba/12345")
        assert resp.status_code == 200
        data = resp.json()
        # Still returns player data from ESPN
        assert data["player"]["name"] == "LeBron James"
        assert data["indices"] == []
        assert data["game_logs"] == []

    @patch("routes.dossier.rate_limiter")
    @patch("routes.dossier.db_service")
    @patch("routes.dossier.espn_service")
    def test_no_stats_available(
        self, mock_espn, mock_db, mock_rl, client, mock_espn_player
    ):
        mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
        mock_espn.get_player = AsyncMock(return_value=mock_espn_player)
        mock_espn.get_player_stats = AsyncMock(return_value=None)
        mock_db.is_configured = False

        resp = client.get("/dossier/nba/12345")
        assert resp.status_code == 200
        data = resp.json()
        assert data["player"]["stats"] is None

    @patch("routes.dossier.rate_limiter")
    @patch("routes.dossier.db_service")
    @patch("routes.dossier.espn_service")
    def test_fantasy_points_zero_not_none(
        self, mock_espn, mock_db, mock_rl, client, mock_espn_player, mock_espn_stats
    ):
        """Verify fantasy_points=0.0 is not converted to None."""
        mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
        mock_espn.get_player = AsyncMock(return_value=mock_espn_player)
        mock_espn.get_player_stats = AsyncMock(return_value=mock_espn_stats)
        mock_db.is_configured = True

        db_player = MagicMock()
        db_player.id = uuid.uuid4()
        db_player.name = "LeBron James"

        mock_gl = MagicMock()
        mock_gl.game_date = datetime(2026, 2, 25)
        mock_gl.opponent = "BOS"
        mock_gl.home_away = "H"
        mock_gl.result = "L"
        mock_gl.fantasy_points = Decimal("0.00")
        # Set NBA stats
        for attr in [
            "minutes",
            "points",
            "rebounds",
            "assists",
            "steals",
            "blocks",
            "turnovers",
            "fg_made",
            "fg_attempted",
            "three_made",
            "three_attempted",
            "ft_made",
            "ft_attempted",
        ]:
            setattr(mock_gl, attr, 0)

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = db_player
            elif call_count == 2:
                result.scalars.return_value.all.return_value = []
            elif call_count == 3:
                result.scalars.return_value.all.return_value = [mock_gl]
            elif call_count == 4:
                result.scalars.return_value.all.return_value = []
            return result

        mock_session = AsyncMock()
        mock_session.execute = mock_execute

        mock_db.session = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        resp = client.get("/dossier/nba/12345")
        assert resp.status_code == 200
        data = resp.json()
        assert data["game_logs"][0]["fantasy_points"] == 0.0
