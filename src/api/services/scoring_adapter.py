"""
Adapter: ESPN PlayerStats → Core Scoring PlayerStats.

Bridges the gap between ESPN's data format and the core scoring engine's
expected input format.
"""

from __future__ import annotations

from core.scoring import PlayerStats as CorePlayerStats

from services.espn import PlayerInfo, TeamDefense
from services.espn import PlayerStats as ESPNPlayerStats


def _position_matchup_field(matchup: TeamDefense, position: str) -> float | None:
    """Look up position-specific fantasy points allowed from TeamDefense."""
    pos = position.upper()
    field_map = {
        "PG": matchup.vs_pg,
        "SG": matchup.vs_sg,
        "SF": matchup.vs_sf,
        "PF": matchup.vs_pf,
        "C": matchup.vs_c,
    }
    return field_map.get(pos)


def adapt_espn_to_core(
    info: PlayerInfo,
    stats: ESPNPlayerStats,
    trends: dict | None = None,
    matchup: TeamDefense | None = None,
) -> CorePlayerStats:
    """Convert ESPN player data to core scoring engine format."""
    gp = stats.games_played or 0
    gs = stats.games_started or 0
    games_started_pct = gs / gp if gp > 0 else 0.0
    is_starter = games_started_pct >= 0.8

    # Trends: use provided dict or default to 0.0
    minutes_trend = 0.0
    usage_trend = 0.0
    points_trend = 0.0
    if trends:
        minutes_trend = trends.get("minutes_trend", 0.0)
        usage_trend = trends.get("usage_trend", 0.0)
        points_trend = trends.get("points_trend", 0.0)

    # Matchup context
    opponent_def_rating = None
    opponent_pace = None
    opponent_vs_position = None
    if matchup:
        # NBA uses defensive_rating; NFL uses points_allowed
        if stats.sport == "nba":
            opponent_def_rating = matchup.defensive_rating
        else:
            opponent_def_rating = matchup.points_allowed
        opponent_pace = matchup.pace
        opponent_vs_position = _position_matchup_field(matchup, info.position)

    return CorePlayerStats(
        player_id=info.id,
        name=info.name,
        team=info.team_abbrev,
        position=info.position,
        sport=stats.sport,
        # Volume
        minutes_per_game=stats.minutes_per_game or 0.0,
        usage_rate=stats.usage_rate or 0.0,
        # Scoring
        points_per_game=stats.points_per_game or 0.0,
        assists_per_game=stats.assists_per_game or 0.0,
        rebounds_per_game=stats.rebounds_per_game or 0.0,
        # Efficiency
        field_goal_pct=stats.field_goal_pct or 0.0,
        three_point_pct=stats.three_point_pct or 0.0,
        free_throw_pct=0.0,
        # Trends
        minutes_trend=minutes_trend,
        usage_trend=usage_trend,
        points_trend=points_trend,
        # Role
        is_starter=is_starter,
        games_started_pct=games_started_pct,
        games_played=gp,
        # NFL-specific
        targets=stats.targets or 0.0,
        receptions=stats.receptions or 0.0,
        receiving_yards=stats.receiving_yards or 0.0,
        rush_yards=stats.rush_yards or 0.0,
        snap_pct=stats.snap_pct or 0.0,
        # MLB-specific
        batting_avg=stats.batting_avg or 0.0,
        home_runs=stats.home_runs or 0.0,
        rbis=stats.rbis or 0.0,
        stolen_bases=stats.stolen_bases or 0.0,
        ops=stats.ops or 0.0,
        era=stats.era or 0.0,
        wins=stats.wins or 0,
        strikeouts=stats.strikeouts or 0.0,
        # NHL-specific
        goals=stats.goals or 0.0,
        assists_nhl=stats.assists_nhl or 0.0,
        plus_minus=stats.plus_minus or 0.0,
        shots=stats.shots or 0.0,
        save_pct=stats.save_pct or 0.0,
        # Matchup
        opponent_def_rating=opponent_def_rating,
        opponent_pace=opponent_pace,
        opponent_vs_position=opponent_vs_position,
    )
