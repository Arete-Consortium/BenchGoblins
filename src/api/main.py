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
    yield


# ---------------------------------------------------------------------------
# App Setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="GameSpace API",
    description="Fantasy sports decision engine using role stability, spatial opportunity, and matchup context.",
    version="0.1.0",
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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "claude_available": claude_service.is_available,
    }


@app.post("/players/search", response_model=list[Player])
async def search_players(request: PlayerSearchRequest):
    """
    Search for players by name.

    TODO: Implement actual database search
    """
    # Placeholder - replace with real implementation
    return []


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

    # Classify query complexity
    complexity = classify_query(
        query=request.query,
        decision_type=request.decision_type.value,
        player_a=player_a,
        player_b=player_b,
    )

    # Route based on complexity
    if complexity == QueryComplexity.SIMPLE:
        # Use local scoring engine
        return await _local_decision(request, player_a, player_b)
    else:
        # Use Claude for complex queries
        return await _claude_decision(request, player_a, player_b)


async def _local_decision(
    request: DecisionRequest,
    player_a: Optional[str],
    player_b: Optional[str],
) -> DecisionResponse:
    """
    Handle simple A vs B decisions locally.

    TODO: Integrate with actual player stats from database.
    Currently returns a basic heuristic response.
    """
    # Without real player data, we can still provide a basic response
    # that acknowledges the question and suggests using the full AI
    if player_a and player_b:
        # Simple heuristic: alphabetically first player (placeholder)
        decision = f"Start {player_a}"
        rationale = (
            f"Based on general role stability analysis for {request.risk_mode.value} mode. "
            f"For deeper analysis, ask 'why {player_a} over {player_b}?'"
        )
        return DecisionResponse(
            decision=decision,
            confidence=Confidence.LOW,
            rationale=rationale,
            details={
                "note": "Local scoring without live stats - confidence is low",
                "player_a": player_a,
                "player_b": player_b,
                "risk_mode": request.risk_mode.value,
            },
            source="local",
        )

    # Fall back to Claude if we can't parse the players
    return await _claude_decision(request, player_a, player_b)


async def _claude_decision(
    request: DecisionRequest,
    player_a: Optional[str],
    player_b: Optional[str],
) -> DecisionResponse:
    """Handle complex decisions using Claude API."""
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
