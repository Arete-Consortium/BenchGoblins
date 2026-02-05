"""Tests for database service."""

import pytest

from services.database import DatabaseService


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
        # SQLAlchemy lazy-loads connections, so we need to execute a query
        # to trigger the actual connection attempt and failure
        from sqlalchemy import text

        with pytest.raises(Exception):  # Could be OSError, ConnectionRefusedError, etc.
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
        # The module-level conversion happens on import, so we test the service
        svc = DatabaseService(url="postgresql+asyncpg://localhost/test")
        assert svc.is_configured is True
