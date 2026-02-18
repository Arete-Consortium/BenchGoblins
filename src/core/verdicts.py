"""
BenchGoblins Verdict Engine

Generates multi-mode start/sit verdicts by scoring both players across
all three risk modes (Floor, Median, Ceiling) simultaneously.
"""

from dataclasses import dataclass

from core.scoring import (
    IndexScores,
    PlayerStats,
    RiskMode,
    calculate_indices,
    composite_score,
)


@dataclass
class RiskBreakdown:
    """Scores for a single risk mode."""

    score_a: float
    score_b: float
    winner: str
    margin: float


@dataclass
class Verdict:
    """Full start/sit verdict across all risk modes."""

    decision: str  # "Start Patrick Mahomes"
    confidence: int  # 0-100
    floor: RiskBreakdown
    median: RiskBreakdown
    ceiling: RiskBreakdown
    indices_a: IndexScores
    indices_b: IndexScores
    player_a_name: str
    player_b_name: str
    margin: float  # Average margin across modes


def _margin_to_confidence(avg_margin: float) -> int:
    """Map average margin to 0-100 confidence score.

    0 margin → 0 confidence
    5 margin → 33
    15 margin → 67
    25+ margin → 100
    """
    if avg_margin <= 0:
        return 0
    if avg_margin >= 25:
        return 100
    return min(100, int(avg_margin * 4))


def _make_breakdown(
    score_a: float, score_b: float, name_a: str, name_b: str
) -> RiskBreakdown:
    """Build a RiskBreakdown from two scores."""
    winner = name_a if score_a >= score_b else name_b
    return RiskBreakdown(
        score_a=round(score_a, 1),
        score_b=round(score_b, 1),
        winner=winner,
        margin=round(abs(score_a - score_b), 1),
    )


def generate_verdict(player_a: PlayerStats, player_b: PlayerStats) -> Verdict:
    """Generate a full start/sit verdict across all risk modes.

    Calculates indices once per player (mode-independent), then computes
    composite scores for Floor, Median, and Ceiling. Winner is determined
    by majority of modes, with Median as tiebreaker.
    """
    # Indices are mode-independent — calculate once
    indices_a = calculate_indices(player_a)
    indices_b = calculate_indices(player_b)

    # Score across all 3 risk modes
    floor_a = composite_score(indices_a, RiskMode.FLOOR)
    floor_b = composite_score(indices_b, RiskMode.FLOOR)
    median_a = composite_score(indices_a, RiskMode.MEDIAN)
    median_b = composite_score(indices_b, RiskMode.MEDIAN)
    ceiling_a = composite_score(indices_a, RiskMode.CEILING)
    ceiling_b = composite_score(indices_b, RiskMode.CEILING)

    name_a = player_a.name
    name_b = player_b.name

    # Build breakdowns
    floor = _make_breakdown(floor_a, floor_b, name_a, name_b)
    median = _make_breakdown(median_a, median_b, name_a, name_b)
    ceiling = _make_breakdown(ceiling_a, ceiling_b, name_a, name_b)

    # Determine winner by majority of modes, median as tiebreaker
    a_wins = sum(1 for bd in (floor, median, ceiling) if bd.winner == name_a)
    winner = name_a if a_wins >= 2 else name_b

    # Average margin across all 3 modes
    avg_margin = (floor.margin + median.margin + ceiling.margin) / 3

    return Verdict(
        decision=f"Start {winner}",
        confidence=_margin_to_confidence(avg_margin),
        floor=floor,
        median=median,
        ceiling=ceiling,
        indices_a=indices_a,
        indices_b=indices_b,
        player_a_name=name_a,
        player_b_name=name_b,
        margin=round(avg_margin, 1),
    )
