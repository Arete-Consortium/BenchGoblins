"""Tests for league integration routes (Sleeper)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.sleeper import SleeperLeague, SleeperPlayer, SleeperRoster, SleeperUser

VALID_USER = {
    "user_id": 1,
    "email": "test@example.com",
    "name": "Test User",
    "tier": "pro",
    "exp": 9999999999,
}


@pytest.fixture
def authed_client(test_client):
    """Test client with auth bypassed."""
    from api.main import app
    from routes.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: VALID_USER
    yield test_client
    app.dependency_overrides.pop(get_current_user, None)


def _make_sleeper_user(**overrides):
    defaults = {
        "user_id": "sl_123",
        "username": "goblinmaster",
        "display_name": "Goblin Master",
        "avatar": "abc123",
    }
    defaults.update(overrides)
    return SleeperUser(**defaults)


def _make_sleeper_league(**overrides):
    defaults = {
        "league_id": "lg_456",
        "name": "Fantasy Goblins",
        "sport": "nfl",
        "season": "2025",
        "season_type": "regular",
        "status": "in_season",
        "total_rosters": 12,
        "roster_positions": [
            "QB",
            "RB",
            "RB",
            "WR",
            "WR",
            "TE",
            "FLEX",
            "K",
            "DEF",
            "BN",
        ],
        "scoring_settings": {"pass_td": 4, "rush_td": 6, "rec": 1},
    }
    defaults.update(overrides)
    return SleeperLeague(**defaults)


def _make_sleeper_roster(**overrides):
    defaults = {
        "roster_id": 1,
        "owner_id": "sl_123",
        "players": ["p1", "p2", "p3"],
        "starters": ["p1", "p2"],
        "reserve": None,
    }
    defaults.update(overrides)
    return SleeperRoster(**defaults)


def _make_sleeper_player(player_id="p1", **overrides):
    defaults = {
        "player_id": player_id,
        "full_name": "Patrick Mahomes",
        "first_name": "Patrick",
        "last_name": "Mahomes",
        "team": "KC",
        "position": "QB",
        "sport": "nfl",
        "status": "Active",
        "injury_status": None,
        "age": 29,
        "years_exp": 8,
    }
    defaults.update(overrides)
    return SleeperPlayer(**defaults)


# -------------------------------------------------------------------------
# POST /leagues/connect
# -------------------------------------------------------------------------


class TestConnectSleeper:
    @patch("routes.leagues.sleeper_service")
    def test_connect_success(self, mock_svc, authed_client):
        mock_svc.get_user = AsyncMock(return_value=_make_sleeper_user())
        mock_svc.get_user_leagues = AsyncMock(
            return_value=[
                _make_sleeper_league(),
                _make_sleeper_league(league_id="lg_789", name="Second League"),
            ]
        )

        response = authed_client.post(
            "/leagues/connect",
            json={"username": "goblinmaster", "sport": "nfl", "season": "2025"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sleeper_user"]["user_id"] == "sl_123"
        assert data["sleeper_user"]["username"] == "goblinmaster"
        assert len(data["leagues"]) == 2
        assert data["leagues"][0]["league_id"] == "lg_456"
        assert data["leagues"][0]["scoring_settings"]["pass_td"] == 4
        assert data["leagues"][1]["name"] == "Second League"

    @patch("routes.leagues.sleeper_service")
    def test_connect_user_not_found(self, mock_svc, authed_client):
        mock_svc.get_user = AsyncMock(return_value=None)

        response = authed_client.post(
            "/leagues/connect",
            json={"username": "nobody_here"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @patch("routes.leagues.sleeper_service")
    def test_connect_no_leagues(self, mock_svc, authed_client):
        mock_svc.get_user = AsyncMock(return_value=_make_sleeper_user())
        mock_svc.get_user_leagues = AsyncMock(return_value=[])

        response = authed_client.post(
            "/leagues/connect",
            json={"username": "goblinmaster"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sleeper_user"]["user_id"] == "sl_123"
        assert data["leagues"] == []

    @patch("routes.leagues.sleeper_service")
    def test_connect_nba(self, mock_svc, authed_client):
        mock_svc.get_user = AsyncMock(return_value=_make_sleeper_user())
        mock_svc.get_user_leagues = AsyncMock(
            return_value=[_make_sleeper_league(sport="nba")]
        )

        response = authed_client.post(
            "/leagues/connect",
            json={"username": "goblinmaster", "sport": "nba", "season": "2025"},
        )

        assert response.status_code == 200
        mock_svc.get_user_leagues.assert_called_once_with(
            user_id="sl_123", sport="nba", season="2025"
        )


# -------------------------------------------------------------------------
# GET /leagues/{league_id}/roster
# -------------------------------------------------------------------------


class TestGetRoster:
    @patch("routes.leagues.sleeper_service")
    def test_roster_success(self, mock_svc, authed_client):
        mock_svc.get_user_roster = AsyncMock(return_value=_make_sleeper_roster())
        mock_svc.get_players_by_ids = AsyncMock(
            return_value=[
                _make_sleeper_player("p1", full_name="Patrick Mahomes", position="QB"),
                _make_sleeper_player("p2", full_name="Travis Kelce", position="TE"),
                _make_sleeper_player("p3", full_name="Isiah Pacheco", position="RB"),
            ]
        )

        response = authed_client.get(
            "/leagues/lg_456/roster",
            params={"sleeper_user_id": "sl_123", "sport": "nfl"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["roster_id"] == 1
        assert data["owner_id"] == "sl_123"
        assert len(data["players"]) == 3
        assert data["starters"] == ["p1", "p2"]

        # Check starter flags
        players_by_id = {p["player_id"]: p for p in data["players"]}
        assert players_by_id["p1"]["is_starter"] is True
        assert players_by_id["p2"]["is_starter"] is True
        assert players_by_id["p3"]["is_starter"] is False

    @patch("routes.leagues.sleeper_service")
    def test_roster_not_found(self, mock_svc, authed_client):
        mock_svc.get_user_roster = AsyncMock(return_value=None)

        response = authed_client.get(
            "/leagues/lg_456/roster",
            params={"sleeper_user_id": "nobody"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @patch("routes.leagues.sleeper_service")
    def test_roster_with_reserve(self, mock_svc, authed_client):
        mock_svc.get_user_roster = AsyncMock(
            return_value=_make_sleeper_roster(reserve=["p3"])
        )
        mock_svc.get_players_by_ids = AsyncMock(
            return_value=[
                _make_sleeper_player("p1"),
                _make_sleeper_player("p2"),
                _make_sleeper_player("p3", status="Injured Reserve"),
            ]
        )

        response = authed_client.get(
            "/leagues/lg_456/roster",
            params={"sleeper_user_id": "sl_123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["reserve"] == ["p3"]

    def test_roster_requires_user_id_param(self, authed_client):
        response = authed_client.get("/leagues/lg_456/roster")
        assert response.status_code == 422  # Missing required query param


# -------------------------------------------------------------------------
# GET /leagues/{league_id}/settings
# -------------------------------------------------------------------------


class TestGetLeagueSettings:
    @patch("routes.leagues.sleeper_service")
    def test_settings_success(self, mock_svc, authed_client):
        mock_svc.get_league = AsyncMock(return_value=_make_sleeper_league())

        response = authed_client.get("/leagues/lg_456/settings")

        assert response.status_code == 200
        data = response.json()
        assert data["league_id"] == "lg_456"
        assert data["name"] == "Fantasy Goblins"
        assert data["total_rosters"] == 12
        assert data["scoring_settings"]["pass_td"] == 4
        assert "QB" in data["roster_positions"]

    @patch("routes.leagues.sleeper_service")
    def test_settings_not_found(self, mock_svc, authed_client):
        mock_svc.get_league = AsyncMock(return_value=None)

        response = authed_client.get("/leagues/nonexistent/settings")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


# -------------------------------------------------------------------------
# Helpers for sync/persistence tests
# -------------------------------------------------------------------------


def _mock_db_session(mock_user=None):
    """Create a mock db_service with session() returning a mock that yields mock_user."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_db = MagicMock()
    mock_db.session.return_value = mock_ctx
    return mock_db, mock_session


