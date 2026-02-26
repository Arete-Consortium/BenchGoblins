"""
Commissioner AI Tools — League-wide analytics and management endpoints.

All endpoints require the caller to be commissioner of the specified league.
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.database import League, LeagueMembership
from routes.auth import get_current_user
from services.claude import claude_service
from services.database import db_service
from services.sleeper import sleeper_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/commissioner", tags=["Commissioner"])


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------


async def require_commissioner(league_id: int, current_user: dict) -> League:
    """Verify user is commissioner of this league. Raises 403 if not."""
    async with db_service.session() as session:
        result = await session.execute(
            select(LeagueMembership)
            .options(selectinload(LeagueMembership.league))
            .where(
                LeagueMembership.league_id == league_id,
                LeagueMembership.user_id == current_user["user_id"],
                LeagueMembership.role == "commissioner",
                LeagueMembership.status == "active",
            )
        )
        membership = result.scalar_one_or_none()
        if not membership:
            raise HTTPException(
                status_code=403,
                detail="Commissioner access required",
            )
        return membership.league


# -------------------------------------------------------------------------
# Request/Response Models
# -------------------------------------------------------------------------


class RosterRanking(BaseModel):
    """Single team in power rankings."""

    rank: int
    owner_id: str
    display_name: str | None = None
    roster_size: int = 0
    strength_score: float = 0.0


class PowerRankingsResponse(BaseModel):
    """League-wide power rankings."""

    league_id: int
    league_name: str
    rankings: list[RosterRanking]
    generated_at: str


class TradeCheckRequest(BaseModel):
    """Request to analyze a trade."""

    team_a_players: list[str] = Field(..., description="Player names team A gives up")
    team_b_players: list[str] = Field(..., description="Player names team B receives")


class TradeCheckResponse(BaseModel):
    """Claude-powered trade fairness analysis."""

    fairness_score: float = Field(description="0-100 fairness score")
    verdict: str = Field(description="Fair, Lopsided, etc.")
    reasoning: str
    source: str = "claude"


class TeamAnalysis(BaseModel):
    """Per-team roster analysis."""

    owner_id: str
    display_name: str | None = None
    roster_size: int = 0
    starters_count: int = 0
    strengths: list[str] = []
    weaknesses: list[str] = []


class RosterAnalysisResponse(BaseModel):
    """League-wide roster breakdown."""

    league_id: int
    teams: list[TeamAnalysis]


class MemberActivity(BaseModel):
    """Member activity summary."""

    user_id: int
    name: str
    email: str
    queries_this_week: int = 0
    last_active: str | None = None
    is_active: bool = False


class ActivityResponse(BaseModel):
    """League member activity summary."""

    league_id: int
    total_members: int
    active_members: int
    members: list[MemberActivity]


# -------------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------------


@router.get("/leagues/{league_id}/power-rankings", response_model=PowerRankingsResponse)
async def get_power_rankings(
    league_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Fetch all rosters in the league, score each, return ranked list.

    Uses Sleeper API to fetch rosters and player data, then scores each
    roster using total starter strength.
    """
    league = await require_commissioner(league_id, current_user)

    # Fetch all rosters from Sleeper
    try:
        rosters = await sleeper_service.get_league_rosters(league.external_league_id)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch league rosters from Sleeper: {e}",
        )

    if not rosters:
        return PowerRankingsResponse(
            league_id=league.id,
            league_name=league.name,
            rankings=[],
            generated_at=datetime.now(UTC).isoformat(),
        )

    # Score each roster by total player count (as a proxy — full scoring
    # requires player stats enrichment which is expensive per-call)
    rankings = []
    for roster in rosters:
        player_count = len(roster.players) if roster.players else 0
        starter_count = len(roster.starters) if roster.starters else 0
        # Simple strength proxy: starters * 10 + bench depth * 3
        strength = starter_count * 10 + (player_count - starter_count) * 3

        rankings.append(
            RosterRanking(
                rank=0,
                owner_id=roster.owner_id,
                roster_size=player_count,
                strength_score=round(strength, 1),
            )
        )

    # Sort by strength descending, assign ranks
    rankings.sort(key=lambda r: r.strength_score, reverse=True)
    for i, r in enumerate(rankings):
        r.rank = i + 1

    return PowerRankingsResponse(
        league_id=league.id,
        league_name=league.name,
        rankings=rankings,
        generated_at=datetime.now(UTC).isoformat(),
    )


