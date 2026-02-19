#!/usr/bin/env python3
"""
Database migration runner for BenchGoblins.

Tracks applied migrations in a `schema_migrations` table and applies
pending SQL files from data/migrations/ in version order.

Usage:
    python scripts/migrate.py              # Apply pending migrations
    python scripts/migrate.py --status     # Show migration status
    python scripts/migrate.py --dry-run    # Show what would be applied

Requires DATABASE_URL environment variable.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).parent.parent / "data" / "migrations"

# Match filenames like 002_add_token_tracking.sql
VERSION_RE = re.compile(r"^(\d+)_.*\.sql$")


def get_connection_url() -> str:
    """Get PostgreSQL connection URL from environment."""
    url = os.getenv("DATABASE_URL", "")
    if not url:
        print("ERROR: DATABASE_URL environment variable not set", file=sys.stderr)
        sys.exit(1)
    # Normalize to psycopg-compatible URL
    url = re.sub(r"\s+", "", url)
    if url.startswith("postgresql+psycopg://"):
        url = url.replace("postgresql+psycopg://", "postgresql://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def discover_migrations() -> list[tuple[int, Path]]:
    """Discover and sort migration files by version number."""
    migrations = []
    if not MIGRATIONS_DIR.exists():
        return migrations

    for path in MIGRATIONS_DIR.iterdir():
        match = VERSION_RE.match(path.name)
        if match:
            version = int(match.group(1))
            migrations.append((version, path))

    return sorted(migrations, key=lambda x: x[0])


def ensure_tracking_table(conn: psycopg.Connection) -> None:
    """Create schema_migrations table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            filename TEXT NOT NULL,
            applied_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.commit()


def get_applied_versions(conn: psycopg.Connection) -> set[int]:
    """Get set of already-applied migration versions."""
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row[0] for row in rows}


def apply_migration(conn: psycopg.Connection, version: int, path: Path) -> None:
    """Apply a single migration file."""
    sql = path.read_text()

    # Strip CONCURRENTLY — can't run inside a transaction, and IF NOT EXISTS
    # makes re-running safe anyway
    sql = sql.replace(" CONCURRENTLY ", " ")

    # Execute the migration SQL
    conn.execute(sql)

    # Record it in the tracking table
    conn.execute(
        "INSERT INTO schema_migrations (version, filename) VALUES (%s, %s)",
        (version, path.name),
    )
    conn.commit()


async def run_migrations_async(engine) -> int:
    """
    Run pending migrations using a SQLAlchemy async engine.

    Called from the FastAPI lifespan after Base.metadata.create_all().
    Returns the number of migrations applied.
    """
    import logging

    from sqlalchemy import text as sa_text

    _logger = logging.getLogger(__name__)

    all_migrations = discover_migrations()
    if not all_migrations:
        _logger.info("No migration files found")
        return 0

    # Ensure tracking table exists
    async with engine.begin() as conn:
        await conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                filename TEXT NOT NULL,
                applied_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))

    # Get already-applied versions
    async with engine.begin() as conn:
        result = await conn.execute(sa_text("SELECT version FROM schema_migrations"))
        applied = {row[0] for row in result.fetchall()}

    pending = [(v, p) for v, p in all_migrations if v not in applied]
    if not pending:
        _logger.info("All %d migrations already applied", len(applied))
        return 0

    # Apply each pending migration in its own transaction
    for version, path in pending:
        sql = path.read_text()
        # Strip CONCURRENTLY — can't run inside a transaction
        sql = sql.replace(" CONCURRENTLY ", " ")

        async with engine.begin() as conn:
            await conn.execute(sa_text(sql))
            await conn.execute(
                sa_text(
                    "INSERT INTO schema_migrations (version, filename) VALUES (:v, :f)"
                ),
                {"v": version, "f": path.name},
            )
        _logger.info("Applied migration %d: %s", version, path.name)

    _logger.info("%d migration(s) applied successfully", len(pending))
    return len(pending)


def show_status(conn: psycopg.Connection) -> None:
    """Show status of all migrations."""
    all_migrations = discover_migrations()
    applied = get_applied_versions(conn)

    if not all_migrations:
        print("No migration files found.")
        return

    print(f"{'Version':<10} {'Status':<12} {'Filename'}")
    print("-" * 60)
    for version, path in all_migrations:
        status = "applied" if version in applied else "PENDING"
        print(f"{version:<10} {status:<12} {path.name}")

    pending = [v for v, _ in all_migrations if v not in applied]
    print(f"\n{len(applied)} applied, {len(pending)} pending")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="BenchGoblins database migration runner"
    )
    parser.add_argument("--status", action="store_true", help="Show migration status")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be applied"
    )
    args = parser.parse_args(argv)

    url = get_connection_url()
    all_migrations = discover_migrations()

    if not all_migrations:
        print("No migration files found in", MIGRATIONS_DIR)
        return

    with psycopg.connect(url) as conn:
        ensure_tracking_table(conn)

        if args.status:
            show_status(conn)
            return

        applied = get_applied_versions(conn)
        pending = [(v, p) for v, p in all_migrations if v not in applied]

        if not pending:
            print("All migrations already applied.")
            return

        if args.dry_run:
            print("Would apply the following migrations:")
            for version, path in pending:
                print(f"  {version}: {path.name}")
            return

        for version, path in pending:
            print(f"Applying {version}: {path.name}...", end=" ")
            try:
                apply_migration(conn, version, path)
                print("OK")
            except Exception as e:
                print(f"FAILED: {e}")
                sys.exit(1)

        print(f"\n{len(pending)} migration(s) applied successfully.")


if __name__ == "__main__":
    main()
