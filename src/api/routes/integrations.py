"""
Fantasy platform integration routes — ESPN, Sleeper, Yahoo.
"""

import logging
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from models.schemas import Sport
from services.database import db_service
from services.espn_fantasy import ESPNCredentials, espn_fantasy_service
from services.session import session_service
from services.sleeper import sleeper_service
from services.yahoo import yahoo_service

logger = logging.getLogger("benchgoblins")

router = APIRouter()


# ---------------------------------------------------------------------------
# Shared Helpers
# ---------------------------------------------------------------------------

# Ephemeral OAuth state (consumed in seconds, OK to lose on restart)
_yahoo_oauth_states: dict[str, str] = {}


@asynccontextmanager
async def _resolve_session(session_id: str):
    """Resolve a session_id string to a (db, Session) tuple.

    Auto-creates a "default" session for backward compatibility.
    Raises 503 if the database is not configured.
    """
    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")

    async with db_service.session() as db:
        session = await session_service.get_session_by_token(db, session_id)

        if not session and session_id == "default":
            session = await session_service.create_session(db, platform="web")
            await db.commit()

        if not session:
            raise HTTPException(status_code=401, detail="Invalid session")

        yield db, session


# ---------------------------------------------------------------------------
# ESPN Fantasy Models
# ---------------------------------------------------------------------------


class ESPNConnectRequest(BaseModel):
    """Request to connect ESPN Fantasy account."""

    swid: str = Field(..., description="ESPN SWID cookie value")
    espn_s2: str = Field(..., description="ESPN espn_s2 cookie value")


class ESPNConnectResponse(BaseModel):
    """Response after connecting ESPN account."""

    connected: bool
    user_id: str | None
    leagues_found: int


class FantasyLeagueResponse(BaseModel):
    """Fantasy league information."""

    id: str
    name: str
    sport: str
    season: int
    team_count: int
    scoring_type: str


class RosterPlayerResponse(BaseModel):
    """Player on a fantasy roster."""

    player_id: str
    espn_id: str
    name: str
    position: str
    team: str
    lineup_slot: str
    projected_points: float | None


# ---------------------------------------------------------------------------
# ESPN Fantasy Routes
# ---------------------------------------------------------------------------


@router.post("/integrations/espn/connect", response_model=ESPNConnectResponse)
async def connect_espn_account(
    request: ESPNConnectRequest, session_id: str = Query(default="default")
):
    """
    Connect an ESPN Fantasy account using cookie credentials.

    Users need to provide their SWID and espn_s2 cookies from ESPN.
    These can be found in browser DevTools after logging into ESPN Fantasy.
    """
    creds = ESPNCredentials(swid=request.swid, espn_s2=request.espn_s2)

    # Verify credentials work
    is_valid = await espn_fantasy_service.verify_credentials(creds)

    if not is_valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid ESPN credentials. Please check your SWID and espn_s2 values.",
        )

    # Store credentials in encrypted DB
    async with _resolve_session(session_id) as (db, session):
        await session_service.store_credential(
            db, session, "espn", {"swid": request.swid, "espn_s2": request.espn_s2}
        )
        await db.commit()

    # Get user ID and count leagues
    user_id = await espn_fantasy_service.get_user_id(creds)
    leagues = await espn_fantasy_service.get_user_leagues(creds)

    return ESPNConnectResponse(
        connected=True,
        user_id=user_id,
        leagues_found=len(leagues),
    )


@router.get("/integrations/espn/leagues", response_model=list[FantasyLeagueResponse])
async def get_espn_leagues(
    session_id: str = Query(default="default"),
    sport: Sport | None = None,
):
    """
    Get all fantasy leagues for the connected ESPN account.

    Optionally filter by sport.
    """
    async with _resolve_session(session_id) as (db, session):
        cred_data = await session_service.get_credential(db, session, "espn")

    if not cred_data:
        raise HTTPException(
            status_code=401,
            detail="ESPN account not connected. Call /integrations/espn/connect first.",
        )

    creds = ESPNCredentials(swid=cred_data["swid"], espn_s2=cred_data["espn_s2"])
    leagues = await espn_fantasy_service.get_user_leagues(
        creds,
        sport=sport.value if sport else None,
    )

    return [
        FantasyLeagueResponse(
            id=league.id,
            name=league.name,
            sport=league.sport,
            season=league.season,
            team_count=league.team_count,
            scoring_type=league.scoring_type,
        )
        for league in leagues
    ]


