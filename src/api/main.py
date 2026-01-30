"""
GameSpace API — Fantasy Sports Decision Engine
"""

import os
import secrets
import sys
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from enum import Enum

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sentry_sdk
from core.scoring import RiskMode as CoreRiskMode
from core.scoring import compare_players
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import Integer as SAInteger
from sqlalchemy import func, select

from models.database import BudgetConfig
from models.database import Decision as DecisionModel
from monitoring import MetricsMiddleware, metrics_endpoint
from routes.sessions import router as sessions_router
from services.accuracy import AccuracyTracker, DecisionOutcome
from services.claude import claude_service
from services.database import db_service
from services.espn import espn_service, format_player_context
from services.espn_fantasy import ESPNCredentials, espn_fantasy_service
from services.notifications import PushNotification, notification_service
from services.redis import redis_service
from services.router import QueryComplexity, classify_query, extract_players_from_query
from services.scoring_adapter import adapt_espn_to_core
from services.sleeper import sleeper_service
from services.variants import (
    assign_variant,
    experiment_registry,
    get_experiment_config,
    get_experiment_history,
)
from services.websocket import connection_manager
from services.yahoo import yahoo_service

load_dotenv()

# ---------------------------------------------------------------------------
# Sentry Error Monitoring
# ---------------------------------------------------------------------------

SENTRY_DSN = os.getenv("SENTRY_DSN", "")

if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=os.getenv("ENVIRONMENT", "development"),
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        enable_tracing=True,
        send_default_pii=False,
    )
    print("Sentry error monitoring enabled")

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
    await sleeper_service.close()
    await yahoo_service.close()
    await notification_service.close()
    await db_service.disconnect()
    await redis_service.disconnect()


# ---------------------------------------------------------------------------
# App Setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="GameSpace API",
    description=(
        "Fantasy sports decision engine using role stability,"
        " spatial opportunity, and matchup context."
    ),
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

# Performance monitoring middleware
app.add_middleware(MetricsMiddleware)

# Prometheus metrics endpoint
app.add_route("/metrics", metrics_endpoint)

# Session management routes
app.include_router(sessions_router)


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
        "version": "0.4.0",
        "claude_available": claude_service.is_available,
        "espn_available": True,
        "postgres_connected": db_service.is_configured,
        "redis_connected": redis_healthy,
        "sentry_enabled": bool(SENTRY_DSN),
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
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cache_hit: bool = False,
    prompt_variant: str | None = None,
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
                score_a=response.details.get("player_a", {}).get("score")
                if response.details
                else None,
                score_b=response.details.get("player_b", {}).get("score")
                if response.details
                else None,
                margin=response.details.get("margin") if response.details else None,
                league_type=request.league_type,
                player_context=player_context,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_hit=cache_hit,
                prompt_variant=prompt_variant,
            )
            session.add(decision)
    except Exception as e:
        # Don't fail the request if persistence fails
        print(f"Failed to store decision: {e}")


async def _check_budget_exceeded() -> tuple[bool, str | None]:
    """Check if monthly budget is exceeded.

    Returns:
        Tuple of (exceeded: bool, message: str | None)
    """
    if not db_service.is_configured:
        return False, None

    # Cost per million tokens (Sonnet pricing)
    input_cost_per_mtok = 3.0
    output_cost_per_mtok = 15.0

    try:
        async with db_service.session() as session:
            # Get budget config
            config_q = select(BudgetConfig).order_by(BudgetConfig.id.desc()).limit(1)
            result = await session.execute(config_q)
            config = result.scalar_one_or_none()

            if not config or float(config.monthly_limit_usd) == 0:
                return False, None  # No limit set

            # Calculate current month spend
            now = datetime.now(UTC)
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            usage_q = select(
                func.coalesce(func.sum(DecisionModel.input_tokens), 0).label("input"),
                func.coalesce(func.sum(DecisionModel.output_tokens), 0).label("output"),
            ).where(DecisionModel.created_at >= month_start)
            usage_row = (await session.execute(usage_q)).one()

            input_tokens = int(usage_row.input)
            output_tokens = int(usage_row.output)
            current_spend = (
                input_tokens / 1_000_000 * input_cost_per_mtok
                + output_tokens / 1_000_000 * output_cost_per_mtok
            )

            limit = float(config.monthly_limit_usd)
            if current_spend >= limit:
                return (
                    True,
                    f"Monthly budget exceeded: ${current_spend:.2f} spent of ${limit:.2f} limit",
                )

            return False, None
    except Exception as e:
        print(f"Budget check failed: {e}")
        return False, None  # Fail open - don't block on errors


