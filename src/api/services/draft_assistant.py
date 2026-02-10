"""
Draft Assistant Service.

Parses draft queries, ranks player pools locally using the core scoring engine,
and provides structured draft pick recommendations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.scoring import IndexScores, PlayerStats, RiskMode
from core.scoring import rank_players as core_rank_players

# =============================================================================
# DATACLASSES
# =============================================================================


@dataclass
class DraftPick:
    """Scoring breakdown for a single player in a draft pool."""

    rank: int
    name: str
    team: str
    position: str
    score: float
    base_score: float
    indices: IndexScores
    position_boosted: bool

    @property
    def indices_dict(self) -> dict[str, float]:
        return {
            "sci": round(self.indices.sci, 1),
            "rmi": round(self.indices.rmi, 1),
            "gis": round(self.indices.gis, 1),
            "od": round(self.indices.od, 1),
            "msf": round(self.indices.msf, 1),
        }


@dataclass
class DraftResult:
    """Complete draft evaluation result."""

    ranked_players: list[DraftPick] = field(default_factory=list)
    risk_mode: str = "median"
    sport: str = "nba"
    position_needs: list[str] | None = None

    @property
    def recommended_pick(self) -> DraftPick | None:
        return self.ranked_players[0] if self.ranked_players else None

    @property
    def confidence(self) -> str:
        if len(self.ranked_players) < 2:
            return "low"
        margin = self.ranked_players[0].score - self.ranked_players[1].score
        if margin < 3:
            return "low"
        elif margin < 10:
            return "medium"
        return "high"

    @property
    def rationale(self) -> str:
        if not self.ranked_players:
            return "No players to evaluate."
        top = self.ranked_players[0]
        parts = [
            f"Recommended pick: {top.name} ({top.position}, {top.team}) "
            f"with score {top.score:.1f}"
        ]
        if top.position_boosted:
            parts.append(" (boosted for position need)")
        if len(self.ranked_players) >= 2:
            runner = self.ranked_players[1]
            margin = top.score - runner.score
            parts.append(
                f" over {runner.name} ({runner.score:.1f}), "
                f"margin {margin:+.1f} ({self.risk_mode} mode)."
            )
        else:
            parts.append(f" ({self.risk_mode} mode).")
        return "".join(parts)

    def to_details_dict(self) -> dict:
        return {
            "ranked_players": [
                {
                    "rank": p.rank,
                    "name": p.name,
                    "team": p.team,
                    "position": p.position,
                    "score": p.score,
                    "base_score": p.base_score,
                    "indices": p.indices_dict,
                    "position_boosted": p.position_boosted,
                }
                for p in self.ranked_players
            ],
            "risk_mode": self.risk_mode,
            "sport": self.sport,
            "position_needs": self.position_needs,
        }


# =============================================================================
# QUERY PARSING
# =============================================================================

# Patterns: "pick from X, Y, Z", "choose from X, Y", "who should I draft: X, Y",
#           "rank X, Y, Z", "draft X or Y"
_DRAFT_PATTERNS = [
    # "pick from X, Y, Z" / "choose from X, Y"
    re.compile(
        r"(?:pick|choose)\s+from\s+(.+?)(?:\?|$)",
        re.IGNORECASE,
    ),
    # "who should I draft: X, Y" / "who should I draft X, Y"
    re.compile(
        r"who\s+should\s+I\s+draft[:\s]+(.+?)(?:\?|$)",
        re.IGNORECASE,
    ),
    # "rank X, Y, Z"
    re.compile(
        r"rank\s+(.+?)(?:\?|$)",
        re.IGNORECASE,
    ),
    # "draft X or Y" / "draft X, Y, or Z"
    re.compile(
        r"draft\s+(.+?)(?:\?|$)",
        re.IGNORECASE,
    ),
]


def _split_draft_names(raw: str) -> list[str]:
    """Split a comma/and/or/+/&-separated string into individual player names."""
    normalized = re.sub(
        r"\s+and\s+|\s+or\s+|\s*\+\s*|\s*&\s*", ",", raw, flags=re.IGNORECASE
    )
    names = [name.strip() for name in normalized.split(",")]
    return [n for n in names if n]


def extract_draft_players(query: str) -> list[str] | None:
    """
    Extract a list of player names from a draft query.

    Returns None if fewer than 2 players are found.
    """
    for pattern in _DRAFT_PATTERNS:
        match = pattern.search(query)
        if match:
            names = _split_draft_names(match.group(1).strip())
            if len(names) >= 2:
                return names

    return None


# =============================================================================
# SERVICE CLASS
# =============================================================================


class DraftAssistant:
    """Ranks player pools for draft pick recommendations using the core scoring engine."""

    def analyze(
        self,
        players: list[PlayerStats],
        mode: RiskMode,
        sport: str,
        position_needs: list[str] | None = None,
    ) -> DraftResult:
        """Score and rank all players, returning a DraftResult."""
        ranked = core_rank_players(players, mode, position_needs=position_needs)

        picks = [
            DraftPick(
                rank=entry["rank"],
                name=entry["name"],
                team=entry["team"],
                position=entry["position"],
                score=entry["score"],
                base_score=entry["base_score"],
                indices=entry["indices"],
                position_boosted=entry["position_boosted"],
            )
            for entry in ranked
        ]

        return DraftResult(
            ranked_players=picks,
            risk_mode=mode.value,
            sport=sport,
            position_needs=position_needs,
        )

    def can_analyze_locally(self, player_data: list[tuple | None]) -> bool:
        """Check if all ESPN lookups succeeded (no None entries)."""
        return all(d is not None for d in player_data)


# Global singleton
draft_assistant = DraftAssistant()
