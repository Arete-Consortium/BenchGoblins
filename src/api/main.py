"""
BenchGoblin API — Fantasy Sports Decision Engine
"""

import asyncio
import json
import logging
import os
import secrets
import sys
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Add project root for scripts/ imports (migration runner, etc.)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sentry_sdk
from core.scoring import RiskMode as CoreRiskMode
from core.scoring import compare_players
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, constr, field_validator
from sqlalchemy import Integer as SAInteger
from sqlalchemy import delete, func, select, text

from models.database import BudgetConfig, User
from models.database import Decision as DecisionModel
from models.database import Session as SessionModel
from monitoring import MetricsMiddleware, update_engagement_metrics
from routes.auth import get_current_user, get_optional_user, require_admin_key, require_pro
from routes.auth import router as auth_router
from routes.commissioner import router as commissioner_router
from routes.dossier import router as dossier_router
from routes.goblin import router as goblin_router
from routes.leaderboard import router as leaderboard_router
from routes.leagues import router as leagues_router
from routes.newsletter import router as newsletter_router
from routes.notifications import router as notifications_router
from routes.referral import router as referral_router
from routes.rivalries import router as rivalries_router
from routes.sessions import router as sessions_router
from routes.verdicts import router as verdicts_router
from services import stripe_billing
from services.accuracy import AccuracyTracker, DecisionOutcome
from services.budget_alerts import check_and_send_alerts, send_test_webhook
from services.claude import claude_service
from services.database import db_service
from services.draft_assistant import draft_assistant, extract_draft_players
from services.drip_scheduler import drip_scheduler
from services.engagement import engagement_tracker
from services.espn import espn_service, format_player_context
from services.espn_fantasy import ESPNCredentials, espn_fantasy_service
from services.notification_triggers import notification_scheduler
from services.notifications import PushNotification, notification_service
from services.outcome_scheduler import outcome_scheduler
from services.query_classifier import QueryCategory
from services.query_classifier import classify_query as classify_sports_query
from services.rankings_scheduler import rankings_scheduler
from services.rate_limiter import rate_limiter
from services.recap_scheduler import recap_scheduler
from services.redis import redis_service
from services.router import (
    QueryComplexity,
    classify_draft_query,
    classify_query,
    classify_trade_query,
    extract_players_from_query,
)
from services.scoring_adapter import adapt_espn_to_core
from services.session import session_service
from services.sleeper import sleeper_service
from services.trade_analyzer import extract_trade_players, trade_analyzer
from services.variants import (
    assign_variant,
    experiment_registry,
    get_experiment_config,
    get_experiment_history,
)
from services.verdict_scheduler import verdict_pregen_scheduler
from services.waiver_wire import analyze_roster, build_waiver_prompt
from services.websocket import connection_manager
from services.yahoo import yahoo_service

load_dotenv()

from logging_config import setup_logging  # noqa: E402

logger = logging.getLogger(__name__)

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
    logger.info("Sentry error monitoring enabled")

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


def _validate_production_env() -> None:
    """Fail fast if required env vars are missing in production."""
    required_vars = [
        "ADMIN_API_KEY",
        "ANTHROPIC_API_KEY",
        "DATABASE_URL",
        "JWT_SECRET_KEY",
        "SESSION_ENCRYPTION_KEY",
    ]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables for production: {', '.join(missing)}. "
            "Set these variables or run with ENVIRONMENT=development."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup app resources"""
    setup_logging()

    # Fail fast in production if critical env vars are missing
    if os.getenv("ENVIRONMENT") == "production":
        _validate_production_env()

    # Initialize services
    if claude_service.is_available:
        logger.info("Claude API configured and ready")
    else:
        logger.warning("ANTHROPIC_API_KEY not set - Claude integration disabled")

    # Connect to PostgreSQL and create tables
    logger.info("Connecting to PostgreSQL...")
    if db_service.is_configured:
        try:
            await db_service.connect()
            # Test connection
            async with db_service._engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            # Create tables if they don't exist
            from models.database import Base

            async with db_service._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("PostgreSQL connected and tables created")

            # Run SQL migrations for schema changes not covered by ORM models
            from scripts.migrate import run_migrations_async

            applied = await run_migrations_async(db_service._engine)
            if applied:
                logger.info("Applied %d database migration(s)", applied)
        except Exception as e:
            logger.warning("PostgreSQL connection failed: %s", e)
    else:
        logger.warning("DATABASE_URL not set - persistence disabled")

    # Connect to Redis
    if redis_service.is_configured:
        try:
            await redis_service.connect()
            logger.info("Redis connected")
            # Wire up Redis-backed token blacklist for persistent logout
            from services.auth import set_blacklist_redis

            if redis_service.is_connected and redis_service._client:
                set_blacklist_redis(redis_service._client)
                logger.info("Token blacklist using Redis (persistent)")
        except Exception as e:
            logger.warning("Redis connection failed: %s", e)
    else:
        logger.warning("REDIS_URL not set - caching disabled")

    logger.info("ESPN data service ready")

    # Start notification scheduler if both DB and Redis are available
    if db_service.is_configured and redis_service.is_connected:
        await notification_scheduler.start()
        logger.info("Notification scheduler started")
    else:
        logger.info("Notification scheduler skipped (requires DB + Redis)")

    # Start outcome sync scheduler (only requires DB, not Redis)
    if db_service.is_configured:
        await outcome_scheduler.start()
        logger.info("Outcome scheduler started")
    else:
        logger.info("Outcome scheduler skipped (requires DB)")

    # Start verdict pre-generation scheduler (requires DB + Redis + Claude)
    if db_service.is_configured and redis_service.is_connected:
        await verdict_pregen_scheduler.start()
        logger.info("Verdict pre-gen scheduler started")
    else:
        logger.info("Verdict pre-gen scheduler skipped (requires DB + Redis)")

    # Start recap scheduler (requires DB + Claude)
    if db_service.is_configured:
        await recap_scheduler.start()
        logger.info("Recap scheduler started")
    else:
        logger.info("Recap scheduler skipped (requires DB)")

    # Start rankings scheduler (requires DB + Redis + Sleeper)
    if db_service.is_configured and redis_service.is_connected:
        await rankings_scheduler.start()
        logger.info("Rankings scheduler started")
    else:
        logger.info("Rankings scheduler skipped (requires DB + Redis)")

    # Start drip email scheduler (requires DB, optionally Resend)
    if db_service.is_configured:
        await drip_scheduler.start()
        logger.info("Drip scheduler started")
    else:
        logger.info("Drip scheduler skipped (requires DB)")

    yield

    # Cleanup
    await drip_scheduler.stop()
    await rankings_scheduler.stop()
    await recap_scheduler.stop()
    await verdict_pregen_scheduler.stop()
    await outcome_scheduler.stop()
    await notification_scheduler.stop()
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
    title="BenchGoblin API",
    description=(
        "Fantasy sports decision engine using role stability,"
        " spatial opportunity, and matchup context."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

ALLOWED_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:3001,https://benchgoblins.com",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Admin-Key", "X-Session-Token"],
    max_age=3600,
)


# Security headers middleware
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response


app.add_middleware(SecurityHeadersMiddleware)

# GZip compression for responses > 1KB
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402

app.add_middleware(GZipMiddleware, minimum_size=1000)

# Performance monitoring middleware
app.add_middleware(MetricsMiddleware)


# ---------------------------------------------------------------------------
# Global Exception Handler — prevent stack traces from leaking to clients
# ---------------------------------------------------------------------------
from fastapi.responses import JSONResponse  # noqa: E402


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return a safe 500 response."""
    logger.error("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Prometheus metrics endpoint (admin-only)
@app.get("/metrics", tags=["Admin"])
async def metrics_endpoint(_admin=Depends(require_admin_key)):
    """Prometheus metrics (admin-only)."""
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    from starlette.responses import Response

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Session management routes
app.include_router(sessions_router)

# Authentication routes
app.include_router(auth_router)

# League integration routes (Sleeper)
app.include_router(leagues_router)

# Verdict routes (Start/Sit engine)
app.include_router(verdicts_router)

# Newsletter routes (email capture)
app.include_router(newsletter_router)

# Push notification routes
app.include_router(notifications_router)

# Commissioner AI tools
app.include_router(commissioner_router)

# Rivalry tracking
app.include_router(rivalries_router)

# Player dossier
app.include_router(dossier_router)

# Goblin lineup verdicts
app.include_router(goblin_router)

# Referral system
app.include_router(referral_router)

# Player leaderboards
app.include_router(leaderboard_router)


# ---------------------------------------------------------------------------
# Enums & Models
# ---------------------------------------------------------------------------


class Sport(str, Enum):
    NBA = "nba"
    NFL = "nfl"
    MLB = "mlb"
    NHL = "nhl"
    SOCCER = "soccer"


class RiskMode(str, Enum):
    FLOOR = "floor"
    MEDIAN = "median"
    CEILING = "ceiling"


class DecisionType(str, Enum):
    START_SIT = "start_sit"
    TRADE = "trade"
    WAIVER = "waiver"
    EXPLAIN = "explain"
    DRAFT = "draft"


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
        max_length=1000,
        description="Natural language query, e.g., 'Should I start Jalen Brunson or Tyrese Maxey?'",
    )
    player_a: str | None = Field(
        None, max_length=100, description="First player name (optional if in query)"
    )
    player_b: str | None = Field(
        None, max_length=100, description="Second player name (optional if in query)"
    )
    league_type: str | None = Field(
        None, max_length=50, description="e.g., 'points', 'categories', 'half-ppr'"
    )
    league_id: str | None = Field(
        None, max_length=50, description="Sleeper league ID for roster and scoring context"
    )
    sleeper_user_id: str | None = Field(
        None, max_length=50, description="Sleeper user ID for roster lookup"
    )


