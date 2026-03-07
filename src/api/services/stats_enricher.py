"""
Advanced stats enrichment — wires Basketball Reference & Pro Football Reference
into the player context sent to Claude.

Gracefully degrades: returns None on any error or timeout.
"""

from __future__ import annotations

import asyncio
import logging

from services.reference import (
    AdvancedNBAStats,
    AdvancedNFLStats,
    bball_ref_service,
    pfr_service,
)

logger = logging.getLogger(__name__)

_ENRICHMENT_TIMEOUT = 5.0  # seconds


def format_nba_advanced(stats: AdvancedNBAStats) -> str:
    """Format NBA advanced stats into a single context line."""
    parts: list[str] = []
    if stats.per:
        parts.append(f"PER {stats.per:.1f}")
    if stats.true_shooting_pct:
        parts.append(f"TS% {stats.true_shooting_pct:.3f}")
    if stats.win_shares:
        parts.append(f"WS {stats.win_shares:.1f}")
    if stats.bpm:
        parts.append(f"BPM {stats.bpm:+.1f}")
    if stats.vorp:
        parts.append(f"VORP {stats.vorp:.1f}")
    if not parts:
        return ""
    return f"- Advanced: {', '.join(parts)}"


def format_nfl_advanced(stats: AdvancedNFLStats) -> str:
    """Format NFL advanced stats into a single context line."""
    parts: list[str] = []
    if stats.passer_rating:
        parts.append(f"RTG {stats.passer_rating:.1f}")
    if stats.qbr:
        parts.append(f"QBR {stats.qbr:.1f}")
    if stats.catch_pct:
        parts.append(f"Catch% {stats.catch_pct:.1f}")
    if stats.yards_after_catch:
        parts.append(f"YAC {stats.yards_after_catch:.0f}")
    if stats.approximate_value:
        parts.append(f"AV {stats.approximate_value}")
    if not parts:
        return ""
    return f"- Advanced: {', '.join(parts)}"


async def _fetch_nba_context(player_name: str) -> str | None:
    """Look up NBA advanced stats and return a formatted line."""
    slug = await bball_ref_service.search_player_slug(player_name)
    if not slug:
        return None
    stats = await bball_ref_service.get_advanced_stats(slug)
    if not stats:
        return None
    line = format_nba_advanced(stats)
    return line or None


async def _fetch_nfl_context(player_name: str) -> str | None:
    """Look up NFL advanced stats and return a formatted line."""
    slug = await pfr_service.search_player_slug(player_name)
    if not slug:
        return None
    stats = await pfr_service.get_advanced_stats(slug)
    if not stats:
        return None
    line = format_nfl_advanced(stats)
    return line or None


async def get_advanced_context(player_name: str, sport: str) -> str | None:
    """
    Fetch advanced stats for a player from reference sites.

    Returns a formatted context line (e.g. "- Advanced: PER 24.3, TS% .612")
    or None if unavailable. Never raises — all exceptions are caught.
    Enforces a 5-second total timeout.
    """
    try:
        if sport == "nba":
            return await asyncio.wait_for(
                _fetch_nba_context(player_name),
                timeout=_ENRICHMENT_TIMEOUT,
            )
        elif sport == "nfl":
            return await asyncio.wait_for(
                _fetch_nfl_context(player_name),
                timeout=_ENRICHMENT_TIMEOUT,
            )
        return None
    except Exception:
        logger.debug(
            "Advanced stats enrichment failed for %s (%s)",
            player_name,
            sport,
            exc_info=True,
        )
        return None
