"""Tests for Redis caching service."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from services.redis import RedisService


@pytest.fixture
def redis_svc():
    """RedisService with no URL (unconfigured)."""
    return RedisService(url="")


@pytest.fixture
def redis_svc_configured():
    """RedisService with a fake URL but no real connection."""
    svc = RedisService(url="redis://localhost:6379")
    return svc


@pytest.fixture
def redis_svc_connected():
    """RedisService with a mocked client."""
    svc = RedisService(url="redis://localhost:6379")
    svc._client = AsyncMock()
    return svc


class TestRedisServiceProperties:
    def test_not_configured(self, redis_svc):
        assert redis_svc.is_configured is False
        assert redis_svc.is_connected is False

    def test_configured(self, redis_svc_configured):
        assert redis_svc_configured.is_configured is True
        assert redis_svc_configured.is_connected is False

    def test_connected(self, redis_svc_connected):
        assert redis_svc_connected.is_connected is True


class TestKeyGeneration:
    def test_player_key(self, redis_svc):
        assert redis_svc._player_key("nba", "12345") == "player:nba:12345"

    def test_player_search_key(self, redis_svc):
        key = redis_svc._player_search_key("nba", "LeBron James")
        assert key.startswith("search:nba:")
        # Same query should produce same key
        key2 = redis_svc._player_search_key("nba", "lebron james")
        assert key == key2

    def test_player_search_key_strips(self, redis_svc):
        key1 = redis_svc._player_search_key("nfl", " mahomes ")
        key2 = redis_svc._player_search_key("nfl", "mahomes")
        assert key1 == key2

    def test_decision_key(self, redis_svc):
        key = redis_svc._decision_key("nba", "safe", "start player x")
        assert key.startswith("decision:nba:safe:")

    def test_stats_version_key(self, redis_svc):
        assert redis_svc._stats_version_key("nfl") == "stats_version:nfl"


class TestNoClientReturnsDefaults:
    """When client is None, all operations should return safe defaults."""

    @pytest.mark.asyncio
    async def test_get_player_no_client(self, redis_svc):
        assert await redis_svc.get_player("nba", "123") is None

    @pytest.mark.asyncio
    async def test_set_player_no_client(self, redis_svc):
        assert await redis_svc.set_player("nba", "123", {"name": "test"}) is False

    @pytest.mark.asyncio
    async def test_get_player_search_no_client(self, redis_svc):
        assert await redis_svc.get_player_search("nba", "test") is None

    @pytest.mark.asyncio
    async def test_set_player_search_no_client(self, redis_svc):
        assert await redis_svc.set_player_search("nba", "test", []) is False

    @pytest.mark.asyncio
    async def test_get_decision_no_client(self, redis_svc):
        assert await redis_svc.get_decision("nba", "safe", "query") is None

    @pytest.mark.asyncio
    async def test_set_decision_no_client(self, redis_svc):
        assert await redis_svc.set_decision("nba", "safe", "query", {}) is False

    @pytest.mark.asyncio
    async def test_get_stats_version_no_client(self, redis_svc):
        assert await redis_svc.get_stats_version("nba") == 0

    @pytest.mark.asyncio
    async def test_bump_stats_version_no_client(self, redis_svc):
        assert await redis_svc.bump_stats_version("nba") == 0

    @pytest.mark.asyncio
    async def test_get_stats_no_client(self, redis_svc):
        result = await redis_svc.get_stats()
        assert result == {"connected": False}

    @pytest.mark.asyncio
    async def test_clear_pattern_no_client(self, redis_svc):
        assert await redis_svc.clear_pattern("player:*") == 0

    @pytest.mark.asyncio
    async def test_clear_all_no_client(self, redis_svc):
        assert await redis_svc.clear_all() is False

    @pytest.mark.asyncio
    async def test_health_check_no_client(self, redis_svc):
        assert await redis_svc.health_check() is False


class TestWithMockedClient:
    @pytest.mark.asyncio
    async def test_get_player_hit(self, redis_svc_connected):
        svc = redis_svc_connected
        svc._client.get = AsyncMock(return_value=json.dumps({"name": "LeBron"}))
        result = await svc.get_player("nba", "123")
        assert result == {"name": "LeBron"}

    @pytest.mark.asyncio
    async def test_get_player_miss(self, redis_svc_connected):
        svc = redis_svc_connected
        svc._client.get = AsyncMock(return_value=None)
        result = await svc.get_player("nba", "123")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_player_success(self, redis_svc_connected):
        svc = redis_svc_connected
        svc._client.setex = AsyncMock()
        result = await svc.set_player("nba", "123", {"name": "test"})
        assert result is True
        svc._client.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_player_search_hit(self, redis_svc_connected):
        svc = redis_svc_connected
        svc._client.get = AsyncMock(return_value=json.dumps([{"id": "1"}]))
        result = await svc.get_player_search("nba", "lebron")
        assert result == [{"id": "1"}]

    @pytest.mark.asyncio
    async def test_set_player_search_success(self, redis_svc_connected):
        svc = redis_svc_connected
        svc._client.setex = AsyncMock()
        result = await svc.set_player_search("nba", "test", [{"id": "1"}])
        assert result is True

    @pytest.mark.asyncio
    async def test_get_stats_version(self, redis_svc_connected):
        svc = redis_svc_connected
        svc._client.get = AsyncMock(return_value="5")
        result = await svc.get_stats_version("nba")
        assert result == 5

    @pytest.mark.asyncio
    async def test_get_stats_version_none(self, redis_svc_connected):
        svc = redis_svc_connected
        svc._client.get = AsyncMock(return_value=None)
        result = await svc.get_stats_version("nba")
        assert result == 0

    @pytest.mark.asyncio
    async def test_bump_stats_version(self, redis_svc_connected):
        svc = redis_svc_connected
        svc._client.incr = AsyncMock(return_value=6)
        result = await svc.bump_stats_version("nba")
        assert result == 6

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, redis_svc_connected):
        svc = redis_svc_connected
        svc._client.ping = AsyncMock(return_value=True)
        assert await svc.health_check() is True

    @pytest.mark.asyncio
    async def test_disconnect(self, redis_svc_connected):
        svc = redis_svc_connected
        svc._client.close = AsyncMock()
        await svc.disconnect()
        assert svc._client is None

    @pytest.mark.asyncio
    async def test_get_stats_connected(self, redis_svc_connected):
        svc = redis_svc_connected
        svc._client.info = AsyncMock(
            side_effect=[
                {"keyspace_hits": 100, "keyspace_misses": 20},
                {"used_memory": 1048576},
            ]
        )
        svc._client.dbsize = AsyncMock(return_value=50)
        result = await svc.get_stats()
        assert result["connected"] is True
        assert result["keys"] == 50
        assert result["hits"] == 100

    @pytest.mark.asyncio
    async def test_clear_pattern(self, redis_svc_connected):
        svc = redis_svc_connected

        async def mock_scan_iter(match=None):
            for key in ["player:nba:1", "player:nba:2"]:
                yield key

        svc._client.scan_iter = mock_scan_iter
        svc._client.delete = AsyncMock(return_value=2)
        result = await svc.clear_pattern("player:*")
        assert result == 2

    @pytest.mark.asyncio
    async def test_clear_pattern_no_keys(self, redis_svc_connected):
        svc = redis_svc_connected

        async def mock_scan_iter(match=None):
            return
            yield  # noqa: make it an async generator

        svc._client.scan_iter = mock_scan_iter
        result = await svc.clear_pattern("nonexistent:*")
        assert result == 0

    @pytest.mark.asyncio
    async def test_connect_no_url(self, redis_svc):
        await redis_svc.connect()
        assert redis_svc._client is None

    @pytest.mark.asyncio
    async def test_disconnect_no_client(self, redis_svc):
        await redis_svc.disconnect()  # Should not raise


class TestVersionedDecisionKey:
    @pytest.mark.asyncio
    async def test_versioned_key_includes_version(self, redis_svc_connected):
        svc = redis_svc_connected
        svc._client.get = AsyncMock(return_value="3")
        key = await svc._versioned_decision_key("nba", "safe", "start lebron")
        assert ":v3:" in key

    @pytest.mark.asyncio
    async def test_get_decision_hit(self, redis_svc_connected):
        svc = redis_svc_connected
        # First call for version, second for data
        svc._client.get = AsyncMock(
            side_effect=["1", json.dumps({"decision": "Start LeBron"})]
        )
        result = await svc.get_decision("nba", "safe", "test query")
        assert result == {"decision": "Start LeBron"}

    @pytest.mark.asyncio
    async def test_set_decision_success(self, redis_svc_connected):
        svc = redis_svc_connected
        svc._client.get = AsyncMock(return_value="1")
        svc._client.setex = AsyncMock()
        result = await svc.set_decision("nba", "safe", "test", {"decision": "x"})
        assert result is True


# ---------------------------------------------------------------------------
# Connect / Health Check flows
# ---------------------------------------------------------------------------


class TestConnectFlow:
    @pytest.mark.asyncio
    async def test_connect_success(self, redis_svc_configured):
        svc = redis_svc_configured
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()

        with patch("services.redis.redis.from_url", return_value=mock_client):
            await svc.connect()
            assert svc._client is mock_client
            mock_client.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_ping_failure(self, redis_svc_configured):
        import redis as _redis

        svc = redis_svc_configured
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=_redis.ConnectionError("refused"))

        with patch("services.redis.redis.from_url", return_value=mock_client):
            with pytest.raises(_redis.ConnectionError):
                await svc.connect()
            assert svc._client is None


class TestHealthCheckError:
    @pytest.mark.asyncio
    async def test_health_check_connection_error(self, redis_svc_connected):
        import redis as _redis

        svc = redis_svc_connected
        svc._client.ping = AsyncMock(side_effect=_redis.ConnectionError("down"))
        assert await svc.health_check() is False


# ---------------------------------------------------------------------------
# ConnectionError branches on all operations
# ---------------------------------------------------------------------------


class TestConnectionErrorBranches:
    @pytest.mark.asyncio
    async def test_get_player_connection_error(self, redis_svc_connected):
        import redis as _redis

        svc = redis_svc_connected
        svc._client.get = AsyncMock(side_effect=_redis.ConnectionError("err"))
        assert await svc.get_player("nba", "123") is None

    @pytest.mark.asyncio
    async def test_set_player_connection_error(self, redis_svc_connected):
        import redis as _redis

        svc = redis_svc_connected
        svc._client.setex = AsyncMock(side_effect=_redis.ConnectionError("err"))
        assert await svc.set_player("nba", "123", {"x": 1}) is False

    @pytest.mark.asyncio
    async def test_get_player_search_connection_error(self, redis_svc_connected):
        import redis as _redis

        svc = redis_svc_connected
        svc._client.get = AsyncMock(side_effect=_redis.ConnectionError("err"))
        assert await svc.get_player_search("nba", "test") is None

    @pytest.mark.asyncio
    async def test_set_player_search_connection_error(self, redis_svc_connected):
        import redis as _redis

        svc = redis_svc_connected
        svc._client.setex = AsyncMock(side_effect=_redis.ConnectionError("err"))
        assert await svc.set_player_search("nba", "test", []) is False

    @pytest.mark.asyncio
    async def test_get_stats_version_connection_error(self, redis_svc_connected):
        import redis as _redis

        svc = redis_svc_connected
        svc._client.get = AsyncMock(side_effect=_redis.ConnectionError("err"))
        assert await svc.get_stats_version("nba") == 0

    @pytest.mark.asyncio
    async def test_bump_stats_version_connection_error(self, redis_svc_connected):
        import redis as _redis

        svc = redis_svc_connected
        svc._client.incr = AsyncMock(side_effect=_redis.ConnectionError("err"))
        assert await svc.bump_stats_version("nba") == 0

    @pytest.mark.asyncio
    async def test_get_decision_connection_error(self, redis_svc_connected):
        import redis as _redis

        svc = redis_svc_connected
        svc._client.get = AsyncMock(side_effect=_redis.ConnectionError("err"))
        assert await svc.get_decision("nba", "safe", "query") is None

    @pytest.mark.asyncio
    async def test_set_decision_connection_error(self, redis_svc_connected):
        import redis as _redis

        svc = redis_svc_connected
        # First get for version key, then setex fails
        svc._client.get = AsyncMock(return_value="1")
        svc._client.setex = AsyncMock(side_effect=_redis.ConnectionError("err"))
        assert await svc.set_decision("nba", "safe", "q", {"d": 1}) is False

    @pytest.mark.asyncio
    async def test_get_stats_connection_error(self, redis_svc_connected):
        import redis as _redis

        svc = redis_svc_connected
        svc._client.info = AsyncMock(side_effect=_redis.ConnectionError("err"))
        result = await svc.get_stats()
        assert result == {"connected": False}

    @pytest.mark.asyncio
    async def test_clear_pattern_connection_error(self, redis_svc_connected):
        import redis as _redis

        svc = redis_svc_connected

        async def mock_scan_iter(match=None):
            raise _redis.ConnectionError("err")
            yield  # noqa: make it an async generator

        svc._client.scan_iter = mock_scan_iter
        assert await svc.clear_pattern("player:*") == 0

    @pytest.mark.asyncio
    async def test_clear_all_success(self, redis_svc_connected):
        """clear_all with connected client clears all patterns."""
        svc = redis_svc_connected

        async def mock_scan_iter(match=None):
            return
            yield  # noqa: make it an async generator

        svc._client.scan_iter = mock_scan_iter
        result = await svc.clear_all()
        assert result is True

    @pytest.mark.asyncio
    async def test_clear_all_connection_error(self, redis_svc_connected):
        """clear_all catches ConnectionError from the pattern loop."""
        import redis as _redis

        svc = redis_svc_connected
        with patch.object(
            svc, "clear_pattern", side_effect=_redis.ConnectionError("err")
        ):
            assert await svc.clear_all() is False


# ---------------------------------------------------------------------------
# ImportError fallback for monitoring
# ---------------------------------------------------------------------------


class TestMonitoringImportFallback:
    def test_track_cache_operation_fallback(self):
        """The fallback track_cache_operation is a no-op."""
        from services.redis import track_cache_operation

        # Should not raise
        track_cache_operation("get", hit=True)
        track_cache_operation("set", hit=False)

    def test_import_error_defines_fallback(self):
        """When monitoring module is absent, the fallback is defined (lines 20-23)."""
        import importlib
        import sys

        with patch.dict(sys.modules, {"monitoring": None}):
            import services.redis as redis_mod

            importlib.reload(redis_mod)

            # The fallback should be a callable no-op
            result = redis_mod.track_cache_operation("get", hit=True)
            assert result is None

        # Reload to restore original state
        importlib.reload(redis_mod)
