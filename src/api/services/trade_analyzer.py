"""
Trade Analyzer Service.

Parses trade queries, scores multi-player trades locally using the core
scoring engine, and provides structured trade evaluation results.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.scoring import IndexScores, PlayerStats, RiskMode
from core.scoring import evaluate_trade as core_evaluate_trade

# =============================================================================
# DATACLASSES
# =============================================================================


@dataclass
class PlayerBreakdown:
    """Scoring breakdown for a single player in a trade."""

    name: str
    team: str
    score: float
    indices: IndexScores

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
class TradeSide:
    """One side of a trade (giving or receiving)."""

    players: list[PlayerBreakdown] = field(default_factory=list)

    @property
    def total_score(self) -> float:
        return round(sum(p.score for p in self.players), 1)

    @property
    def player_count(self) -> int:
        return len(self.players)

    @property
    def player_names(self) -> list[str]:
        return [p.name for p in self.players]


@dataclass
class TradeResult:
    """Complete trade evaluation result."""

    side_giving: TradeSide
    side_receiving: TradeSide
    risk_mode: str
    sport: str

    @property
    def net_value(self) -> float:
        return round(self.side_receiving.total_score - self.side_giving.total_score, 1)

    @property
    def decision(self) -> str:
        return "Accept Trade" if self.net_value > 0 else "Reject Trade"

    @property
    def confidence(self) -> str:
        player_count = self.side_giving.player_count + self.side_receiving.player_count
        avg_margin = abs(self.net_value) / max(player_count, 1)
        if avg_margin < 3:
            return "low"
        elif avg_margin < 8:
            return "medium"
        return "high"

    @property
    def rationale(self) -> str:
        giving_names = ", ".join(self.side_giving.player_names)
        receiving_names = ", ".join(self.side_receiving.player_names)
        direction = "favors accepting" if self.net_value > 0 else "favors rejecting"
        return (
            f"Trade {direction}: receiving [{receiving_names}] "
            f"({self.side_receiving.total_score}) vs giving [{giving_names}] "
            f"({self.side_giving.total_score}), "
            f"net value {self.net_value:+.1f} ({self.risk_mode} mode)."
        )

    def to_details_dict(self) -> dict:
        return {
            "side_giving": {
                "players": [
                    {
                        "name": p.name,
                        "team": p.team,
                        "score": p.score,
                        "indices": p.indices_dict,
                    }
                    for p in self.side_giving.players
                ],
                "total_score": self.side_giving.total_score,
            },
            "side_receiving": {
                "players": [
                    {
                        "name": p.name,
                        "team": p.team,
                        "score": p.score,
                        "indices": p.indices_dict,
                    }
                    for p in self.side_receiving.players
                ],
                "total_score": self.side_receiving.total_score,
            },
            "net_value": self.net_value,
            "margin": abs(self.net_value),
            "risk_mode": self.risk_mode,
            "sport": self.sport,
        }


# =============================================================================
# QUERY PARSING
# =============================================================================

# Patterns: "trade X for Y", "give up X for Y", "should I trade X for Y",
#           "receive Y for X"
_TRADE_PATTERNS = [
    # "trade X for Y" / "should I trade X for Y"
    re.compile(
        r"(?:should\s+I\s+)?trade\s+(.+?)\s+for\s+(.+?)(?:\?|$)",
        re.IGNORECASE,
    ),
    # "give up X for Y" / "giving up X for Y"
    re.compile(
        r"giv(?:e|ing)\s+up\s+(.+?)\s+for\s+(.+?)(?:\?|$)",
        re.IGNORECASE,
    ),
    # "receive Y for X" — note: reversed capture groups
    re.compile(
        r"receive\s+(.+?)\s+for\s+(.+?)(?:\?|$)",
        re.IGNORECASE,
    ),
]

# Index of patterns where group order is (receiving, giving) instead of (giving, receiving)
_REVERSED_PATTERNS = {2}  # "receive Y for X" — Y is receiving, X is giving


def _split_player_names(raw: str) -> list[str]:
    """Split a comma/and/+/&-separated string into individual player names."""
    # Normalize separators to commas
    normalized = re.sub(r"\s+and\s+|\s*\+\s*|\s*&\s*", ",", raw, flags=re.IGNORECASE)
    names = [name.strip() for name in normalized.split(",")]
    return [n for n in names if n]


def extract_trade_players(query: str) -> tuple[list[str], list[str]] | None:
    """
    Extract (giving, receiving) player lists from a trade query.

    Returns None if query doesn't match any trade pattern.
    """
    for idx, pattern in enumerate(_TRADE_PATTERNS):
        match = pattern.search(query)
        if match:
            group_a = match.group(1).strip()
            group_b = match.group(2).strip()

            if idx in _REVERSED_PATTERNS:
                # "receive Y for X" → giving=X, receiving=Y
                giving = _split_player_names(group_b)
                receiving = _split_player_names(group_a)
            else:
                giving = _split_player_names(group_a)
                receiving = _split_player_names(group_b)

            if giving and receiving:
                return giving, receiving

    return None


# =============================================================================
# SERVICE CLASS
# =============================================================================


class TradeAnalyzer:
    """Evaluates multi-player trades using the core scoring engine."""

    def analyze(
        self,
        giving: list[PlayerStats],
        receiving: list[PlayerStats],
        mode: RiskMode,
        sport: str,
    ) -> TradeResult:
        """Score all players and build a TradeResult."""
        result = core_evaluate_trade(giving, receiving, mode)

        side_giving = TradeSide(
            players=[
                PlayerBreakdown(
                    name=p["name"],
                    team=giving[i].team,
                    score=p["score"],
                    indices=p["indices"],
                )
                for i, p in enumerate(result["side_a_players"])
            ]
        )

        side_receiving = TradeSide(
            players=[
                PlayerBreakdown(
                    name=p["name"],
                    team=receiving[i].team,
                    score=p["score"],
                    indices=p["indices"],
                )
                for i, p in enumerate(result["side_b_players"])
            ]
        )

        return TradeResult(
            side_giving=side_giving,
            side_receiving=side_receiving,
            risk_mode=mode.value,
            sport=sport,
        )

    def can_analyze_locally(
        self,
        giving_data: list[tuple | None],
        receiving_data: list[tuple | None],
    ) -> bool:
        """Check if all ESPN lookups succeeded (no None entries)."""
        return all(d is not None for d in giving_data) and all(
            d is not None for d in receiving_data
        )


# Global singleton
trade_analyzer = TradeAnalyzer()
