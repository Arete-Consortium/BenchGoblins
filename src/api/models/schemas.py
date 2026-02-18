"""
Shared Pydantic models and enums used across API routes.
"""

from enum import Enum

from pydantic import BaseModel, Field, constr, field_validator


# ---------------------------------------------------------------------------
# Enums
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


# ---------------------------------------------------------------------------
# Shared Models
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    """Standardized error response envelope."""

    error: str
    code: str
    detail: str | None = None
    retry_after: int | None = None
    upgrade_url: str | None = None


# ---------------------------------------------------------------------------
# Decision Models
# ---------------------------------------------------------------------------


class DecisionRequest(BaseModel):
    """Request body for /decide endpoint"""

    sport: Sport
    risk_mode: RiskMode = RiskMode.MEDIAN
    decision_type: DecisionType = DecisionType.START_SIT
    query: str = Field(
        ...,
        min_length=1,
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

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Query must not be blank")
        return stripped


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
        min_length=1,
        max_length=1000,
        description="Natural language query, e.g., 'draft Jalen Brunson or Tyrese Maxey?'",
    )

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Query must not be blank")
        return stripped
    players: list[constr(max_length=100)] | None = Field(
        None, max_length=20, description="Explicit list of player names to rank"
    )
    position_needs: list[constr(max_length=10)] | None = Field(
        None, max_length=10, description="Positions to boost, e.g., ['PG', 'C']"
    )
    league_type: str | None = Field(
        None, max_length=50, description="e.g., 'points', 'categories', 'half-ppr'"
    )


class DraftResponse(BaseModel):
    """Response from /draft endpoint"""

    recommended_pick: str
    confidence: Confidence
    rationale: str
    details: dict | None = None
    source: str = Field(..., description="'local' or 'claude'")


# ---------------------------------------------------------------------------
# Player Models
# ---------------------------------------------------------------------------


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
# History Models
# ---------------------------------------------------------------------------


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


class PaginatedHistory(BaseModel):
    """Paginated decision history response."""

    items: list[DecisionHistoryItem]
    total: int
    skip: int
    limit: int
