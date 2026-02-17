"""
Record Outcomes Background Job.

Runs daily to fetch actual game results from ESPN and record
outcomes for past decisions. This enables accuracy tracking.

Usage:
    # Run as a standalone script
    python -m jobs.record_outcomes

    # Or import and run programmatically
    from jobs.record_outcomes import run_daily_outcome_sync
    await run_daily_outcome_sync()

Scheduling:
    In production, schedule this job to run daily around 6 AM
    (after most games have completed and stats are finalized).

    Examples:
    - Cron: 0 6 * * * python -m jobs.record_outcomes
    - Railway/Fly.io: Use their scheduled job features
    - APScheduler: Add to FastAPI lifespan with background scheduler
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import date, timedelta

# Add parent directory to path for imports when running as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.database import db_service
from services.outcome_recorder import (
    record_outcomes_for_date,
    sync_recent_outcomes,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_daily_outcome_sync(
    days_back: int = 2,
    sport: str | None = None,
) -> dict:
    """
    Daily job to sync outcomes for recent decisions.

    Args:
        days_back: Number of days back to process (default 2)
        sport: Optional sport filter (nba, nfl, mlb, nhl)

    Returns:
        Summary dict with results
    """
    logger.info(f"Starting daily outcome sync (days_back={days_back}, sport={sport or 'all'})")

    try:
        result = await sync_recent_outcomes(days_back=days_back, sport=sport)

        logger.info(
            f"Outcome sync complete: "
            f"{result['total_decisions_processed']} decisions processed, "
            f"{result['total_outcomes_recorded']} outcomes recorded"
        )

        if result["errors"]:
            for error in result["errors"]:
                logger.warning(f"Sync error: {error}")

        return result

    except Exception as e:
        logger.error(f"Daily outcome sync failed: {e}")
        raise


async def run_backfill(start_date: date, end_date: date, sport: str | None = None) -> dict:
    """
    Backfill outcomes for a date range.

    Useful for initial setup or recovering from downtime.

    Args:
        start_date: Start of backfill range
        end_date: End of backfill range
        sport: Optional sport filter

    Returns:
        Summary dict with results
    """
    logger.info(f"Starting outcome backfill from {start_date} to {end_date}")

    total_processed = 0
    total_recorded = 0
    all_errors: list[str] = []

    current = start_date
    while current <= end_date:
        result = await record_outcomes_for_date(current, sport)
        total_processed += result.decisions_processed
        total_recorded += result.outcomes_recorded
        all_errors.extend(result.errors)

        logger.info(
            f"Date {current}: {result.decisions_processed} processed, "
            f"{result.outcomes_recorded} recorded"
        )
        current += timedelta(days=1)

    logger.info(
        f"Backfill complete: {total_processed} total processed, {total_recorded} total recorded"
    )

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "sport": sport or "all",
        "total_processed": total_processed,
        "total_recorded": total_recorded,
        "errors": all_errors,
    }


async def main():
    """Main entry point for running as a script."""
    import argparse

    parser = argparse.ArgumentParser(description="Record decision outcomes from ESPN box scores")
    parser.add_argument(
        "--days-back",
        type=int,
        default=2,
        help="Number of days back to process (default: 2)",
    )
    parser.add_argument(
        "--sport",
        type=str,
        choices=["nba", "nfl", "mlb", "nhl", "soccer"],
        default=None,
        help="Filter by sport (default: all)",
    )
    parser.add_argument(
        "--backfill-start",
        type=str,
        default=None,
        help="Start date for backfill (YYYY-MM-DD format)",
    )
    parser.add_argument(
        "--backfill-end",
        type=str,
        default=None,
        help="End date for backfill (YYYY-MM-DD format)",
    )

    args = parser.parse_args()

    # Initialize database connection
    if db_service.is_configured:
        await db_service.connect()
        logger.info("Database connected")
    else:
        logger.error("DATABASE_URL not configured")
        sys.exit(1)

    try:
        if args.backfill_start and args.backfill_end:
            # Run backfill mode
            start_date = date.fromisoformat(args.backfill_start)
            end_date = date.fromisoformat(args.backfill_end)
            result = await run_backfill(start_date, end_date, args.sport)
        else:
            # Run daily sync mode
            result = await run_daily_outcome_sync(
                days_back=args.days_back,
                sport=args.sport,
            )

        print(f"\nResults: {result}")

    finally:
        await db_service.disconnect()
        logger.info("Database disconnected")


if __name__ == "__main__":
    asyncio.run(main())
