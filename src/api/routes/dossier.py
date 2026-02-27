"""
Player Dossier API Routes.

Comprehensive player profiles aggregating ESPN data, five-index scores,
game logs, and decision history for commissioners and managers.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from models.database import Decision as DecisionModel
from models.database import GameLog, PlayerIndex
from models.database import Player as PlayerModel
from services.database import db_service
from services.espn import espn_service
from services.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dossier", tags=["Dossier"])


# -------------------------------------------------------------------------
# Response Models
# -------------------------------------------------------------------------


class DossierIndices(BaseModel):
    """Five-index scores for a player."""

    sci: float
    rmi: float
    gis: float
    od: float
    msf: float
    floor_score: float
    median_score: float
    ceiling_score: float
    calculated_at: str
    opponent: str | None = None
    game_date: str | None = None


class DossierGameLog(BaseModel):
    """Single game entry for the dossier."""

    game_date: str
    opponent: str | None = None
    home_away: str | None = None
    result: str | None = None
    fantasy_points: float | None = None
    stats: dict[str, Any]


class DossierDecision(BaseModel):
    """Past decision involving this player."""

    id: str
    decision_type: str
    query: str
    decision: str
    confidence: str
    risk_mode: str
    source: str
    created_at: str
    outcome: str | None = None


class DossierPlayerDetail(BaseModel):
    """Player bio and stats for the dossier header."""

    id: str
    name: str
    team: str | None = None
    team_abbrev: str | None = None
    position: str | None = None
    sport: str
    headshot_url: str | None = None
    stats: dict[str, Any] | None = None


class DossierSummary(BaseModel):
    """Aggregate stats for the dossier overview."""

    games_played: int
    total_indices: int
    total_game_logs: int
    total_decisions: int
    latest_median: float | None = None


class DossierResponse(BaseModel):
    """Full player dossier for the commissioner/manager dashboard."""

    player: DossierPlayerDetail
    indices: list[DossierIndices]
    game_logs: list[DossierGameLog]
    decisions: list[DossierDecision]
    summary: DossierSummary


# -------------------------------------------------------------------------
# Sport-specific stat extraction
# -------------------------------------------------------------------------

_NBA_STATS = [
    "minutes",
    "points",
    "rebounds",
    "assists",
    "steals",
    "blocks",
    "turnovers",
    "fg_made",
    "fg_attempted",
    "three_made",
    "three_attempted",
    "ft_made",
    "ft_attempted",
]

_NFL_STATS = [
    "pass_yards_game",
    "pass_tds_game",
    "pass_ints_game",
    "rush_yards_game",
    "rush_tds_game",
    "receptions_game",
    "receiving_yards_game",
    "receiving_tds_game",
    "targets_game",
    "snaps",
    "snap_pct_game",
]

_MLB_STATS = [
    "at_bats",
    "hits",
    "home_runs_game",
    "rbis_game",
    "stolen_bases_game",
    "walks",
    "strikeouts_game",
    "innings_pitched",
    "earned_runs",
]

_NHL_STATS = [
    "goals_game",
    "assists_game",
    "plus_minus_game",
    "shots_game",
    "time_on_ice",
    "saves",
    "goals_against",
]

_SOCCER_STATS = [
    "soccer_goals_game",
    "soccer_assists_game",
    "soccer_minutes_game",
    "soccer_shots_game",
    "soccer_shots_on_target_game",
    "soccer_key_passes_game",
    "soccer_tackles_game",
    "soccer_interceptions_game",
    "soccer_clean_sheet",
    "soccer_saves_game",
    "soccer_goals_conceded_game",
    "soccer_xg_game",
    "soccer_xa_game",
]

_SPORT_STAT_FIELDS: dict[str, list[str]] = {
    "nba": _NBA_STATS,
    "nfl": _NFL_STATS,
    "mlb": _MLB_STATS,
    "nhl": _NHL_STATS,
    "soccer": _SOCCER_STATS,
}


def _extract_game_log_stats(gl: GameLog, sport: str) -> dict[str, Any]:
    """Extract sport-specific stats from a GameLog row."""
    fields = _SPORT_STAT_FIELDS.get(sport, _NBA_STATS)
    stats: dict[str, Any] = {}
    for field in fields:
        val = getattr(gl, field, None)
        if val is not None:
            if isinstance(val, bool):
                stats[field] = val
            elif hasattr(val, "__float__"):
                stats[field] = float(val)
            else:
                stats[field] = val
    return stats


# -------------------------------------------------------------------------
# DB query helpers
# -------------------------------------------------------------------------


async def _fetch_indices(session: Any, db_player_id: Any, limit: int = 5) -> list[DossierIndices]:
    """Fetch most recent five-index calculations for a player."""
    result = await session.execute(
        select(PlayerIndex)
        .where(PlayerIndex.player_id == db_player_id)
        .order_by(PlayerIndex.calculated_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        DossierIndices(
            sci=float(r.sci),
            rmi=float(r.rmi),
            gis=float(r.gis),
            od=float(r.od),
            msf=float(r.msf),
            floor_score=float(r.floor_score),
            median_score=float(r.median_score),
            ceiling_score=float(r.ceiling_score),
            calculated_at=str(r.calculated_at),
            opponent=r.opponent,
            game_date=str(r.game_date) if r.game_date else None,
        )
        for r in rows
    ]


async def _fetch_game_logs(
    session: Any, db_player_id: Any, sport: str, limit: int = 10
) -> list[DossierGameLog]:
    """Fetch recent game logs with sport-specific stats."""
    result = await session.execute(
        select(GameLog)
        .where(GameLog.player_id == db_player_id)
        .order_by(GameLog.game_date.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        DossierGameLog(
            game_date=str(gl.game_date),
            opponent=gl.opponent,
            home_away=gl.home_away,
            result=gl.result,
            fantasy_points=float(gl.fantasy_points) if gl.fantasy_points is not None else None,
            stats=_extract_game_log_stats(gl, sport),
        )
        for gl in rows
    ]


async def _fetch_decisions(
    session: Any, db_player_id: Any, player_name: str, sport: str, limit: int = 10
) -> list[DossierDecision]:
    """Fetch decisions involving this player (by FK or name fallback)."""
    result = await session.execute(
        select(DecisionModel)
        .where(
            DecisionModel.sport == sport,
            (DecisionModel.player_a_id == db_player_id)
            | (DecisionModel.player_b_id == db_player_id)
            | (DecisionModel.player_a_name == player_name)
            | (DecisionModel.player_b_name == player_name),
        )
        .order_by(DecisionModel.created_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        DossierDecision(
            id=str(d.id),
            decision_type=d.decision_type,
            query=d.query,
            decision=d.decision,
            confidence=d.confidence,
            risk_mode=d.risk_mode,
            source=d.source,
            created_at=str(d.created_at),
            outcome=d.actual_outcome,
        )
        for d in rows
    ]


# -------------------------------------------------------------------------
# Endpoint
# -------------------------------------------------------------------------


@router.get("/{sport}/{player_id}", response_model=DossierResponse)
async def get_player_dossier(sport: str, player_id: str, req: Request):
    """
    Get a comprehensive player dossier.

    Aggregates player bio, stats, five-index scores, recent game logs,
    and past decisions involving this player.
    """
    # Rate limiting
    client_ip = req.client.host if req.client else "anonymous"
    allowed, retry_after = await rate_limiter.check_rate_limit(f"dossier:{client_ip}")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )

    # Fetch player info from ESPN
    player = await espn_service.get_player(player_id, sport)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    stats = await espn_service.get_player_stats(player_id, sport)
    stats_dict: dict[str, Any] | None = None
    if stats:
        stats_dict = {
            k: v
            for k, v in stats.__dict__.items()
            if v is not None and k not in ("player_id", "sport")
        }

    player_detail = DossierPlayerDetail(
        id=player.id,
        name=player.name,
        team=player.team,
        team_abbrev=getattr(player, "team_abbrev", None),
        position=player.position,
        sport=sport,
        headshot_url=player.headshot_url,
        stats=stats_dict,
    )

    # Query DB for indices, game logs, decisions
    indices_list: list[DossierIndices] = []
    game_logs_list: list[DossierGameLog] = []
    decisions_list: list[DossierDecision] = []

    if db_service.is_configured:
        try:
            async with db_service.session() as session:
                db_player_result = await session.execute(
                    select(PlayerModel).where(PlayerModel.espn_id == player_id)
                )
                db_player = db_player_result.scalar_one_or_none()

                if db_player:
                    indices_list = await _fetch_indices(session, db_player.id)
                    game_logs_list = await _fetch_game_logs(session, db_player.id, sport)
                    decisions_list = await _fetch_decisions(
                        session, db_player.id, db_player.name, sport
                    )
        except SQLAlchemyError:
            logger.exception("Dossier DB query error")

    # Build summary
    latest_median: float | None = None
    if indices_list:
        latest_median = indices_list[0].median_score

    summary = DossierSummary(
        games_played=len(game_logs_list),
        total_indices=len(indices_list),
        total_game_logs=len(game_logs_list),
        total_decisions=len(decisions_list),
        latest_median=latest_median,
    )

    return DossierResponse(
        player=player_detail,
        indices=indices_list,
        game_logs=game_logs_list,
        decisions=decisions_list,
        summary=summary,
    )
