"""
League Integration API Routes.

Handles Sleeper league connection, roster retrieval, and league settings.
Sleeper API is public — no OAuth required, just a username.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.sleeper import sleeper_service

router = APIRouter(prefix="/leagues", tags=["Leagues"])


# -------------------------------------------------------------------------
# Request/Response Models
# -------------------------------------------------------------------------


class ConnectRequest(BaseModel):
    """Request to connect a Sleeper account."""

    username: str = Field(..., description="Sleeper username")
    sport: str = Field(default="nfl", description="Sport: nfl, nba, mlb, nhl")
    season: str = Field(default="2025", description="Season year")


class SleeperUserResponse(BaseModel):
    """Sleeper user info."""

    user_id: str
    username: str
    display_name: str
    avatar: str | None = None


class LeagueResponse(BaseModel):
    """League summary."""

    league_id: str
    name: str
    sport: str
    season: str
    status: str
    total_rosters: int
    roster_positions: list[str]
    scoring_settings: dict


class ConnectResponse(BaseModel):
    """Response after connecting a Sleeper account."""

    sleeper_user: SleeperUserResponse
    leagues: list[LeagueResponse]


class RosterPlayerResponse(BaseModel):
    """Player in a roster."""

    player_id: str
    full_name: str
    team: str | None = None
    position: str
    status: str
    injury_status: str | None = None
    is_starter: bool


class RosterResponse(BaseModel):
    """Full roster with player details."""

    roster_id: int
    owner_id: str
    players: list[RosterPlayerResponse]
    starters: list[str]
    reserve: list[str] | None = None


# -------------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------------


@router.post("/connect", response_model=ConnectResponse)
async def connect_sleeper(
    request: ConnectRequest,
):
    """
    Connect a Sleeper account by username.

    Looks up the Sleeper user and returns all their leagues
    for the specified sport and season.
    """
    user = await sleeper_service.get_user(request.username)
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"Sleeper user '{request.username}' not found",
        )

    leagues = await sleeper_service.get_user_leagues(
        user_id=user.user_id,
        sport=request.sport,
        season=request.season,
    )

    return ConnectResponse(
        sleeper_user=SleeperUserResponse(
            user_id=user.user_id,
            username=user.username,
            display_name=user.display_name,
            avatar=user.avatar,
        ),
        leagues=[
            LeagueResponse(
                league_id=lg.league_id,
                name=lg.name,
                sport=lg.sport,
                season=lg.season,
                status=lg.status,
                total_rosters=lg.total_rosters,
                roster_positions=lg.roster_positions,
                scoring_settings=lg.scoring_settings,
            )
            for lg in leagues
        ],
    )


@router.get("/{league_id}/roster", response_model=RosterResponse)
async def get_roster(
    league_id: str,
    sleeper_user_id: str = Query(..., description="Sleeper user ID"),
    sport: str = Query(default="nfl", description="Sport: nfl, nba, mlb, nhl"),
):
    """
    Get a user's roster in a league with full player details.

    Returns player names, positions, injury status, and starter designation.
    Stats are not included — use /decide or /players/search for scoring data.
    """
    roster = await sleeper_service.get_user_roster(league_id, sleeper_user_id)
    if not roster:
        raise HTTPException(
            status_code=404,
            detail=f"Roster not found for user '{sleeper_user_id}' in league '{league_id}'",
        )

    players = await sleeper_service.get_players_by_ids(roster.players, sport)
    starter_set = set(roster.starters)

    return RosterResponse(
        roster_id=roster.roster_id,
        owner_id=roster.owner_id,
        players=[
            RosterPlayerResponse(
                player_id=p.player_id,
                full_name=p.full_name,
                team=p.team,
                position=p.position,
                status=p.status,
                injury_status=p.injury_status,
                is_starter=p.player_id in starter_set,
            )
            for p in players
        ],
        starters=roster.starters,
        reserve=roster.reserve,
    )


@router.get("/{league_id}/settings", response_model=LeagueResponse)
async def get_league_settings(
    league_id: str,
):
    """
    Get league settings including scoring rules and roster positions.
    """
    league = await sleeper_service.get_league(league_id)
    if not league:
        raise HTTPException(
            status_code=404,
            detail=f"League '{league_id}' not found",
        )

    return LeagueResponse(
        league_id=league.league_id,
        name=league.name,
        sport=league.sport,
        season=league.season,
        status=league.status,
        total_rosters=league.total_rosters,
        roster_positions=league.roster_positions,
        scoring_settings=league.scoring_settings,
    )
