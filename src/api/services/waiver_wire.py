"""
Waiver Wire Recommendation Service.

Analyzes a user's roster to identify position weaknesses and generates
structured waiver wire recommendations via Claude.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from services.sleeper import SleeperPlayer

# =============================================================================
# SPORT-SPECIFIC POSITION MINIMUMS
# =============================================================================

# Minimum starters per position for a healthy roster
POSITION_MINIMUMS: dict[str, dict[str, int]] = {
    "nfl": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1},
    "nba": {"PG": 1, "SG": 1, "SF": 1, "PF": 1, "C": 1},
    "mlb": {"C": 1, "1B": 1, "2B": 1, "SS": 1, "3B": 1, "OF": 3, "SP": 2, "RP": 1},
    "nhl": {"C": 1, "LW": 1, "RW": 1, "D": 2, "G": 1},
    "soccer": {"GK": 1, "DEF": 3, "MID": 3, "FWD": 1},
}

# Minimum total roster depth (starters + bench) per position
DEPTH_MINIMUMS: dict[str, dict[str, int]] = {
    "nfl": {"QB": 2, "RB": 4, "WR": 4, "TE": 2, "K": 1, "DEF": 1},
    "nba": {"PG": 2, "SG": 2, "SF": 2, "PF": 2, "C": 2},
    "mlb": {"C": 1, "1B": 1, "2B": 1, "SS": 1, "3B": 1, "OF": 4, "SP": 4, "RP": 2},
    "nhl": {"C": 2, "LW": 2, "RW": 2, "D": 4, "G": 2},
    "soccer": {"GK": 1, "DEF": 4, "MID": 4, "FWD": 2},
}


# =============================================================================
# DATACLASSES
# =============================================================================


@dataclass
class RosterAnalysis:
    """Analysis of a user's current roster composition."""

    position_counts: dict[str, int] = field(default_factory=dict)
    starters: list[dict] = field(default_factory=list)
    bench: list[dict] = field(default_factory=list)
    injured: list[dict] = field(default_factory=list)
    position_needs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "position_counts": self.position_counts,
            "starters": self.starters,
            "bench": self.bench,
            "injured": self.injured,
            "position_needs": self.position_needs,
        }


@dataclass
class WaiverCandidate:
    """A recommended waiver wire pickup."""

    name: str
    position: str
    team: str
    rationale: str
    priority: int  # 1 = highest priority

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "position": self.position,
            "team": self.team,
            "rationale": self.rationale,
            "priority": self.priority,
        }


@dataclass
class WaiverResult:
    """Complete waiver wire recommendation result."""

    roster_analysis: RosterAnalysis = field(default_factory=RosterAnalysis)
    recommendations: list[WaiverCandidate] = field(default_factory=list)
    drop_candidates: list[dict] = field(default_factory=list)
    risk_mode: str = "median"
    sport: str = "nfl"

    @property
    def confidence(self) -> str:
        if not self.recommendations:
            return "low"
        if len(self.roster_analysis.position_needs) >= 2:
            return "high"
        if self.roster_analysis.injured:
            return "high"
        return "medium"

    @property
    def rationale(self) -> str:
        if not self.recommendations:
            return "Your roster looks solid. No urgent waiver moves needed."
        top = self.recommendations[0]
        needs = self.roster_analysis.position_needs
        parts = [f"Top pickup: {top.name} ({top.position}, {top.team})."]
        if needs:
            parts.append(f" Position needs: {', '.join(needs)}.")
        if self.roster_analysis.injured:
            injured_names = [p["name"] for p in self.roster_analysis.injured]
            parts.append(f" Injured: {', '.join(injured_names)}.")
        return "".join(parts)

    def to_details_dict(self) -> dict:
        return {
            "recommendations": [r.to_dict() for r in self.recommendations],
            "drop_candidates": self.drop_candidates,
            "position_needs": self.roster_analysis.position_needs,
        }


# =============================================================================
# ROSTER ANALYSIS
# =============================================================================


def _player_dict(player: SleeperPlayer, is_starter: bool) -> dict:
    """Convert a SleeperPlayer to a summary dict."""
    return {
        "name": player.full_name,
        "position": player.position,
        "team": player.team or "?",
        "injury_status": player.injury_status,
        "is_starter": is_starter,
    }


