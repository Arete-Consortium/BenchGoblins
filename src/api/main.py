"""
GameSpace API — Fantasy Sports Decision Engine
"""

from contextlib import asynccontextmanager
from enum import Enum
from typing import Optional
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup app resources"""
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_key:
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
    query: str = Field(..., description="Natural language query, e.g., 'Should I start Jalen Brunson or Tyrese Maxey?'")
    player_a: Optional[str] = Field(None, description="First player name (optional if in query)")
    player_b: Optional[str] = Field(None, description="Second player name (optional if in query)")
    league_type: Optional[str] = Field(None, description="e.g., 'points', 'categories', 'half-ppr'")


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
    return {"status": "healthy", "version": "0.1.0"}


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
    # TODO: Implement decision router
    # 1. Classify query complexity
    # 2. If simple: use local scoring engine
    # 3. If complex: call Claude API with enriched context
    
    # Placeholder response
    return DecisionResponse(
        decision="Start Player A",
        confidence=Confidence.MEDIUM,
        rationale="Placeholder - not yet implemented",
        source="local"
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
