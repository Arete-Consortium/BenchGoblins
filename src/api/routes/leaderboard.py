"""
Leaderboard API Routes.

Top players by position using BenchGoblins five-index scoring system.
Supports filtering by sport, position, and risk mode (floor/median/ceiling).
Includes trending movers (7-day score delta) and decision accuracy leaders.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import Numeric, case, func, select
from sqlalchemy.exc import SQLAlchemyError

from models.database import Decision, Player, PlayerIndex
from services.database import db_service
from services.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leaderboard", tags=["Leaderboard"])

# Valid positions per sport
POSITIONS: dict[str, list[str]] = {
    "nfl": ["QB", "RB", "WR", "TE", "K", "DEF"],
    "nba": ["PG", "SG", "SF", "PF", "C"],
    "mlb": ["SP", "RP", "C", "1B", "2B", "3B", "SS", "OF", "DH"],
    "nhl": ["C", "LW", "RW", "D", "G"],
    "soccer": ["GK", "DEF", "MID", "FWD"],
}

VALID_SPORTS = {"nba", "nfl", "mlb", "nhl", "soccer"}
VALID_MODES = {"floor", "median", "ceiling"}


# -------------------------------------------------------------------------
# Response Models
# -------------------------------------------------------------------------


class LeaderboardPlayer(BaseModel):
    """A player entry on the leaderboard."""

    rank: int
    player_id: str
    name: str
    team: str | None = None
    position: str | None = None
    score: float
    floor_score: float
    median_score: float
    ceiling_score: float
    sci: float
    rmi: float
    gis: float
    od: float
    msf: float
    calculated_at: str


class LeaderboardResponse(BaseModel):
    """Leaderboard results for a sport/position."""

    sport: str
    position: str | None = None
    mode: str
    players: list[LeaderboardPlayer]
    positions: list[str]


# -------------------------------------------------------------------------
# Endpoint
# -------------------------------------------------------------------------


@router.get("/{sport}/top", response_model=LeaderboardResponse)
async def get_top_players(
    sport: str,
    req: Request,
    position: str | None = Query(None, description="Filter by position (e.g., QB, RB, WR)"),
    mode: str = Query("median", description="Score mode: floor, median, or ceiling"),
    limit: int = Query(5, ge=1, le=25, description="Number of players to return"),
) -> Any:
    """
    Get top players by position for a sport.

    Returns players ranked by their five-index composite score
    (floor, median, or ceiling mode). Filter by position to see
    position-specific leaderboards.
    """
    sport = sport.lower()
    if sport not in VALID_SPORTS:
        raise HTTPException(status_code=400, detail=f"Invalid sport: {sport}")

    mode = mode.lower()
    if mode not in VALID_MODES:
        raise HTTPException(
            status_code=400, detail=f"Invalid mode: {mode}. Use floor, median, or ceiling"
        )

    sport_positions = POSITIONS.get(sport, [])

    if position:
        position = position.strip().upper()
        if position not in sport_positions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid position '{position}' for {sport}. Valid: {', '.join(sport_positions)}",
            )

    # Rate limit
    client_ip = req.client.host if req.client else "anonymous"
    allowed, retry_after = await rate_limiter.check_rate_limit(f"leaderboard:{client_ip}")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )

    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")

    # Pick the score column based on mode
    score_column = {
        "floor": PlayerIndex.floor_score,
        "median": PlayerIndex.median_score,
        "ceiling": PlayerIndex.ceiling_score,
    }[mode]

    try:
        async with db_service.session() as session:
            # Subquery: latest index per player
            latest_idx = (
                select(
                    PlayerIndex.player_id,
                    func.max(PlayerIndex.calculated_at).label("max_calc"),
                )
                .group_by(PlayerIndex.player_id)
                .subquery()
            )

            # Main query: join Player + PlayerIndex on latest calculation
            query = (
                select(Player, PlayerIndex)
                .join(PlayerIndex, Player.id == PlayerIndex.player_id)
                .join(
                    latest_idx,
                    (PlayerIndex.player_id == latest_idx.c.player_id)
                    & (PlayerIndex.calculated_at == latest_idx.c.max_calc),
                )
                .where(Player.sport == sport)
            )

            if position:
                query = query.where(func.upper(func.trim(Player.position)) == position)

            query = query.order_by(score_column.desc()).limit(limit)

            result = await session.execute(query)
            rows = result.all()

            players = []
            for rank, (player, idx) in enumerate(rows, 1):
                players.append(
                    LeaderboardPlayer(
                        rank=rank,
                        player_id=str(player.espn_id),
                        name=player.name,
                        team=player.team_abbrev or player.team,
                        position=player.position,
                        score=float(getattr(idx, f"{mode}_score")),
                        floor_score=float(idx.floor_score),
                        median_score=float(idx.median_score),
                        ceiling_score=float(idx.ceiling_score),
                        sci=float(idx.sci),
                        rmi=float(idx.rmi),
                        gis=float(idx.gis),
                        od=float(idx.od),
                        msf=float(idx.msf),
                        calculated_at=str(idx.calculated_at),
                    )
                )

    except SQLAlchemyError:
        logger.exception("Leaderboard query error")
        raise HTTPException(status_code=500, detail="Failed to load leaderboard")

    return LeaderboardResponse(
        sport=sport,
        position=position,
        mode=mode,
        players=players,
        positions=sport_positions,
    )


# -------------------------------------------------------------------------
# Trending Movers (7-day score change)
# -------------------------------------------------------------------------


class TrendingPlayer(BaseModel):
    """A player with score change over the last 7 days."""

    rank: int
    player_id: str
    name: str
    team: str | None = None
    position: str | None = None
    current_score: float
    previous_score: float
    delta: float
    direction: str  # "up" or "down"


class TrendingResponse(BaseModel):
    """Trending movers for a sport."""

    sport: str
    mode: str
    direction: str
    players: list[TrendingPlayer]


@router.get("/{sport}/trending", response_model=TrendingResponse)
async def get_trending_players(
    sport: str,
    req: Request,
    mode: str = Query("median", description="Score mode: floor, median, or ceiling"),
    direction: str = Query("up", description="Sort direction: up (risers) or down (fallers)"),
    limit: int = Query(10, ge=1, le=25, description="Number of players to return"),
) -> Any:
    """
    Get trending players based on 7-day score change.

    Compares each player's latest index score against their score from ~7 days ago.
    Returns the biggest risers (direction=up) or fallers (direction=down).
    """
    sport = sport.lower()
    if sport not in VALID_SPORTS:
        raise HTTPException(status_code=400, detail=f"Invalid sport: {sport}")

    mode = mode.lower()
    if mode not in VALID_MODES:
        raise HTTPException(
            status_code=400, detail=f"Invalid mode: {mode}. Use floor, median, or ceiling"
        )

    direction = direction.lower()
    if direction not in {"up", "down"}:
        raise HTTPException(status_code=400, detail="Direction must be 'up' or 'down'")

    # Rate limit
    client_ip = req.client.host if req.client else "anonymous"
    allowed, retry_after = await rate_limiter.check_rate_limit(f"trending:{client_ip}")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )

    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")

    score_col_name = f"{mode}_score"
    now = datetime.now(UTC)
    seven_days_ago = now - timedelta(days=7)

    try:
        async with db_service.session() as session:
            # Latest index per player
            latest_sub = (
                select(
                    PlayerIndex.player_id,
                    func.max(PlayerIndex.calculated_at).label("max_calc"),
                )
                .group_by(PlayerIndex.player_id)
                .subquery()
            )

            # Previous index: latest before 7 days ago
            prev_sub = (
                select(
                    PlayerIndex.player_id,
                    func.max(PlayerIndex.calculated_at).label("prev_calc"),
                )
                .where(PlayerIndex.calculated_at < seven_days_ago)
                .group_by(PlayerIndex.player_id)
                .subquery()
            )

            # Alias PlayerIndex for current and previous
            current_idx = PlayerIndex.__table__.alias("current_idx")
            prev_idx = PlayerIndex.__table__.alias("prev_idx")

            current_score = current_idx.c[score_col_name]
            prev_score = prev_idx.c[score_col_name]
            delta_col = (current_score - prev_score).label("delta")

            query = (
                select(
                    Player,
                    current_score.label("current_score"),
                    prev_score.label("previous_score"),
                    delta_col,
                )
                .join(current_idx, Player.id == current_idx.c.player_id)
                .join(
                    latest_sub,
                    (current_idx.c.player_id == latest_sub.c.player_id)
                    & (current_idx.c.calculated_at == latest_sub.c.max_calc),
                )
                .join(prev_idx, Player.id == prev_idx.c.player_id)
                .join(
                    prev_sub,
                    (prev_idx.c.player_id == prev_sub.c.player_id)
                    & (prev_idx.c.calculated_at == prev_sub.c.prev_calc),
                )
                .where(Player.sport == sport)
            )

            if direction == "up":
                query = query.order_by(delta_col.desc())
            else:
                query = query.order_by(delta_col.asc())

            query = query.limit(limit)

            result = await session.execute(query)
            rows = result.all()

            players = []
            for rank, row in enumerate(rows, 1):
                player = row[0]
                cur = float(row[1])
                prev = float(row[2])
                d = float(row[3])
                players.append(
                    TrendingPlayer(
                        rank=rank,
                        player_id=str(player.espn_id),
                        name=player.name,
                        team=player.team_abbrev or player.team,
                        position=player.position,
                        current_score=cur,
                        previous_score=prev,
                        delta=round(d, 2),
                        direction="up" if d >= 0 else "down",
                    )
                )

    except SQLAlchemyError:
        logger.exception("Trending query error")
        raise HTTPException(status_code=500, detail="Failed to load trending data")

    return TrendingResponse(
        sport=sport,
        mode=mode,
        direction=direction,
        players=players,
    )


# -------------------------------------------------------------------------
# Decision Accuracy Leaders
# -------------------------------------------------------------------------


class AccuracyLeader(BaseModel):
    """A user's decision accuracy stats."""

    rank: int
    user_id: str
    total_decisions: int
    correct: int
    incorrect: int
    accuracy_pct: float


