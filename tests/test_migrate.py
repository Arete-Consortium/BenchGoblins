"""
Tests for the database migration runner (scripts/migrate.py).

Tests the pure logic — version extraction, ordering, discovery —
without requiring a real PostgreSQL database.
"""

import pytest

try:
    import psycopg  # noqa: F401
except ImportError:
    pytest.skip("psycopg not installed", allow_module_level=True)

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from scripts.migrate import (
    VERSION_RE,
    discover_migrations,
    get_applied_versions,
    main,
    run_migrations_async,
)


class TestVersionRegex:
    """Tests for migration filename version extraction."""

    def test_standard_filename(self):
        match = VERSION_RE.match("002_add_token_tracking.sql")
        assert match
        assert match.group(1) == "002"

    def test_three_digit_version(self):
        match = VERSION_RE.match("008_add_composite_indexes.sql")
        assert match
        assert match.group(1) == "008"

    def test_single_digit_version(self):
        match = VERSION_RE.match("1_initial.sql")
        assert match
        assert match.group(1) == "1"

    def test_non_sql_file_rejected(self):
        assert VERSION_RE.match("002_readme.md") is None

    def test_no_version_prefix_rejected(self):
        assert VERSION_RE.match("add_users.sql") is None

    def test_hidden_file_rejected(self):
        assert VERSION_RE.match(".002_hidden.sql") is None


class TestDiscoverMigrations:
    """Tests for migration file discovery and ordering."""

    def test_discovers_real_migrations(self):
        """Should find the actual migration files in data/migrations/."""
        migrations = discover_migrations()
        assert len(migrations) == 22
        # Should be sorted by version
        versions = [v for v, _ in migrations]
        assert versions == sorted(versions)
        assert versions[0] == 2
        assert versions[-1] == 23

    def test_migrations_are_sql_files(self):
        migrations = discover_migrations()
        for _, path in migrations:
            assert path.suffix == ".sql"
            assert path.exists()

    def test_returns_empty_for_missing_dir(self):
        with patch("scripts.migrate.MIGRATIONS_DIR", Path("/nonexistent")):
            assert discover_migrations() == []


