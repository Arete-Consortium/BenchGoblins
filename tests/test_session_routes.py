"""Tests for session management API routes."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_session(**overrides):
    """Create a mock Session ORM object."""
    session = MagicMock()
    session.id = overrides.get("id", "sess-abc-123")
    session.session_token = overrides.get("session_token", "tok_secret_123")
    session.platform = overrides.get("platform", "ios")
    session.device_id = overrides.get("device_id", "device-xyz")
    session.device_name = overrides.get("device_name", "iPhone 15")
    session.status = overrides.get("status", "active")
    now = datetime.now(UTC)
    session.created_at = overrides.get("created_at", now)
    session.expires_at = overrides.get("expires_at", now + timedelta(days=30))
    session.last_active_at = overrides.get("last_active_at", now)
    return session


def _mock_db_session():
    """Create a mock db_service.session() async context manager."""
    mock_session = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_session


# ---------------------------------------------------------------------------
# get_session_token dependency
# ---------------------------------------------------------------------------


class TestGetSessionToken:
    def test_missing_token_returns_401(self, test_client):
        response = test_client.get("/sessions/current")
        assert response.status_code == 401
        assert "Session token required" in response.json()["detail"]

    def test_token_from_header(self, test_client):
        """Verify X-Session-Token header is accepted (full route test below)."""
        # Just verifying 401 is not "token required" when header is provided
        # (will get 503 if db not configured or other error, not the 401 for missing token)
        with patch("routes.sessions.db_service") as mock_db:
            mock_db.is_configured = False
            response = test_client.get(
                "/sessions/current",
                headers={"X-Session-Token": "test_token"},
            )
            # Should get 503 (db not configured), not 401 (missing token)
            assert response.status_code == 503

    def test_token_from_query_param(self, test_client):
        with patch("routes.sessions.db_service") as mock_db:
            mock_db.is_configured = False
            response = test_client.get("/sessions/current?session_id=test_token")
            assert response.status_code == 503


# ---------------------------------------------------------------------------
# POST /sessions (create)
# ---------------------------------------------------------------------------


class TestCreateSession:
    def test_invalid_platform(self, test_client):
        response = test_client.post("/sessions", json={"platform": "windows"})
        assert response.status_code == 400
        assert "Invalid platform" in response.json()["detail"]

    def test_db_not_configured(self, test_client):
        with patch("routes.sessions.db_service") as mock_db:
            mock_db.is_configured = False
            response = test_client.post("/sessions", json={"platform": "ios"})
            assert response.status_code == 503

    @patch("routes.sessions.session_service")
    @patch("routes.sessions.db_service")
    def test_success(self, mock_db_svc, mock_session_svc, test_client):
        mock_ctx, _ = _mock_db_session()
        mock_db_svc.is_configured = True
        mock_db_svc.session.return_value = mock_ctx

        mock_sess = _make_mock_session()
        mock_session_svc.create_session = AsyncMock(return_value=mock_sess)

        response = test_client.post(
            "/sessions",
            json={"platform": "ios", "device_id": "dev-1", "device_name": "My iPhone"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == str(mock_sess.id)
        assert data["session_token"] == mock_sess.session_token
        assert data["platform"] == "ios"

    @patch("routes.sessions.session_service")
    @patch("routes.sessions.db_service")
    def test_creation_failure_returns_500(
        self, mock_db_svc, mock_session_svc, test_client
    ):
        mock_ctx, _ = _mock_db_session()
        mock_db_svc.is_configured = True
        mock_db_svc.session.return_value = mock_ctx

        mock_session_svc.create_session = AsyncMock(
            side_effect=RuntimeError("DB write failed")
        )

        response = test_client.post("/sessions", json={"platform": "web"})
        assert response.status_code == 500
        assert "Session creation failed" in response.json()["detail"]


# ---------------------------------------------------------------------------
# GET /sessions/current
# ---------------------------------------------------------------------------


class TestGetCurrentSession:
    @patch("routes.sessions.session_service")
    @patch("routes.sessions.db_service")
    def test_success(self, mock_db_svc, mock_session_svc, test_client):
        mock_ctx, _ = _mock_db_session()
        mock_db_svc.is_configured = True
        mock_db_svc.session.return_value = mock_ctx

        mock_sess = _make_mock_session()
        mock_session_svc.validate_session = AsyncMock(
            return_value=(True, mock_sess, None)
        )
        mock_session_svc.get_credential_status = AsyncMock(
            return_value={"espn": {"connected": True}}
        )

        response = test_client.get(
            "/sessions/current",
            headers={"X-Session-Token": "tok_valid"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == str(mock_sess.id)
        assert data["credentials"]["espn"]["connected"] is True

    @patch("routes.sessions.session_service")
    @patch("routes.sessions.db_service")
    def test_invalid_session_returns_401(
        self, mock_db_svc, mock_session_svc, test_client
    ):
        mock_ctx, _ = _mock_db_session()
        mock_db_svc.is_configured = True
        mock_db_svc.session.return_value = mock_ctx

        mock_session_svc.validate_session = AsyncMock(
            return_value=(False, None, "Session expired")
        )

        response = test_client.get(
            "/sessions/current",
            headers={"X-Session-Token": "tok_expired"},
        )

        assert response.status_code == 401
        assert "Session expired" in response.json()["detail"]


# ---------------------------------------------------------------------------
# POST /sessions/refresh
# ---------------------------------------------------------------------------


class TestRefreshSession:
    @patch("routes.sessions.session_service")
    @patch("routes.sessions.db_service")
    def test_success(self, mock_db_svc, mock_session_svc, test_client):
        mock_ctx, _ = _mock_db_session()
        mock_db_svc.is_configured = True
        mock_db_svc.session.return_value = mock_ctx

        mock_sess = _make_mock_session()
        mock_session_svc.validate_session = AsyncMock(
            return_value=(True, mock_sess, None)
        )
        mock_session_svc.refresh_session = AsyncMock(return_value=mock_sess)
        mock_session_svc.get_credential_status = AsyncMock(return_value={})

        response = test_client.post(
            "/sessions/refresh",
            headers={"X-Session-Token": "tok_valid"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == str(mock_sess.id)

    @patch("routes.sessions.session_service")
    @patch("routes.sessions.db_service")
    def test_invalid_session_returns_401(
        self, mock_db_svc, mock_session_svc, test_client
    ):
        mock_ctx, _ = _mock_db_session()
        mock_db_svc.is_configured = True
        mock_db_svc.session.return_value = mock_ctx

        mock_session_svc.validate_session = AsyncMock(
            return_value=(False, None, "Invalid session")
        )

        response = test_client.post(
            "/sessions/refresh",
            headers={"X-Session-Token": "tok_bad"},
        )

        assert response.status_code == 401

    def test_db_not_configured(self, test_client):
        with patch("routes.sessions.db_service") as mock_db:
            mock_db.is_configured = False
            response = test_client.post(
                "/sessions/refresh",
                headers={"X-Session-Token": "tok_any"},
            )
            assert response.status_code == 503


# ---------------------------------------------------------------------------
# DELETE /sessions/current
# ---------------------------------------------------------------------------


class TestRevokeSession:
    @patch("routes.sessions.session_service")
    @patch("routes.sessions.db_service")
    def test_success(self, mock_db_svc, mock_session_svc, test_client):
        mock_ctx, _ = _mock_db_session()
        mock_db_svc.is_configured = True
        mock_db_svc.session.return_value = mock_ctx

        mock_sess = _make_mock_session()
        mock_session_svc.get_session_by_token = AsyncMock(return_value=mock_sess)
        mock_session_svc.revoke_session = AsyncMock()

        response = test_client.delete(
            "/sessions/current",
            headers={"X-Session-Token": "tok_valid"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "revoked"
        assert data["session_id"] == str(mock_sess.id)

    @patch("routes.sessions.session_service")
    @patch("routes.sessions.db_service")
    def test_session_not_found(self, mock_db_svc, mock_session_svc, test_client):
        mock_ctx, _ = _mock_db_session()
        mock_db_svc.is_configured = True
        mock_db_svc.session.return_value = mock_ctx

        mock_session_svc.get_session_by_token = AsyncMock(return_value=None)

        response = test_client.delete(
            "/sessions/current",
            headers={"X-Session-Token": "tok_unknown"},
        )

        assert response.status_code == 404

    def test_db_not_configured(self, test_client):
        with patch("routes.sessions.db_service") as mock_db:
            mock_db.is_configured = False
            response = test_client.delete(
                "/sessions/current",
                headers={"X-Session-Token": "tok_any"},
            )
            assert response.status_code == 503


# ---------------------------------------------------------------------------
# GET /sessions/validate
# ---------------------------------------------------------------------------


class TestValidateSession:
    @patch("routes.sessions.session_service")
    @patch("routes.sessions.db_service")
    def test_valid_session(self, mock_db_svc, mock_session_svc, test_client):
        mock_ctx, _ = _mock_db_session()
        mock_db_svc.is_configured = True
        mock_db_svc.session.return_value = mock_ctx

        mock_sess = _make_mock_session()
        mock_session_svc.validate_session = AsyncMock(
            return_value=(True, mock_sess, None)
        )

        response = test_client.get(
            "/sessions/validate",
            headers={"X-Session-Token": "tok_valid"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["session_id"] == str(mock_sess.id)
        assert data["error"] is None

    @patch("routes.sessions.session_service")
    @patch("routes.sessions.db_service")
    def test_invalid_session(self, mock_db_svc, mock_session_svc, test_client):
        mock_ctx, _ = _mock_db_session()
        mock_db_svc.is_configured = True
        mock_db_svc.session.return_value = mock_ctx

        mock_session_svc.validate_session = AsyncMock(
            return_value=(False, None, "Token expired")
        )

        response = test_client.get(
            "/sessions/validate",
            headers={"X-Session-Token": "tok_expired"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert data["session_id"] is None
        assert data["error"] == "Token expired"

    def test_db_not_configured(self, test_client):
        with patch("routes.sessions.db_service") as mock_db:
            mock_db.is_configured = False
            response = test_client.get(
                "/sessions/validate",
                headers={"X-Session-Token": "tok_any"},
            )
            assert response.status_code == 503