class AccuracyResponse(BaseModel):
    """Decision accuracy leaderboard."""

    sport: str | None
    min_decisions: int
    leaders: list[AccuracyLeader]


@router.get("/accuracy", response_model=AccuracyResponse)
async def get_accuracy_leaders(
    req: Request,
    sport: str | None = Query(None, description="Filter by sport (optional)"),
    min_decisions: int = Query(5, ge=1, le=100, description="Minimum decisions to qualify"),
    limit: int = Query(10, ge=1, le=25, description="Number of leaders to return"),
) -> Any:
    """
    Get decision accuracy leaderboard.

    Ranks users by accuracy percentage (correct / total resolved decisions).
    Requires a minimum number of resolved decisions to qualify.
    """
    if sport:
        sport = sport.lower()
        if sport not in VALID_SPORTS:
            raise HTTPException(status_code=400, detail=f"Invalid sport: {sport}")

    # Rate limit
    client_ip = req.client.host if req.client else "anonymous"
    allowed, retry_after = await rate_limiter.check_rate_limit(f"accuracy:{client_ip}")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )

    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        async with db_service.session() as session:
            correct_count = func.sum(
                case((Decision.actual_outcome == "correct", 1), else_=0)
            ).label("correct")
            incorrect_count = func.sum(
                case((Decision.actual_outcome == "incorrect", 1), else_=0)
            ).label("incorrect")
            total = (correct_count + incorrect_count).label("total")

            query = select(
                Decision.user_id,
                correct_count,
                incorrect_count,
                total,
            ).where(
                Decision.user_id.is_not(None),
                Decision.actual_outcome.in_(["correct", "incorrect"]),
            )

            if sport:
                query = query.where(Decision.sport == sport)

            query = (
                query.group_by(Decision.user_id)
                .having(total >= min_decisions)
                .order_by(
                    (func.cast(correct_count, Numeric) / func.cast(total, Numeric)).desc(),
                    total.desc(),
                )
                .limit(limit)
            )

            result = await session.execute(query)
            rows = result.all()

            leaders = []
            for rank, row in enumerate(rows, 1):
                uid, cor, inc, tot = row
                pct = round((cor / tot) * 100, 1) if tot > 0 else 0.0
                leaders.append(
                    AccuracyLeader(
                        rank=rank,
                        user_id=str(uid),
                        total_decisions=int(tot),
                        correct=int(cor),
                        incorrect=int(inc),
                        accuracy_pct=pct,
                    )
                )

    except SQLAlchemyError:
        logger.exception("Accuracy leaderboard query error")
        raise HTTPException(status_code=500, detail="Failed to load accuracy data")

    return AccuracyResponse(
        sport=sport,
        min_decisions=min_decisions,
        leaders=leaders,
    )