class DecisionResponse(BaseModel):
    """Response from /decide endpoint"""

    decision: str
    confidence: Confidence
    rationale: str
    details: dict | None = None
    source: str = Field(..., description="'local' or 'claude'")


class DraftRequest(BaseModel):
    """Request body for /draft endpoint"""

    sport: Sport
    risk_mode: RiskMode = RiskMode.MEDIAN
    query: str = Field(
        ...,
        max_length=1000,
        description="Natural language query, e.g., 'draft Jalen Brunson or Tyrese Maxey?'",
    )
    players: list[constr(max_length=100)] | None = Field(
        None, max_length=20, description="Explicit list of player names to rank"
    )
    position_needs: list[constr(max_length=10)] | None = Field(
        None, max_length=10, description="Positions to boost, e.g., ['PG', 'C']"
    )
    league_type: str | None = Field(
        None, max_length=50, description="e.g., 'points', 'categories', 'half-ppr'"
    )
    league_id: str | None = Field(
        None, max_length=50, description="Sleeper league ID for roster and scoring context"
    )
    sleeper_user_id: str | None = Field(
        None, max_length=50, description="Sleeper user ID for roster lookup"
    )


class DraftResponse(BaseModel):
    """Response from /draft endpoint"""

    recommended_pick: str
    confidence: Confidence
    rationale: str
    details: dict | None = None
    source: str = Field(..., description="'local' or 'claude'")


class WaiverRequest(BaseModel):
    """Request body for /waiver/recommend endpoint"""

    sport: Sport
    risk_mode: RiskMode = RiskMode.MEDIAN
    query: str = Field(
        default="Who should I pick up?",
        max_length=1000,
        description="Waiver wire question",
    )
    league_id: str = Field(..., max_length=50, description="Sleeper league ID (required)")
    sleeper_user_id: str = Field(..., max_length=50, description="Sleeper user ID (required)")
    position_filter: str | None = Field(
        None, max_length=10, description="Filter to specific position, e.g., 'RB'"
    )


class WaiverResponse(BaseModel):
    """Response from /waiver/recommend endpoint"""

    recommendations: list[dict]
    drop_candidates: list[dict]
    position_needs: list[str]
    confidence: Confidence
    rationale: str
    source: str = Field(default="claude", description="'claude'")


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
    """Health check endpoint — returns 503 if critical services are down."""
    from starlette.responses import JSONResponse

    # Test actual database connectivity (not just is_configured)
    db_healthy = False
    if db_service.is_configured:
        try:
            async with db_service._engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            db_healthy = True
        except Exception as e:
            logger.error("Health check: DB connectivity failed: %s", e)

    redis_healthy = await redis_service.health_check() if redis_service.is_connected else False

    status = "healthy" if db_healthy else "unhealthy"
    payload = {
        "status": status,
        "version": "1.0.0",
        "claude_available": claude_service.is_available,
        "postgres_connected": db_healthy,
        "redis_connected": redis_healthy,
        "sentry_enabled": bool(SENTRY_DSN),
    }

    if not db_healthy:
        return JSONResponse(status_code=503, content=payload)
    return payload


@app.post("/players/search", response_model=list[Player])
async def search_players(request: PlayerSearchRequest, req: Request):
    """Search for players by name using ESPN data."""
    client_ip = req.client.host if req.client else "anonymous"
    allowed, retry_after = await rate_limiter.check_rate_limit(f"player_search:{client_ip}")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )
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
async def get_player(sport: Sport, player_id: str, req: Request):
    """Get detailed player information and stats."""
    client_ip = req.client.host if req.client else "anonymous"
    allowed, retry_after = await rate_limiter.check_rate_limit(f"player_get:{client_ip}")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )

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
        logger.error("Failed to store decision: %s", e)


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

            # Calculate current month spend (single indexed query)
            month_start = datetime.now(UTC).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )

            usage_row = (
                await session.execute(
                    select(
                        func.coalesce(func.sum(DecisionModel.input_tokens), 0).label("input"),
                        func.coalesce(func.sum(DecisionModel.output_tokens), 0).label("output"),
                    ).where(DecisionModel.created_at >= month_start)
                )
            ).one()

            current_spend = (
                int(usage_row.input) / 1_000_000 * input_cost_per_mtok
                + int(usage_row.output) / 1_000_000 * output_cost_per_mtok
            )

            limit = float(config.monthly_limit_usd)
            if current_spend >= limit:
                return (
                    True,
                    f"Monthly budget exceeded: ${current_spend:.2f} spent of ${limit:.2f} limit",
                )

            return False, None
    except Exception as e:
        logger.error("Budget check failed: %s", e)
        return False, None  # Fail open - don't block on errors


def _is_sports_query(query: str) -> tuple[bool, str]:
    """Check if query is sports-related using the smart classifier.

    Returns (is_allowed, reason) tuple.
    - SPORTS: allowed
    - AMBIGUOUS: allowed (logged for review)
    - OFF_TOPIC: rejected with reason
    """
    result = classify_sports_query(query)

    if result.category == QueryCategory.OFF_TOPIC:
        return False, result.reason

    # Log ambiguous queries for review (could add proper logging here)
    if result.category == QueryCategory.AMBIGUOUS:
        logger.info("AMBIGUOUS query allowed: '%s...' - %s", query[:50], result.reason)

    return True, result.reason


# Sport-specific suggestion templates for rejected/unclear queries
_SPORT_SUGGESTIONS: dict[str, list[str]] = {
    "nba": [
        "Should I start {A} or {B} this week?",
        "Trade value for {A} — buy or sell?",
        "Best waiver wire pickups for NBA this week?",
        "Is {A} a must-start in my lineup?",
    ],
    "nfl": [
        "Should I start {A} or {B} at QB this week?",
        "Trade {A} for {B} — who wins?",
        "Best waiver wire RBs for this week?",
        "Is {A} a must-start in ceiling mode?",
    ],
    "mlb": [
        "Start {A} or {B} tonight?",
        "Best waiver wire pitchers this week?",
        "Should I bench {A} against a lefty?",
        "Trade {A} for {B} — fair deal?",
    ],
    "nhl": [
        "Start {A} or {B} this week?",
        "Best waiver wire goalies this week?",
        "Trade {A} for {B} — fair?",
        "Is {A} a good pickup off waivers?",
    ],
    "soccer": [
        "Captain {A} or {B} this gameweek?",
        "Best budget midfielders to pick up?",
        "Should I start {A} in my FPL squad?",
        "Is {A} a good differential captain?",
    ],
}

_SAMPLE_PLAYERS: dict[str, list[str]] = {
    "nba": ["Jayson Tatum", "Anthony Edwards", "Luka Doncic", "Tyrese Haliburton"],
    "nfl": ["Josh Allen", "Lamar Jackson", "Tyreek Hill", "CeeDee Lamb"],
    "mlb": ["Shohei Ohtani", "Aaron Judge", "Mookie Betts", "Trea Turner"],
    "nhl": ["Connor McDavid", "Nathan MacKinnon", "Auston Matthews", "Cale Makar"],
    "soccer": ["Haaland", "Salah", "Palmer", "Saka"],
}


def _generate_suggestions(query: str, sport: str) -> list[str]:
    """Generate helpful rephrased suggestions for a rejected/unclear query."""
    import random

    templates = _SPORT_SUGGESTIONS.get(sport, _SPORT_SUGGESTIONS["nfl"])
    players = _SAMPLE_PLAYERS.get(sport, _SAMPLE_PLAYERS["nfl"])

    suggestions = []
    for tmpl in random.sample(templates, min(3, len(templates))):
        a, b = random.sample(players, 2)
        suggestions.append(tmpl.replace("{A}", a).replace("{B}", b))

    return suggestions


