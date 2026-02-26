"""Tests for authentication API routes."""

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from routes.auth import (
    _get_client_ip,
    _queries_limit_for_tier,
    get_current_user,
    get_current_user_token,
    get_optional_user,
    require_admin_key,
)
from services.auth import ConfigurationError, InvalidTokenError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_USER = {
    "user_id": 1,
    "email": "test@example.com",
    "name": "Test User",
    "tier": "pro",
    "exp": 9999999999,
}


def _make_mock_user(**overrides):
    """Create a mock User ORM object."""
    user = MagicMock()
    user.id = overrides.get("id", 1)
    user.email = overrides.get("email", "test@example.com")
    user.name = overrides.get("name", "Test User")
    user.picture_url = overrides.get("picture_url", "https://photo.url/pic.jpg")
    user.subscription_tier = overrides.get("subscription_tier", "free")
    user.queries_today = overrides.get("queries_today", 0)
    user.created_at = overrides.get("created_at", datetime.now(UTC))
    return user


def _mock_db_session(mock_session=None):
    """Create a mock db_service.session() async context manager."""
    if mock_session is None:
        mock_session = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_session


@pytest.fixture
def authed_client(test_client):
    """Test client with auth bypassed."""
    from api.main import app

    app.dependency_overrides[get_current_user] = lambda: VALID_USER
    yield test_client
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestQueriesLimitForTier:
    def test_pro_tier(self):
        assert _queries_limit_for_tier("pro") == -1

    def test_free_tier(self):
        assert _queries_limit_for_tier("free") == 5

    def test_unknown_tier(self):
        assert _queries_limit_for_tier("basic") == 5


class TestGetClientIp:
    def test_x_forwarded_for_single(self):
        request = MagicMock()
        request.headers.get.return_value = "1.2.3.4"
        assert _get_client_ip(request) == "1.2.3.4"

    def test_x_forwarded_for_chain(self):
        request = MagicMock()
        request.headers.get.return_value = "1.2.3.4, 5.6.7.8"
        assert _get_client_ip(request) == "1.2.3.4"

    def test_falls_back_to_client_host(self):
        request = MagicMock()
        request.headers.get.return_value = None
        request.client.host = "10.0.0.1"
        assert _get_client_ip(request) == "10.0.0.1"

    def test_no_client_returns_unknown(self):
        request = MagicMock()
        request.headers.get.return_value = None
        request.client = None
        assert _get_client_ip(request) == "unknown"


# ---------------------------------------------------------------------------
# get_current_user_token dependency
# ---------------------------------------------------------------------------


class TestGetCurrentUserToken:
    async def test_no_authorization_header(self):
        with pytest.raises(Exception) as exc_info:
            await get_current_user_token(authorization=None)
        assert exc_info.value.status_code == 401
        assert "Authorization header required" in exc_info.value.detail

    async def test_invalid_format_no_bearer(self):
        with pytest.raises(Exception) as exc_info:
            await get_current_user_token(authorization="Token abc123")
        assert exc_info.value.status_code == 401
        assert "Invalid authorization header format" in exc_info.value.detail

    async def test_invalid_format_too_many_parts(self):
        with pytest.raises(Exception) as exc_info:
            await get_current_user_token(authorization="Bearer token extra")
        assert exc_info.value.status_code == 401

    async def test_valid_bearer_token(self):
        result = await get_current_user_token(authorization="Bearer my_jwt_token")
        assert result == "my_jwt_token"


# ---------------------------------------------------------------------------
# get_optional_user dependency
# ---------------------------------------------------------------------------


class TestGetOptionalUser:
    async def test_no_header_returns_none(self):
        result = await get_optional_user(authorization=None)
        assert result is None

    async def test_invalid_format(self):
        with pytest.raises(Exception) as exc_info:
            await get_optional_user(authorization="Basic abc123")
        assert exc_info.value.status_code == 401

    @patch("routes.auth.is_token_blacklisted", new_callable=AsyncMock)
    async def test_blacklisted_token(self, mock_blacklisted):
        mock_blacklisted.return_value = True
        with pytest.raises(Exception) as exc_info:
            await get_optional_user(authorization="Bearer revoked_token")
        assert exc_info.value.status_code == 401
        assert "revoked" in exc_info.value.detail

    @patch("routes.auth.verify_jwt_token")
    @patch("routes.auth.is_token_blacklisted", new_callable=AsyncMock)
    async def test_valid_token(self, mock_blacklisted, mock_verify):
        mock_blacklisted.return_value = False
        mock_verify.return_value = VALID_USER
        result = await get_optional_user(authorization="Bearer valid_token")
        assert result == VALID_USER

    @patch(
        "routes.auth.verify_jwt_token",
        side_effect=ConfigurationError("JWT not configured"),
    )
    @patch("routes.auth.is_token_blacklisted", new_callable=AsyncMock)
    async def test_config_error(self, mock_blacklisted, mock_verify):
        mock_blacklisted.return_value = False
        with pytest.raises(Exception) as exc_info:
            await get_optional_user(authorization="Bearer token")
        assert exc_info.value.status_code == 503

    @patch(
        "routes.auth.verify_jwt_token", side_effect=InvalidTokenError("Token expired")
    )
    @patch("routes.auth.is_token_blacklisted", new_callable=AsyncMock)
    async def test_invalid_token(self, mock_blacklisted, mock_verify):
        mock_blacklisted.return_value = False
        with pytest.raises(Exception) as exc_info:
            await get_optional_user(authorization="Bearer expired_token")
        assert exc_info.value.status_code == 401
        assert "Token expired" in exc_info.value.detail