# -------------------------------------------------------------------------
# Season Snapshot (historical comparison)
# -------------------------------------------------------------------------


class SeasonPlayer(BaseModel):
    """A player's aggregated stats over a date range."""

    player_id: str
    name: str
    team: str | None = None
    position: str | None = None
    avg_floor: float
    avg_median: float
    avg_ceiling: float
    games: int
    first_seen: str
    last_seen: str


class SeasonResponse(BaseModel):
    """Season snapshot for a sport within a date range."""

    sport: str
    start_date: str
    end_date: str
    players: list[SeasonPlayer]


@router.get("/{sport}/season", response_model=SeasonResponse)
async def get_season_snapshot(
    sport: str,
    req: Request,
    start: str | None = Query(None, description="Start date YYYY-MM-DD (default: 30 days ago)"),
    end: str | None = Query(None, description="End date YYYY-MM-DD (default: today)"),
    position: str | None = Query(None, description="Filter by position"),
    limit: int = Query(25, ge=1, le=50, description="Number of players"),
    mode: str = Query("median", description="Sort by: floor, median, or ceiling"),
) -> Any:
    """
    Get aggregated player scores over a date range for season comparison.

    Returns average floor/median/ceiling scores and game counts.
    Use different date ranges to compare performance across time periods.
    """
    sport = sport.lower()
    if sport not in VALID_SPORTS:
        raise HTTPException(status_code=400, detail=f"Invalid sport: {sport}")

    mode = mode.lower()
    if mode not in VALID_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {mode}")

    now = datetime.now(UTC)
    try:
        end_dt = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=UTC) if end else now
        start_dt = (
            datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=UTC)
            if start
            else end_dt - timedelta(days=30)
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if start_dt > end_dt:
        raise HTTPException(status_code=400, detail="start must be before end")

    sport_positions = POSITIONS.get(sport, [])
    if position:
        position = position.strip().upper()
        if position not in sport_positions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid position '{position}' for {sport}",
            )

    client_ip = req.client.host if req.client else "anonymous"
    allowed, retry_after = await rate_limiter.check_rate_limit(f"season:{client_ip}")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )

    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        async with db_service.session() as session:
            query = (
                select(
                    Player.espn_id,
                    Player.name,
                    func.coalesce(Player.team_abbrev, Player.team).label("team"),
                    Player.position,
                    func.avg(PlayerIndex.floor_score).label("avg_floor"),
                    func.avg(PlayerIndex.median_score).label("avg_median"),
                    func.avg(PlayerIndex.ceiling_score).label("avg_ceiling"),
                    func.count(PlayerIndex.id).label("games"),
                    func.min(PlayerIndex.calculated_at).label("first_seen"),
                    func.max(PlayerIndex.calculated_at).label("last_seen"),
                )
                .join(PlayerIndex, Player.id == PlayerIndex.player_id)
                .where(
                    Player.sport == sport,
                    PlayerIndex.calculated_at >= start_dt,
                    PlayerIndex.calculated_at <= end_dt,
                )
            )

            if position:
                query = query.where(func.upper(func.trim(Player.position)) == position)

            query = (
                query.group_by(
                    Player.espn_id, Player.name, Player.team_abbrev, Player.team, Player.position
                )
                .order_by(func.avg(getattr(PlayerIndex, f"{mode}_score")).desc())
                .limit(limit)
            )

            result = await session.execute(query)
            rows = result.all()

            players = [
                SeasonPlayer(
                    player_id=str(r.espn_id),
                    name=r.name,
                    team=r.team,
                    position=r.position,
                    avg_floor=round(float(r.avg_floor), 2),
                    avg_median=round(float(r.avg_median), 2),
                    avg_ceiling=round(float(r.avg_ceiling), 2),
                    games=int(r.games),
                    first_seen=str(r.first_seen),
                    last_seen=str(r.last_seen),
                )
                for r in rows
            ]

    except SQLAlchemyError:
        logger.exception("Season snapshot query error")
        raise HTTPException(status_code=500, detail="Failed to load season data")

    return SeasonResponse(
        sport=sport,
        start_date=str(start_dt.date()),
        end_date=str(end_dt.date()),
        players=players,
    )