def _raise_off_topic(query: str, sport: str) -> None:
    """Raise a 400 with helpful suggestions instead of a vague rejection."""
    suggestions = _generate_suggestions(query, sport)
    raise HTTPException(
        status_code=400,
        detail={
            "message": "I'm built for fantasy sports questions — try rephrasing like one of these:",
            "suggestions": suggestions,
        },
    )


# ---------------------------------------------------------------------------
# Tier-Based Query Limiting Helpers
# ---------------------------------------------------------------------------

# Tier limits
FREE_TIER_WEEKLY_LIMIT = 5
PRO_TIER_WEEKLY_LIMIT = -1  # Unlimited


async def _check_and_increment_query_count(user_id: int) -> tuple[bool, int, int]:
    """Check if user can make a query and increment counter.

    Uses SELECT FOR UPDATE to prevent race conditions where concurrent
    requests could bypass the free-tier limit.

    Returns:
        Tuple of (allowed, queries_this_period, weekly_limit)
    """
    if not db_service.is_configured:
        return True, 0, FREE_TIER_WEEKLY_LIMIT

    async with db_service.session() as session:
        # Lock the row to prevent concurrent requests from reading stale counts
        result = await session.execute(select(User).where(User.id == user_id).with_for_update())
        user = result.scalar_one_or_none()

        if not user:
            return True, 0, FREE_TIER_WEEKLY_LIMIT

        # Check direct Pro OR league-inherited Pro
        is_pro = user.subscription_tier == "pro"
        if not is_pro:
            try:
                is_pro = await stripe_billing.is_league_pro(user_id)
            except Exception:
                pass  # Graceful degradation — default to direct tier

        # Determine weekly limit based on tier
        weekly_limit = PRO_TIER_WEEKLY_LIMIT if is_pro else FREE_TIER_WEEKLY_LIMIT

        # Check if counter needs reset (new week — 7 days since last reset)
        now = datetime.now(UTC)
        reset_at = user.queries_reset_at
        # Handle timezone-naive timestamps from DB (TIMESTAMP vs TIMESTAMPTZ)
        if reset_at is not None and reset_at.tzinfo is None:
            reset_at = reset_at.replace(tzinfo=UTC)

        if reset_at is None or (now - reset_at) >= timedelta(days=7):
            # Reset counter for new week
            user.queries_today = 0
            user.queries_reset_at = now

        # Pro tier has unlimited queries
        if is_pro:
            user.queries_today += 1
            session.add(user)
            await session.commit()
            return True, user.queries_today, weekly_limit

        # Free tier - check limit
        if user.queries_today >= weekly_limit:
            return False, user.queries_today, weekly_limit

        # Increment counter
        user.queries_today += 1
        session.add(user)
        await session.commit()
        return True, user.queries_today, weekly_limit


def _raise_quota_exceeded(queries_today: int, weekly_limit: int) -> None:
    """Raise a standardized 402 quota-exceeded error."""
    raise HTTPException(
        status_code=402,
        detail={
            "code": "QUOTA_EXCEEDED",
            "message": f"Weekly query limit reached ({queries_today}/{weekly_limit}). Upgrade to Pro for unlimited queries.",
            "queries_used": queries_today,
            "queries_limit": weekly_limit,
            "upgrade_url": "/billing/create-checkout",
        },
    )


@app.post("/decide", response_model=DecisionResponse)
async def make_decision(
    request: DecisionRequest,
    session_id: str | None = Query(default=None, description="Session ID for variant assignment"),
    current_user: dict | None = Depends(get_optional_user),
):
    """
    Make a fantasy sports decision.

    Routes to local scoring engine for simple queries,
    Claude API for complex queries.

    Rate limits:
    - Free tier: 5 queries per day
    - Pro tier: unlimited queries
    """
    # Check rate limit (use "anonymous" for requests without session_id)
    effective_session = session_id or "anonymous"
    allowed, retry_after = await rate_limiter.check_rate_limit(effective_session)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    # Check tier-based daily limit if authenticated
    user_id = current_user["user_id"] if current_user else None
    if user_id is not None:
        tier_allowed, queries_today, weekly_limit = await _check_and_increment_query_count(user_id)
        if not tier_allowed:
            _raise_quota_exceeded(queries_today, weekly_limit)

    # Check if query is sports-related (skip when league connected — clearly fantasy)
    if not request.league_id:
        is_allowed, rejection_reason = _is_sports_query(request.query)
        if not is_allowed:
            _raise_off_topic(
                request.query,
                request.sport.value if hasattr(request.sport, "value") else str(request.sport),
            )

    # Assign A/B prompt variant
    variant = assign_variant(session_id)

    # --- Trade intercept: try local scoring for trade queries ---
    if request.decision_type == DecisionType.TRADE:
        trade_parsed = extract_trade_players(request.query)
        if trade_parsed:
            giving_names, receiving_names = trade_parsed
            sport = request.sport.value

            # Fetch ESPN data for all trade players (parallel)
            all_names = giving_names + receiving_names
            all_results = await asyncio.gather(
                *(espn_service.find_player_by_name(name, sport) for name in all_names)
            )
            giving_data = list(all_results[: len(giving_names)])
            receiving_data = list(all_results[len(giving_names) :])

            trade_complexity = classify_trade_query(request.query, trade_players_found=True)

            if trade_complexity == QueryComplexity.SIMPLE and trade_analyzer.can_analyze_locally(
                giving_data, receiving_data
            ):
                response = await _local_trade_decision(
                    request, giving_names, receiving_names, giving_data, receiving_data
                )
                await _store_decision(
                    request,
                    response,
                    player_a_name=", ".join(giving_names),
                    player_b_name=", ".join(receiving_names),
                    prompt_variant=variant,
                )
                return response

    # --- Standard start/sit flow ---

    # Extract players from query if not provided
    player_a = request.player_a
    player_b = request.player_b

    if not player_a or not player_b:
        extracted_a, extracted_b = extract_players_from_query(request.query)
        player_a = player_a or extracted_a
        player_b = player_b or extracted_b

    # Fetch real player data (parallel when both present)
    player_a_data = None
    player_b_data = None
    player_context = None

    if player_a and player_b:
        player_a_data, player_b_data = await asyncio.gather(
            espn_service.find_player_by_name(player_a, request.sport.value),
            espn_service.find_player_by_name(player_b, request.sport.value),
        )
    elif player_a:
        player_a_data = await espn_service.find_player_by_name(player_a, request.sport.value)
    elif player_b:
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

    # Auto-fill league context from authenticated user's profile (single DB lookup)
    user = None
    if current_user:
        user = await _get_user_by_id(current_user["user_id"])

    if not request.league_id and user and user.sleeper_league_id:
        request = request.model_copy(
            update={
                "league_id": user.sleeper_league_id,
                "sleeper_user_id": user.sleeper_user_id,
            }
        )

    # Inject Sleeper league context (roster + scoring)
    if request.league_id:
        try:
            league = await sleeper_service.get_league(request.league_id)
            if league:
                scoring_items = list(league.scoring_settings.items())[:15]
                scoring_summary = ", ".join(f"{k}: {v}" for k, v in scoring_items)
                league_ctx = f"League: {league.name} ({league.season}, {league.total_rosters} teams)\nScoring: {scoring_summary}"

                # Fetch user's actual roster if we have their Sleeper ID
                if request.sleeper_user_id:
                    roster = await sleeper_service.get_user_roster(
                        request.league_id, request.sleeper_user_id
                    )
                    if roster and roster.players:
                        players = await sleeper_service.get_players_by_ids(
                            roster.players, request.sport.value
                        )
                        starter_set = set(roster.starters or [])
                        player_lines = [
                            f"  {p.full_name} ({p.position}, {p.team or '?'})"
                            f"{' (' + p.injury_status + ')' if p.injury_status else ''}"
                            f"{' [STARTER]' if p.player_id in starter_set else ' [BENCH]'}"
                            for p in players
                        ]
                        league_ctx += "\n\nUser's roster:\n" + "\n".join(player_lines)

                if player_context:
                    player_context = f"{player_context}\n\n{league_ctx}"
                else:
                    player_context = league_ctx
        except Exception:
            logger.warning("Failed to fetch Sleeper league context for %s", request.league_id)

    # Auto-inject ESPN roster context if no Sleeper and user has ESPN connection
    if not request.league_id and user and user.espn_league_id and user.espn_roster_snapshot:
        try:
            player_lines = [
                f"  {p['name']} ({p.get('position', '?')}, {p.get('team', '?')}) [{p.get('lineup_slot', 'ROSTER')}]"
                for p in user.espn_roster_snapshot
            ]
            espn_ctx = (
                f"ESPN League {user.espn_league_id} ({user.espn_sport or 'nfl'})\n\nUser's roster:\n"
                + "\n".join(player_lines)
            )
            if player_context:
                player_context = f"{player_context}\n\n{espn_ctx}"
            else:
                player_context = espn_ctx
        except Exception:
            logger.warning("Failed to inject ESPN roster context")

    # Auto-inject Yahoo roster context if no Sleeper/ESPN and user has Yahoo connection
    if (
        not request.league_id
        and user
        and not user.espn_league_id
        and user.yahoo_league_key
        and user.yahoo_roster_snapshot
    ):
        try:
            player_lines = [
                f"  {p['name']} ({p.get('position', '?')}, {p.get('team', '?')}) [{p.get('status', 'Active')}]"
                for p in user.yahoo_roster_snapshot
            ]
            yahoo_ctx = (
                f"Yahoo League {user.yahoo_league_key} ({user.yahoo_sport or 'nfl'})\n\nUser's roster:\n"
                + "\n".join(player_lines)
            )
            if player_context:
                player_context = f"{player_context}\n\n{yahoo_ctx}"
            else:
                player_context = yahoo_ctx
        except Exception:
            logger.warning("Failed to inject Yahoo roster context")

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

        # Check and send budget alerts after Claude call
        await check_and_send_alerts()

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


