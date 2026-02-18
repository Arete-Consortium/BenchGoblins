"""
Decision routes — /decide, /decide/stream, /draft endpoints and helpers.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

from core.scoring import RiskMode as CoreRiskMode
from core.scoring import compare_players
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from models.database import BudgetConfig, User
from models.database import Decision as DecisionModel
from models.schemas import (
    Confidence,
    DecisionRequest,
    DecisionResponse,
    DecisionType,
    DraftRequest,
    DraftResponse,
    Sport,
)
from routes.auth import get_current_user, get_optional_user
from services.budget_alerts import check_and_send_alerts
from services.claude import claude_service
from services.database import db_service
from services.draft_assistant import draft_assistant, extract_draft_players
from services.espn import espn_service, format_player_context
from services.query_classifier import QueryCategory
from services.query_classifier import classify_query as classify_sports_query
from services.rate_limiter import rate_limiter
from services.redis import redis_service
from services.router import (
    QueryComplexity,
    classify_draft_query,
    classify_query,
    classify_trade_query,
    extract_players_from_query,
)
from services.scoring_adapter import adapt_espn_to_core
from services.trade_analyzer import extract_trade_players, trade_analyzer
from services.variants import assign_variant

logger = logging.getLogger("benchgoblins")

router = APIRouter()


# ---------------------------------------------------------------------------
# Tier-Based Query Limiting
# ---------------------------------------------------------------------------

FREE_TIER_WEEKLY_LIMIT = 5
PRO_TIER_WEEKLY_LIMIT = -1  # Unlimited


async def _check_and_increment_query_count(user_id: int) -> tuple[bool, int, int]:
    """Check if user can make a query and increment counter.

    Uses SELECT ... FOR UPDATE to prevent race conditions where
    concurrent requests could bypass the query limit.

    Returns:
        Tuple of (allowed, queries_this_period, weekly_limit)
    """
    if not db_service.is_configured:
        return True, 0, FREE_TIER_WEEKLY_LIMIT

    async with db_service.session() as session:
        # Lock the row to prevent concurrent bypass
        result = await session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        user = result.scalar_one_or_none()

        if not user:
            return True, 0, FREE_TIER_WEEKLY_LIMIT

        # Determine weekly limit based on tier
        weekly_limit = (
            PRO_TIER_WEEKLY_LIMIT if user.subscription_tier == "pro" else FREE_TIER_WEEKLY_LIMIT
        )

        # Check if counter needs reset (new week — 7 days since last reset)
        now = datetime.now(UTC)
        if user.queries_reset_at is None or (now - user.queries_reset_at) >= timedelta(days=7):
            # Reset counter for new week
            user.queries_today = 0
            user.queries_reset_at = now

        # Pro tier has unlimited queries
        if user.subscription_tier == "pro":
            user.queries_today += 1
            return True, user.queries_today, weekly_limit

        # Free tier - check limit
        if user.queries_today >= weekly_limit:
            return False, user.queries_today, weekly_limit

        # Increment counter
        user.queries_today += 1
        return True, user.queries_today, weekly_limit


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
            from sqlalchemy import func

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
        logger.error("Budget check failed: %s", e, exc_info=True)
        return False, None  # Fail open - don't block on errors


def _is_sports_query(query: str) -> tuple[bool, str]:
    """Check if query is sports-related using the smart classifier.

    Returns (is_allowed, reason) tuple.
    """
    result = classify_sports_query(query)

    if result.category == QueryCategory.OFF_TOPIC:
        return False, result.reason

    if result.category == QueryCategory.AMBIGUOUS:
        logger.info("Ambiguous query allowed: '%s...' — %s", query[:50], result.reason)

    return True, result.reason


# ---------------------------------------------------------------------------
# Storage Helpers
# ---------------------------------------------------------------------------


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
        # Safely extract scores from details dict
        details = response.details if isinstance(response.details, dict) else {}
        player_a_detail = details.get("player_a")
        player_b_detail = details.get("player_b")
        score_a = player_a_detail.get("score") if isinstance(player_a_detail, dict) else None
        score_b = player_b_detail.get("score") if isinstance(player_b_detail, dict) else None
        margin = details.get("margin")

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
                score_a=score_a,
                score_b=score_b,
                margin=margin,
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
        logger.error("Failed to store decision: %s", e, exc_info=True)


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
        logger.error("Failed to store draft decision: %s", e, exc_info=True)


# ---------------------------------------------------------------------------
# Local Scoring Helpers
# ---------------------------------------------------------------------------


async def _local_decision(
    request: DecisionRequest,
    player_a_name: str | None,
    player_b_name: str | None,
    player_a_data: tuple | None,
    player_b_data: tuple | None,
) -> DecisionResponse:
    """Handle simple A vs B decisions locally using the core scoring engine."""
    if not player_a_data or not player_b_data:
        resp, _, _ = await _claude_decision(request, player_a_name, player_b_name, None)
        return resp

    info_a, stats_a = player_a_data
    info_b, stats_b = player_b_data

    if not stats_a or not stats_b:
        resp, _, _ = await _claude_decision(request, player_a_name, player_b_name, None)
        return resp

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
    """Handle trade decisions locally using the core scoring engine."""
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
            player_context=player_context,
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Claude decision failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred processing your request. Please try again.",
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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/decide", response_model=DecisionResponse)
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
    # Check rate limit — use IP-derived key for anonymous to avoid shared-bucket DoS
    effective_session = session_id or f"anon:{id(request)}"
    allowed, retry_after = await rate_limiter.check_rate_limit(effective_session)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    # Check tier-based weekly limit if authenticated
    user_id = current_user["user_id"] if current_user else None
    if user_id is not None:
        tier_allowed, queries_today, weekly_limit = await _check_and_increment_query_count(user_id)
        if not tier_allowed:
            raise HTTPException(
                status_code=402,
                detail=f"Weekly query limit reached ({queries_today}/{weekly_limit}). Upgrade to Pro for unlimited queries.",
            )

    # Check if query is sports-related using smart classifier
    is_allowed, rejection_reason = _is_sports_query(request.query)
    if not is_allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Query must be about fantasy sports. {rejection_reason}",
        )

    # Assign A/B prompt variant
    variant = assign_variant(session_id)

    # --- Trade intercept: try local scoring for trade queries ---
    if request.decision_type == DecisionType.TRADE:
        trade_parsed = extract_trade_players(request.query)
        if trade_parsed:
            giving_names, receiving_names = trade_parsed
            sport = request.sport.value

            # Fetch ESPN data for all trade players
            giving_data = [
                await espn_service.find_player_by_name(name, sport) for name in giving_names
            ]
            receiving_data = [
                await espn_service.find_player_by_name(name, sport) for name in receiving_names
            ]

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
                source=(cached.get("source") or "claude") + "_cached",
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


@router.post("/draft", response_model=DraftResponse)
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
    effective_session = session_id or f"anon:{id(request)}"
    allowed, retry_after = await rate_limiter.check_rate_limit(effective_session)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    # Check tier-based weekly limit if authenticated
    user_id = current_user["user_id"] if current_user else None
    if user_id is not None:
        tier_allowed, queries_today, weekly_limit = await _check_and_increment_query_count(user_id)
        if not tier_allowed:
            raise HTTPException(
                status_code=402,
                detail=f"Weekly query limit reached ({queries_today}/{weekly_limit}). Upgrade to Pro for unlimited queries.",
            )

    # Check if query is sports-related
    is_allowed, rejection_reason = _is_sports_query(request.query)
    if not is_allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Query must be about fantasy sports. {rejection_reason}",
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


@router.post("/decide/stream")
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
    # Check rate limit
    effective_session = session_id or f"anon:{id(request)}"
    allowed, retry_after = await rate_limiter.check_rate_limit(effective_session)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    # Check tier-based weekly limit if authenticated
    user_id = current_user["user_id"] if current_user else None
    if user_id is not None:
        tier_allowed, queries_today, weekly_limit = await _check_and_increment_query_count(user_id)
        if not tier_allowed:
            raise HTTPException(
                status_code=402,
                detail=f"Weekly query limit reached ({queries_today}/{weekly_limit}). Upgrade to Pro for unlimited queries.",
            )

    # Check if query is sports-related using smart classifier
    is_allowed, rejection_reason = _is_sports_query(request.query)
    if not is_allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Query must be about fantasy sports. {rejection_reason}",
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
                    logger.error("Failed to persist streaming decision: %s", e, exc_info=True)

            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error("Stream error: %s", e, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': 'An error occurred processing your request.'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
