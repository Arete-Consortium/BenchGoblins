"""
Outcome Recorder Service — Fetches ESPN box scores and records decision outcomes.

Automatically tracks decision accuracy by fetching actual fantasy points
from completed games and comparing against predictions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, update

from models.database import Decision
from services.database import db_service
from services.espn import espn_service


@dataclass
class PlayerGameResult:
    """Fantasy points result for a single player in a game."""

    player_name: str
    espn_id: str
    team: str
    game_date: date
    fantasy_points: float
    sport: str


@dataclass
class OutcomeRecordResult:
    """Result of recording outcomes for a date."""

    date: date
    sport: str
    decisions_processed: int
    outcomes_recorded: int
    errors: list[str]


def _calculate_nba_fantasy_points(game_log: dict) -> float:
    """
    Calculate standard NBA fantasy points from game log.

    Standard scoring: 1 pt per point, 1.2 per rebound, 1.5 per assist,
    3 per steal, 3 per block, -1 per turnover.
    """
    pts = game_log.get("points", 0)
    reb = game_log.get("rebounds", 0)
    ast = game_log.get("assists", 0)
    stl = game_log.get("steals", 0)
    blk = game_log.get("blocks", 0)
    to = game_log.get("turnovers", 0)

    return pts * 1.0 + reb * 1.2 + ast * 1.5 + stl * 3.0 + blk * 3.0 - to * 1.0


def _calculate_nfl_fantasy_points(game_log: dict, scoring: str = "ppr") -> float:
    """
    Calculate NFL fantasy points from game log.

    PPR scoring by default.
    """
    pass_yds = game_log.get("pass_yards", 0)
    pass_tds = game_log.get("pass_tds", 0)
    pass_ints = game_log.get("pass_ints", 0)
    rush_yds = game_log.get("rush_yards", 0)
    rush_tds = game_log.get("rush_tds", 0)
    rec = game_log.get("receptions", 0)
    rec_yds = game_log.get("receiving_yards", 0)
    rec_tds = game_log.get("receiving_tds", 0)

    points = 0.0
    # Passing
    points += pass_yds * 0.04  # 1 pt per 25 yards
    points += pass_tds * 4.0
    points -= pass_ints * 2.0
    # Rushing
    points += rush_yds * 0.1  # 1 pt per 10 yards
    points += rush_tds * 6.0
    # Receiving
    if scoring == "ppr":
        points += rec * 1.0
    elif scoring == "half_ppr":
        points += rec * 0.5
    points += rec_yds * 0.1
    points += rec_tds * 6.0

    return points


def _calculate_mlb_fantasy_points(game_log: dict) -> float:
    """
    Calculate standard MLB fantasy points from game log.

    Standard scoring for hitters: 3 per hit, 6 per HR, 2 per RBI, 2 per run, 5 per SB.
    """
    hits = game_log.get("hits", 0)
    hr = game_log.get("home_runs", 0)
    rbis = game_log.get("rbis", 0)
    sb = game_log.get("stolen_bases", 0)

    return hits * 3.0 + hr * 6.0 + rbis * 2.0 + sb * 5.0


def _calculate_nhl_fantasy_points(game_log: dict) -> float:
    """
    Calculate standard NHL fantasy points from game log.

    Standard scoring: 3 per goal, 2 per assist, 0.5 per shot.
    """
    goals = game_log.get("goals", 0)
    assists = game_log.get("assists", 0)
    shots = game_log.get("shots", 0)

    return goals * 3.0 + assists * 2.0 + shots * 0.5


def calculate_fantasy_points(game_log: dict, sport: str) -> float:
    """Calculate fantasy points from a game log based on sport."""
    if sport == "nba":
        return _calculate_nba_fantasy_points(game_log)
    elif sport == "nfl":
        return _calculate_nfl_fantasy_points(game_log)
    elif sport == "mlb":
        return _calculate_mlb_fantasy_points(game_log)
    elif sport == "nhl":
        return _calculate_nhl_fantasy_points(game_log)
    return 0.0


async def fetch_player_game_result(
    player_name: str,
    sport: str,
    target_date: date,
) -> PlayerGameResult | None:
    """
    Fetch a player's fantasy points for a specific game date.

    Uses ESPN's find_player_by_name and get_player_game_logs to find results.
    """
    # Find the player
    player_data = await espn_service.find_player_by_name(player_name, sport)
    if not player_data:
        return None

    player_info, _ = player_data

    # Get recent game logs
    game_logs = await espn_service.get_player_game_logs(player_info.id, sport, limit=10)
    if not game_logs:
        return None

    # Find the game matching the target date
    for log in game_logs:
        log_date_str = log.get("date", "")
        if not log_date_str:
            continue

        # Parse the date (ESPN returns ISO format)
        try:
            # Handle both "2024-01-15" and "2024-01-15T00:00:00Z" formats
            log_date = datetime.fromisoformat(log_date_str.replace("Z", "+00:00")).date()
        except (ValueError, TypeError):
            continue

        if log_date == target_date:
            fantasy_pts = calculate_fantasy_points(log, sport)
            return PlayerGameResult(
                player_name=player_info.name,
                espn_id=player_info.id,
                team=player_info.team_abbrev,
                game_date=target_date,
                fantasy_points=fantasy_pts,
                sport=sport,
            )

    return None


async def fetch_game_results(target_date: date, sport: str) -> list[PlayerGameResult]:
    """
    Fetch all player game results for a given date and sport.

    Note: This is a placeholder. In production, you would use ESPN's
    scoreboard API to get all games for a date and then fetch box scores.
    For now, this fetches results on-demand per player.
    """
    # This function exists for API symmetry but actual fetching
    # happens per-player in match_decision_to_outcome
    return []


def _normalize_player_name(name: str | None) -> str:
    """Normalize player name for matching."""
    if not name:
        return ""
    # Lowercase, remove common suffixes, strip whitespace
    normalized = name.lower().strip()
    # Process longer suffixes first to avoid partial matches (e.g., " iii" before " ii")
    for suffix in [" jr.", " jr", " sr.", " sr", " iii", " ii", " iv"]:
        normalized = normalized.replace(suffix, "")
    return normalized


def _names_match(name1: str | None, name2: str | None) -> bool:
    """Check if two player names match (fuzzy)."""
    n1 = _normalize_player_name(name1)
    n2 = _normalize_player_name(name2)

    if not n1 or not n2:
        return False

    # Exact match
    if n1 == n2:
        return True

    # One contains the other (handles "LeBron James" vs "LeBron")
    if n1 in n2 or n2 in n1:
        return True

    # Check last name match
    parts1 = n1.split()
    parts2 = n2.split()
    if len(parts1) >= 2 and len(parts2) >= 2:
        if parts1[-1] == parts2[-1]:  # Last names match
            # Check first initial
            if parts1[0][0] == parts2[0][0]:
                return True

    return False


async def match_decision_to_outcome(
    decision: Decision,
) -> tuple[float | None, float | None]:
    """
    Match a decision to actual game results.

    Returns (points_a, points_b) or (None, None) if results not found.
    """
    if not decision.player_a_name and not decision.player_b_name:
        return None, None

    # Get the game date (decision date or 1-2 days after)
    decision_date = decision.created_at.date() if decision.created_at else None
    if not decision_date:
        return None, None

    points_a = None
    points_b = None

    # Try to fetch results for player A
    if decision.player_a_name:
        # Check same day and next day (games might be evening)
        for offset in [0, 1]:
            target_date = decision_date + timedelta(days=offset)
            result = await fetch_player_game_result(
                decision.player_a_name,
                decision.sport,
                target_date,
            )
            if result:
                points_a = result.fantasy_points
                break

    # Try to fetch results for player B
    if decision.player_b_name:
        for offset in [0, 1]:
            target_date = decision_date + timedelta(days=offset)
            result = await fetch_player_game_result(
                decision.player_b_name,
                decision.sport,
                target_date,
            )
            if result:
                points_b = result.fantasy_points
                break

    return points_a, points_b


def determine_outcome(
    decision: Decision,
    actual_points_a: float | None,
    actual_points_b: float | None,
) -> str | None:
    """
    Determine if the decision was correct based on actual points.

    Returns "correct", "incorrect", "push", or None if can't determine.
    """
    if actual_points_a is None or actual_points_b is None:
        return None

    # Figure out which player was recommended
    # The decision text typically says "Start Player X" or recommends one player
    decision_text = decision.decision.lower() if decision.decision else ""
    player_a_name = (decision.player_a_name or "").lower()
    player_b_name = (decision.player_b_name or "").lower()

    # Determine who was recommended
    recommended_a = True  # Default to player A
    if player_b_name and player_b_name in decision_text:
        if player_a_name not in decision_text:
            recommended_a = False
        elif decision_text.index(player_b_name) < decision_text.index(player_a_name):
            # Player B mentioned first in "Start X" recommendation
            recommended_a = False

    # Push if within 1 point
    margin = abs(actual_points_a - actual_points_b)
    if margin < 1.0:
        return "push"

    # Check if recommendation was correct
    if recommended_a:
        return "correct" if actual_points_a > actual_points_b else "incorrect"
    else:
        return "correct" if actual_points_b > actual_points_a else "incorrect"


async def record_outcomes_for_date(
    target_date: date,
    sport: str | None = None,
) -> OutcomeRecordResult:
    """
    Record outcomes for all decisions from a given date.

    Fetches actual fantasy points from ESPN and updates decision records.

    Args:
        target_date: The date of decisions to process
        sport: Optional sport filter (nba, nfl, mlb, nhl)

    Returns:
        OutcomeRecordResult with counts and any errors
    """
    if not db_service.is_configured:
        return OutcomeRecordResult(
            date=target_date,
            sport=sport or "all",
            decisions_processed=0,
            outcomes_recorded=0,
            errors=["Database not configured"],
        )

    errors: list[str] = []
    decisions_processed = 0
    outcomes_recorded = 0

    try:
        async with db_service.session() as session:
            # Query decisions from the target date without outcomes
            start_of_day = datetime.combine(target_date, datetime.min.time())
            end_of_day = datetime.combine(target_date, datetime.max.time())

            query = (
                select(Decision)
                .where(Decision.created_at >= start_of_day)
                .where(Decision.created_at <= end_of_day)
                .where(Decision.actual_outcome.is_(None))
            )

            if sport:
                query = query.where(Decision.sport == sport)

            result = await session.execute(query)
            decisions = result.scalars().all()
            decisions_processed = len(decisions)

            for decision in decisions:
                try:
                    # Fetch actual points
                    points_a, points_b = await match_decision_to_outcome(decision)

                    if points_a is None and points_b is None:
                        continue

                    # Determine outcome
                    outcome = determine_outcome(decision, points_a, points_b)

                    # Update the decision record
                    stmt = (
                        update(Decision)
                        .where(Decision.id == decision.id)
                        .values(
                            actual_points_a=Decimal(str(points_a))
                            if points_a is not None
                            else None,
                            actual_points_b=Decimal(str(points_b))
                            if points_b is not None
                            else None,
                            actual_outcome=outcome,
                            feedback_at=datetime.now(UTC),
                        )
                    )
                    await session.execute(stmt)
                    outcomes_recorded += 1

                except Exception as e:
                    errors.append(f"Error processing decision {decision.id}: {str(e)}")

    except Exception as e:
        errors.append(f"Database error: {str(e)}")

    return OutcomeRecordResult(
        date=target_date,
        sport=sport or "all",
        decisions_processed=decisions_processed,
        outcomes_recorded=outcomes_recorded,
        errors=errors,
    )


async def record_outcomes_for_date_range(
    start_date: date,
    end_date: date,
    sport: str | None = None,
) -> list[OutcomeRecordResult]:
    """
    Record outcomes for decisions across a date range.

    Args:
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)
        sport: Optional sport filter

    Returns:
        List of OutcomeRecordResult for each date
    """
    results = []
    current = start_date

    while current <= end_date:
        result = await record_outcomes_for_date(current, sport)
        results.append(result)
        current += timedelta(days=1)

    return results


async def sync_recent_outcomes(days_back: int = 2, sport: str | None = None) -> dict:
    """
    Sync outcomes for recent decisions (convenience method).

    Args:
        days_back: Number of days back to process (default 2 for completed games)
        sport: Optional sport filter

    Returns:
        Summary dict with total counts
    """
    today = date.today()
    start_date = today - timedelta(days=days_back)
    end_date = today - timedelta(days=1)  # Don't process today (games may not be complete)

    results = await record_outcomes_for_date_range(start_date, end_date, sport)

    total_processed = sum(r.decisions_processed for r in results)
    total_recorded = sum(r.outcomes_recorded for r in results)
    all_errors = []
    for r in results:
        all_errors.extend(r.errors)

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "sport": sport or "all",
        "total_decisions_processed": total_processed,
        "total_outcomes_recorded": total_recorded,
        "errors": all_errors,
        "daily_results": [
            {
                "date": r.date.isoformat(),
                "processed": r.decisions_processed,
                "recorded": r.outcomes_recorded,
            }
            for r in results
        ],
    }
