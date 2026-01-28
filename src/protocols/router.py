"""Protocol for query classification."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from services.router import QueryComplexity


@runtime_checkable
class QueryClassifier(Protocol):
    """Structural interface for query routing/classification."""

    def classify_query(
        self,
        query: str,
        decision_type: str,
        player_a: str | None = None,
        player_b: str | None = None,
    ) -> QueryComplexity: ...