@router.get("/integrations/espn/leagues/{league_id}/roster", response_model=list[RosterPlayerResponse])
async def get_espn_roster(
    league_id: str,
    sport: Sport,
    team_id: int = Query(..., description="Team ID within the league"),
    session_id: str = Query(default="default"),
):
    """
    Get the roster for a specific team in an ESPN Fantasy league.
    """
    async with _resolve_session(session_id) as (db, session):
        cred_data = await session_service.get_credential(db, session, "espn")

    if not cred_data:
        raise HTTPException(
            status_code=401,
            detail="ESPN account not connected. Call /integrations/espn/connect first.",
        )

    creds = ESPNCredentials(swid=cred_data["swid"], espn_s2=cred_data["espn_s2"])
    roster = await espn_fantasy_service.get_roster(
        creds=creds,
        league_id=league_id,
        team_id=team_id,
        sport=sport.value,
    )

    return [
        RosterPlayerResponse(
            player_id=p.player_id,
            espn_id=p.espn_id,
            name=p.name,
            position=p.position,
            team=p.team,
            lineup_slot=p.lineup_slot,
            projected_points=p.projected_points,
        )
        for p in roster
    ]


@router.delete("/integrations/espn/disconnect")
async def disconnect_espn_account(session_id: str = Query(default="default")):
    """
    Disconnect ESPN Fantasy account and clear stored credentials.
    """
    try:
        async with _resolve_session(session_id) as (db, session):
            await session_service.delete_credential(db, session, "espn")
            await db.commit()
    except HTTPException:
        pass  # Already disconnected or DB unavailable — idempotent

    return {"status": "disconnected"}


@router.get("/integrations/espn/status")
async def get_espn_status(session_id: str = Query(default="default")):
    """
    Check if ESPN Fantasy account is connected.
    """
    try:
        async with _resolve_session(session_id) as (db, session):
            cred_data = await session_service.get_credential(db, session, "espn")
    except HTTPException:
        return {"connected": False, "user_id": None}

    if cred_data:
        creds = ESPNCredentials(swid=cred_data["swid"], espn_s2=cred_data["espn_s2"])
        user_id = await espn_fantasy_service.get_user_id(creds)
        return {"connected": True, "user_id": user_id}

    return {"connected": False, "user_id": None}


# ---------------------------------------------------------------------------
# Sleeper Models
# ---------------------------------------------------------------------------


class SleeperUserResponse(BaseModel):
    """Sleeper user information."""

    user_id: str
    username: str
    display_name: str
    avatar: str | None


class SleeperLeagueResponse(BaseModel):
    """Sleeper fantasy league information."""

    league_id: str
    name: str
    sport: str
    season: str
    status: str
    total_rosters: int


class SleeperPlayerResponse(BaseModel):
    """Sleeper player information."""

    player_id: str
    full_name: str
    team: str | None
    position: str
    status: str
    injury_status: str | None


class SleeperRosterResponse(BaseModel):
    """Sleeper roster with players."""

    roster_id: int
    owner_id: str
    players: list[SleeperPlayerResponse]
    starters: list[str]


# ---------------------------------------------------------------------------
# Sleeper Routes
# ---------------------------------------------------------------------------


@router.get("/integrations/sleeper/user/{username}", response_model=SleeperUserResponse)
async def get_sleeper_user(username: str):
    """
    Look up a Sleeper user by username.

    No authentication required - Sleeper API is public.
    """
    user = await sleeper_service.get_user(username)

    if not user:
        raise HTTPException(status_code=404, detail="Sleeper user not found")

    return SleeperUserResponse(
        user_id=user.user_id,
        username=user.username,
        display_name=user.display_name,
        avatar=user.avatar,
    )