class TestGetAppliedVersions:
    """Tests for reading applied versions from tracking table."""

    def test_returns_set_of_versions(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [(2,), (3,), (4,)]
        result = get_applied_versions(mock_conn)
        assert result == {2, 3, 4}

    def test_returns_empty_set_when_none_applied(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        result = get_applied_versions(mock_conn)
        assert result == set()


class TestMigrationFileContent:
    """Tests for migration file SQL validity."""

    def test_migration_006_uses_postgresql_syntax(self):
        """Migration 006 should use SERIAL, not AUTOINCREMENT."""
        migrations = discover_migrations()
        path_006 = next(p for v, p in migrations if v == 6)
        content = path_006.read_text()
        assert "AUTOINCREMENT" not in content
        assert "SERIAL" in content

    def test_migration_008_uses_concurrently(self):
        """Migration 008 should have CONCURRENTLY (runner strips it)."""
        migrations = discover_migrations()
        path_008 = next(p for v, p in migrations if v == 8)
        content = path_008.read_text()
        assert "CONCURRENTLY" in content

    def test_all_migrations_are_valid_utf8(self):
        for _, path in discover_migrations():
            path.read_text(encoding="utf-8")  # Should not raise


class TestMainCLI:
    """Tests for the CLI entry point."""

    @patch("scripts.migrate.get_connection_url")
    def test_dry_run_shows_pending(self, mock_url, capsys):
        """--dry-run should list pending migrations without connecting."""
        mock_url.return_value = "postgresql://localhost/test"

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("psycopg.connect", return_value=mock_conn):
            main(["--dry-run"])

        output = capsys.readouterr().out
        assert "Would apply" in output

    @patch("scripts.migrate.get_connection_url")
    def test_status_shows_all(self, mock_url, capsys):
        """--status should list all migrations with their status."""
        mock_url.return_value = "postgresql://localhost/test"

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchall.return_value = [(2,), (3,)]

        with patch("psycopg.connect", return_value=mock_conn):
            main(["--status"])

        output = capsys.readouterr().out
        assert "applied" in output
        assert "PENDING" in output

    @patch("scripts.migrate.get_connection_url")
    def test_all_applied_shows_message(self, mock_url, capsys):
        """When all migrations applied, show appropriate message."""
        mock_url.return_value = "postgresql://localhost/test"

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        # Return all versions as applied
        all_versions = [(v,) for v, _ in discover_migrations()]
        mock_conn.execute.return_value.fetchall.return_value = all_versions

        with patch("psycopg.connect", return_value=mock_conn):
            main([])

        output = capsys.readouterr().out
        assert "All migrations already applied" in output

    def test_missing_database_url_exits(self):
        """Should exit with error if DATABASE_URL not set."""
        with patch.dict("os.environ", {}, clear=True):
            # Remove DATABASE_URL if present
            os.environ.pop("DATABASE_URL", None)
            with pytest.raises(SystemExit):
                from scripts.migrate import get_connection_url

                get_connection_url()


class TestRunMigrationsAsync:
    """Tests for the async migration runner used in FastAPI lifespan."""

    def _make_mock_engine(self, applied_versions: list[int] | None = None):
        """Build a mock async engine with begin() context manager."""
        if applied_versions is None:
            applied_versions = []

        mock_conn = AsyncMock()
        # fetchall for SELECT version query
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(v,) for v in applied_versions]
        mock_conn.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_engine = MagicMock()
        mock_engine.begin = MagicMock(return_value=mock_ctx)
        return mock_engine, mock_conn

    def test_returns_zero_when_no_migration_files(self):
        """Should return 0 when migrations directory is empty/missing."""
        engine, _ = self._make_mock_engine()
        with patch("scripts.migrate.discover_migrations", return_value=[]):
            result = asyncio.get_event_loop().run_until_complete(
                run_migrations_async(engine)
            )
        assert result == 0

    def test_returns_zero_when_all_applied(self):
        """Should return 0 when all migrations are already tracked."""
        engine, _ = self._make_mock_engine(
            applied_versions=[
                2,
                3,
                4,
                5,
                6,
                7,
                8,
                9,
                10,
                11,
                12,
                13,
                14,
                15,
                16,
                17,
                18,
                19,
                20,
                21,
                22,
                23,
            ]
        )
        result = asyncio.get_event_loop().run_until_complete(
            run_migrations_async(engine)
        )
        assert result == 0

    def test_applies_pending_migrations(self, tmp_path):
        """Should apply only unapplied migrations and return count."""
        # Create two fake migration files
        m1 = tmp_path / "010_test_a.sql"
        m1.write_text("CREATE TABLE test_a (id INT);")
        m2 = tmp_path / "011_test_b.sql"
        m2.write_text("CREATE TABLE test_b (id INT);")

        fake_migrations = [(10, m1), (11, m2)]
        # Version 10 already applied
        engine, mock_conn = self._make_mock_engine(applied_versions=[10])

        with patch("scripts.migrate.discover_migrations", return_value=fake_migrations):
            result = asyncio.get_event_loop().run_until_complete(
                run_migrations_async(engine)
            )

        # Only migration 11 should be applied
        assert result == 1
        # engine.begin() called 3 times: tracking table, get applied, apply migration 11
        assert engine.begin.call_count == 3

    def test_creates_tracking_table(self):
        """Should execute CREATE TABLE IF NOT EXISTS for schema_migrations."""
        engine, mock_conn = self._make_mock_engine(
            applied_versions=[2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
        )

        asyncio.get_event_loop().run_until_complete(run_migrations_async(engine))

        # First call to execute should be CREATE TABLE
        first_call_sql = str(mock_conn.execute.call_args_list[0][0][0])
        assert "schema_migrations" in first_call_sql
        assert "CREATE TABLE IF NOT EXISTS" in first_call_sql

    def test_strips_concurrently_from_sql(self, tmp_path):
        """Should strip CONCURRENTLY keyword from migration SQL."""
        m1 = tmp_path / "020_with_concurrently.sql"
        m1.write_text("CREATE INDEX CONCURRENTLY idx_test ON test (id);")

        fake_migrations = [(20, m1)]
        engine, mock_conn = self._make_mock_engine(applied_versions=[])

        with patch("scripts.migrate.discover_migrations", return_value=fake_migrations):
            asyncio.get_event_loop().run_until_complete(run_migrations_async(engine))

        # Find the execute call that ran the migration SQL (not tracking table or SELECT)
        # The migration apply transaction is the third begin() call
        # Within it, first execute is the SQL, second is the INSERT
        migration_sql_call = mock_conn.execute.call_args_list[2]
        sql_text = str(migration_sql_call[0][0])
        assert "CONCURRENTLY" not in sql_text

    def test_records_applied_version(self, tmp_path):
        """Should INSERT into schema_migrations after applying."""
        m1 = tmp_path / "030_record_test.sql"
        m1.write_text("SELECT 1;")

        fake_migrations = [(30, m1)]
        engine, mock_conn = self._make_mock_engine(applied_versions=[])

        with patch("scripts.migrate.discover_migrations", return_value=fake_migrations):
            asyncio.get_event_loop().run_until_complete(run_migrations_async(engine))

        # The INSERT call should reference the version and filename
        insert_call = mock_conn.execute.call_args_list[3]
        insert_sql = str(insert_call[0][0])
        assert "INSERT INTO schema_migrations" in insert_sql
        params = insert_call[0][1]
        assert params["v"] == 30
        assert params["f"] == "030_record_test.sql"
