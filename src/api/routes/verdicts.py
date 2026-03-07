"""
Verdict API Routes.

Dedicated start/sit verdict endpoint with multi-mode scoring
and optional Claude reasoning.
"""

import logging

from core.verdicts import Verdict, generate_verdict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routes.auth import require_pro_or_free_verdict
from services.claude import claude_service
from services.espn import espn_service
from services.scoring_adapter import adapt_espn_to_core
from services.sleeper import sleeper_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/verdicts", tags=["Verdicts"])


# -------------------------------------------------------------------------
# Request/Response Models
# -------------------------------------------------------------------------


class StartSitRequest(BaseModel):
    """Request body for start/sit verdict."""

    player_a: str = Field(..., description="First player name")
    player_b: str = Field(..., description="Second player name")
    sport: str = Field(default="nfl", description="Sport: nfl, nba, mlb, nhl, soccer")
    league_id: str | None = Field(default=None, description="Sleeper league ID for scoring context")
    week: int | None = Field(default=None, description="Week number for temporal context")


class RiskBreakdownResponse(BaseModel):
    """Score breakdown for a single risk mode."""

    player_a: float
    player_b: float
    winner: str
    margin: float


class PlayerIndicesResponse(BaseModel):
    """Player identity + index scores."""

    name: str
    team: str
    sci: float
    rmi: float
    gis: float
    od: float
    msf: float


class VerdictResponse(BaseModel):
    """Full start/sit verdict response."""

    verdict: str
    confidence: int
    reasoning: str | None = None
    breakdown: dict[str, RiskBreakdownResponse]
    indices: dict[str, PlayerIndicesResponse]
    league_context: dict | None = None
    source: str


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------


async def _resolve_player(name: str, sport: str):
    """Resolve a player name to ESPN data + core stats.

    Returns (info, core_stats) or raises HTTPException.
    """
    data = await espn_service.find_player_by_name(name, sport)
    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"Player '{name}' not found in ESPN {sport.upper()} data",
        )

    info, stats = data
    if not stats:
        raise HTTPException(
            status_code=404,
            detail=f"No stats available for '{name}'",
        )

    # Fetch trends, matchup, and game line data
    game_logs = await espn_service.get_player_game_logs(info.id, sport)
    trends = espn_service.calculate_trends(game_logs, sport)

    game = await espn_service.get_next_game(info.team_abbrev, sport)
    opp = game.away_abbrev if game and game.home_abbrev == info.team_abbrev else (game.home_abbrev if game else None)
    matchup = await espn_service.get_team_defense(opp, sport) if opp else None

    core_stats = adapt_espn_to_core(info, stats, trends=trends, matchup=matchup, game=game)
    return info, core_stats


def _build_reasoning_prompt(verdict: Verdict, league_settings: dict | None) -> str:
    """Build a focused prompt for Claude to generate verdict reasoning."""
    winner = verdict.decision.replace("Start ", "")
    loser = verdict.player_b_name if winner == verdict.player_a_name else verdict.player_a_name

    # Find top 2 differentiating indices
    idx_a = verdict.indices_a
    idx_b = verdict.indices_b
    diffs = [
        ("SCI", abs(idx_a.sci - idx_b.sci)),
        ("RMI", abs(idx_a.rmi - idx_b.rmi)),
        ("GIS", abs(idx_a.gis - idx_b.gis)),
        ("OD", abs(idx_a.od - idx_b.od)),
        ("MSF", abs(idx_a.msf - idx_b.msf)),
    ]
    diffs.sort(key=lambda x: x[1], reverse=True)
    top_indices = f"{diffs[0][0]} and {diffs[1][0]}"

    league_str = "standard scoring"
    if league_settings:
        parts = [f"{k}: {v}" for k, v in list(league_settings.items())[:5]]
        league_str = ", ".join(parts)

    return (
        f"You are the BenchGoblins analyst. Write 2-3 sentences explaining "
        f"why {winner} is the start over {loser}. Be decisive — no hedging.\n\n"
        f"Scores — Floor: {verdict.floor.score_a}/{verdict.floor.score_b}, "
        f"Median: {verdict.median.score_a}/{verdict.median.score_b}, "
        f"Ceiling: {verdict.ceiling.score_a}/{verdict.ceiling.score_b}.\n"
        f"Key differentiators: {top_indices}.\n"
        f"League scoring: {league_str}."
    )


