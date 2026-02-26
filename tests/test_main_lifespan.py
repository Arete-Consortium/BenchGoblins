"""Tests for main.py lifespan, Sentry init, and WebhookTestRequest validator.

Covers lines 95-103 (Sentry), 130-203 (lifespan), and 2387 (webhook None).
"""

import importlib
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_migrate(return_value=0):
    """Inject a mock ``scripts.migrate`` module so the lazy import works."""
    mock_fn = AsyncMock(return_value=return_value)
    mod = types.ModuleType("scripts.migrate")
    mod.run_migrations_async = mock_fn  # type: ignore[attr-defined]
    return mod, mock_fn


def _lifespan_patches(
    *,
    claude_available=True,
    db_configured=True,
    redis_configured=True,
    redis_connected=True,
    db_connect_side_effect=None,
    redis_connect_side_effect=None,
    env="development",
    migrations_return=0,
):
    """Build the common patch stack for lifespan tests.

    Returns (context_manager, mocks_dict).
    """
    from contextlib import ExitStack

    mock_engine = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_conn.run_sync = AsyncMock()
    mock_begin_ctx = MagicMock()
    mock_begin_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_begin_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_engine.begin.return_value = mock_begin_ctx

    mock_migrate_mod, mock_migrate_fn = _make_mock_migrate(migrations_return)

    mocks = {
        "engine": mock_engine,
        "migrate_fn": mock_migrate_fn,
    }

    stack = ExitStack()

    stack.enter_context(patch("api.main.setup_logging"))
    stack.enter_context(patch.dict(os.environ, {"ENVIRONMENT": env}))
    stack.enter_context(patch.dict(sys.modules, {"scripts.migrate": mock_migrate_mod}))

    m_claude = stack.enter_context(patch("api.main.claude_service"))
    m_claude.is_available = claude_available

    m_db = stack.enter_context(patch("api.main.db_service"))
    m_db.is_configured = db_configured
    m_db.connect = AsyncMock(side_effect=db_connect_side_effect)
    m_db._engine = mock_engine
    m_db.disconnect = AsyncMock()

    m_redis = stack.enter_context(patch("api.main.redis_service"))
    m_redis.is_configured = redis_configured
    m_redis.is_connected = redis_connected
    m_redis.connect = AsyncMock(side_effect=redis_connect_side_effect)
    m_redis._client = MagicMock() if redis_connected else None
    m_redis.disconnect = AsyncMock()

    m_scheduler = stack.enter_context(patch("api.main.notification_scheduler"))
    m_scheduler.start = AsyncMock()
    m_scheduler.stop = AsyncMock()

    for svc_name in (
        "espn_service",
        "espn_fantasy_service",
        "sleeper_service",
        "yahoo_service",
        "notification_service",
    ):
        m = stack.enter_context(patch(f"api.main.{svc_name}"))
        m.close = AsyncMock()
        mocks[svc_name] = m

    mocks["db"] = m_db
    mocks["redis"] = m_redis
    mocks["scheduler"] = m_scheduler
    mocks["claude"] = m_claude

    return stack, mocks


# ---------------------------------------------------------------------------
# Line 2387: WebhookTestRequest.check_webhook_url when result is None
# ---------------------------------------------------------------------------


class TestWebhookCheckNoneResult:
    """WebhookTestRequest.check_webhook_url raises when _validate_webhook_url returns None."""

    def test_check_webhook_url_raises_when_validate_returns_none(self):
        from api.main import WebhookTestRequest

        with patch("api.main._validate_webhook_url", return_value=None):
            with pytest.raises(ValueError, match="Webhook URL is required"):
                WebhookTestRequest.check_webhook_url("")


# ---------------------------------------------------------------------------
# Lines 95-103: Sentry SDK initialization
# ---------------------------------------------------------------------------


class TestSentryInit:
    """Module-level Sentry init block (lines 95-103)."""

    def test_sentry_init_called_when_dsn_set(self):
        """Reload the module with SENTRY_DSN set to trigger sentry_sdk.init."""
        import api.main as main_module

        with (
            patch.dict(
                os.environ,
                {"SENTRY_DSN": "https://examplePublicKey@o0.ingest.sentry.io/0"},
            ),
            patch("sentry_sdk.init") as mock_init,
        ):
            importlib.reload(main_module)
            mock_init.assert_called_once()
            call_kwargs = mock_init.call_args[1]
            assert (
                call_kwargs["dsn"] == "https://examplePublicKey@o0.ingest.sentry.io/0"
            )
            assert call_kwargs["traces_sample_rate"] == 0.1
            assert call_kwargs["send_default_pii"] is False

        # Reload again without DSN to restore clean state
        with patch.dict(os.environ, {"SENTRY_DSN": ""}, clear=False):
            importlib.reload(main_module)


