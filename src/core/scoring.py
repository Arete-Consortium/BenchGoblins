"""
GameSpace Core Scoring Engine

Local scoring logic for fast A vs B comparisons without Claude API calls.
Implements the five qualitative indices (SCI, RMI, GIS, OD, MSF).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RiskMode(str, Enum):
    FLOOR = "floor"
    MEDIAN = "median"
    CEILING = "ceiling"


@dataclass
class PlayerStats:
    """Core stats used for index calculations."""

    # Identity
    player_id: str
    name: str
    team: str
    position: str
    sport: str = "nba"

    # Volume metrics
    minutes_per_game: float = 0.0
    usage_rate: float = 0.0

    # Scoring
    points_per_game: float = 0.0
    assists_per_game: float = 0.0
    rebounds_per_game: float = 0.0

    # Efficiency
    field_goal_pct: float = 0.0
    three_point_pct: float = 0.0
    free_throw_pct: float = 0.0

    # Recent trends (last 5 games vs season)
    minutes_trend: float = 0.0  # Positive = increasing, negative = decreasing
    usage_trend: float = 0.0
    points_trend: float = 0.0

    # Role indicators
    is_starter: bool = True
    games_started_pct: float = 1.0  # Games started / games played
    games_played: int = 0

    # NFL-specific
    targets: float = 0.0
    receptions: float = 0.0
    receiving_yards: float = 0.0
    rush_yards: float = 0.0
    snap_pct: float = 0.0

    # MLB-specific
    batting_avg: float = 0.0
    home_runs: float = 0.0
    rbis: float = 0.0
    stolen_bases: float = 0.0
    ops: float = 0.0
    era: float = 0.0  # Pitchers
    wins: int = 0
    strikeouts: float = 0.0

    # NHL-specific
    goals: float = 0.0
    assists_nhl: float = 0.0
    plus_minus: float = 0.0
    shots: float = 0.0
    save_pct: float = 0.0  # Goalies

    # Matchup context (populated per-game)
    opponent_def_rating: Optional[float] = None
    opponent_pace: Optional[float] = None
    opponent_vs_position: Optional[float] = None  # FP allowed to position


@dataclass
class IndexScores:
    """The five qualitative indices for a player."""

    sci: float  # Space Creation Index (0-100)
    rmi: float  # Role Motion Index (0-100, higher = more dependent on scheme)
    gis: float  # Gravity Impact Score (0-100)
    od: float  # Opportunity Delta (-50 to +50)
    msf: float  # Matchup Space Fit (0-100)


@dataclass
class ScoringWeights:
    """Risk mode determines weighting of each index."""

    sci: float
    rmi: float
    gis: float
    od: float
    msf: float

    @classmethod
    def for_mode(cls, mode: RiskMode) -> "ScoringWeights":
        """Get weights for a given risk mode."""
        if mode == RiskMode.FLOOR:
            # Prioritize stability, penalize volatility
            return cls(sci=0.15, rmi=-0.25, gis=0.10, od=0.20, msf=0.30)
        elif mode == RiskMode.CEILING:
            # Prioritize upside, accept volatility
            return cls(sci=0.30, rmi=0.10, gis=0.25, od=0.20, msf=0.15)
        else:  # MEDIAN
            # Balanced
            return cls(sci=0.20, rmi=0.00, gis=0.20, od=0.30, msf=0.30)


# =============================================================================
# INDEX CALCULATIONS - NBA
# =============================================================================


def calculate_sci_nba(stats: PlayerStats) -> float:
    """
    Space Creation Index (NBA) — How a player generates usable space.

    Higher = creates own opportunities independent of volume.

    Components:
    - Points per game (scoring ability)
    - Usage rate (ball dominance)
    - Assists (playmaking)
    - Shooting efficiency (threat level)
    """
    # Base scoring contribution (0-40 points)
    ppg_score = min(40, stats.points_per_game * 1.5)

    # Usage contribution (0-25 points)
    # Higher usage = more space creation responsibility
    usage_score = min(25, stats.usage_rate * 1.0) if stats.usage_rate else 0

    # Playmaking contribution (0-20 points)
    assist_score = min(20, stats.assists_per_game * 2.0)

    # Efficiency modifier (-10 to +15 points)
    # Good shooters create more space via threat
    fg_modifier = 0.0
    if stats.field_goal_pct:
        fg_modifier = (stats.field_goal_pct - 0.45) * 50  # 45% = neutral

    three_modifier = 0.0
    if stats.three_point_pct:
        three_modifier = (stats.three_point_pct - 0.35) * 30  # 35% = neutral

    efficiency_bonus = max(-10, min(15, fg_modifier + three_modifier))

    raw_sci = ppg_score + usage_score + assist_score + efficiency_bonus
    return max(0, min(100, raw_sci))


def calculate_rmi_nba(stats: PlayerStats) -> float:
    """
    Role Motion Index (NBA) — Dependence on motion, scheme, or teammates.

    Higher = more dependent (fragile if game flow changes).
    Lower = self-sufficient (stable but potentially capped).

    Components:
    - Starter status (role stability)
    - Games started percentage
    - Minutes variance (via trends)
    """
    base_score = 50.0

    # Starter status (affects stability)
    if stats.is_starter:
        base_score -= 15  # Starters are more stable
    else:
        base_score += 15  # Bench players are scheme-dependent

    # Games started consistency
    if stats.games_started_pct > 0.9:
        base_score -= 10  # Very consistent role
    elif stats.games_started_pct < 0.5:
        base_score += 10  # Inconsistent role

    # Minutes trend indicates role instability
    if abs(stats.minutes_trend) > 5:
        base_score += 10  # High variance = scheme dependent

    # Usage trend
    if abs(stats.usage_trend) > 3:
        base_score += 5  # Usage volatility

    return max(0, min(100, base_score))


def calculate_gis_nba(stats: PlayerStats) -> float:
    """
    Gravity Impact Score (NBA) — Defensive attention drawn.

    High GIS = bends the defense even when not scoring.

    Components:
    - Usage rate (ball demand)
    - Assists (creates for others)
    - Three-point shooting (stretches floor)
    """
    # Usage contribution (0-35 points)
    usage_score = min(35, stats.usage_rate * 1.2) if stats.usage_rate else 0

    # Playmaking gravity (0-25 points)
    assist_gravity = min(25, stats.assists_per_game * 2.5)

    # Shooting gravity (0-25 points)
    # Good three-point shooters demand attention
    shooting_gravity = 0.0
    if stats.three_point_pct and stats.three_point_pct > 0.33:
        shooting_gravity = min(25, (stats.three_point_pct - 0.33) * 150)

    # Scoring volume gravity (0-15 points)
    volume_gravity = min(15, stats.points_per_game * 0.5)

    raw_gis = usage_score + assist_gravity + shooting_gravity + volume_gravity
    return max(0, min(100, raw_gis))


# =============================================================================
# INDEX CALCULATIONS - NFL
# =============================================================================


def calculate_sci_nfl(stats: PlayerStats) -> float:
    """
    Space Creation Index (NFL) — How a player generates usable space.

    For receivers: Route separation, YAC potential
    For RBs: Breakaway ability, receiving work
    """
    position = stats.position.upper() if stats.position else ""

    if position in ("WR", "TE"):
        # Receivers: targets, receptions, yards
        target_score = min(30, stats.targets * 3) if stats.targets else 0
        rec_score = min(25, stats.receptions * 3) if stats.receptions else 0
        yds_score = (
            min(30, stats.receiving_yards * 0.03) if stats.receiving_yards else 0
        )

        # Catch rate bonus
        catch_rate = stats.receptions / stats.targets if stats.targets else 0
        catch_bonus = min(15, (catch_rate - 0.6) * 50) if catch_rate > 0.6 else 0

        return max(0, min(100, target_score + rec_score + yds_score + catch_bonus))

    elif position == "RB":
        # RBs: rushing + receiving versatility
        rush_score = min(35, stats.rush_yards * 0.035) if stats.rush_yards else 0
        rec_score = min(30, stats.receptions * 4) if stats.receptions else 0
        target_score = min(20, stats.targets * 2.5) if stats.targets else 0
        snap_score = min(15, stats.snap_pct * 0.15) if stats.snap_pct else 0

        return max(0, min(100, rush_score + rec_score + target_score + snap_score))

    elif position == "QB":
        # QBs: use different metrics
        return min(100, stats.usage_rate * 3) if stats.usage_rate else 50

    return 50  # Default


def calculate_rmi_nfl(stats: PlayerStats) -> float:
    """
    Role Motion Index (NFL) — Dependence on motion, scheme, or teammates.

    Components:
    - Snap percentage (role stability)
    - Target share consistency
    """
    base_score = 50.0

    # Snap percentage indicates role security
    if stats.snap_pct:
        if stats.snap_pct > 80:
            base_score -= 20  # High snap % = stable role
        elif stats.snap_pct > 60:
            base_score -= 10
        elif stats.snap_pct < 40:
            base_score += 20  # Low snap % = scheme-dependent

    # Starter status
    if stats.is_starter:
        base_score -= 10
    else:
        base_score += 15

    return max(0, min(100, base_score))


def calculate_gis_nfl(stats: PlayerStats) -> float:
    """
    Gravity Impact Score (NFL) — Defensive attention drawn.

    Components:
    - Target share
    - Yards per target/carry
    - TD potential
    """
    position = stats.position.upper() if stats.position else ""

    if position in ("WR", "TE"):
        target_gravity = min(40, stats.targets * 4) if stats.targets else 0
        yds_gravity = (
            min(35, stats.receiving_yards * 0.035) if stats.receiving_yards else 0
        )

        # Yards per target efficiency
        ypr = stats.receiving_yards / stats.receptions if stats.receptions else 0
        efficiency_gravity = min(25, ypr * 1.5) if ypr > 10 else 0

        return max(0, min(100, target_gravity + yds_gravity + efficiency_gravity))

    elif position == "RB":
        rush_gravity = min(50, stats.rush_yards * 0.05) if stats.rush_yards else 0
        rec_gravity = min(30, stats.targets * 3) if stats.targets else 0

        return max(0, min(100, rush_gravity + rec_gravity + 20))  # +20 base

    return 50


# =============================================================================
# INDEX CALCULATIONS - MLB
# =============================================================================


def calculate_sci_mlb(stats: PlayerStats) -> float:
    """
    Space Creation Index (MLB).

    Hitters: OPS-driven + SB speed + HR power.
    Pitchers: K rate + ERA dominance.
    """
    # Detect pitcher by ERA > 0 or position
    is_pitcher = stats.era > 0 or (
        stats.position and stats.position.upper() in ("P", "SP", "RP")
    )

    if is_pitcher:
        # K rate contribution (0-40)
        k_score = min(40, stats.strikeouts * 0.2)
        # ERA contribution (0-35): lower ERA = better
        era_score = max(0, min(35, (5.0 - stats.era) * 10)) if stats.era > 0 else 0
        # Wins contribution (0-25)
        win_score = min(25, stats.wins * 2.5)
        return max(0, min(100, k_score + era_score + win_score))

    # Hitter
    # OPS contribution (0-45)
    ops_score = min(45, stats.ops * 50)
    # HR power (0-25)
    hr_score = min(25, stats.home_runs * 0.7)
    # SB speed (0-15)
    sb_score = min(15, stats.stolen_bases * 0.5)
    # Batting avg floor (0-15)
    avg_score = min(15, stats.batting_avg * 50)

    return max(0, min(100, ops_score + hr_score + sb_score + avg_score))


def calculate_rmi_mlb(stats: PlayerStats) -> float:
    """
    Role Motion Index (MLB).

    Lineup position stability: starter pct, games played consistency.
    """
    base_score = 50.0

    if stats.is_starter:
        base_score -= 15
    else:
        base_score += 15

    if stats.games_started_pct > 0.9:
        base_score -= 10
    elif stats.games_started_pct < 0.5:
        base_score += 10

    # Games played consistency (out of ~162)
    if stats.games_played > 140:
        base_score -= 5  # Very durable
    elif stats.games_played < 80:
        base_score += 10  # Platoon or injured

    return max(0, min(100, base_score))


def calculate_gis_mlb(stats: PlayerStats) -> float:
    """
    Gravity Impact Score (MLB).

    Hitters: HR power + RBI gravity.
    Pitchers: K dominance + win gravity.
    """
    is_pitcher = stats.era > 0 or (
        stats.position and stats.position.upper() in ("P", "SP", "RP")
    )

    if is_pitcher:
        k_gravity = min(45, stats.strikeouts * 0.25)
        era_gravity = max(0, min(30, (4.5 - stats.era) * 10)) if stats.era > 0 else 0
        win_gravity = min(25, stats.wins * 2.0)
        return max(0, min(100, k_gravity + era_gravity + win_gravity))

    # Hitter
    hr_gravity = min(40, stats.home_runs * 1.1)
    rbi_gravity = min(30, stats.rbis * 0.3)
    ops_gravity = min(30, stats.ops * 35)

    return max(0, min(100, hr_gravity + rbi_gravity + ops_gravity))


# =============================================================================
# INDEX CALCULATIONS - NHL
# =============================================================================


def calculate_sci_nhl(stats: PlayerStats) -> float:
    """
    Space Creation Index (NHL).

    Skaters: Goals + shots + assists creation.
    Goalies: Save pct based.
    """
    is_goalie = stats.save_pct > 0 or (
        stats.position and stats.position.upper() in ("G",)
    )

    if is_goalie:
        # Goalie SCI based on save pct
        sv_score = min(80, stats.save_pct * 90) if stats.save_pct > 0 else 40
        gp_score = min(20, stats.games_played * 0.3)
        return max(0, min(100, sv_score + gp_score))

    # Skater
    goal_score = min(35, stats.goals * 1.0)
    assist_score = min(30, stats.assists_nhl * 0.7)
    shot_score = min(20, stats.shots * 0.1)
    pm_score = max(-15, min(15, stats.plus_minus * 0.5))

    return max(0, min(100, goal_score + assist_score + shot_score + pm_score))


def calculate_rmi_nhl(stats: PlayerStats) -> float:
    """
    Role Motion Index (NHL).

    Games started pct, role stability.
    """
    base_score = 50.0

    if stats.is_starter:
        base_score -= 15
    else:
        base_score += 15

    if stats.games_started_pct > 0.9:
        base_score -= 10
    elif stats.games_started_pct < 0.5:
        base_score += 10

    # Games played consistency (out of ~82)
    if stats.games_played > 70:
        base_score -= 5
    elif stats.games_played < 40:
        base_score += 10

    return max(0, min(100, base_score))


def calculate_gis_nhl(stats: PlayerStats) -> float:
    """
    Gravity Impact Score (NHL).

    Shot volume + goal threat + assist playmaking.
    """
    is_goalie = stats.save_pct > 0 or (
        stats.position and stats.position.upper() in ("G",)
    )

    if is_goalie:
        sv_gravity = min(70, stats.save_pct * 80) if stats.save_pct > 0 else 35
        gp_gravity = min(30, stats.games_played * 0.4)
        return max(0, min(100, sv_gravity + gp_gravity))

    goal_gravity = min(40, stats.goals * 1.2)
    shot_gravity = min(30, stats.shots * 0.12)
    assist_gravity = min(30, stats.assists_nhl * 0.8)

    return max(0, min(100, goal_gravity + shot_gravity + assist_gravity))


# =============================================================================
# OPPORTUNITY DELTA (All Sports)
# =============================================================================


def calculate_od(stats: PlayerStats) -> float:
    """
    Opportunity Delta — Change in role, not raw size.

    Positive = opportunity expanding
    Negative = opportunity contracting

    Range: -50 to +50

    Uses 5-game vs season comparison for minutes, usage, targets.
    """
    # Minutes trend is primary driver
    minutes_delta = stats.minutes_trend * 2.0

    # Usage/involvement trend
    if stats.sport == "nba":
        usage_delta = stats.usage_trend * 1.5
        points_delta = stats.points_trend * 0.5
        raw_od = minutes_delta + usage_delta + points_delta
    elif stats.sport == "nfl":
        # Snap % trend and target trend
        usage_delta = stats.usage_trend * 2.0
        raw_od = minutes_delta + usage_delta
    elif stats.sport == "mlb":
        # For MLB, minutes_trend maps to at-bats trend; usage to plate appearances
        usage_delta = stats.usage_trend * 1.5
        points_delta = stats.points_trend * 1.0
        raw_od = minutes_delta + usage_delta + points_delta
    elif stats.sport == "nhl":
        # TOI trend and shot trend
        usage_delta = stats.usage_trend * 1.5
        points_delta = stats.points_trend * 1.0
        raw_od = minutes_delta + usage_delta + points_delta
    else:
        raw_od = minutes_delta

    return max(-50, min(50, raw_od))


# =============================================================================
# MATCHUP SPACE FIT (All Sports)
# =============================================================================


def calculate_msf(stats: PlayerStats) -> float:
    """
    Matchup Space Fit — Does opponent allow exploitable space?

    Higher = favorable matchup for this player's skill set.

    Components:
    - Opponent defensive rating
    - Position-specific matchup data
    - Pace factor
    """
    # No matchup data = neutral
    if stats.opponent_def_rating is None and stats.opponent_vs_position is None:
        return 50.0

    base_msf = 50.0

    # Defensive rating (higher = worse defense = better matchup)
    if stats.opponent_def_rating is not None:
        if stats.sport == "nba":
            # NBA defensive rating: 100 is neutral, higher is worse
            rating_boost = (stats.opponent_def_rating - 110) * 2
            base_msf += max(-25, min(25, rating_boost))
        elif stats.sport == "mlb":
            # MLB: ERA allowed or runs allowed, higher = worse pitching
            rating_boost = (stats.opponent_def_rating - 4.5) * 8
            base_msf += max(-25, min(25, rating_boost))
        elif stats.sport == "nhl":
            # NHL: goals allowed per game, higher = worse defense
            rating_boost = (stats.opponent_def_rating - 3.0) * 10
            base_msf += max(-25, min(25, rating_boost))
        else:
            # NFL: points allowed, higher = worse defense
            rating_boost = (stats.opponent_def_rating - 25) * 1.5
            base_msf += max(-25, min(25, rating_boost))

    # Position-specific matchup (fantasy points allowed)
    if stats.opponent_vs_position is not None:
        if stats.sport == "nba":
            avg_fp = 30.0
        elif stats.sport == "mlb":
            avg_fp = 10.0
        elif stats.sport == "nhl":
            avg_fp = 8.0
        else:
            avg_fp = 15.0  # NFL

        position_boost = (stats.opponent_vs_position - avg_fp) * 1.5
        base_msf += max(-20, min(20, position_boost))

    # Pace factor (higher pace = more opportunities)
    if stats.opponent_pace is not None:
        if stats.sport == "nba":
            pace_boost = (stats.opponent_pace - 100) * 0.5
            base_msf += max(-10, min(10, pace_boost))

    return max(0, min(100, base_msf))


# =============================================================================
# UNIFIED CALCULATION INTERFACE
# =============================================================================


def calculate_sci(stats: PlayerStats) -> float:
    """Calculate SCI based on sport."""
    if stats.sport == "nfl":
        return calculate_sci_nfl(stats)
    if stats.sport == "mlb":
        return calculate_sci_mlb(stats)
    if stats.sport == "nhl":
        return calculate_sci_nhl(stats)
    return calculate_sci_nba(stats)


def calculate_rmi(stats: PlayerStats) -> float:
    """Calculate RMI based on sport."""
    if stats.sport == "nfl":
        return calculate_rmi_nfl(stats)
    if stats.sport == "mlb":
        return calculate_rmi_mlb(stats)
    if stats.sport == "nhl":
        return calculate_rmi_nhl(stats)
    return calculate_rmi_nba(stats)


def calculate_gis(stats: PlayerStats) -> float:
    """Calculate GIS based on sport."""
    if stats.sport == "nfl":
        return calculate_gis_nfl(stats)
    if stats.sport == "mlb":
        return calculate_gis_mlb(stats)
    if stats.sport == "nhl":
        return calculate_gis_nhl(stats)
    return calculate_gis_nba(stats)


def calculate_indices(stats: PlayerStats) -> IndexScores:
    """Calculate all five indices for a player."""
    return IndexScores(
        sci=calculate_sci(stats),
        rmi=calculate_rmi(stats),
        gis=calculate_gis(stats),
        od=calculate_od(stats),
        msf=calculate_msf(stats),
    )


def composite_score(indices: IndexScores, mode: RiskMode) -> float:
    """
    Calculate weighted composite score based on risk mode.

    Returns: Score from 0-100
    """
    weights = ScoringWeights.for_mode(mode)

    # Normalize OD from [-50, 50] to [0, 100]
    od_normalized = indices.od + 50

    raw_score = (
        weights.sci * indices.sci
        + weights.rmi * indices.rmi  # Note: negative weight for FLOOR mode
        + weights.gis * indices.gis
        + weights.od * od_normalized
        + weights.msf * indices.msf
    )

    # Clamp to 0-100
    return max(0, min(100, raw_score))


def compare_players(
    player_a: PlayerStats, player_b: PlayerStats, mode: RiskMode
) -> dict:
    """
    Compare two players and return a decision.

    Returns dict with:
    - decision: "Start A" or "Start B"
    - confidence: "low" | "medium" | "high"
    - score_a: float
    - score_b: float
    - margin: float
    """
    indices_a = calculate_indices(player_a)
    indices_b = calculate_indices(player_b)

    score_a = composite_score(indices_a, mode)
    score_b = composite_score(indices_b, mode)

    margin = abs(score_a - score_b)

    # Determine confidence based on margin
    if margin < 5:
        confidence = "low"
    elif margin < 15:
        confidence = "medium"
    else:
        confidence = "high"

    decision = (
        f"Start {player_a.name}" if score_a > score_b else f"Start {player_b.name}"
    )

    return {
        "decision": decision,
        "confidence": confidence,
        "score_a": round(score_a, 1),
        "score_b": round(score_b, 1),
        "margin": round(margin, 1),
        "indices_a": indices_a,
        "indices_b": indices_b,
    }
