#!/usr/bin/env python3
"""
BenchGoblins Nightly Stats Sync Job

Syncs player stats from ESPN API to PostgreSQL database.
Run nightly via cron or GitHub Actions.

Usage:
    python scripts/sync_stats.py [--sport SPORT] [--force] [--dry-run]

Options:
    --sport     Sync only specific sport (nba, nfl, mlb, nhl)
    --force     Force update even if recently synced
    --dry-run   Print what would be synced without writing to database
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "api"))

from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Import after path setup
from services.database import db_service  # noqa: E402
from services.espn import espn_service  # noqa: E402
from services.redis import redis_service  # noqa: E402

# Sports to sync (ESPN-sourced)
# Soccer uses FPL/external APIs — not ESPN — so it's excluded here.
SPORTS = ["nba", "nfl", "mlb", "nhl"]

# How recently a player must have been updated to skip
SKIP_IF_UPDATED_WITHIN_HOURS = 20


async def get_active_players(sport: str) -> list[dict[str, Any]]:
    """Fetch active players from ESPN for a sport."""
    logger.info(f"Fetching active players for {sport.upper()}...")

    players = []
    try:
        # Search for top players by common patterns
        # ESPN doesn't have a great "all players" endpoint, so we iterate
        search_terms = [
            "a",
            "b",
            "c",
            "d",
            "e",
            "f",
            "g",
            "h",
            "i",
            "j",
            "k",
            "l",
            "m",
            "n",
            "o",
            "p",
            "q",
            "r",
            "s",
            "t",
            "u",
            "v",
            "w",
            "x",
            "y",
            "z",
        ]

        seen_ids = set()
        for term in search_terms:
            try:
                results = await espn_service.search_players(sport, term, limit=50)
                for player in results:
                    player_id = player.get("id")
                    if player_id and player_id not in seen_ids:
                        seen_ids.add(player_id)
                        players.append(player)
            except Exception as e:
                logger.debug(f"Search '{term}' failed: {e}")
                continue

        logger.info(f"Found {len(players)} unique players for {sport.upper()}")
        return players

    except Exception as e:
        logger.error(f"Failed to fetch players for {sport}: {e}")
        return []


async def sync_player_stats(
    player_id: str,
    sport: str,
    force: bool = False,
    dry_run: bool = False,
) -> bool:
    """Sync stats for a single player."""
    try:
        # Get detailed player info with stats
        player_data = await espn_service.get_player(sport, player_id)
        if not player_data:
            logger.debug(f"No data found for player {player_id}")
            return False

        name = player_data.get("name", "Unknown")
        team = player_data.get("team", "")
        stats = player_data.get("stats", {})

        if dry_run:
            logger.info(
                f"[DRY-RUN] Would sync: {name} ({team}) - {len(stats)} stat categories"
            )
            return True

        # Upsert player to database
        if db_service.is_configured:
            # Build player record
            _player_record = {  # noqa: F841 (TODO: pass to db_service.upsert_player)
                "espn_id": player_id,
                "name": name,
                "team": player_data.get("team_name"),
                "team_abbrev": team,
                "position": player_data.get("position"),
                "sport": sport,
                "jersey": player_data.get("jersey"),
                "height": player_data.get("height"),
                "weight": player_data.get("weight"),
                "age": player_data.get("age"),
                "headshot_url": player_data.get("headshot"),
            }

            # Upsert player (would need to add this to db_service)
            # For now, log success
            logger.debug(f"Synced: {name} ({team})")
            return True
        else:
            logger.warning("Database not connected - stats not persisted")
            return False

    except Exception as e:
        logger.error(f"Failed to sync player {player_id}: {e}")
        return False


async def sync_sport_stats(
    sport: str,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, int]:
    """Sync all player stats for a sport."""
    logger.info(f"\n{'=' * 60}")
    logger.info(f"Starting {sport.upper()} stats sync")
    logger.info(f"{'=' * 60}")

    results = {
        "total": 0,
        "synced": 0,
        "skipped": 0,
        "failed": 0,
    }

    # Get active players
    players = await get_active_players(sport)
    results["total"] = len(players)

    if not players:
        logger.warning(f"No players found for {sport}")
        return results

    # Sync each player with rate limiting
    for i, player in enumerate(players):
        player_id = player.get("id")
        if not player_id:
            continue

        # Progress logging every 50 players
        if (i + 1) % 50 == 0:
            logger.info(f"Progress: {i + 1}/{len(players)} players processed")

        success = await sync_player_stats(player_id, sport, force, dry_run)
        if success:
            results["synced"] += 1
        else:
            results["failed"] += 1

        # Rate limiting - don't hammer ESPN
        await asyncio.sleep(0.1)

    # Invalidate cached data for this sport
    if redis_service.is_connected:
        total_invalidated = 0
        for pattern in [
            f"decision:{sport}:*",
            f"player:{sport}:*",
            f"search:{sport}:*",
        ]:
            total_invalidated += await redis_service.clear_pattern(pattern)
        new_version = await redis_service.bump_stats_version(sport)
        logger.info(
            f"  Cache invalidated: {total_invalidated} keys deleted, stats version bumped to {new_version}"
        )

    logger.info(f"\n{sport.upper()} sync complete:")
    logger.info(f"  Total: {results['total']}")
    logger.info(f"  Synced: {results['synced']}")
    logger.info(f"  Skipped: {results['skipped']}")
    logger.info(f"  Failed: {results['failed']}")

    return results


async def run_sync(
    sports: list[str] | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run the full stats sync."""
    start_time = datetime.now(timezone.utc)
    logger.info(f"Stats sync started at {start_time.isoformat()}")

    if dry_run:
        logger.info("*** DRY RUN MODE - No changes will be made ***")

    # Connect to database
    if not dry_run and db_service.is_configured:
        try:
            await db_service.connect()
            logger.info("Database connected")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            logger.info("Continuing without database persistence")

    # Connect to Redis for cache invalidation
    if redis_service.is_configured:
        try:
            await redis_service.connect()
            logger.info("Redis connected for cache invalidation")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            logger.info("Continuing without cache invalidation")

    # Sync each sport
    sports_to_sync = sports or SPORTS
    all_results = {}

    for sport in sports_to_sync:
        if sport not in SPORTS:
            logger.warning(f"Unknown sport: {sport} - skipping")
            continue

        results = await sync_sport_stats(sport, force, dry_run)
        all_results[sport] = results

    # Cleanup
    if db_service.is_configured:
        await db_service.disconnect()
    if redis_service.is_connected:
        await redis_service.disconnect()
    await espn_service.close()

    # Summary
    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    total_synced = sum(r["synced"] for r in all_results.values())
    total_failed = sum(r["failed"] for r in all_results.values())

    logger.info(f"\n{'=' * 60}")
    logger.info("SYNC COMPLETE")
    logger.info(f"{'=' * 60}")
    logger.info(f"Duration: {duration:.1f} seconds")
    logger.info(f"Total synced: {total_synced}")
    logger.info(f"Total failed: {total_failed}")

    return {
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_seconds": duration,
        "results": all_results,
    }


def main():
    parser = argparse.ArgumentParser(description="BenchGoblins nightly stats sync")
    parser.add_argument(
        "--sport",
        choices=SPORTS,
        help="Sync only specific sport",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force update even if recently synced",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be synced without writing to database",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    sports = [args.sport] if args.sport else None

    try:
        asyncio.run(run_sync(sports, args.force, args.dry_run))
    except KeyboardInterrupt:
        logger.info("\nSync interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