def _verdict_to_response(
    verdict: Verdict,
    info_a,
    info_b,
    reasoning: str | None,
    league_settings: dict | None,
    source: str,
) -> VerdictResponse:
    """Convert a Verdict + metadata into the API response."""
    return VerdictResponse(
        verdict=verdict.decision,
        confidence=verdict.confidence,
        reasoning=reasoning,
        breakdown={
            "floor": RiskBreakdownResponse(
                player_a=verdict.floor.score_a,
                player_b=verdict.floor.score_b,
                winner=verdict.floor.winner,
                margin=verdict.floor.margin,
            ),
            "median": RiskBreakdownResponse(
                player_a=verdict.median.score_a,
                player_b=verdict.median.score_b,
                winner=verdict.median.winner,
                margin=verdict.median.margin,
            ),
            "ceiling": RiskBreakdownResponse(
                player_a=verdict.ceiling.score_a,
                player_b=verdict.ceiling.score_b,
                winner=verdict.ceiling.winner,
                margin=verdict.ceiling.margin,
            ),
        },
        indices={
            "player_a": PlayerIndicesResponse(
                name=info_a.name,
                team=info_a.team_abbrev,
                sci=round(verdict.indices_a.sci, 1),
                rmi=round(verdict.indices_a.rmi, 1),
                gis=round(verdict.indices_a.gis, 1),
                od=round(verdict.indices_a.od, 1),
                msf=round(verdict.indices_a.msf, 1),
            ),
            "player_b": PlayerIndicesResponse(
                name=info_b.name,
                team=info_b.team_abbrev,
                sci=round(verdict.indices_b.sci, 1),
                rmi=round(verdict.indices_b.rmi, 1),
                gis=round(verdict.indices_b.gis, 1),
                od=round(verdict.indices_b.od, 1),
                msf=round(verdict.indices_b.msf, 1),
            ),
        },
        league_context=league_settings,
        source=source,
    )


# -------------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------------


@router.post("/start-sit", response_model=VerdictResponse)
async def start_sit_verdict(
    request: StartSitRequest,
    current_user: dict = Depends(require_pro_or_free_verdict),
):
    """
    Generate a start/sit verdict with multi-mode scoring.

    Scores both players across Floor, Median, and Ceiling risk modes.
    Optionally enriches with Claude reasoning and Sleeper league context.
    """
    sport = request.sport

    # Resolve both players via ESPN
    info_a, core_a = await _resolve_player(request.player_a, sport)
    info_b, core_b = await _resolve_player(request.player_b, sport)

    # Generate the multi-mode verdict
    verdict = generate_verdict(core_a, core_b)

    # Fetch league context if provided
    league_settings = None
    if request.league_id:
        league = await sleeper_service.get_league(request.league_id)
        if league:
            league_settings = league.scoring_settings

    # Generate Claude reasoning (optional, non-blocking on failure)
    reasoning = None
    source = "local"
    if claude_service.is_available:
        try:
            prompt = _build_reasoning_prompt(verdict, league_settings)
            result = await claude_service.make_decision(
                query=prompt,
                sport=sport,
                risk_mode="median",
                decision_type="start_sit",
                player_a=request.player_a,
                player_b=request.player_b,
                player_context=None,
                use_cache=True,
                prompt_variant="concise_v1",
            )
            reasoning = result.get("rationale") or result.get("decision")
            source = "local+claude"
        except Exception:
            logger.warning("Claude reasoning failed, returning local-only verdict")

    return _verdict_to_response(verdict, info_a, info_b, reasoning, league_settings, source)