# ---------------------------------------------------------------------------
# require_admin_key dependency
# ---------------------------------------------------------------------------


class TestRequireAdminKey:
    async def test_admin_key_not_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            # Ensure ADMIN_API_KEY is not set
            with patch("os.getenv", return_value=None):
                with pytest.raises(Exception) as exc_info:
                    await require_admin_key(x_admin_key="anything")
                assert exc_info.value.status_code == 503

    async def test_missing_key(self):
        with patch("os.getenv", return_value="real-admin-key"):
            with pytest.raises(Exception) as exc_info:
                await require_admin_key(x_admin_key=None)
            assert exc_info.value.status_code == 403

    async def test_wrong_key(self):
        with patch("os.getenv", return_value="real-admin-key"):
            with pytest.raises(Exception) as exc_info:
                await require_admin_key(x_admin_key="wrong-key")
            assert exc_info.value.status_code == 403

    async def test_valid_key(self):
        with patch("os.getenv", return_value="real-admin-key"):
            # Should not raise
            await require_admin_key(x_admin_key="real-admin-key")


# ---------------------------------------------------------------------------
# get_current_user dependency
# ---------------------------------------------------------------------------


class TestGetCurrentUser:
    @patch("routes.auth.verify_jwt_token")
    @patch("routes.auth.is_token_blacklisted", new_callable=AsyncMock)
    async def test_valid_token(self, mock_blacklisted, mock_verify):
        mock_blacklisted.return_value = False
        mock_verify.return_value = VALID_USER
        result = await get_current_user(token="valid_jwt")
        assert result == VALID_USER

    @patch("routes.auth.is_token_blacklisted", new_callable=AsyncMock)
    async def test_blacklisted_token(self, mock_blacklisted):
        mock_blacklisted.return_value = True
        with pytest.raises(Exception) as exc_info:
            await get_current_user(token="revoked_jwt")
        assert exc_info.value.status_code == 401

    @patch(
        "routes.auth.verify_jwt_token", side_effect=ConfigurationError("not configured")
    )
    @patch("routes.auth.is_token_blacklisted", new_callable=AsyncMock)
    async def test_config_error(self, mock_blacklisted, mock_verify):
        mock_blacklisted.return_value = False
        with pytest.raises(Exception) as exc_info:
            await get_current_user(token="some_jwt")
        assert exc_info.value.status_code == 503

    @patch("routes.auth.verify_jwt_token", side_effect=InvalidTokenError("expired"))
    @patch("routes.auth.is_token_blacklisted", new_callable=AsyncMock)
    async def test_invalid_token(self, mock_blacklisted, mock_verify):
        mock_blacklisted.return_value = False
        with pytest.raises(Exception) as exc_info:
            await get_current_user(token="bad_jwt")
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# GET /auth/status
# ---------------------------------------------------------------------------


