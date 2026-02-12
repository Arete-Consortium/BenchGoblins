"""Tests for credential migration: ESPN/Yahoo endpoints use encrypted DB storage."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_session_obj():
    """Create a mock Session ORM object."""
    s = MagicMock()
    s.id = uuid4()
    s.session_token = "default"
    s.platform = "web"
    return s


@asynccontextmanager
async def _fake_db_session():
    """Async context manager mimicking db_service.session()."""
    db = AsyncMock()
    db.commit = AsyncMock()
    yield db


# ---------------------------------------------------------------------------
# _resolve_session tests
# ---------------------------------------------------------------------------


class TestResolveSession:
    """Tests for the _resolve_session async context manager."""

    def test_db_not_configured_returns_503(self, test_client):
        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = False
            response = test_client.get("/integrations/espn/status?session_id=test")
        # Status endpoint catches the 503 and returns connected=False
        assert response.status_code == 200
        assert response.json()["connected"] is False

    def test_unknown_token_returns_401(self, test_client):
        session_obj = None  # Not found

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.session_service") as mock_ss,
        ):
            mock_db.is_configured = True
            mock_db.session = _fake_db_session
            mock_ss.get_session_by_token = AsyncMock(return_value=session_obj)

            response = test_client.get(
                "/integrations/espn/leagues?session_id=unknown-token"
            )

        assert response.status_code == 401
        assert "Invalid session" in response.json()["detail"]

    def test_default_session_auto_created(self, test_client):
        session_obj = _fake_session_obj()

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.session_service") as mock_ss,
        ):
            mock_db.is_configured = True
            mock_db.session = _fake_db_session
            # First call returns None (not found), triggers auto-create
            mock_ss.get_session_by_token = AsyncMock(return_value=None)
            mock_ss.create_session = AsyncMock(return_value=session_obj)
            mock_ss.get_credential = AsyncMock(return_value=None)

            response = test_client.get("/integrations/espn/status?session_id=default")

        assert response.status_code == 200
        mock_ss.create_session.assert_called_once()

    def test_known_token_resolved(self, test_client):
        session_obj = _fake_session_obj()

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.session_service") as mock_ss,
        ):
            mock_db.is_configured = True
            mock_db.session = _fake_db_session
            mock_ss.get_session_by_token = AsyncMock(return_value=session_obj)
            mock_ss.get_credential = AsyncMock(return_value=None)

            response = test_client.get(
                "/integrations/espn/status?session_id=known-token"
            )

        assert response.status_code == 200
        mock_ss.get_session_by_token.assert_called_once()


# ---------------------------------------------------------------------------
# ESPN endpoint tests
# ---------------------------------------------------------------------------


class TestESPNConnect:
    def test_stores_credentials_in_db(self, test_client):
        session_obj = _fake_session_obj()

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.session_service") as mock_ss,
            patch("api.main.espn_fantasy_service") as mock_espn,
        ):
            mock_db.is_configured = True
            mock_db.session = _fake_db_session
            mock_ss.get_session_by_token = AsyncMock(return_value=session_obj)
            mock_ss.store_credential = AsyncMock()
            mock_espn.verify_credentials = AsyncMock(return_value=True)
            mock_espn.get_user_id = AsyncMock(return_value="user123")
            mock_espn.get_user_leagues = AsyncMock(return_value=[])

            response = test_client.post(
                "/integrations/espn/connect?session_id=default",
                json={"swid": "{ABC}", "espn_s2": "s2token"},
            )

        assert response.status_code == 200
        assert response.json()["connected"] is True
        mock_ss.store_credential.assert_called_once()
        call_args = mock_ss.store_credential.call_args
        assert call_args[0][2] == "espn"
        assert call_args[0][3] == {"swid": "{ABC}", "espn_s2": "s2token"}

    def test_invalid_credentials_rejected(self, test_client):
        with patch("api.main.espn_fantasy_service") as mock_espn:
            mock_espn.verify_credentials = AsyncMock(return_value=False)

            response = test_client.post(
                "/integrations/espn/connect",
                json={"swid": "{BAD}", "espn_s2": "bad"},
            )

        assert response.status_code == 401


class TestESPNLeagues:
    def test_retrieves_from_db(self, test_client):
        session_obj = _fake_session_obj()

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.session_service") as mock_ss,
            patch("api.main.espn_fantasy_service") as mock_espn,
        ):
            mock_db.is_configured = True
            mock_db.session = _fake_db_session
            mock_ss.get_session_by_token = AsyncMock(return_value=session_obj)
            mock_ss.get_credential = AsyncMock(
                return_value={"swid": "{ABC}", "espn_s2": "s2token"}
            )
            mock_espn.get_user_leagues = AsyncMock(return_value=[])

            response = test_client.get("/integrations/espn/leagues")

        assert response.status_code == 200
        mock_ss.get_credential.assert_called_once()

    def test_not_connected_returns_401(self, test_client):
        session_obj = _fake_session_obj()

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.session_service") as mock_ss,
        ):
            mock_db.is_configured = True
            mock_db.session = _fake_db_session
            mock_ss.get_session_by_token = AsyncMock(return_value=session_obj)
            mock_ss.get_credential = AsyncMock(return_value=None)

            response = test_client.get("/integrations/espn/leagues")

        assert response.status_code == 401


class TestESPNRoster:
    def test_retrieves_from_db(self, test_client):
        from services.espn_fantasy import RosterPlayer

        session_obj = _fake_session_obj()
        mock_player = RosterPlayer(
            player_id="p1",
            espn_id="e1",
            name="Test Player",
            position="PG",
            team="LAL",
            lineup_slot="PG",
            acquisition_type="DRAFT",
            projected_points=20.0,
        )

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.session_service") as mock_ss,
            patch("api.main.espn_fantasy_service") as mock_espn,
        ):
            mock_db.is_configured = True
            mock_db.session = _fake_db_session
            mock_ss.get_session_by_token = AsyncMock(return_value=session_obj)
            mock_ss.get_credential = AsyncMock(
                return_value={"swid": "{ABC}", "espn_s2": "s2token"}
            )
            mock_espn.get_roster = AsyncMock(return_value=[mock_player])

            response = test_client.get(
                "/integrations/espn/leagues/123/roster?sport=nba&team_id=1"
            )

        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_not_connected_returns_401(self, test_client):
        session_obj = _fake_session_obj()

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.session_service") as mock_ss,
        ):
            mock_db.is_configured = True
            mock_db.session = _fake_db_session
            mock_ss.get_session_by_token = AsyncMock(return_value=session_obj)
            mock_ss.get_credential = AsyncMock(return_value=None)

            response = test_client.get(
                "/integrations/espn/leagues/123/roster?sport=nba&team_id=1"
            )

        assert response.status_code == 401


class TestESPNDisconnect:
    def test_deletes_from_db(self, test_client):
        session_obj = _fake_session_obj()

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.session_service") as mock_ss,
        ):
            mock_db.is_configured = True
            mock_db.session = _fake_db_session
            mock_ss.get_session_by_token = AsyncMock(return_value=session_obj)
            mock_ss.delete_credential = AsyncMock(return_value=True)

            response = test_client.delete("/integrations/espn/disconnect")

        assert response.status_code == 200
        assert response.json()["status"] == "disconnected"
        mock_ss.delete_credential.assert_called_once()

    def test_idempotent_when_db_unavailable(self, test_client):
        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = False

            response = test_client.delete("/integrations/espn/disconnect")

        assert response.status_code == 200
        assert response.json()["status"] == "disconnected"


class TestESPNStatus:
    def test_connected(self, test_client):
        session_obj = _fake_session_obj()

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.session_service") as mock_ss,
            patch("api.main.espn_fantasy_service") as mock_espn,
        ):
            mock_db.is_configured = True
            mock_db.session = _fake_db_session
            mock_ss.get_session_by_token = AsyncMock(return_value=session_obj)
            mock_ss.get_credential = AsyncMock(
                return_value={"swid": "{ABC}", "espn_s2": "s2token"}
            )
            mock_espn.get_user_id = AsyncMock(return_value="user123")

            response = test_client.get("/integrations/espn/status")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["user_id"] == "user123"

    def test_not_connected(self, test_client):
        session_obj = _fake_session_obj()

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.session_service") as mock_ss,
        ):
            mock_db.is_configured = True
            mock_db.session = _fake_db_session
            mock_ss.get_session_by_token = AsyncMock(return_value=session_obj)
            mock_ss.get_credential = AsyncMock(return_value=None)

            response = test_client.get("/integrations/espn/status")

        assert response.status_code == 200
        assert response.json()["connected"] is False

    def test_graceful_when_db_unavailable(self, test_client):
        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = False

            response = test_client.get("/integrations/espn/status")

        assert response.status_code == 200
        assert response.json()["connected"] is False


# ---------------------------------------------------------------------------
# Yahoo endpoint tests
# ---------------------------------------------------------------------------


class TestYahooAuth:
    def test_stores_state_in_memory(self, test_client):
        with patch("api.main.yahoo_service") as mock_yahoo:
            mock_yahoo.get_auth_url.return_value = "https://yahoo.com/auth?state=abc"

            response = test_client.get(
                "/integrations/yahoo/auth?redirect_uri=http://localhost/callback"
            )

        assert response.status_code == 200
        data = response.json()
        assert "auth_url" in data
        assert "state" in data


class TestYahooToken:
    def test_stores_tokens_in_db(self, test_client):
        session_obj = _fake_session_obj()
        mock_tokens = MagicMock(
            access_token="at123",
            refresh_token="rt456",
            expires_at=9999999999,
            expires_in=3600,
        )

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.session_service") as mock_ss,
            patch("api.main.yahoo_service") as mock_yahoo,
        ):
            mock_db.is_configured = True
            mock_db.session = _fake_db_session
            mock_ss.get_session_by_token = AsyncMock(return_value=session_obj)
            mock_ss.store_credential = AsyncMock()
            mock_yahoo.exchange_code = AsyncMock(return_value=mock_tokens)

            response = test_client.post(
                "/integrations/yahoo/token",
                json={
                    "code": "auth_code",
                    "redirect_uri": "http://localhost/callback",
                },
            )

        assert response.status_code == 200
        mock_ss.store_credential.assert_called_once()
        call_args = mock_ss.store_credential.call_args
        assert call_args[0][2] == "yahoo"
        assert call_args[0][3]["access_token"] == "at123"

    def test_invalid_state_rejected(self, test_client):
        import api.main as main_mod

        main_mod._yahoo_oauth_states["default_state"] = "correct_state"

        try:
            response = test_client.post(
                "/integrations/yahoo/token",
                json={
                    "code": "auth_code",
                    "redirect_uri": "http://localhost/callback",
                    "state": "wrong_state",
                },
            )
            assert response.status_code == 400
        finally:
            main_mod._yahoo_oauth_states.pop("default_state", None)


class TestYahooRefresh:
    def test_updates_tokens_in_db(self, test_client):
        session_obj = _fake_session_obj()
        mock_tokens = MagicMock(
            access_token="new_at",
            refresh_token="new_rt",
            expires_at=9999999999,
            expires_in=3600,
        )

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.session_service") as mock_ss,
            patch("api.main.yahoo_service") as mock_yahoo,
        ):
            mock_db.is_configured = True
            mock_db.session = _fake_db_session
            mock_ss.get_session_by_token = AsyncMock(return_value=session_obj)
            mock_ss.get_credential = AsyncMock(
                return_value={
                    "access_token": "old_at",
                    "refresh_token": "old_rt",
                    "expires_at": 0,
                }
            )
            mock_ss.store_credential = AsyncMock()
            mock_yahoo.refresh_token = AsyncMock(return_value=mock_tokens)

            response = test_client.post("/integrations/yahoo/refresh")

        assert response.status_code == 200
        assert response.json()["access_token"] == "new_at"
        mock_ss.store_credential.assert_called_once()

    def test_no_token_returns_401(self, test_client):
        session_obj = _fake_session_obj()

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.session_service") as mock_ss,
        ):
            mock_db.is_configured = True
            mock_db.session = _fake_db_session
            mock_ss.get_session_by_token = AsyncMock(return_value=session_obj)
            mock_ss.get_credential = AsyncMock(return_value=None)

            response = test_client.post("/integrations/yahoo/refresh")

        assert response.status_code == 401


class TestGetYahooToken:
    """Tests for the _get_yahoo_token helper via downstream endpoints."""

    def test_auto_refresh_expired_token(self, test_client):
        session_obj = _fake_session_obj()
        mock_tokens = MagicMock(
            access_token="refreshed_at",
            refresh_token="refreshed_rt",
            expires_at=9999999999,
        )

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.session_service") as mock_ss,
            patch("api.main.yahoo_service") as mock_yahoo,
        ):
            mock_db.is_configured = True
            mock_db.session = _fake_db_session
            mock_ss.get_session_by_token = AsyncMock(return_value=session_obj)
            mock_ss.get_credential = AsyncMock(
                return_value={
                    "access_token": "expired_at",
                    "refresh_token": "rt",
                    "expires_at": 0,  # expired
                }
            )
            mock_ss.store_credential = AsyncMock()
            mock_yahoo.refresh_token = AsyncMock(return_value=mock_tokens)
            mock_yahoo.get_user_leagues = AsyncMock(return_value=[])

            response = test_client.get("/integrations/yahoo/leagues")

        assert response.status_code == 200
        # Token was refreshed and stored back
        mock_ss.store_credential.assert_called_once()

    def test_not_connected_returns_401(self, test_client):
        session_obj = _fake_session_obj()

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.session_service") as mock_ss,
        ):
            mock_db.is_configured = True
            mock_db.session = _fake_db_session
            mock_ss.get_session_by_token = AsyncMock(return_value=session_obj)
            mock_ss.get_credential = AsyncMock(return_value=None)

            response = test_client.get("/integrations/yahoo/leagues")

        assert response.status_code == 401


class TestYahooDisconnect:
    def test_deletes_from_db(self, test_client):
        session_obj = _fake_session_obj()

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.session_service") as mock_ss,
        ):
            mock_db.is_configured = True
            mock_db.session = _fake_db_session
            mock_ss.get_session_by_token = AsyncMock(return_value=session_obj)
            mock_ss.delete_credential = AsyncMock(return_value=True)

            response = test_client.delete("/integrations/yahoo/disconnect")

        assert response.status_code == 200
        assert response.json()["status"] == "disconnected"
        mock_ss.delete_credential.assert_called_once()

    def test_idempotent_when_db_unavailable(self, test_client):
        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = False

            response = test_client.delete("/integrations/yahoo/disconnect")

        assert response.status_code == 200
        assert response.json()["status"] == "disconnected"


class TestYahooStatus:
    def test_connected(self, test_client):
        session_obj = _fake_session_obj()

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.session_service") as mock_ss,
        ):
            mock_db.is_configured = True
            mock_db.session = _fake_db_session
            mock_ss.get_session_by_token = AsyncMock(return_value=session_obj)
            mock_ss.get_credential = AsyncMock(
                return_value={
                    "access_token": "at",
                    "refresh_token": "rt",
                    "expires_at": 9999999999,
                }
            )

            response = test_client.get("/integrations/yahoo/status")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["expired"] is False

    def test_not_connected(self, test_client):
        session_obj = _fake_session_obj()

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.session_service") as mock_ss,
        ):
            mock_db.is_configured = True
            mock_db.session = _fake_db_session
            mock_ss.get_session_by_token = AsyncMock(return_value=session_obj)
            mock_ss.get_credential = AsyncMock(return_value=None)

            response = test_client.get("/integrations/yahoo/status")

        assert response.status_code == 200
        assert response.json()["connected"] is False

    def test_graceful_when_db_unavailable(self, test_client):
        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = False

            response = test_client.get("/integrations/yahoo/status")

        assert response.status_code == 200
        assert response.json()["connected"] is False