async def _local_trade_decision(
    request: DecisionRequest,
    giving_names: list[str],
    receiving_names: list[str],
    giving_data: list[tuple],
    receiving_data: list[tuple],
) -> DecisionResponse:
    """
    Handle trade decisions locally using the core scoring engine.
    """
    sport = request.sport.value
    core_mode = CoreRiskMode(request.risk_mode.value)

    # Convert ESPN data to core PlayerStats for each player
    giving_core = []
    for info, stats in giving_data:
        game_logs = await espn_service.get_player_game_logs(info.id, sport)
        trends = espn_service.calculate_trends(game_logs, sport)
        opp = await espn_service.get_next_opponent(info.team_abbrev, sport)
        matchup = await espn_service.get_team_defense(opp, sport) if opp else None
        giving_core.append(adapt_espn_to_core(info, stats, trends=trends, matchup=matchup))

    receiving_core = []
    for info, stats in receiving_data:
        game_logs = await espn_service.get_player_game_logs(info.id, sport)
        trends = espn_service.calculate_trends(game_logs, sport)
        opp = await espn_service.get_next_opponent(info.team_abbrev, sport)
        matchup = await espn_service.get_team_defense(opp, sport) if opp else None
        receiving_core.append(adapt_espn_to_core(info, stats, trends=trends, matchup=matchup))

    # Run trade analysis
    trade_result = trade_analyzer.analyze(giving_core, receiving_core, core_mode, sport)

    # Map confidence
    confidence_map = {
        "low": Confidence.LOW,
        "medium": Confidence.MEDIUM,
        "high": Confidence.HIGH,
    }

    return DecisionResponse(
        decision=trade_result.decision,
        confidence=confidence_map.get(trade_result.confidence, Confidence.MEDIUM),
        rationale=trade_result.rationale,
        details=trade_result.to_details_dict(),
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


@app.post("/draft", response_model=DraftResponse)
async def draft_decision(
    request: DraftRequest,
    session_id: str | None = Query(default=None, description="Session ID for variant assignment"),
    current_user: dict | None = Depends(get_optional_user),
):
    """
    Rank a pool of players for draft pick recommendations.

    Players can be provided explicitly via the `players` field or
    extracted from the `query` via natural language parsing.
    Optionally boost players matching `position_needs`.

    Rate limits:
    - Free tier: 5 queries per day
    - Pro tier: unlimited queries
    """
    # Check rate limit
    effective_session = session_id or "anonymous"
    allowed, retry_after = await rate_limiter.check_rate_limit(effective_session)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    # Check tier-based daily limit if authenticated
    user_id = current_user["user_id"] if current_user else None
    if user_id is not None:
        tier_allowed, queries_today, weekly_limit = await _check_and_increment_query_count(user_id)
        if not tier_allowed:
            _raise_quota_exceeded(queries_today, weekly_limit)

    # Check if query is sports-related (skip when league connected)
    if not request.league_id:
        is_allowed, rejection_reason = _is_sports_query(request.query)
        if not is_allowed:
            _raise_off_topic(
                request.query,
                request.sport.value if hasattr(request.sport, "value") else str(request.sport),
            )

    # Determine player names: explicit list takes priority over query parsing
    player_names: list[str] | None = request.players
    if not player_names:
        player_names = extract_draft_players(request.query)

    # < 2 players → fall back to Claude
    if not player_names or len(player_names) < 2:
        return await _claude_draft_fallback(request, session_id)

    # Fetch ESPN data for all draft players
    sport = request.sport.value
    player_data = [await espn_service.find_player_by_name(name, sport) for name in player_names]

    # Classify complexity
    draft_complexity = classify_draft_query(request.query, draft_players_found=True)

    # Route to local or Claude
    if draft_complexity == QueryComplexity.SIMPLE and draft_assistant.can_analyze_locally(
        player_data
    ):
        response = await _local_draft_decision(request, player_names, player_data)
        await _store_draft_decision(request, response, player_names)
        return response

    # Fall back to Claude for complex queries or missing ESPN data
    return await _claude_draft_fallback(request, session_id)


@app.post("/waiver/recommend", response_model=WaiverResponse)
async def waiver_recommend(
    request: WaiverRequest,
    session_id: str | None = Query(default=None, description="Session ID for variant assignment"),
    current_user: dict | None = Depends(get_optional_user),
):
    """
    Generate waiver wire recommendations based on roster analysis.

    Requires a connected Sleeper league to analyze the user's roster.
    Uses Claude to generate recommendations tailored to position needs.

    Rate limits:
    - Free tier: 5 queries per day
    - Pro tier: unlimited queries
    """
    # Check rate limit
    effective_session = session_id or "anonymous"
    allowed, retry_after = await rate_limiter.check_rate_limit(effective_session)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    # Check tier-based daily limit if authenticated
    user_id = current_user["user_id"] if current_user else None
    if user_id is not None:
        tier_allowed, queries_today, weekly_limit = await _check_and_increment_query_count(user_id)
        if not tier_allowed:
            _raise_quota_exceeded(queries_today, weekly_limit)

    # Fetch user roster from Sleeper
    roster = await sleeper_service.get_user_roster(request.league_id, request.sleeper_user_id)
    if not roster or not roster.players:
        raise HTTPException(
            status_code=404,
            detail="Could not find your roster. Make sure your Sleeper league is connected.",
        )

    # Enrich roster with player details
    players = await sleeper_service.get_players_by_ids(roster.players, request.sport.value)
    if not players:
        raise HTTPException(
            status_code=404,
            detail="Could not load player data for your roster.",
        )

    # Analyze roster composition
    starter_ids = set(roster.starters or [])
    analysis = analyze_roster(players, starter_ids, request.sport.value)

    # Build Claude prompt with roster context
    prompt = build_waiver_prompt(
        analysis,
        request.sport.value,
        request.risk_mode.value,
        request.query,
        position_filter=request.position_filter,
    )

    # Check budget before calling Claude
    budget_exceeded, budget_msg = await _check_budget_exceeded()
    if budget_exceeded:
        raise HTTPException(
            status_code=402,
            detail=budget_msg or "Monthly API budget exceeded",
        )

    # Call Claude for recommendations
    try:
        result = await claude_service.make_decision(
            query=prompt,
            sport=request.sport.value,
            risk_mode=request.risk_mode.value,
            decision_type="waiver",
            player_context=prompt,
            use_cache=False,
        )

        # Parse JSON from Claude's response
        response_text = result.get("rationale", "") or result.get("decision", "")

        # Extract JSON block from response
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            parsed = json.loads(response_text[json_start:json_end])
        else:
            parsed = {"recommendations": [], "drop_candidates": [], "summary": response_text}

        recommendations = parsed.get("recommendations", [])
        drop_candidates = parsed.get("drop_candidates", [])
        summary = parsed.get("summary", "")

        # Build rationale from analysis + Claude summary
        rationale_parts = []
        if analysis.position_needs:
            rationale_parts.append(f"Position needs: {', '.join(analysis.position_needs)}.")
        if analysis.injured:
            injured_names = [p["name"] for p in analysis.injured]
            rationale_parts.append(f"Injured: {', '.join(injured_names)}.")
        if summary:
            rationale_parts.append(summary)
        rationale = " ".join(rationale_parts) if rationale_parts else "No urgent needs identified."

        # Determine confidence
        confidence = Confidence.MEDIUM
        if analysis.position_needs and len(analysis.position_needs) >= 2:
            confidence = Confidence.HIGH
        elif analysis.injured:
            confidence = Confidence.HIGH
        elif not recommendations:
            confidence = Confidence.LOW

        await check_and_send_alerts()

        return WaiverResponse(
            recommendations=recommendations,
            drop_candidates=drop_candidates,
            position_needs=analysis.position_needs,
            confidence=confidence,
            rationale=rationale,
            source="claude",
        )

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="Failed to parse waiver recommendations from AI response.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating waiver recommendations: {str(e)}",
        )