@router.get("/integrations/sleeper/user/{user_id}/leagues", response_model=list[SleeperLeagueResponse])
async def get_sleeper_leagues(
    user_id: str,
    sport: str = Query(default="nfl", description="Sport: nfl, nba, mlb, nhl"),
    season: str = Query(default="2024", description="Season year"),
):
    """
    Get all Sleeper leagues for a user.

    No authentication required.
    """
    leagues = await sleeper_service.get_user_leagues(user_id, sport, season)

    return [
        SleeperLeagueResponse(
            league_id=league.league_id,
            name=league.name,
            sport=league.sport,
            season=league.season,
            status=league.status,
            total_rosters=league.total_rosters,
        )
        for league in leagues
    ]


@router.get(
    "/integrations/sleeper/league/{league_id}/roster/{user_id}",
    response_model=SleeperRosterResponse,
)
async def get_sleeper_roster(
    league_id: str,
    user_id: str,
    sport: str = Query(default="nfl", description="Sport for player lookup"),
):
    """
    Get a user's roster in a Sleeper league with full player details.
    """
    roster = await sleeper_service.get_user_roster(league_id, user_id)

    if not roster:
        raise HTTPException(status_code=404, detail="Roster not found")

    # Get player details
    players = await sleeper_service.get_players_by_ids(roster.players, sport)

    return SleeperRosterResponse(
        roster_id=roster.roster_id,
        owner_id=roster.owner_id,
        players=[
            SleeperPlayerResponse(
                player_id=p.player_id,
                full_name=p.full_name,
                team=p.team,
                position=p.position,
                status=p.status,
                injury_status=p.injury_status,
            )
            for p in players
        ],
        starters=roster.starters,
    )


@router.get("/integrations/sleeper/trending/{sport}")
async def get_sleeper_trending(
    sport: str,
    trend_type: str = Query(default="add", description="'add' or 'drop'"),
    limit: int = Query(default=25, ge=1, le=50),
):
    """
    Get trending players on Sleeper (most added/dropped in last 24h).

    Useful for waiver wire decisions.
    """
    trending = await sleeper_service.get_trending_players(sport, trend_type, limit)

    # Enrich with player names
    player_ids = [t.get("player_id") for t in trending if t.get("player_id")]
    players = await sleeper_service.get_players_by_ids(player_ids, sport)
    player_map = {p.player_id: p for p in players}

    return [
        {
            "player_id": t.get("player_id"),
            "count": t.get("count", 0),
            "player": {
                "full_name": player_map[t["player_id"]].full_name,
                "team": player_map[t["player_id"]].team,
                "position": player_map[t["player_id"]].position,
            }
            if t.get("player_id") in player_map
            else None,
        }
        for t in trending
    ]


# ---------------------------------------------------------------------------
# Yahoo Fantasy Models
# ---------------------------------------------------------------------------


class YahooAuthResponse(BaseModel):
    """Response with OAuth authorization URL."""

    auth_url: str
    state: str


class YahooTokenRequest(BaseModel):
    """Request to exchange OAuth code for tokens."""

    code: str = Field(..., description="OAuth authorization code")
    redirect_uri: str = Field(..., description="Same redirect URI used in auth request")
    state: str | None = Field(None, description="State parameter for verification")


class YahooTokenResponse(BaseModel):
    """Response with OAuth tokens."""

    access_token: str
    refresh_token: str
    expires_in: int
    expires_at: float


class YahooLeagueResponse(BaseModel):
    """Yahoo fantasy league information."""

    league_key: str
    league_id: str
    name: str
    sport: str
    season: str
    num_teams: int
    scoring_type: str


class YahooTeamResponse(BaseModel):
    """Yahoo fantasy team information."""

    team_key: str
    team_id: str
    name: str
    logo_url: str | None


