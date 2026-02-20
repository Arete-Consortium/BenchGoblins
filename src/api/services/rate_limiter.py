"""
Rate Limiter Service — Per-session request rate limiting.

Implements sliding window algorithm to prevent API abuse.
Uses Redis if available, falls back to in-memory dict.
"""

import os
import time
from typing import Any

# Import Redis service for persistence
try:
    from services.redis import redis_service
except ImportError:
    redis_service: Any = None


# Configuration via environment variables
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "20"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))


class RateLimiter:
    """
    Per-session rate limiter using sliding window algorithm.

    Uses Redis for distributed rate limiting if available,
    falls back to in-memory storage for single-instance deployments.
    """

    def __init__(
        self,
        max_requests: int = RATE_LIMIT_REQUESTS,
        window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # In-memory fallback: session_id -> list of timestamps
        self._memory_store: dict[str, list[float]] = {}

    def _rate_limit_key(self, session_id: str) -> str:
        """Generate Redis key for rate limit data."""
        return f"ratelimit:{session_id}"

    def _cleanup_memory_store(self, session_id: str, now: float) -> list[float]:
        """Remove expired timestamps from memory store and return current list."""
        if session_id not in self._memory_store:
            self._memory_store[session_id] = []

        cutoff = now - self.window_seconds
        self._memory_store[session_id] = [
            ts for ts in self._memory_store[session_id] if ts > cutoff
        ]
        return self._memory_store[session_id]

    async def check_rate_limit(self, session_id: str) -> tuple[bool, int]:
        """
        Check if request is allowed under rate limit.

        Args:
            session_id: Unique session identifier

        Returns:
            Tuple of (allowed: bool, retry_after: int)
            - allowed: True if request should proceed
            - retry_after: Seconds until next request allowed (0 if allowed)
        """
        now = time.time()

        # Try Redis first if available
        if redis_service and redis_service.is_connected:
            return await self._check_redis(session_id, now)

        # Fallback to in-memory
        return self._check_memory(session_id, now)

    async def _check_redis(self, session_id: str, now: float) -> tuple[bool, int]:
        """Check rate limit using Redis sorted set."""
        key = self._rate_limit_key(session_id)
        cutoff = now - self.window_seconds

        try:
            client = redis_service._client
            if not client:
                return self._check_memory(session_id, now)

            # Remove old entries and count current
            pipe = client.pipeline()
            pipe.zremrangebyscore(key, 0, cutoff)
            pipe.zcard(key)
            results = await pipe.execute()

            current_count = results[1]

            if current_count >= self.max_requests:
                # Get oldest timestamp to calculate retry_after
                oldest = await client.zrange(key, 0, 0, withscores=True)
                if oldest:
                    oldest_ts = oldest[0][1]
                    retry_after = int(oldest_ts + self.window_seconds - now) + 1
                    return False, max(1, retry_after)
                return False, 1

            # Add current request timestamp
            await client.zadd(key, {str(now): now})
            # Set expiry on the key to auto-cleanup
            await client.expire(key, self.window_seconds + 10)

            return True, 0

        except Exception:
            # On Redis error, fall back to memory
            return self._check_memory(session_id, now)

    def _check_memory(self, session_id: str, now: float) -> tuple[bool, int]:
        """Check rate limit using in-memory store."""
        timestamps = self._cleanup_memory_store(session_id, now)

        if len(timestamps) >= self.max_requests:
            # Calculate retry_after from oldest timestamp
            oldest = min(timestamps)
            retry_after = int(oldest + self.window_seconds - now) + 1
            return False, max(1, retry_after)

        # Add current request
        timestamps.append(now)
        return True, 0

    async def get_status(self, session_id: str) -> dict[str, Any]:
        """
        Get current rate limit status for a session.

        Returns:
            Dict with requests_remaining, window_seconds, reset_at
        """
        now = time.time()

        # Try Redis first
        if redis_service and redis_service.is_connected:
            return await self._get_status_redis(session_id, now)

        return self._get_status_memory(session_id, now)

    async def _get_status_redis(self, session_id: str, now: float) -> dict[str, Any]:
        """Get status from Redis."""
        key = self._rate_limit_key(session_id)
        cutoff = now - self.window_seconds

        try:
            client = redis_service._client
            if not client:
                return self._get_status_memory(session_id, now)

            # Clean up and get count
            await client.zremrangebyscore(key, 0, cutoff)
            current_count = await client.zcard(key)

            # Get oldest for reset time
            oldest = await client.zrange(key, 0, 0, withscores=True)
            reset_at = None
            if oldest:
                reset_at = oldest[0][1] + self.window_seconds

            return {
                "session_id": session_id,
                "requests_used": current_count,
                "requests_remaining": max(0, self.max_requests - current_count),
                "max_requests": self.max_requests,
                "window_seconds": self.window_seconds,
                "reset_at": reset_at,
                "storage": "redis",
            }
        except Exception:
            return self._get_status_memory(session_id, now)

    def _get_status_memory(self, session_id: str, now: float) -> dict[str, Any]:
        """Get status from in-memory store."""
        timestamps = self._cleanup_memory_store(session_id, now)
        current_count = len(timestamps)

        reset_at = None
        if timestamps:
            reset_at = min(timestamps) + self.window_seconds

        return {
            "session_id": session_id,
            "requests_used": current_count,
            "requests_remaining": max(0, self.max_requests - current_count),
            "max_requests": self.max_requests,
            "window_seconds": self.window_seconds,
            "reset_at": reset_at,
            "storage": "memory",
        }

    def reset(self, session_id: str) -> None:
        """Reset rate limit for a session (in-memory only, for testing)."""
        if session_id in self._memory_store:
            del self._memory_store[session_id]


# Singleton instance
rate_limiter = RateLimiter()