# Sports-related keywords for query filtering
SPORTS_KEYWORDS = {
    # Actions
    "start",
    "sit",
    "trade",
    "waiver",
    "add",
    "drop",
    "bench",
    "lineup",
    "roster",
    "pick",
    "draft",
    "stash",
    "stream",
    "hold",
    "sell",
    "buy",
    # Sports terms
    "fantasy",
    "player",
    "team",
    "matchup",
    "injury",
    "injured",
    "questionable",
    "doubtful",
    "out",
    "gtd",
    "game",
    "week",
    "season",
    "playoff",
    "playoffs",
    # Positions
    "qb",
    "rb",
    "wr",
    "te",
    "flex",
    "dst",
    "defense",
    "kicker",
    "pg",
    "sg",
    "sf",
    "pf",
    "center",
    "guard",
    "forward",
    "pitcher",
    "catcher",
    "outfield",
    "infield",
    "dh",
    "goalie",
    "winger",
    "defenseman",
    # Stats
    "points",
    "rebounds",
    "assists",
    "touchdowns",
    "yards",
    "receptions",
    "targets",
    "carries",
    "rushing",
    "passing",
    "receiving",
    "scoring",
    "ppg",
    "rpg",
    "apg",
    "ppr",
    "half-ppr",
    "standard",
    # Sports
    "nba",
    "nfl",
    "mlb",
    "nhl",
    "basketball",
    "football",
    "baseball",
    "hockey",
    # Context
    "vs",
    "versus",
    "against",
    "tonight",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
}

# Explicit off-topic patterns to reject
OFF_TOPIC_PATTERNS = [
    "how do i look",
    "what should i say",
    "how to talk to",
    "dating",
    "girlfriend",
    "boyfriend",
    "write me",
    "write a",
    "code",
    "programming",
    "python",
    "javascript",
    "explain how",
    "what is the meaning",
    "tell me a joke",
    "who is the president",
    "capital of",
]


def _is_sports_query(query: str) -> bool:
    """Check if query is sports-related.

    Returns True if query appears to be about fantasy sports.
    Uses keyword matching and off-topic pattern detection.
    """
    query_lower = query.lower()

    # Check for explicit off-topic patterns first
    for pattern in OFF_TOPIC_PATTERNS:
        if pattern in query_lower:
            return False

    # Check for sports keywords
    words = set(query_lower.replace("?", " ").replace(",", " ").split())
    if words & SPORTS_KEYWORDS:
        return True

    # If no sports keywords found, likely off-topic
    return False