def analyze_roster(
    players: list[SleeperPlayer],
    starter_ids: set[str],
    sport: str,
) -> RosterAnalysis:
    """
    Analyze roster composition and identify position needs.

    Args:
        players: List of SleeperPlayer objects on the roster
        starter_ids: Set of player IDs that are starters
        sport: Sport key (nfl, nba, etc.)

    Returns:
        RosterAnalysis with position counts, injured players, and needs
    """
    position_counts: dict[str, int] = {}
    starters: list[dict] = []
    bench: list[dict] = []
    injured: list[dict] = []

    for player in players:
        pos = player.position
        if not pos:
            continue

        position_counts[pos] = position_counts.get(pos, 0) + 1
        is_starter = player.player_id in starter_ids

        info = _player_dict(player, is_starter)

        if is_starter:
            starters.append(info)
        else:
            bench.append(info)

        if player.injury_status:
            injured.append(info)

    # Identify position needs by comparing against depth minimums
    depth_mins = DEPTH_MINIMUMS.get(sport, {})
    position_needs: list[str] = []

    for pos, min_count in depth_mins.items():
        current = position_counts.get(pos, 0)
        if current < min_count:
            position_needs.append(pos)

    # Also flag positions where a starter is injured
    starter_positions_injured: set[str] = set()
    for p in injured:
        if p["is_starter"]:
            starter_positions_injured.add(p["position"])

    for pos in starter_positions_injured:
        if pos not in position_needs:
            position_needs.append(pos)

    return RosterAnalysis(
        position_counts=position_counts,
        starters=starters,
        bench=bench,
        injured=injured,
        position_needs=position_needs,
    )


def build_waiver_prompt(
    analysis: RosterAnalysis,
    sport: str,
    risk_mode: str,
    query: str,
    position_filter: str | None = None,
) -> str:
    """
    Build a structured prompt for Claude to generate waiver recommendations.

    Returns a prompt string with roster context and position needs.
    """
    roster_lines = []
    for p in analysis.starters:
        injury = f" ({p['injury_status']})" if p["injury_status"] else ""
        roster_lines.append(f"  [STARTER] {p['name']} ({p['position']}, {p['team']}){injury}")
    for p in analysis.bench:
        injury = f" ({p['injury_status']})" if p["injury_status"] else ""
        roster_lines.append(f"  [BENCH]   {p['name']} ({p['position']}, {p['team']}){injury}")

    roster_text = "\n".join(roster_lines) if roster_lines else "  (empty roster)"

    needs_text = (
        ", ".join(analysis.position_needs) if analysis.position_needs else "None identified"
    )

    injured_text = "None"
    if analysis.injured:
        injured_text = ", ".join(
            f"{p['name']} ({p['position']}, {p['injury_status']})" for p in analysis.injured
        )

    position_instruction = ""
    if position_filter:
        position_instruction = f"\nFocus specifically on {position_filter} recommendations."

    return f"""You are a fantasy {sport.upper()} waiver wire expert analyzing in {risk_mode} risk mode.

User's question: {query}

CURRENT ROSTER:
{roster_text}

POSITION COUNTS: {analysis.position_counts}
POSITION NEEDS: {needs_text}
INJURED PLAYERS: {injured_text}
{position_instruction}
Based on this roster analysis, recommend the top waiver wire pickups available in most leagues.
Consider current trends, matchups, and the user's specific roster needs.

You MUST respond with valid JSON in this exact format:
{{
  "recommendations": [
    {{
      "name": "Player Name",
      "position": "POS",
      "team": "TEAM",
      "rationale": "Why this player helps this roster",
      "priority": 1
    }}
  ],
  "drop_candidates": [
    {{
      "name": "Player Name",
      "position": "POS",
      "reason": "Why this player can be dropped"
    }}
  ],
  "summary": "Brief overall waiver strategy summary"
}}

Provide 3-5 recommendations sorted by priority (1 = most important).
If the roster has droppable players, suggest 1-2 drop candidates.
Tailor recommendations to the {risk_mode} risk mode."""
