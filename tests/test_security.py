"""
Tests for security boundaries: auth enforcement, input validation, CORS.
"""

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def _bypass_rate_limiter():
    """Bypass rate limiter for all tests in this module."""
    with patch(
        "api.main.rate_limiter.check_rate_limit",
        new_callable=AsyncMock,
        return_value=(True, 0),
    ):
        yield


@pytest.fixture
def _valid_sports_query():
    """Make _is_sports_query always approve."""
    with patch("api.main._is_sports_query", return_value=(True, None)):
        yield


VALID_USER = {
    "user_id": 42,
    "email": "test@example.com",
    "name": "Test",
    "tier": "free",
}

DECIDE_PAYLOAD = {
    "sport": "nba",
    "query": "Should I start LeBron or AD?",
}

DRAFT_PAYLOAD = {
    "sport": "nba",
    "query": "Draft LeBron or AD?",
}


# ---------------------------------------------------------------------------
# H1: Billing endpoints require JWT auth (401 without)
# ---------------------------------------------------------------------------


class TestBillingAuthRequired:
    """Billing endpoints must return 401 when no JWT is provided."""

    def test_create_checkout_no_auth_returns_401(self, test_client):
        response = test_client.post(
            "/billing/create-checkout",
            json={
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )
        assert response.status_code == 401

    def test_create_portal_no_auth_returns_401(self, test_client):
        response = test_client.post(
            "/billing/create-portal",
            json={"return_url": "https://example.com/billing"},
        )
        assert response.status_code == 401

    def test_billing_status_no_auth_returns_401(self, test_client):
        response = test_client.get("/billing/status")
        assert response.status_code == 401

    def test_create_checkout_with_valid_jwt(self, test_client):
        """Billing works when valid JWT is provided."""
        with patch(
            "api.main.get_current_user",
            return_value=VALID_USER,
        ):
            with patch("api.main.stripe_billing.is_configured", return_value=True):
                with patch(
                    "api.main.stripe_billing.create_checkout_session",
                    new_callable=AsyncMock,
                    return_value="https://checkout.stripe.com/test",
                ):
                    from api.main import app
                    from routes.auth import get_current_user

                    app.dependency_overrides[get_current_user] = lambda: VALID_USER
                    try:
                        response = test_client.post(
                            "/billing/create-checkout",
                            json={
                                "price_id": "price_test_123",
                                "success_url": "https://example.com/success",
                                "cancel_url": "https://example.com/cancel",
                            },
                        )
                        assert response.status_code == 200
                        assert "checkout_url" in response.json()
                    finally:
                        app.dependency_overrides.pop(get_current_user, None)

    def test_billing_status_with_valid_jwt(self, test_client):
        """Billing status works when valid JWT is provided."""
        from api.main import app
        from routes.auth import get_current_user

        mock_user = MagicMock()
        mock_user.subscription_tier = "free"
        mock_user.queries_today = 3
        mock_user.queries_reset_at = None
        mock_user.stripe_customer_id = None
        mock_user.stripe_subscription_id = None

        app.dependency_overrides[get_current_user] = lambda: VALID_USER
        try:
            with patch(
                "api.main._get_user_by_id",
                new_callable=AsyncMock,
                return_value=mock_user,
            ):
                response = test_client.get("/billing/status")
                assert response.status_code == 200
                data = response.json()
                assert "tier" in data
                assert "queries_today" in data
        finally:
            app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# H1: /decide, /draft, /decide/stream work anonymously
# ---------------------------------------------------------------------------


class TestAnonymousAccess:
    """Endpoints should work without auth (anonymous, rate-limited)."""

    @pytest.mark.usefixtures("_bypass_rate_limiter", "_valid_sports_query")
    def test_decide_anonymous_works(self, test_client):
        """POST /decide with no auth header should not return 401."""
        response = test_client.post("/decide", json=DECIDE_PAYLOAD)
        # May fail for other reasons (ESPN lookup, Claude unavailable)
        # but must NOT be 401 — anonymous access is allowed
        assert response.status_code != 401

    @pytest.mark.usefixtures("_bypass_rate_limiter")
    def test_draft_anonymous_works(self, test_client):
        """POST /draft with no auth header should not return 401."""
        response = test_client.post("/draft", json=DRAFT_PAYLOAD)
        assert response.status_code != 401


# ---------------------------------------------------------------------------
# H1: Invalid JWT returns 401 (not silent anonymous fallback)
# ---------------------------------------------------------------------------


class TestInvalidJwtReturns401:
    """When a JWT is sent but is invalid/expired, return 401 not anonymous."""

    @pytest.mark.usefixtures("_bypass_rate_limiter", "_valid_sports_query")
    def test_decide_expired_jwt_returns_401(self, test_client):
        """POST /decide with expired JWT should return 401."""
        from services.auth import InvalidTokenError

        with patch(
            "routes.auth.verify_jwt_token",
            side_effect=InvalidTokenError("Token has expired"),
        ):
            with patch("routes.auth.is_token_blacklisted", new_callable=AsyncMock, return_value=False):
                response = test_client.post(
                    "/decide",
                    json=DECIDE_PAYLOAD,
                    headers={"Authorization": "Bearer expired.jwt.token"},
                )
                assert response.status_code == 401
                assert "expired" in response.json()["detail"].lower()

    @pytest.mark.usefixtures("_bypass_rate_limiter", "_valid_sports_query")
    def test_decide_blacklisted_jwt_returns_401(self, test_client):
        """POST /decide with blacklisted JWT should return 401."""
        with patch("routes.auth.is_token_blacklisted", new_callable=AsyncMock, return_value=True):
            response = test_client.post(
                "/decide",
                json=DECIDE_PAYLOAD,
                headers={"Authorization": "Bearer blacklisted.jwt.token"},
            )
            assert response.status_code == 401
            assert "revoked" in response.json()["detail"].lower()

    @pytest.mark.usefixtures("_bypass_rate_limiter", "_valid_sports_query")
    def test_decide_malformed_auth_header_returns_401(self, test_client):
        """POST /decide with malformed auth header should return 401."""
        response = test_client.post(
            "/decide",
            json=DECIDE_PAYLOAD,
            headers={"Authorization": "NotBearer some.token"},
        )
        assert response.status_code == 401

    @pytest.mark.usefixtures("_bypass_rate_limiter")
    def test_draft_expired_jwt_returns_401(self, test_client):
        """POST /draft with expired JWT should return 401."""
        from services.auth import InvalidTokenError

        with patch(
            "routes.auth.verify_jwt_token",
            side_effect=InvalidTokenError("Token has expired"),
        ):
            with patch("routes.auth.is_token_blacklisted", new_callable=AsyncMock, return_value=False):
                response = test_client.post(
                    "/draft",
                    json=DRAFT_PAYLOAD,
                    headers={"Authorization": "Bearer expired.jwt.token"},
                )
                assert response.status_code == 401

    @pytest.mark.usefixtures("_bypass_rate_limiter", "_valid_sports_query")
    def test_decide_stream_expired_jwt_returns_401(self, test_client):
        """POST /decide/stream with expired JWT should return 401."""
        from services.auth import InvalidTokenError

        with patch(
            "routes.auth.verify_jwt_token",
            side_effect=InvalidTokenError("Token has expired"),
        ):
            with patch("routes.auth.is_token_blacklisted", new_callable=AsyncMock, return_value=False):
                response = test_client.post(
                    "/decide/stream",
                    json=DECIDE_PAYLOAD,
                    headers={"Authorization": "Bearer expired.jwt.token"},
                )
                assert response.status_code == 401


# ---------------------------------------------------------------------------
# H1: Valid JWT extracts user_id from token
# ---------------------------------------------------------------------------


class TestJwtUserExtraction:
    """When a valid JWT is provided, user_id comes from token claims."""

    @pytest.mark.usefixtures("_bypass_rate_limiter", "_valid_sports_query")
    def test_decide_valid_jwt_extracts_user_id(self, test_client):
        """POST /decide with valid JWT uses token's user_id for tier check."""
        from api.main import app
        from routes.auth import get_optional_user
        from services.claude import ClaudeService

        app.dependency_overrides[get_optional_user] = lambda: VALID_USER
        try:
            with patch(
                "api.main._check_and_increment_query_count",
                new_callable=AsyncMock,
                return_value=(True, 1, 5),
            ) as mock_check:
                with patch(
                    "api.main.classify_query",
                    return_value="simple",
                ):
                    with patch(
                        "api.main.extract_players_from_query",
                        return_value=("LeBron James", "Anthony Davis"),
                    ):
                        with patch(
                            "api.main.espn_service.find_player_by_name",
                            new_callable=AsyncMock,
                            return_value=None,
                        ):
                            with patch.object(
                                ClaudeService,
                                "is_available",
                                new_callable=PropertyMock,
                                return_value=False,
                            ):
                                test_client.post("/decide", json=DECIDE_PAYLOAD)
                                # Verify user_id=42 was passed to tier check
                                mock_check.assert_called_once_with(42)
        finally:
            app.dependency_overrides.pop(get_optional_user, None)


# ---------------------------------------------------------------------------
# H7: Input length validation (422 on oversized input)
# ---------------------------------------------------------------------------


class TestInputLengthValidation:
    """Oversized inputs should be rejected with 422."""

    def test_decide_query_too_long_returns_422(self, test_client):
        response = test_client.post(
            "/decide",
            json={
                "sport": "nba",
                "query": "x" * 1001,
            },
        )
        assert response.status_code == 422

    def test_decide_query_at_max_is_ok(self, test_client):
        """Query exactly at max_length should not be rejected by validation."""
        response = test_client.post(
            "/decide",
            json={
                "sport": "nba",
                "query": "x" * 1000,
            },
        )
        # May fail for other reasons (rate limit, not sports query) but not 422
        assert response.status_code != 422

    def test_decide_player_name_too_long_returns_422(self, test_client):
        response = test_client.post(
            "/decide",
            json={
                "sport": "nba",
                "query": "Start A or B?",
                "player_a": "x" * 101,
            },
        )
        assert response.status_code == 422

    def test_decide_league_type_too_long_returns_422(self, test_client):
        response = test_client.post(
            "/decide",
            json={
                "sport": "nba",
                "query": "Start A or B?",
                "league_type": "x" * 51,
            },
        )
        assert response.status_code == 422

    def test_draft_query_too_long_returns_422(self, test_client):
        response = test_client.post(
            "/draft",
            json={
                "sport": "nba",
                "query": "x" * 1001,
            },
        )
        assert response.status_code == 422

    def test_draft_too_many_players_returns_422(self, test_client):
        response = test_client.post(
            "/draft",
            json={
                "sport": "nba",
                "query": "Draft someone",
                "players": [f"Player {i}" for i in range(21)],
            },
        )
        assert response.status_code == 422

    def test_draft_player_name_too_long_returns_422(self, test_client):
        response = test_client.post(
            "/draft",
            json={
                "sport": "nba",
                "query": "Draft someone",
                "players": ["x" * 101],
            },
        )
        assert response.status_code == 422

    def test_draft_too_many_position_needs_returns_422(self, test_client):
        response = test_client.post(
            "/draft",
            json={
                "sport": "nba",
                "query": "Draft someone",
                "position_needs": [
                    "PG",
                    "SG",
                    "SF",
                    "PF",
                    "C",
                    "G",
                    "F",
                    "UTIL",
                    "BE",
                    "IR",
                    "X",
                ],
            },
        )
        assert response.status_code == 422

    def test_draft_position_need_too_long_returns_422(self, test_client):
        response = test_client.post(
            "/draft",
            json={
                "sport": "nba",
                "query": "Draft someone",
                "position_needs": ["x" * 11],
            },
        )
        assert response.status_code == 422

    def test_checkout_url_too_long_returns_422(self, test_client):
        """Even with auth, oversized URLs should be rejected."""
        from api.main import app
        from routes.auth import get_current_user

        app.dependency_overrides[get_current_user] = lambda: VALID_USER
        try:
            response = test_client.post(
                "/billing/create-checkout",
                json={
                    "success_url": "https://example.com/" + "x" * 500,
                    "cancel_url": "https://example.com/cancel",
                },
            )
            assert response.status_code == 422
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_portal_url_too_long_returns_422(self, test_client):
        """Even with auth, oversized return URL should be rejected."""
        from api.main import app
        from routes.auth import get_current_user

        app.dependency_overrides[get_current_user] = lambda: VALID_USER
        try:
            response = test_client.post(
                "/billing/create-portal",
                json={"return_url": "https://example.com/" + "x" * 500},
            )
            assert response.status_code == 422
        finally:
            app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# get_optional_user unit tests
# ---------------------------------------------------------------------------


class TestGetOptionalUser:
    """Unit tests for the get_optional_user dependency."""

    @pytest.mark.asyncio
    async def test_no_header_returns_none(self):
        from routes.auth import get_optional_user

        result = await get_optional_user(authorization=None)
        assert result is None

    @pytest.mark.asyncio
    async def test_valid_bearer_returns_user(self):
        from routes.auth import get_optional_user

        with patch("routes.auth.is_token_blacklisted", new_callable=AsyncMock, return_value=False):
            with patch("routes.auth.verify_jwt_token", return_value=VALID_USER):
                result = await get_optional_user(authorization="Bearer valid.token")
                assert result == VALID_USER

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self):
        from fastapi import HTTPException

        from routes.auth import get_optional_user
        from services.auth import InvalidTokenError

        with patch("routes.auth.is_token_blacklisted", new_callable=AsyncMock, return_value=False):
            with patch(
                "routes.auth.verify_jwt_token",
                side_effect=InvalidTokenError("Token has expired"),
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await get_optional_user(authorization="Bearer expired.token")
                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_blacklisted_token_raises_401(self):
        from fastapi import HTTPException

        from routes.auth import get_optional_user

        with patch("routes.auth.is_token_blacklisted", new_callable=AsyncMock, return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                await get_optional_user(authorization="Bearer blacklisted.token")
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_header_raises_401(self):
        from fastapi import HTTPException

        from routes.auth import get_optional_user

        with pytest.raises(HTTPException) as exc_info:
            await get_optional_user(authorization="Basic dXNlcjpwYXNz")
        assert exc_info.value.status_code == 401