@app.post("/decide", response_model=DecisionResponse)
async def make_decision(
    request: DecisionRequest,
    session_id: str | None = Query(default=None, description="Session ID for variant assignment"),
):
    """
    Make a fantasy sports decision.

    Routes to local scoring engine for simple queries,
    Claude API for complex queries.
    """
    # Check if query is sports-related
    if not _is_sports_query(request.query):
        raise HTTPException(
            status_code=400,
            detail="Query must be about fantasy sports (start/sit, trades, waivers, player matchups, etc.)",
        )

    # Assign A/B prompt variant
    variant = assign_variant(session_id)

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
            response = DecisionResponse(
                decision=cached["decision"],
                confidence=confidence_map.get(
                    cached.get("confidence", "medium"), Confidence.MEDIUM
                ),
                rationale=cached.get("rationale", ""),
                details=cached.get("details"),
                source=cached.get("source", "claude") + "_cached",
            )
            await _store_decision(
                request,
                response,
                player_a,
                player_b,
                player_context,
                cache_hit=True,
                prompt_variant=variant,
            )
            return response

    # Route based on complexity
    input_tokens = None
    output_tokens = None

    if complexity == QueryComplexity.SIMPLE and player_a_data and player_b_data:
        # Use local scoring engine with real data
        response = await _local_decision(request, player_a, player_b, player_a_data, player_b_data)
    else:
        # Check budget before calling Claude (costs money)
        budget_exceeded, budget_msg = await _check_budget_exceeded()
        if budget_exceeded:
            raise HTTPException(
                status_code=402,
                detail=budget_msg or "Monthly API budget exceeded",
            )

        # Use Claude for complex queries or when we need more reasoning
        response, input_tokens, output_tokens = await _claude_decision(
            request, player_a, player_b, player_context, prompt_variant=variant
        )

    # Store decision in database (async, non-blocking)
    await _store_decision(
        request,
        response,
        player_a,
        player_b,
        player_context,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        prompt_variant=variant,
    )

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
    Handle simple A vs B decisions locally using the core scoring engine.
    """
    if not player_a_data or not player_b_data:
        return await _claude_decision(request, player_a_name, player_b_name, None)

    info_a, stats_a = player_a_data
    info_b, stats_b = player_b_data

    if not stats_a or not stats_b:
        return await _claude_decision(request, player_a_name, player_b_name, None)

    sport = request.sport.value

    # Fetch game logs and calculate trends for OD index
    game_logs_a = await espn_service.get_player_game_logs(info_a.id, sport)
    trends_a = espn_service.calculate_trends(game_logs_a, sport)
    game_logs_b = await espn_service.get_player_game_logs(info_b.id, sport)
    trends_b = espn_service.calculate_trends(game_logs_b, sport)

    # Fetch opponent defensive data for MSF index
    opp_a = await espn_service.get_next_opponent(info_a.team_abbrev, sport)
    matchup_a = await espn_service.get_team_defense(opp_a, sport) if opp_a else None
    opp_b = await espn_service.get_next_opponent(info_b.team_abbrev, sport)
    matchup_b = await espn_service.get_team_defense(opp_b, sport) if opp_b else None

    # Adapt ESPN stats to core scoring format
    core_a = adapt_espn_to_core(info_a, stats_a, trends=trends_a, matchup=matchup_a)
    core_b = adapt_espn_to_core(info_b, stats_b, trends=trends_b, matchup=matchup_b)

    # Map API risk mode to core enum
    core_mode = CoreRiskMode(request.risk_mode.value)

    # Run the five-index scoring engine
    result = compare_players(core_a, core_b, core_mode)

    # Map confidence
    confidence_map = {
        "low": Confidence.LOW,
        "medium": Confidence.MEDIUM,
        "high": Confidence.HIGH,
    }
    confidence = confidence_map.get(result["confidence"], Confidence.MEDIUM)

    # Build rationale from index scores
    indices_a = result["indices_a"]
    indices_b = result["indices_b"]
    winner_name = info_a.name if result["score_a"] > result["score_b"] else info_b.name
    rationale = (
        f"{winner_name} scores higher across the five-index system "
        f"({result['score_a']} vs {result['score_b']}, margin {result['margin']}). "
        f"SCI: {indices_a.sci:.0f}/{indices_b.sci:.0f}, "
        f"GIS: {indices_a.gis:.0f}/{indices_b.gis:.0f}, "
        f"OD: {indices_a.od:+.0f}/{indices_b.od:+.0f}, "
        f"MSF: {indices_a.msf:.0f}/{indices_b.msf:.0f} "
        f"({request.risk_mode.value} mode)."
    )

    return DecisionResponse(
        decision=result["decision"],
        confidence=confidence,
        rationale=rationale,
        details={
            "player_a": {
                "name": info_a.name,
                "team": info_a.team_abbrev,
                "score": result["score_a"],
                "indices": {
                    "sci": round(indices_a.sci, 1),
                    "rmi": round(indices_a.rmi, 1),
                    "gis": round(indices_a.gis, 1),
                    "od": round(indices_a.od, 1),
                    "msf": round(indices_a.msf, 1),
                },
            },
            "player_b": {
                "name": info_b.name,
                "team": info_b.team_abbrev,
                "score": result["score_b"],
                "indices": {
                    "sci": round(indices_b.sci, 1),
                    "rmi": round(indices_b.rmi, 1),
                    "gis": round(indices_b.gis, 1),
                    "od": round(indices_b.od, 1),
                    "msf": round(indices_b.msf, 1),
                },
            },
            "margin": result["margin"],
            "risk_mode": request.risk_mode.value,
        },
        source="local",
    )


async def _claude_decision(
    request: DecisionRequest,
    player_a: str | None,
    player_b: str | None,
    player_context: str | None,
    prompt_variant: str = "control",
) -> tuple[DecisionResponse, int | None, int | None]:
    """Handle complex decisions using Claude API with real player context.

    Returns:
        Tuple of (response, input_tokens, output_tokens).
    """
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
            prompt_variant=prompt_variant,
        )

        # Map confidence string to enum
        confidence_map = {
            "low": Confidence.LOW,
            "medium": Confidence.MEDIUM,
            "high": Confidence.HIGH,
        }
        confidence = confidence_map.get(result.get("confidence", "medium"), Confidence.MEDIUM)

        response = DecisionResponse(
            decision=result["decision"],
            confidence=confidence,
            rationale=result["rationale"],
            details=result.get("details"),
            source="claude",
        )

        return response, result.get("input_tokens"), result.get("output_tokens")

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing request: {str(e)}",
        )


@app.post("/decide/stream")
async def make_decision_stream(
    request: DecisionRequest,
    session_id: str | None = Query(default=None, description="Session ID for variant assignment"),
):
    """
    Stream a fantasy sports decision (Server-Sent Events).

    Returns streamed text chunks from Claude for faster perceived response.
    Complex queries only - simple queries should use /decide.
    """
    # Check if query is sports-related
    if not _is_sports_query(request.query):
        raise HTTPException(
            status_code=400,
            detail="Query must be about fantasy sports (start/sit, trades, waivers, player matchups, etc.)",
        )

    if not claude_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Claude API not configured. Set ANTHROPIC_API_KEY environment variable.",
        )

    # Check budget before calling Claude (streaming always uses Claude)
    budget_exceeded, budget_msg = await _check_budget_exceeded()
    if budget_exceeded:
        raise HTTPException(
            status_code=402,
            detail=budget_msg or "Monthly API budget exceeded",
        )

    # Assign A/B prompt variant
    variant = assign_variant(session_id)

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

    # Capture metadata for persistence after streaming
    stream_metadata: dict = {}

    async def event_generator():
        """Generate Server-Sent Events."""
        nonlocal stream_metadata
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
                prompt_variant=variant,
            ):
                # Check if this is the final metadata dict
                if isinstance(chunk, dict) and chunk.get("_metadata"):
                    stream_metadata = chunk
                    continue
                # Format as SSE
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"

            # Persist decision to database after stream completes
            if stream_metadata:
                try:
                    # Parse the response to build a DecisionResponse
                    parsed = claude_service._parse_response(
                        stream_metadata.get("full_response", "")
                    )
                    confidence_map = {
                        "low": Confidence.LOW,
                        "medium": Confidence.MEDIUM,
                        "high": Confidence.HIGH,
                    }
                    response = DecisionResponse(
                        decision=parsed["decision"],
                        confidence=confidence_map.get(
                            parsed.get("confidence", "medium"), Confidence.MEDIUM
                        ),
                        rationale=parsed["rationale"],
                        details=parsed.get("details"),
                        source="claude",
                    )
                    await _store_decision(
                        request,
                        response,
                        player_a,
                        player_b,
                        player_context,
                        input_tokens=stream_metadata.get("input_tokens"),
                        output_tokens=stream_metadata.get("output_tokens"),
                        prompt_variant=variant,
                    )
                except Exception as e:
                    # Don't fail the stream if persistence fails
                    print(f"Failed to persist streaming decision: {e}")
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


@app.post("/cache/invalidate/{sport}")
async def invalidate_sport_cache(sport: Sport):
    """Invalidate all cached data for a specific sport.

    Useful after stat updates or breaking news (e.g., injuries).
    """
    if not redis_service.is_connected:
        return {"status": "skipped", "reason": "redis not connected", "keys_deleted": 0}

    total_deleted = 0
    for pattern in [
        f"decision:{sport.value}:*",
        f"player:{sport.value}:*",
        f"search:{sport.value}:*",
    ]:
        total_deleted += await redis_service.clear_pattern(pattern)

    # Bump stats version so old cache keys auto-miss
    new_version = await redis_service.bump_stats_version(sport.value)

    return {
        "status": "invalidated",
        "sport": sport.value,
        "keys_deleted": total_deleted,
        "stats_version": new_version,
    }


@app.get("/usage")
async def get_token_usage(
    sport: Sport | None = None,
):
    """Get Claude API token usage and estimated costs.

    Returns usage for today, this week, and this month with per-sport breakdown.
    """
    if not db_service.is_configured:
        return {"error": "Database not configured"}

    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())
    month_start = today_start.replace(day=1)

    # Cost per million tokens (Sonnet pricing)
    input_cost_per_mtok = 3.0
    output_cost_per_mtok = 15.0

    try:
        async with db_service.session() as session:

            async def _usage_for_period(start: datetime, sport_filter: Sport | None = None) -> dict:
                q = select(
                    func.coalesce(func.sum(DecisionModel.input_tokens), 0).label("input"),
                    func.coalesce(func.sum(DecisionModel.output_tokens), 0).label("output"),
                    func.count().label("total"),
                    func.sum(func.cast(DecisionModel.cache_hit, SAInteger)).label("cache_hits"),
                ).where(DecisionModel.created_at >= start)
                if sport_filter:
                    q = q.where(DecisionModel.sport == sport_filter.value)
                row = (await session.execute(q)).one()
                inp, out, total, hits = (
                    int(row.input),
                    int(row.output),
                    int(row.total),
                    int(hits) if (hits := row.cache_hits) else 0,
                )
                return {
                    "input_tokens": inp,
                    "output_tokens": out,
                    "total_decisions": total,
                    "cache_hits": hits,
                    "cache_hit_rate": round(hits / total, 3) if total else 0,
                    "estimated_cost_usd": round(
                        inp / 1_000_000 * input_cost_per_mtok
                        + out / 1_000_000 * output_cost_per_mtok,
                        4,
                    ),
                }

            result = {
                "today": await _usage_for_period(today_start, sport),
                "this_week": await _usage_for_period(week_start, sport),
                "this_month": await _usage_for_period(month_start, sport),
            }

            # Per-sport breakdown (this month)
            if not sport:
                sport_q = (
                    select(
                        DecisionModel.sport,
                        func.coalesce(func.sum(DecisionModel.input_tokens), 0).label("input"),
                        func.coalesce(func.sum(DecisionModel.output_tokens), 0).label("output"),
                        func.count().label("total"),
                    )
                    .where(DecisionModel.created_at >= month_start)
                    .group_by(DecisionModel.sport)
                )
                rows = (await session.execute(sport_q)).all()
                result["by_sport"] = {
                    row.sport: {
                        "input_tokens": int(row.input),
                        "output_tokens": int(row.output),
                        "total_decisions": int(row.total),
                    }
                    for row in rows
                }

            return result
    except Exception as e:
        print(f"Failed to fetch usage: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Budget Configuration
# ---------------------------------------------------------------------------


class BudgetConfigRequest(BaseModel):
    """Request to set budget configuration."""

    monthly_limit_usd: float = Field(..., ge=0, description="Monthly spending cap in USD")
    alert_threshold_pct: int = Field(
        default=80, ge=0, le=100, description="Alert when spending reaches this percentage"
    )


class BudgetConfigResponse(BaseModel):
    """Budget configuration and current status."""

    monthly_limit_usd: float
    alert_threshold_pct: int
    current_month_spent_usd: float
    percent_used: float
    budget_exceeded: bool
    alert_triggered: bool
    updated_at: str | None


class BudgetAlertResponse(BaseModel):
    """Active budget alert information."""

    alert_active: bool
    alert_type: str | None  # "threshold" or "exceeded"
    message: str | None
    current_spend_usd: float
    monthly_limit_usd: float
    percent_used: float


@app.get("/budget", response_model=BudgetConfigResponse)
async def get_budget():
    """Get current budget configuration and spending status."""
    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")

    # Cost per million tokens (Sonnet pricing)
    input_cost_per_mtok = 3.0
    output_cost_per_mtok = 15.0

    try:
        async with db_service.session() as session:
            # Get current budget config (most recent)
            config_q = select(BudgetConfig).order_by(BudgetConfig.id.desc()).limit(1)
            result = await session.execute(config_q)
            config = result.scalar_one_or_none()

            if not config:
                # No config set, return defaults
                return BudgetConfigResponse(
                    monthly_limit_usd=0,
                    alert_threshold_pct=80,
                    current_month_spent_usd=0,
                    percent_used=0,
                    budget_exceeded=False,
                    alert_triggered=False,
                    updated_at=None,
                )

            # Calculate current month spend
            now = datetime.now(UTC)
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            usage_q = select(
                func.coalesce(func.sum(DecisionModel.input_tokens), 0).label("input"),
                func.coalesce(func.sum(DecisionModel.output_tokens), 0).label("output"),
            ).where(DecisionModel.created_at >= month_start)
            usage_row = (await session.execute(usage_q)).one()

            input_tokens = int(usage_row.input)
            output_tokens = int(usage_row.output)
            current_spend = (
                input_tokens / 1_000_000 * input_cost_per_mtok
                + output_tokens / 1_000_000 * output_cost_per_mtok
            )

            limit = float(config.monthly_limit_usd)
            percent_used = (current_spend / limit * 100) if limit > 0 else 0
            budget_exceeded = limit > 0 and current_spend >= limit
            alert_triggered = limit > 0 and percent_used >= config.alert_threshold_pct

            return BudgetConfigResponse(
                monthly_limit_usd=limit,
                alert_threshold_pct=config.alert_threshold_pct,
                current_month_spent_usd=round(current_spend, 4),
                percent_used=round(percent_used, 2),
                budget_exceeded=budget_exceeded,
                alert_triggered=alert_triggered,
                updated_at=config.updated_at.isoformat() if config.updated_at else None,
            )
    except Exception as e:
        print(f"Failed to fetch budget: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/budget", response_model=BudgetConfigResponse)
async def set_budget(request: BudgetConfigRequest):
    """Set monthly spending limit and alert threshold."""
    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        async with db_service.session() as session:
            # Check if config exists
            config_q = select(BudgetConfig).order_by(BudgetConfig.id.desc()).limit(1)
            result = await session.execute(config_q)
            config = result.scalar_one_or_none()

            now = datetime.now(UTC)
            if config:
                # Update existing
                config.monthly_limit_usd = request.monthly_limit_usd  # type: ignore[assignment]
                config.alert_threshold_pct = request.alert_threshold_pct
                config.updated_at = now
            else:
                # Create new
                config = BudgetConfig(
                    monthly_limit_usd=request.monthly_limit_usd,  # type: ignore[arg-type]
                    alert_threshold_pct=request.alert_threshold_pct,
                    created_at=now,
                    updated_at=now,
                )
                session.add(config)

        # Return updated status
        return await get_budget()
    except Exception as e:
        print(f"Failed to set budget: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/budget/alerts", response_model=BudgetAlertResponse)
async def get_budget_alerts():
    """Get any active budget warnings or alerts."""
    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")

    # Cost per million tokens (Sonnet pricing)
    input_cost_per_mtok = 3.0
    output_cost_per_mtok = 15.0

    try:
        async with db_service.session() as session:
            # Get budget config
            config_q = select(BudgetConfig).order_by(BudgetConfig.id.desc()).limit(1)
            result = await session.execute(config_q)
            config = result.scalar_one_or_none()

            if not config or float(config.monthly_limit_usd) == 0:
                return BudgetAlertResponse(
                    alert_active=False,
                    alert_type=None,
                    message=None,
                    current_spend_usd=0,
                    monthly_limit_usd=0,
                    percent_used=0,
                )

            # Calculate current month spend
            now = datetime.now(UTC)
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            usage_q = select(
                func.coalesce(func.sum(DecisionModel.input_tokens), 0).label("input"),
                func.coalesce(func.sum(DecisionModel.output_tokens), 0).label("output"),
            ).where(DecisionModel.created_at >= month_start)
            usage_row = (await session.execute(usage_q)).one()

            input_tokens = int(usage_row.input)
            output_tokens = int(usage_row.output)
            current_spend = (
                input_tokens / 1_000_000 * input_cost_per_mtok
                + output_tokens / 1_000_000 * output_cost_per_mtok
            )

            limit = float(config.monthly_limit_usd)
            percent_used = (current_spend / limit * 100) if limit > 0 else 0

            # Determine alert status
            alert_active = False
            alert_type = None
            message = None

            if current_spend >= limit:
                alert_active = True
                alert_type = "exceeded"
                message = f"Budget exceeded! Spent ${current_spend:.2f} of ${limit:.2f} limit."
            elif percent_used >= config.alert_threshold_pct:
                alert_active = True
                alert_type = "threshold"
                message = f"Budget warning: {percent_used:.1f}% of monthly limit used (${current_spend:.2f} of ${limit:.2f})."

            return BudgetAlertResponse(
                alert_active=alert_active,
                alert_type=alert_type,
                message=message,
                current_spend_usd=round(current_spend, 4),
                monthly_limit_usd=limit,
                percent_used=round(percent_used, 2),
            )
    except Exception as e:
        print(f"Failed to fetch budget alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
# Sleeper Integration Routes (No Auth Required)
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


@app.get("/integrations/sleeper/user/{username}", response_model=SleeperUserResponse)
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


@app.get("/integrations/sleeper/user/{user_id}/leagues", response_model=list[SleeperLeagueResponse])
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


@app.get(
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


@app.get("/integrations/sleeper/trending/{sport}")
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
# Yahoo Fantasy Integration Routes (OAuth 2.0)
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


# In-memory token storage (per session)
# TODO: Move to database with encryption for production
_yahoo_tokens: dict[str, dict] = {}


@app.get("/integrations/yahoo/auth", response_model=YahooAuthResponse)
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

    # Store state for verification
    _yahoo_tokens[f"{session_id}_state"] = state

    auth_url = yahoo_service.get_auth_url(redirect_uri, state)

    return YahooAuthResponse(auth_url=auth_url, state=state)


@app.post("/integrations/yahoo/token", response_model=YahooTokenResponse)
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
    stored_state = _yahoo_tokens.get(f"{session_id}_state")
    if request.state and stored_state and request.state != stored_state:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    tokens = await yahoo_service.exchange_code(request.code, request.redirect_uri)

    if not tokens:
        raise HTTPException(
            status_code=400,
            detail="Failed to exchange code for tokens. Code may be expired or invalid.",
        )

    # Store tokens for this session
    _yahoo_tokens[session_id] = {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "expires_at": tokens.expires_at,
    }

    return YahooTokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        expires_at=tokens.expires_at,
    )


@app.post("/integrations/yahoo/refresh", response_model=YahooTokenResponse)
async def refresh_yahoo_token(
    session_id: str = Query(default="default"),
):
    """
    Refresh an expired Yahoo access token.

    Uses the stored refresh token to get a new access token.
    """
    stored = _yahoo_tokens.get(session_id)

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
    _yahoo_tokens[session_id] = {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "expires_at": tokens.expires_at,
    }

    return YahooTokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        expires_at=tokens.expires_at,
    )


async def _get_yahoo_token(session_id: str) -> str:
    """Get valid Yahoo access token, refreshing if needed."""
    stored = _yahoo_tokens.get(session_id)

    if not stored:
        raise HTTPException(
            status_code=401,
            detail="Yahoo account not connected. Complete OAuth flow first.",
        )

    # Refresh if expired (with 60s buffer)
    if stored.get("expires_at", 0) < time.time() + 60:
        tokens = await yahoo_service.refresh_token(stored["refresh_token"])
        if tokens:
            _yahoo_tokens[session_id] = {
                "access_token": tokens.access_token,
                "refresh_token": tokens.refresh_token,
                "expires_at": tokens.expires_at,
            }
            return tokens.access_token
        else:
            raise HTTPException(
                status_code=401,
                detail="Failed to refresh Yahoo token. Please re-authorize.",
            )

    return stored["access_token"]


@app.get("/integrations/yahoo/leagues", response_model=list[YahooLeagueResponse])
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


@app.get("/integrations/yahoo/teams", response_model=list[YahooTeamResponse])
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


@app.get("/integrations/yahoo/roster/{team_key}", response_model=list[YahooPlayerResponse])
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


@app.get("/integrations/yahoo/standings/{league_key}")
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


@app.delete("/integrations/yahoo/disconnect")
async def disconnect_yahoo_account(session_id: str = Query(default="default")):
    """
    Disconnect Yahoo Fantasy account and clear stored tokens.
    """
    if session_id in _yahoo_tokens:
        del _yahoo_tokens[session_id]

    state_key = f"{session_id}_state"
    if state_key in _yahoo_tokens:
        del _yahoo_tokens[state_key]

    return {"status": "disconnected"}


@app.get("/integrations/yahoo/status")
async def get_yahoo_status(session_id: str = Query(default="default")):
    """
    Check if Yahoo Fantasy account is connected.
    """
    stored = _yahoo_tokens.get(session_id)
    connected = stored is not None and "access_token" in stored

    if connected:
        expires_at = stored.get("expires_at", 0)
        return {
            "connected": True,
            "expires_at": expires_at,
            "expired": expires_at < time.time(),
        }

    return {"connected": False}


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


# ---------------------------------------------------------------------------
# WebSocket — Real-Time Updates
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time updates.

    Message Protocol:
    - Client sends: {"type": "subscribe", "topic": "player:nba:12345"}
    - Client sends: {"type": "unsubscribe", "topic": "player:nba:12345"}
    - Client sends: {"type": "ping"}
    - Server sends: {"type": "connected", "timestamp": "...", "data": {"connection_id": "..."}}
    - Server sends: {"type": "stat_update", "timestamp": "...", "data": {...}}
    - Server sends: {"type": "injury_alert", "timestamp": "...", "data": {...}}

    Topics:
    - player:{sport}:{player_id} — Updates for a specific player
    - game:{sport}:{game_id} — Updates for a specific game
    - sport:{sport} — All updates for a sport (nba, nfl, mlb, nhl)
    - injuries — All injury alerts
    """
    connection_id = await connection_manager.connect(websocket)
    try:
        while True:
            message = await websocket.receive_text()
            await connection_manager.handle_message(connection_id, message)
    except WebSocketDisconnect:
        await connection_manager.disconnect(connection_id)


