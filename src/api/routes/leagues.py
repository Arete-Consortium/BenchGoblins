"""
League Integration API Routes.

Handles Sleeper league connection, roster retrieval, and league settings.
Sleeper API is public — no OAuth required, just a username.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from models.database import User
from routes.auth import get_current_user
from services.database import db_service
from services.espn_fantasy import ESPNCredentials, espn_fantasy_service
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


class SyncRequest(BaseModel):
    """Request to persist Sleeper connection to user profile."""

    username: str = Field(..., description="Sleeper username")
    league_id: str = Field(..., description="Sleeper league ID")
    sport: str = Field(default="nfl", description="Sport: nfl, nba, mlb, nhl")
    season: str = Field(default="2025", description="Season year")


class SyncResponse(BaseModel):
    """Response after syncing Sleeper to user profile."""

    sleeper_username: str
    sleeper_user_id: str
    sleeper_league_id: str
    roster_player_count: int
    synced_at: str


class MyLeagueResponse(BaseModel):
    """Current user's Sleeper connection status."""

    connected: bool
    sleeper_username: str | None = None
    sleeper_league_id: str | None = None
    sleeper_user_id: str | None = None
    roster_player_count: int = 0
    synced_at: str | None = None


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


# -------------------------------------------------------------------------
# Sleeper Sync (persist to user profile)
# -------------------------------------------------------------------------