class TestAuthStatusRoute:
    @patch("routes.auth.is_configured")
    def test_fully_configured(self, mock_configured, test_client):
        mock_configured.return_value = {
            "google_oauth": True,
            "jwt": True,
            "fully_configured": True,
        }
        response = test_client.get("/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["google_oauth_configured"] is True
        assert data["jwt_configured"] is True
        assert data["fully_configured"] is True

    @patch("routes.auth.is_configured")
    def test_not_configured(self, mock_configured, test_client):
        mock_configured.return_value = {
            "google_oauth": False,
            "jwt": False,
            "fully_configured": False,
        }
        response = test_client.get("/auth/status")
        data = response.json()
        assert data["fully_configured"] is False


# ---------------------------------------------------------------------------
# POST /auth/google
# ---------------------------------------------------------------------------


class TestGoogleAuth:
    @patch("routes.auth.db_service")
    def test_db_not_configured(self, mock_db, test_client):
        mock_db.is_configured = False

        with patch("services.rate_limiter.rate_limiter") as mock_rl:
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            response = test_client.post("/auth/google", json={"id_token": "tok"})

        assert response.status_code == 503

    @patch("routes.auth.create_jwt_token")
    @patch("routes.auth.get_or_create_user", new_callable=AsyncMock)
    @patch("routes.auth.verify_google_token")
    @patch("routes.auth.db_service")
    def test_success(
        self, mock_db, mock_google_verify, mock_get_user, mock_create_jwt, test_client
    ):
        mock_google_verify.return_value = {
            "google_id": "g123",
            "email": "user@gmail.com",
            "name": "User",
            "picture_url": None,
            "email_verified": True,
        }

        mock_user = _make_mock_user()
        mock_get_user.return_value = mock_user

        mock_db_ctx, mock_session = _mock_db_session(AsyncMock())
        mock_db.is_configured = True
        mock_db.session.return_value = mock_db_ctx

        mock_create_jwt.return_value = "jwt_token_123"

        # Patch the rate limiter lazy import
        with patch("services.rate_limiter.rate_limiter") as mock_rl:
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            response = test_client.post(
                "/auth/google", json={"id_token": "valid_google_token"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "jwt_token_123"
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == "test@example.com"

    @patch(
        "routes.auth.verify_google_token",
        side_effect=ConfigurationError("not configured"),
    )
    @patch("routes.auth.db_service")
    def test_google_not_configured(self, mock_db, mock_verify, test_client):
        mock_db.is_configured = True

        with patch("services.rate_limiter.rate_limiter") as mock_rl:
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            response = test_client.post("/auth/google", json={"id_token": "tok"})

        assert response.status_code == 503

    @patch(
        "routes.auth.verify_google_token", side_effect=InvalidTokenError("bad token")
    )
    @patch("routes.auth.db_service")
    def test_invalid_google_token(self, mock_db, mock_verify, test_client):
        mock_db.is_configured = True

        with patch("services.rate_limiter.rate_limiter") as mock_rl:
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            response = test_client.post("/auth/google", json={"id_token": "bad_tok"})

        assert response.status_code == 401

    @patch("routes.auth.verify_google_token")
    @patch("routes.auth.db_service")
    def test_email_not_verified(self, mock_db, mock_verify, test_client):
        mock_db.is_configured = True
        mock_verify.return_value = {
            "google_id": "g123",
            "email": "user@gmail.com",
            "name": "User",
            "email_verified": False,
        }

        with patch("services.rate_limiter.rate_limiter") as mock_rl:
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            response = test_client.post("/auth/google", json={"id_token": "tok"})

        assert response.status_code == 401
        assert "not verified" in response.json()["detail"]

    @patch("routes.auth.db_service")
    def test_rate_limited(self, mock_db, test_client):
        mock_db.is_configured = True

        with patch("services.rate_limiter.rate_limiter") as mock_rl:
            mock_rl.check_rate_limit = AsyncMock(return_value=(False, 30))
            response = test_client.post("/auth/google", json={"id_token": "tok"})

        assert response.status_code == 429
        assert "Retry-After" in response.headers


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------


class TestGetMe:
    @patch("routes.auth.get_user_by_id", new_callable=AsyncMock)
    @patch("routes.auth.db_service")
    def test_success(self, mock_db, mock_get_user, authed_client):
        mock_db_ctx, _ = _mock_db_session()
        mock_db.is_configured = True
        mock_db.session.return_value = mock_db_ctx

        mock_user = _make_mock_user(subscription_tier="pro")
        mock_get_user.return_value = mock_user

        response = authed_client.get(
            "/auth/me",
            headers={"Authorization": "Bearer fake_jwt"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["queries_limit"] == -1  # pro tier

    @patch("routes.auth.get_user_by_id", new_callable=AsyncMock)
    @patch("routes.auth.db_service")
    def test_user_not_found(self, mock_db, mock_get_user, authed_client):
        mock_db_ctx, _ = _mock_db_session()
        mock_db.is_configured = True
        mock_db.session.return_value = mock_db_ctx

        mock_get_user.return_value = None

        response = authed_client.get(
            "/auth/me",
            headers={"Authorization": "Bearer fake_jwt"},
        )

        assert response.status_code == 404

    def test_db_not_configured(self, authed_client):
        with patch("routes.auth.db_service") as mock_db:
            mock_db.is_configured = False
            response = authed_client.get(
                "/auth/me",
                headers={"Authorization": "Bearer fake_jwt"},
            )
            assert response.status_code == 503


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------


class TestLogout:
    def test_success(self, test_client):
        from api.main import app

        app.dependency_overrides[get_current_user] = lambda: VALID_USER
        app.dependency_overrides[get_current_user_token] = lambda: "jwt_to_revoke"

        with patch("routes.auth.blacklist_token", new_callable=AsyncMock) as mock_bl:
            response = test_client.post(
                "/auth/logout",
                headers={"Authorization": "Bearer jwt_to_revoke"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "logged_out"
            mock_bl.assert_called_once_with("jwt_to_revoke")

        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_token, None)


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------


class TestRefreshToken:
    @patch("routes.auth.blacklist_token", new_callable=AsyncMock)
    @patch("routes.auth.create_jwt_token")
    @patch("routes.auth.get_user_by_id", new_callable=AsyncMock)
    @patch("routes.auth.db_service")
    def test_success(
        self, mock_db, mock_get_user, mock_create_jwt, mock_bl, test_client
    ):
        from api.main import app

        app.dependency_overrides[get_current_user] = lambda: VALID_USER
        app.dependency_overrides[get_current_user_token] = lambda: "old_jwt"

        mock_db_ctx, _ = _mock_db_session()
        mock_db.is_configured = True
        mock_db.session.return_value = mock_db_ctx

        mock_user = _make_mock_user()
        mock_get_user.return_value = mock_user
        mock_create_jwt.return_value = "new_jwt_token"

        with patch("services.rate_limiter.rate_limiter") as mock_rl:
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            response = test_client.post(
                "/auth/refresh",
                headers={"Authorization": "Bearer old_jwt"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "new_jwt_token"
        mock_bl.assert_called_once_with("old_jwt")

        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_token, None)

    @patch("routes.auth.get_user_by_id", new_callable=AsyncMock)
    @patch("routes.auth.db_service")
    def test_user_not_found(self, mock_db, mock_get_user, test_client):
        from api.main import app

        app.dependency_overrides[get_current_user] = lambda: VALID_USER
        app.dependency_overrides[get_current_user_token] = lambda: "jwt"

        mock_db_ctx, _ = _mock_db_session()
        mock_db.is_configured = True
        mock_db.session.return_value = mock_db_ctx

        mock_get_user.return_value = None

        with patch("services.rate_limiter.rate_limiter") as mock_rl:
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            response = test_client.post(
                "/auth/refresh",
                headers={"Authorization": "Bearer jwt"},
            )

        assert response.status_code == 404

        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_token, None)

    def test_db_not_configured(self, test_client):
        from api.main import app

        app.dependency_overrides[get_current_user] = lambda: VALID_USER
        app.dependency_overrides[get_current_user_token] = lambda: "jwt"

        with patch("routes.auth.db_service") as mock_db:
            mock_db.is_configured = False
            with patch("services.rate_limiter.rate_limiter") as mock_rl:
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                response = test_client.post(
                    "/auth/refresh",
                    headers={"Authorization": "Bearer jwt"},
                )

        assert response.status_code == 503

        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_token, None)

    def test_rate_limited(self, test_client):
        from api.main import app

        app.dependency_overrides[get_current_user] = lambda: VALID_USER
        app.dependency_overrides[get_current_user_token] = lambda: "jwt"

        with patch("services.rate_limiter.rate_limiter") as mock_rl:
            mock_rl.check_rate_limit = AsyncMock(return_value=(False, 60))
            response = test_client.post(
                "/auth/refresh",
                headers={"Authorization": "Bearer jwt"},
            )

        assert response.status_code == 429

        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_token, None)

    @patch(
        "routes.auth.create_jwt_token", side_effect=ConfigurationError("not configured")
    )
    @patch("routes.auth.get_user_by_id", new_callable=AsyncMock)
    @patch("routes.auth.db_service")
    def test_jwt_config_error(
        self, mock_db, mock_get_user, mock_create_jwt, test_client
    ):
        from api.main import app

        app.dependency_overrides[get_current_user] = lambda: VALID_USER
        app.dependency_overrides[get_current_user_token] = lambda: "jwt"

        mock_db_ctx, _ = _mock_db_session()
        mock_db.is_configured = True
        mock_db.session.return_value = mock_db_ctx

        mock_get_user.return_value = _make_mock_user()

        with patch("services.rate_limiter.rate_limiter") as mock_rl:
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            response = test_client.post(
                "/auth/refresh",
                headers={"Authorization": "Bearer jwt"},
            )

        assert response.status_code == 503

        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_token, None)