# ---------------------------------------------------------------------------
# Lines 130-203: lifespan async context manager
# ---------------------------------------------------------------------------


class TestLifespan:
    """Test the lifespan() async context manager directly."""

    @pytest.mark.asyncio
    async def test_lifespan_full_startup_and_shutdown(self):
        """Happy path: all services configured and connected."""
        from api.main import lifespan

        stack, mocks = _lifespan_patches(migrations_return=3)
        with stack:
            async with lifespan(MagicMock()):
                pass

            mocks["db"].connect.assert_called_once()
            mocks["redis"].connect.assert_called_once()
            mocks["scheduler"].start.assert_called_once()
            mocks["migrate_fn"].assert_called_once()

            # Shutdown
            mocks["scheduler"].stop.assert_called_once()
            mocks["espn_service"].close.assert_called_once()
            mocks["db"].disconnect.assert_called_once()
            mocks["redis"].disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_claude_not_available(self):
        """Claude not configured — logs warning."""
        from api.main import lifespan

        stack, mocks = _lifespan_patches(
            claude_available=False,
            db_configured=False,
            redis_configured=False,
            redis_connected=False,
        )
        with stack:
            async with lifespan(MagicMock()):
                pass

            mocks["db"].connect.assert_not_called()
            mocks["redis"].connect.assert_not_called()
            mocks["scheduler"].start.assert_not_called()

    @pytest.mark.asyncio
    async def test_lifespan_db_connection_failure(self):
        """DB connect fails — should log warning and continue."""
        from api.main import lifespan

        stack, _ = _lifespan_patches(
            db_connect_side_effect=Exception("connection refused"),
            redis_configured=False,
            redis_connected=False,
        )
        with stack:
            async with lifespan(MagicMock()):
                pass

    @pytest.mark.asyncio
    async def test_lifespan_redis_connection_failure(self):
        """Redis connect fails — should log warning and continue."""
        from api.main import lifespan

        stack, _ = _lifespan_patches(
            redis_connect_side_effect=Exception("Redis down"),
            redis_connected=False,
        )
        with stack:
            async with lifespan(MagicMock()):
                pass

    @pytest.mark.asyncio
    async def test_lifespan_production_validate_env(self):
        """Production environment triggers _validate_production_env."""
        from api.main import lifespan

        stack, _ = _lifespan_patches(
            claude_available=False,
            db_configured=False,
            redis_configured=False,
            redis_connected=False,
            env="production",
        )
        with stack:
            with patch("api.main._validate_production_env") as mock_validate:
                async with lifespan(MagicMock()):
                    pass
                mock_validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_redis_connected_sets_blacklist(self):
        """Redis connected + has client → set_blacklist_redis called."""
        from api.main import lifespan

        stack, mocks = _lifespan_patches()
        mock_redis_client = MagicMock()
        with stack:
            mocks["redis"]._client = mock_redis_client
            with patch("services.auth.set_blacklist_redis") as mock_set_bl:
                async with lifespan(MagicMock()):
                    pass
                mock_set_bl.assert_called_once_with(mock_redis_client)

    @pytest.mark.asyncio
    async def test_lifespan_no_migrations_applied(self):
        """Migrations return 0 — no migration log message."""
        from api.main import lifespan

        stack, _ = _lifespan_patches(
            migrations_return=0,
            redis_configured=False,
            redis_connected=False,
        )
        with stack:
            async with lifespan(MagicMock()):
                pass

    @pytest.mark.asyncio
    async def test_lifespan_scheduler_skipped_no_redis(self):
        """Scheduler skipped when DB configured but Redis not connected."""
        from api.main import lifespan

        stack, mocks = _lifespan_patches(
            redis_configured=True,
            redis_connected=False,
            redis_connect_side_effect=Exception("Redis down"),
        )
        with stack:
            async with lifespan(MagicMock()):
                pass
            mocks["scheduler"].start.assert_not_called()
