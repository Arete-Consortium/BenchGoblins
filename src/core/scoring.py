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
    """Core stats used for index calculations"""
    # Identity
    player_id: str
    name: str
    team: str
    position: str
    
    # Volume metrics
    minutes_per_game: float
    usage_rate: float
    
    # Recent trends (last 5-10 games)
    minutes_trend: float  # Positive = increasing, negative = decreasing
    usage_trend: float
    
    # Role indicators
    is_starter: bool
    games_started_last_10: int
    
    # Matchup context (populated per-game)
    opponent_def_rating: Optional[float] = None
    opponent_pace: Optional[float] = None


@dataclass
class IndexScores:
    """The five qualitative indices for a player"""
    sci: float  # Space Creation Index (0-100)
    rmi: float  # Role Motion Index (0-100, higher = more dependent on scheme)
    gis: float  # Gravity Impact Score (0-100)
    od: float   # Opportunity Delta (-50 to +50)
    msf: float  # Matchup Space Fit (0-100)


@dataclass 
class ScoringWeights:
    """Risk mode determines weighting of each index"""
    sci: float
    rmi: float
    gis: float
    od: float
    msf: float
    
    @classmethod
    def for_mode(cls, mode: RiskMode) -> "ScoringWeights":
        """Get weights for a given risk mode"""
        if mode == RiskMode.FLOOR:
            # Prioritize stability, penalize volatility
            return cls(sci=0.15, rmi=-0.25, gis=0.10, od=0.20, msf=0.30)
        elif mode == RiskMode.CEILING:
            # Prioritize upside, accept volatility
            return cls(sci=0.30, rmi=0.10, gis=0.25, od=0.20, msf=0.15)
        else:  # MEDIAN
            # Balanced
            return cls(sci=0.20, rmi=0.00, gis=0.20, od=0.30, msf=0.30)


def calculate_sci(stats: PlayerStats) -> float:
    """
    Space Creation Index — How a player generates usable space.
    
    Higher = creates own opportunities independent of volume.
    
    TODO: Implement sport-specific calculations
    - NBA: Drives per game, pull-up shooting %, off-ball movement metrics
    - NFL: Route separation, yards after catch, alignment versatility
    - MLB: Sprint speed, stolen base success rate
    - NHL: Zone entry success, skating speed metrics
    """
    # Placeholder: Base on usage rate as proxy
    return min(100, stats.usage_rate * 3)


def calculate_rmi(stats: PlayerStats) -> float:
    """
    Role Motion Index — Dependence on motion, scheme, or teammates.
    
    Higher = more dependent (fragile if game flow changes).
    Lower = self-sufficient (stable but potentially capped).
    
    TODO: Implement sport-specific calculations
    - NBA: % of shots assisted, off-ball vs on-ball scoring split
    - NFL: Motion snap %, scheme target share
    - MLB: RBI opportunities (lineup protection)
    - NHL: Power play vs even strength production split
    """
    # Placeholder: Starter status as stability proxy
    starter_bonus = -20 if stats.is_starter else 20
    return 50 + starter_bonus


def calculate_gis(stats: PlayerStats) -> float:
    """
    Gravity Impact Score — Defensive attention drawn.
    
    High GIS = bends the defense even when not scoring.
    
    TODO: Implement sport-specific calculations
    - NBA: Double team frequency, hockey assists, screen assists
    - NFL: Coverage shell changes, safety rotation
    - MLB: Walk rate, intentional walks
    - NHL: Shot attempts against when on ice
    """
    # Placeholder: Usage as proxy for attention
    return min(100, stats.usage_rate * 2.5)


def calculate_od(stats: PlayerStats) -> float:
    """
    Opportunity Delta — Change in role, not raw size.
    
    Positive = opportunity expanding
    Negative = opportunity contracting
    
    Range: -50 to +50
    """
    # Combine minute trend and usage trend
    minutes_delta = stats.minutes_trend * 2  # Weight minutes heavily
    usage_delta = stats.usage_trend * 1.5
    
    raw_od = minutes_delta + usage_delta
    return max(-50, min(50, raw_od))


def calculate_msf(stats: PlayerStats) -> float:
    """
    Matchup Space Fit — Does opponent allow exploitable space?
    
    Higher = favorable matchup for this player's skill set.
    
    TODO: Implement sport-specific calculations
    - NBA: Opponent drop vs switch tendency, pace differential
    - NFL: Zone vs man coverage %, linebacker speed
    - MLB: Park factors, pitcher handedness
    - NHL: Forecheck aggressiveness, goalie save %
    """
    if stats.opponent_def_rating is None:
        return 50  # Neutral if no matchup data
    
    # Placeholder: Weaker defense = better matchup
    # Def rating of 110 = bad defense = good matchup
    # Def rating of 105 = good defense = tough matchup
    return min(100, max(0, (stats.opponent_def_rating - 100) * 10))


def calculate_indices(stats: PlayerStats) -> IndexScores:
    """Calculate all five indices for a player"""
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
    od_normalized = (indices.od + 50)
    
    raw_score = (
        weights.sci * indices.sci +
        weights.rmi * indices.rmi +  # Note: negative weight for FLOOR mode
        weights.gis * indices.gis +
        weights.od * od_normalized +
        weights.msf * indices.msf
    )
    
    # Clamp to 0-100
    return max(0, min(100, raw_score))


def compare_players(
    player_a: PlayerStats,
    player_b: PlayerStats,
    mode: RiskMode
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
    
    decision = f"Start {player_a.name}" if score_a > score_b else f"Start {player_b.name}"
    
    return {
        "decision": decision,
        "confidence": confidence,
        "score_a": round(score_a, 1),
        "score_b": round(score_b, 1),
        "margin": round(margin, 1),
        "indices_a": indices_a,
        "indices_b": indices_b,
    }
