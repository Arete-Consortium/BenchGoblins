"""
Tests for the database migration runner (scripts/migrate.py).

Tests the pure logic — version extraction, ordering, discovery —
without requiring a real PostgreSQL database.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.migrate import (
    VERSION_RE,
    discover_migrations,
    get_applied_versions,
    main,
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
        assert len(migrations) == 7
        # Should be sorted by version
        versions = [v for v, _ in migrations]
        assert versions == sorted(versions)
        assert versions[0] == 2
        assert versions[-1] == 8

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
