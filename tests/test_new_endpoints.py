"""Tests for admin grant-pro, player news, calibration, and ops endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch


# ---- helpers ---------------------------------------------------------------


def _mock_db_session():
    mock_session = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_session


def _override_admin():
    from api.main import app
    from routes.auth import require_admin_key

    app.dependency_overrides[require_admin_key] = lambda: "admin"


def _clear_overrides():
    from api.main import app

    app.dependency_overrides.clear()


# =============================================================================
# ADMIN GRANT-PRO
# =============================================================================


class TestAdminGrantPro:
    def setup_method(self):
        _override_admin()

    def teardown_method(self):
        _clear_overrides()

    @patch("api.main.db_service")
    def test_grant_pro_success(self, mock_db, test_client):
        mock_ctx, mock_session = _mock_db_session()
        mock_db.is_configured = True
        mock_db.session.return_value = mock_ctx

        mock_user = MagicMock()
        mock_user.email = "judychad@gmail.com"
        mock_user.subscription_tier = "free"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        resp = test_client.post(
            "/admin/grant-pro",
            json={"email": "judychad@gmail.com", "days": 30},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "granted"
        assert data["email"] == "judychad@gmail.com"
        assert data["tier"] == "pro"
        assert mock_user.subscription_tier == "pro"

    @patch("api.main.db_service")
    def test_grant_pro_user_not_found(self, mock_db, test_client):
        mock_ctx, mock_session = _mock_db_session()
        mock_db.is_configured = True
        mock_db.session.return_value = mock_ctx

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        resp = test_client.post(
            "/admin/grant-pro",
            json={"email": "nobody@example.com"},
        )
        assert resp.status_code == 404

    @patch("api.main.db_service")
    def test_grant_pro_db_not_configured(self, mock_db, test_client):
        mock_db.is_configured = False

        resp = test_client.post(
            "/admin/grant-pro",
            json={"email": "test@example.com"},
        )
        assert resp.status_code == 503

    @patch.dict("os.environ", {"ADMIN_API_KEY": "real-admin-key"})
    def test_grant_pro_wrong_admin_key(self, test_client):
        _clear_overrides()
        resp = test_client.post(
            "/admin/grant-pro",
            json={"email": "test@example.com"},
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert resp.status_code == 403

    @patch("api.main.db_service")
    def test_grant_pro_default_days(self, mock_db, test_client):
        mock_ctx, mock_session = _mock_db_session()
        mock_db.is_configured = True
        mock_db.session.return_value = mock_ctx

        mock_user = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        resp = test_client.post(
            "/admin/grant-pro",
            json={"email": "test@example.com"},
        )
        assert resp.status_code == 200
        assert resp.json()["days"] == 30


# =============================================================================
# ACCURACY CALIBRATION
# =============================================================================


class TestAccuracyCalibration:
    @patch("api.main.db_service")
    def test_calibration_success(self, mock_db, test_client):
        mock_ctx, mock_session = _mock_db_session()
        mock_db.is_configured = True
        mock_db.session.return_value = mock_ctx

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"confidence": "high", "total": 50, "correct": 40, "accuracy_pct": 80.0},
            {"confidence": "medium", "total": 80, "correct": 50, "accuracy_pct": 62.5},
            {"confidence": "low", "total": 30, "correct": 10, "accuracy_pct": 33.3},
        ]
        mock_session.execute = AsyncMock(return_value=mock_result)

        resp = test_client.get("/accuracy/calibration")
        assert resp.status_code == 200
        data = resp.json()
        assert "levels" in data
        assert data["levels"]["high"]["accuracy_pct"] == 80.0
        assert data["well_calibrated"] is True
        assert "current_thresholds" in data

    @patch("api.main.db_service")
    def test_calibration_not_calibrated(self, mock_db, test_client):
        mock_ctx, mock_session = _mock_db_session()
        mock_db.is_configured = True
        mock_db.session.return_value = mock_ctx

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"confidence": "high", "total": 10, "correct": 3, "accuracy_pct": 30.0},
            {"confidence": "low", "total": 20, "correct": 15, "accuracy_pct": 75.0},
        ]
        mock_session.execute = AsyncMock(return_value=mock_result)

        resp = test_client.get("/accuracy/calibration")
        assert resp.status_code == 200
        assert resp.json()["well_calibrated"] is False

    @patch("api.main.db_service")
    def test_calibration_no_data(self, mock_db, test_client):
        mock_ctx, mock_session = _mock_db_session()
        mock_db.is_configured = True
        mock_db.session.return_value = mock_ctx

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        resp = test_client.get("/accuracy/calibration")
        assert resp.status_code == 200
        data = resp.json()
        assert data["levels"] == {}
        assert data["well_calibrated"] is None

    @patch("api.main.db_service")
    def test_calibration_db_not_configured(self, mock_db, test_client):
        mock_db.is_configured = False

        resp = test_client.get("/accuracy/calibration")
        assert resp.status_code == 503


# =============================================================================
# PLAYER NEWS (dossier route)
# =============================================================================


class TestPlayerNews:
    @patch("routes.dossier.espn_service")
    @patch("routes.dossier.rate_limiter")
    def test_news_success_with_injury(self, mock_rl, mock_espn, test_client):
        mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))

        info = MagicMock()
        info.name = "LeBron James"
        info.id = "1966"
        info.team_abbrev = "LAL"
        info.position = "PF"
        info.injury_status = "Questionable"
        info.injury_detail = "Left ankle"

        mock_espn.find_player_by_name = AsyncMock(return_value=(info, MagicMock()))
        mock_espn.get_player_game_logs = AsyncMock(return_value=[])
        mock_espn.calculate_trends.return_value = {
            "minutes_trend": 0,
            "points_trend": 0,
        }
        mock_espn.get_next_game = AsyncMock(return_value=None)

        resp = test_client.get("/dossier/news/nba/LeBron%20James")
        assert resp.status_code == 200
        data = resp.json()
        assert data["player_name"] == "LeBron James"
        assert data["sport"] == "nba"
        assert any(item["type"] == "injury" for item in data["items"])

    @patch("routes.dossier.espn_service")
    @patch("routes.dossier.rate_limiter")
    def test_news_player_not_found(self, mock_rl, mock_espn, test_client):
        mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
        mock_espn.find_player_by_name = AsyncMock(return_value=None)

        resp = test_client.get("/dossier/news/nba/FakePlayer")
        assert resp.status_code == 404

    @patch("routes.dossier.espn_service")
    @patch("routes.dossier.rate_limiter")
    def test_news_invalid_sport(self, mock_rl, mock_espn, test_client):
        mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))

        resp = test_client.get("/dossier/news/cricket/Someone")
        assert resp.status_code == 400

    @patch("routes.dossier.espn_service")
    @patch("routes.dossier.rate_limiter")
    def test_news_rate_limited(self, mock_rl, mock_espn, test_client):
        mock_rl.check_rate_limit = AsyncMock(return_value=(False, 30))

        resp = test_client.get("/dossier/news/nba/LeBron%20James")
        assert resp.status_code == 429

    @patch("routes.dossier.espn_service")
    @patch("routes.dossier.rate_limiter")
    def test_news_with_matchup(self, mock_rl, mock_espn, test_client):
        mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))

        info = MagicMock()
        info.name = "Jayson Tatum"
        info.id = "4065648"
        info.team_abbrev = "BOS"
        info.position = "SF"
        info.injury_status = None
        info.injury_detail = None

        next_game = MagicMock()
        next_game.home_abbrev = "BOS"
        next_game.away_abbrev = "NYK"
        next_game.spread = -4.5
        next_game.over_under = 218.5

        mock_espn.find_player_by_name = AsyncMock(return_value=(info, MagicMock()))
        mock_espn.get_player_game_logs = AsyncMock(return_value=[])
        mock_espn.calculate_trends.return_value = {
            "minutes_trend": 0,
            "points_trend": 0,
        }
        mock_espn.get_next_game = AsyncMock(return_value=next_game)

        resp = test_client.get("/dossier/news/nba/Jayson%20Tatum")
        assert resp.status_code == 200
        data = resp.json()
        assert any(item["type"] == "matchup" for item in data["items"])

    @patch("routes.dossier.espn_service")
    @patch("routes.dossier.rate_limiter")
    def test_news_with_trends(self, mock_rl, mock_espn, test_client):
        mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))

        info = MagicMock()
        info.name = "Luka Doncic"
        info.id = "4395725"
        info.team_abbrev = "DAL"
        info.position = "PG"
        info.injury_status = None
        info.injury_detail = None

        mock_espn.find_player_by_name = AsyncMock(return_value=(info, MagicMock()))
        mock_espn.get_player_game_logs = AsyncMock(return_value=[MagicMock()])
        mock_espn.calculate_trends.return_value = {
            "minutes_trend": 3.5,
            "points_trend": -2.5,
        }
        mock_espn.get_next_game = AsyncMock(return_value=None)

        resp = test_client.get("/dossier/news/nba/Luka%20Doncic")
        assert resp.status_code == 200
        data = resp.json()
        items = data["items"]
        assert any("Minutes" in item["headline"] for item in items)
        assert any("Scoring" in item["headline"] for item in items)

    @patch("routes.dossier.espn_service")
    @patch("routes.dossier.rate_limiter")
    def test_news_no_items(self, mock_rl, mock_espn, test_client):
        """Player with no injury, no significant trends, no matchup."""
        mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))

        info = MagicMock()
        info.name = "Bench Warmer"
        info.id = "99999"
        info.team_abbrev = "BKN"
        info.position = "C"
        info.injury_status = None
        info.injury_detail = None

        mock_espn.find_player_by_name = AsyncMock(return_value=(info, MagicMock()))
        mock_espn.get_player_game_logs = AsyncMock(return_value=[])
        mock_espn.calculate_trends.return_value = {
            "minutes_trend": 0,
            "points_trend": 0,
        }
        mock_espn.get_next_game = AsyncMock(return_value=None)

        resp = test_client.get("/dossier/news/nba/Bench%20Warmer")
        assert resp.status_code == 200
        assert resp.json()["items"] == []


# =============================================================================
# OPS HEALTH (admin/ops)
# =============================================================================


class TestAdminOps:
    def setup_method(self):
        _override_admin()

    def teardown_method(self):
        _clear_overrides()

    @patch("api.main.db_service")
    @patch("api.main.redis_service")
    @patch("api.main.claude_service")
    def test_ops_success(self, mock_claude, mock_redis, mock_db, test_client):
        mock_claude.is_available = True
        mock_db.is_configured = True
        mock_redis.is_connected = True

        mock_ctx, mock_session = _mock_db_session()
        mock_db.session.return_value = mock_ctx

        # Mock DB queries: tables, size, decisions
        tables_result = MagicMock()
        tables_result.mappings.return_value.all.return_value = [
            {"table_name": "decisions", "row_count": 500},
            {"table_name": "users", "row_count": 10},
        ]
        size_result = MagicMock()
        size_result.scalar.return_value = "42 MB"
        decisions_result = MagicMock()
        decisions_result.mappings.return_value.first.return_value = {
            "total_decisions": 500,
            "with_outcomes": 50,
            "oldest_decision": "2025-01-01",
            "newest_decision": "2026-03-07",
        }
        mock_session.execute = AsyncMock(
            side_effect=[tables_result, size_result, decisions_result]
        )

        resp = test_client.get("/admin/ops")
        assert resp.status_code == 200
        data = resp.json()
        assert data["services"]["claude"] is True
        assert data["services"]["postgres"] is True
        assert "database" in data
        assert "schedulers" in data
        assert isinstance(data["config_warnings"], list)

    @patch("api.main.db_service")
    @patch("api.main.redis_service")
    @patch("api.main.claude_service")
    def test_ops_db_not_configured(self, mock_claude, mock_redis, mock_db, test_client):
        mock_claude.is_available = False
        mock_db.is_configured = False
        mock_redis.is_connected = False

        resp = test_client.get("/admin/ops")
        assert resp.status_code == 200
        data = resp.json()
        assert data["services"]["postgres"] is False
        assert data["database"] == {}

    def test_ops_no_admin_key(self, test_client):
        _clear_overrides()
        resp = test_client.get("/admin/ops")
        # 503 because ADMIN_API_KEY env var not set in test
        assert resp.status_code == 503