async def _local_draft_decision(
    request: DraftRequest,
    player_names: list[str],
    player_data: list[tuple],
) -> DraftResponse:
    """Handle draft decisions locally using the core scoring engine."""
    sport = request.sport.value
    core_mode = CoreRiskMode(request.risk_mode.value)

    # Convert ESPN data to core PlayerStats
    core_players = []
    for info, stats in player_data:
        game_logs = await espn_service.get_player_game_logs(info.id, sport)
        trends = espn_service.calculate_trends(game_logs, sport)
        opp = await espn_service.get_next_opponent(info.team_abbrev, sport)
        matchup = await espn_service.get_team_defense(opp, sport) if opp else None
        core_players.append(adapt_espn_to_core(info, stats, trends=trends, matchup=matchup))

    # Run draft analysis
    draft_result = draft_assistant.analyze(
        core_players, core_mode, sport, position_needs=request.position_needs
    )

    confidence_map = {
        "low": Confidence.LOW,
        "medium": Confidence.MEDIUM,
        "high": Confidence.HIGH,
    }

    return DraftResponse(
        recommended_pick=draft_result.recommended_pick.name
        if draft_result.recommended_pick
        else "",
        confidence=confidence_map.get(draft_result.confidence, Confidence.MEDIUM),
        rationale=draft_result.rationale,
        details=draft_result.to_details_dict(),
        source="local",
    )


async def _store_draft_decision(
    request: DraftRequest,
    response: DraftResponse,
    player_names: list[str],
) -> None:
    """Store draft decision in database for history and analytics."""
    if not db_service.is_configured:
        return

    try:
        # Get scores from details for storage
        ranked = (response.details or {}).get("ranked_players", [])
        score_a = ranked[0]["score"] if len(ranked) >= 1 else None
        score_b = ranked[1]["score"] if len(ranked) >= 2 else None
        margin = (
            round(score_a - score_b, 1) if score_a is not None and score_b is not None else None
        )

        async with db_service.session() as session:
            decision = DecisionModel(
                sport=request.sport.value,
                risk_mode=request.risk_mode.value,
                decision_type="draft",
                query=request.query,
                player_a_name=", ".join(player_names),
                player_b_name=response.recommended_pick,
                decision=f"Draft {response.recommended_pick}",
                confidence=response.confidence.value,
                rationale=response.rationale,
                source=response.source,
                score_a=score_a,
                score_b=score_b,
                margin=margin,
                league_type=request.league_type,
            )
            session.add(decision)
    except Exception as e:
        logger.error("Failed to store draft decision: %s", e)


async def _claude_draft_fallback(
    request: DraftRequest,
    session_id: str | None,
) -> DraftResponse:
    """Fall back to Claude for draft decisions that can't be handled locally."""
    budget_exceeded, budget_msg = await _check_budget_exceeded()
    if budget_exceeded:
        raise HTTPException(
            status_code=402,
            detail=budget_msg or "Monthly API budget exceeded",
        )

    # Build a DecisionRequest to reuse _claude_decision
    decide_req = DecisionRequest(
        sport=request.sport,
        risk_mode=request.risk_mode,
        decision_type=DecisionType.DRAFT,
        query=request.query,
        league_type=request.league_type,
        league_id=request.league_id,
        sleeper_user_id=request.sleeper_user_id,
    )

    variant = assign_variant(session_id)
    player_names = request.players or []
    player_context = f"Draft pool: {', '.join(player_names)}" if player_names else None

    response, _, _ = await _claude_decision(
        decide_req,
        player_a=", ".join(player_names) if player_names else None,
        player_b=None,
        player_context=player_context,
        prompt_variant=variant,
    )

    await check_and_send_alerts()

    return DraftResponse(
        recommended_pick=response.decision,
        confidence=response.confidence,
        rationale=response.rationale,
        details=response.details,
        source="claude",
    )


