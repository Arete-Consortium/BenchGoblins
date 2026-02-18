"""
BenchGoblin API — Fantasy Sports Decision Engine
"""

import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sentry_sdk
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import Integer as SAInteger
from sqlalchemy import func, select, text

# ---------------------------------------------------------------------------
# Structured Logging
# ---------------------------------------------------------------------------

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)
logger = logging.getLogger("benchgoblins")

from models.database import User
from models.database import Decision as DecisionModel
from models.database import Session as SessionModel
from models.schemas import Sport
from monitoring import MetricsMiddleware, metrics_endpoint, update_engagement_metrics
from routes.auth import get_current_user, get_optional_user
from routes.auth import router as auth_router
from routes.billing import router as billing_router
from routes.decisions import router as decisions_router
from routes.integrations import router as integrations_router
from routes.sessions import router as sessions_router
from services.accuracy import AccuracyTracker, DecisionOutcome
from services.claude import claude_service
from services.database import db_service
from services.engagement import engagement_tracker
from services.espn import espn_service
from services.espn_fantasy import espn_fantasy_service
from services.notifications import PushNotification, notification_service
from services.redis import redis_service
from services.sleeper import sleeper_service
from services.variants import (
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
    logger.info("Sentry error monitoring enabled")

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup app resources"""
    # ---------------------------------------------------------------------------
    # Startup Validation — fail fast in production
    # ---------------------------------------------------------------------------
    _missing_env: list[str] = []
    is_production = os.getenv("ENVIRONMENT", "development") == "production"

    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.warning("ANTHROPIC_API_KEY not set — Claude integration disabled")
    if not os.getenv("DATABASE_URL"):
        logger.warning("DATABASE_URL not set — persistence disabled")
        _missing_env.append("DATABASE_URL")
    if not os.getenv("JWT_SECRET_KEY"):
        logger.warning("JWT_SECRET_KEY not set — auth will use insecure default")

    if is_production:
        for var in ("ANTHROPIC_API_KEY", "DATABASE_URL", "JWT_SECRET_KEY", "SESSION_ENCRYPTION_KEY"):
            if not os.getenv(var):
                _missing_env.append(var)
        if _missing_env:
            msg = f"Missing required env vars for production: {', '.join(_missing_env)}"
            logger.critical(msg)
            raise SystemExit(msg)

    # Initialize services
    if claude_service.is_available:
        logger.info("Claude API configured and ready")

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
        except Exception as e:
            if is_production:
                raise SystemExit(f"PostgreSQL connection failed: {e}")
            logger.error("PostgreSQL connection failed: %s", e)
    else:
        logger.warning("DATABASE_URL not set — persistence disabled")

    # Connect to Redis
    if redis_service.is_configured:
        try:
            await redis_service.connect()
            logger.info("Redis connected")
        except Exception as e:
            logger.warning("Redis connection failed: %s", e)
    else:
        logger.warning("REDIS_URL not set — caching disabled")

    logger.info("ESPN data service ready")
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
    title="BenchGoblin API",
    description=(
        "Fantasy sports decision engine using role stability,"
        " spatial opportunity, and matchup context."
    ),
    version="0.3.0",
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
    allow_headers=["authorization", "content-type", "x-session-id"],
)

# Performance monitoring middleware
app.add_middleware(MetricsMiddleware)

# Prometheus metrics endpoint — restricted by IP or auth token.
METRICS_TRUSTED_IPS = os.getenv("METRICS_TRUSTED_IPS", "127.0.0.1,::1").split(",")


@app.get("/metrics", include_in_schema=False)
async def protected_metrics(request: Request):
    """Prometheus metrics (restricted to trusted IPs or authenticated users)."""
    client_ip = request.client.host if request.client else ""
    if client_ip in METRICS_TRUSTED_IPS:
        return await metrics_endpoint(request)
    # Require auth for external callers
    auth_header = request.headers.get("authorization", "")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Authentication required")
    from routes.auth import get_current_user_token, get_current_user as _get_user
    token = await get_current_user_token(auth_header)
    await _get_user(token)
    return await metrics_endpoint(request)

# ---------------------------------------------------------------------------
# Include Domain Routers
# ---------------------------------------------------------------------------

app.include_router(sessions_router)
app.include_router(auth_router)
app.include_router(decisions_router)
app.include_router(integrations_router)
app.include_router(billing_router)


# ---------------------------------------------------------------------------
# Core Utility Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health_check():
    """Health check endpoint — always returns fast so Railway doesn't kill us."""
    # Redis check is async; wrap in a timeout so a slow Redis can't stall deploy
    redis_healthy = False
    if redis_service.is_connected:
        try:
            import asyncio

            redis_healthy = await asyncio.wait_for(redis_service.health_check(), timeout=2.0)
        except Exception:
            redis_healthy = False

    return {
        "status": "healthy",
        "version": "0.7.0",
        "claude_available": claude_service.is_available,
        "espn_available": True,
        "postgres_connected": db_service.is_configured,
        "redis_connected": redis_healthy,
        "sentry_enabled": bool(SENTRY_DSN),
    }


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
    """Invalidate all cached data for a specific sport."""
    if not redis_service.is_connected:
        return {"status": "skipped", "reason": "redis not connected", "keys_deleted": 0}

    total_deleted = 0
    for pattern in [
        f"decision:{sport.value}:*",
        f"player:{sport.value}:*",
        f"search:{sport.value}:*",
    ]:
        total_deleted += await redis_service.clear_pattern(pattern)

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

from services.rate_limiter import rate_limiter


@app.get("/rate-limit/status")
async def get_rate_limit_status(
    session_id: str | None = Query(default=None, description="Session ID to check"),
):
    """Get current rate limit status for a session."""
    effective_session = session_id or "anonymous"
    return await rate_limiter.get_status(effective_session)


@app.get("/usage")
async def get_token_usage(
    sport: Sport | None = None,
):
    """Get Claude API token usage and estimated costs."""
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
        logger.error("Failed to fetch usage: %s", e, exc_info=True)
        return {"error": str(e)}


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
    """Register a device for push notifications."""
    notification_service.register_token(request.token)
    return {"status": "registered", "token": request.token}


@app.post("/notifications/unregister")
async def unregister_push_token(request: PushTokenRequest):
    """Unregister a device from push notifications."""
    notification_service.unregister_token(request.token)
    return {"status": "unregistered"}


@app.post("/notifications/send")
async def send_notification_to_token(
    token: str = Query(..., description="Target push token"),
    request: SendNotificationRequest = ...,
):
    """Send a notification to a specific device (admin/testing endpoint)."""
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
    """Send a notification to all registered devices (admin endpoint)."""
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
    """List all registered push tokens (admin endpoint)."""
    tokens = notification_service.get_all_tokens()
    return {"count": len(tokens), "tokens": tokens}


# ---------------------------------------------------------------------------
# WebSocket — Real-Time Updates
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = Query(default=None)):
    """
    WebSocket endpoint for real-time updates (authenticated).

    Connect with: ws://host/ws?token=<JWT>
    """
    from services.auth import InvalidTokenError, verify_jwt_token, is_token_blacklisted

    # Authenticate before accepting the connection
    if not token:
        await websocket.close(code=1008, reason="Missing authentication token")
        return

    if is_token_blacklisted(token):
        await websocket.close(code=1008, reason="Token has been revoked")
        return

    try:
        verify_jwt_token(token)
    except (InvalidTokenError, Exception):
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    connection_id = await connection_manager.connect(websocket)
    try:
        while True:
            message = await websocket.receive_text()
            await connection_manager.handle_message(connection_id, message)
    except WebSocketDisconnect:
        await connection_manager.disconnect(connection_id)


