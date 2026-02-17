"""
Database Service — Async PostgreSQL session management.

Provides async database sessions using SQLAlchemy 2.0 with psycopg (psycopg3).
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Database URL from environment — remove all embedded whitespace (newlines, spaces)
# that Railway env var references can sometimes inject.
import re

DATABASE_URL = re.sub(r"\s+", "", os.getenv("DATABASE_URL", ""))

# Detect Railway internal connection - needs SSL disabled
IS_RAILWAY_INTERNAL = DATABASE_URL and ".railway.internal" in DATABASE_URL

# Convert to appropriate SQLAlchemy URL
# For internal Railway: use psycopg with sslmode=disable
# For external/public: use psycopg with SSL
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

    # For Railway internal, add sslmode=disable
    if IS_RAILWAY_INTERNAL:
        if "?" in DATABASE_URL:
            DATABASE_URL = DATABASE_URL + "&sslmode=disable"
        else:
            DATABASE_URL = DATABASE_URL + "?sslmode=disable"
        print("[DB] Using internal Railway URL with sslmode=disable")


class DatabaseService:
    """Async database session management."""

    def __init__(self, url: str | None = None):
        self._url = url or DATABASE_URL
        self._engine = None
        self._session_factory = None

    @property
    def is_configured(self) -> bool:
        """Check if database URL is configured."""
        return bool(self._url)

    async def connect(self) -> None:
        """Initialize database connection pool."""
        if not self._url:
            return

        if self._engine is not None:
            return  # Already connected

        print(f"[DB] Connecting with URL prefix: {self._url[:50]}...")

        self._engine = create_async_engine(
            self._url,
            poolclass=NullPool,  # Better for async in web contexts
            echo=os.getenv("DB_ECHO", "false").lower() == "true",
        )
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def disconnect(self) -> None:
        """Close database connection pool."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get an async database session.

        Usage:
            async with db.session() as session:
                result = await session.execute(...)
        """
        # Lazy connect if not yet connected
        if not self._session_factory:
            await self.connect()
        if not self._session_factory:
            raise RuntimeError("Database not configured or connection failed.")

        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def get_session(self) -> AsyncSession:
        """
        Get a raw session (for dependency injection).

        Caller is responsible for committing/rolling back.
        """
        if not self._session_factory:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._session_factory()


# Singleton instance
db_service = DatabaseService()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database sessions.

    Usage in routes:
        @app.get("/")
        async def read_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(...)
    """
    if not db_service.is_configured:
        raise RuntimeError("DATABASE_URL not configured")

    async with db_service.session() as session:
        yield session


# Optional: Direct session context for scripts/testing
@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for scripts and tests.

    Usage:
        async with get_session_context() as session:
            ...
    """
    async with db_service.session() as session:
        yield session
