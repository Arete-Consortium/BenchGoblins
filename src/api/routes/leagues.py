"""
League Integration API Routes.

Handles Sleeper league connection, roster retrieval, and league settings.
Sleeper API is public — no OAuth required, just a username.
"""

import logging
import secrets
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.database import League, LeagueMembership, User
from routes.auth import get_current_user
from services.database import db_service
from services.espn_fantasy import ESPNCredentials, espn_fantasy_service
from services.sleeper import sleeper_service
from services.yahoo import yahoo_service

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

    # Query current year and next year to catch off-season league creation
    # (Sleeper defaults new leagues to the upcoming season)
    current_year = date.today().year
    seasons_to_check = [request.season] if request.season != str(current_year) else []
    seasons_to_check.extend([str(current_year), str(current_year + 1)])
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_seasons = []
    for s in seasons_to_check:
        if s not in seen:
            seen.add(s)
            unique_seasons.append(s)

    all_leagues = []
    seen_ids: set[str] = set()
    for season in unique_seasons:
        leagues = await sleeper_service.get_user_leagues(
            user_id=user.user_id,
            sport=request.sport,
            season=season,
        )
        for lg in leagues:
            if lg.league_id not in seen_ids:
                seen_ids.add(lg.league_id)
                all_leagues.append(lg)

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
            for lg in all_leagues
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

    # Auto-create managed league + membership
    if db_service.is_configured:
        try:
            await _ensure_league_on_sync(
                external_league_id=request.league_id,
                platform="sleeper",
                season=request.season,
                league_name=league.name,
                sport=request.sport,
                user_id=current_user["user_id"],
                external_team_id=sleeper_user.user_id,
            )
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Failed to create managed league for %s: %s",
                request.league_id,
                exc,
            )

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


# -------------------------------------------------------------------------
# Yahoo Fantasy Integration (persist to user profile)
# -------------------------------------------------------------------------


class YahooSyncRequest(BaseModel):
    """Request to persist Yahoo Fantasy connection to user profile."""

    access_token: str = Field(..., description="Yahoo OAuth access token")
    refresh_token: str = Field(..., description="Yahoo OAuth refresh token")
    expires_at: float = Field(..., description="Token expiry (Unix timestamp)")
    league_key: str = Field(..., description="Yahoo league key (e.g., '449.l.12345')")
    team_key: str = Field(..., description="Yahoo team key (e.g., '449.l.12345.t.1')")
    sport: str = Field(default="nfl", description="Sport: nfl, nba, mlb, nhl")


class YahooSyncResponse(BaseModel):
    """Response after syncing Yahoo connection to user profile."""

    yahoo_league_key: str
    yahoo_team_key: str
    sport: str
    roster_player_count: int
    synced_at: str


class MyYahooResponse(BaseModel):
    """Current user's Yahoo connection status."""

    connected: bool
    yahoo_league_key: str | None = None
    yahoo_team_key: str | None = None
    sport: str | None = None
    roster_player_count: int = 0
    synced_at: str | None = None


