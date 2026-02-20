"""Tests for Google OAuth authentication service."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest

from services.auth import (
    ConfigurationError,
    InvalidTokenError,
    blacklist_token,
    clear_expired_blacklist_entries,
    create_jwt_token,
    get_or_create_user,
    get_user_by_email,
    get_user_by_id,
    is_token_blacklisted,
    set_blacklist_redis,
    verify_google_token,
    verify_jwt_token,
)
from services.auth import is_configured as auth_is_configured


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(**overrides):
    """Create a mock User with sensible defaults."""
    user = MagicMock()
    user.id = overrides.get("id", 1)
    user.google_id = overrides.get("google_id", "g123")
    user.email = overrides.get("email", "test@example.com")
    user.name = overrides.get("name", "Test User")
    user.picture_url = overrides.get("picture_url", "https://photo.url/pic.jpg")
    user.subscription_tier = overrides.get("subscription_tier", "free")
    user.queries_today = overrides.get("queries_today", 0)
    return user


# ---------------------------------------------------------------------------
# verify_google_token
# ---------------------------------------------------------------------------


class TestVerifyGoogleToken:
    def test_raises_when_not_configured(self):
        with patch("services.auth.GOOGLE_CLIENT_ID", ""):
            with pytest.raises(ConfigurationError, match="GOOGLE_CLIENT_ID"):
                verify_google_token("some_token")

    def test_valid_token(self):
        idinfo = {
            "iss": "accounts.google.com",
            "sub": "google_user_123",
            "email": "user@gmail.com",
            "name": "John Doe",
            "picture": "https://lh3.google.com/photo.jpg",
            "email_verified": True,
        }

        with (
            patch("services.auth.GOOGLE_CLIENT_ID", "client_id_123"),
            patch("services.auth.id_token.verify_oauth2_token", return_value=idinfo),
            patch("services.auth.google_requests.Request"),
        ):
            result = verify_google_token("valid_token")

            assert result["google_id"] == "google_user_123"
            assert result["email"] == "user@gmail.com"
            assert result["name"] == "John Doe"
            assert result["picture_url"] == "https://lh3.google.com/photo.jpg"
            assert result["email_verified"] is True

    def test_valid_token_https_issuer(self):
        idinfo = {
            "iss": "https://accounts.google.com",
            "sub": "g_user",
            "email": "u@g.com",
            "email_verified": True,
        }

        with (
            patch("services.auth.GOOGLE_CLIENT_ID", "client_id"),
            patch("services.auth.id_token.verify_oauth2_token", return_value=idinfo),
            patch("services.auth.google_requests.Request"),
        ):
            result = verify_google_token("token")
            assert result["google_id"] == "g_user"
            # Name falls back to email prefix when not provided
            assert result["name"] == "u"

    def test_invalid_issuer(self):
        idinfo = {
            "iss": "evil.example.com",
            "sub": "user",
            "email": "u@e.com",
        }

        with (
            patch("services.auth.GOOGLE_CLIENT_ID", "client_id"),
            patch("services.auth.id_token.verify_oauth2_token", return_value=idinfo),
            patch("services.auth.google_requests.Request"),
        ):
            with pytest.raises(InvalidTokenError, match="Invalid token issuer"):
                verify_google_token("token")

    def test_value_error_from_google_raises_invalid_token(self):
        with (
            patch("services.auth.GOOGLE_CLIENT_ID", "client_id"),
            patch(
                "services.auth.id_token.verify_oauth2_token",
                side_effect=ValueError("Token expired"),
            ),
            patch("services.auth.google_requests.Request"),
        ):
            with pytest.raises(InvalidTokenError, match="Invalid Google ID token"):
                verify_google_token("expired_token")


# ---------------------------------------------------------------------------
# get_or_create_user
# ---------------------------------------------------------------------------


class TestGetOrCreateUser:
    async def test_existing_user_updates_info(self):
        existing_user = _make_user(name="Old Name")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_user

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        # db.add is sync in SQLAlchemy
        mock_db.add = MagicMock()

        google_info = {
            "google_id": "g123",
            "email": "test@example.com",
            "name": "New Name",
            "picture_url": "https://new.pic/photo.jpg",
        }

        user = await get_or_create_user(google_info, mock_db)

        assert user.name == "New Name"
        assert user.picture_url == "https://new.pic/photo.jpg"
        assert user is existing_user

    async def test_new_user_created(self):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        mock_db.add = MagicMock()

        google_info = {
            "google_id": "g_new",
            "email": "new@example.com",
            "name": "New User",
            "picture_url": None,
        }

        user = await get_or_create_user(google_info, mock_db)

        mock_db.add.assert_called_once()
        added_user = mock_db.add.call_args[0][0]
        assert added_user.google_id == "g_new"
        assert added_user.email == "new@example.com"
        assert added_user.name == "New User"
        assert added_user.subscription_tier == "free"
        assert user is added_user


# ---------------------------------------------------------------------------
# get_user_by_id / get_user_by_email
# ---------------------------------------------------------------------------


class TestGetUserById:
    async def test_user_found(self):
        mock_user = _make_user(id=42)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        user = await get_user_by_id(42, mock_db)
        assert user.id == 42

    async def test_user_not_found(self):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        user = await get_user_by_id(999, mock_db)
        assert user is None


class TestGetUserByEmail:
    async def test_user_found(self):
        mock_user = _make_user(email="found@example.com")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        user = await get_user_by_email("found@example.com", mock_db)
        assert user.email == "found@example.com"

    async def test_user_not_found(self):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        user = await get_user_by_email("nope@example.com", mock_db)
        assert user is None


# ---------------------------------------------------------------------------
# create_jwt_token / verify_jwt_token
# ---------------------------------------------------------------------------


class TestCreateJwtToken:
    def test_raises_when_not_configured(self):
        with patch("services.auth.JWT_SECRET_KEY", ""):
            with pytest.raises(ConfigurationError, match="JWT_SECRET_KEY"):
                create_jwt_token(_make_user())

    def test_creates_valid_token(self):
        user = _make_user(id=42, email="u@b.com", name="U", subscription_tier="pro")

        with patch("services.auth.JWT_SECRET_KEY", "super-secret-key-for-testing-1234"):
            token = create_jwt_token(user)

            assert isinstance(token, str)
            # Decode without verification to check claims
            payload = pyjwt.decode(
                token,
                "super-secret-key-for-testing-1234",
                algorithms=["HS256"],
                issuer="benchgoblins",
            )
            assert payload["sub"] == "42"
            assert payload["email"] == "u@b.com"
            assert payload["name"] == "U"
            assert payload["tier"] == "pro"
            assert payload["iss"] == "benchgoblins"
            assert "jti" in payload
            assert "iat" in payload
            assert "exp" in payload


class TestVerifyJwtToken:
    def test_raises_when_not_configured(self):
        with patch("services.auth.JWT_SECRET_KEY", ""):
            with pytest.raises(ConfigurationError, match="JWT_SECRET_KEY"):
                verify_jwt_token("some.jwt.token")

    def test_valid_token(self):
        secret = "super-secret-key-for-testing-1234"
        user = _make_user(id=7, email="x@y.com", name="X", subscription_tier="free")

        with patch("services.auth.JWT_SECRET_KEY", secret):
            token = create_jwt_token(user)
            result = verify_jwt_token(token)

            assert result["user_id"] == 7
            assert result["email"] == "x@y.com"
            assert result["name"] == "X"
            assert result["tier"] == "free"
            assert isinstance(result["exp"], datetime)

    def test_expired_token(self):
        secret = "super-secret-key-for-testing-1234"
        # Create an already-expired token
        payload = {
            "sub": "1",
            "email": "e@e.com",
            "name": "E",
            "tier": "free",
            "jti": "abc",
            "iat": datetime(2020, 1, 1, tzinfo=UTC),
            "exp": datetime(2020, 1, 2, tzinfo=UTC),
            "iss": "benchgoblins",
        }
        token = pyjwt.encode(payload, secret, algorithm="HS256")

        with patch("services.auth.JWT_SECRET_KEY", secret):
            with pytest.raises(InvalidTokenError, match="expired"):
                verify_jwt_token(token)

    def test_invalid_issuer(self):
        secret = "super-secret-key-for-testing-1234"
        payload = {
            "sub": "1",
            "email": "e@e.com",
            "name": "E",
            "tier": "free",
            "jti": "abc",
            "iat": datetime.now(UTC),
            "exp": datetime(2099, 1, 1, tzinfo=UTC),
            "iss": "evil_issuer",
        }
        token = pyjwt.encode(payload, secret, algorithm="HS256")

        with patch("services.auth.JWT_SECRET_KEY", secret):
            with pytest.raises(InvalidTokenError, match="Invalid token"):
                verify_jwt_token(token)

    def test_malformed_token(self):
        with patch("services.auth.JWT_SECRET_KEY", "secret"):
            with pytest.raises(InvalidTokenError, match="Invalid token"):
                verify_jwt_token("not.a.valid.jwt")


# ---------------------------------------------------------------------------
# Token Blacklist
# ---------------------------------------------------------------------------


class TestBlacklistToken:
    async def test_redis_available(self):
        mock_redis = AsyncMock()

        with patch("services.auth._blacklist_redis", mock_redis):
            await blacklist_token("tok_123")

            mock_redis.setex.assert_called_once()
            key = mock_redis.setex.call_args[0][0]
            assert "tok_123" in key

    async def test_redis_failure_falls_back_to_memory(self):
        mock_redis = AsyncMock()
        mock_redis.setex.side_effect = ConnectionError("Redis down")
        test_set = set()

        with (
            patch("services.auth._blacklist_redis", mock_redis),
            patch("services.auth._token_blacklist", test_set),
        ):
            await blacklist_token("tok_456")

            assert "tok_456" in test_set

    async def test_no_redis_uses_memory(self):
        test_set = set()

        with (
            patch("services.auth._blacklist_redis", None),
            patch("services.auth._token_blacklist", test_set),
        ):
            await blacklist_token("tok_789")

            assert "tok_789" in test_set


class TestIsTokenBlacklisted:
    async def test_found_in_redis(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = b"1"

        with patch("services.auth._blacklist_redis", mock_redis):
            assert await is_token_blacklisted("tok_123") is True

    async def test_not_found_in_redis(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        with (
            patch("services.auth._blacklist_redis", mock_redis),
            patch("services.auth._token_blacklist", set()),
        ):
            assert await is_token_blacklisted("tok_123") is False

    async def test_redis_failure_checks_memory(self):
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = ConnectionError("Redis down")

        with (
            patch("services.auth._blacklist_redis", mock_redis),
            patch("services.auth._token_blacklist", {"tok_in_memory"}),
        ):
            assert await is_token_blacklisted("tok_in_memory") is True
            assert await is_token_blacklisted("tok_not_there") is False

    async def test_no_redis_checks_memory(self):
        with (
            patch("services.auth._blacklist_redis", None),
            patch("services.auth._token_blacklist", {"tok_mem"}),
        ):
            assert await is_token_blacklisted("tok_mem") is True
            assert await is_token_blacklisted("tok_nope") is False


class TestClearExpiredBlacklistEntries:
    async def test_removes_expired_keeps_valid(self):
        def mock_verify(token):
            if token == "expired_tok":
                raise InvalidTokenError("expired")
            return {"user_id": 1}

        test_set = {"valid_tok", "expired_tok"}

        with (
            patch("services.auth._token_blacklist", test_set),
            patch("services.auth.verify_jwt_token", side_effect=mock_verify),
        ):
            removed = await clear_expired_blacklist_entries()

            assert removed == 1

    async def test_all_expired(self):
        test_set = {"exp1", "exp2", "exp3"}

        with (
            patch("services.auth._token_blacklist", test_set),
            patch(
                "services.auth.verify_jwt_token",
                side_effect=InvalidTokenError("expired"),
            ),
        ):
            removed = await clear_expired_blacklist_entries()

            assert removed == 3

    async def test_none_expired(self):
        test_set = {"ok1", "ok2"}

        with (
            patch("services.auth._token_blacklist", test_set),
            patch("services.auth.verify_jwt_token", return_value={"user_id": 1}),
        ):
            removed = await clear_expired_blacklist_entries()

            assert removed == 0


# ---------------------------------------------------------------------------
# set_blacklist_redis
# ---------------------------------------------------------------------------


class TestSetBlacklistRedis:
    def test_sets_module_level_client(self):
        mock_redis = MagicMock()

        with patch("services.auth._blacklist_redis", None):
            set_blacklist_redis(mock_redis)
            # Verify it was set by the function (module-level global)
            import services.auth

            assert services.auth._blacklist_redis is mock_redis


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------


class TestIsConfigured:
    def test_fully_configured(self):
        with (
            patch("services.auth.GOOGLE_CLIENT_ID", "client_id"),
            patch("services.auth.JWT_SECRET_KEY", "secret"),
        ):
            result = auth_is_configured()
            assert result["google_oauth"] is True
            assert result["jwt"] is True
            assert result["fully_configured"] is True

    def test_only_google(self):
        with (
            patch("services.auth.GOOGLE_CLIENT_ID", "client_id"),
            patch("services.auth.JWT_SECRET_KEY", ""),
        ):
            result = auth_is_configured()
            assert result["google_oauth"] is True
            assert result["jwt"] is False
            assert result["fully_configured"] is False

    def test_only_jwt(self):
        with (
            patch("services.auth.GOOGLE_CLIENT_ID", ""),
            patch("services.auth.JWT_SECRET_KEY", "secret"),
        ):
            result = auth_is_configured()
            assert result["google_oauth"] is False
            assert result["jwt"] is True
            assert result["fully_configured"] is False

    def test_nothing_configured(self):
        with (
            patch("services.auth.GOOGLE_CLIENT_ID", ""),
            patch("services.auth.JWT_SECRET_KEY", ""),
        ):
            result = auth_is_configured()
            assert result["google_oauth"] is False
            assert result["jwt"] is False
            assert result["fully_configured"] is False
