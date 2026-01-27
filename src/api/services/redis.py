"""
Redis Caching Service — Fast player data and response caching.

Provides async Redis operations for:
- Player data caching (TTL: 1 hour)
- Claude response caching (TTL: 1 hour for identical queries)
- Rate limiting support (future)
"""

import hashlib
import json
import os
from typing import Any

import redis.asyncio as redis

# Import monitoring helpers (optional - gracefully degrade if not available)
try:
    from monitoring import track_cache_operation
except ImportError:

    def track_cache_operation(operation: str, hit: bool) -> None:
        pass


# Redis URL from environment
REDIS_URL = os.getenv("REDIS_URL", "")


class RedisService:
    """Async Redis caching service."""

    # TTLs in seconds
    PLAYER_TTL = 3600  # 1 hour
    DECISION_TTL = 3600  # 1 hour
    STATS_TTL = 1800  # 30 minutes

    def __init__(self, url: str | None = None):
        self._url = url or REDIS_URL
        self._client: redis.Redis | None = None

    @property
    def is_configured(self) -> bool:
        """Check if Redis URL is configured."""
        return bool(self._url)

    @property
    def is_connected(self) -> bool:
        """Check if connected to Redis."""
        return self._client is not None

    async def connect(self) -> None:
        """Initialize Redis connection."""
        if not self._url:
            return

        self._client = redis.from_url(
            self._url,
            encoding="utf-8",
            decode_responses=True,
        )
        # Test connection
        try:
            await self._client.ping()
        except redis.ConnectionError:
            self._client = None
            raise

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None

    async def health_check(self) -> bool:
        """Check if Redis is healthy."""
        if not self._client:
            return False
        try:
            await self._client.ping()
            return True
        except redis.ConnectionError:
            return False

    # =========================================================================
    # Player Caching
    # =========================================================================

    def _player_key(self, sport: str, player_id: str) -> str:
        """Generate cache key for player data."""
        return f"player:{sport}:{player_id}"

    def _player_search_key(self, sport: str, query: str) -> str:
        """Generate cache key for player search results."""
        query_hash = hashlib.md5(query.lower().strip().encode()).hexdigest()[:8]
        return f"search:{sport}:{query_hash}"

    async def get_player(self, sport: str, player_id: str) -> dict | None:
        """Get cached player data."""
        if not self._client:
            return None
        try:
            data = await self._client.get(self._player_key(sport, player_id))
            result = json.loads(data) if data else None
            track_cache_operation("get", hit=result is not None)
            return result
        except (redis.ConnectionError, json.JSONDecodeError):
            return None

    async def set_player(self, sport: str, player_id: str, data: dict) -> bool:
        """Cache player data."""
        if not self._client:
            return False
        try:
            await self._client.setex(
                self._player_key(sport, player_id),
                self.PLAYER_TTL,
                json.dumps(data),
            )
            return True
        except redis.ConnectionError:
            return False

    async def get_player_search(self, sport: str, query: str) -> list[dict] | None:
        """Get cached search results."""
        if not self._client:
            return None
        try:
            data = await self._client.get(self._player_search_key(sport, query))
            result = json.loads(data) if data else None
            track_cache_operation("get", hit=result is not None)
            return result
        except (redis.ConnectionError, json.JSONDecodeError):
            return None

    async def set_player_search(self, sport: str, query: str, results: list[dict]) -> bool:
        """Cache search results."""
        if not self._client:
            return False
        try:
            await self._client.setex(
                self._player_search_key(sport, query),
                self.STATS_TTL,  # Shorter TTL for search
                json.dumps(results),
            )
            return True
        except redis.ConnectionError:
            return False

    # =========================================================================
    # Decision Caching (for Claude responses)
    # =========================================================================

    def _decision_key(self, sport: str, risk_mode: str, query: str) -> str:
        """Generate cache key for decision."""
        query_hash = hashlib.md5(query.lower().strip().encode()).hexdigest()[:12]
        return f"decision:{sport}:{risk_mode}:{query_hash}"

    async def get_decision(self, sport: str, risk_mode: str, query: str) -> dict | None:
        """Get cached Claude decision."""
        if not self._client:
            return None
        try:
            data = await self._client.get(self._decision_key(sport, risk_mode, query))
            result = json.loads(data) if data else None
            track_cache_operation("get", hit=result is not None)
            return result
        except (redis.ConnectionError, json.JSONDecodeError):
            return None

    async def set_decision(self, sport: str, risk_mode: str, query: str, decision: dict) -> bool:
        """Cache Claude decision."""
        if not self._client:
            return False
        try:
            await self._client.setex(
                self._decision_key(sport, risk_mode, query),
                self.DECISION_TTL,
                json.dumps(decision),
            )
            return True
        except redis.ConnectionError:
            return False

    # =========================================================================
    # Stats / Metrics
    # =========================================================================

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        if not self._client:
            return {"connected": False}

        try:
            info = await self._client.info("stats")
            memory = await self._client.info("memory")
            keys = await self._client.dbsize()

            return {
                "connected": True,
                "keys": keys,
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
                "memory_used_mb": round(memory.get("used_memory", 0) / (1024 * 1024), 2),
            }
        except redis.ConnectionError:
            return {"connected": False}

    async def clear_pattern(self, pattern: str) -> int:
        """Clear keys matching pattern."""
        if not self._client:
            return 0
        try:
            keys = []
            async for key in self._client.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                return await self._client.delete(*keys)
            return 0
        except redis.ConnectionError:
            return 0

    async def clear_all(self) -> bool:
        """Clear all GameSpace cache keys."""
        if not self._client:
            return False
        try:
            # Only clear our keys, not the entire Redis
            patterns = ["player:*", "search:*", "decision:*"]
            for pattern in patterns:
                await self.clear_pattern(pattern)
            return True
        except redis.ConnectionError:
            return False


# Singleton instance
redis_service = RedisService()