@app.get("/ws/stats")
async def websocket_stats(current_user: dict = Depends(get_current_user)):
    """Get WebSocket connection statistics (requires authentication)."""
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


class SyncOutcomesRequest(BaseModel):
    """Request to sync outcomes from ESPN box scores."""

    days_back: int = Field(default=2, ge=1, le=14, description="Days back to process")
    sport: str | None = Field(
        default=None, description="Filter by sport (nba, nfl, mlb, nhl, soccer)"
    )


@app.post("/accuracy/sync")
async def sync_outcomes(request: SyncOutcomesRequest | None = None):
    """Manually trigger outcome recording from ESPN box scores."""
    from services.outcome_recorder import sync_recent_outcomes

    days_back = request.days_back if request else 2
    sport = request.sport if request else None

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
        logger.error("League sync failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="League sync failed")


# ---------------------------------------------------------------------------
# A/B Experiment Endpoints
# ---------------------------------------------------------------------------


@app.get("/experiments/active")
async def get_active_experiment():
    """Get current A/B experiment configuration."""
    return get_experiment_config()


@app.get("/experiments/results")
async def get_experiment_results():
    """Get A/B experiment results."""
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
        logger.error("Failed to fetch experiment results: %s", e, exc_info=True)
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
    """Get user engagement analytics."""
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
        logger.error("Failed to fetch engagement metrics: %s", e, exc_info=True)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Waitlist
# ---------------------------------------------------------------------------


class WaitlistRequest(BaseModel):
    """Request to join the waitlist."""

    email: str = Field(..., description="Email address", max_length=255)
    source: str = Field(default="landing", max_length=50)


@app.post("/waitlist")
async def join_waitlist(request: WaitlistRequest):
    """Add email to the draft-season waitlist."""
    import re as _re

    if not _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", request.email):
        raise HTTPException(status_code=400, detail="Invalid email address")

    if not db_service.is_configured:
        logger.info("Waitlist signup (no DB): %s", request.email)
        return {"status": "ok"}

    from models.database import WaitlistEntry

    try:
        async with db_service.session() as session:
            entry = WaitlistEntry(email=request.email.lower().strip(), source=request.source)
            session.add(entry)
        return {"status": "ok"}
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            return {"status": "ok", "message": "Already on the list"}
        logger.error("Waitlist signup failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to join waitlist")


# ---------------------------------------------------------------------------
# Manual Roster Entry
# ---------------------------------------------------------------------------


class ManualPlayerEntry(BaseModel):
    """A single player in a manual roster."""

    name: str = Field(..., min_length=1, max_length=100)
    position: str = Field(..., max_length=20)
    team: str = Field(default="", max_length=50)


class ManualRosterRequest(BaseModel):
    """Request to submit a manual roster."""

    sport: Sport
    players: list[ManualPlayerEntry] = Field(..., min_length=1, max_length=30)
    league_type: str | None = Field(default=None, max_length=50)
    team_name: str | None = Field(default=None, max_length=100)


class ManualRosterResponse(BaseModel):
    """Response after saving a manual roster."""

    id: str
    sport: str
    player_count: int


@app.post("/roster/manual", response_model=ManualRosterResponse)
async def submit_manual_roster(
    request: ManualRosterRequest,
    session_id: str | None = Query(default=None),
    current_user: dict | None = Depends(get_optional_user),
):
    """Submit a roster manually when league sync isn't available."""
    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")

    from models.database import ManualRoster

    user_id = str(current_user["user_id"]) if current_user else None

    async with db_service.session() as session:
        roster = ManualRoster(
            user_id=user_id,
            session_id=session_id,
            sport=request.sport.value,
            league_type=request.league_type,
            team_name=request.team_name,
            players=[p.model_dump() for p in request.players],
        )
        session.add(roster)
        await session.flush()
        roster_id = str(roster.id)

    return ManualRosterResponse(
        id=roster_id,
        sport=request.sport.value,
        player_count=len(request.players),
    )


@app.get("/roster/manual")
async def get_manual_rosters(
    sport: Sport | None = None,
    session_id: str | None = Query(default=None),
    current_user: dict | None = Depends(get_optional_user),
):
    """Get saved manual rosters for the current user/session."""
    if not db_service.is_configured:
        return {"rosters": []}

    from models.database import ManualRoster

    user_id = str(current_user["user_id"]) if current_user else None

    async with db_service.session() as session:
        q = select(ManualRoster).order_by(ManualRoster.updated_at.desc()).limit(20)
        if user_id:
            q = q.where(ManualRoster.user_id == user_id)
        elif session_id:
            q = q.where(ManualRoster.session_id == session_id)
        else:
            return {"rosters": []}

        if sport:
            q = q.where(ManualRoster.sport == sport.value)

        rows = (await session.execute(q)).scalars().all()
        return {
            "rosters": [
                {
                    "id": str(r.id),
                    "sport": r.sport,
                    "team_name": r.team_name,
                    "league_type": r.league_type,
                    "players": r.players,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ]
        }


# ---------------------------------------------------------------------------
# Goblin Score — Single-Player Index Lookup
# ---------------------------------------------------------------------------


class GoblinScoreResponse(BaseModel):
    """Single-player Goblin Score (five-index breakdown)."""

    player_name: str
    team: str
    position: str
    sport: str
    goblin_score: float
    risk_mode: str
    indices: dict


@app.get("/goblin-score/{sport}/{player_name}", response_model=GoblinScoreResponse)
async def get_goblin_score(
    sport: Sport,
    player_name: str,
    risk_mode: str = Query(default="median", pattern="^(floor|median|ceiling)$"),
):
    """Get a single player's Goblin Score and five-index breakdown."""
    from core.scoring import RiskMode as CoreRiskMode
    from core.scoring import composite_score, calculate_indices
    from services.scoring_adapter import adapt_espn_to_core

    player_data = await espn_service.find_player_by_name(player_name, sport.value)
    if not player_data:
        raise HTTPException(status_code=404, detail=f"Player '{player_name}' not found")

    info, stats = player_data

    game_logs = await espn_service.get_player_game_logs(info.id, sport.value)
    trends = espn_service.calculate_trends(game_logs, sport.value)
    opp = await espn_service.get_next_opponent(info.team_abbrev, sport.value)
    matchup = await espn_service.get_team_defense(opp, sport.value) if opp else None

    core_player = adapt_espn_to_core(info, stats, trends=trends, matchup=matchup)
    core_mode = CoreRiskMode(risk_mode)

    indices = calculate_indices(core_player)
    score = composite_score(indices, core_mode)

    return GoblinScoreResponse(
        player_name=info.name,
        team=info.team_abbrev or info.team or "",
        position=info.position or "",
        sport=sport.value,
        goblin_score=round(score, 1),
        risk_mode=risk_mode,
        indices={
            "sci": round(indices.sci, 1),
            "rmi": round(indices.rmi, 1),
            "gis": round(indices.gis, 1),
            "od": round(indices.od, 1),
            "msf": round(indices.msf, 1),
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
