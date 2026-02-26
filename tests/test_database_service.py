"""Tests for database service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.database import DatabaseService, get_db, get_session_context


@pytest.fixture
def svc():
    return DatabaseService(url="")


@pytest.fixture
def svc_configured():
    return DatabaseService(url="postgresql+asyncpg://localhost/test")


class TestDatabaseService:
    def test_not_configured(self, svc):
        assert svc.is_configured is False

    def test_configured(self, svc_configured):
        assert svc_configured.is_configured is True

    @pytest.mark.asyncio
    async def test_connect_no_url(self, svc):
        await svc.connect()
        assert svc._engine is None

    @pytest.mark.asyncio
    async def test_session_connection_fails(self, svc_configured):
        """Test that session() raises when executing query against invalid DB."""
        from sqlalchemy import text

        with pytest.raises(Exception):
            async with svc_configured.session() as session:
                await session.execute(text("SELECT 1"))

    @pytest.mark.asyncio
    async def test_get_session_not_connected(self, svc_configured):
        with pytest.raises(RuntimeError, match="Database not connected"):
            await svc_configured.get_session()

    @pytest.mark.asyncio
    async def test_disconnect_no_engine(self, svc):
        await svc.disconnect()  # Should not raise
        assert svc._engine is None


class TestDatabaseURLConversion:
    def test_postgres_prefix(self):
        """Test that postgres:// URLs are converted at module level."""
        svc = DatabaseService(url="postgresql+asyncpg://localhost/test")
        assert svc.is_configured is True

    def test_module_level_postgres_conversion(self):
        """Test module-level DATABASE_URL conversion logic."""
        import importlib

        with patch.dict(
            "os.environ",
            {"DATABASE_URL": "postgres://user:pass@host/db"},
        ):
            import services.database as db_mod

            importlib.reload(db_mod)
            assert db_mod.DATABASE_URL.startswith("postgresql+psycopg://")

        # Restore
        with patch.dict("os.environ", {"DATABASE_URL": ""}):
            importlib.reload(db_mod)

    def test_module_level_postgresql_conversion(self):
        """Test postgresql:// prefix is also converted."""
        import importlib

        with patch.dict(
            "os.environ",
            {"DATABASE_URL": "postgresql://user:pass@host/db"},
        ):
            import services.database as db_mod

            importlib.reload(db_mod)
            assert db_mod.DATABASE_URL.startswith("postgresql+psycopg://")

        with patch.dict("os.environ", {"DATABASE_URL": ""}):
            importlib.reload(db_mod)

    def test_module_level_railway_internal_ssl(self):
        """Railway internal URLs get sslmode=disable appended."""
        import importlib

        with patch.dict(
            "os.environ",
            {"DATABASE_URL": "postgres://user:pass@host.railway.internal/db"},
        ):
            import services.database as db_mod

            importlib.reload(db_mod)
            assert "sslmode=disable" in db_mod.DATABASE_URL
            assert db_mod.IS_RAILWAY_INTERNAL is True

        with patch.dict("os.environ", {"DATABASE_URL": ""}):
            importlib.reload(db_mod)

    def test_module_level_railway_internal_existing_params(self):
        """Railway internal URLs with existing query params use & separator."""
        import importlib

        with patch.dict(
            "os.environ",
            {
                "DATABASE_URL": "postgres://user:pass@host.railway.internal/db?timeout=30"
            },
        ):
            import services.database as db_mod

            importlib.reload(db_mod)
            assert "&sslmode=disable" in db_mod.DATABASE_URL

        with patch.dict("os.environ", {"DATABASE_URL": ""}):
            importlib.reload(db_mod)


class TestConnect:
    @pytest.mark.asyncio
    async def test_connect_creates_engine(self):
        """connect() creates engine and session factory."""
        svc = DatabaseService(url="postgresql+psycopg://localhost/test")
        mock_engine = MagicMock()
        mock_factory = MagicMock()

        with (
            patch(
                "services.database.create_async_engine", return_value=mock_engine
            ) as mock_create,
            patch("services.database.async_sessionmaker", return_value=mock_factory),
        ):
            await svc.connect()
            mock_create.assert_called_once()
            assert svc._engine is mock_engine
            assert svc._session_factory is mock_factory

    @pytest.mark.asyncio
    async def test_connect_already_connected(self):
        """connect() returns early when engine already exists."""
        svc = DatabaseService(url="postgresql+psycopg://localhost/test")
        svc._engine = MagicMock()  # Pretend already connected

        with patch("services.database.create_async_engine") as mock_create:
            await svc.connect()
            mock_create.assert_not_called()


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_disposes_engine(self):
        """disconnect() calls engine.dispose() and clears state."""
        svc = DatabaseService(url="postgresql+psycopg://localhost/test")
        mock_engine = AsyncMock()
        svc._engine = mock_engine
        svc._session_factory = MagicMock()

        await svc.disconnect()
        mock_engine.dispose.assert_called_once()
        assert svc._engine is None
        assert svc._session_factory is None


class TestSession:
    @pytest.mark.asyncio
    async def test_session_commit(self):
        """Successful session usage commits."""
        svc = DatabaseService(url="postgresql+psycopg://localhost/test")
        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_ctx
        svc._session_factory = mock_factory

        async with svc.session() as session:
            assert session is mock_session

        mock_session.commit.assert_called_once()
        mock_session.rollback.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_rollback_on_error(self):
        """Session rolls back on exception."""
        svc = DatabaseService(url="postgresql+psycopg://localhost/test")
        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_ctx
        svc._session_factory = mock_factory

        with pytest.raises(ValueError):
            async with svc.session() as _session:
                raise ValueError("test error")

        mock_session.rollback.assert_called_once()
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_runtime_error_no_factory(self):
        """session() raises RuntimeError when factory is None after connect."""
        svc = DatabaseService(url="")
        with pytest.raises(RuntimeError, match="Database not configured"):
            async with svc.session():
                pass


class TestGetSession:
    @pytest.mark.asyncio
    async def test_get_session_returns_factory_result(self):
        """get_session() returns factory() when connected."""
        svc = DatabaseService(url="postgresql+psycopg://localhost/test")
        mock_session = MagicMock()
        svc._session_factory = MagicMock(return_value=mock_session)

        result = await svc.get_session()
        assert result is mock_session


class TestGetDb:
    @pytest.mark.asyncio
    async def test_get_db_not_configured(self):
        """get_db() raises RuntimeError when DATABASE_URL not set."""
        with patch("services.database.db_service") as mock_svc:
            mock_svc.is_configured = False
            gen = get_db()
            with pytest.raises(RuntimeError, match="DATABASE_URL not configured"):
                await gen.__anext__()

    @pytest.mark.asyncio
    async def test_get_db_yields_session(self):
        """get_db() yields a session from db_service."""
        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("services.database.db_service") as mock_svc:
            mock_svc.is_configured = True
            mock_svc.session.return_value = mock_ctx
            gen = get_db()
            session = await gen.__anext__()
            assert session is mock_session


class TestGetSessionContext:
    @pytest.mark.asyncio
    async def test_get_session_context_yields_session(self):
        """get_session_context() yields session from db_service."""
        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("services.database.db_service") as mock_svc:
            mock_svc.session.return_value = mock_ctx
            async with get_session_context() as session:
                assert session is mock_session