def _make_mock_user(**overrides):
    """Create a mock User ORM object with Sleeper columns."""
    user = MagicMock()
    user.id = overrides.get("id", 1)
    user.sleeper_username = overrides.get("sleeper_username", None)
    user.sleeper_user_id = overrides.get("sleeper_user_id", None)
    user.sleeper_league_id = overrides.get("sleeper_league_id", None)
    user.roster_snapshot = overrides.get("roster_snapshot", None)
    user.sleeper_synced_at = overrides.get("sleeper_synced_at", None)
    return user


# -------------------------------------------------------------------------
# POST /leagues/sync
# -------------------------------------------------------------------------


class TestSyncSleeper:
    @patch("routes.leagues.db_service")
    @patch("routes.leagues.sleeper_service")
    def test_sync_success(self, mock_svc, mock_db_svc, authed_client):
        mock_svc.get_user = AsyncMock(return_value=_make_sleeper_user())
        mock_svc.get_league = AsyncMock(return_value=_make_sleeper_league())
        mock_svc.get_user_roster = AsyncMock(return_value=_make_sleeper_roster())
        mock_svc.get_players_by_ids = AsyncMock(
            return_value=[
                _make_sleeper_player("p1", full_name="Patrick Mahomes", position="QB"),
                _make_sleeper_player("p2", full_name="Travis Kelce", position="TE"),
            ]
        )

        mock_db, mock_session = _mock_db_session(_make_mock_user())
        mock_db_svc.session = mock_db.session

        response = authed_client.post(
            "/leagues/sync",
            json={"username": "goblinmaster", "league_id": "lg_456"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sleeper_username"] == "goblinmaster"
        assert data["sleeper_user_id"] == "sl_123"
        assert data["sleeper_league_id"] == "lg_456"
        assert data["roster_player_count"] == 2
        assert data["synced_at"]
        mock_session.commit.assert_called_once()

    @patch("routes.leagues.db_service")
    @patch("routes.leagues.sleeper_service")
    def test_sync_user_not_found(self, mock_svc, mock_db_svc, authed_client):
        mock_svc.get_user = AsyncMock(return_value=None)

        response = authed_client.post(
            "/leagues/sync",
            json={"username": "nobody", "league_id": "lg_456"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @patch("routes.leagues.db_service")
    @patch("routes.leagues.sleeper_service")
    def test_sync_league_not_found(self, mock_svc, mock_db_svc, authed_client):
        mock_svc.get_user = AsyncMock(return_value=_make_sleeper_user())
        mock_svc.get_league = AsyncMock(return_value=None)

        response = authed_client.post(
            "/leagues/sync",
            json={"username": "goblinmaster", "league_id": "nonexistent"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @patch("routes.leagues.db_service")
    @patch("routes.leagues.sleeper_service")
    def test_sync_no_roster(self, mock_svc, mock_db_svc, authed_client):
        """Sync succeeds even when user has no roster (empty snapshot)."""
        mock_svc.get_user = AsyncMock(return_value=_make_sleeper_user())
        mock_svc.get_league = AsyncMock(return_value=_make_sleeper_league())
        mock_svc.get_user_roster = AsyncMock(return_value=None)

        mock_db, _ = _mock_db_session(_make_mock_user())
        mock_db_svc.session = mock_db.session

        response = authed_client.post(
            "/leagues/sync",
            json={"username": "goblinmaster", "league_id": "lg_456"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["roster_player_count"] == 0

    def test_sync_unauthenticated(self, test_client):
        response = test_client.post(
            "/leagues/sync",
            json={"username": "goblinmaster", "league_id": "lg_456"},
        )
        assert response.status_code == 401


# -------------------------------------------------------------------------
# GET /leagues/me
# -------------------------------------------------------------------------


class TestGetMyLeague:
    @patch("routes.leagues.db_service")
    def test_connected_user(self, mock_db_svc, authed_client):
        synced = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        mock_user = _make_mock_user(
            sleeper_username="goblinmaster",
            sleeper_user_id="sl_123",
            sleeper_league_id="lg_456",
            roster_snapshot=[{"player_id": "p1"}, {"player_id": "p2"}],
            sleeper_synced_at=synced,
        )
        mock_db, _ = _mock_db_session(mock_user)
        mock_db_svc.session = mock_db.session

        response = authed_client.get("/leagues/me")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["sleeper_username"] == "goblinmaster"
        assert data["sleeper_league_id"] == "lg_456"
        assert data["sleeper_user_id"] == "sl_123"
        assert data["roster_player_count"] == 2
        assert data["synced_at"] is not None

    @patch("routes.leagues.db_service")
    def test_no_connection(self, mock_db_svc, authed_client):
        mock_db, _ = _mock_db_session(_make_mock_user())
        mock_db_svc.session = mock_db.session

        response = authed_client.get("/leagues/me")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False
        assert data["sleeper_username"] is None
        assert data["roster_player_count"] == 0

    def test_unauthenticated(self, test_client):
        response = test_client.get("/leagues/me")
        assert response.status_code == 401


# -------------------------------------------------------------------------
# DELETE /leagues/me
# -------------------------------------------------------------------------


class TestDisconnectLeague:
    @patch("routes.leagues.db_service")
    def test_disconnect_success(self, mock_db_svc, authed_client):
        mock_user = _make_mock_user(
            sleeper_username="goblinmaster",
            sleeper_league_id="lg_456",
        )
        mock_db, mock_session = _mock_db_session(mock_user)
        mock_db_svc.session = mock_db.session

        response = authed_client.delete("/leagues/me")

        assert response.status_code == 200
        assert response.json() == {"disconnected": True}
        assert mock_user.sleeper_username is None
        assert mock_user.sleeper_league_id is None
        assert mock_user.sleeper_user_id is None
        assert mock_user.roster_snapshot is None
        assert mock_user.sleeper_synced_at is None
        mock_session.commit.assert_called_once()

    def test_disconnect_unauthenticated(self, test_client):
        response = test_client.delete("/leagues/me")
        assert response.status_code == 401