@app.post("/decide/stream")
async def make_decision_stream(
    request: DecisionRequest,
    session_id: str | None = Query(default=None, description="Session ID for variant assignment"),
    current_user: dict | None = Depends(get_optional_user),
):
    """
    Stream a fantasy sports decision (Server-Sent Events).

    Returns streamed text chunks from Claude for faster perceived response.
    Complex queries only - simple queries should use /decide.

    Rate limits:
    - Free tier: 5 queries per day
    - Pro tier: unlimited queries
    """
    # Check rate limit (use "anonymous" for requests without session_id)
    effective_session = session_id or "anonymous"
    allowed, retry_after = await rate_limiter.check_rate_limit(effective_session)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    # Check tier-based daily limit if authenticated
    user_id = current_user["user_id"] if current_user else None
    if user_id is not None:
        tier_allowed, queries_today, weekly_limit = await _check_and_increment_query_count(user_id)
        if not tier_allowed:
            _raise_quota_exceeded(queries_today, weekly_limit)

    # Check if query is sports-related (skip when league connected)
    if not request.league_id:
        is_allowed, rejection_reason = _is_sports_query(request.query)
        if not is_allowed:
            _raise_off_topic(
                request.query,
                request.sport.value if hasattr(request.sport, "value") else str(request.sport),
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

    # Auto-fill league context from authenticated user's profile (single DB lookup)
    user = None
    if current_user:
        user = await _get_user_by_id(current_user["user_id"])

    if not request.league_id and user and user.sleeper_league_id:
        request = request.model_copy(
            update={
                "league_id": user.sleeper_league_id,
                "sleeper_user_id": user.sleeper_user_id,
            }
        )

    # Inject Sleeper league context (roster + scoring)
    if request.league_id:
        try:
            league = await sleeper_service.get_league(request.league_id)
            if league:
                scoring_items = list(league.scoring_settings.items())[:15]
                scoring_summary = ", ".join(f"{k}: {v}" for k, v in scoring_items)
                league_ctx = f"League: {league.name} ({league.season}, {league.total_rosters} teams)\nScoring: {scoring_summary}"

                if request.sleeper_user_id:
                    roster = await sleeper_service.get_user_roster(
                        request.league_id, request.sleeper_user_id
                    )
                    if roster and roster.players:
                        players = await sleeper_service.get_players_by_ids(
                            roster.players, request.sport.value
                        )
                        starter_set = set(roster.starters or [])
                        player_lines = [
                            f"  {p.full_name} ({p.position}, {p.team or '?'})"
                            f"{' (' + p.injury_status + ')' if p.injury_status else ''}"
                            f"{' [STARTER]' if p.player_id in starter_set else ' [BENCH]'}"
                            for p in players
                        ]
                        league_ctx += "\n\nUser's roster:\n" + "\n".join(player_lines)

                if player_context:
                    player_context = f"{player_context}\n\n{league_ctx}"
                else:
                    player_context = league_ctx
        except Exception:
            logger.warning("Failed to fetch Sleeper league context for %s", request.league_id)

    # Auto-inject ESPN roster context if no Sleeper and user has ESPN connection
    if not request.league_id and user and user.espn_league_id and user.espn_roster_snapshot:
        try:
            player_lines = [
                f"  {p['name']} ({p.get('position', '?')}, {p.get('team', '?')}) [{p.get('lineup_slot', 'ROSTER')}]"
                for p in user.espn_roster_snapshot
            ]
            espn_ctx = (
                f"ESPN League {user.espn_league_id} ({user.espn_sport or 'nfl'})\n\nUser's roster:\n"
                + "\n".join(player_lines)
            )
            if player_context:
                player_context = f"{player_context}\n\n{espn_ctx}"
            else:
                player_context = espn_ctx
        except Exception:
            logger.warning("Failed to inject ESPN roster context")

    # Auto-inject Yahoo roster context if no Sleeper/ESPN and user has Yahoo connection
    if (
        not request.league_id
        and user
        and not user.espn_league_id
        and user.yahoo_league_key
        and user.yahoo_roster_snapshot
    ):
        try:
            player_lines = [
                f"  {p['name']} ({p.get('position', '?')}, {p.get('team', '?')}) [{p.get('status', 'Active')}]"
                for p in user.yahoo_roster_snapshot
            ]
            yahoo_ctx = (
                f"Yahoo League {user.yahoo_league_key} ({user.yahoo_sport or 'nfl'})\n\nUser's roster:\n"
                + "\n".join(player_lines)
            )
            if player_context:
                player_context = f"{player_context}\n\n{yahoo_ctx}"
            else:
                player_context = yahoo_ctx
        except Exception:
            logger.warning("Failed to inject Yahoo roster context")

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
                # Format as structured SSE event
                yield f"data: {json.dumps({'type': 'content', 'text': chunk})}\n\n"

            # Parse the full response and send structured 'done' event
            if stream_metadata:
                try:
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
                    # Send the parsed response to the client
                    yield f"data: {json.dumps({'type': 'done', 'response': response.model_dump(mode='json')})}\n\n"

                    # Persist decision to database
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
                    await check_and_send_alerts()
                except Exception as e:
                    logger.error("Failed to persist streaming decision: %s", e)

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


@app.post("/cron/sync", tags=["Admin"])
async def cron_sync(_admin=Depends(require_admin_key)):
    """Trigger background sync jobs on demand.

    Designed for external cron (GitHub Actions, Fly.io scheduled machine)
    to work around scale-to-zero killing long-running asyncio schedulers.
    """
    results = {}

    # Outcome sync
    if db_service.is_configured:
        try:
            from services.outcome_recorder import sync_recent_outcomes

            outcome = await sync_recent_outcomes(days_back=2)
            results["outcomes"] = outcome or {"status": "no_results"}
        except Exception as e:
            logger.exception("Cron outcome sync failed")
            results["outcomes"] = {"error": str(e)}
    else:
        results["outcomes"] = {"status": "skipped", "reason": "db not configured"}

    # Rankings recalculation
    if db_service.is_configured and redis_service.is_connected:
        try:
            from services.rankings_scheduler import rankings_scheduler

            await rankings_scheduler._run_rankings()
            results["rankings"] = {"status": "completed"}
        except Exception as e:
            logger.exception("Cron rankings sync failed")
            results["rankings"] = {"error": str(e)}
    else:
        results["rankings"] = {"status": "skipped", "reason": "db or redis not available"}

    return {"status": "completed", "results": results}


@app.post("/cache/clear", tags=["Admin"])
async def clear_cache(_admin=Depends(require_admin_key)):
    """Clear all caches (Claude in-memory + Redis). Requires admin API key."""
    claude_service.clear_cache()
    if redis_service.is_connected:
        await redis_service.clear_all()
    return {"status": "cleared"}


@app.post("/cache/invalidate/{sport}", tags=["Admin"])
async def invalidate_sport_cache(sport: Sport, _admin=Depends(require_admin_key)):
    """Invalidate all cached data for a specific sport. Requires admin API key."""
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


# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------


@app.get("/rate-limit/status")
async def get_rate_limit_status(
    session_id: str | None = Query(default=None, description="Session ID to check"),
):
    """
    Get current rate limit status for a session.

    Returns requests used, remaining, and reset time.
    """
    effective_session = session_id or "anonymous"
    return await rate_limiter.get_status(effective_session)


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
        logger.error("Failed to fetch usage: %s", e)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Budget Configuration
# ---------------------------------------------------------------------------


def _validate_webhook_url(url: str | None) -> str | None:
    """Validate webhook URL to prevent SSRF attacks."""
    if url is None:
        return None
    import ipaddress
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Webhook URL must use http:// or https://")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Webhook URL must have a valid hostname")
    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise ValueError("Webhook URL cannot point to localhost")
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise ValueError("Webhook URL cannot point to private/internal network")
    except ValueError as exc:
        if "cannot point" in str(exc):
            raise
        # Not an IP address (it's a domain name) — that's fine
    if len(url) > 2000:
        raise ValueError("Webhook URL too long")
    return url


class BudgetConfigRequest(BaseModel):
    """Request to set budget configuration."""

    monthly_limit_usd: float = Field(..., ge=0, description="Monthly spending cap in USD")
    alert_threshold_pct: int = Field(
        default=80, ge=0, le=100, description="Alert when spending reaches this percentage"
    )
    alerts_enabled: bool = Field(default=True, description="Enable webhook alerts")
    slack_webhook_url: str | None = Field(default=None, description="Slack webhook URL for alerts")
    discord_webhook_url: str | None = Field(
        default=None, description="Discord webhook URL for alerts"
    )

    @field_validator("slack_webhook_url", "discord_webhook_url")
    @classmethod
    def check_webhook_url(cls, v: str | None) -> str | None:
        return _validate_webhook_url(v)


class BudgetConfigResponse(BaseModel):
    """Budget configuration and current status."""

    monthly_limit_usd: float
    alert_threshold_pct: int
    alerts_enabled: bool
    slack_webhook_url: str | None
    discord_webhook_url: str | None
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


@app.get("/budget", response_model=BudgetConfigResponse, tags=["Admin"])
async def get_budget(_admin=Depends(require_admin_key)):
    """Get current budget configuration and spending status. Requires admin API key."""
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
                    alerts_enabled=True,
                    slack_webhook_url=None,
                    discord_webhook_url=None,
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
                alerts_enabled=config.alerts_enabled,
                slack_webhook_url=config.slack_webhook_url,
                discord_webhook_url=config.discord_webhook_url,
                current_month_spent_usd=round(current_spend, 4),
                percent_used=round(percent_used, 2),
                budget_exceeded=budget_exceeded,
                alert_triggered=alert_triggered,
                updated_at=config.updated_at.isoformat() if config.updated_at else None,
            )
    except Exception as e:
        logger.error("Failed to fetch budget: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/budget", response_model=BudgetConfigResponse, tags=["Admin"])
async def set_budget(request: BudgetConfigRequest, _admin=Depends(require_admin_key)):
    """Set monthly spending limit, alert threshold, and webhook URLs. Requires admin API key."""
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
                config.monthly_limit_usd = Decimal(str(request.monthly_limit_usd))
                config.alert_threshold_pct = request.alert_threshold_pct
                config.alerts_enabled = request.alerts_enabled
                config.slack_webhook_url = request.slack_webhook_url
                config.discord_webhook_url = request.discord_webhook_url
                config.updated_at = now
            else:
                # Create new
                config = BudgetConfig(
                    monthly_limit_usd=Decimal(str(request.monthly_limit_usd)),
                    alert_threshold_pct=request.alert_threshold_pct,
                    alerts_enabled=request.alerts_enabled,
                    slack_webhook_url=request.slack_webhook_url,
                    discord_webhook_url=request.discord_webhook_url,
                    created_at=now,
                    updated_at=now,
                )
                session.add(config)

        # Return updated status
        return await get_budget()
    except Exception as e:
        logger.error("Failed to set budget: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/budget/alerts", response_model=BudgetAlertResponse, tags=["Admin"])
