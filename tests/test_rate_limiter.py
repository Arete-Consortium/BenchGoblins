"""Tests for rate limiter service."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.rate_limiter import RateLimiter


@pytest.fixture
def rate_limiter():
    """Fresh rate limiter with default settings."""
    return RateLimiter(max_requests=20, window_seconds=60)


@pytest.fixture
def strict_rate_limiter():
    """Rate limiter with strict limits for testing."""
    return RateLimiter(max_requests=3, window_seconds=10)


class TestRateLimiterBasics:
    def test_init_with_defaults(self):
        rl = RateLimiter()
        assert rl.max_requests == 20
        assert rl.window_seconds == 60

    def test_init_with_custom_values(self):
        rl = RateLimiter(max_requests=100, window_seconds=120)
        assert rl.max_requests == 100
        assert rl.window_seconds == 120

    def test_rate_limit_key(self, rate_limiter):
        key = rate_limiter._rate_limit_key("test-session")
        assert key == "ratelimit:test-session"


class TestMemoryRateLimiting:
    """Tests for in-memory rate limiting (no Redis)."""

    @pytest.mark.asyncio
    async def test_allows_requests_under_limit(self, strict_rate_limiter):
        """Should allow requests when under the limit."""
        rl = strict_rate_limiter

        # First request should be allowed
        allowed, retry_after = await rl.check_rate_limit("session1")
        assert allowed is True
        assert retry_after == 0

        # Second request should be allowed
        allowed, retry_after = await rl.check_rate_limit("session1")
        assert allowed is True
        assert retry_after == 0

        # Third request should be allowed (at limit)
        allowed, retry_after = await rl.check_rate_limit("session1")
        assert allowed is True
        assert retry_after == 0

    @pytest.mark.asyncio
    async def test_blocks_requests_over_limit(self, strict_rate_limiter):
        """Should block requests when over the limit."""
        rl = strict_rate_limiter

        # Use up all 3 requests
        for _ in range(3):
            await rl.check_rate_limit("session2")

        # Fourth request should be blocked
        allowed, retry_after = await rl.check_rate_limit("session2")
        assert allowed is False
        assert retry_after > 0

    @pytest.mark.asyncio
    async def test_retry_after_calculation(self, strict_rate_limiter):
        """Should calculate retry_after correctly."""
        rl = strict_rate_limiter

        # Use up all requests
        for _ in range(3):
            await rl.check_rate_limit("session3")

        # Blocked request should have retry_after <= window_seconds
        allowed, retry_after = await rl.check_rate_limit("session3")
        assert allowed is False
        assert 1 <= retry_after <= rl.window_seconds + 1

    @pytest.mark.asyncio
    async def test_separate_sessions(self, strict_rate_limiter):
        """Different sessions should have independent rate limits."""
        rl = strict_rate_limiter

        # Use up all requests for session A
        for _ in range(3):
            await rl.check_rate_limit("sessionA")

        # Session A should be blocked
        allowed_a, _ = await rl.check_rate_limit("sessionA")
        assert allowed_a is False

        # Session B should still be allowed
        allowed_b, _ = await rl.check_rate_limit("sessionB")
        assert allowed_b is True

    @pytest.mark.asyncio
    async def test_window_expiry(self):
        """Requests should be allowed again after window expires."""
        # Use a very short window for testing
        rl = RateLimiter(max_requests=1, window_seconds=1)

        # First request allowed
        allowed, _ = await rl.check_rate_limit("session4")
        assert allowed is True

        # Second request blocked
        allowed, _ = await rl.check_rate_limit("session4")
        assert allowed is False

        # Wait for window to expire
        time.sleep(1.1)

        # Should be allowed again
        allowed, _ = await rl.check_rate_limit("session4")
        assert allowed is True

    @pytest.mark.asyncio
    async def test_cleanup_removes_expired(self):
        """Memory store should clean up expired timestamps."""
        rl = RateLimiter(max_requests=10, window_seconds=1)

        # Add some requests
        await rl.check_rate_limit("session5")
        await rl.check_rate_limit("session5")
        assert len(rl._memory_store["session5"]) == 2

        # Wait for expiry
        time.sleep(1.1)

        # Cleanup happens on next check
        await rl.check_rate_limit("session5")
        # Should only have the new request, old ones cleaned up
        assert len(rl._memory_store["session5"]) == 1


class TestGetStatus:
    """Tests for get_status method."""

    @pytest.mark.asyncio
    async def test_status_empty_session(self, rate_limiter):
        """Status for new session should show full remaining."""
        status = await rate_limiter.get_status("new-session")

        assert status["session_id"] == "new-session"
        assert status["requests_used"] == 0
        assert status["requests_remaining"] == 20
        assert status["max_requests"] == 20
        assert status["window_seconds"] == 60
        assert status["storage"] == "memory"

    @pytest.mark.asyncio
    async def test_status_after_requests(self, strict_rate_limiter):
        """Status should reflect used requests."""
        rl = strict_rate_limiter

        # Make 2 requests
        await rl.check_rate_limit("status-session")
        await rl.check_rate_limit("status-session")

        status = await rl.get_status("status-session")

        assert status["requests_used"] == 2
        assert status["requests_remaining"] == 1
        assert status["reset_at"] is not None

    @pytest.mark.asyncio
    async def test_status_at_limit(self, strict_rate_limiter):
        """Status at limit should show 0 remaining."""
        rl = strict_rate_limiter

        # Use all requests
        for _ in range(3):
            await rl.check_rate_limit("limit-session")

        status = await rl.get_status("limit-session")

        assert status["requests_used"] == 3
        assert status["requests_remaining"] == 0


class TestReset:
    """Tests for reset method."""

    @pytest.mark.asyncio
    async def test_reset_clears_session(self, strict_rate_limiter):
        """Reset should clear rate limit for session."""
        rl = strict_rate_limiter

        # Use up all requests
        for _ in range(3):
            await rl.check_rate_limit("reset-session")

        # Should be blocked
        allowed, _ = await rl.check_rate_limit("reset-session")
        assert allowed is False

        # Reset the session
        rl.reset("reset-session")

        # Should be allowed again
        allowed, _ = await rl.check_rate_limit("reset-session")
        assert allowed is True

    def test_reset_nonexistent_session(self, rate_limiter):
        """Reset on nonexistent session should not error."""
        rate_limiter.reset("nonexistent")  # Should not raise


class TestRedisRateLimiting:
    """Tests for Redis-backed rate limiting."""

    @pytest.mark.asyncio
    async def test_uses_redis_when_connected(self, strict_rate_limiter):
        """Should use Redis when available."""
        rl = strict_rate_limiter

        # Mock redis_service
        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_client = AsyncMock()
        mock_redis._client = mock_client

        # Mock pipeline for check — pipeline methods are sync (queue commands),
        # only execute() is async
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(
            return_value=[0, 0]
        )  # zremrangebyscore result, zcard result
        mock_client.pipeline = MagicMock(return_value=mock_pipe)
        mock_client.zadd = AsyncMock()
        mock_client.expire = AsyncMock()

        with patch("services.rate_limiter.redis_service", mock_redis):
            allowed, _ = await rl.check_rate_limit("redis-session")

        assert allowed is True
        mock_client.zadd.assert_called_once()
        mock_client.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_blocks_over_limit(self, strict_rate_limiter):
        """Should block when Redis reports over limit."""
        rl = strict_rate_limiter

        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_client = AsyncMock()
        mock_redis._client = mock_client

        # Mock pipeline returning count at limit — pipeline methods are sync
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[0, 3])  # 3 requests already
        mock_client.pipeline = MagicMock(return_value=mock_pipe)
        mock_client.zrange = AsyncMock(return_value=[("ts", time.time() - 5)])

        with patch("services.rate_limiter.redis_service", mock_redis):
            allowed, retry_after = await rl.check_rate_limit("redis-blocked")

        assert allowed is False
        assert retry_after > 0

    @pytest.mark.asyncio
    async def test_falls_back_to_memory_on_redis_error(self, strict_rate_limiter):
        """Should fall back to memory when Redis fails."""
        rl = strict_rate_limiter

        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_client = AsyncMock()
        mock_redis._client = mock_client

        # Make pipeline raise an error
        mock_client.pipeline = MagicMock(side_effect=Exception("Redis error"))

        with patch("services.rate_limiter.redis_service", mock_redis):
            # Should not raise, should fall back to memory
            allowed, _ = await rl.check_rate_limit("fallback-session")

        assert allowed is True
        assert "fallback-session" in rl._memory_store

    @pytest.mark.asyncio
    async def test_falls_back_when_no_client(self, strict_rate_limiter):
        """Should fall back when Redis client is None."""
        rl = strict_rate_limiter

        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_redis._client = None

        with patch("services.rate_limiter.redis_service", mock_redis):
            allowed, _ = await rl.check_rate_limit("no-client-session")

        assert allowed is True
        assert "no-client-session" in rl._memory_store

    @pytest.mark.asyncio
    async def test_status_uses_redis_when_connected(self, rate_limiter):
        """get_status should use Redis when available."""
        rl = rate_limiter

        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_client = AsyncMock()
        mock_redis._client = mock_client

        mock_client.zremrangebyscore = AsyncMock()
        mock_client.zcard = AsyncMock(return_value=5)
        mock_client.zrange = AsyncMock(return_value=[("ts", time.time() - 30)])

        with patch("services.rate_limiter.redis_service", mock_redis):
            status = await rl.get_status("redis-status")

        assert status["requests_used"] == 5
        assert status["requests_remaining"] == 15
        assert status["storage"] == "redis"


class TestEnvironmentConfig:
    """Tests for environment variable configuration."""

    def test_default_config_from_env(self):
        """Should use environment variables for defaults."""
        with patch.dict(
            "os.environ",
            {"RATE_LIMIT_REQUESTS": "50", "RATE_LIMIT_WINDOW_SECONDS": "120"},
        ):
            # Need to reload module to pick up env vars
            import importlib
            import services.rate_limiter as rl_module

            importlib.reload(rl_module)

            # Check module-level constants were updated
            assert rl_module.RATE_LIMIT_REQUESTS == 50
            assert rl_module.RATE_LIMIT_WINDOW_SECONDS == 120

            # Reset to defaults
            with patch.dict(
                "os.environ",
                {"RATE_LIMIT_REQUESTS": "20", "RATE_LIMIT_WINDOW_SECONDS": "60"},
            ):
                importlib.reload(rl_module)
