"""Protocol for AI decision backends."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Protocol, runtime_checkable


@runtime_checkable
class IntelligenceBackend(Protocol):
    """Structural interface for AI-powered decision services."""

    async def make_decision(
        self,
        query: str,
        sport: str,
        risk_mode: str,
        decision_type: str,
        player_a: str | None = None,
        player_b: str | None = None,
        league_type: str | None = None,
        player_context: str | None = None,
        use_cache: bool = True,
        prompt_variant: str = "control",
    ) -> dict: ...

    async def make_decision_stream(
        self,
        query: str,
        sport: str,
        risk_mode: str,
        decision_type: str,
        player_a: str | None = None,
        player_b: str | None = None,
        league_type: str | None = None,
        player_context: str | None = None,
        prompt_variant: str = "control",
    ) -> AsyncGenerator[str, None]: ...