async def get_budget_alerts(_admin=Depends(require_admin_key)):
    """Get any active budget warnings or alerts. Requires admin API key."""
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
        logger.error("Failed to fetch budget alerts: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class WebhookTestRequest(BaseModel):
    """Request to test a webhook URL."""

    webhook_type: str = Field(..., description="Either 'slack' or 'discord'")
    webhook_url: str = Field(..., description="The webhook URL to test")

    @field_validator("webhook_url")
    @classmethod
    def check_webhook_url(cls, v: str) -> str:
        result = _validate_webhook_url(v)
        if result is None:
            raise ValueError("Webhook URL is required")
        return result


@app.post("/budget/webhooks/test", tags=["Admin"])
async def test_budget_webhook(request: WebhookTestRequest, _admin=Depends(require_admin_key)):
    """Send a test notification to verify webhook configuration. Requires admin API key."""
    if request.webhook_type.lower() not in ("slack", "discord"):
        raise HTTPException(
            status_code=400,
            detail="webhook_type must be 'slack' or 'discord'",
        )

    success = await send_test_webhook(request.webhook_type, request.webhook_url)

    if success:
        return {"status": "success", "message": "Test notification sent successfully"}
    else:
        raise HTTPException(
            status_code=400,
            detail="Failed to send test notification. Check the webhook URL.",
        )


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
        logger.error("Failed to fetch history: %s", e)
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


@app.get("/integrations/espn/leagues", response_model=list[FantasyLeagueResponse])
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


@app.delete("/integrations/espn/disconnect")
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


@app.get("/integrations/espn/status")
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

    # Ephemeral state — consumed in seconds, OK to lose on restart
    _yahoo_oauth_states[f"{session_id}_state"] = state

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


@app.post("/integrations/yahoo/refresh", response_model=YahooTokenResponse)
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
    try:
        async with _resolve_session(session_id) as (db, session):
            await session_service.delete_credential(db, session, "yahoo")
            await db.commit()
    except HTTPException:
        pass  # Already disconnected or DB unavailable — idempotent

    # Clean up ephemeral OAuth state
    _yahoo_oauth_states.pop(f"{session_id}_state", None)

    return {"status": "disconnected"}


@app.get("/integrations/yahoo/status")
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
    if db_service.is_configured:
        async with db_service.session() as session:
            await notification_service.register_token(session, request.token)
    return {"status": "registered", "token": request.token}


@app.post("/notifications/unregister")
async def unregister_push_token(request: PushTokenRequest):
    """
    Unregister a device from push notifications.
    """
    if db_service.is_configured:
        async with db_service.session() as session:
            await notification_service.unregister_token(session, request.token)
    return {"status": "unregistered"}


@app.post("/notifications/send", tags=["Admin"])
async def send_notification_to_token(
    token: str = Query(..., description="Target push token"),
    request: SendNotificationRequest = ...,
    _admin=Depends(require_admin_key),
):
    """Send a notification to a specific device. Requires admin API key."""
    notification = PushNotification(
        to=token,
        title=request.title,
        body=request.body,
        data=request.data,
    )

    result = await notification_service.send_notification(notification)
    return result


@app.post("/notifications/broadcast", tags=["Admin"])
async def broadcast_notification(
    request: SendNotificationRequest, _admin=Depends(require_admin_key)
):
    """Send a notification to all registered devices. Requires admin API key."""
    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")
    async with db_service.session() as session:
        results = await notification_service.send_to_all(
            session,
            title=request.title,
            body=request.body,
            data=request.data,
        )

    return {
        "sent": len(results),
        "results": results,
    }


@app.get("/notifications/tokens", tags=["Admin"])
async def list_registered_tokens(_admin=Depends(require_admin_key)):
    """List all registered push tokens. Requires admin API key."""
    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")
    async with db_service.session() as session:
        tokens = await notification_service.get_all_tokens(session)
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
    - sport:{sport} — All updates for a sport (nba, nfl, mlb, nhl, soccer)
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
    if db_service.is_configured:
        async with db_service.session() as session:
            found = await accuracy_tracker.record_outcome(session, outcome)
            if not found:
                raise HTTPException(status_code=404, detail="Decision not found")
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
                        "actual_points_a": float(d.actual_points_a)
                        if d.actual_points_a is not None
                        else None,
                        "actual_points_b": float(d.actual_points_b)
                        if d.actual_points_b is not None
                        else None,
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
    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")
    async with db_service.session() as session:
        outcome = await accuracy_tracker.get_outcome(session, decision_id)
    if not outcome:
        raise HTTPException(status_code=404, detail="No outcome recorded for this decision")
    return {
        "decision_id": outcome.decision_id,
        "actual_points_a": outcome.actual_points_a,
        "actual_points_b": outcome.actual_points_b,
    }


class SyncOutcomesRequest(BaseModel):
    """Request to sync outcomes from ESPN box scores."""

    days_back: int = Field(default=2, ge=1, le=14, description="Days back to process")
    sport: str | None = Field(
        default=None, description="Filter by sport (nba, nfl, mlb, nhl, soccer)"
    )


@app.post("/accuracy/sync")
async def sync_outcomes(request: SyncOutcomesRequest | None = None):
    """
    Manually trigger outcome recording from ESPN box scores.

    Fetches actual fantasy points for decisions from the past N days
    and records outcomes (correct/incorrect/push).
    """
    from services.outcome_recorder import sync_recent_outcomes

    days_back = request.days_back if request else 2
    sport = request.sport if request else None

    # Validate sport if provided
    if sport and sport not in ("nba", "nfl", "mlb", "nhl", "soccer"):
        raise HTTPException(
            status_code=400, detail="Invalid sport. Must be nba, nfl, mlb, nhl, or soccer."
        )

    try:
        result = await sync_recent_outcomes(days_back=days_back, sport=sport)
        return {
            "status": "completed",
            **result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@app.delete("/accuracy/reset")
async def reset_accuracy(current_user: dict = Depends(get_current_user)):
    """Delete all decisions for the current user, resetting accuracy tracking."""
    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")
    async with db_service.session() as session:
        result = await session.execute(
            delete(DecisionModel).where(DecisionModel.user_id == current_user["user_id"])
        )
        await session.commit()
    return {"status": "reset", "deleted": result.rowcount}


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
        logger.error("Failed to fetch experiment results: %s", e)
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


# ---------------------------------------------------------------------------
# User Engagement Metrics
# ---------------------------------------------------------------------------


@app.get("/engagement")
async def get_engagement_metrics(
    period: str = Query("month", pattern="^(today|week|month)$"),
    sport: Sport | None = None,
):
    """Get user engagement analytics: sessions, queries, retention, features, depth."""
    if not db_service.is_configured:
        return {"error": "Database not configured"}

    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if period == "today":
        period_start = today_start
    elif period == "week":
        period_start = today_start - timedelta(days=now.weekday())
    else:
        period_start = today_start.replace(day=1)

    try:
        async with db_service.session() as session:
            # Fetch decisions
            dec_q = select(DecisionModel).where(DecisionModel.created_at >= period_start)
            if sport:
                dec_q = dec_q.where(DecisionModel.sport == sport.value)
            dec_rows = (await session.execute(dec_q)).scalars().all()
            decisions = [
                {
                    "id": str(d.id),
                    "user_id": d.user_id,
                    "session_id": d.session_id,
                    "sport": d.sport,
                    "risk_mode": d.risk_mode,
                    "decision_type": d.decision_type,
                    "source": d.source,
                    "cache_hit": d.cache_hit,
                    "created_at": d.created_at,
                }
                for d in dec_rows
            ]

            # Fetch sessions
            sess_q = select(SessionModel).where(SessionModel.created_at >= period_start)
            sess_rows = (await session.execute(sess_q)).scalars().all()
            sessions_data = [
                {
                    "id": str(s.id),
                    "session_id": str(s.id),
                    "platform": s.platform,
                    "status": s.status,
                    "created_at": s.created_at,
                    "last_active_at": s.last_active_at,
                    "user_id": s.user_id,
                }
                for s in sess_rows
            ]

            # Fetch users active in period
            user_ids = {d.user_id for d in dec_rows if d.user_id}
            users_data: list[dict] = []
            if user_ids:
                user_q = select(User).where(
                    User.id.in_([int(uid) for uid in user_ids if uid.isdigit()])
                )
                user_rows = (await session.execute(user_q)).scalars().all()
                users_data = [
                    {
                        "id": str(u.id),
                        "created_at": u.created_at,
                    }
                    for u in user_rows
                ]

            metrics = engagement_tracker.compute_metrics(
                decisions=decisions,
                sessions=sessions_data,
                users=users_data,
                period_start=period_start,
                period_end=now,
            )

            # Update Prometheus gauges
            update_engagement_metrics(metrics)

            return {
                "period": period,
                "period_start": period_start.isoformat(),
                "period_end": now.isoformat(),
                "sessions": {
                    "active_count": metrics.sessions.active_count,
                    "avg_duration_minutes": metrics.sessions.avg_duration_minutes,
                    "by_platform": metrics.sessions.by_platform,
                    "total": metrics.sessions.total,
                },
                "queries": {
                    "total": metrics.queries.total_queries,
                    "avg_per_day": metrics.queries.avg_queries_per_day,
                    "by_date": metrics.queries.by_date,
                    "popular_sports": metrics.queries.popular_sports,
                    "popular_decision_types": metrics.queries.popular_decision_types,
                    "popular_risk_modes": metrics.queries.popular_risk_modes,
                },
                "retention": {
                    "new_users": metrics.retention.new_users,
                    "returning_users": metrics.retention.returning_users,
                    "dau": metrics.retention.dau,
                    "wau": metrics.retention.wau,
                    "mau": metrics.retention.mau,
                },
                "features": {
                    "local_routing": {
                        "count": metrics.features.local_routing_count,
                        "pct": metrics.features.local_routing_pct,
                    },
                    "claude_routing": {
                        "count": metrics.features.claude_routing_count,
                        "pct": metrics.features.claude_routing_pct,
                    },
                    "cache": {
                        "hits": metrics.features.cache_hits,
                        "misses": metrics.features.cache_misses,
                        "hit_rate": metrics.features.cache_hit_rate,
                    },
                },
                "depth": {
                    "avg_queries_per_session": metrics.depth.avg_queries_per_session,
                    "avg_queries_per_user_per_day": metrics.depth.avg_queries_per_user_per_day,
                    "active_users": metrics.depth.active_users,
                    "active_sessions": metrics.depth.active_sessions,
                },
            }
    except Exception as e:
        logger.error("Failed to fetch engagement metrics: %s", e)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Stripe Billing Endpoints
# ---------------------------------------------------------------------------


class CheckoutRequest(BaseModel):
    """Request to create a Stripe checkout session."""

    price_id: str = Field(
        ...,
        description="Stripe Price ID for the subscription",
    )
    success_url: str = Field(
        ..., max_length=500, description="URL to redirect to after successful checkout"
    )
    cancel_url: str = Field(
        ..., max_length=500, description="URL to redirect to if checkout is cancelled"
    )
    league_id: int | None = Field(default=None, description="League ID for pro_league checkout")


class CheckoutResponse(BaseModel):
    """Response with checkout session URL."""

    checkout_url: str


class PortalRequest(BaseModel):
    """Request to create a Stripe billing portal session."""

    return_url: str = Field(
        ..., max_length=500, description="URL to return to after portal session"
    )


class PortalResponse(BaseModel):
    """Response with billing portal URL."""

    portal_url: str


class BillingStatusResponse(BaseModel):
    """Current billing status for user."""

    tier: str
    status: str
    queries_today: int
    weekly_limit: int
    queries_remaining: int | None  # None if unlimited
    subscription_id: str | None = None
    current_period_end: str | None = None
    cancel_at_period_end: bool = False


async def _get_user_by_id(user_id: int) -> User | None:
    """Get user from database by ID."""
    if not db_service.is_configured:
        return None

    async with db_service.session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


@app.get("/billing/prices")
async def get_billing_prices():
    """Return available Stripe price IDs for checkout."""
    return {"prices": {k: v for k, v in stripe_billing.PRICE_IDS.items() if v}}


@app.post("/billing/create-checkout", response_model=CheckoutResponse)
async def create_checkout(
    request: CheckoutRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Create a Stripe Checkout session for Pro subscription upgrade.

    Redirects user to Stripe-hosted checkout page. Requires authentication.
    """
    if not stripe_billing.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Stripe billing is not configured. Set STRIPE_SECRET_KEY.",
        )

    user_id = current_user["user_id"]
    user_email = current_user["email"]

    try:
        extra_metadata = None
        if request.league_id is not None:
            extra_metadata = {
                "league_id": str(request.league_id),
                "plan_type": "pro_league",
            }

        checkout_url = await stripe_billing.create_checkout_session(
            user_id=user_id,
            user_email=user_email,
            price_id=request.price_id,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            extra_metadata=extra_metadata,
        )
        return CheckoutResponse(checkout_url=checkout_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create checkout session: {e}")


@app.post("/billing/create-portal", response_model=PortalResponse)
async def create_portal(
    request: PortalRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Create a Stripe Billing Portal session for subscription management.

    Allows users to update payment method, cancel subscription, etc. Requires authentication.
    """
    if not stripe_billing.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Stripe billing is not configured. Set STRIPE_SECRET_KEY.",
        )

    # Get user's Stripe customer ID
    user = await _get_user_by_id(current_user["user_id"])
    if not user or not user.stripe_customer_id:
        raise HTTPException(
            status_code=404,
            detail="User has no active subscription. Subscribe first.",
        )

    try:
        portal_url = await stripe_billing.create_portal_session(
            customer_id=user.stripe_customer_id,
            return_url=request.return_url,
        )
        return PortalResponse(portal_url=portal_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create portal session: {e}")


@app.post("/billing/webhook")
async def handle_stripe_webhook(request: Request):
    """
    Handle Stripe webhook events.

    Processes subscription lifecycle events:
    - checkout.session.completed
    - customer.subscription.updated
    - customer.subscription.deleted
    - invoice.payment_failed
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing Stripe signature header")

    try:
        result = await stripe_billing.handle_webhook(payload, sig_header)
        return result
    except ValueError as e:
        logger.warning("Stripe webhook validation failed: %s", e)
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    except Exception as e:
        logger.error("Stripe webhook processing failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Webhook processing failed")


@app.get("/billing/status", response_model=BillingStatusResponse)
async def get_billing_status(
    current_user: dict = Depends(get_current_user),
):
    """
    Get current billing status for a user.

    Returns subscription tier, usage, and limits. Requires authentication.
    """
    user = await _get_user_by_id(current_user["user_id"])

    if not user:
        return BillingStatusResponse(
            tier="free",
            status="none",
            queries_today=0,
            weekly_limit=FREE_TIER_WEEKLY_LIMIT,
            queries_remaining=FREE_TIER_WEEKLY_LIMIT,
        )

    # Check if queries_reset_at needs update for new week
    now = datetime.now(UTC)
    queries_today = user.queries_today
    reset_at = user.queries_reset_at
    # Handle timezone-naive timestamps from DB (TIMESTAMP vs TIMESTAMPTZ)
    if reset_at is not None and reset_at.tzinfo is None:
        reset_at = reset_at.replace(tzinfo=UTC)
    if reset_at is None or (now - reset_at) >= timedelta(days=7):
        queries_today = 0

    # Check direct Pro OR league-inherited Pro
    is_pro = user.subscription_tier == "pro"
    if not is_pro:
        try:
            is_pro = await stripe_billing.is_league_pro(user.id)
        except Exception:
            pass

    # Determine limits
    if is_pro:
        weekly_limit = -1  # Unlimited
        queries_remaining = None
    else:
        weekly_limit = FREE_TIER_WEEKLY_LIMIT
        queries_remaining = max(0, weekly_limit - queries_today)

    # Get Stripe subscription details if available
    subscription_status = "none"
    current_period_end = None
    cancel_at_period_end = False

    if user.stripe_customer_id:
        stripe_status = stripe_billing.get_subscription_status(user.stripe_customer_id)
        subscription_status = stripe_status.get("status", "none")
        current_period_end = stripe_status.get("current_period_end")
        cancel_at_period_end = stripe_status.get("cancel_at_period_end", False)

    return BillingStatusResponse(
        tier=user.subscription_tier,
        status=subscription_status,
        queries_today=queries_today,
        weekly_limit=weekly_limit,
        queries_remaining=queries_remaining,
        subscription_id=user.stripe_subscription_id,
        current_period_end=current_period_end,
        cancel_at_period_end=cancel_at_period_end,
    )


# ---------------------------------------------------------------------------
# Weekly Recaps
# ---------------------------------------------------------------------------


class WeeklyRecapResponse(BaseModel):
    """Response model for a weekly recap."""

    id: str
    week_start: str
    week_end: str
    total_decisions: int
    correct_decisions: int
    incorrect_decisions: int
    pending_decisions: int
    accuracy_pct: float | None
    avg_confidence: str | None
    most_asked_sport: str | None
    narrative: str
    highlights: str | None
    created_at: str


@app.get("/recaps/weekly", response_model=list[WeeklyRecapResponse])
async def get_weekly_recaps(
    limit: int = Query(default=10, ge=1, le=50),
    current_user: dict = Depends(require_pro),
):
    """
    Get stored weekly recaps for the authenticated user.

    Returns most recent recaps first. Requires authentication.
    """
    if not db_service.is_configured:
        return []

    from services.weekly_recap import get_user_recaps

    try:
        async with db_service.session() as session:
            recaps = await get_user_recaps(session, current_user["user_id"], limit)
            return [
                WeeklyRecapResponse(
                    id=str(r.id),
                    week_start=r.week_start.isoformat() if r.week_start else "",
                    week_end=r.week_end.isoformat() if r.week_end else "",
                    total_decisions=r.total_decisions,
                    correct_decisions=r.correct_decisions,
                    incorrect_decisions=r.incorrect_decisions,
                    pending_decisions=r.pending_decisions,
                    accuracy_pct=float(r.accuracy_pct) if r.accuracy_pct is not None else None,
                    avg_confidence=r.avg_confidence,
                    most_asked_sport=r.most_asked_sport,
                    narrative=r.narrative,
                    highlights=r.highlights,
                    created_at=r.created_at.isoformat() if r.created_at else "",
                )
                for r in recaps
            ]
    except Exception as e:
        logger.error("Failed to fetch recaps: %s", e)
        return []


@app.post("/recaps/weekly/generate", response_model=WeeklyRecapResponse | None)
async def generate_recap(
    current_user: dict = Depends(require_pro),
):
    """
    Generate a weekly recap for the current week.

    If a recap already exists for this week, returns the cached version.
    Requires authentication. Pro users only.
    """
    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")

    user = await _get_user_by_id(current_user["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    from services.weekly_recap import generate_weekly_recap

    try:
        async with db_service.session() as session:
            recap = await generate_weekly_recap(
                session=session,
                user_id=user.id,
                user_name=user.name,
            )

            if recap is None:
                return None

            return WeeklyRecapResponse(
                id=str(recap.id),
                week_start=recap.week_start.isoformat() if recap.week_start else "",
                week_end=recap.week_end.isoformat() if recap.week_end else "",
                total_decisions=recap.total_decisions,
                correct_decisions=recap.correct_decisions,
                incorrect_decisions=recap.incorrect_decisions,
                pending_decisions=recap.pending_decisions,
                accuracy_pct=float(recap.accuracy_pct) if recap.accuracy_pct is not None else None,
                avg_confidence=recap.avg_confidence,
                most_asked_sport=recap.most_asked_sport,
                narrative=recap.narrative,
                highlights=recap.highlights,
                created_at=recap.created_at.isoformat() if recap.created_at else "",
            )
    except Exception as e:
        logger.error("Failed to generate recap: %s", e)
        raise HTTPException(status_code=500, detail="Failed to generate recap") from e


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