@router.post("/sync", response_model=SyncResponse)
async def sync_sleeper(
    request: SyncRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Persist a Sleeper connection to the authenticated user's profile.

    Validates the username and league, fetches the roster snapshot,
    and stores everything on the User record so /decide can auto-inject context.
    """
    # Validate Sleeper username
    sleeper_user = await sleeper_service.get_user(request.username)
    if not sleeper_user:
        raise HTTPException(
            status_code=404,
            detail=f"Sleeper user '{request.username}' not found",
        )

    # Validate league exists
    league = await sleeper_service.get_league(request.league_id)
    if not league:
        raise HTTPException(
            status_code=404,
            detail=f"League '{request.league_id}' not found",
        )

    # Fetch roster snapshot (may be None if user hasn't joined yet)
    roster_snapshot = []
    roster = await sleeper_service.get_user_roster(request.league_id, sleeper_user.user_id)
    if roster and roster.players:
        players = await sleeper_service.get_players_by_ids(roster.players, request.sport)
        starter_set = set(roster.starters or [])
        roster_snapshot = [
            {
                "player_id": p.player_id,
                "full_name": p.full_name,
                "position": p.position,
                "team": p.team,
                "is_starter": p.player_id in starter_set,
            }
            for p in players
        ]

    now = datetime.now(UTC)

    async with db_service.session() as session:
        result = await session.execute(select(User).where(User.id == current_user["user_id"]))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.sleeper_username = sleeper_user.username
        user.sleeper_user_id = sleeper_user.user_id
        user.sleeper_league_id = request.league_id
        user.roster_snapshot = roster_snapshot
        user.sleeper_synced_at = now
        session.add(user)
        await session.commit()

    return SyncResponse(
        sleeper_username=sleeper_user.username,
        sleeper_user_id=sleeper_user.user_id,
        sleeper_league_id=request.league_id,
        roster_player_count=len(roster_snapshot),
        synced_at=now.isoformat(),
    )


@router.get("/me", response_model=MyLeagueResponse)
async def get_my_league(
    current_user: dict = Depends(get_current_user),
):
    """
    Check if the authenticated user has a connected Sleeper league.
    """
    async with db_service.session() as session:
        result = await session.execute(select(User).where(User.id == current_user["user_id"]))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

    connected = user.sleeper_league_id is not None
    return MyLeagueResponse(
        connected=connected,
        sleeper_username=user.sleeper_username,
        sleeper_league_id=user.sleeper_league_id,
        sleeper_user_id=user.sleeper_user_id,
        roster_player_count=len(user.roster_snapshot) if user.roster_snapshot else 0,
        synced_at=user.sleeper_synced_at.isoformat() if user.sleeper_synced_at else None,
    )


@router.delete("/me")
async def disconnect_league(
    current_user: dict = Depends(get_current_user),
):
    """
    Disconnect the authenticated user's Sleeper league.
    """
    async with db_service.session() as session:
        result = await session.execute(select(User).where(User.id == current_user["user_id"]))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.sleeper_username = None
        user.sleeper_user_id = None
        user.sleeper_league_id = None
        user.roster_snapshot = None
        user.sleeper_synced_at = None
        session.add(user)
        await session.commit()

    return {"disconnected": True}


# -------------------------------------------------------------------------
# ESPN Fantasy Integration (persist to user profile)
# -------------------------------------------------------------------------


class ESPNSyncRequest(BaseModel):
    """Request to persist ESPN Fantasy connection to user profile."""

    swid: str = Field(..., description="ESPN SWID cookie")
    espn_s2: str = Field(..., description="ESPN espn_s2 cookie")
    league_id: str = Field(..., description="ESPN league ID")
    team_id: str = Field(..., description="Team ID within the league")
    sport: str = Field(default="nfl", description="Sport: nfl, nba, mlb, nhl")


class ESPNSyncResponse(BaseModel):
    """Response after syncing ESPN connection to user profile."""

    espn_league_id: str
    espn_team_id: str
    sport: str
    roster_player_count: int
    synced_at: str


class MyESPNResponse(BaseModel):
    """Current user's ESPN connection status."""

    connected: bool
    espn_league_id: str | None = None
    espn_team_id: str | None = None
    sport: str | None = None
    roster_player_count: int = 0
    synced_at: str | None = None


@router.post("/sync-espn", response_model=ESPNSyncResponse)
async def sync_espn(
    request: ESPNSyncRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Persist an ESPN Fantasy connection to the authenticated user's profile.

    Validates credentials, fetches roster snapshot, and stores on User record
    so /decide can auto-inject ESPN roster context.
    """
    creds = ESPNCredentials(swid=request.swid, espn_s2=request.espn_s2)

    # Verify credentials
    valid = await espn_fantasy_service.verify_credentials(creds)
    if not valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid ESPN credentials. Check your SWID and espn_s2 cookies.",
        )

    # Fetch roster snapshot
    roster_snapshot = []
    players = await espn_fantasy_service.get_roster(
        creds, request.league_id, int(request.team_id), request.sport
    )
    roster_snapshot = [
        {
            "player_id": p.player_id,
            "name": p.name,
            "position": p.position,
            "team": str(p.team),
            "lineup_slot": p.lineup_slot,
        }
        for p in players
    ]

    now = datetime.now(UTC)

    async with db_service.session() as session:
        result = await session.execute(select(User).where(User.id == current_user["user_id"]))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.espn_swid = request.swid
        user.espn_s2 = request.espn_s2
        user.espn_league_id = request.league_id
        user.espn_team_id = request.team_id
        user.espn_sport = request.sport
        user.espn_roster_snapshot = roster_snapshot
        user.espn_synced_at = now
        session.add(user)
        await session.commit()

    return ESPNSyncResponse(
        espn_league_id=request.league_id,
        espn_team_id=request.team_id,
        sport=request.sport,
        roster_player_count=len(roster_snapshot),
        synced_at=now.isoformat(),
    )


@router.get("/me/espn", response_model=MyESPNResponse)
async def get_my_espn(
    current_user: dict = Depends(get_current_user),
):
    """
    Check if the authenticated user has a connected ESPN Fantasy league.
    """
    async with db_service.session() as session:
        result = await session.execute(select(User).where(User.id == current_user["user_id"]))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

    connected = user.espn_league_id is not None
    return MyESPNResponse(
        connected=connected,
        espn_league_id=user.espn_league_id,
        espn_team_id=user.espn_team_id,
        sport=user.espn_sport,
        roster_player_count=len(user.espn_roster_snapshot) if user.espn_roster_snapshot else 0,
        synced_at=user.espn_synced_at.isoformat() if user.espn_synced_at else None,
    )


@router.delete("/me/espn")
async def disconnect_espn(
    current_user: dict = Depends(get_current_user),
):
    """
    Disconnect the authenticated user's ESPN Fantasy connection.
    """
    async with db_service.session() as session:
        result = await session.execute(select(User).where(User.id == current_user["user_id"]))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.espn_swid = None
        user.espn_s2 = None
        user.espn_league_id = None
        user.espn_team_id = None
        user.espn_sport = None
        user.espn_roster_snapshot = None
        user.espn_synced_at = None
        session.add(user)
        await session.commit()

    return {"disconnected": True}