@app.get("/ws/stats")
async def websocket_stats():
    """Get WebSocket connection statistics."""
    return connection_manager.get_stats()


# ---------------------------------------------------------------------------
# Decision Accuracy Tracking
# ---------------------------------------------------------------------------

accuracy_tracker = AccuracyTracker()


class OutcomeRequest(BaseModel):
    """Record the actual outcome of a decision."""

    decision_id: str
    actual_points_a: float | None = None
    actual_points_b: float | None = None
    user_followed: bool | None = None
    feedback_note: str | None = None


@app.post("/accuracy/outcomes")
async def record_outcome(request: OutcomeRequest):
    """Record the actual outcome for a past decision."""
    outcome = DecisionOutcome(
        decision_id=request.decision_id,
        actual_points_a=request.actual_points_a,
        actual_points_b=request.actual_points_b,
        user_followed=request.user_followed,
        feedback_note=request.feedback_note,
    )
    accuracy_tracker.record_outcome(outcome)
    return {"status": "recorded", "decision_id": request.decision_id}


@app.get("/accuracy/metrics")
async def get_accuracy_metrics(
    sport: Sport | None = None, limit: int = Query(default=500, ge=1, le=5000)
):
    """Get aggregate accuracy metrics across all tracked decisions."""
    decisions = []
    if db_service.is_configured:
        try:
            async with db_service.session() as session:
                query = select(DecisionModel).order_by(DecisionModel.created_at.desc()).limit(limit)
                if sport:
                    query = query.where(DecisionModel.sport == sport.value)
                result = await session.execute(query)
                rows = result.scalars().all()
                decisions = [
                    {
                        "id": str(d.id),
                        "sport": d.sport,
                        "confidence": d.confidence,
                        "source": d.source,
                        "decision": d.decision,
                        "player_a_name": d.player_a_name,
                        "prompt_variant": d.prompt_variant,
                    }
                    for d in rows
                ]
        except Exception:
            decisions = []
    metrics = accuracy_tracker.compute_metrics(decisions)
    return {
        "total_decisions": metrics.total_decisions,
        "decisions_with_outcomes": metrics.decisions_with_outcomes,
        "correct": metrics.correct_decisions,
        "incorrect": metrics.incorrect_decisions,
        "pushes": metrics.pushes,
        "accuracy_pct": metrics.accuracy_pct,
        "coverage_pct": metrics.coverage_pct,
        "by_confidence": {
            "high": {
                "total": metrics.high_confidence_total,
                "correct": metrics.high_confidence_correct,
                "accuracy": metrics.confidence_accuracy("high"),
            },
            "medium": {
                "total": metrics.medium_confidence_total,
                "correct": metrics.medium_confidence_correct,
                "accuracy": metrics.confidence_accuracy("medium"),
            },
            "low": {
                "total": metrics.low_confidence_total,
                "correct": metrics.low_confidence_correct,
                "accuracy": metrics.confidence_accuracy("low"),
            },
        },
        "by_source": {
            "local": {"total": metrics.local_total, "correct": metrics.local_correct},
            "claude": {"total": metrics.claude_total, "correct": metrics.claude_correct},
        },
        "by_sport": metrics.by_sport,
        "by_variant": metrics.by_variant,
    }