class YahooPlayerResponse(BaseModel):
    """Yahoo player information."""

    player_key: str
    player_id: str
    name: str
    team_abbrev: str | None
    position: str
    status: str
    injury_status: str | None


# ---------------------------------------------------------------------------
# Yahoo Fantasy Routes
# ---------------------------------------------------------------------------


@router.get("/integrations/yahoo/auth", response_model=YahooAuthResponse)
async def get_yahoo_auth_url(
    redirect_uri: str = Query(..., description="OAuth redirect URI"),
    session_id: str = Query(default="default"),
):
    """
    Get Yahoo OAuth authorization URL.

    User should be redirected to this URL to authorize the app.
    After authorization, Yahoo will redirect back with an authorization code.
    """
    state = secrets.token_urlsafe(16)

    # Ephemeral state — consumed in seconds, OK to lose on restart
    _yahoo_oauth_states[f"{session_id}_state"] = state

    auth_url = yahoo_service.get_auth_url(redirect_uri, state)

    return YahooAuthResponse(auth_url=auth_url, state=state)


@router.post("/integrations/yahoo/token", response_model=YahooTokenResponse)
async def exchange_yahoo_code(
    request: YahooTokenRequest,
    session_id: str = Query(default="default"),
):
    """
    Exchange OAuth authorization code for access tokens.

    Call this after user authorizes the app and is redirected back
    with an authorization code.
    """
    # Verify state if provided
    stored_state = _yahoo_oauth_states.get(f"{session_id}_state")
    if request.state and stored_state and request.state != stored_state:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    tokens = await yahoo_service.exchange_code(request.code, request.redirect_uri)

    if not tokens:
        raise HTTPException(
            status_code=400,
            detail="Failed to exchange code for tokens. Code may be expired or invalid.",
        )

    # Store tokens in encrypted DB
    async with _resolve_session(session_id) as (db, session):
        await session_service.store_credential(
            db,
            session,
            "yahoo",
            {
                "access_token": tokens.access_token,
                "refresh_token": tokens.refresh_token,
                "expires_at": tokens.expires_at,
            },
        )
        await db.commit()

    # Clean up ephemeral state
    _yahoo_oauth_states.pop(f"{session_id}_state", None)

    return YahooTokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        expires_at=tokens.expires_at,
    )


@router.post("/integrations/yahoo/refresh", response_model=YahooTokenResponse)
async def refresh_yahoo_token(
    session_id: str = Query(default="default"),
):
    """
    Refresh an expired Yahoo access token.

    Uses the stored refresh token to get a new access token.
    """
    async with _resolve_session(session_id) as (db, session):
        stored = await session_service.get_credential(db, session, "yahoo")

        if not stored or "refresh_token" not in stored:
            raise HTTPException(
                status_code=401,
                detail="No Yahoo refresh token found. Complete OAuth flow first.",
            )

        tokens = await yahoo_service.refresh_token(stored["refresh_token"])

        if not tokens:
            raise HTTPException(
                status_code=401,
                detail="Failed to refresh token. User may need to re-authorize.",
            )

        # Update stored tokens
        await session_service.store_credential(
            db,
            session,
            "yahoo",
            {
                "access_token": tokens.access_token,
                "refresh_token": tokens.refresh_token,
                "expires_at": tokens.expires_at,
            },
        )
        await db.commit()

    return YahooTokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        expires_at=tokens.expires_at,
    )


async def _get_yahoo_token(session_id: str) -> str:
    """Get valid Yahoo access token, refreshing if needed."""
    async with _resolve_session(session_id) as (db, session):
        stored = await session_service.get_credential(db, session, "yahoo")

        if not stored:
            raise HTTPException(
                status_code=401,
                detail="Yahoo account not connected. Complete OAuth flow first.",
            )

        # Refresh if expired (with 60s buffer)
        if stored.get("expires_at", 0) < time.time() + 60:
            tokens = await yahoo_service.refresh_token(stored["refresh_token"])
            if tokens:
                await session_service.store_credential(
                    db,
                    session,
                    "yahoo",
                    {
                        "access_token": tokens.access_token,
                        "refresh_token": tokens.refresh_token,
                        "expires_at": tokens.expires_at,
                    },
                )
                await db.commit()
                return tokens.access_token
            else:
                raise HTTPException(
                    status_code=401,
                    detail="Failed to refresh Yahoo token. Please re-authorize.",
                )

        return stored["access_token"]


