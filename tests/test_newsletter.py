"""Tests for newsletter subscription endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from routes.newsletter import (
    CountResponse,
    SubscribeRequest,
    SubscribeResponse,
    UnsubscribeRequest,
    _check_subscribe_rate,
    _get_client_ip,
    _subscribe_timestamps,
    count,
    subscribe,
    unsubscribe,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(ip: str = "127.0.0.1") -> MagicMock:
    """Create a mock FastAPI Request object."""
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = ip
    req.headers = {}  # No X-Forwarded-For in tests — uses client.host
    return req


def _make_subscriber(email: str, unsubscribed: bool = False) -> MagicMock:
    """Create a mock NewsletterSubscriber row."""
    sub = MagicMock()
    sub.email = email
    sub.name = None
    sub.sport_interest = None
    sub.ip_address = None
    sub.unsubscribed_at = MagicMock() if unsubscribed else None
    return sub


# ---------------------------------------------------------------------------
# Request Validation
# ---------------------------------------------------------------------------


class TestSubscribeRequestValidation:
    def test_valid_email(self):
        req = SubscribeRequest(email="test@example.com")
        assert req.email == "test@example.com"

    def test_email_normalized_lowercase(self):
        req = SubscribeRequest(email="  Test@EXAMPLE.COM  ")
        assert req.email == "test@example.com"

    def test_invalid_email_rejected(self):
        with pytest.raises(ValueError):
            SubscribeRequest(email="not-an-email")

    def test_empty_email_rejected(self):
        with pytest.raises(ValueError):
            SubscribeRequest(email="")

    def test_valid_sport(self):
        req = SubscribeRequest(email="a@b.com", sport="nfl")
        assert req.sport == "nfl"

    def test_invalid_sport_rejected(self):
        with pytest.raises(ValueError):
            SubscribeRequest(email="a@b.com", sport="cricket")

    def test_empty_sport_becomes_none(self):
        req = SubscribeRequest(email="a@b.com", sport="")
        assert req.sport is None

    def test_optional_fields(self):
        req = SubscribeRequest(email="a@b.com", name="Test", referrer="landing")
        assert req.name == "Test"
        assert req.referrer == "landing"


class TestUnsubscribeRequestValidation:
    def test_email_normalized(self):
        req = UnsubscribeRequest(email="  Test@EXAMPLE.COM  ")
        assert req.email == "test@example.com"


# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Client IP Extraction
# ---------------------------------------------------------------------------


class TestGetClientIp:
    def test_uses_x_forwarded_for_first_entry(self):
        """Line 96: X-Forwarded-For header present — returns first IP."""
        req = MagicMock()
        req.headers = {"X-Forwarded-For": "203.0.113.50, 70.41.3.18, 150.172.238.178"}
        req.client = MagicMock()
        req.client.host = "10.0.0.1"

        assert _get_client_ip(req) == "203.0.113.50"

    def test_uses_x_forwarded_for_single_ip(self):
        """Line 96: X-Forwarded-For with a single IP."""
        req = MagicMock()
        req.headers = {"X-Forwarded-For": " 192.168.1.1 "}
        req.client = MagicMock()
        req.client.host = "10.0.0.1"

        assert _get_client_ip(req) == "192.168.1.1"

    def test_falls_back_to_client_host(self):
        """Uses request.client.host when no X-Forwarded-For."""
        req = MagicMock()
        req.headers = {}
        req.client = MagicMock()
        req.client.host = "172.16.0.1"

        assert _get_client_ip(req) == "172.16.0.1"

    def test_returns_unknown_when_no_client(self):
        """Line 99: request.client is None — returns 'unknown'."""
        req = MagicMock()
        req.headers = {}
        req.client = None

        assert _get_client_ip(req) == "unknown"


# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------


class TestSubscribeRateLimit:
    def setup_method(self):
        _subscribe_timestamps.clear()

    @pytest.mark.asyncio
    async def test_allows_first_request(self):
        assert await _check_subscribe_rate("1.2.3.4") is True

    @pytest.mark.asyncio
    async def test_allows_up_to_limit(self):
        for _ in range(5):
            assert await _check_subscribe_rate("1.2.3.5") is True

    @pytest.mark.asyncio
    async def test_blocks_over_limit(self):
        for _ in range(5):
            await _check_subscribe_rate("1.2.3.6")
        assert await _check_subscribe_rate("1.2.3.6") is False

    @pytest.mark.asyncio
    async def test_separate_ips_tracked_independently(self):
        for _ in range(5):
            await _check_subscribe_rate("10.0.0.1")
        assert await _check_subscribe_rate("10.0.0.1") is False
        assert await _check_subscribe_rate("10.0.0.2") is True


# ---------------------------------------------------------------------------
# Redis Rate Limiting (lines 114-121)
# ---------------------------------------------------------------------------


class TestRedisRateLimit:
    """Tests for the Redis-based rate limiting path."""

    def setup_method(self):
        _subscribe_timestamps.clear()

    @pytest.mark.asyncio
    async def test_redis_rate_limit_allows_first_request(self):
        """Lines 114-119: Redis connected, first request (count=1) sets expiry."""
        mock_client = AsyncMock()
        mock_client.incr = AsyncMock(return_value=1)
        mock_client.expire = AsyncMock()

        with patch("routes.newsletter.redis_service") as mock_redis:
            mock_redis.is_connected = True
            mock_redis._client = mock_client

            result = await _check_subscribe_rate("redis-ip-1")

        assert result is True
        mock_client.incr.assert_called_once_with("newsletter_rate:redis-ip-1")
        mock_client.expire.assert_called_once_with("newsletter_rate:redis-ip-1", 3600)

    @pytest.mark.asyncio
    async def test_redis_rate_limit_allows_within_limit(self):
        """Lines 114-119: Redis connected, count within limit (count=3)."""
        mock_client = AsyncMock()
        mock_client.incr = AsyncMock(return_value=3)

        with patch("routes.newsletter.redis_service") as mock_redis:
            mock_redis.is_connected = True
            mock_redis._client = mock_client

            result = await _check_subscribe_rate("redis-ip-2")

        assert result is True
        # expire should NOT be called since count != 1
        mock_client.expire.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_rate_limit_blocks_over_limit(self):
        """Lines 114-119: Redis connected, count exceeds limit (count=6)."""
        mock_client = AsyncMock()
        mock_client.incr = AsyncMock(return_value=6)

        with patch("routes.newsletter.redis_service") as mock_redis:
            mock_redis.is_connected = True
            mock_redis._client = mock_client

            result = await _check_subscribe_rate("redis-ip-3")

        assert result is False

    @pytest.mark.asyncio
    async def test_redis_rate_limit_at_exact_limit(self):
        """Lines 114-119: Redis connected, count exactly at limit (count=5)."""
        mock_client = AsyncMock()
        mock_client.incr = AsyncMock(return_value=5)

        with patch("routes.newsletter.redis_service") as mock_redis:
            mock_redis.is_connected = True
            mock_redis._client = mock_client

            result = await _check_subscribe_rate("redis-ip-4")

        assert result is True

    @pytest.mark.asyncio
    async def test_redis_exception_falls_back_to_in_memory(self):
        """Lines 120-121: Redis raises exception, falls back to in-memory."""
        mock_client = AsyncMock()
        mock_client.incr = AsyncMock(side_effect=ConnectionError("Redis down"))

        with patch("routes.newsletter.redis_service") as mock_redis:
            mock_redis.is_connected = True
            mock_redis._client = mock_client

            # Should fall through to in-memory and allow (first request)
            result = await _check_subscribe_rate("redis-fail-ip")

        assert result is True
        # Verify it used the in-memory path by checking timestamps
        assert "redis-fail-ip" in _subscribe_timestamps

    @pytest.mark.asyncio
    async def test_redis_not_connected_uses_in_memory(self):
        """When Redis is not connected, uses in-memory fallback."""
        with patch("routes.newsletter.redis_service") as mock_redis:
            mock_redis.is_connected = False
            mock_redis._client = None

            result = await _check_subscribe_rate("no-redis-ip")

        assert result is True
        assert "no-redis-ip" in _subscribe_timestamps


# ---------------------------------------------------------------------------
# Subscribe Endpoint
# ---------------------------------------------------------------------------


class TestSubscribeEndpoint:
    @pytest.mark.asyncio
    async def test_new_subscriber(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        _subscribe_timestamps.clear()
        with patch("routes.newsletter.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            result = await subscribe(
                _make_request(),
                SubscribeRequest(email="new@test.com"),
            )

        assert isinstance(result, SubscribeResponse)
        assert result.success is True
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_subscriber_returns_success(self):
        existing = _make_subscriber("dup@test.com", unsubscribed=False)
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        _subscribe_timestamps.clear()
        with patch("routes.newsletter.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            result = await subscribe(
                _make_request(),
                SubscribeRequest(email="dup@test.com"),
            )

        assert result.success is True
        # Should NOT add a new subscriber
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_resubscribe_clears_unsubscribed(self):
        existing = _make_subscriber("re@test.com", unsubscribed=True)
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        _subscribe_timestamps.clear()
        with patch("routes.newsletter.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            result = await subscribe(
                _make_request(),
                SubscribeRequest(email="re@test.com"),
            )

        assert result.success is True
        assert existing.unsubscribed_at is None

    @pytest.mark.asyncio
    async def test_rate_limited(self):
        _subscribe_timestamps.clear()
        # Exhaust rate limit
        for _ in range(5):
            await _check_subscribe_rate("9.9.9.9")

        with patch("routes.newsletter.db_service") as mock_db:
            mock_db.is_configured = True

            with pytest.raises(Exception) as exc_info:
                await subscribe(
                    _make_request("9.9.9.9"),
                    SubscribeRequest(email="rate@test.com"),
                )
            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_db_not_configured(self):
        _subscribe_timestamps.clear()
        with patch("routes.newsletter.db_service") as mock_db:
            mock_db.is_configured = False

            with pytest.raises(Exception) as exc_info:
                await subscribe(
                    _make_request(),
                    SubscribeRequest(email="x@test.com"),
                )
            assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Unsubscribe Endpoint
# ---------------------------------------------------------------------------


class TestUnsubscribeEndpoint:
    @pytest.mark.asyncio
    async def test_unsubscribe_active(self):
        existing = _make_subscriber("bye@test.com", unsubscribed=False)
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routes.newsletter.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            result = await unsubscribe(UnsubscribeRequest(email="bye@test.com"))

        assert result.success is True
        # unsubscribed_at should have been set (func.now())
        assert existing.unsubscribed_at is not None

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_returns_success(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routes.newsletter.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            result = await unsubscribe(UnsubscribeRequest(email="ghost@test.com"))

        # Doesn't leak that the email doesn't exist
        assert result.success is True

    @pytest.mark.asyncio
    async def test_unsubscribe_db_not_configured(self):
        """Line 193: unsubscribe raises 503 when db not configured."""
        with patch("routes.newsletter.db_service") as mock_db:
            mock_db.is_configured = False

            with pytest.raises(Exception) as exc_info:
                await unsubscribe(UnsubscribeRequest(email="x@test.com"))
            assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Count Endpoint (Admin)
# ---------------------------------------------------------------------------


class TestCountEndpoint:
    @pytest.mark.asyncio
    async def test_count_returns_active_and_total(self):
        mock_session = AsyncMock()

        # First call returns active count, second returns total
        active_result = MagicMock()
        active_result.scalar.return_value = 42
        total_result = MagicMock()
        total_result.scalar.return_value = 50

        mock_session.execute = AsyncMock(side_effect=[active_result, total_result])

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("routes.newsletter.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            result = await count()

        assert isinstance(result, CountResponse)
        assert result.active == 42
        assert result.total == 50

    @pytest.mark.asyncio
    async def test_count_db_not_configured(self):
        """Line 213: count raises 503 when db not configured."""
        with patch("routes.newsletter.db_service") as mock_db:
            mock_db.is_configured = False

            with pytest.raises(Exception) as exc_info:
                await count()
            assert exc_info.value.status_code == 503
