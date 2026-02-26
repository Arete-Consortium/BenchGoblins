"""
Rivalry tracking API routes.

Provides endpoints for syncing matchup data from Sleeper and
viewing head-to-head records between league members.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from routes.auth import get_current_user
from services.database import db_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rivalries", tags=["Rivalries"])


# -------------------------------------------------------------------------
# Response Models
# -------------------------------------------------------------------------


class SyncResponse(BaseModel):
    """Response from matchup sync operation."""

    upserted: int
    message: str


class H2HMatchup(BaseModel):
    """A single historical matchup entry."""

    season: str
    week: int
    points_a: float
    points_b: float
    winner: str | None


class H2HRecord(BaseModel):
    """Head-to-head record between two owners."""

    owner_a: str
    owner_b: str
    wins_a: int
    wins_b: int
    ties: int
    total_points_a: float
    total_points_b: float
    matchups: list[H2HMatchup]


class RivalrySummary(BaseModel):
    """Summary of a rivalry between two owners."""

    owner_a: str
    owner_b: str
    games_played: int
    wins_a: int
    wins_b: int
    ties: int
    avg_margin: float
    total_points_a: float
    total_points_b: float


class UserRivalry(BaseModel):
    """A user's record against a specific opponent."""

    opponent: str
    games_played: int
    wins: int
    losses: int
    ties: int
    win_pct: float


# -------------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------------


@router.post("/{league_id}/sync", response_model=SyncResponse)
async def sync_league_matchups(
    league_id: int,
    season: str = Query(default="2025", description="Season year"),
    weeks: str = Query(default="1-18", description="Week range, e.g. 1-18"),
    current_user: dict = Depends(get_current_user),
):
    """
    Sync matchup data from Sleeper for a league.

    Fetches weekly results and stores them for rivalry tracking.
    Only the league commissioner or a member can trigger sync.
    """
    from services.rivalry import sync_matchups

    async with db_service.session() as session:
        # Verify league exists and user has access
        from sqlalchemy import select

        from models.database import League, LeagueMembership

        league_result = await session.execute(select(League).where(League.id == league_id))
        league = league_result.scalar_one_or_none()

        if not league:
            raise HTTPException(status_code=404, detail="League not found")

        if not league.sleeper_league_id:
            raise HTTPException(
                status_code=400,
                detail="League is not connected to Sleeper",
            )

        # Check membership
        user_id = current_user["user_id"]
        member_result = await session.execute(
            select(LeagueMembership).where(
                LeagueMembership.league_id == league_id,
                LeagueMembership.user_id == user_id,
                LeagueMembership.status == "active",
            )
        )
        is_member = member_result.scalar_one_or_none() is not None
        is_commissioner = league.commissioner_user_id == user_id

        if not is_member and not is_commissioner:
            raise HTTPException(
                status_code=403,
                detail="You must be a league member to sync matchups",
            )

        # Parse week range
        week_list = _parse_week_range(weeks)

        count = await sync_matchups(
            session,
            league_id=league_id,
            sleeper_league_id=league.sleeper_league_id,
            season=season,
            weeks=week_list,
        )

    return SyncResponse(
        upserted=count,
        message=f"Synced {count} matchups for {len(week_list)} weeks",
    )


@router.get("/{league_id}", response_model=list[RivalrySummary])
async def get_league_rivalries(
    league_id: int,
    season: str | None = Query(default=None, description="Filter by season"),
    current_user: dict = Depends(get_current_user),
):
    """Get all rivalry records in a league."""
    from services.rivalry import get_league_rivalries

    async with db_service.session() as session:
        return await get_league_rivalries(session, league_id, season)


@router.get("/{league_id}/me", response_model=list[UserRivalry])
async def get_my_rivalries(
    league_id: int,
    season: str | None = Query(default=None, description="Filter by season"),
    current_user: dict = Depends(get_current_user),
):
    """Get the current user's rivalry records in a league."""
    from services.rivalry import get_user_rivalries

    # Look up user's Sleeper owner_id from the users table
    async with db_service.session() as session:
        from sqlalchemy import select

        from models.database import User

        user_result = await session.execute(select(User).where(User.id == current_user["user_id"]))
        user = user_result.scalar_one_or_none()

        if not user or not user.sleeper_user_id:
            raise HTTPException(
                status_code=404,
                detail="Sleeper account not linked. Connect your Sleeper username first.",
            )

        return await get_user_rivalries(session, league_id, user.sleeper_user_id, season)


@router.get("/{league_id}/h2h", response_model=H2HRecord)
async def get_head_to_head(
    league_id: int,
    owner_a: str = Query(..., description="Sleeper owner ID of first user"),
    owner_b: str = Query(..., description="Sleeper owner ID of second user"),
    season: str | None = Query(default=None, description="Filter by season"),
    current_user: dict = Depends(get_current_user),
):
    """Get detailed head-to-head record between two owners."""
    from services.rivalry import get_h2h_record

    async with db_service.session() as session:
        return await get_h2h_record(session, league_id, owner_a, owner_b, season)


def _parse_week_range(weeks: str) -> list[int]:
    """Parse a week range string like '1-18' or '1,3,5' into a list of ints."""
    result = []
    for part in weeks.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            result.extend(range(int(start), int(end) + 1))
        else:
            result.append(int(part))
    return sorted(set(result))
