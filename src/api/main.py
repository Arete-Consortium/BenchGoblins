"""
GameSpace API — Fantasy Sports Decision Engine
"""

import os
import sys
from contextlib import asynccontextmanager
from enum import Enum
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from services.claude import claude_service
from services.espn import espn_service, format_player_context
from services.router import QueryComplexity, classify_query, extract_players_from_query


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup app resources"""
    if claude_service.is_available:
        print("Claude API configured and ready")
    else:
        print("WARNING: ANTHROPIC_API_KEY not set - Claude integration disabled")
    print("ESPN data service ready")
    yield
    # Cleanup
    await espn_service.close()


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
    player_a: Optional[str] = Field(
        None, description="First player name (optional if in query)"
    )
    player_b: Optional[str] = Field(
        None, description="Second player name (optional if in query)"
    )
    league_type: Optional[str] = Field(
        None, description="e.g., 'points', 'categories', 'half-ppr'"
    )


class DecisionResponse(BaseModel):
    """Response from /decide endpoint"""

    decision: str
    confidence: Confidence
    rationale: str
    details: Optional[dict] = None
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
    headshot_url: Optional[str] = None


class PlayerDetail(BaseModel):
    """Detailed player information with stats"""

    id: str
    name: str
    team: str
    team_abbrev: str
    position: str
    sport: Sport
    headshot_url: Optional[str] = None
    stats: Optional[dict] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "0.2.0",
        "claude_available": claude_service.is_available,
        "espn_available": True,
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
        player_a_data = await espn_service.find_player_by_name(
            player_a, request.sport.value
        )
    if player_b:
        player_b_data = await espn_service.find_player_by_name(
            player_b, request.sport.value
        )

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

    # Route based on complexity
    if complexity == QueryComplexity.SIMPLE and player_a_data and player_b_data:
        # Use local scoring engine with real data
        return await _local_decision(
            request, player_a, player_b, player_a_data, player_b_data
        )
    else:
        # Use Claude for complex queries or when we need more reasoning
        return await _claude_decision(request, player_a, player_b, player_context)


async def _local_decision(
    request: DecisionRequest,
    player_a_name: Optional[str],
    player_b_name: Optional[str],
    player_a_data: Optional[tuple],
    player_b_data: Optional[tuple],
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
            score += ((stats.pass_tds or 0) + (stats.rush_tds or 0) + (stats.receiving_tds or 0)) * 2

    elif sport == "mlb":
        if stats.batting_avg:
            # Hitter
            score = (stats.home_runs or 0) * 4 + (stats.rbis or 0) * 1 + (stats.stolen_bases or 0) * 2
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
    player_a: Optional[str],
    player_b: Optional[str],
    player_context: Optional[str],
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
        confidence = confidence_map.get(
            result.get("confidence", "medium"), Confidence.MEDIUM
        )

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


@app.get("/history")
async def get_decision_history(limit: int = 20):
    """
    Get recent decision history for the user.

    TODO: Implement with user authentication
    """
    return []


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