@router.post("/leagues/{league_id}/trade-check", response_model=TradeCheckResponse)
async def check_trade(
    league_id: int,
    request: TradeCheckRequest,
    current_user: dict = Depends(get_current_user),
):
    """Analyze trade fairness using Claude.

    Takes two lists of player names and returns a fairness analysis.
    """
    league = await require_commissioner(league_id, current_user)

    if not claude_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Claude AI service is not available",
        )

    team_a_str = ", ".join(request.team_a_players)
    team_b_str = ", ".join(request.team_b_players)

    query = (
        f"Analyze this fantasy {league.sport.upper()} trade for fairness. "
        f"Team A gives up: {team_a_str}. "
        f"Team B gives up: {team_b_str}. "
        "Rate fairness 0-100 (50=perfectly fair). "
        'Return JSON: {{"fairness_score": N, "verdict": "Fair|Slightly Lopsided|Lopsided|Robbery", "reasoning": "..."}}'
    )

    try:
        result = await claude_service.make_decision(
            query=query,
            sport=league.sport,
            risk_mode="median",
            decision_type="trade",
            use_cache=False,
        )

        details = result.get("details", {})
        return TradeCheckResponse(
            fairness_score=details.get("fairness_score", 50.0)
            if isinstance(details, dict)
            else 50.0,
            verdict=details.get("verdict", result.get("decision", "Unknown"))
            if isinstance(details, dict)
            else result.get("decision", "Unknown"),
            reasoning=result.get("rationale", "Analysis complete"),
            source="claude",
        )

    except Exception as e:
        logger.error("Trade check failed: %s", e)
        raise HTTPException(status_code=500, detail="Trade analysis failed")


@router.get("/leagues/{league_id}/roster-analysis", response_model=RosterAnalysisResponse)
async def get_roster_analysis(
    league_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Per-team breakdown: roster size, starters, basic analysis."""
    league = await require_commissioner(league_id, current_user)

    try:
        rosters = await sleeper_service.get_league_rosters(league.external_league_id)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch rosters: {e}",
        )

    teams = []
    for roster in rosters or []:
        player_count = len(roster.players) if roster.players else 0
        starter_count = len(roster.starters) if roster.starters else 0
        bench_count = player_count - starter_count

        strengths = []
        weaknesses = []

        if player_count >= 15:
            strengths.append("Deep roster")
        elif player_count < 10:
            weaknesses.append("Thin roster")

        if starter_count >= 9:
            strengths.append("Strong starting lineup")

        if bench_count < 3:
            weaknesses.append("Limited bench depth")

        teams.append(
            TeamAnalysis(
                owner_id=roster.owner_id,
                roster_size=player_count,
                starters_count=starter_count,
                strengths=strengths,
                weaknesses=weaknesses,
            )
        )

    return RosterAnalysisResponse(
        league_id=league.id,
        teams=teams,
    )


@router.get("/leagues/{league_id}/activity", response_model=ActivityResponse)
async def get_league_activity(
    league_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Which members are using BenchGoblins, last active, queries this week."""
    league = await require_commissioner(league_id, current_user)

    async with db_service.session() as session:
        result = await session.execute(
            select(LeagueMembership)
            .options(selectinload(LeagueMembership.user))
            .where(
                LeagueMembership.league_id == league.id,
                LeagueMembership.status == "active",
            )
        )
        memberships = result.scalars().all()

        now = datetime.now(UTC)
        week_ago = now - timedelta(days=7)

        members = []
        active_count = 0

        for m in memberships:
            user = m.user
            if not user:
                continue

            is_active = user.updated_at is not None and user.updated_at > week_ago
            if is_active:
                active_count += 1

            members.append(
                MemberActivity(
                    user_id=user.id,
                    name=user.name,
                    email=user.email,
                    queries_this_week=user.queries_today,
                    last_active=user.updated_at.isoformat() if user.updated_at else None,
                    is_active=is_active,
                )
            )

        return ActivityResponse(
            league_id=league.id,
            total_members=len(members),
            active_members=active_count,
            members=members,
        )