@router.post("/sync-yahoo", response_model=YahooSyncResponse)
async def sync_yahoo(
    request: YahooSyncRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Persist a Yahoo Fantasy connection to the authenticated user's profile.

    Validates the access token, fetches roster snapshot, and stores on User
    record so /decide can auto-inject Yahoo roster context.
    """
    # Fetch roster snapshot using the provided token
    roster_snapshot = []
    try:
        players = await yahoo_service.get_team_roster(request.access_token, request.team_key)
        roster_snapshot = [
            {
                "player_key": p.player_key,
                "name": p.name,
                "position": p.position,
                "team": p.team_abbrev or "?",
                "status": p.status,
            }
            for p in players
        ]
    except Exception:
        # Roster fetch may fail but sync should still succeed
        pass

    now = datetime.now(UTC)

    async with db_service.session() as session:
        result = await session.execute(select(User).where(User.id == current_user["user_id"]))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.yahoo_access_token = request.access_token
        user.yahoo_refresh_token = request.refresh_token
        user.yahoo_token_expires_at = datetime.fromtimestamp(request.expires_at, tz=UTC)
        user.yahoo_league_key = request.league_key
        user.yahoo_team_key = request.team_key
        user.yahoo_sport = request.sport
        user.yahoo_roster_snapshot = roster_snapshot
        user.yahoo_synced_at = now
        session.add(user)
        await session.commit()

    return YahooSyncResponse(
        yahoo_league_key=request.league_key,
        yahoo_team_key=request.team_key,
        sport=request.sport,
        roster_player_count=len(roster_snapshot),
        synced_at=now.isoformat(),
    )


@router.get("/me/yahoo", response_model=MyYahooResponse)
async def get_my_yahoo(
    current_user: dict = Depends(get_current_user),
):
    """
    Check if the authenticated user has a connected Yahoo Fantasy league.
    """
    async with db_service.session() as session:
        result = await session.execute(select(User).where(User.id == current_user["user_id"]))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

    connected = user.yahoo_league_key is not None
    return MyYahooResponse(
        connected=connected,
        yahoo_league_key=user.yahoo_league_key,
        yahoo_team_key=user.yahoo_team_key,
        sport=user.yahoo_sport,
        roster_player_count=len(user.yahoo_roster_snapshot) if user.yahoo_roster_snapshot else 0,
        synced_at=user.yahoo_synced_at.isoformat() if user.yahoo_synced_at else None,
    )


@router.delete("/me/yahoo")
async def disconnect_yahoo_profile(
    current_user: dict = Depends(get_current_user),
):
    """
    Disconnect the authenticated user's Yahoo Fantasy connection.
    """
    async with db_service.session() as session:
        result = await session.execute(select(User).where(User.id == current_user["user_id"]))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.yahoo_access_token = None
        user.yahoo_refresh_token = None
        user.yahoo_token_expires_at = None
        user.yahoo_user_guid = None
        user.yahoo_league_key = None
        user.yahoo_team_key = None
        user.yahoo_sport = None
        user.yahoo_roster_snapshot = None
        user.yahoo_synced_at = None
        session.add(user)
        await session.commit()

    return {"disconnected": True}


# -------------------------------------------------------------------------
# Multi-League Aggregation
# -------------------------------------------------------------------------


class ConnectedLeagueInfo(BaseModel):
    """Unified league info across all platforms."""

    platform: str
    league_id: str
    sport: str
    roster_player_count: int = 0
    synced_at: str | None = None


class AllLeaguesResponse(BaseModel):
    """Aggregated leagues from all connected platforms."""

    leagues: list[ConnectedLeagueInfo]
    total: int


@router.get("/all", response_model=AllLeaguesResponse)
async def get_all_leagues(
    current_user: dict = Depends(get_current_user),
):
    """
    Aggregate leagues from all connected platforms (Sleeper, ESPN, Yahoo).

    Returns a unified list of connected leagues with platform info.
    """
    async with db_service.session() as session:
        result = await session.execute(select(User).where(User.id == current_user["user_id"]))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

    leagues: list[ConnectedLeagueInfo] = []

    # Sleeper
    if user.sleeper_league_id:
        leagues.append(
            ConnectedLeagueInfo(
                platform="sleeper",
                league_id=user.sleeper_league_id,
                sport="nfl",
                roster_player_count=len(user.roster_snapshot) if user.roster_snapshot else 0,
                synced_at=user.sleeper_synced_at.isoformat() if user.sleeper_synced_at else None,
            )
        )

    # ESPN
    if user.espn_league_id:
        leagues.append(
            ConnectedLeagueInfo(
                platform="espn",
                league_id=user.espn_league_id,
                sport=user.espn_sport or "nfl",
                roster_player_count=(
                    len(user.espn_roster_snapshot) if user.espn_roster_snapshot else 0
                ),
                synced_at=user.espn_synced_at.isoformat() if user.espn_synced_at else None,
            )
        )

    # Yahoo
    if user.yahoo_league_key:
        leagues.append(
            ConnectedLeagueInfo(
                platform="yahoo",
                league_id=user.yahoo_league_key,
                sport=user.yahoo_sport or "nfl",
                roster_player_count=(
                    len(user.yahoo_roster_snapshot) if user.yahoo_roster_snapshot else 0
                ),
                synced_at=user.yahoo_synced_at.isoformat() if user.yahoo_synced_at else None,
            )
        )

    return AllLeaguesResponse(leagues=leagues, total=len(leagues))


# -------------------------------------------------------------------------
# Managed League Models
# -------------------------------------------------------------------------


class ManagedLeagueResponse(BaseModel):
    """Managed league summary."""

    id: int
    external_league_id: str
    platform: str
    name: str
    sport: str
    season: str
    role: str
    member_count: int
    has_pro: bool = False
    invite_code: str | None = None


class MemberResponse(BaseModel):
    """League member info."""

    user_id: int
    email: str
    name: str
    role: str
    external_team_id: str | None = None
    status: str
    joined_at: str


class InviteResponse(BaseModel):
    """Invite code response."""

    invite_code: str
    invite_url: str


# -------------------------------------------------------------------------
# Managed League Endpoints
# -------------------------------------------------------------------------


async def _ensure_league_on_sync(
    external_league_id: str,
    platform: str,
    season: str,
    league_name: str,
    sport: str,
    user_id: int,
    external_team_id: str | None = None,
) -> League:
    """Find or create a managed league row, then add user membership.

    First user to connect becomes commissioner; subsequent users become members.
    """
    async with db_service.session() as session:
        result = await session.execute(
            select(League).where(
                League.external_league_id == external_league_id,
                League.platform == platform,
                League.season == season,
            )
        )
        league = result.scalar_one_or_none()

        if not league:
            league = League(
                external_league_id=external_league_id,
                platform=platform,
                name=league_name,
                sport=sport,
                season=season,
                commissioner_user_id=user_id,
                invite_code=secrets.token_hex(16),
            )
            session.add(league)
            await session.flush()

            membership = LeagueMembership(
                league_id=league.id,
                user_id=user_id,
                role="commissioner",
                external_team_id=external_team_id,
                status="active",
            )
            session.add(membership)
            await session.commit()
            await session.refresh(league)
            return league

        # League exists — add membership if not already present
        existing = await session.execute(
            select(LeagueMembership).where(
                LeagueMembership.league_id == league.id,
                LeagueMembership.user_id == user_id,
            )
        )
        membership = existing.scalar_one_or_none()

        if not membership:
            membership = LeagueMembership(
                league_id=league.id,
                user_id=user_id,
                role="member",
                external_team_id=external_team_id,
                status="active",
            )
            session.add(membership)
            await session.commit()
        elif membership.status == "removed":
            membership.status = "active"
            membership.external_team_id = external_team_id
            await session.commit()

        return league


@router.get("/managed", response_model=list[ManagedLeagueResponse])
async def get_my_managed_leagues(
    current_user: dict = Depends(get_current_user),
):
    """List all managed leagues the user belongs to (with role)."""
    async with db_service.session() as session:
        result = await session.execute(
            select(LeagueMembership)
            .options(selectinload(LeagueMembership.league))
            .where(
                LeagueMembership.user_id == current_user["user_id"],
                LeagueMembership.status == "active",
            )
        )
        memberships = result.scalars().all()

        leagues = []
        for m in memberships:
            league = m.league
            # Count active members
            count_result = await session.execute(
                select(LeagueMembership).where(
                    LeagueMembership.league_id == league.id,
                    LeagueMembership.status == "active",
                )
            )
            member_count = len(count_result.scalars().all())

            leagues.append(
                ManagedLeagueResponse(
                    id=league.id,
                    external_league_id=league.external_league_id,
                    platform=league.platform,
                    name=league.name,
                    sport=league.sport,
                    season=league.season,
                    role=m.role,
                    member_count=member_count,
                    invite_code=league.invite_code if m.role == "commissioner" else None,
                )
            )

        return leagues


@router.get("/managed/{league_id}", response_model=ManagedLeagueResponse)
async def get_managed_league(
    league_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Get managed league details (must be a member)."""
    async with db_service.session() as session:
        result = await session.execute(
            select(LeagueMembership)
            .options(selectinload(LeagueMembership.league))
            .where(
                LeagueMembership.league_id == league_id,
                LeagueMembership.user_id == current_user["user_id"],
                LeagueMembership.status == "active",
            )
        )
        membership = result.scalar_one_or_none()

        if not membership:
            raise HTTPException(status_code=404, detail="League not found or not a member")

        league = membership.league

        count_result = await session.execute(
            select(LeagueMembership).where(
                LeagueMembership.league_id == league.id,
                LeagueMembership.status == "active",
            )
        )
        member_count = len(count_result.scalars().all())

        return ManagedLeagueResponse(
            id=league.id,
            external_league_id=league.external_league_id,
            platform=league.platform,
            name=league.name,
            sport=league.sport,
            season=league.season,
            role=membership.role,
            member_count=member_count,
            invite_code=league.invite_code if membership.role == "commissioner" else None,
        )


@router.get("/managed/{league_id}/members", response_model=list[MemberResponse])
async def get_league_members(
    league_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Get league member list. Commissioner sees all; members see active only."""
    async with db_service.session() as session:
        # Verify caller is a member
        caller_result = await session.execute(
            select(LeagueMembership).where(
                LeagueMembership.league_id == league_id,
                LeagueMembership.user_id == current_user["user_id"],
                LeagueMembership.status == "active",
            )
        )
        caller = caller_result.scalar_one_or_none()
        if not caller:
            raise HTTPException(status_code=403, detail="Not a member of this league")

        query = (
            select(LeagueMembership)
            .options(selectinload(LeagueMembership.user))
            .where(LeagueMembership.league_id == league_id)
        )
        if caller.role != "commissioner":
            query = query.where(LeagueMembership.status == "active")

        result = await session.execute(query)
        members = result.scalars().all()

        return [
            MemberResponse(
                user_id=m.user_id,
                email=m.user.email if m.user else "",
                name=m.user.name if m.user else "",
                role=m.role,
                external_team_id=m.external_team_id,
                status=m.status,
                joined_at=m.joined_at.isoformat() if m.joined_at else "",
            )
            for m in members
        ]


@router.post("/managed/{league_id}/invite", response_model=InviteResponse)
async def generate_invite(
    league_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Generate or regenerate invite code (commissioner only)."""
    async with db_service.session() as session:
        result = await session.execute(
            select(LeagueMembership).where(
                LeagueMembership.league_id == league_id,
                LeagueMembership.user_id == current_user["user_id"],
                LeagueMembership.role == "commissioner",
                LeagueMembership.status == "active",
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=403, detail="Only the commissioner can generate invites"
            )

        league_result = await session.execute(select(League).where(League.id == league_id))
        league = league_result.scalar_one_or_none()
        if not league:
            raise HTTPException(status_code=404, detail="League not found")

        league.invite_code = secrets.token_hex(16)
        session.add(league)
        await session.commit()

        return InviteResponse(
            invite_code=league.invite_code,
            invite_url=f"https://benchgoblins.com/leagues/join/{league.invite_code}",
        )


@router.post("/join/{invite_code}")
async def join_league(
    invite_code: str,
    current_user: dict = Depends(get_current_user),
):
    """Join a league via invite code."""
    async with db_service.session() as session:
        result = await session.execute(select(League).where(League.invite_code == invite_code))
        league = result.scalar_one_or_none()
        if not league:
            raise HTTPException(status_code=404, detail="Invalid invite code")

        # Check if already a member
        existing = await session.execute(
            select(LeagueMembership).where(
                LeagueMembership.league_id == league.id,
                LeagueMembership.user_id == current_user["user_id"],
            )
        )
        membership = existing.scalar_one_or_none()

        if membership:
            if membership.status == "active":
                return {"joined": False, "reason": "Already a member", "league_id": league.id}
            # Reactivate removed membership
            membership.status = "active"
            membership.joined_at = datetime.now(UTC)
            await session.commit()
            return {"joined": True, "league_id": league.id, "role": "member"}

        membership = LeagueMembership(
            league_id=league.id,
            user_id=current_user["user_id"],
            role="member",
            status="active",
        )
        session.add(membership)
        await session.commit()

        return {"joined": True, "league_id": league.id, "role": "member"}


@router.delete("/managed/{league_id}/members/{user_id}")
async def remove_member(
    league_id: int,
    user_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Remove a member from the league (commissioner only)."""
    if user_id == current_user["user_id"]:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    async with db_service.session() as session:
        # Verify caller is commissioner
        caller_result = await session.execute(
            select(LeagueMembership).where(
                LeagueMembership.league_id == league_id,
                LeagueMembership.user_id == current_user["user_id"],
                LeagueMembership.role == "commissioner",
                LeagueMembership.status == "active",
            )
        )
        if not caller_result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Only the commissioner can remove members")

        # Find and remove target member
        target_result = await session.execute(
            select(LeagueMembership).where(
                LeagueMembership.league_id == league_id,
                LeagueMembership.user_id == user_id,
                LeagueMembership.status == "active",
            )
        )
        target = target_result.scalar_one_or_none()
        if not target:
            raise HTTPException(status_code=404, detail="Member not found")

        target.status = "removed"
        await session.commit()

        return {"removed": True, "user_id": user_id}
