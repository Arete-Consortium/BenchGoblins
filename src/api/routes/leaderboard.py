"""
Leaderboard API Routes.

Top players by position using BenchGoblins five-index scoring system.
Supports filtering by sport, position, and risk mode (floor/median/ceiling).
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from models.database import Player, PlayerIndex
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
