"""Protocol for stats/scoring providers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.scoring import IndexScores, PlayerStats, RiskMode


@runtime_checkable
class StatsProvider(Protocol):
    """Structural interface for player stats and scoring."""

    def calculate_indices(self, stats: PlayerStats) -> IndexScores: ...
    def composite_score(self, indices: IndexScores, mode: RiskMode) -> float: ...
    def compare_players(
        self, player_a: PlayerStats, player_b: PlayerStats, mode: RiskMode
    ) -> dict: ...