@app.get("/accuracy/outcome/{decision_id}")
async def get_outcome(decision_id: str):
    """Get the recorded outcome for a specific decision."""
    outcome = accuracy_tracker.get_outcome(decision_id)
    if not outcome:
        raise HTTPException(status_code=404, detail="No outcome recorded for this decision")
    return {
        "decision_id": outcome.decision_id,
        "actual_points_a": outcome.actual_points_a,
        "actual_points_b": outcome.actual_points_b,
        "user_followed": outcome.user_followed,
        "feedback_note": outcome.feedback_note,
    }


# ---------------------------------------------------------------------------
# A/B Experiment Endpoints
# ---------------------------------------------------------------------------


@app.get("/experiments/active")
async def get_active_experiment():
    """Get current A/B experiment configuration."""
    return get_experiment_config()


@app.get("/experiments/results")
async def get_experiment_results():
    """Get A/B experiment results: per-variant decision count, token usage, confidence distribution."""
    if not db_service.is_configured:
        return {"error": "Database not configured"}

    try:
        async with db_service.session() as session:
            q = (
                select(
                    DecisionModel.prompt_variant,
                    func.count().label("total"),
                    func.coalesce(func.sum(DecisionModel.input_tokens), 0).label("input_tokens"),
                    func.coalesce(func.sum(DecisionModel.output_tokens), 0).label("output_tokens"),
                    func.sum(func.cast(DecisionModel.cache_hit, SAInteger)).label("cache_hits"),
                )
                .where(DecisionModel.prompt_variant.isnot(None))
                .group_by(DecisionModel.prompt_variant)
            )
            rows = (await session.execute(q)).all()

            # Confidence distribution per variant
            conf_q = (
                select(
                    DecisionModel.prompt_variant,
                    DecisionModel.confidence,
                    func.count().label("count"),
                )
                .where(DecisionModel.prompt_variant.isnot(None))
                .group_by(DecisionModel.prompt_variant, DecisionModel.confidence)
            )
            conf_rows = (await session.execute(conf_q)).all()

            conf_dist: dict[str, dict[str, int]] = {}
            for row in conf_rows:
                conf_dist.setdefault(row.prompt_variant, {})[row.confidence] = int(row.count)

            results = {}
            for row in rows:
                variant = row.prompt_variant
                total = int(row.total)
                hits = int(row.cache_hits) if row.cache_hits else 0
                results[variant] = {
                    "total_decisions": total,
                    "input_tokens": int(row.input_tokens),
                    "output_tokens": int(row.output_tokens),
                    "cache_hits": hits,
                    "cache_hit_rate": round(hits / total, 3) if total else 0,
                    "confidence_distribution": conf_dist.get(variant, {}),
                }

            return {"variants": results}
    except Exception as e:
        print(f"Failed to fetch experiment results: {e}")
        return {"error": str(e)}


