"""Protocol interface contracts for BenchGoblins components."""

from protocols.intelligence import IntelligenceBackend
from protocols.router import QueryClassifier
from protocols.scoring import StatsProvider

__all__ = [
    "IntelligenceBackend",
    "QueryClassifier",
    "StatsProvider",
]
