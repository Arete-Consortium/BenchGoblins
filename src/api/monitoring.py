"""
Performance monitoring and metrics for BenchGoblin API.

Provides:
- Prometheus metrics endpoint (/metrics)
- Request latency/count tracking
- Custom business metrics
- Integration with Sentry performance tracing
"""

import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# =============================================================================
# Application Info
# =============================================================================

APP_INFO = Info("benchgoblins_app", "BenchGoblin application information")
APP_INFO.info(
    {
        "version": "0.3.0",
        "name": "BenchGoblin API",
    }
)

# =============================================================================
# Request Metrics
# =============================================================================

REQUEST_COUNT = Counter(
    "benchgoblins_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "benchgoblins_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

REQUESTS_IN_PROGRESS = Gauge(
    "benchgoblins_http_requests_in_progress",
    "Number of HTTP requests currently in progress",
    ["method", "endpoint"],
)

# =============================================================================
# Business Metrics
# =============================================================================

DECISION_REQUESTS = Counter(
    "benchgoblins_decisions_total",
    "Total decision requests",
    ["sport", "query_type", "risk_mode"],
)

DECISION_LATENCY = Histogram(
    "benchgoblins_decision_duration_seconds",
    "Decision request latency in seconds",
    ["sport", "routed_to"],  # routed_to: local, claude
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

CLAUDE_REQUESTS = Counter(
    "benchgoblins_claude_requests_total",
    "Total requests to Claude API",
    ["status", "prompt_variant"],  # status: success, error, rate_limited
)

CLAUDE_TOKENS = Counter(
    "benchgoblins_claude_tokens_total",
    "Total tokens used in Claude requests",
    ["type"],  # input, output
)

CACHE_OPERATIONS = Counter(
    "benchgoblins_cache_operations_total",
    "Cache operations",
    ["operation", "result"],  # operation: get, set; result: hit, miss, error
)

EXTERNAL_API_REQUESTS = Counter(
    "benchgoblins_external_api_requests_total",
    "External API requests",
    ["service", "status"],  # service: espn, yahoo, sleeper
)

EXTERNAL_API_LATENCY = Histogram(
    "benchgoblins_external_api_duration_seconds",
    "External API latency in seconds",
    ["service"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

DATABASE_OPERATIONS = Counter(
    "benchgoblins_database_operations_total",
    "Database operations",
    ["operation", "table", "status"],  # operation: select, insert, update, delete
)

DATABASE_LATENCY = Histogram(
    "benchgoblins_database_duration_seconds",
    "Database operation latency in seconds",
    ["operation"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

ACTIVE_USERS = Gauge(
    "benchgoblins_active_users",
    "Number of active users",
    ["tier"],  # free, premium
)

SUBSCRIPTION_EVENTS = Counter(
    "benchgoblins_subscription_events_total",
    "Subscription events",
    ["event_type"],  # started, renewed, cancelled, expired
)

# =============================================================================
# Engagement Metrics
# =============================================================================

ENGAGEMENT_DAU = Gauge(
    "benchgoblins_engagement_dau",
    "Daily active users",
)

ENGAGEMENT_WAU = Gauge(
    "benchgoblins_engagement_wau",
    "Weekly active users",
)

ENGAGEMENT_MAU = Gauge(
    "benchgoblins_engagement_mau",
    "Monthly active users",
)

ENGAGEMENT_QUERIES_PER_DAY = Gauge(
    "benchgoblins_engagement_queries_per_day",
    "Average queries per day (7-day window)",
)

ENGAGEMENT_LOCAL_ROUTING_PCT = Gauge(
    "benchgoblins_engagement_local_routing_pct",
    "Local routing percentage",
)

# =============================================================================
# Metrics Middleware
# =============================================================================


def normalize_path(path: str) -> str:
    """Normalize path to reduce cardinality in metrics."""
    # Replace UUIDs and numeric IDs with placeholders
    import re

    # Replace UUIDs
    path = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "{id}",
        path,
        flags=re.IGNORECASE,
    )

    # Replace numeric IDs in paths like /players/123
    path = re.sub(r"/\d+(?=/|$)", "/{id}", path)

    # Replace team keys like 449.l.123456.t.1
    path = re.sub(r"\d+\.l\.\d+\.t\.\d+", "{team_key}", path)

    # Replace league keys
    path = re.sub(r"\d+\.l\.\d+", "{league_key}", path)

    return path


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to track request metrics."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip metrics endpoint to avoid recursion
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        endpoint = normalize_path(request.url.path)

        # Track in-progress requests
        REQUESTS_IN_PROGRESS.labels(method=method, endpoint=endpoint).inc()

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            # Record metrics
            duration = time.perf_counter() - start_time

            REQUEST_COUNT.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code,
            ).inc()

            REQUEST_LATENCY.labels(
                method=method,
                endpoint=endpoint,
            ).observe(duration)

            REQUESTS_IN_PROGRESS.labels(method=method, endpoint=endpoint).dec()

        return response


# =============================================================================
# Metrics Endpoint
# =============================================================================


async def metrics_endpoint(request: Request) -> Response:
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# =============================================================================
# Instrumentation Decorators
# =============================================================================


def track_decision(sport: str, query_type: str, risk_mode: str, routed_to: str):
    """Decorator to track decision metrics."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            DECISION_REQUESTS.labels(
                sport=sport,
                query_type=query_type,
                risk_mode=risk_mode,
            ).inc()

            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.perf_counter() - start_time
                DECISION_LATENCY.labels(
                    sport=sport,
                    routed_to=routed_to,
                ).observe(duration)

        return wrapper

    return decorator


@asynccontextmanager
async def track_external_api(service: str):
    """Context manager to track external API calls."""
    start_time = time.perf_counter()
    try:
        yield
        EXTERNAL_API_REQUESTS.labels(service=service, status="success").inc()
    except Exception:
        EXTERNAL_API_REQUESTS.labels(service=service, status="error").inc()
        raise
    finally:
        duration = time.perf_counter() - start_time
        EXTERNAL_API_LATENCY.labels(service=service).observe(duration)


@asynccontextmanager
async def track_database_operation(operation: str, table: str = "unknown"):
    """Context manager to track database operations."""
    start_time = time.perf_counter()
    try:
        yield
        DATABASE_OPERATIONS.labels(
            operation=operation,
            table=table,
            status="success",
        ).inc()
    except Exception:
        DATABASE_OPERATIONS.labels(
            operation=operation,
            table=table,
            status="error",
        ).inc()
        raise
    finally:
        duration = time.perf_counter() - start_time
        DATABASE_LATENCY.labels(operation=operation).observe(duration)


def track_claude_request(
    input_tokens: int, output_tokens: int, success: bool, variant: str = "control"
):
    """Track Claude API request metrics."""
    status = "success" if success else "error"
    CLAUDE_REQUESTS.labels(status=status, prompt_variant=variant).inc()
    CLAUDE_TOKENS.labels(type="input").inc(input_tokens)
    CLAUDE_TOKENS.labels(type="output").inc(output_tokens)


def track_cache_operation(operation: str, hit: bool):
    """Track cache operation metrics."""
    result = "hit" if hit else "miss"
    CACHE_OPERATIONS.labels(operation=operation, result=result).inc()


def update_active_users(free_count: int, premium_count: int):
    """Update active users gauge."""
    ACTIVE_USERS.labels(tier="free").set(free_count)
    ACTIVE_USERS.labels(tier="premium").set(premium_count)


def track_subscription_event(event_type: str):
    """Track subscription events."""
    SUBSCRIPTION_EVENTS.labels(event_type=event_type).inc()


def update_engagement_metrics(metrics) -> None:
    """Update engagement Prometheus gauges from EngagementMetrics."""
    ENGAGEMENT_DAU.set(metrics.retention.dau)
    ENGAGEMENT_WAU.set(metrics.retention.wau)
    ENGAGEMENT_MAU.set(metrics.retention.mau)
    ENGAGEMENT_QUERIES_PER_DAY.set(metrics.queries.avg_queries_per_day)
    ENGAGEMENT_LOCAL_ROUTING_PCT.set(metrics.features.local_routing_pct)