@router.get("/integrations/yahoo/leagues", response_model=list[YahooLeagueResponse])
async def get_yahoo_leagues(
    session_id: str = Query(default="default"),
    sport: str | None = Query(default=None, description="Filter by sport"),
):
    """
    Get all Yahoo Fantasy leagues for the connected account.
    """
    access_token = await _get_yahoo_token(session_id)
    leagues = await yahoo_service.get_user_leagues(access_token, sport)

    return [
        YahooLeagueResponse(
            league_key=league.league_key,
            league_id=league.league_id,
            name=league.name,
            sport=league.sport,
            season=league.season,
            num_teams=league.num_teams,
            scoring_type=league.scoring_type,
        )
        for league in leagues
    ]


@router.get("/integrations/yahoo/teams", response_model=list[YahooTeamResponse])
async def get_yahoo_teams(
    session_id: str = Query(default="default"),
    league_key: str | None = Query(default=None, description="Filter by league key"),
):
    """
    Get all Yahoo Fantasy teams for the connected account.
    """
    access_token = await _get_yahoo_token(session_id)
    teams = await yahoo_service.get_user_teams(access_token, league_key or "")

    return [
        YahooTeamResponse(
            team_key=team.team_key,
            team_id=team.team_id,
            name=team.name,
            logo_url=team.logo_url,
        )
        for team in teams
    ]


@router.get("/integrations/yahoo/roster/{team_key}", response_model=list[YahooPlayerResponse])
async def get_yahoo_roster(
    team_key: str,
    session_id: str = Query(default="default"),
    week: int | None = Query(default=None, description="Week number for roster"),
):
    """
    Get roster for a Yahoo Fantasy team.
    """
    access_token = await _get_yahoo_token(session_id)
    players = await yahoo_service.get_team_roster(access_token, team_key, week)

    return [
        YahooPlayerResponse(
            player_key=player.player_key,
            player_id=player.player_id,
            name=player.name,
            team_abbrev=player.team_abbrev,
            position=player.position,
            status=player.status,
            injury_status=player.injury_status,
        )
        for player in players
    ]


@router.get("/integrations/yahoo/standings/{league_key}")
async def get_yahoo_standings(
    league_key: str,
    session_id: str = Query(default="default"),
):
    """
    Get standings for a Yahoo Fantasy league.
    """
    access_token = await _get_yahoo_token(session_id)
    standings = await yahoo_service.get_league_standings(access_token, league_key)

    return {"standings": standings}


@router.delete("/integrations/yahoo/disconnect")
async def disconnect_yahoo_account(session_id: str = Query(default="default")):
    """
    Disconnect Yahoo Fantasy account and clear stored tokens.
    """
    try:
        async with _resolve_session(session_id) as (db, session):
            await session_service.delete_credential(db, session, "yahoo")
            await db.commit()
    except HTTPException:
        pass  # Already disconnected or DB unavailable — idempotent

    # Clean up ephemeral OAuth state
    _yahoo_oauth_states.pop(f"{session_id}_state", None)

    return {"status": "disconnected"}


@router.get("/integrations/yahoo/status")
async def get_yahoo_status(session_id: str = Query(default="default")):
    """
    Check if Yahoo Fantasy account is connected.
    """
    try:
        async with _resolve_session(session_id) as (db, session):
            stored = await session_service.get_credential(db, session, "yahoo")
    except HTTPException:
        return {"connected": False}

    if stored and "access_token" in stored:
        expires_at = stored.get("expires_at", 0)
        return {
            "connected": True,
            "expires_at": expires_at,
            "expired": expires_at < time.time(),
        }

    return {"connected": False}
