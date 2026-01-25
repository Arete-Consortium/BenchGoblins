"""
GameSpace API — Fantasy Sports Decision Engine
"""

import os
import sys
from contextlib import asynccontextmanager
from enum import Enum
from uuid import UUID

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from models.database import Decision as DecisionModel
from services.claude import claude_service
from services.database import db_service
from services.espn import espn_service, format_player_context
from services.espn_fantasy import ESPNCredentials, espn_fantasy_service
from services.notifications import notification_service, PushNotification
from services.redis import redis_service
from services.router import QueryComplexity, classify_query, extract_players_from_query

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup app resources"""
    # Initialize services
    if claude_service.is_available:
        print("Claude API configured and ready")
    else:
        print("WARNING: ANTHROPIC_API_KEY not set - Claude integration disabled")

    # Connect to PostgreSQL
    if db_service.is_configured:
        try:
            await db_service.connect()
            print("PostgreSQL connected")
        except Exception as e:
            print(f"WARNING: PostgreSQL connection failed: {e}")
    else:
        print("WARNING: DATABASE_URL not set - persistence disabled")

    # Connect to Redis
    if redis_service.is_configured:
        try:
            await redis_service.connect()
            print("Redis connected")
        except Exception as e:
            print(f"WARNING: Redis connection failed: {e}")
    else:
        print("WARNING: REDIS_URL not set - caching disabled")

    print("ESPN data service ready")
    yield

    # Cleanup
    await espn_service.close()
    await espn_fantasy_service.close()
    await notification_service.close()
    await db_service.disconnect()
    await redis_service.disconnect()


# ---------------------------------------------------------------------------
# App Setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="GameSpace API",
    description="Fantasy sports decision engine using role stability, spatial opportunity, and matchup context.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Enums & Models
# ---------------------------------------------------------------------------


class Sport(str, Enum):
    NBA = "nba"
    NFL = "nfl"
    MLB = "mlb"
    NHL = "nhl"


class RiskMode(str, Enum):
    FLOOR = "floor"
    MEDIAN = "median"
    CEILING = "ceiling"


class DecisionType(str, Enum):
    START_SIT = "start_sit"
    TRADE = "trade"
    WAIVER = "waiver"
    EXPLAIN = "explain"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DecisionRequest(BaseModel):
    """Request body for /decide endpoint"""

    sport: Sport
    risk_mode: RiskMode = RiskMode.MEDIAN
    decision_type: DecisionType = DecisionType.START_SIT
    query: str = Field(
        ...,
        description="Natural language query, e.g., 'Should I start Jalen Brunson or Tyrese Maxey?'",
    )
    player_a: str | None = Field(None, description="First player name (optional if in query)")
    player_b: str | None = Field(None, description="Second player name (optional if in query)")
    league_type: str | None = Field(None, description="e.g., 'points', 'categories', 'half-ppr'")


class DecisionResponse(BaseModel):
    """Response from /decide endpoint"""

    decision: str
    confidence: Confidence
    rationale: str
    details: dict | None = None
    source: str = Field(..., description="'local' or 'claude'")


class PlayerSearchRequest(BaseModel):
    """Request body for /players/search"""

    query: str
    sport: Sport
    limit: int = 10


class Player(BaseModel):
    """Player data model"""

    id: str
    name: str
    team: str
    position: str
    sport: Sport
    headshot_url: str | None = None


class PlayerDetail(BaseModel):
    """Detailed player information with stats"""

    id: str
    name: str
    team: str
    team_abbrev: str
    position: str
    sport: Sport
    headshot_url: str | None = None
    stats: dict | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    redis_healthy = await redis_service.health_check() if redis_service.is_connected else False
    return {
        "status": "healthy",
        "version": "0.3.0",
        "claude_available": claude_service.is_available,
        "espn_available": True,
        "postgres_connected": db_service.is_configured,
        "redis_connected": redis_healthy,
    }


@app.post("/players/search", response_model=list[Player])
async def search_players(request: PlayerSearchRequest):
    """Search for players by name using ESPN data."""
    players = await espn_service.search_players(
        query=request.query,
        sport=request.sport.value,
        limit=request.limit,
    )

    return [
        Player(
            id=p.id,
            name=p.name,
            team=p.team,
            position=p.position,
            sport=request.sport,
            headshot_url=p.headshot_url,
        )
        for p in players
    ]


@app.get("/players/{sport}/{player_id}", response_model=PlayerDetail)
async def get_player(sport: Sport, player_id: str):
    """Get detailed player information and stats."""
    player = await espn_service.get_player(player_id, sport.value)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    stats = await espn_service.get_player_stats(player_id, sport.value)

    stats_dict = None
    if stats:
        stats_dict = {
            k: v
            for k, v in stats.__dict__.items()
            if v is not None and k not in ("player_id", "sport")
        }

    return PlayerDetail(
        id=player.id,
        name=player.name,
        team=player.team,
        team_abbrev=player.team_abbrev,
        position=player.position,
        sport=sport,
        headshot_url=player.headshot_url,
        stats=stats_dict,
    )


async def _store_decision(
    request: DecisionRequest,
    response: DecisionResponse,
    player_a_name: str | None = None,
    player_b_name: str | None = None,
    player_context: str | None = None,
) -> None:
    """Store decision in database for history and analytics."""
    if not db_service.is_configured:
        return

    try:
        async with db_service.session() as session:
            decision = DecisionModel(
                sport=request.sport.value,
                risk_mode=request.risk_mode.value,
                decision_type=request.decision_type.value,
                query=request.query,
                player_a_name=player_a_name,
                player_b_name=player_b_name,
                decision=response.decision,
                confidence=response.confidence.value,
                rationale=response.rationale,
                source=response.source,
                score_a=response.details.get("player_a", {}).get("score") if response.details else None,
                score_b=response.details.get("player_b", {}).get("score") if response.details else None,
                margin=response.details.get("margin") if response.details else None,
                league_type=request.league_type,
                player_context=player_context,
            )
            session.add(decision)
    except Exception as e:
        # Don't fail the request if persistence fails
        print(f"Failed to store decision: {e}")


@app.post("/decide", response_model=DecisionResponse)
async def make_decision(request: DecisionRequest):
    """
    Make a fantasy sports decision.

    Routes to local scoring engine for simple queries,
    Claude API for complex queries.
    """
    # Extract players from query if not provided
    player_a = request.player_a
    player_b = request.player_b

    if not player_a or not player_b:
        extracted_a, extracted_b = extract_players_from_query(request.query)
        player_a = player_a or extracted_a
        player_b = player_b or extracted_b

    # Fetch real player data
    player_a_data = None
    player_b_data = None
    player_context = None

    if player_a:
        player_a_data = await espn_service.find_player_by_name(player_a, request.sport.value)
    if player_b:
        player_b_data = await espn_service.find_player_by_name(player_b, request.sport.value)

    # Build context string for Claude
    if player_a_data or player_b_data:
        context_parts = []
        if player_a_data:
            info, stats = player_a_data
            context_parts.append(
                f"Player A:\n{format_player_context(info, stats, request.sport.value)}"
            )
        if player_b_data:
            info, stats = player_b_data
            context_parts.append(
                f"Player B:\n{format_player_context(info, stats, request.sport.value)}"
            )
        player_context = "\n\n".join(context_parts)

    # Classify query complexity
    complexity = classify_query(
        query=request.query,
        decision_type=request.decision_type.value,
        player_a=player_a,
        player_b=player_b,
    )

    # Check Redis cache for Claude decisions first
    if redis_service.is_connected:
        cached = await redis_service.get_decision(
            request.sport.value, request.risk_mode.value, request.query
        )
        if cached:
            confidence_map = {
                "low": Confidence.LOW,
                "medium": Confidence.MEDIUM,
                "high": Confidence.HIGH,
            }
            return DecisionResponse(
                decision=cached["decision"],
                confidence=confidence_map.get(cached.get("confidence", "medium"), Confidence.MEDIUM),
                rationale=cached.get("rationale", ""),
                details=cached.get("details"),
                source=cached.get("source", "claude") + "_cached",
            )

    # Route based on complexity
    if complexity == QueryComplexity.SIMPLE and player_a_data and player_b_data:
        # Use local scoring engine with real data
        response = await _local_decision(request, player_a, player_b, player_a_data, player_b_data)
    else:
        # Use Claude for complex queries or when we need more reasoning
        response = await _claude_decision(request, player_a, player_b, player_context)

    # Store decision in database (async, non-blocking)
    await _store_decision(request, response, player_a, player_b, player_context)

    # Cache Claude decisions in Redis
    if response.source == "claude" and redis_service.is_connected:
        await redis_service.set_decision(
            request.sport.value,
            request.risk_mode.value,
            request.query,
            {
                "decision": response.decision,
                "confidence": response.confidence.value,
                "rationale": response.rationale,
                "details": response.details,
                "source": response.source,
            },
        )

    return response


async def _local_decision(
    request: DecisionRequest,
    player_a_name: str | None,
    player_b_name: str | None,
    player_a_data: tuple | None,
    player_b_data: tuple | None,
) -> DecisionResponse:
    """
    Handle simple A vs B decisions locally using real stats.
    """
    if not player_a_data or not player_b_data:
        # Fall back to Claude if we don't have data
        return await _claude_decision(request, player_a_name, player_b_name, None)

    info_a, stats_a = player_a_data
    info_b, stats_b = player_b_data

    # Calculate simple scoring based on available stats
    score_a = _calculate_simple_score(stats_a, request.sport.value, request.risk_mode.value)
    score_b = _calculate_simple_score(stats_b, request.sport.value, request.risk_mode.value)

    margin = abs(score_a - score_b)

    # Determine winner and confidence
    if score_a > score_b:
        decision = f"Start {info_a.name}"
        winner_stats = stats_a
        loser_stats = stats_b
    else:
        decision = f"Start {info_b.name}"
        winner_stats = stats_b
        loser_stats = stats_a

    # Confidence based on margin
    if margin < 5:
        confidence = Confidence.LOW
    elif margin < 15:
        confidence = Confidence.MEDIUM
    else:
        confidence = Confidence.HIGH

    # Build rationale based on sport
    rationale = _build_rationale(
        request.sport.value,
        request.risk_mode.value,
        info_a if score_a > score_b else info_b,
        winner_stats,
    )

    return DecisionResponse(
        decision=decision,
        confidence=confidence,
        rationale=rationale,
        details={
            "player_a": {
                "name": info_a.name,
                "team": info_a.team_abbrev,
                "score": round(score_a, 1),
            },
            "player_b": {
                "name": info_b.name,
                "team": info_b.team_abbrev,
                "score": round(score_b, 1),
            },
            "margin": round(margin, 1),
            "risk_mode": request.risk_mode.value,
        },
        source="local",
    )


def _calculate_simple_score(stats, sport: str, risk_mode: str) -> float:
    """Calculate a simple fantasy score for comparison."""
    if not stats:
        return 0.0

    score = 0.0

    if sport == "nba":
        # Base on PPG, RPG, APG with risk mode adjustments
        ppg = stats.points_per_game or 0
        rpg = stats.rebounds_per_game or 0
        apg = stats.assists_per_game or 0
        mpg = stats.minutes_per_game or 0
        gp = stats.games_played or 0
        gs = stats.games_started or 0

        # Base fantasy score
        score = ppg + (rpg * 1.2) + (apg * 1.5)

        # Risk mode adjustments
        if risk_mode == "floor":
            # Prioritize starters, minutes stability
            starter_bonus = 10 if gs >= gp * 0.8 else 0
            minutes_bonus = min(mpg / 3, 10)  # Up to 10 pts for 30+ mpg
            score += starter_bonus + minutes_bonus
        elif risk_mode == "ceiling":
            # Prioritize scoring upside
            score += ppg * 0.3  # Extra weight on points
            if stats.usage_rate:
                score += stats.usage_rate * 0.5

    elif sport == "nfl":
        # Fantasy points estimation
        if stats.pass_yards:
            score += stats.pass_yards * 0.04 + (stats.pass_tds or 0) * 4
        if stats.rush_yards:
            score += stats.rush_yards * 0.1 + (stats.rush_tds or 0) * 6
        if stats.receiving_yards:
            score += stats.receiving_yards * 0.1 + (stats.receiving_tds or 0) * 6
            score += (stats.receptions or 0) * 0.5  # Half PPR

        if risk_mode == "floor":
            # Value volume
            score += (stats.targets or 0) * 0.2
        elif risk_mode == "ceiling":
            # Value TD potential
            score += (
                (stats.pass_tds or 0) + (stats.rush_tds or 0) + (stats.receiving_tds or 0)
            ) * 2

    elif sport == "mlb":
        if stats.batting_avg:
            # Hitter
            score = (
                (stats.home_runs or 0) * 4 + (stats.rbis or 0) * 1 + (stats.stolen_bases or 0) * 2
            )
            if stats.ops:
                score += stats.ops * 10
        elif stats.era:
            # Pitcher
            score = (stats.wins or 0) * 5 + (stats.strikeouts or 0) * 0.5
            score -= (stats.era or 4) * 2  # Lower ERA is better

    elif sport == "nhl":
        score = (stats.goals or 0) * 3 + (stats.assists_nhl or 0) * 2
        if stats.plus_minus:
            score += stats.plus_minus * 0.5

    return score


def _build_rationale(sport: str, risk_mode: str, winner_info, winner_stats) -> str:
    """Build a rationale string for the decision."""
    name = winner_info.name

    if sport == "nba":
        ppg = winner_stats.points_per_game or 0
        mpg = winner_stats.minutes_per_game or 0
        return (
            f"{name} has the edge with {ppg:.1f} PPG on {mpg:.1f} minutes. "
            f"For {risk_mode} mode, the role stability and usage support this pick."
        )
    elif sport == "nfl":
        if winner_stats.pass_yards:
            return f"{name} offers strong passing production for your {risk_mode} strategy."
        elif winner_stats.receiving_yards:
            targets = winner_stats.targets or 0
            return f"{name} has consistent target share ({targets:.0f} targets), good for {risk_mode} mode."
        else:
            return f"{name} has the better rushing floor for {risk_mode} mode."
    elif sport == "mlb":
        return f"{name} has the statistical edge for {risk_mode} mode."
    elif sport == "nhl":
        return f"{name} offers better production for {risk_mode} strategy."

    return f"{name} is the recommended start for {risk_mode} mode."


async def _claude_decision(
    request: DecisionRequest,
    player_a: str | None,
    player_b: str | None,
    player_context: str | None,
) -> DecisionResponse:
    """Handle complex decisions using Claude API with real player context."""
    if not claude_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Claude API not configured. Set ANTHROPIC_API_KEY environment variable.",
        )

    try:
        result = await claude_service.make_decision(
            query=request.query,
            sport=request.sport.value,
            risk_mode=request.risk_mode.value,
            decision_type=request.decision_type.value,
            player_a=player_a,
            player_b=player_b,
            league_type=request.league_type,
            player_context=player_context,  # Real stats injected here
        )

        # Map confidence string to enum
        confidence_map = {
            "low": Confidence.LOW,
            "medium": Confidence.MEDIUM,
            "high": Confidence.HIGH,
        }
        confidence = confidence_map.get(result.get("confidence", "medium"), Confidence.MEDIUM)

        return DecisionResponse(
            decision=result["decision"],
            confidence=confidence,
            rationale=result["rationale"],
            details=result.get("details"),
            source="claude",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing request: {str(e)}",
        )


@app.post("/decide/stream")
async def make_decision_stream(request: DecisionRequest):
    """
    Stream a fantasy sports decision (Server-Sent Events).

    Returns streamed text chunks from Claude for faster perceived response.
    Complex queries only - simple queries should use /decide.
    """
    if not claude_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Claude API not configured. Set ANTHROPIC_API_KEY environment variable.",
        )

    # Extract players from query if not provided
    player_a = request.player_a
    player_b = request.player_b

    if not player_a or not player_b:
        extracted_a, extracted_b = extract_players_from_query(request.query)
        player_a = player_a or extracted_a
        player_b = player_b or extracted_b

    # Fetch player data for context
    player_context = None
    if player_a or player_b:
        context_parts = []
        if player_a:
            player_a_data = await espn_service.find_player_by_name(player_a, request.sport.value)
            if player_a_data:
                info, stats = player_a_data
                context_parts.append(
                    f"Player A:\n{format_player_context(info, stats, request.sport.value)}"
                )
        if player_b:
            player_b_data = await espn_service.find_player_by_name(player_b, request.sport.value)
            if player_b_data:
                info, stats = player_b_data
                context_parts.append(
                    f"Player B:\n{format_player_context(info, stats, request.sport.value)}"
                )
        if context_parts:
            player_context = "\n\n".join(context_parts)

    async def event_generator():
        """Generate Server-Sent Events."""
        try:
            async for chunk in claude_service.make_decision_stream(
                query=request.query,
                sport=request.sport.value,
                risk_mode=request.risk_mode.value,
                decision_type=request.decision_type.value,
                player_a=player_a,
                player_b=player_b,
                league_type=request.league_type,
                player_context=player_context,
            ):
                # Format as SSE
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.get("/cache/stats")
async def get_cache_stats():
    """Get cache statistics (Claude in-memory + Redis)."""
    claude_stats = claude_service.get_cache_stats()
    redis_stats = await redis_service.get_stats()
    return {
        "claude_memory_cache": claude_stats,
        "redis_cache": redis_stats,
    }


@app.post("/cache/clear")
async def clear_cache():
    """Clear all caches (Claude in-memory + Redis)."""
    claude_service.clear_cache()
    if redis_service.is_connected:
        await redis_service.clear_all()
    return {"status": "cleared"}


class DecisionHistoryItem(BaseModel):
    """Decision history item for API response."""

    id: str
    sport: str
    risk_mode: str
    decision_type: str
    query: str
    player_a_name: str | None
    player_b_name: str | None
    decision: str
    confidence: str
    rationale: str | None
    source: str
    score_a: float | None
    score_b: float | None
    margin: float | None
    created_at: str


@app.get("/history", response_model=list[DecisionHistoryItem])
async def get_decision_history(
    limit: int = Query(default=20, ge=1, le=100),
    sport: Sport | None = None,
):
    """
    Get recent decision history.

    Optionally filter by sport.
    """
    if not db_service.is_configured:
        return []

    try:
        async with db_service.session() as session:
            query = select(DecisionModel).order_by(DecisionModel.created_at.desc()).limit(limit)

            if sport:
                query = query.where(DecisionModel.sport == sport.value)

            result = await session.execute(query)
            decisions = result.scalars().all()

            return [
                DecisionHistoryItem(
                    id=str(d.id),
                    sport=d.sport,
                    risk_mode=d.risk_mode,
                    decision_type=d.decision_type,
                    query=d.query,
                    player_a_name=d.player_a_name,
                    player_b_name=d.player_b_name,
                    decision=d.decision,
                    confidence=d.confidence,
                    rationale=d.rationale,
                    source=d.source,
                    score_a=float(d.score_a) if d.score_a else None,
                    score_b=float(d.score_b) if d.score_b else None,
                    margin=float(d.margin) if d.margin else None,
                    created_at=d.created_at.isoformat(),
                )
                for d in decisions
            ]
    except Exception as e:
        print(f"Failed to fetch history: {e}")
        return []


# ---------------------------------------------------------------------------
# ESPN Fantasy Integration Routes
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


# In-memory credential storage (per session)
# TODO: Move to Redis or database with encryption for production
_espn_credentials: dict[str, ESPNCredentials] = {}


@app.post("/integrations/espn/connect", response_model=ESPNConnectResponse)
async def connect_espn_account(request: ESPNConnectRequest, session_id: str = Query(default="default")):
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

    # Store credentials for this session
    _espn_credentials[session_id] = creds

    # Get user ID and count leagues
    user_id = await espn_fantasy_service.get_user_id(creds)
    leagues = await espn_fantasy_service.get_user_leagues(creds)

    return ESPNConnectResponse(
        connected=True,
        user_id=user_id,
        leagues_found=len(leagues),
    )


@app.get("/integrations/espn/leagues", response_model=list[FantasyLeagueResponse])
async def get_espn_leagues(
    session_id: str = Query(default="default"),
    sport: Sport | None = None,
):
    """
    Get all fantasy leagues for the connected ESPN account.

    Optionally filter by sport.
    """
    creds = _espn_credentials.get(session_id)

    if not creds:
        raise HTTPException(
            status_code=401,
            detail="ESPN account not connected. Call /integrations/espn/connect first.",
        )

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


@app.get("/integrations/espn/leagues/{league_id}/roster", response_model=list[RosterPlayerResponse])
async def get_espn_roster(
    league_id: str,
    sport: Sport,
    team_id: int = Query(..., description="Team ID within the league"),
    session_id: str = Query(default="default"),
):
    """
    Get the roster for a specific team in an ESPN Fantasy league.
    """
    creds = _espn_credentials.get(session_id)

    if not creds:
        raise HTTPException(
            status_code=401,
            detail="ESPN account not connected. Call /integrations/espn/connect first.",
        )

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


@app.delete("/integrations/espn/disconnect")
async def disconnect_espn_account(session_id: str = Query(default="default")):
    """
    Disconnect ESPN Fantasy account and clear stored credentials.
    """
    if session_id in _espn_credentials:
        del _espn_credentials[session_id]

    return {"status": "disconnected"}


@app.get("/integrations/espn/status")
async def get_espn_status(session_id: str = Query(default="default")):
    """
    Check if ESPN Fantasy account is connected.
    """
    creds = _espn_credentials.get(session_id)
    connected = creds is not None

    if connected:
        user_id = await espn_fantasy_service.get_user_id(creds)
        return {"connected": True, "user_id": user_id}

    return {"connected": False, "user_id": None}


# ---------------------------------------------------------------------------
# Push Notification Routes
# ---------------------------------------------------------------------------


class PushTokenRequest(BaseModel):
    """Request to register/unregister push token."""

    token: str = Field(..., description="Expo push token")


class SendNotificationRequest(BaseModel):
    """Request to send a notification."""

    title: str
    body: str
    data: dict | None = None


@app.post("/notifications/register")
async def register_push_token(request: PushTokenRequest):
    """
    Register a device for push notifications.

    The token should be an Expo push token from expo-notifications.
    """
    notification_service.register_token(request.token)
    return {"status": "registered", "token": request.token}


@app.post("/notifications/unregister")
async def unregister_push_token(request: PushTokenRequest):
    """
    Unregister a device from push notifications.
    """
    notification_service.unregister_token(request.token)
    return {"status": "unregistered"}


@app.post("/notifications/send")
async def send_notification_to_token(
    token: str = Query(..., description="Target push token"),
    request: SendNotificationRequest = ...,
):
    """
    Send a notification to a specific device (admin/testing endpoint).
    """
    notification = PushNotification(
        to=token,
        title=request.title,
        body=request.body,
        data=request.data,
    )

    result = await notification_service.send_notification(notification)
    return result


@app.post("/notifications/broadcast")
async def broadcast_notification(request: SendNotificationRequest):
    """
    Send a notification to all registered devices (admin endpoint).
    """
    results = await notification_service.send_to_all(
        title=request.title,
        body=request.body,
        data=request.data,
    )

    return {
        "sent": len(results),
        "results": results,
    }


@app.get("/notifications/tokens")
async def list_registered_tokens():
    """
    List all registered push tokens (admin endpoint).
    """
    tokens = notification_service.get_all_tokens()
    return {"count": len(tokens), "tokens": tokens}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