@app.get("/experiments/history")
async def get_experiments_history():
    """Get all past (ended) experiments."""
    return {"experiments": get_experiment_history()}


class StartExperimentRequest(BaseModel):
    """Request to start a new A/B experiment."""

    name: str = Field(..., description="Experiment name, e.g. 'concise_prompt_v2'")
    variants: dict[str, int] = Field(
        ..., description="Variant name -> weight mapping, e.g. {'control': 50, 'concise_v1': 50}"
    )
    description: str = Field(default="", description="What this experiment tests")


@app.post("/experiments/start")
async def start_experiment(request: StartExperimentRequest):
    """Start a new A/B experiment. Ends the current one if active."""
    try:
        experiment = experiment_registry.start_experiment(
            name=request.name,
            variants=request.variants,
            description=request.description,
        )
        return {
            "status": "started",
            "experiment": {
                "name": experiment.name,
                "variants": experiment.variants,
                "started_at": experiment.started_at.isoformat(),
                "description": experiment.description,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/experiments/end")
async def end_experiment():
    """End the active experiment and archive it."""
    ended = experiment_registry.end_experiment()
    if ended is None:
        raise HTTPException(status_code=404, detail="No active experiment to end")

    return {
        "status": "ended",
        "experiment": {
            "name": ended.name,
            "variants": ended.variants,
            "started_at": ended.started_at.isoformat(),
            "ended_at": ended.ended_at.isoformat() if ended.ended_at else None,
            "duration_hours": ended.duration_hours,
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
